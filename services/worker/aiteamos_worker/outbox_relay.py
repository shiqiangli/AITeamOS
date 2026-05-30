"""
Worker — Outbox Relay 运行器。

封装 shared_kernel 的 OutboxRelay，提供 Worker 进程级别的配置和生命周期管理。
多实例分片加固在 Stage 4.6 实现 (arch.md §6.1)。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.outbox import OutboxRelay as _SharedOutboxRelay

logger = logging.getLogger(__name__)


class WorkerOutboxRelay:
    """Worker-level wrapper for the OutboxRelay.

    Provides configuration injection and lifecycle management.
    The actual relay logic lives in ``aiteamos_shared.outbox.OutboxRelay``.
    """

    def __init__(
        self,
        *,
        db: Any,
        kafka_producer: Any,
        topic: str = "domain-events",
        batch_size: int = 100,
        poll_interval: float = 0.5,
    ):
        self._relay = _SharedOutboxRelay(
            db=db,
            kafka_producer=kafka_producer,
            topic=topic,
            batch_size=batch_size,
            poll_interval=poll_interval,
        )

    async def run(self) -> None:
        """Start the relay loop."""
        logger.info("WorkerOutboxRelay: starting")
        await self._relay.run()

    def stop(self) -> None:
        """Signal the relay to stop."""
        self._relay.stop()
        logger.info("WorkerOutboxRelay: stopped")
