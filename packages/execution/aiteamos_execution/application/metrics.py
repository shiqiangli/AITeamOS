"""
Execution Context — 价值度量 API (plan.md §4.5.1)。

ValueMetricsService: 价值度量计算。
SystemHealthService: 系统健康度指标。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValueMetrics:
    """价值度量指标。"""

    tasks_avoided_rework: int = 0  # 本月 Memory 避免重复失败的 Task 数
    new_member_onboarding_boost: float = 0.0  # 新 Member 上手效率提升
    memory_active_rate: float = 0.0  # Memory 库活跃率
    unresolved_conflicts: int = 0  # 未解决冲突数
    period: str = "monthly"  # daily/weekly/monthly


@dataclass(frozen=True)
class SystemHealthMetrics:
    """系统健康度指标。"""

    task_first_pass_rate: float = 0.0  # Task 首次通过率
    avg_fix_rounds: float = 0.0  # 平均修复轮次
    skill_health_distribution: dict[str, int] = field(default_factory=dict)
    validation_availability: float = 1.0  # 验证系统可用性 (0~1)
    total_tasks: int = 0
    total_members: int = 0


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class MetricsDataProvider(Protocol):
    """度量数据源。"""

    async def count_tasks_avoided_rework(self, *, since: datetime) -> int: ...
    async def get_onboarding_efficiency(self) -> float: ...
    async def get_memory_active_rate(self) -> float: ...
    async def count_unresolved_conflicts(self) -> int: ...
    async def get_task_first_pass_rate(self) -> float: ...
    async def get_avg_fix_rounds(self) -> float: ...
    async def get_skill_health(self) -> dict[str, int]: ...
    async def get_validation_availability(self) -> float: ...
    async def count_total_tasks(self) -> int: ...
    async def count_total_members(self) -> int: ...


# ---------------------------------------------------------------------------
# ValueMetricsService (plan.md §4.5.1)
# ---------------------------------------------------------------------------


class ValueMetricsService:
    """价值度量计算服务。"""

    def __init__(self, *, data_provider: MetricsDataProvider):
        self._provider = data_provider

    async def compute_value_metrics(
        self,
        *,
        period: str = "monthly",
        now: datetime | None = None,
    ) -> ValueMetrics:
        """计算价值度量。"""
        current_time = now or datetime.now(timezone.utc)

        from datetime import timedelta
        if period == "daily":
            since = current_time - timedelta(days=1)
        elif period == "weekly":
            since = current_time - timedelta(weeks=1)
        else:
            since = current_time - timedelta(days=30)

        avoided = await self._provider.count_tasks_avoided_rework(since=since)
        onboarding = await self._provider.get_onboarding_efficiency()
        active_rate = await self._provider.get_memory_active_rate()
        conflicts = await self._provider.count_unresolved_conflicts()

        return ValueMetrics(
            tasks_avoided_rework=avoided,
            new_member_onboarding_boost=round(onboarding, 4),
            memory_active_rate=round(active_rate, 4),
            unresolved_conflicts=conflicts,
            period=period,
        )


class SystemHealthService:
    """系统健康度指标服务。"""

    def __init__(self, *, data_provider: MetricsDataProvider):
        self._provider = data_provider

    async def compute_health(self) -> SystemHealthMetrics:
        """计算系统健康度。"""
        first_pass = await self._provider.get_task_first_pass_rate()
        avg_rounds = await self._provider.get_avg_fix_rounds()
        skill_health = await self._provider.get_skill_health()
        availability = await self._provider.get_validation_availability()
        total_tasks = await self._provider.count_total_tasks()
        total_members = await self._provider.count_total_members()

        return SystemHealthMetrics(
            task_first_pass_rate=round(first_pass, 4),
            avg_fix_rounds=round(avg_rounds, 2),
            skill_health_distribution=skill_health,
            validation_availability=round(availability, 4),
            total_tasks=total_tasks,
            total_members=total_members,
        )
