"""
Tests for Execution Context — Value Metrics & System Health (plan.md §4.5).
"""

from datetime import datetime, timezone

import pytest

from aiteamos_execution.application.metrics import (
    SystemHealthMetrics,
    SystemHealthService,
    ValueMetrics,
    ValueMetricsService,
)


# ---------------------------------------------------------------------------
# Mock data provider
# ---------------------------------------------------------------------------


class MockMetricsProvider:
    """In-memory metrics data provider for testing."""

    def __init__(
        self,
        *,
        tasks_avoided_rework: int = 12,
        onboarding_efficiency: float = 0.25,
        memory_active_rate: float = 0.72,
        unresolved_conflicts: int = 3,
        task_first_pass_rate: float = 0.85,
        avg_fix_rounds: float = 1.7,
        skill_health: dict | None = None,
        validation_availability: float = 0.998,
        total_tasks: int = 500,
        total_members: int = 20,
    ):
        self._tasks_avoided_rework = tasks_avoided_rework
        self._onboarding_efficiency = onboarding_efficiency
        self._memory_active_rate = memory_active_rate
        self._unresolved_conflicts = unresolved_conflicts
        self._task_first_pass_rate = task_first_pass_rate
        self._avg_fix_rounds = avg_fix_rounds
        self._skill_health = skill_health if skill_health is not None else {"active": 15, "warning": 3, "deprecated": 2}
        self._validation_availability = validation_availability
        self._total_tasks = total_tasks
        self._total_members = total_members
        self.last_since: datetime | None = None

    async def count_tasks_avoided_rework(self, *, since: datetime) -> int:
        self.last_since = since
        return self._tasks_avoided_rework

    async def get_onboarding_efficiency(self) -> float:
        return self._onboarding_efficiency

    async def get_memory_active_rate(self) -> float:
        return self._memory_active_rate

    async def count_unresolved_conflicts(self) -> int:
        return self._unresolved_conflicts

    async def get_task_first_pass_rate(self) -> float:
        return self._task_first_pass_rate

    async def get_avg_fix_rounds(self) -> float:
        return self._avg_fix_rounds

    async def get_skill_health(self) -> dict[str, int]:
        return self._skill_health

    async def get_validation_availability(self) -> float:
        return self._validation_availability

    async def count_total_tasks(self) -> int:
        return self._total_tasks

    async def count_total_members(self) -> int:
        return self._total_members


# ---------------------------------------------------------------------------
# TestValueMetricsService
# ---------------------------------------------------------------------------


class TestValueMetricsService:
    async def test_compute_monthly_metrics(self):
        provider = MockMetricsProvider()
        svc = ValueMetricsService(data_provider=provider)
        result = await svc.compute_value_metrics(period="monthly")

        assert isinstance(result, ValueMetrics)
        assert result.tasks_avoided_rework == 12
        assert result.new_member_onboarding_boost == 0.25
        assert result.memory_active_rate == 0.72
        assert result.unresolved_conflicts == 3
        assert result.period == "monthly"

    async def test_compute_daily_metrics(self):
        provider = MockMetricsProvider()
        svc = ValueMetricsService(data_provider=provider)
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = await svc.compute_value_metrics(period="daily", now=now)

        assert result.period == "daily"
        assert provider.last_since is not None
        # Daily = now - 1 day
        assert provider.last_since.day == 14

    async def test_compute_weekly_metrics(self):
        provider = MockMetricsProvider()
        svc = ValueMetricsService(data_provider=provider)
        now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = await svc.compute_value_metrics(period="weekly", now=now)

        assert result.period == "weekly"
        assert provider.last_since is not None
        # Weekly = now - 7 days
        assert provider.last_since.day == 8

    async def test_rounding(self):
        provider = MockMetricsProvider(
            onboarding_efficiency=0.123456789,
            memory_active_rate=0.987654321,
        )
        svc = ValueMetricsService(data_provider=provider)
        result = await svc.compute_value_metrics()

        assert result.new_member_onboarding_boost == 0.1235  # rounded to 4
        assert result.memory_active_rate == 0.9877  # rounded to 4

    async def test_zero_defaults(self):
        provider = MockMetricsProvider(
            tasks_avoided_rework=0,
            onboarding_efficiency=0.0,
            memory_active_rate=0.0,
            unresolved_conflicts=0,
        )
        svc = ValueMetricsService(data_provider=provider)
        result = await svc.compute_value_metrics()

        assert result.tasks_avoided_rework == 0
        assert result.new_member_onboarding_boost == 0.0
        assert result.memory_active_rate == 0.0
        assert result.unresolved_conflicts == 0

    async def test_custom_now(self):
        provider = MockMetricsProvider()
        svc = ValueMetricsService(data_provider=provider)
        now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = await svc.compute_value_metrics(period="monthly", now=now)

        assert result.period == "monthly"
        assert provider.last_since is not None
        # Monthly = now - 30 days => Dec 2, 2025
        assert provider.last_since.month == 12
        assert provider.last_since.day == 2

    def test_value_metrics_is_frozen(self):
        vm = ValueMetrics(tasks_avoided_rework=5)
        with pytest.raises(AttributeError):
            vm.tasks_avoided_rework = 10  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestSystemHealthService
