"""
Knowledge Context — Memory Promotion Approval Bridge (arch.md §2.6.3).

消费 Governance 审核决策事件，当 target_kind=memory_promotion 且
verdict=approve 时，驱动 MemoryTierPromotionService 执行晋升。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


class PromotionApprovalBridge(IdempotentProjectionConsumer):
    """消费 review_case.decision_made 事件，驱动 Memory 晋升。

    仅在 target_kind == 'memory_promotion' 且 verdict == 'approve' 时
    调用 MemoryTierPromotionService.approve_promotion()。

    其他审核决策（reject / revise / merge）仅记录日志。
    """

    consumer_id = "promotion-approval-bridge-v1"

    def __init__(
        self, *, db: Any, promotion_service: Any
    ) -> None:
        super().__init__(db)
        self._promotion = promotion_service

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        if event.event_type != "governance.review_case.decision_made":
            return

        data = event.model_dump()
        target_kind = data.get("target_kind", "")
        verdict = data.get("verdict", "")

        if target_kind != "memory_promotion":
            return

        target_id = data.get("target_id")
        if not target_id:
            return

        if verdict != "approve":
            logger.info(
                "PromotionBridge: review %s verdict=%s (not approve), skipping",
                data.get("review_case_id"),
                verdict,
            )
            return

        approved_by = data.get("reviewer_member_id")

        try:
            await self._promotion.approve_promotion(
                target_id, approved_by=approved_by,
            )
            logger.info(
                "PromotionBridge: memory %s promoted (review %s)",
                target_id,
                data.get("review_case_id"),
            )
        except ValueError as exc:
            logger.warning(
                "PromotionBridge: promotion failed for memory %s — %s",
                target_id,
                exc,
            )
