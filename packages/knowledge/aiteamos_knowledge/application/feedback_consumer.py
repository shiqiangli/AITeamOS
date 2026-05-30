"""
Knowledge Context — Feedback Projection Consumer (arch.md §2.2.1).

消费 Memory 反馈事件，同步到 memory_feedback 读侧表，
驱动置信度演进 (positive → boost, negative → decay)。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


class FeedbackConsumer(IdempotentProjectionConsumer):
    """消费 Knowledge 反馈事件，维护 memory_feedback 投影。

    处理事件:
    - knowledge.memory_feedback.recorded  → INSERT feedback row + update confidence
    """

    consumer_id = "feedback-v1"

    _INSERT_FEEDBACK = """
        INSERT INTO memory_feedback (
            id, memory_id, task_run_id, outcome, delta,
            reviewer_member_id, occurred_at, is_system_meta
        ) VALUES ($1, $2, $3, $4, $5, $6, now(), $7)
        ON CONFLICT (id) DO NOTHING
    """

    _UPDATE_CONFIDENCE = """
        UPDATE memory_node
        SET confidence_value = GREATEST(0.0, LEAST(1.0, confidence_value + $2)),
            last_decay_at = now()
        WHERE id = $1
    """

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        data = event.model_dump()
        et = event.event_type

        if et != "knowledge.memory_feedback.recorded":
            logger.debug("FeedbackConsumer: ignoring %s", et)
            return

        from uuid import uuid4

        feedback_id = uuid4()
        memory_id = data["memory_id"]
        task_run_id = data["task_run_id"]
        outcome = data.get("outcome", "neutral")
        delta = float(data.get("delta", 0.0))
        is_system_meta = bool(data.get("is_system_meta", False))

        # Insert feedback record
        await self._db.execute(
            self._INSERT_FEEDBACK,
            feedback_id,
            memory_id,
            task_run_id,
            outcome,
            delta,
            None,  # reviewer_member_id (populated from task context if available)
            is_system_meta,
        )

        # Apply confidence delta
        if delta != 0.0:
            await self._db.execute(
                self._UPDATE_CONFIDENCE,
                memory_id,
                delta,
            )
            logger.info(
                "Feedback: memory %s outcome=%s delta=%.3f",
                memory_id,
                outcome,
                delta,
            )
