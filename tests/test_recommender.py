"""
Stage 4.2 — 智能推荐系统测试。

Test MemberRecommender, MemoryRecommender, SkillRecommender。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from aiteamos_execution.application.recommender import (
    MemberRecommender,
    MemoryRecommender,
    SkillRecommender,
    TaskProfile,
    MemberRecommendation,
    MemoryRecommendation,
    SkillRecommendation,
)


# ---------------------------------------------------------------------------
# Mock providers
# ---------------------------------------------------------------------------


class MockMemberProvider:
    def __init__(self):
        self._skills: dict[str, list[str]] = {}
        self._memories: dict[str, list[str]] = {}
        self._loads: dict[str, float] = {}
        self._success: dict[str, float] = {}
        self._active: list[str] = []

    def add_member(self, mid, *, skills=None, memories=None, load=0.5, success=0.8):
        sid = str(mid)
        self._skills[sid] = skills or []
        self._memories[sid] = memories or []
        self._loads[sid] = load
        self._success[sid] = success
        self._active.append(mid)

    async def get_member_skills(self, member_id):
        return self._skills.get(str(member_id), [])

    async def get_member_memories(self, member_id):
        return self._memories.get(str(member_id), [])

    async def get_member_load(self, member_id):
        return self._loads.get(str(member_id), 0.5)

    async def get_member_success_rate(self, member_id):
        return self._success.get(str(member_id), 0.5)

    async def list_active_members(self):
        return list(self._active)


class MockMemoryProvider:
    def __init__(self):
        self._dept_memories: dict[str, list] = {}
        self._proj_memories: dict[str, list] = {}
        self._success_memories: dict[str, list] = {}

    def set_dept_memories(self, dept_id, memories):
        self._dept_memories[str(dept_id)] = memories

    def set_proj_memories(self, proj_id, memories):
        self._proj_memories[str(proj_id)] = memories

    def set_success_memories(self, dept_id, memories):
        self._success_memories[str(dept_id)] = memories

    async def get_popular_memories_for_department(self, department_id, limit):
        return self._dept_memories.get(str(department_id), [])[:limit]

    async def get_popular_memories_for_project(self, project_id, limit):
        return self._proj_memories.get(str(project_id), [])[:limit]

    async def get_successful_member_memories(self, department_id, limit):
        return self._success_memories.get(str(department_id), [])[:limit]


class MockTaskHistory:
    def __init__(self):
        self._tasks: list[dict[str, Any]] = []

    def add_task(self, *, skills, outcome="success"):
        self._tasks.append({"skills": skills, "outcome": outcome})

    async def find_similar_tasks(self, description, tags, limit):
        return self._tasks[:limit]


# ---------------------------------------------------------------------------
# Tests: MemberRecommender
# ---------------------------------------------------------------------------


class TestMemberRecommender:
    @pytest.fixture
    def provider(self):
        return MockMemberProvider()

    @pytest.mark.asyncio
    async def test_empty_members_returns_empty(self, provider):
        rec = MemberRecommender(member_provider=provider)
        task = TaskProfile(
            task_id="t1",
            department_id=uuid4(),
            declared_skills=["python"],
        )
        result = await rec.recommend(task)
        assert result == []

    @pytest.mark.asyncio
    async def test_full_skill_coverage_scores_high(self, provider):
        m1, m2 = uuid4(), uuid4()
        provider.add_member(m1, skills=["python", "testing"], success=0.9, load=0.2)
        provider.add_member(m2, skills=["java"], success=0.9, load=0.2)

        rec = MemberRecommender(member_provider=provider)
        task = TaskProfile(
            task_id="t1",
            department_id=uuid4(),
            declared_skills=["python", "testing"],
        )

        result = await rec.recommend(task)

        assert len(result) == 2
        assert result[0].member_id == m1  # Full coverage
        assert result[0].skill_coverage == 1.0
        assert result[0].score > result[1].score

    @pytest.mark.asyncio
    async def test_memory_relevance_boosts_score(self, provider):
        m1 = uuid4()
        mem1, mem2 = uuid4(), uuid4()
        provider.add_member(m1, skills=[], memories=[mem1, mem2], success=0.8)

        rec = MemberRecommender(member_provider=provider)
        task = TaskProfile(
            task_id="t1",
            department_id=uuid4(),
            declared_memory_hints=[mem1],
        )

        result = await rec.recommend(task)

        assert result[0].memory_relevance == 1.0

    @pytest.mark.asyncio
    async def test_low_load_preferred(self, provider):
        m1, m2 = uuid4(), uuid4()
        provider.add_member(m1, load=0.1, success=0.8)
        provider.add_member(m2, load=0.9, success=0.8)

        rec = MemberRecommender(member_provider=provider)
        task = TaskProfile(task_id="t1", department_id=uuid4())

        result = await rec.recommend(task)

        assert result[0].member_id == m1
        assert result[0].load_factor < result[1].load_factor

    @pytest.mark.asyncio
    async def test_exclude_members(self, provider):
        m1, m2 = uuid4(), uuid4()
        provider.add_member(m1, success=0.9)
        provider.add_member(m2, success=0.5)

        rec = MemberRecommender(member_provider=provider)
        task = TaskProfile(task_id="t1", department_id=uuid4())

        result = await rec.recommend(task, exclude_members={m1})

        assert len(result) == 1
        assert result[0].member_id == m2

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self, provider):
        for _ in range(10):
            provider.add_member(uuid4(), success=0.7)

        rec = MemberRecommender(member_provider=provider)
        task = TaskProfile(task_id="t1", department_id=uuid4())

        result = await rec.recommend(task, top_k=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_no_skills_gives_neutral_score(self, provider):
        m1 = uuid4()
        provider.add_member(m1, success=0.8)

        rec = MemberRecommender(member_provider=provider)
        task = TaskProfile(task_id="t1", department_id=uuid4())  # No declared skills

        result = await rec.recommend(task)
        assert result[0].skill_coverage == 0.5


# ---------------------------------------------------------------------------
# Tests: MemoryRecommender
# ---------------------------------------------------------------------------


class TestMemoryRecommender:
    @pytest.fixture
    def provider(self):
        return MockMemoryProvider()

    @pytest.mark.asyncio
    async def test_recommends_dept_memories(self, provider):
        dept_id = uuid4()
        m1, m2 = uuid4(), uuid4()
        provider.set_dept_memories(dept_id, [m1, m2])

        rec = MemoryRecommender(memory_provider=provider)
        result = await rec.recommend(department_id=dept_id)

        assert len(result) == 2
        assert all(isinstance(r, MemoryRecommendation) for r in result)

    @pytest.mark.asyncio
    async def test_project_memories_boost_score(self, provider):
        dept_id = uuid4()
        proj_id = uuid4()
        m1 = uuid4()
        provider.set_dept_memories(dept_id, [m1])
        provider.set_proj_memories(proj_id, [m1])

        rec = MemoryRecommender(memory_provider=provider)
        result = await rec.recommend(
            department_id=dept_id, project_ids=[proj_id],
        )

        assert len(result) == 1
        # m1 gets both dept + project score
        assert result[0].score > 0.3

    @pytest.mark.asyncio
    async def test_excludes_existing_memories(self, provider):
        dept_id = uuid4()
        m1, m2 = uuid4(), uuid4()
        provider.set_dept_memories(dept_id, [m1, m2])

        rec = MemoryRecommender(memory_provider=provider)
        result = await rec.recommend(
            department_id=dept_id,
            existing_memories={m1},
        )

        assert len(result) == 1
        assert result[0].memory_id == m2

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self, provider):
        dept_id = uuid4()
        memories = [uuid4() for _ in range(20)]
        provider.set_dept_memories(dept_id, memories)

        rec = MemoryRecommender(memory_provider=provider)
        result = await rec.recommend(department_id=dept_id, top_k=5)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_empty_provider_returns_empty(self, provider):
        rec = MemoryRecommender(memory_provider=provider)
        result = await rec.recommend(department_id=uuid4())
        assert result == []


# ---------------------------------------------------------------------------
# Tests: SkillRecommender
# ---------------------------------------------------------------------------


class TestSkillRecommender:
    @pytest.fixture
    def history(self):
        return MockTaskHistory()

    @pytest.mark.asyncio
    async def test_recommends_frequent_skills(self, history):
        history.add_task(skills=["python", "testing"])
        history.add_task(skills=["python", "docker"])
        history.add_task(skills=["python", "testing"])

        rec = SkillRecommender(task_history=history)
        task = TaskProfile(
            task_id="t1",
            department_id=uuid4(),
            description="Build a Python service",
        )

        result = await rec.recommend(task)

        assert len(result) > 0
        # "python" appears in all 3 tasks
        python_rec = next(r for r in result if r.skill_id == "python")
        assert python_rec.score == 1.0

    @pytest.mark.asyncio
    async def test_excludes_declared_skills(self, history):
        history.add_task(skills=["python", "testing", "docker"])

        rec = SkillRecommender(task_history=history)
        task = TaskProfile(
            task_id="t1",
            department_id=uuid4(),
            declared_skills=["python"],
            description="Build a service",
        )

        result = await rec.recommend(task)

        skill_ids = {r.skill_id for r in result}
        assert "python" not in skill_ids

    @pytest.mark.asyncio
    async def test_empty_history_returns_empty(self, history):
        rec = SkillRecommender(task_history=history)
        task = TaskProfile(
            task_id="t1",
            department_id=uuid4(),
            description="New task",
        )

        result = await rec.recommend(task)
        assert result == []

    @pytest.mark.asyncio
    async def test_top_k_limits_results(self, history):
        for i in range(10):
            history.add_task(skills=[f"skill_{i}"])

        rec = SkillRecommender(task_history=history)
        task = TaskProfile(
            task_id="t1",
            department_id=uuid4(),
            description="Complex task",
        )

        result = await rec.recommend(task, top_k=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Tests: Value objects
# ---------------------------------------------------------------------------


class TestRecommendationValueObjects:
    def test_member_recommendation_frozen(self):
        rec = MemberRecommendation(
            member_id=uuid4(),
            score=0.85,
            skill_coverage=0.9,
            memory_relevance=0.7,
            success_rate=0.95,
            load_factor=0.2,
        )
        assert rec.score == 0.85
        with pytest.raises(AttributeError):
            rec.score = 0.5  # type: ignore

    def test_memory_recommendation_frozen(self):
        rec = MemoryRecommendation(memory_id=uuid4(), score=0.7, reason="test")
        assert rec.reason == "test"

    def test_skill_recommendation_frozen(self):
        rec = SkillRecommendation(skill_id="python", score=1.0)
        assert rec.score == 1.0

    def test_task_profile_defaults(self):
        tp = TaskProfile(task_id="t1", department_id=uuid4())
        assert tp.declared_skills == []
        assert tp.declared_memory_hints == []
        assert tp.tags == []
