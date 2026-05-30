"""
Knowledge Context — Review → Memory Bridge (H5).

Consumes ``governance.review_case.decision_made`` events and creates
Memory candidates from review findings (reason + correction).

PRD §3.1.1: "Review 过程中发现的问题，生成 Memory 候选（必须包含 reason + correction）"
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer
from aiteamos_shared.types import new_id

from ..domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryNode,
    Provenance,
    Scope,
    ScopeKind,
    SourceKind,
    Tier,
)
from .extraction import EventPublisherLike, MemoryNodeRepoLike, TransactionManagerLike

logger = logging.getLogger(__name__)


class ReviewMemoryExtractor(IdempotentProjectionConsumer):
    """Consume ReviewDecisionMade events → create Memory proposals.

    When a review decision includes a non-empty ``reason``, the finding is
    converted into a Memory candidate with ``source_kind=REVIEW_FINDING``.

    consumer_id is unique for idempotent offset tracking.
    """

    consumer_id = "review-memory-extract-v1"

    def __init__(
        self,
        *,
        memory_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
        db: Any,
    ):
        super().__init__(db=db)
        self._repo = memory_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        if event.event_type != "governance.review_case.decision_made":
            return

        data = event.model_dump()
        verdict = data.get("verdict", "")
        reason = data.get("reason", "")

        # Only extract from reviews that found issues
        if not reason:
            logger.debug("ReviewMemoryExtractor: no reason in review, skipping")
            return

        # Build Memory candidate from review finding
        target_kind = data.get("target_kind", "task_deliverable")
        target_id = data.get("target_id", "")
        review_case_id = data.get("review_case_id", "")

        title = f"Review finding: {reason[:80]}"
        statement = reason

        content = MemoryContent(
            statement=statement,
            applicable_when=f"Relevant to {target_kind} reviews",
            counter_example="",
            tags=["review-finding", target_kind],
        )

        provenance = Provenance(
            source_kind=SourceKind.REVIEW,
            task_id=target_id if target_kind in ("task", "task_deliverable") else "",
            run_id="",
            member_id=str(data.get("reviewer_member_id", "")),
            system_meta=True,  # Prevent recursive extraction (PRD §3.1.3)
        )

        confidence = Confidence(
            value=Decimal("0.500"),
            state=ConfidenceState.NEEDS_VERIFY,
            last_updated=datetime.now(timezone.utc),
            last_decay_at=datetime.now(timezone.utc),
        )

        node = MemoryNode(
            id=new_id(),
            tier=Tier.FACTS,
            scope=Scope(kind=ScopeKind.GLOBAL, ref=None),
            title=title,
            content=content,
            confidence=confidence,
            provenance=provenance,
            lifecycle=LifecycleState.CANDIDATE,
        )

        try:
            async with self._tx.transaction() as tx:
                await self._repo.save(node, tx=tx)

                events = node.pending_events
                node.clear_pending_events()
                if events:
                    await self._publisher.publish_events(
                        events,
                        partition_key=str(review_case_id),
                        tx=tx,
                    )

            logger.info(
                "ReviewMemoryExtractor: created Memory candidate %s from review %s",
                node.id, review_case_id,
            )
        except Exception:
            logger.exception(
                "ReviewMemoryExtractor: failed to create candidate from review %s",
                review_case_id,
            )
