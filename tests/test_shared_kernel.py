"""
Stage 1.1 验证: Shared Kernel 单元测试。

覆盖:
- types: TaskId 生成、SemVer 兼容性、Priority 排序
- events: VersionedDomainEvent 序列化、向前兼容
- outbox: OutboxWriter 写入 (mock tx)
- projection: IdempotentProjectionConsumer CAS 水位 (mock db)
- saga: CompensationStack push/unwind/DLQ
- llm: 离线模式 mock
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# types
# ---------------------------------------------------------------------------
from aiteamos_shared.types import (
    MemberKind,
    Priority,
    ResourceKind,
    SemVer,
    TaskId,
    generate_task_id,
    new_id,
)


class TestTaskId:
    def test_format(self):
        tid = generate_task_id()
        assert tid.startswith("TASK-")
        # TASK-YYYYMMDDTHHMMSSmmm-XXXXX = 4+1+18+1+5 = 29 chars
        assert len(tid) == 29
        parts = tid.split("-")
        assert parts[0] == "TASK"
        assert len(parts[2]) == 5  # random suffix

    def test_with_specific_time(self):
        dt = datetime(2026, 5, 27, 10, 30, 45, 123000, tzinfo=timezone.utc)
        tid = generate_task_id(now=dt)
        assert "20260527T103045123" in tid

    def test_uniqueness(self):
        ids = {generate_task_id() for _ in range(100)}
        assert len(ids) == 100

    def test_is_newtype_str(self):
        tid = generate_task_id()
        assert isinstance(tid, str)


class TestSemVer:
    def test_str(self):
        v = SemVer(major=1, minor=2, patch=3)
        assert str(v) == "1.2.3"

    def test_parse(self):
        v = SemVer.parse("2.0.1")
        assert v.major == 2 and v.minor == 0 and v.patch == 1

    def test_parse_invalid(self):
        with pytest.raises(ValueError):
            SemVer.parse("1.2")

    def test_backward_compatible(self):
        v1 = SemVer(major=1, minor=0, patch=0)
        v2 = SemVer(major=1, minor=1, patch=0)
        assert v2.is_backward_compatible_with(v1)
        assert not v1.is_backward_compatible_with(v2)

    def test_major_breaks_compatibility(self):
        v1 = SemVer(major=1, minor=0, patch=0)
        v2 = SemVer(major=2, minor=0, patch=0)
        assert not v2.is_backward_compatible_with(v1)


class TestPriority:
    def test_ordinal(self):
        assert Priority.P0.ordinal < Priority.P1.ordinal
        assert Priority.P1.ordinal < Priority.P2.ordinal
        assert Priority.P2.ordinal < Priority.P3.ordinal


class TestNewId:
    def test_generates_uuid(self):
        uid = new_id()
        assert uid.version == 4


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------
from aiteamos_shared.events import VersionedDomainEvent, create_event


class TestVersionedDomainEvent:
    def test_defaults(self):
        evt = VersionedDomainEvent(event_type="test.event")
        assert evt.event_version == 1
        assert evt.global_seq == 0
        assert evt.correlation_id is not None
        assert evt.timestamp is not None

    def test_serialization(self):
        evt = VersionedDomainEvent(event_type="test.event", event_version=2)
        data = evt.model_dump(mode="json")
        assert data["event_type"] == "test.event"
        assert data["event_version"] == 2
        assert "correlation_id" in data

    def test_extra_fields_ignored(self):
        """Forward compatibility: unknown fields are silently ignored."""
        data = {
            "event_type": "test.event",
            "event_version": 1,
            "unknown_future_field": "should be ignored",
            "correlation_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "global_seq": 42,
        }
        evt = VersionedDomainEvent.model_validate(data)
        assert evt.event_type == "test.event"
        assert evt.global_seq == 42
        assert not hasattr(evt, "unknown_future_field")

    def test_subclass(self):
        class TaskCompleted(VersionedDomainEvent):
            event_type: str = "task.completed"
            task_id: str = ""
            outcome: str = ""

        evt = TaskCompleted(task_id="TASK-123", outcome="done")
        assert evt.event_type == "task.completed"
        assert evt.task_id == "TASK-123"

    def test_create_event_factory(self):
        cid = uuid4()
        evt = create_event(VersionedDomainEvent, event_type="test.factory", correlation_id=cid)
        assert evt.correlation_id == cid
        assert evt.event_type == "test.factory"


# ---------------------------------------------------------------------------
# outbox
# ---------------------------------------------------------------------------
from aiteamos_shared.outbox import OutboxEntry, OutboxWriter


class TestOutboxWriter:
    @pytest.mark.asyncio
    async def test_write(self):
        mock_tx = AsyncMock()
        mock_tx.fetchrow = AsyncMock(return_value={"global_seq": 42})

        evt = VersionedDomainEvent(event_type="test.write")
        writer = OutboxWriter()
        entry = await writer.write(evt, partition_key="pk-1", tx=mock_tx)

        assert entry.event_type == "test.write"
        assert entry.partition_key == "pk-1"
        assert entry.global_seq == 42
        mock_tx.fetchrow.assert_awaited_once()


class TestOutboxEntry:
    def test_defaults(self):
        entry = OutboxEntry()
        assert entry.published_at is None
        assert entry.payload == {}


# ---------------------------------------------------------------------------
# projection
# ---------------------------------------------------------------------------
from aiteamos_shared.projection import IdempotentProjectionConsumer


class _TestProjection(IdempotentProjectionConsumer):
    consumer_id = "test-projection-v1"

    def __init__(self, db):
        super().__init__(db)
        self.processed_events: list[VersionedDomainEvent] = []

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        self.processed_events.append(event)


class TestIdempotentProjectionConsumer:
    @pytest.mark.asyncio
    async def test_first_event_processed(self):
        mock_db = AsyncMock()
        mock_db.fetchrow = AsyncMock(return_value=None)  # no watermark yet
        mock_db.execute = AsyncMock()

        proj = _TestProjection(db=mock_db)
        evt = VersionedDomainEvent(event_type="test.proj", global_seq=1)
        result = await proj.consume(evt)

        assert result is True
        assert len(proj.processed_events) == 1

    @pytest.mark.asyncio
    async def test_duplicate_event_skipped(self):
        mock_db = AsyncMock()
        # watermark already at seq 5
        mock_db.fetchrow = AsyncMock(
            return_value={"last_seq": 5, "last_event_id": "abc", "processed_at": datetime.now()}
        )

        proj = _TestProjection(db=mock_db)
        evt = VersionedDomainEvent(event_type="test.dup", global_seq=3)  # 3 < 5
        result = await proj.consume(evt)

        assert result is False
        assert len(proj.processed_events) == 0

    @pytest.mark.asyncio
    async def test_consumer_id_required(self):
        class BadProjection(IdempotentProjectionConsumer):
            async def handle_event(self, event):
                pass

        proj = BadProjection(db=AsyncMock())
        evt = VersionedDomainEvent(event_type="test.bad", global_seq=1)
        with pytest.raises(ValueError, match="consumer_id"):
            await proj.consume(evt)


# ---------------------------------------------------------------------------
# saga
# ---------------------------------------------------------------------------
from aiteamos_shared.saga import CompensationItem, CompensationStack


class TestCompensationStack:
    def test_push_and_len(self):
        stack = CompensationStack()
        assert stack.is_empty
        stack.push(
            CompensationItem(
                activity="release",
                args={"id": "1"},
                kind=ResourceKind.MEMBER_CONCURRENCY,
                correlation_id="c1",
            )
        )
        assert len(stack) == 1
        assert not stack.is_empty

    @pytest.mark.asyncio
    async def test_unwind_lifo_order(self):
        order: list[str] = []

        async def mock_executor(item: CompensationItem):
            order.append(item.activity)

        stack = CompensationStack(executor=mock_executor)
        for name in ["first", "second", "third"]:
            stack.push(
                CompensationItem(
                    activity=name,
                    args={},
                    kind=ResourceKind.SANDBOX,
                    correlation_id=name,
                )
            )

        await stack.unwind(reason="test")

        # LIFO: third -> second -> first
        assert order == ["third", "second", "first"]
        assert stack.is_empty

    @pytest.mark.asyncio
    async def test_unwind_failure_routes_to_dlq(self):
        dlq_items: list[CompensationItem] = []

        async def failing_executor(item: CompensationItem):
            raise RuntimeError("compensation failed")

        async def dlq_handler(item: CompensationItem):
            dlq_items.append(item)

        stack = CompensationStack(executor=failing_executor, dlq_handler=dlq_handler)
        stack.push(
            CompensationItem(
                activity="failing_op",
                args={},
                kind=ResourceKind.SKILL_BUNDLE,
                correlation_id="c1",
            )
        )

        await stack.unwind(reason="test_failure")
        assert len(dlq_items) == 1
        assert dlq_items[0].activity == "failing_op"
        assert stack.is_empty

    @pytest.mark.asyncio
    async def test_unwind_empty_stack(self):
        stack = CompensationStack()
        await stack.unwind(reason="noop")  # should not raise

    def test_serialization_roundtrip(self):
        stack = CompensationStack()
        stack.push(
            CompensationItem(
                activity="release_member",
                args={"task_id": "T1"},
                kind=ResourceKind.MEMBER_CONCURRENCY,
                correlation_id="c1",
            )
        )
        data = stack.to_dicts()
        restored = CompensationStack.from_dicts(data)
        assert len(restored) == 1
        assert restored.items[0].activity == "release_member"
        assert restored.items[0].kind == ResourceKind.MEMBER_CONCURRENCY


# ---------------------------------------------------------------------------
# llm (offline mode)
# ---------------------------------------------------------------------------
from aiteamos_shared.llm import generate_embedding, llm_extract


class TestLLMOfflineMode:
    @pytest.mark.asyncio
    async def test_embedding_returns_vector(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        vec = await generate_embedding("test text")
        assert isinstance(vec, list)
        assert len(vec) == 1536  # default dim
        assert all(isinstance(v, float) for v in vec)

    @pytest.mark.asyncio
    async def test_embedding_deterministic(self, monkeypatch):
        """Same input should produce same output in offline mode (seeded RNG)."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        v1 = await generate_embedding("hello")
        v2 = await generate_embedding("hello")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_llm_extract_returns_mock(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = await llm_extract("prompt", "system")
        assert isinstance(result, str)
        assert len(result) > 0
        assert "mock" in result.lower()
