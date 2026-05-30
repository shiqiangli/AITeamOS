"""
Worker 进程入口 — Outbox Relay + Projection Runner。

启动方式::

    python -m aiteamos_worker

或通过 docker compose::

    docker compose up worker
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

logger = logging.getLogger(__name__)


async def _main() -> None:
    """Start the worker: Outbox Relay + Projection Runner."""
    logging.basicConfig(
        level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("AITeamOS Worker starting...")

    # --- Database ---
    dsn = os.environ.get(
        "DATABASE_URL",
        "postgresql://aiteamos:dev_password@localhost:5432/aiteamos",
    )

    # Lazy imports to avoid hard dependency on asyncpg during testing
    from aiteamos_shared.repository import create_pool

    db = await create_pool(dsn)

    # --- Kafka ---
    kafka_bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_producer = _create_kafka_producer(kafka_bootstrap)

    # --- Outbox Relay ---
    from aiteamos_shared.outbox import OutboxRelay

    relay = OutboxRelay(db=db, kafka_producer=kafka_producer)

    # --- Projection Runner ---
    from .projection_runner import ProjectionRunner

    projection_runner = ProjectionRunner(
        db=db, kafka_bootstrap=kafka_bootstrap
    )

    # --- Register projection consumers ---
    _register_projection_consumers(projection_runner, db)

    # --- Run concurrently ---
    stop_event = asyncio.Event()

    def _handle_signal():
        logger.info("Worker received shutdown signal")
        stop_event.set()
        relay.stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    logger.info("Worker started: Outbox Relay + Projection Runner")

    try:
        await asyncio.gather(
            relay.run(),
            projection_runner.run(stop_event=stop_event),
        )
    finally:
        await db.close()
        logger.info("Worker stopped")


def _register_projection_consumers(runner: Any, db: Any) -> None:
    """Register all projection consumers with the runner."""
    from aiteamos_knowledge.infrastructure.graph_store import SqlGraphStore
    from aiteamos_knowledge.infrastructure.repository import (
        PostgresMemoryNodeRepository,
    )
    from aiteamos_knowledge.application.graph_projection_consumer import (
        GraphEdgeProjectionConsumer,
    )
    from aiteamos_knowledge.application.cascade_consumer import (
        CascadeInvalidationConsumer,
    )
    from aiteamos_knowledge.application.cascade_invalidation import (
        CascadeInvalidationService,
    )
    from aiteamos_shared.outbox import OutboxWriter
    from aiteamos_knowledge.infrastructure.event_publisher import (
        KnowledgeEventPublisher,
    )

    graph_store = SqlGraphStore(db=db)

    # Graph edge projection
    graph_consumer = GraphEdgeProjectionConsumer(db=db, graph_store=graph_store)
    runner.register_for_event_types(
        graph_consumer,
        ["knowledge.memory_edge.added", "knowledge.memory_edge.removed"],
    )

    # Cascade invalidation
    memory_repo = PostgresMemoryNodeRepository(db=db)
    outbox_writer = OutboxWriter(db=db)
    event_publisher = KnowledgeEventPublisher(outbox_writer=outbox_writer)

    cascade_service = CascadeInvalidationService(
        graph_store=graph_store,
        memory_repo=memory_repo,
        tx_manager=db,
        event_publisher=event_publisher,
    )
    cascade_consumer = CascadeInvalidationConsumer(
        db=db, cascade_service=cascade_service
    )
    runner.register_for_event_types(
        cascade_consumer,
        ["knowledge.memory_node.lifecycle_changed"],
    )

    # -- Feedback consumer (knowledge) --
    from aiteamos_knowledge.application.feedback_consumer import FeedbackConsumer

    feedback_consumer = FeedbackConsumer(db=db)
    runner.register_for_event_types(
        feedback_consumer,
        ["knowledge.memory_feedback.recorded"],
    )

    # -- Task execution consumer (execution) --
    from aiteamos_execution.application.task_execution_consumer import (
        TaskExecutionConsumer,
    )

    task_exec_consumer = TaskExecutionConsumer(db=db)
    runner.register_for_event_types(
        task_exec_consumer,
        [
            "execution.task.created",
            "execution.task.state_changed",
            "execution.task.assigned",
            "execution.run.started",
            "execution.run.finished",
            "execution.task.hard_circuit_triggered",
            "execution.task.dependency_resolved",
            "execution.task.dependency_blocked",
        ],
    )

    # -- Review gate consumer (governance) --
    from aiteamos_governance.application.review_gate_consumer import ReviewGateConsumer

    review_gate_consumer = ReviewGateConsumer(db=db)
    runner.register_for_event_types(
        review_gate_consumer,
        [
            "governance.review_case.created",
            "governance.review_case.decision_made",
            "governance.conflict_case.detected",
            "governance.conflict_case.resolved",
        ],
    )

    # -- Reflection consumer (validation) --
    from aiteamos_validation.application.reflection_consumer import ReflectionConsumer

    reflection_consumer = ReflectionConsumer(db=db)
    runner.register_for_event_types(
        reflection_consumer,
        [
            "validation.harness_invocation.triggered",
            "validation.harness_invocation.completed",
            "validation.harness_invocation.expired",
            "validation.harness_adapter.registered",
            "validation.harness_adapter.health_changed",
        ],
    )

    # -- Promotion approval bridge (knowledge ← governance) --
    from aiteamos_knowledge.application.promotion_approval_bridge import (
        PromotionApprovalBridge,
    )
    from aiteamos_knowledge.application.promotion import MemoryTierPromotionService
    from aiteamos_knowledge.infrastructure.repository import (
        PostgresMemoryNodeRepository as _BridgeMemRepo,
    )

    class _NoOpFeedbackStore:
        """Minimal stub satisfying FeedbackStoreLike for approve_promotion()."""
        async def get_unique_task_count(self, memory_id): return 0
        async def get_positive_rate(self, memory_id): return 0.0
        async def get_unique_project_count(self, memory_id): return 0
        async def get_unique_department_count(self, memory_id): return 0
        async def get_consecutive_first_passes(self, memory_id): return 0

    _bridge_mem_repo = _BridgeMemRepo(db=db)
    _bridge_promotion_svc = MemoryTierPromotionService(
        memory_repo=_bridge_mem_repo,
        feedback_store=_NoOpFeedbackStore(),
        tx_manager=db,
        event_publisher=event_publisher,
    )
    promotion_bridge = PromotionApprovalBridge(
        db=db, promotion_service=_bridge_promotion_svc,
    )
    runner.register_for_event_types(
        promotion_bridge,
        ["governance.review_case.decision_made"],
    )

    # -- Skill health metric consumer (capability ← execution) --
    from aiteamos_capability.application.health_metric_consumer import (
        SkillHealthMetricConsumer,
    )

    skill_health_consumer = SkillHealthMetricConsumer(db=db)
    runner.register_for_event_types(
        skill_health_consumer,
        ["execution.run.finished"],
    )

    logger.info("Projection consumers registered")


def _create_kafka_producer(bootstrap_servers: str):
    """Create a Kafka producer (or a no-op stub if aiokafka unavailable)."""
    try:
        from aiokafka import AIOKafkaProducer

        producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
        # Note: caller must await producer.start() / producer.stop()
        return producer
    except ImportError:
        logger.warning(
            "aiokafka not installed; using NoOpKafkaProducer. "
            "Install with: pip install aiokafka"
        )
        return _NoOpKafkaProducer()


class _NoOpKafkaProducer:
    """Stub Kafka producer for environments without aiokafka."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, topic: str, value: bytes, key: str | None = None) -> None:
        logger.debug("NoOpKafkaProducer.send(topic=%s, key=%s)", topic, key)


logger = logging.getLogger(__name__)

if __name__ == "__main__":
    asyncio.run(_main())
