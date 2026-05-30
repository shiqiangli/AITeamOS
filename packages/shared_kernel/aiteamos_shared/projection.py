"""
Shared Kernel — 幂等投影消费者基类 (arch.md 纪律 #10)。

所有 CQRS 读侧投影消费者必须继承 IdempotentProjectionConsumer，
基于 projection_watermark 表实现 CAS 水位推进，保证 At-least-once
投递下绝对幂等、绝对不回滚。

不变量 N6: source_event_seq 只进不退。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .events import VersionedDomainEvent

logger = logging.getLogger(__name__)


@dataclass
class ProjectionWatermark:
    """Current watermark for a projection consumer."""

    consumer_id: str
    last_event_id: str
    last_seq: int
    processed_at: datetime


class IdempotentProjectionConsumer(ABC):
    """Abstract base for all CQRS read-side projection consumers.

    Subclasses must implement :meth:`handle_event` with their specific
    projection logic. The :meth:`consume` method wraps the handler with
    CAS-based watermark checks to guarantee idempotency.

    Usage::

        class MyProjection(IdempotentProjectionConsumer):
            consumer_id = "my-projection-v1"

            async def handle_event(self, event, tx):
                # projection logic here
                ...

        # In worker:
        projection = MyProjection(db=db)
        await projection.consume(event)
    """

    consumer_id: str = ""  # Must be set by subclass

    # SQL templates
    _GET_WATERMARK = """
        SELECT last_event_id, last_seq, processed_at
        FROM projection_watermark
        WHERE consumer_id = $1
    """

    _CAS_ADVANCE = """
        INSERT INTO projection_watermark (consumer_id, last_event_id, last_seq, processed_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (consumer_id) DO UPDATE
        SET last_event_id = EXCLUDED.last_event_id,
            last_seq = EXCLUDED.last_seq,
            processed_at = now()
        WHERE projection_watermark.last_seq < EXCLUDED.last_seq
    """

    def __init__(self, db: Any):
        self._db = db

    async def consume(self, event: VersionedDomainEvent) -> bool:
        """Consume an event with idempotency guarantee.

        Returns True if the event was processed, False if it was a duplicate
        (global_seq <= current watermark).
        """
        if not self.consumer_id:
            raise ValueError(f"{type(self).__name__} must set consumer_id")

        # Check watermark — skip if event already processed
        row = await self._db.fetchrow(self._GET_WATERMARK, self.consumer_id)
        if row and row["last_seq"] >= event.global_seq:
            logger.debug(
                "Projection %s: skipping duplicate event (seq=%d <= watermark=%d)",
                self.consumer_id,
                event.global_seq,
                row["last_seq"],
            )
            return False

        # Process the event
        await self.handle_event(event)

        # CAS advance watermark — only moves forward (N6)
        await self._db.execute(
            self._CAS_ADVANCE,
            self.consumer_id,
            str(event.correlation_id),
            event.global_seq,
        )
        logger.debug(
            "Projection %s: processed event %s (seq=%d)",
            self.consumer_id,
            event.event_type,
            event.global_seq,
        )
        return True

    @abstractmethod
    async def handle_event(self, event: VersionedDomainEvent) -> None:
        """Subclass hook for actual projection logic.

        This method is only called when the event has NOT been processed
        before (global_seq > watermark). Implementations should be
        idempotent as a defense-in-depth measure.
        """
        ...
