"""
Knowledge Context — 图投影与图遍历 (plan.md §4.1.1, §4.1.2)。

GraphProjectionService: 消费 MemoryEdgeAdded/MemoryEdgeRemoved 事件，
  幂等写入图存储 (Apache AGE / PostgreSQL 邻接表)。

GraphTraversalChannel: 实现 GraphMemoryFetcher Protocol，
  基于 PostgreSQL 递归 CTE 的 BFS 多跳遍历。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.types import MemoryId

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class GraphStoreLike(Protocol):
    """图存储抽象 (AGE 或 PostgreSQL 邻接表)。"""

    async def merge_edge(
        self,
        source_id: MemoryId,
        target_id: MemoryId,
        relation_type: str,
        *,
        tx: Any = None,
    ) -> None:
        """幂等写入边 (MERGE 语义)。"""
        ...

    async def remove_edge(
        self,
        source_id: MemoryId,
        target_id: MemoryId,
        relation_type: str,
        *,
        tx: Any = None,
    ) -> None:
        """删除边。"""
        ...

    async def bfs_neighbors(
        self,
        seed_ids: set[MemoryId],
        depth: int,
        edge_types: set[str] | None = None,
        *,
        tx: Any = None,
    ) -> set[MemoryId]:
        """BFS 多跳邻居 (排除种子自身)。"""
        ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


# ---------------------------------------------------------------------------
# 图遍历边类型
# ---------------------------------------------------------------------------

TRAVERSABLE_EDGE_TYPES = {"depends", "derived", "causal"}


# ---------------------------------------------------------------------------
# GraphProjectionService (plan.md §4.1.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectionResult:
    """图投影结果。"""

    edges_merged: int = 0
    edges_removed: int = 0


class GraphProjectionService:
    """幂等图投影消费者。

    消费 MemoryEdgeAdded / MemoryEdgeRemoved 事件，
    将变更同步到图存储。

    幂等保证：MERGE 语义确保重复事件不会产生重复边。
    """

    def __init__(
        self,
        *,
        graph_store: GraphStoreLike,
        tx_manager: TransactionManagerLike,
    ):
        self._store = graph_store
        self._tx = tx_manager

    async def on_edge_added(
        self,
        source_id: MemoryId,
        target_id: MemoryId,
        relation_type: str,
    ) -> ProjectionResult:
        """处理 MemoryEdgeAdded 事件。"""
        async with self._tx.transaction() as tx:
            await self._store.merge_edge(
                source_id, target_id, relation_type, tx=tx,
            )

        logger.debug(
            "Graph projection: edge added %s -[%s]-> %s",
            source_id, relation_type, target_id,
        )
        return ProjectionResult(edges_merged=1)

    async def on_edge_removed(
        self,
        source_id: MemoryId,
        target_id: MemoryId,
        relation_type: str,
    ) -> ProjectionResult:
        """处理 MemoryEdgeRemoved 事件。"""
        async with self._tx.transaction() as tx:
            await self._store.remove_edge(
                source_id, target_id, relation_type, tx=tx,
            )

        logger.debug(
            "Graph projection: edge removed %s -[%s]-> %s",
            source_id, relation_type, target_id,
        )
        return ProjectionResult(edges_removed=1)

    async def project_batch(
        self,
        events: list[dict[str, Any]],
    ) -> ProjectionResult:
        """批量投影 (用于 IdempotentProjectionConsumer)。

        events 格式: [{"action": "added"|"removed", "source_id": ..., ...}]
        """
        merged = 0
        removed = 0

        async with self._tx.transaction() as tx:
            for evt in events:
                action = evt.get("action")
                source_id = evt["source_id"]
                target_id = evt["target_id"]
                relation_type = evt["relation_type"]

                if action == "added":
                    await self._store.merge_edge(
                        source_id, target_id, relation_type, tx=tx,
                    )
                    merged += 1
                elif action == "removed":
                    await self._store.remove_edge(
                        source_id, target_id, relation_type, tx=tx,
                    )
                    removed += 1

        logger.info(
            "Graph batch projection: %d merged, %d removed", merged, removed,
        )
        return ProjectionResult(edges_merged=merged, edges_removed=removed)


# ---------------------------------------------------------------------------
# GraphTraversalChannel (plan.md §4.1.2)
# ---------------------------------------------------------------------------


class GraphTraversalChannel:
    """图遍历召回通道 — 实现 GraphMemoryFetcher Protocol。

    基于 PostgreSQL 递归 CTE 的 BFS 多跳遍历。
    沿 Depends/Derived/Causal 边 BFS 2 跳。
    超时 500ms 降级 (由 RecallChannelOrchestrator 管理)。
    """

    DEFAULT_DEPTH = 2

    def __init__(self, *, graph_store: GraphStoreLike):
        self._store = graph_store

    async def fetch_graph_neighbors(
        self,
        seed_ids: set[MemoryId],
        depth: int = DEFAULT_DEPTH,
    ) -> set[MemoryId]:
        """BFS 多跳遍历获取邻居节点。

        Args:
            seed_ids: 种子 Memory ID 集合 (通常来自 scope 通道)
            depth: 遍历深度 (默认 2)

        Returns:
            邻居 Memory ID 集合 (不含种子自身)
        """
        if not seed_ids:
            return set()

        neighbors = await self._store.bfs_neighbors(
            seed_ids,
            depth=depth,
            edge_types=TRAVERSABLE_EDGE_TYPES,
        )

        logger.debug(
            "Graph traversal: %d seeds -> %d neighbors (depth=%d)",
            len(seed_ids), len(neighbors), depth,
        )
        return neighbors
