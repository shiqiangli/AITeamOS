"""
Stage 4.3 — Member 活动与成长追踪测试。

Test ActivityTrackingService, GrowthStatisticsService, SkillDecayDetector。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from aiteamos_workforce.application.activity import (
    ActivityEvent,
    ActivityKind,
    ActivityTrackingService,
    DecayWarning,
    GrowthStats,
    GrowthStatisticsService,
    SkillDecayDetector,
    DECAY_WARNING_THRESHOLD,
    DECAY_CRITICAL_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------


class MockTransactionManager:
    def __init__(self):
        self.commit_count = 0

    @asynccontextmanager
    async def transaction(self):
        yield None
        self.commit_count += 1


class MockActivityRepo:
    def __init__(self):
        self._events: list[ActivityEvent] = []

    async def save(self, event, *, tx=None):
        self._events.append(event)

    async def find_by_member(self, member_id, *, limit=50, offset=0, tx=None):
        matching = [e for e in self._events if e.member_id == member_id]
        matching.sort(key=lambda e: e.occurred_at, reverse=True)
        return matching[offset : offset + limit]

    async def count_by_member_and_kind(self, member_id, kind, *, since=None, tx=None):
        count = 0
        for e in self._events:
            if e.member_id == member_id and e.event_kind.value == kind:
                if since and e.occurred_at < since:
                    continue
                count += 1
        return count

    async def count_by_member_in_range(self, member_id, *, start, end, tx=None):
        count = 0
        for e in self._events:
            if e.member_id == member_id and start <= e.occurred_at < end:
                count += 1
        return count


class MockSkillUsage:
    def __init__(self):
        self._failures: dict[str, int] = {}

    def set_consecutive_failures(self, member_id, skill_id, count):
        key = f"{member_id}:{skill_id}"
        self._failures[key] = count

    async def get_consecutive_failures(self, member_id, skill_id):
        key = f"{member_id}:{skill_id}"
        return self._failures.get(key, 0)


# ---------------------------------------------------------------------------
# Tests: ActivityTrackingService
# ---------------------------------------------------------------------------


class TestActivityTrackingService:
    @pytest.fixture
    def setup(self):
        repo = MockActivityRepo()
        tx = MockTransactionManager()
        svc = ActivityTrackingService(activity_repo=repo, tx_manager=tx)
        return svc, repo, tx

    @pytest.mark.asyncio
    async def test_record_activity(self, setup):
        svc, repo, tx = setup
        mid = uuid4()

        event = await svc.record_activity(
            member_id=mid,
            kind=ActivityKind.TASK_COMPLETED,
            payload={"task_id": "t1"},
        )

        assert event.member_id == mid
        assert event.event_kind == ActivityKind.TASK_COMPLETED
        assert event.event_payload["task_id"] == "t1"
        assert len(repo._events) == 1
        assert tx.commit_count == 1

    @pytest.mark.asyncio
    async def test_record_multiple_activities(self, setup):
        svc, repo, tx = setup
        mid = uuid4()

        await svc.record_activity(member_id=mid, kind=ActivityKind.TASK_COMPLETED)
        await svc.record_activity(member_id=mid, kind=ActivityKind.MEMORY_CONTRIBUTED)
        await svc.record_activity(member_id=mid, kind=ActivityKind.SKILL_USED)

        assert len(repo._events) == 3

    @pytest.mark.asyncio
    async def test_get_timeline(self, setup):
        svc, repo, tx = setup
        mid = uuid4()

        await svc.record_activity(member_id=mid, kind=ActivityKind.TASK_COMPLETED)
        await svc.record_activity(member_id=mid, kind=ActivityKind.MEMORY_CONTRIBUTED)

        timeline = await svc.get_timeline(mid)
        assert len(timeline) == 2

    @pytest.mark.asyncio
    async def test_get_timeline_empty(self, setup):
        svc, repo, tx = setup
        timeline = await svc.get_timeline(uuid4())
        assert timeline == []

    @pytest.mark.asyncio
    async def test_get_timeline_limit(self, setup):
        svc, repo, tx = setup
        mid = uuid4()

        for i in range(10):
            await svc.record_activity(member_id=mid, kind=ActivityKind.TASK_COMPLETED)

        timeline = await svc.get_timeline(mid, limit=3)
        assert len(timeline) == 3

    @pytest.mark.asyncio
    async def test_record_activity_default_payload(self, setup):
        svc, repo, tx = setup
        event = await svc.record_activity(
            member_id=uuid4(), kind=ActivityKind.SKILL_ACQUIRED,
        )
        assert event.event_payload == {}


# ---------------------------------------------------------------------------
# Tests: GrowthStatisticsService
# ---------------------------------------------------------------------------


class TestGrowthStatisticsService:
    @pytest.fixture
    def setup(self):
        repo = MockActivityRepo()
        svc = GrowthStatisticsService(activity_repo=repo)
        return svc, repo

    @pytest.mark.asyncio
    async def test_empty_stats(self, setup):
        svc, repo = setup
        mid = uuid4()

        stats = await svc.compute_stats(mid)

        assert stats.member_id == mid
        assert stats.memory_contributions == 0
        assert stats.tasks_completed == 0
        assert stats.tasks_failed == 0
        assert stats.first_pass_rate == 0.0
        assert stats.skills_used == 0
        assert stats.activity_trend == 0.0

    @pytest.mark.asyncio
    async def test_first_pass_rate_calculation(self, setup):
        svc, repo = setup
        mid = uuid4()

        for _ in range(7):
            await svc._repo.save(ActivityEvent(
                member_id=mid, event_kind=ActivityKind.TASK_COMPLETED,
            ))
        for _ in range(3):
            await svc._repo.save(ActivityEvent(
                member_id=mid, event_kind=ActivityKind.TASK_FAILED,
            ))

        stats = await svc.compute_stats(mid)

        assert stats.tasks_completed == 7
        assert stats.tasks_failed == 3
        assert stats.first_pass_rate == 0.7

    @pytest.mark.asyncio
    async def test_memory_contributions_counted(self, setup):
        svc, repo = setup
        mid = uuid4()

        for _ in range(5):
            await repo.save(ActivityEvent(
                member_id=mid, event_kind=ActivityKind.MEMORY_CONTRIBUTED,
            ))

        stats = await svc.compute_stats(mid)
        assert stats.memory_contributions == 5

    @pytest.mark.asyncio
    async def test_activity_trend_up(self, setup):
        svc, repo = setup
        mid = uuid4()
        now = datetime.now(timezone.utc)

        # Recent 7 days: 10 events
        for _ in range(10):
            await repo.save(ActivityEvent(
                member_id=mid,
                event_kind=ActivityKind.TASK_COMPLETED,
                occurred_at=now - timedelta(days=3),
            ))

        # Previous 7 days: 5 events
        for _ in range(5):
            await repo.save(ActivityEvent(
                member_id=mid,
                event_kind=ActivityKind.TASK_COMPLETED,
                occurred_at=now - timedelta(days=10),
            ))

        stats = await svc.compute_stats(mid, now=now)
        assert stats.activity_trend > 0  # Uptrend

    @pytest.mark.asyncio
    async def test_activity_trend_down(self, setup):
        svc, repo = setup
        mid = uuid4()
        now = datetime.now(timezone.utc)

        # Recent 7 days: 2 events
        for _ in range(2):
            await repo.save(ActivityEvent(
                member_id=mid,
                event_kind=ActivityKind.TASK_COMPLETED,
                occurred_at=now - timedelta(days=3),
            ))

        # Previous 7 days: 10 events
        for _ in range(10):
            await repo.save(ActivityEvent(
                member_id=mid,
                event_kind=ActivityKind.TASK_COMPLETED,
                occurred_at=now - timedelta(days=10),
            ))

        stats = await svc.compute_stats(mid, now=now)
        assert stats.activity_trend < 0  # Downtrend

    @pytest.mark.asyncio
    async def test_skills_used_counted(self, setup):
        svc, repo = setup
        mid = uuid4()

        for _ in range(3):
            await repo.save(ActivityEvent(
                member_id=mid, event_kind=ActivityKind.SKILL_USED,
            ))

        stats = await svc.compute_stats(mid)
        assert stats.skills_used == 3


# ---------------------------------------------------------------------------
# Tests: SkillDecayDetector
# ---------------------------------------------------------------------------


class TestSkillDecayDetector:
    @pytest.fixture
    def setup(self):
        usage = MockSkillUsage()
        detector = SkillDecayDetector(skill_usage=usage)
        return detector, usage

    @pytest.mark.asyncio
    async def test_no_decay_below_threshold(self, setup):
        detector, usage = setup
        mid = uuid4()
        usage.set_consecutive_failures(mid, "python", 2)

        warning = await detector.check_decay(mid, "python")
        assert warning is None

    @pytest.mark.asyncio
    async def test_warning_at_threshold(self, setup):
        detector, usage = setup
        mid = uuid4()
        usage.set_consecutive_failures(mid, "python", DECAY_WARNING_THRESHOLD)

        warning = await detector.check_decay(mid, "python")

        assert warning is not None
        assert warning.warning_level == "warning"
        assert warning.consecutive_failures == DECAY_WARNING_THRESHOLD

    @pytest.mark.asyncio
    async def test_critical_at_threshold(self, setup):
        detector, usage = setup
        mid = uuid4()
        usage.set_consecutive_failures(mid, "python", DECAY_CRITICAL_THRESHOLD)

        warning = await detector.check_decay(mid, "python")

        assert warning is not None
        assert warning.warning_level == "critical"
        assert warning.consecutive_failures == DECAY_CRITICAL_THRESHOLD

    @pytest.mark.asyncio
    async def test_above_critical(self, setup):
        detector, usage = setup
        mid = uuid4()
        usage.set_consecutive_failures(mid, "docker", 10)

        warning = await detector.check_decay(mid, "docker")

        assert warning is not None
        assert warning.warning_level == "critical"
        assert "10" in warning.message

    @pytest.mark.asyncio
    async def test_check_multiple_skills(self, setup):
        detector, usage = setup
        mid = uuid4()
        usage.set_consecutive_failures(mid, "python", 5)
        usage.set_consecutive_failures(mid, "testing", 3)
        usage.set_consecutive_failures(mid, "docker", 1)

        warnings = await detector.check_multiple_skills(
            mid, ["python", "testing", "docker"],
        )

        assert len(warnings) == 2  # python(critical) + testing(warning)
        skill_ids = {w.skill_id for w in warnings}
        assert "python" in skill_ids
        assert "testing" in skill_ids
        assert "docker" not in skill_ids

    @pytest.mark.asyncio
    async def test_no_warning_for_zero_failures(self, setup):
        detector, usage = setup
        mid = uuid4()

        warning = await detector.check_decay(mid, "python")
        assert warning is None


# ---------------------------------------------------------------------------
# Tests: Value objects & Constants
# ---------------------------------------------------------------------------


class TestActivityValueObjects:
    def test_activity_kind_values(self):
        assert ActivityKind.TASK_COMPLETED == "task_completed"
        assert ActivityKind.MEMORY_CONTRIBUTED == "memory_contributed"
        assert ActivityKind.SKILL_ACQUIRED == "skill_acquired"

    def test_activity_event_defaults(self):
        mid = uuid4()
        event = ActivityEvent(member_id=mid)
        assert event.event_kind == ActivityKind.TASK_COMPLETED
        assert event.event_payload == {}

    def test_growth_stats_frozen(self):
        stats = GrowthStats(member_id=uuid4(), tasks_completed=10)
        assert stats.tasks_completed == 10
        with pytest.raises(AttributeError):
            stats.tasks_completed = 5  # type: ignore

    def test_decay_warning_frozen(self):
        w = DecayWarning(
            member_id=uuid4(),
            skill_id="python",
            consecutive_failures=5,
            warning_level="critical",
        )
        assert w.warning_level == "critical"

    def test_decay_thresholds(self):
        assert DECAY_WARNING_THRESHOLD == 3
        assert DECAY_CRITICAL_THRESHOLD == 5
