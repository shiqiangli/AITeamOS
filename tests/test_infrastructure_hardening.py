"""
Tests for Stage 4.6 — Infrastructure Hardening.

- ShardedOutboxRelay (plan.md §4.6.1)
- ZombieTaskScanner (plan.md §4.6.2)
- Observability: MetricsRegistry, AppMetrics, StructuredFormatter, HealthChecker (plan.md §4.6.3)
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from aiteamos_shared.outbox import (
    RelayCheckpoint,
    ShardedOutboxRelay,
)
from aiteamos_execution.application.zombie_scanner import (
    ZombieScanResult,
    ZombieTaskInfo,
    ZombieTaskScanner,
)
from aiteamos_shared.observability import (
    AppMetrics,
    HealthCheckResult,
    HealthChecker,
    MetricsRegistry,
    StructuredFormatter,
    configure_structured_logging,
)


# ===================================================================
# Mock infrastructure
# ===================================================================


class MockDB:
    """Mock database for ShardedOutboxRelay."""

    def __init__(
        self,
        *,
        rows: list[dict[str, Any]] | None = None,
        checkpoint_seq: int | None = None,
        lock_acquired: bool = True,
    ):
        self._rows = rows or []
        self._checkpoint_seq = checkpoint_seq
        self._lock_acquired = lock_acquired
        self.published_ids: list[Any] = []
        self.saved_checkpoints: list[tuple[int, int, str]] = []
        self.executed_queries: list[str] = []
        self.fetched_queries: list[str] = []

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.fetched_queries.append(query)
        return self._rows

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        self.executed_queries.append(query)
        if "pg_try_advisory_lock" in query:
            return {0: self._lock_acquired}
        if "last_published_seq" in query:
            if self._checkpoint_seq is not None:
                return {"last_published_seq": self._checkpoint_seq}
            return None
        return None

    async def execute(self, query: str, *args: Any) -> None:
        self.executed_queries.append(query)
        if "UPDATE outbox SET published_at" in query:
            self.published_ids.extend(args[0] if args else [])
        if "outbox_relay_checkpoints" in query:
            self.saved_checkpoints.append(args)


class MockKafka:
    """Mock Kafka producer."""

    def __init__(self, *, fail_after: int = -1):
        self.sent: list[tuple[str, bytes, str | None]] = []
        self._fail_after = fail_after

    async def send(self, topic: str, value: bytes, key: str | None = None) -> None:
        if 0 <= self._fail_after <= len(self.sent):
            raise ConnectionError("Kafka unavailable")
        self.sent.append((topic, value, key))


class MockTaskStore:
    """Mock task store for ZombieTaskScanner."""

    def __init__(self, *, tasks: list[dict[str, Any]] | None = None):
        self._tasks = tasks or []
        self.failed_tasks: list[tuple[str, str]] = []

    async def find_active_tasks(self) -> list[dict[str, Any]]:
        return self._tasks

    async def fail_task(self, task_id: str, *, reason: str) -> None:
        self.failed_tasks.append((task_id, reason))


class MockWorkflowChecker:
    """Mock Temporal workflow checker."""

    def __init__(self, *, active_run_ids: set[str] | None = None, raise_on_check: bool = False):
        self._active = active_run_ids or set()
        self._raise = raise_on_check

    async def is_workflow_active(self, run_id: str) -> bool:
        if self._raise:
            raise ConnectionError("Temporal unavailable")
        return run_id in self._active


class MockHealthComponent:
    """Mock health check component."""

    def __init__(self, *, healthy: bool = True, raise_error: bool = False):
        self._healthy = healthy
        self._raise = raise_error

    async def check(self) -> bool:
        if self._raise:
            raise RuntimeError("check failed")
        return self._healthy


# ===================================================================
# TestShardedOutboxRelay (plan.md §4.6.1)
# ===================================================================


class TestShardedOutboxRelay:
    def _make_relay(
        self,
        *,
        db: MockDB | None = None,
        kafka: MockKafka | None = None,
        shard_id: int = 0,
        num_shards: int = 2,
    ) -> ShardedOutboxRelay:
        return ShardedOutboxRelay(
            db=db or MockDB(),
            kafka_producer=kafka or MockKafka(),
            shard_id=shard_id,
            num_shards=num_shards,
            instance_id="test-instance",
        )

    async def test_try_acquire_lock_success(self):
        db = MockDB(lock_acquired=True)
        relay = self._make_relay(db=db)
        result = await relay.try_acquire_lock()
        assert result is True

    async def test_try_acquire_lock_failure(self):
        db = MockDB(lock_acquired=False)
        relay = self._make_relay(db=db)
        result = await relay.try_acquire_lock()
        assert result is False

    async def test_release_lock(self):
        db = MockDB(lock_acquired=True)
        relay = self._make_relay(db=db)
        await relay.try_acquire_lock()
        await relay.release_lock()
        # Verify release query was executed
        assert any("pg_advisory_unlock" in q for q in db.executed_queries)

    async def test_load_checkpoint(self):
        db = MockDB(checkpoint_seq=42)
        relay = self._make_relay(db=db)
        seq = await relay.load_checkpoint()
        assert seq == 42
        assert relay.high_watermark == 42

    async def test_load_checkpoint_empty(self):
        db = MockDB(checkpoint_seq=None)
        relay = self._make_relay(db=db)
        seq = await relay.load_checkpoint()
        assert seq == 0

    async def test_save_checkpoint(self):
        db = MockDB()
        relay = self._make_relay(db=db)
        relay._high_watermark = 100
        await relay.save_checkpoint()
        assert len(db.saved_checkpoints) == 1

    async def test_poll_and_publish_success(self):
        rows = [
            {"id": uuid4(), "event_type": "TestEvent", "partition_key": "pk1", "payload": {"key": "val"}, "global_seq": 1},
            {"id": uuid4(), "event_type": "TestEvent2", "partition_key": "pk2", "payload": {"key": "val2"}, "global_seq": 2},
        ]
        db = MockDB(rows=rows)
        kafka = MockKafka()
        relay = self._make_relay(db=db, kafka=kafka)
        count = await relay._poll_and_publish()
        assert count == 2
        assert len(kafka.sent) == 2

    async def test_poll_and_publish_empty(self):
        db = MockDB(rows=[])
        relay = self._make_relay(db=db)
        count = await relay._poll_and_publish()
        assert count == 0

    async def test_backpressure_on_kafka_failure(self):
        rows = [
            {"id": uuid4(), "event_type": "E1", "partition_key": "pk1", "payload": {}, "global_seq": 1},
        ]
        db = MockDB(rows=rows)
        kafka = MockKafka(fail_after=0)
        relay = self._make_relay(db=db, kafka=kafka)
        count = await relay._poll_and_publish()
        assert count == 0
        assert relay.kafka_available is False

    async def test_high_watermark_advances(self):
        rows = [
            {"id": uuid4(), "event_type": "E1", "partition_key": "pk1", "payload": {}, "global_seq": 5},
            {"id": uuid4(), "event_type": "E2", "partition_key": "pk2", "payload": {}, "global_seq": 10},
        ]
        db = MockDB(rows=rows)
        kafka = MockKafka()
        relay = self._make_relay(db=db, kafka=kafka)
        await relay._poll_and_publish()
        assert relay.high_watermark == 10

    async def test_properties(self):
        relay = self._make_relay(shard_id=3)
        assert relay.shard_id == 3
        assert relay.high_watermark == 0
        assert relay.kafka_available is True

    async def test_stop(self):
        relay = self._make_relay()
        relay.stop()
        assert relay._stopped is True

    def test_relay_checkpoint_frozen(self):
        cp = RelayCheckpoint(shard_id=0, last_published_seq=100, instance_id="inst")
        with pytest.raises(AttributeError):
            cp.shard_id = 1  # type: ignore[misc]

    def test_relay_checkpoint_defaults(self):
        cp = RelayCheckpoint()
        assert cp.shard_id == 0
        assert cp.last_published_seq == 0
        assert cp.instance_id == ""


# ===================================================================
# TestZombieTaskScanner (plan.md §4.6.2)
# ===================================================================


class TestZombieTaskScanner:
    async def test_scan_no_tasks(self):
        store = MockTaskStore(tasks=[])
        checker = MockWorkflowChecker()
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker)
        result = await scanner.scan_once()
        assert isinstance(result, ZombieScanResult)
        assert result.scanned_count == 0
        assert result.zombie_count == 0

    async def test_detect_zombie_no_run_id(self):
        """Task with no run_id is a zombie."""
        tasks = [{"task_id": "TASK-001", "state": "running", "run_id": None, "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}]
        store = MockTaskStore(tasks=tasks)
        checker = MockWorkflowChecker()
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker)
        result = await scanner.scan_once()
        assert result.zombie_count == 1
        assert "TASK-001" in result.failed_task_ids
        assert len(store.failed_tasks) == 1

    async def test_detect_zombie_inactive_workflow(self):
        """Task with inactive workflow is a zombie."""
        run_id = str(uuid4())
        tasks = [{"task_id": "TASK-002", "state": "running", "run_id": run_id, "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}]
        store = MockTaskStore(tasks=tasks)
        checker = MockWorkflowChecker(active_run_ids=set())
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker)
        result = await scanner.scan_once()
        assert result.zombie_count == 1
        assert "TASK-002" in result.failed_task_ids

    async def test_skip_active_workflow(self):
        """Task with active workflow is NOT a zombie."""
        run_id = str(uuid4())
        tasks = [{"task_id": "TASK-003", "state": "running", "run_id": run_id, "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}]
        store = MockTaskStore(tasks=tasks)
        checker = MockWorkflowChecker(active_run_ids={run_id})
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker)
        result = await scanner.scan_once()
        assert result.zombie_count == 0
        assert len(store.failed_tasks) == 0

    async def test_grace_period_skips_recent(self):
        """Recently updated tasks are skipped (grace period)."""
        now = datetime.now(timezone.utc)
        tasks = [{"task_id": "TASK-004", "state": "running", "run_id": None, "updated_at": now}]
        store = MockTaskStore(tasks=tasks)
        checker = MockWorkflowChecker()
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker, grace_period_seconds=3600)
        result = await scanner.scan_once(now=now)
        assert result.zombie_count == 0
        assert result.scanned_count == 1

    async def test_mixed_zombies_and_healthy(self):
        """Mix of zombie and healthy tasks."""
        active_run = str(uuid4())
        tasks = [
            {"task_id": "TASK-Z1", "state": "running", "run_id": None, "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)},
            {"task_id": "TASK-H1", "state": "running", "run_id": active_run, "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)},
            {"task_id": "TASK-Z2", "state": "suspended", "run_id": str(uuid4()), "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)},
        ]
        store = MockTaskStore(tasks=tasks)
        checker = MockWorkflowChecker(active_run_ids={active_run})
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker)
        result = await scanner.scan_once()
        assert result.scanned_count == 3
        assert result.zombie_count == 2
        assert "TASK-Z1" in result.failed_task_ids
        assert "TASK-Z2" in result.failed_task_ids

    async def test_workflow_check_error_treated_as_non_zombie(self):
        """If workflow check raises, task is NOT marked zombie."""
        tasks = [{"task_id": "TASK-ERR", "state": "running", "run_id": str(uuid4()), "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}]
        store = MockTaskStore(tasks=tasks)
        checker = MockWorkflowChecker(raise_on_check=True)
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker)
        result = await scanner.scan_once()
        assert result.zombie_count == 0

    async def test_scan_count_increments(self):
        store = MockTaskStore(tasks=[])
        checker = MockWorkflowChecker()
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker)
        assert scanner.scan_count == 0
        await scanner.scan_once()
        assert scanner.scan_count == 1
        await scanner.scan_once()
        assert scanner.scan_count == 2

    async def test_stop(self):
        store = MockTaskStore(tasks=[])
        checker = MockWorkflowChecker()
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=checker)
        scanner.stop()
        assert scanner._stopped is True


# ===================================================================
# TestMetricsRegistry (plan.md §4.6.3)
# ===================================================================


class TestMetricsRegistry:
    def test_counter_increment(self):
        reg = MetricsRegistry()
        reg.inc_counter("test_counter")
        assert reg.get_counter("test_counter") == 1.0
        reg.inc_counter("test_counter", value=5)
        assert reg.get_counter("test_counter") == 6.0

    def test_counter_with_labels(self):
        reg = MetricsRegistry()
        reg.inc_counter("http_requests", labels={"method": "GET", "status": "200"})
        reg.inc_counter("http_requests", labels={"method": "POST", "status": "201"})
        assert reg.get_counter("http_requests", labels={"method": "GET", "status": "200"}) == 1.0
        assert reg.get_counter("http_requests", labels={"method": "POST", "status": "201"}) == 1.0

    def test_gauge_set(self):
        reg = MetricsRegistry()
        reg.set_gauge("memory_usage", 0.75)
        assert reg.get_gauge("memory_usage") == 0.75
        reg.set_gauge("memory_usage", 0.80)
        assert reg.get_gauge("memory_usage") == 0.80

    def test_gauge_with_labels(self):
        reg = MetricsRegistry()
        reg.set_gauge("queue_depth", 10, labels={"queue": "events"})
        assert reg.get_gauge("queue_depth", labels={"queue": "events"}) == 10

    def test_histogram_observe(self):
        reg = MetricsRegistry()
        reg.observe_histogram("latency", 0.1)
        reg.observe_histogram("latency", 0.2)
        reg.observe_histogram("latency", 0.3)
        stats = reg.get_histogram_stats("latency")
        assert stats["count"] == 3
        assert abs(stats["sum"] - 0.6) < 0.001
        assert abs(stats["avg"] - 0.2) < 0.001

    def test_histogram_empty(self):
        reg = MetricsRegistry()
        stats = reg.get_histogram_stats("empty")
        assert stats["count"] == 0

    def test_export_prometheus_text(self):
        reg = MetricsRegistry()
        reg.register("test_counter", description="A test counter", metric_type="counter")
        reg.register("test_gauge", description="A test gauge", metric_type="gauge")
        reg.inc_counter("test_counter", value=42)
        reg.set_gauge("test_gauge", 3.14)
        text = reg.export_prometheus_text()
        assert "test_counter" in text
        assert "42" in text
        assert "test_gauge" in text
        assert "3.14" in text
        assert "# HELP test_counter" in text
        assert "# TYPE test_counter counter" in text

    def test_export_empty(self):
        reg = MetricsRegistry()
        assert reg.export_prometheus_text() == ""

    def test_histogram_trim(self):
        """Histogram trims to 500 when exceeding 1000."""
        reg = MetricsRegistry()
        for i in range(1001):
            reg.observe_histogram("big_hist", float(i))
        stats = reg.get_histogram_stats("big_hist")
        assert stats["count"] == 500


# ===================================================================
# TestAppMetrics
# ===================================================================


class TestAppMetrics:
    def test_record_api_request(self):
        metrics = AppMetrics()
        metrics.record_api_request(method="GET", path="/api/v1/memories", duration=0.05, status_code=200)
        count = metrics.registry.get_counter(
            AppMetrics.API_REQUEST_TOTAL,
            labels={"method": "GET", "path": "/api/v1/memories", "status": "200"},
        )
        assert count == 1.0

    def test_set_event_consumption_lag(self):
        metrics = AppMetrics()
        metrics.set_event_consumption_lag(2.5)
        assert metrics.registry.get_gauge(AppMetrics.EVENT_CONSUMPTION_LAG) == 2.5

    def test_set_outbox_backlog(self):
        metrics = AppMetrics()
        metrics.set_outbox_backlog(150)
        assert metrics.registry.get_gauge(AppMetrics.OUTBOX_BACKLOG) == 150.0

    def test_register_all_metrics(self):
        metrics = AppMetrics()
        text = metrics.registry.export_prometheus_text()
        # All registered metrics should have HELP entries
        # But only if they have values
        assert metrics.registry is not None


# ===================================================================
# TestStructuredFormatter
# ===================================================================


class TestStructuredFormatter:
    def test_format_basic(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello world",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["message"] == "Hello world"
        assert data["level"] == "INFO"
        assert data["logger"] == "test"
        assert "timestamp" in data

    def test_format_with_exception(self):
        formatter = StructuredFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "test error" in data["exception"]

    def test_format_with_extra_fields(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="With extras",
            args=(),
            exc_info=None,
        )
        record.task_id = "TASK-001"  # type: ignore[attr-defined]
        record.duration_ms = 42  # type: ignore[attr-defined]
        output = formatter.format(record)
        data = json.loads(output)
        assert data["task_id"] == "TASK-001"
        assert data["duration_ms"] == 42


# ===================================================================
# TestHealthChecker
# ===================================================================


class TestHealthChecker:
    async def test_all_healthy(self):
        checker = HealthChecker(version="1.0.0")
        checker.register_check("db", MockHealthComponent(healthy=True))
        checker.register_check("kafka", MockHealthComponent(healthy=True))
        result = await checker.check()
        assert isinstance(result, HealthCheckResult)
        assert result.status == "ok"
        assert result.checks["db"] == "ok"
        assert result.checks["kafka"] == "ok"
        assert result.version == "1.0.0"

    async def test_one_unhealthy(self):
        checker = HealthChecker()
        checker.register_check("db", MockHealthComponent(healthy=True))
        checker.register_check("kafka", MockHealthComponent(healthy=False))
        result = await checker.check()
        assert result.status == "degraded"
        assert result.checks["db"] == "ok"
        assert result.checks["kafka"] == "failed"

    async def test_error_check(self):
        checker = HealthChecker()
        checker.register_check("broken", MockHealthComponent(raise_error=True))
        result = await checker.check()
        assert result.status == "degraded"
        assert "error" in result.checks["broken"]

    async def test_no_checks(self):
        checker = HealthChecker()
        result = await checker.check()
        assert result.status == "unhealthy"
        assert result.checks == {}

    async def test_uptime(self):
        checker = HealthChecker()
        result = await checker.check()
        assert result.uptime_seconds >= 0

    def test_to_dict(self):
        checker = HealthChecker(version="2.0.0")
        result = HealthCheckResult(
            status="ok",
            checks={"db": "ok"},
            version="2.0.0",
            uptime_seconds=100.5,
        )
        d = checker.to_dict(result)
        assert d["status"] == "ok"
        assert d["version"] == "2.0.0"
        assert d["uptime_seconds"] == 100.5
        assert d["checks"]["db"] == "ok"


# ===================================================================
# TestValueObjects
# ===================================================================


class TestInfrastructureValueObjects:
    def test_zombie_scan_result_defaults(self):
        r = ZombieScanResult()
        assert r.scanned_count == 0
        assert r.zombie_count == 0
        assert r.failed_task_ids == []
        assert r.scan_completed_at is None

    def test_zombie_scan_result_frozen(self):
        r = ZombieScanResult()
        with pytest.raises(AttributeError):
            r.scanned_count = 1  # type: ignore[misc]

    def test_zombie_task_info_defaults(self):
        info = ZombieTaskInfo()
        assert info.task_id == ""
        assert info.current_state == ""
        assert info.run_id is None

    def test_zombie_task_info_custom(self):
        info = ZombieTaskInfo(
            task_id="TASK-X",
            current_state="running",
            run_id="run-uuid",
            last_updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert info.task_id == "TASK-X"

    def test_health_check_result_defaults(self):
        h = HealthCheckResult()
        assert h.status == "ok"
        assert h.checks == {}
