"""
Workforce Context — Member 活动追踪与成长统计 (plan.md §4.3)。

ActivityTrackingService: 消费领域事件，投影到活动流表。
GrowthStatisticsService: 成长统计 API (Memory 贡献、Task 完成率、Skill 使用)。
SkillDecayDetector: 能力衰减预警。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID, uuid4

from aiteamos_shared.types import MemberId

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActivityKind(StrEnum):
    """活动事件类型。"""

    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    MEMORY_CONTRIBUTED = "memory_contributed"
    REVIEW_PARTICIPATED = "review_participated"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    SKILL_ACQUIRED = "skill_acquired"
    SKILL_USED = "skill_used"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityEvent:
    """活动事件。"""

    id: UUID = field(default_factory=uuid4)
    member_id: MemberId = field(default_factory=lambda: UUID(int=0))
    event_kind: ActivityKind = ActivityKind.TASK_COMPLETED
    event_payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class GrowthStats:
    """Member 成长统计。"""

    member_id: MemberId
    memory_contributions: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    first_pass_rate: float = 0.0  # tasks_completed / (tasks_completed + tasks_failed)
    avg_fix_rounds: float = 0.0
    skills_used: int = 0
    activity_trend: float = 0.0  # 近 7 天活动 vs 前 7 天 (正=上升, 负=下降)


@dataclass(frozen=True)
class DecayWarning:
    """能力衰减预警。"""

    member_id: MemberId
    skill_id: str
    consecutive_failures: int
    warning_level: str  # "info" | "warning" | "critical"
    message: str = ""


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class ActivityRepoLike(Protocol):
    async def save(self, event: ActivityEvent, *, tx: Any = None) -> None: ...
    async def find_by_member(
        self,
        member_id: MemberId,
        *,
        limit: int = 50,
        offset: int = 0,
        tx: Any = None,
    ) -> list[ActivityEvent]: ...
    async def count_by_member_and_kind(
        self,
        member_id: MemberId,
        kind: str,
        *,
        since: datetime | None = None,
        tx: Any = None,
    ) -> int: ...
    async def count_by_member_in_range(
        self,
        member_id: MemberId,
        *,
        start: datetime,
        end: datetime,
        tx: Any = None,
    ) -> int: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class SkillUsageProvider(Protocol):
    """Skill 使用历史数据源。"""

    async def get_consecutive_failures(
        self, member_id: MemberId, skill_id: str
    ) -> int:
        """获取某 Member 某 Skill 连续失败次数。"""
        ...


# ---------------------------------------------------------------------------
# ActivityTrackingService (plan.md §4.3.1)
# ---------------------------------------------------------------------------


class ActivityTrackingService:
    """活动事件消费与聚合。

    消费领域事件，投影到 member_activity_event 表。
    支持时间线查询。
    """

    def __init__(
        self,
        *,
        activity_repo: ActivityRepoLike,
        tx_manager: TransactionManagerLike,
    ):
        self._repo = activity_repo
        self._tx = tx_manager

    async def record_activity(
        self,
        *,
        member_id: MemberId,
        kind: ActivityKind,
        payload: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> ActivityEvent:
        """记录活动事件。"""
        event = ActivityEvent(
            member_id=member_id,
            event_kind=kind,
            event_payload=payload or {},
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )

        async with self._tx.transaction() as tx:
            await self._repo.save(event, tx=tx)

        logger.debug(
            "Activity recorded: member=%s kind=%s", member_id, kind.value,
        )
        return event

    async def get_timeline(
        self,
        member_id: MemberId,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityEvent]:
        """获取 Member 活动时间线。"""
        return await self._repo.find_by_member(
            member_id, limit=limit, offset=offset,
        )


# ---------------------------------------------------------------------------
# GrowthStatisticsService (plan.md §4.3.2)
# ---------------------------------------------------------------------------


class GrowthStatisticsService:
    """Member 成长统计。

    计算:
    - Memory 贡献数
    - Task 完成数、首次通过率
    - Skill 使用频率
    - 活跃度趋势 (按周)
    """

    def __init__(self, *, activity_repo: ActivityRepoLike):
        self._repo = activity_repo

    async def compute_stats(
        self, member_id: MemberId, *, now: datetime | None = None
    ) -> GrowthStats:
        """计算 Member 成长统计。"""
        current_time = now or datetime.now(timezone.utc)

        memory_count = await self._repo.count_by_member_and_kind(
            member_id, ActivityKind.MEMORY_CONTRIBUTED.value,
        )
        tasks_completed = await self._repo.count_by_member_and_kind(
            member_id, ActivityKind.TASK_COMPLETED.value,
        )
        tasks_failed = await self._repo.count_by_member_and_kind(
            member_id, ActivityKind.TASK_FAILED.value,
        )
        skills_used = await self._repo.count_by_member_and_kind(
            member_id, ActivityKind.SKILL_USED.value,
        )

        # 首次通过率
        total_tasks = tasks_completed + tasks_failed
        first_pass_rate = tasks_completed / total_tasks if total_tasks > 0 else 0.0

        # 活跃度趋势: 近 7 天 vs 前 7 天
        from datetime import timedelta

        recent_start = current_time - timedelta(days=7)
        previous_start = current_time - timedelta(days=14)

        recent_count = await self._repo.count_by_member_in_range(
            member_id, start=recent_start, end=current_time,
        )
        previous_count = await self._repo.count_by_member_in_range(
            member_id, start=previous_start, end=recent_start,
        )

        if previous_count > 0:
            activity_trend = (recent_count - previous_count) / previous_count
        elif recent_count > 0:
            activity_trend = 1.0  # 从 0 到有活动
        else:
            activity_trend = 0.0

        return GrowthStats(
            member_id=member_id,
            memory_contributions=memory_count,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            first_pass_rate=round(first_pass_rate, 4),
            skills_used=skills_used,
            activity_trend=round(activity_trend, 4),
        )


# ---------------------------------------------------------------------------
# SkillDecayDetector (plan.md §4.3.3)
# ---------------------------------------------------------------------------

# 衰减预警阈值
DECAY_WARNING_THRESHOLD = 3  # 连续 3 次失败 -> warning
DECAY_CRITICAL_THRESHOLD = 5  # 连续 5 次失败 -> critical


class SkillDecayDetector:
    """能力衰减预警。

    - Skill 连续 N 次 Task 失败 -> 衰减预警
    - Memory 被分配但连续未召回 -> 分配不当提示
    """

    def __init__(self, *, skill_usage: SkillUsageProvider):
        self._usage = skill_usage

    async def check_decay(
        self,
        member_id: MemberId,
        skill_id: str,
    ) -> DecayWarning | None:
        """检查某 Member 某 Skill 的衰减状态。

        Returns:
            DecayWarning 或 None (无预警)
        """
        consecutive = await self._usage.get_consecutive_failures(
            member_id, skill_id,
        )

        if consecutive >= DECAY_CRITICAL_THRESHOLD:
            return DecayWarning(
                member_id=member_id,
                skill_id=skill_id,
                consecutive_failures=consecutive,
                warning_level="critical",
                message=f"Skill '{skill_id}' has failed {consecutive} consecutive times",
            )

        if consecutive >= DECAY_WARNING_THRESHOLD:
            return DecayWarning(
                member_id=member_id,
                skill_id=skill_id,
                consecutive_failures=consecutive,
                warning_level="warning",
                message=f"Skill '{skill_id}' has failed {consecutive} consecutive times",
            )

        return None

    async def check_multiple_skills(
        self,
        member_id: MemberId,
        skill_ids: list[str],
    ) -> list[DecayWarning]:
        """批量检查多个 Skill 的衰减状态。"""
        warnings: list[DecayWarning] = []
        for sid in skill_ids:
            warning = await self.check_decay(member_id, sid)
            if warning:
                warnings.append(warning)
        return warnings
