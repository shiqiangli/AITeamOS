"""
Context Assembler — 测试 (plan.md §2.2 验证标准)。

验证标准:
- Context Snapshot 一旦写入即只读 (SHA-256 不可变)
- ACL 调用正确传递
- 事件发布正确
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from aiteamos_execution.application.context_assembler import (
    ContextAssembler,
    ContextSnapshot,
    ContextSnapshotSealed,
    MemorySnippet,
    SkillBundle,
)
from aiteamos_shared.types import new_id


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeTxManager:
    @asynccontextmanager
    async def transaction(self):
        yield FakeTransaction()


class MockKnowledgeACL:
    """Mock Knowledge ACL — returns pre-configured memories."""

    def __init__(
        self,
        memories: list[MemorySnippet] | None = None,
        total_tokens: int = 0,
    ):
        self._memories = memories or []
        self._total_tokens = total_tokens
        self.call_count = 0
        self.last_kwargs: dict[str, Any] = {}

    async def recall(
        self,
        *,
        task_id: str,
        member_id: UUID,
        project_ids: list[UUID],
        dept_id: UUID | None,
        max_recall_tokens: int,
    ) -> tuple[list[MemorySnippet], int]:
        self.call_count += 1
        self.last_kwargs = {
            "task_id": task_id,
            "member_id": member_id,
            "project_ids": project_ids,
            "dept_id": dept_id,
            "max_recall_tokens": max_recall_tokens,
        }
        return self._memories, self._total_tokens


class MockCapabilityACL:
    """Mock Capability ACL — returns pre-configured skills."""

    def __init__(self, skills: list[SkillBundle] | None = None):
        self._skills = skills or []
        self.call_count = 0

    async def get_skill_bundle(
        self, *, skill_ids: list[Any], member_id: UUID
    ) -> list[SkillBundle]:
        self.call_count += 1
        return self._skills


class MockSnapshotRepo:
    """In-memory snapshot repo."""

    def __init__(self):
        self._store: dict[UUID, ContextSnapshot] = {}
        self.save_count = 0

    async def save_snapshot(
        self, snapshot: ContextSnapshot, *, tx: Any
    ) -> None:
        self._store[snapshot.id] = snapshot
        self.save_count += 1

    async def get_snapshot(self, snapshot_id: UUID) -> ContextSnapshot | None:
        return self._store.get(snapshot_id)


class RecordingEventPublisher:
    def __init__(self):
        self.events: list[Any] = []

    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None:
        self.events.extend(events)


# ===========================================================================
# §1: ContextSnapshot 不可变性
# ===========================================================================


class TestContextSnapshot:
    """Context Snapshot 不可变性验证。"""

    def test_seal_computes_sha256(self):
        snap = ContextSnapshot(
            task_id="TASK-TEST",
            memories=[
                MemorySnippet(
                    memory_id=new_id(),
                    title="M1",
                    statement="Test statement",
                    confidence=0.9,
                    score=0.8,
                    tokens=50,
                )
            ],
        )
        snap.seal()
        assert len(snap.sha256) == 64  # SHA-256 hex digest
        assert snap.sha256  # non-empty

    def test_seal_deterministic(self):
        """Same content → same SHA-256."""
        mid = new_id()
        sid = uuid4()
        fixed_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)

        def make():
            s = ContextSnapshot(
                id=sid,
                task_id="TASK-TEST",
                sealed_at=fixed_ts,
                memories=[
                    MemorySnippet(
                        memory_id=mid,
                        title="M1",
                        statement="Test",
                        confidence=0.9,
                        score=0.8,
                        tokens=50,
                    )
                ],
            )
            return s

        s1 = make()
        s1.seal()
        s2 = make()
        s2.seal()
        assert s1.sha256 == s2.sha256

    def test_different_content_different_hash(self):
        """Different content → different SHA-256."""
        s1 = ContextSnapshot(
            task_id="TASK-1",
            memories=[
                MemorySnippet(
                    memory_id=new_id(),
                    title="A",
                    statement="Statement A",
                    confidence=0.9,
                    score=0.8,
                    tokens=50,
                )
            ],
        )
        s1.seal()

        s2 = ContextSnapshot(
            task_id="TASK-2",
            memories=[
                MemorySnippet(
                    memory_id=new_id(),
                    title="B",
                    statement="Statement B",
                    confidence=0.5,
                    score=0.3,
                    tokens=30,
                )
            ],
        )
        s2.seal()
        assert s1.sha256 != s2.sha256

    def test_snapshot_read_only_after_seal(self):
        """Once sealed, modifying content invalidates SHA-256."""
        snap = ContextSnapshot(
            task_id="TASK-TEST",
            memories=[
                MemorySnippet(
                    memory_id=new_id(),
                    title="M1",
                    statement="Original",
                    confidence=0.9,
                    score=0.8,
                    tokens=50,
                )
            ],
        )
        snap.seal()
        original_hash = snap.sha256

        # Tamper with content
        snap.task_id = "TASK-TAMPERED"
        # SHA-256 no longer matches
        assert snap.compute_sha256() != original_hash


# ===========================================================================
# §2: ContextAssembler 组装流程
# ===========================================================================


class TestContextAssembler:
    """Context Assembler 集成测试。"""

    @pytest.fixture
    def deps(self):
        memories = [
            MemorySnippet(
                memory_id=new_id(),
                title="Memory A",
                statement="Important fact",
                confidence=0.9,
                score=0.85,
                tokens=100,
            ),
            MemorySnippet(
                memory_id=new_id(),
                title="Memory B",
                statement="Useful pattern",
                confidence=0.7,
                score=0.65,
                tokens=80,
            ),
        ]
        skills = [
            SkillBundle(
                skill_id=new_id(),
                name="python-lint",
                version="1.0.0",
                description="Python linter",
            )
        ]
        return {
            "knowledge_acl": MockKnowledgeACL(memories, total_tokens=180),
            "capability_acl": MockCapabilityACL(skills),
            "snapshot_repo": MockSnapshotRepo(),
            "tx_manager": FakeTxManager(),
            "event_publisher": RecordingEventPublisher(),
        }

    @pytest.mark.asyncio
    async def test_assemble_creates_snapshot(self, deps):
        assembler = ContextAssembler(**deps)
        snap = await assembler.assemble(
            task_id="TASK-20260101T000000000-AAAA",
            member_id=uuid4(),
        )
        assert snap.task_id == "TASK-20260101T000000000-AAAA"
        assert len(snap.memories) == 2
        assert len(snap.skills) == 1
        assert snap.total_tokens == 180
        assert snap.sha256  # sealed

    @pytest.mark.asyncio
    async def test_assemble_persists_snapshot(self, deps):
        assembler = ContextAssembler(**deps)
        snap = await assembler.assemble(
            task_id="TASK-TEST",
            member_id=uuid4(),
        )
        saved = await deps["snapshot_repo"].get_snapshot(snap.id)
        assert saved is not None
        assert saved.sha256 == snap.sha256

    @pytest.mark.asyncio
    async def test_assemble_publishes_event(self, deps):
        assembler = ContextAssembler(**deps)
        snap = await assembler.assemble(
            task_id="TASK-TEST",
            member_id=uuid4(),
        )
        events = deps["event_publisher"].events
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, ContextSnapshotSealed)
        assert evt.snapshot_id == snap.id
        assert evt.memory_count == 2
        assert evt.skill_count == 1
        assert evt.total_tokens == 180

    @pytest.mark.asyncio
    async def test_assemble_calls_knowledge_acl(self, deps):
        assembler = ContextAssembler(**deps)
        mid = uuid4()
        dept = uuid4()
        await assembler.assemble(
            task_id="TASK-TEST",
            member_id=mid,
            dept_id=dept,
            max_recall_tokens=4000,
        )
        acl = deps["knowledge_acl"]
        assert acl.call_count == 1
        assert acl.last_kwargs["member_id"] == mid
        assert acl.last_kwargs["dept_id"] == dept
        assert acl.last_kwargs["max_recall_tokens"] == 4000

    @pytest.mark.asyncio
    async def test_assemble_calls_capability_acl(self, deps):
        assembler = ContextAssembler(**deps)
        skill_ids = [new_id(), new_id()]
        await assembler.assemble(
            task_id="TASK-TEST",
            member_id=uuid4(),
            declared_skills=skill_ids,
        )
        assert deps["capability_acl"].call_count == 1

    @pytest.mark.asyncio
    async def test_assemble_empty_memories_and_skills(self):
        """Empty recall + empty skills → valid snapshot with zero tokens."""
        assembler = ContextAssembler(
            knowledge_acl=MockKnowledgeACL([], total_tokens=0),
            capability_acl=MockCapabilityACL([]),
            snapshot_repo=MockSnapshotRepo(),
            tx_manager=FakeTxManager(),
            event_publisher=RecordingEventPublisher(),
        )
        snap = await assembler.assemble(
            task_id="TASK-EMPTY",
            member_id=uuid4(),
        )
        assert len(snap.memories) == 0
        assert len(snap.skills) == 0
        assert snap.total_tokens == 0
        assert snap.sha256  # still sealed
