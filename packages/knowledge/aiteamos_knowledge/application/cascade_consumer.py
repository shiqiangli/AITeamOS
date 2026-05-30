"""
Knowledge Context — Cascade Invalidation Consumer (arch.md §2.7)。

消费 memory_node.lifecycle_changed 事件，
当 Memory 进入 needs_verify/deprecated 状态时触发级联失效。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

from .cascade_invalidation import CascadeInvalidationService, StructuralChangeEvent

logger = logging.getLogger(__name__)


class CascadeInvalidationConsumer(IdempotentProjectionConsumer):
    """消费 lifecycle_changed 事件，按需触发级联失效。

    仅在 new_state 为 needs_verify 或 deprecated 时触发，
    其他状态变更忽略。
    """

    consumer_id = "cascade-invalidation-v1"

    TRIGGER_STATES = {"needs_verify", "deprecated"}

    def __init__(
        self, *, db: Any, cascade_service: CascadeInvalidationService
    ) -> None:
        super().__init__(db)
        self._service = cascade_service

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        """lifecycle_changed → 若 new_state 在触发集合中则启动级联。"""
        if event.event_type != "knowledge.memory_node.lifecycle_changed":
            return

        data = event.model_dump()
        new_state = data.get("new_state", "")
        if new_state not in self.TRIGGER_STATES:
            return

        memory_id = data.get("memory_id")
        if not memory_id:
            return

        structural_event = StructuralChangeEvent(
            event_type="knowledge.cascade.structural_change",
            changed_anchors=[str(memory_id)],
            triggered_by="lifecycle_change",
        )

        result = await self._service.on_structural_change(structural_event)

        logger.info(
            "CascadeInvalidation: memory %s -> %s, impacted %d nodes (overflow=%s)",
            memory_id,
            new_state,
            result.impacted_count,
            result.overflow,
        )
