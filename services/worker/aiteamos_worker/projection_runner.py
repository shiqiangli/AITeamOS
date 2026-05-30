"""
Worker — Projection Runner。

消费 Kafka topic，按事件类型路由到已注册的 IdempotentProjectionConsumer 实例。
支持 aiokafka 消费者集成，无 aiokafka 时降级为 no-op 等待循环。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


class ProjectionRunner:
    """Consume Kafka events and dispatch to registered projection consumers.

    Supports event-type routing: consumers register for specific event types,
    and only receive matching events.

    Usage::

        runner = ProjectionRunner(db=db, kafka_bootstrap="localhost:9092")
        runner.register_for_event_types(
            GraphEdgeProjection(db=db),
            ["knowledge.memory_edge.added", "knowledge.memory_edge.removed"],
        )
        await runner.run(stop_event=event)
    """

    def __init__(
        self, *, db: Any, topic: str = "domain-events", kafka_bootstrap: str = ""
    ):
        self._db = db
        self._topic = topic
        self._kafka_bootstrap = kafka_bootstrap
        self._catch_all: list[IdempotentProjectionConsumer] = []
        # event_type -> list of consumers interested in that type
        self._routes: dict[str, list[IdempotentProjectionConsumer]] = defaultdict(list)

    @property
    def _consumers(self) -> list[IdempotentProjectionConsumer]:
        """All registered consumers (catch-all + routed, deduplicated)."""
        seen: set[str] = set()
        result: list[IdempotentProjectionConsumer] = []
        for c in self._catch_all:
            if c.consumer_id not in seen:
                seen.add(c.consumer_id)
                result.append(c)
        for consumers in self._routes.values():
            for c in consumers:
                if c.consumer_id not in seen:
                    seen.add(c.consumer_id)
                    result.append(c)
        return result

    def register(self, consumer: IdempotentProjectionConsumer) -> None:
        """Register a consumer that receives ALL events (catch-all)."""
        self._catch_all.append(consumer)
        logger.info(
            "ProjectionRunner: registered catch-all consumer '%s'",
            consumer.consumer_id,
        )

    def register_for_event_types(
        self,
        consumer: IdempotentProjectionConsumer,
        event_types: list[str],
    ) -> None:
        """Register a consumer for specific event types only."""
        for et in event_types:
            self._routes[et].append(consumer)
        logger.info(
            "ProjectionRunner: registered consumer '%s' for event types %s",
            consumer.consumer_id,
            event_types,
        )

    async def run(self, *, stop_event: asyncio.Event) -> None:
        """Main loop: consume Kafka events and dispatch to consumers.

        If aiokafka is available and kafka_bootstrap is set, uses a real
        Kafka consumer loop. Otherwise falls back to a no-op wait.
        """
        if not self._consumers:
            logger.info(
                "ProjectionRunner: no consumers registered, waiting for stop signal..."
            )
            await stop_event.wait()
            return

        logger.info(
            "ProjectionRunner: running with %d consumer(s), %d route(s)",
            len(self._consumers),
            len(self._routes),
        )

        kafka_consumer = self._create_kafka_consumer()
        if kafka_consumer is not None:
            await self._run_kafka_loop(kafka_consumer, stop_event)
        else:
            logger.info(
                "ProjectionRunner: Kafka unavailable, waiting for stop signal "
                "(use dispatch() for in-process events)"
            )
            await stop_event.wait()

        logger.info("ProjectionRunner: stopped")

    async def dispatch(self, event: VersionedDomainEvent) -> None:
        """Dispatch an event to matching registered consumers.

        Routed consumers only receive events they subscribed for.
        Catch-all consumers receive every event.
        """
        targets = list(self._routes.get(event.event_type, []))
        # Add catch-all consumers (avoid duplicates)
        seen_ids = {c.consumer_id for c in targets}
        for c in self._catch_all:
            if c.consumer_id not in seen_ids:
                targets.append(c)

        for consumer in targets:
            try:
                await consumer.consume(event)
            except Exception:
                logger.exception(
                    "ProjectionRunner: consumer '%s' failed for event %s",
                    consumer.consumer_id,
                    event.event_type,
                )

    # -- Internal --

    def _create_kafka_consumer(self) -> Any:
        """Try to create an aiokafka consumer; return None if unavailable."""
        if not self._kafka_bootstrap:
            return None
        try:
            from aiokafka import AIOKafkaConsumer

            return AIOKafkaConsumer(
                self._topic,
                bootstrap_servers=self._kafka_bootstrap,
                group_id="aiteamos-projections",
                auto_offset_reset="earliest",
                value_deserializer=lambda m: json.loads(m),
            )
        except ImportError:
            logger.warning(
                "aiokafka not installed; ProjectionRunner runs in dispatch-only mode. "
                "Install with: pip install aiokafka"
            )
            return None

    async def _run_kafka_loop(
        self, kafka_consumer: Any, stop_event: asyncio.Event
    ) -> None:
        """Consume Kafka messages and dispatch events until stop."""
        await kafka_consumer.start()
        try:
            async for msg in kafka_consumer:
                if stop_event.is_set():
                    break
                try:
                    data = msg.value
                    # Reconstruct event from JSON payload
                    event = VersionedDomainEvent.model_validate(data)
                    await self.dispatch(event)
                except Exception:
                    logger.exception(
                        "ProjectionRunner: failed to process message at "
                        "offset=%s partition=%s",
                        msg.offset,
                        msg.partition,
                    )
        finally:
            await kafka_consumer.stop()
