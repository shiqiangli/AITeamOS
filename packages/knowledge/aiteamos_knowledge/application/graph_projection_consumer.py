"""
Knowledge Context — Graph Edge Projection Consumer (arch.md §2.6)。

消费 MemoryEdgeAdded / MemoryEdgeRemoved 事件，
幂等同步到图存储 (memory_edge 表)。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


class GraphEdgeProjectionConsumer(IdempotentProjectionConsumer):
    """消费 memory_edge.added / memory_edge.removed 事件，同步图存储。

    幂等保证：MERGE 语义 + CAS 水位推进 (由基类提供)。
    """

    consumer_id = "graph-edge-projection-v1"

    HANDLED_EVENT_TYPES = {
        "knowledge.memory_edge.added",
        "knowledge.memory_edge.removed",
    }

    def __init__(self, *, db: Any, graph_store: Any) -> None:
        super().__init__(db)
        self._graph = graph_store

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        """根据事件类型执行 merge_edge 或 remove_edge。"""
        if event.event_type not in self.HANDLED_EVENT_TYPES:
            return

        source_id = event.model_dump().get("source_id")
        target_id = event.model_dump().get("target_id")
        relation_type = event.model_dump().get("relation_type", "")

        if not source_id or not target_id:
            logger.warning(
                "GraphEdgeProjection: missing source_id/target_id in event %s",
                event.event_type,
            )
            return

        if event.event_type == "knowledge.memory_edge.added":
            await self._graph.merge_edge(source_id, target_id, relation_type)
            logger.debug(
                "GraphEdgeProjection: merged edge %s -[%s]-> %s",
                source_id, relation_type, target_id,
            )
        elif event.event_type == "knowledge.memory_edge.removed":
            await self._graph.remove_edge(source_id, target_id, relation_type)
            logger.debug(
                "GraphEdgeProjection: removed edge %s -[%s]-> %s",
                source_id, relation_type, target_id,
            )
