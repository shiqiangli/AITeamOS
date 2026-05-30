"""
Knowledge Context — 级联失效服务 (arch.md §2.7)。

CascadeInvalidationService: 事件驱动的级联失效算法。
- 消费 RepositoryStructureChanged / DependencyMajorBumped 事件
- BFS 传播 (深度 3, 每跳扇出 200, 总上限 1000)
- 超限降级为异步扫描 (DeferredCascadeRequired)
- 分批写回 (每 50 节点一个事务)
- UUID 字典序排序防死锁
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.types import MemoryId, new_id

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (arch.md §2.7)
# ---------------------------------------------------------------------------

MAX_FAN_OUT_PER_HOP = 200
MAX_TOTAL_IMPACTED = 1000
BATCH_SIZE = 50
BFS_DEPTH = 3


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CascadeResult:
    """级联失效结果。"""

    impacted_count: int = 0
    overflow: bool = False
    batches_written: int = 0
    deferred: bool = False


@dataclass(frozen=True)
class StructuralChangeEvent:
    """结构性变更事件 (触发级联失效)。"""

    event_type: str
    changed_anchors: list[str] = field(default_factory=list)
    project_id: UUID | None = None
    triggered_by: str = "unknown"


@dataclass(frozen=True)
class DeferredCascadeRequired:
    """降级事件 — 超限后由后台 Worker 异步完成。"""

    event_type: str = "knowledge.cascade.deferred"
    root_ids: list[MemoryId] = field(default_factory=list)
    already_processed: list[MemoryId] = field(default_factory=list)
    reason: str = "fan_out_exceeded"


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class CascadeGraphStoreLike(Protocol):
    """级联失效所需的图存储接口。"""

    async def bfs_dependents(
        self,
        root_id: MemoryId,
        depth: int,
        fan_limit: int,
        *,
        tx: Any = None,
    ) -> set[MemoryId]:
        """从 root_id 沿反向 DEPENDS/DERIVED 边 BFS，返回受影响节点。"""
        ...


class CascadeMemoryRepoLike(Protocol):
    """级联失效所需的 Memory 仓储接口。"""

    async def find_facts_with_anchors(
        self, anchors: list[str], *, tx: Any = None
    ) -> list[MemoryId]:
        """查找锚点匹配的 Facts 节点。"""
        ...

    async def lock_for_update(
        self, memory_id: MemoryId, *, tx: Any = None
    ) -> Any:
        """SELECT FOR UPDATE 获取 Memory 节点。"""
        ...

    async def set_needs_verify(
        self, memory_id: MemoryId, *, tx: Any = None
    ) -> None:
        """将 Memory 状态设为 needs_verify。"""
        ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


# ---------------------------------------------------------------------------
# CascadeInvalidationService (arch.md §2.7)
# ---------------------------------------------------------------------------


class CascadeInvalidationService:
    """级联失效服务。

    防爆破约束:
    - 每跳扇出 <= MAX_FAN_OUT_PER_HOP (200)
    - 总影响节点 <= MAX_TOTAL_IMPACTED (1000)
    - 超限降级为 DeferredCascadeRequired 异步事件
    - 分批写回 (BATCH_SIZE=50) 避免大事务击穿 WAL
    - UUID 字典序确定性排序防死锁
    """

    def __init__(
        self,
        *,
        graph_store: CascadeGraphStoreLike,
        memory_repo: CascadeMemoryRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._graph = graph_store
        self._repo = memory_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def on_structural_change(
        self, evt: StructuralChangeEvent
    ) -> CascadeResult:
        """处理结构性变更事件。

        Step 1: 找到根失效节点 (命中变更锚点的 Facts)
        Step 2: 沿图边反向 BFS 传播 (深度 3, 带扇出约束)
        Step 3: 超限降级 / 分批降级到 needs_verify
        """
        # Step 1: 找到根失效节点
        async with self._tx.transaction() as tx:
            roots = await self._repo.find_facts_with_anchors(
                evt.changed_anchors, tx=tx,
            )

        if not roots:
            return CascadeResult()

        # Step 2: BFS 传播
        impacted: set[MemoryId] = set()
        overflow = False

        for root_id in roots:
            impacted.add(root_id)
            overflow = await self._bfs_propagate_bounded(root_id, impacted)
            if overflow:
                break

        if overflow:
            # 降级: 发出 DeferredCascadeRequired 事件
            deferred_event = DeferredCascadeRequired(
                root_ids=list(roots),
                already_processed=list(impacted),
                reason="fan_out_exceeded",
            )

            # 先处理已收集的部分
            batches = await self._batch_invalidate(impacted, evt)

            logger.warning(
                "Cascade overflow: %d impacted, deferred %d roots",
                len(impacted), len(roots),
            )
            return CascadeResult(
                impacted_count=len(impacted),
                overflow=True,
                batches_written=batches,
                deferred=True,
            )

        # Step 3: 分批降级
        batches = await self._batch_invalidate(impacted, evt)

        logger.info(
            "Cascade invalidation: %d impacted, %d batches",
            len(impacted), batches,
        )
        return CascadeResult(
            impacted_count=len(impacted),
            overflow=False,
            batches_written=batches,
        )

    async def _bfs_propagate_bounded(
        self, root_id: MemoryId, out: set[MemoryId]
    ) -> bool:
        """带扇出限制的 BFS。返回 True 表示超出总上限需降级。"""
        frontier = {root_id}

        for _hop in range(BFS_DEPTH):
            if len(out) >= MAX_TOTAL_IMPACTED:
                return True

            next_frontier: set[MemoryId] = set()

            for node_id in frontier:
                dependents = await self._graph.bfs_dependents(
                    node_id,
                    depth=1,
                    fan_limit=MAX_FAN_OUT_PER_HOP,
                )

                for dep_id in dependents:
                    if dep_id not in out:
                        next_frontier.add(dep_id)
                        out.add(dep_id)
                        if len(out) >= MAX_TOTAL_IMPACTED:
                            return True

            frontier = next_frontier

        return False

    async def _batch_invalidate(
        self, impacted: set[MemoryId], root_cause: StructuralChangeEvent
    ) -> int:
        """分批写回 PostgreSQL。

        按 UUID 字典序确定性排序后再分批 lock_for_update，
        消除并发级联失效事件影响重叠节点时的死锁风险。
        原理：所有事务以相同顺序获取锁 -> 彻底避免循环等待。
        """
        # 确定性排序: 按 UUID 字典序
        ordered = sorted(impacted, key=lambda mid: str(mid))

        batches_written = 0
        for i in range(0, len(ordered), BATCH_SIZE):
            batch = ordered[i : i + BATCH_SIZE]

            async with self._tx.transaction() as tx:
                for mid in batch:
                    node = await self._repo.lock_for_update(mid, tx=tx)
                    if node is not None:
                        await self._repo.set_needs_verify(mid, tx=tx)

            batches_written += 1

        # 发布批量事件
        from ..domain.events import MemoryBatchNeedsVerifyEvent

        event = MemoryBatchNeedsVerifyEvent(
            event_type="knowledge.memory_batch.needs_verify",
            memory_ids=list(ordered),
            triggered_by="cascade_invalidation",
            triggered_by_system_meta=True,
        )

        async with self._tx.transaction() as tx:
            await self._publisher.publish_events(
                [event],
                partition_key=str(root_cause.project_id or "cascade"),
                tx=tx,
            )

        return batches_written