# ---------------------------------------------------------------------------


class TestSystemHealthService:
    async def test_compute_health(self):
        provider = MockMetricsProvider()
        svc = SystemHealthService(data_provider=provider)
        result = await svc.compute_health()

        assert isinstance(result, SystemHealthMetrics)
        assert result.task_first_pass_rate == 0.85
        assert result.avg_fix_rounds == 1.7
        assert result.skill_health_distribution == {"active": 15, "warning": 3, "deprecated": 2}
        assert result.validation_availability == 0.998
        assert result.total_tasks == 500
        assert result.total_members == 20

    async def test_rounding(self):
        provider = MockMetricsProvider(
            task_first_pass_rate=0.123456,
            avg_fix_rounds=2.567,
            validation_availability=0.99999,
        )
        svc = SystemHealthService(data_provider=provider)
        result = await svc.compute_health()

        assert result.task_first_pass_rate == 0.1235  # rounded to 4
        assert result.avg_fix_rounds == 2.57  # rounded to 2
        assert result.validation_availability == 1.0  # rounded to 4

    async def test_empty_skill_health(self):
        provider = MockMetricsProvider(skill_health={})
        svc = SystemHealthService(data_provider=provider)
        result = await svc.compute_health()

        assert result.skill_health_distribution == {}

    async def test_zero_counts(self):
        provider = MockMetricsProvider(
            task_first_pass_rate=0.0,
            avg_fix_rounds=0.0,
            validation_availability=0.0,
            total_tasks=0,
            total_members=0,
        )
        svc = SystemHealthService(data_provider=provider)
        result = await svc.compute_health()

        assert result.task_first_pass_rate == 0.0
        assert result.avg_fix_rounds == 0.0
        assert result.validation_availability == 0.0
        assert result.total_tasks == 0
        assert result.total_members == 0

    async def test_perfect_scores(self):
        provider = MockMetricsProvider(
            task_first_pass_rate=1.0,
            avg_fix_rounds=1.0,
            validation_availability=1.0,
        )
        svc = SystemHealthService(data_provider=provider)
        result = await svc.compute_health()

        assert result.task_first_pass_rate == 1.0
        assert result.avg_fix_rounds == 1.0
        assert result.validation_availability == 1.0

    def test_system_health_metrics_is_frozen(self):
        shm = SystemHealthMetrics(total_tasks=100)
        with pytest.raises(AttributeError):
            shm.total_tasks = 200  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestValueObjects
# ---------------------------------------------------------------------------


class TestMetricsValueObjects:
    def test_value_metrics_defaults(self):
        vm = ValueMetrics()
        assert vm.tasks_avoided_rework == 0
        assert vm.new_member_onboarding_boost == 0.0
        assert vm.memory_active_rate == 0.0
        assert vm.unresolved_conflicts == 0
        assert vm.period == "monthly"

    def test_value_metrics_custom(self):
        vm = ValueMetrics(
            tasks_avoided_rework=50,
            new_member_onboarding_boost=0.5,
            memory_active_rate=0.9,
            unresolved_conflicts=1,
            period="weekly",
        )
        assert vm.tasks_avoided_rework == 50
        assert vm.period == "weekly"

    def test_system_health_defaults(self):
        shm = SystemHealthMetrics()
        assert shm.task_first_pass_rate == 0.0
        assert shm.avg_fix_rounds == 0.0
        assert shm.skill_health_distribution == {}
        assert shm.validation_availability == 1.0
        assert shm.total_tasks == 0
        assert shm.total_members == 0

    def test_system_health_custom(self):
        shm = SystemHealthMetrics(
            task_first_pass_rate=0.95,
            avg_fix_rounds=1.2,
            skill_health_distribution={"active": 10},
            validation_availability=0.999,
            total_tasks=1000,
            total_members=50,
        )
        assert shm.task_first_pass_rate == 0.95
        assert shm.total_members == 50

    def test_value_metrics_equality(self):
        a = ValueMetrics(tasks_avoided_rework=5, period="daily")
        b = ValueMetrics(tasks_avoided_rework=5, period="daily")
        assert a == b
