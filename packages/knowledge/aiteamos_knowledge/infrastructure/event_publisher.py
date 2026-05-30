"""
Knowledge Context — Event Publisher。

基于 OutboxWriter 发布领域事件，保证与聚合操作同事务。
"""

from __future__ import annotations

import logging
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.outbox import OutboxWriter

logger = logging.getLogger(__name__)


class KnowledgeEventPublisher:
    """Knowledge Context 事件发布器。

    将领域事件通过 OutboxWriter 写入 outbox 表，
    保证与聚合状态变更同事务（纪律 #3）。
    """

    def __init__(self, *, outbox_writer: OutboxWriter):
        self._writer = outbox_writer

    async def publish_events(
        self,
        events: list[VersionedDomainEvent],
        *,
        partition_key: str,
        tx: Any,
    ) -> None:
        """批量发布领域事件到 Outbox。

        Args:
            events: 待发布的事件列表
            partition_key: Kafka 分区键（通常为聚合 ID）
            tx: 数据库事务上下文
        """
        for event in events:
            await self._writer.write(
                event,
                partition_key=partition_key,
                tx=tx,
            )
            logger.debug(
                "Published event %s (partition=%s)",
                event.event_type,
                partition_key,
            )

    async def publish_event(
        self,
        event: VersionedDomainEvent,
        *,
        partition_key: str,
        tx: Any,
    ) -> None:
        """发布单个领域事件到 Outbox。"""
        await self._writer.write(
            event,
            partition_key=partition_key,
            tx=tx,
        )
