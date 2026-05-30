"""
Execution Context — 智能推荐系统 (plan.md §4.2)。

三类推荐引擎:
1. MemberRecommender: 根据 Task Skills + Memory 匹配最佳 Member
   评分: Skill 覆盖度 × Memory 相关性 × 历史成功率 × 当前负载
2. MemoryRecommender: 为新 Member 推荐应分配的 Memory
   基于 Department + Project + 已有成功 Member 的分配模式
3. SkillRecommender: 根据 Task 描述推荐所需 Skill
   基于历史相似 Task 的 Skill 使用模式
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.types import MemberId, MemoryId, SkillId

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemberRecommendation:
    """Member 推荐结果。"""

    member_id: MemberId
    score: float
    skill_coverage: float
    memory_relevance: float
    success_rate: float
    load_factor: float
    reason: str = ""


@dataclass(frozen=True)
class MemoryRecommendation:
    """Memory 推荐结果。"""

    memory_id: MemoryId
    score: float
    reason: str = ""


@dataclass(frozen=True)
class SkillRecommendation:
    """Skill 推荐结果。"""

    skill_id: SkillId
    score: float
    reason: str = ""


@dataclass(frozen=True)
class TaskProfile:
    """Task 特征概要 (推荐引擎的输入)。"""

    task_id: str
    department_id: UUID
    project_ids: list[UUID] = field(default_factory=list)
    declared_skills: list[SkillId] = field(default_factory=list)
    declared_memory_hints: list[MemoryId] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Protocols — 数据源
# ---------------------------------------------------------------------------


class MemberProfileProvider(Protocol):
    """Member 画像数据源。"""

    async def get_member_skills(self, member_id: MemberId) -> list[SkillId]: ...
    async def get_member_memories(self, member_id: MemberId) -> list[MemoryId]: ...
    async def get_member_load(self, member_id: MemberId) -> float:
        """当前负载 (0.0=空闲, 1.0=满载)。"""
        ...
    async def get_member_success_rate(self, member_id: MemberId) -> float:
        """历史成功率 (0.0~1.0)。"""
        ...
    async def list_active_members(self) -> list[MemberId]: ...


class TaskHistoryProvider(Protocol):
    """Task 历史数据源。"""

    async def find_similar_tasks(
        self, description: str, tags: list[str], limit: int
    ) -> list[dict[str, Any]]:
        """查找历史相似 Task。

        返回 [{"task_id": ..., "skills": [...], "outcome": ...}, ...]
        """
        ...


class MemoryUsageProvider(Protocol):
    """Memory 使用模式数据源。"""

    async def get_popular_memories_for_department(
        self, department_id: UUID, limit: int
    ) -> list[MemoryId]: ...

    async def get_popular_memories_for_project(
        self, project_id: UUID, limit: int
    ) -> list[MemoryId]: ...

    async def get_successful_member_memories(
        self, department_id: UUID, limit: int
    ) -> list[MemoryId]:
        """获取同部门高成功率 Member 常用的 Memory。"""
        ...


# ---------------------------------------------------------------------------
# MemberRecommender (plan.md §4.2)
# ---------------------------------------------------------------------------


class MemberRecommender:
    """根据 Task 声明的 Skills + Memory hints，匹配最佳 Member。

    评分公式:
    score = skill_coverage × memory_relevance × success_rate × (1 - load_factor)

    权重说明:
    - skill_coverage: Member 技能集覆盖 Task 声明技能的比例
    - memory_relevance: Member 已分配 Memory 与 Task hints 的交集比例
    - success_rate: Member 历史 Task 成功率
    - load_factor: 当前负载 (越高越不利)
    """

    # 评分权重
    W_SKILL = 0.35
    W_MEMORY = 0.20
    W_SUCCESS = 0.30
    W_LOAD = 0.15

    def __init__(self, *, member_provider: MemberProfileProvider):
        self._provider = member_provider

    async def recommend(
        self,
        task: TaskProfile,
        *,
        top_k: int = 5,
        exclude_members: set[MemberId] | None = None,
    ) -> list[MemberRecommendation]:
        """推荐最佳 Member。

        Args:
            task: Task 特征概要
            top_k: 返回前 K 个推荐
            exclude_members: 排除的 Member ID 集合

        Returns:
            按 score 降序排列的推荐列表
        """
        excludes = exclude_members or set()
        all_members = await self._provider.list_active_members()
        candidates = [m for m in all_members if m not in excludes]

        if not candidates:
            return []

        recommendations: list[MemberRecommendation] = []

        for member_id in candidates:
            rec = await self._score_member(member_id, task)
            recommendations.append(rec)

        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations[:top_k]

    async def _score_member(
        self, member_id: MemberId, task: TaskProfile
    ) -> MemberRecommendation:
        """对单个 Member 评分。"""
        member_skills = await self._provider.get_member_skills(member_id)
        member_memories = await self._provider.get_member_memories(member_id)
        success_rate = await self._provider.get_member_success_rate(member_id)
        load = await self._provider.get_member_load(member_id)

        # Skill 覆盖度
        if task.declared_skills:
            covered = sum(1 for s in task.declared_skills if s in member_skills)
            skill_coverage = covered / len(task.declared_skills)
        else:
            skill_coverage = 0.5  # 无技能要求时给中性分

        # Memory 相关性
        if task.declared_memory_hints:
            matched = sum(
                1 for m in task.declared_memory_hints if m in member_memories
            )
            memory_relevance = matched / len(task.declared_memory_hints)
        else:
            memory_relevance = 0.3  # 无 hint 时给基础分

        # 综合评分
        score = (
            self.W_SKILL * skill_coverage
            + self.W_MEMORY * memory_relevance
            + self.W_SUCCESS * success_rate
            + self.W_LOAD * (1.0 - load)
        )

        return MemberRecommendation(
            member_id=member_id,
            score=round(score, 4),
            skill_coverage=round(skill_coverage, 4),
            memory_relevance=round(memory_relevance, 4),
            success_rate=round(success_rate, 4),
            load_factor=round(load, 4),
        )


# ---------------------------------------------------------------------------
# MemoryRecommender (plan.md §4.2)
# ---------------------------------------------------------------------------


class MemoryRecommender:
    """为新 Member 推荐应分配的 Memory。

    基于:
    - Department 热门 Memory
    - Project 热门 Memory
    - 同部门高成功率 Member 常用 Memory
    """

    W_DEPT = 0.30
    W_PROJECT = 0.40
    W_SUCCESS_PATTERN = 0.30

    def __init__(self, *, memory_provider: MemoryUsageProvider):
        self._provider = memory_provider

    async def recommend(
        self,
        *,
        department_id: UUID,
        project_ids: list[UUID] | None = None,
        existing_memories: set[MemoryId] | None = None,
        top_k: int = 10,
    ) -> list[MemoryRecommendation]:
        """推荐 Memory。

        Args:
            department_id: 目标部门
            project_ids: 关联项目
            existing_memories: 已分配的 Memory (去重)
            top_k: 返回前 K 个推荐
        """
        existing = existing_memories or set()
        scores: dict[MemoryId, float] = {}

        # Department 热门
        dept_memories = await self._provider.get_popular_memories_for_department(
            department_id, limit=top_k * 2,
        )
        for i, mid in enumerate(dept_memories):
            rank_score = 1.0 - (i / max(len(dept_memories), 1))
            scores[mid] = scores.get(mid, 0.0) + self.W_DEPT * rank_score

        # Project 热门
        if project_ids:
            for pid in project_ids:
                proj_memories = await self._provider.get_popular_memories_for_project(
                    pid, limit=top_k * 2,
                )
                for i, mid in enumerate(proj_memories):
                    rank_score = 1.0 - (i / max(len(proj_memories), 1))
                    scores[mid] = scores.get(mid, 0.0) + self.W_PROJECT * rank_score

        # 成功模式
        pattern_memories = await self._provider.get_successful_member_memories(
            department_id, limit=top_k * 2,
        )
        for i, mid in enumerate(pattern_memories):
            rank_score = 1.0 - (i / max(len(pattern_memories), 1))
            scores[mid] = scores.get(mid, 0.0) + self.W_SUCCESS_PATTERN * rank_score

        # 排除已有 + 排序
        recommendations = [
            MemoryRecommendation(
                memory_id=mid,
                score=round(s, 4),
                reason="recommended_by_dept_project_pattern",
            )
            for mid, s in scores.items()
            if mid not in existing
        ]
        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations[:top_k]


# ---------------------------------------------------------------------------
# SkillRecommender (plan.md §4.2)
# ---------------------------------------------------------------------------


class SkillRecommender:
    """根据 Task 描述推荐所需 Skill。

    基于历史相似 Task 的 Skill 使用模式。
    """

    def __init__(self, *, task_history: TaskHistoryProvider):
        self._history = task_history

    async def recommend(
        self,
        task: TaskProfile,
        *,
        top_k: int = 5,
        exclude_skills: set[SkillId] | None = None,
    ) -> list[SkillRecommendation]:
        """推荐 Skill。

        Args:
            task: Task 特征概要
            top_k: 返回前 K 个推荐
            exclude_skills: 排除的 Skill (如已声明的)
        """
        excludes = exclude_skills or set(task.declared_skills)

        similar_tasks = await self._history.find_similar_tasks(
            task.description, task.tags, limit=20,
        )

        if not similar_tasks:
            return []

        # 统计 Skill 频率 (按相似 Task 中的出现次数)
        skill_counts: dict[SkillId, int] = {}
        total = len(similar_tasks)

        for st in similar_tasks:
            for skill in st.get("skills", []):
                if skill not in excludes:
                    skill_counts[skill] = skill_counts.get(skill, 0) + 1

        # 按频率排序
        recommendations = [
            SkillRecommendation(
                skill_id=sid,
                score=round(count / total, 4),
                reason=f"used_in_{count}_of_{total}_similar_tasks",
            )
            for sid, count in skill_counts.items()
        ]
        recommendations.sort(key=lambda r: r.score, reverse=True)
        return recommendations[:top_k]
