"""
Knowledge Context — Command Handlers (CQRS write side).

每个 Handler 负责:
1. 从仓储加载聚合
2. 执行不变量校验
3. 修改聚合状态
4. 发出领域事件（通过 Outbox 同事务写入）
5. 保存聚合
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.outbox import OutboxWriter
from aiteamos_shared.types import MemberId, MemoryId, new_id

from ..domain.events import (
    MemoryEdgeAdded,
    MemoryEdgeRemoved,
    MemoryNodeCreated,
)
from ..domain.invariants import (
    InvariantViolationError,
    validate_confidence_value,
)
from ..domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryEdge,
    MemoryNode,
    Provenance,
    RelationType,
    Scope,
    ScopeKind,
    SourceKind,
    Tier,
)
from .commands import (
    AppendMemoryVersionCommand,
    ChangeLifecycleCommand,
    CreateMemoryEdgeCommand,
    CreateMemoryNodeCommand,
    DeprecateMemoryNodeCommand,
    MergeMemoryNodesCommand,
    RemoveMemoryEdgeCommand,
    UpdateMemoryContentCommand,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class MemoryNodeRepoLike(Protocol):
    async def get_by_id(self, id: Any, *, tx: Any = None) -> MemoryNode | None: ...
    async def save(self, aggregate: MemoryNode, *, tx: Any = None) -> None: ...
    async def lock_for_update(self, id: Any, *, tx: Any) -> MemoryNode | None: ...


class MemoryEdgeRepoLike(Protocol):
    async def get_by_id(self, id: Any, *, tx: Any = None) -> MemoryEdge | None: ...
    async def save(self, aggregate: MemoryEdge, *, tx: Any = None) -> None: ...
    async def delete(self, edge_id: UUID, *, tx: Any = None) -> None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


class CreateMemoryNodeHandler:
    """处理 CreateMemoryNodeCommand。"""

    def __init__(
        self,
        *,
        node_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = node_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: CreateMemoryNodeCommand) -> MemoryNode:
        """创建 Memory 节点并发出 MemoryNodeCreated 事件。"""
        validate_confidence_value(cmd.initial_confidence)

        content = MemoryContent(
            statement=cmd.statement,
            applicable_when=cmd.applicable_when,
            counter_example=cmd.counter_example,
            tags=cmd.tags,
        )
        provenance = Provenance(
            source_kind=cmd.source_kind,
            task_id=cmd.task_id,
            run_id=cmd.run_id,
            member_id=cmd.member_id,
            system_meta=cmd.system_meta,
        )
        confidence = Confidence(
            value=cmd.initial_confidence,
            state=ConfidenceState.NEEDS_VERIFY,
        )
        scope = Scope(kind=cmd.scope_kind, ref=cmd.scope_ref)

        node = MemoryNode(
            tier=cmd.tier,
            scope=scope,
            title=cmd.title,
            content=content,
            confidence=confidence,
            provenance=provenance,
            lifecycle=LifecycleState.CANDIDATE,
        )

        created_event = MemoryNodeCreated(
            event_type="knowledge.memory_node.created",
            memory_id=node.id,
            tier=node.tier.value,
            title=node.title,
            provenance_source_kind=provenance.source_kind.value,
        )

        async with self._tx.transaction() as tx:
            await self._repo.save(node, tx=tx)
            all_events = [created_event] + node.pending_events
            node.clear_pending_events()
            await self._publisher.publish_events(
                all_events, partition_key=str(node.id), tx=tx
            )

        logger.info("Created MemoryNode %s (tier=%s)", node.id, node.tier.value)
        return node


class UpdateMemoryContentHandler:
    """处理 UpdateMemoryContentCommand。"""

    def __init__(
        self,
        *,
        node_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = node_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: UpdateMemoryContentCommand) -> MemoryNode:
        async with self._tx.transaction() as tx:
            node = await self._repo.lock_for_update(cmd.memory_id, tx=tx)
            if node is None:
                raise ValueError(f"MemoryNode {cmd.memory_id} not found")

            new_content = MemoryContent(
                statement=cmd.statement,
                applicable_when=cmd.applicable_when,
                counter_example=cmd.counter_example,
                tags=cmd.tags,
            )
            node.update_content(
                new_content,
                reason=cmd.reason,
                author_member_id=cmd.author_member_id,
            )

            await self._repo.save(node, tx=tx)
            events = node.pending_events
            node.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(node.id), tx=tx
            )

        return node


class AppendMemoryVersionHandler:
    """处理 AppendMemoryVersionCommand。"""

    def __init__(
        self,
        *,
        node_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = node_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: AppendMemoryVersionCommand) -> MemoryNode:
        async with self._tx.transaction() as tx:
            node = await self._repo.lock_for_update(cmd.memory_id, tx=tx)
            if node is None:
                raise ValueError(f"MemoryNode {cmd.memory_id} not found")

            node.append_version(
                diff=cmd.diff,
                reason=cmd.reason,
                author_member_id=cmd.author_member_id,
            )

            await self._repo.save(node, tx=tx)
            events = node.pending_events
            node.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(node.id), tx=tx
            )

        return node


class ChangeLifecycleHandler:
    """处理 ChangeLifecycleCommand。"""

    def __init__(
        self,
        *,
        node_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = node_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: ChangeLifecycleCommand) -> MemoryNode:
        async with self._tx.transaction() as tx:
            node = await self._repo.lock_for_update(cmd.memory_id, tx=tx)
            if node is None:
                raise ValueError(f"MemoryNode {cmd.memory_id} not found")

            node.change_lifecycle(cmd.new_state)

            await self._repo.save(node, tx=tx)
            events = node.pending_events
            node.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(node.id), tx=tx
            )

        return node


class DeprecateMemoryNodeHandler:
    """处理 DeprecateMemoryNodeCommand。"""

    def __init__(
        self,
        *,
        node_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = node_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: DeprecateMemoryNodeCommand) -> MemoryNode:
        async with self._tx.transaction() as tx:
            node = await self._repo.lock_for_update(cmd.memory_id, tx=tx)
            if node is None:
                raise ValueError(f"MemoryNode {cmd.memory_id} not found")

            node.deprecate()

            await self._repo.save(node, tx=tx)
            events = node.pending_events
            node.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(node.id), tx=tx
            )

        return node


class CreateMemoryEdgeHandler:
    """处理 CreateMemoryEdgeCommand。

    I-K-5: Edge 创建不锁定 source/target MemoryNode。
    """

    def __init__(
        self,
        *,
        edge_repo: MemoryEdgeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = edge_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: CreateMemoryEdgeCommand) -> MemoryEdge:
        edge = MemoryEdge(
            source_id=cmd.source_id,
            target_id=cmd.target_id,
            relation_type=cmd.relation_type,
            weight=cmd.weight,
            created_by=cmd.created_by,
        )

        event = MemoryEdgeAdded(
            event_type="knowledge.memory_edge.added",
            edge_id=edge.edge_id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_type=edge.relation_type.value,
        )

        async with self._tx.transaction() as tx:
            await self._repo.save(edge, tx=tx)
            await self._publisher.publish_events(
                [event], partition_key=str(edge.source_id), tx=tx
            )

        logger.info(
            "Created MemoryEdge %s (%s -> %s)",
            edge.edge_id,
            edge.source_id,
            edge.target_id,
        )
        return edge


class RemoveMemoryEdgeHandler:
    """处理 RemoveMemoryEdgeCommand。

    I-K-5: Edge 删除不锁定 source/target MemoryNode。
    """

    def __init__(
        self,
        *,
        edge_repo: MemoryEdgeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = edge_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: RemoveMemoryEdgeCommand) -> None:
        async with self._tx.transaction() as tx:
            edge = await self._repo.get_by_id(cmd.edge_id, tx=tx)
            if edge is None:
                raise ValueError(f"MemoryEdge {cmd.edge_id} not found")

            event = MemoryEdgeRemoved(
                event_type="knowledge.memory_edge.removed",
                edge_id=edge.edge_id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                relation_type=edge.relation_type.value,
            )

            await self._repo.delete(cmd.edge_id, tx=tx)
            await self._publisher.publish_events(
                [event], partition_key=str(edge.source_id), tx=tx
            )

        logger.info("Removed MemoryEdge %s", cmd.edge_id)


class MergeMemoryNodesHandler:
    """处理 MergeMemoryNodesCommand。

    将多个 source Memory 合并到 target。
    1. 将 source 的 tags 合并到 target
    2. 追加版本记录说明合并来源
    3. 将 source 标记为 deprecated
    """

    def __init__(
        self,
        *,
        node_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = node_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: MergeMemoryNodesCommand) -> MemoryNode:
        async with self._tx.transaction() as tx:
            target = await self._repo.lock_for_update(cmd.target_id, tx=tx)
            if target is None:
                raise ValueError(f"Target MemoryNode {cmd.target_id} not found")

            merged_tags = set(target.content.tags)
            merged_statements = []

            for source_id in cmd.source_ids:
                source = await self._repo.lock_for_update(source_id, tx=tx)
                if source is None:
                    raise ValueError(f"Source MemoryNode {source_id} not found")

                merged_tags.update(source.content.tags)
                merged_statements.append(source.content.statement)
                source.deprecate()
                await self._repo.save(source, tx=tx)

                source_events = source.pending_events
                source.clear_pending_events()
                await self._publisher.publish_events(
                    source_events, partition_key=str(source.id), tx=tx
                )

            # 更新 target
            new_content = MemoryContent(
                statement=target.content.statement,
                applicable_when=target.content.applicable_when,
                counter_example=target.content.counter_example,
                tags=list(merged_tags),
            )
            target.update_content(
                new_content,
                reason=f"Merge from {[str(s) for s in cmd.source_ids]}: {cmd.reason}",
                author_member_id=cmd.author_member_id,
            )

            await self._repo.save(target, tx=tx)
            events = target.pending_events
            target.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(target.id), tx=tx
            )

        return target
