"""Tests for ACL bridges (RecallEngineKnowledgeACL + SqlCapabilityACL)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from aiteamos_execution.application.context_assembler import (
    MemorySnippet,
    SkillBundle,
)
from aiteamos_knowledge.application.recall_engine import (
    RecallCandidate,
    RecallResult,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeRecallEngine:
    """Minimal stub that returns a pre-configured RecallResult."""

    result: RecallResult = field(default_factory=lambda: RecallResult(memories=[]))
    last_ctx: object | None = None
    last_budget: object | None = None

    async def recall(self, ctx, budget) -> RecallResult:
        self.last_ctx = ctx
        self.last_budget = budget
        return self.result


@dataclass
class FakeDB:
    """Minimal DB stub returning pre-configured rows."""

    rows: list[dict] = field(default_factory=list)

    async def fetch(self, query: str, *args) -> list[dict]:
        return self.rows


# ---------------------------------------------------------------------------
# RecallEngineKnowledgeACL tests
# ---------------------------------------------------------------------------


class TestRecallEngineKnowledgeACL:
    async def test_empty_recall_returns_empty(self):
        from services.api.aiteamos_api.acl_bridges import RecallEngineKnowledgeACL

        engine = FakeRecallEngine()
        acl = RecallEngineKnowledgeACL(recall_engine=engine)

        snippets, tokens = await acl.recall(
            task_id="T-1",
            member_id=uuid4(),
            project_ids=[],
            dept_id=None,
            max_recall_tokens=8000,
        )

        assert snippets == []
        assert tokens == 0

    async def test_recall_maps_candidates_to_snippets(self):
        from services.api.aiteamos_api.acl_bridges import RecallEngineKnowledgeACL

        mid = uuid4()
        candidates = [
            RecallCandidate(
                memory_id=mid,
                title="Test Memory",
                statement="This is a test statement.",
                lifecycle_state="active",
                confidence=0.9,
                tokens=10,
                score=0.85,
                has_conflict=False,
            ),
        ]
        engine = FakeRecallEngine(
            result=RecallResult(memories=candidates, total_tokens=10)
        )
        acl = RecallEngineKnowledgeACL(recall_engine=engine)

        snippets, tokens = await acl.recall(
            task_id="T-2",
            member_id=uuid4(),
            project_ids=[],
            dept_id=None,
            max_recall_tokens=4000,
        )

        assert len(snippets) == 1
        assert snippets[0].memory_id == mid
        assert snippets[0].title == "Test Memory"
        assert snippets[0].score == 0.85
        assert snippets[0].tokens == 10
        assert tokens == 10

    async def test_recall_passes_budget_and_context(self):
        from services.api.aiteamos_api.acl_bridges import RecallEngineKnowledgeACL

        engine = FakeRecallEngine()
        acl = RecallEngineKnowledgeACL(recall_engine=engine)
        member = uuid4()
        proj = uuid4()

        await acl.recall(
            task_id="T-3",
            member_id=member,
            project_ids=[proj],
            dept_id=None,
            max_recall_tokens=2000,
        )

        assert engine.last_ctx.task_id == "T-3"
        assert engine.last_ctx.member_id == member
        assert engine.last_ctx.project_ids == [proj]
        assert engine.last_budget.max_recall_tokens == 2000

    async def test_conflict_flag_preserved(self):
        from services.api.aiteamos_api.acl_bridges import RecallEngineKnowledgeACL

        mid = uuid4()
        candidates = [
            RecallCandidate(
                memory_id=mid,
                title="Conflicting",
                statement="Has conflict",
                lifecycle_state="active",
                confidence=0.7,
                tokens=5,
                score=0.6,
                has_conflict=True,
            ),
        ]
        engine = FakeRecallEngine(
            result=RecallResult(memories=candidates, total_tokens=5)
        )
        acl = RecallEngineKnowledgeACL(recall_engine=engine)

        snippets, _ = await acl.recall(
            task_id="T-4",
            member_id=uuid4(),
            project_ids=[],
            dept_id=None,
            max_recall_tokens=8000,
        )

        assert snippets[0].has_conflict is True

    async def test_degraded_channels_logged(self):
        from services.api.aiteamos_api.acl_bridges import RecallEngineKnowledgeACL

        engine = FakeRecallEngine(
            result=RecallResult(memories=[], total_tokens=0, degraded_channels=["vector"])
        )
        acl = RecallEngineKnowledgeACL(recall_engine=engine)

        snippets, tokens = await acl.recall(
            task_id="T-5",
            member_id=uuid4(),
            project_ids=[],
            dept_id=None,
            max_recall_tokens=8000,
        )

        assert snippets == []
        assert tokens == 0


# ---------------------------------------------------------------------------
# SqlCapabilityACL tests
# ---------------------------------------------------------------------------


class TestSqlCapabilityACL:
    async def test_empty_skill_ids(self):
        from services.api.aiteamos_api.acl_bridges import SqlCapabilityACL

        db = FakeDB()
        acl = SqlCapabilityACL(db=db)

        bundles = await acl.get_skill_bundle(skill_ids=[], member_id=uuid4())
        assert bundles == []

    async def test_maps_rows_to_skill_bundles(self):
        from services.api.aiteamos_api.acl_bridges import SqlCapabilityACL

        sid = uuid4()
        db = FakeDB(
            rows=[
                {
                    "id": sid,
                    "name": "python-expert",
                    "version": 3,
                    "description": "Python expertise",
                },
            ]
        )
        acl = SqlCapabilityACL(db=db)

        bundles = await acl.get_skill_bundle(
            skill_ids=[sid], member_id=uuid4()
        )

        assert len(bundles) == 1
        assert bundles[0].skill_id == sid
        assert bundles[0].name == "python-expert"
        assert bundles[0].version == "3"
        assert bundles[0].description == "Python expertise"

    async def test_no_rows_returns_empty(self):
        from services.api.aiteamos_api.acl_bridges import SqlCapabilityACL

        db = FakeDB(rows=[])
        acl = SqlCapabilityACL(db=db)

        bundles = await acl.get_skill_bundle(
            skill_ids=[uuid4()], member_id=uuid4()
        )
        assert bundles == []

    async def test_missing_description_defaults_empty(self):
        from services.api.aiteamos_api.acl_bridges import SqlCapabilityACL

        db = FakeDB(
            rows=[{"id": uuid4(), "name": "test-skill", "version": 1}],
        )
        acl = SqlCapabilityACL(db=db)

        bundles = await acl.get_skill_bundle(
            skill_ids=[uuid4()], member_id=uuid4()
        )

        assert len(bundles) == 1
        assert bundles[0].description == ""
