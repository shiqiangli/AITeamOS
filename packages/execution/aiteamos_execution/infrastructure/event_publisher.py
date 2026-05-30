"""
Execution Context — Event Publisher。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.outbox import OutboxWriter

logger = logging.getLogger(__name__)


class ExecutionEventPublisher:
    """Execution Context 事件发布器。"""

    def __init__(self, *, outbox_writer: OutboxWriter):
        self._writer = outbox_writer

    async def publish_events(
        self,
        events: list[VersionedDomainEvent],
        *,
        partition_key: str,
        tx: Any,
    ) -> None:
        for event in events:
            await self._writer.write(event, partition_key=partition_key, tx=tx)
            logger.debug("Published event %s (partition=%s)", event.event_type, partition_key)
