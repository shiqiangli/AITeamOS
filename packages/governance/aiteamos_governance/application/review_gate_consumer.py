"""
Governance Context — Review Gate Projection Consumer (arch.md §2.2.6).

消费审核生命周期事件，维护 review_case 读侧投影，
并在审核决策后驱动跨上下文门控 (Task → Review → Continue)。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


class ReviewGateConsumer(IdempotentProjectionConsumer):
    """消费 Governance 审核事件，维护 review_case 投影。

    处理事件:
    - governance.review_case.created        → INSERT review_case row
    - governance.review_case.decision_made  → UPDATE verdict/reason/decision_at
    - governance.conflict_case.detected     → INSERT conflict_case row
    - governance.conflict_case.resolved     → UPDATE resolution/resolved_at
    """

    consumer_id = "review-gate-v1"

    _UPSERT_REVIEW = """
        INSERT INTO review_case (
            id, target_kind, target_id, reviewer_member_id, created_at
        ) VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (id) DO NOTHING
    """

    _UPDATE_REVIEW_VERDICT = """
        UPDATE review_case
        SET verdict = $2, reason = $3, decision_at = now()
        WHERE id = $1
    """

    _UPSERT_CONFLICT = """
        INSERT INTO conflict_case (
            id, memory_a_id, memory_b_id, conflict_kind, detected_by, detected_at
        ) VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (id) DO NOTHING
    """

    _UPDATE_CONFLICT_RESOLVED = """
        UPDATE conflict_case
        SET resolution = $2, winner_id = $3, resolved_by = $4, resolved_at = now()
        WHERE id = $1
    """

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        data = event.model_dump()
        et = event.event_type

        if et == "governance.review_case.created":
            await self._db.execute(
                self._UPSERT_REVIEW,
                data["review_case_id"],
                data["target_kind"],
                data["target_id"],
                data["reviewer_member_id"],
            )

        elif et == "governance.review_case.decision_made":
            await self._db.execute(
                self._UPDATE_REVIEW_VERDICT,
                data["review_case_id"],
                data["verdict"],
                data.get("reason", ""),
            )
            logger.info(
                "ReviewGate: case %s → %s",
                data["review_case_id"],
                data["verdict"],
            )

        elif et == "governance.conflict_case.detected":
            await self._db.execute(
                self._UPSERT_CONFLICT,
                data["conflict_case_id"],
                data["memory_a_id"],
                data["memory_b_id"],
                data["conflict_kind"],
                data["detected_by"],
            )

        elif et == "governance.conflict_case.resolved":
            await self._db.execute(
                self._UPDATE_CONFLICT_RESOLVED,
                data["conflict_case_id"],
                data["resolution"],
                data.get("winner_id"),
                data.get("resolved_by"),
            )
            logger.info(
                "ReviewGate: conflict %s → %s",
                data["conflict_case_id"],
                data["resolution"],
            )

        else:
            logger.debug("ReviewGateConsumer: ignoring %s", et)
