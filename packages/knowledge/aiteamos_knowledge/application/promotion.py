"""
Knowledge Context — Memory 层级晋升 (plan.md §2.6b.2, PRD §3.1.2 + §3.1.6)。

核心职责:
1. 评估 Memory 是否满足晋升条件
2. 发起晋升申请 (需人工审核)
3. 执行晋升操作 (修改 tier + 追加版本 + 发布事件)
4. 推荐晋升候选 (系统自动推荐)

晋升条件:
- Facts → Patterns:
  - 被 ≥5 个不同 Task 使用且正向反馈率 > 80%
  - 跨 ≥2 个 Project 验证过
  - 由人工审核确认晋升

- Patterns → Principles:
  - 跨 ≥3 个 Department 使用
  - 置信度 ≥ 0.85 持续 30 天
  - 由人工审核确认 + 验证"跨场景适用性"

高价值扩散 (PRD §3.1.4):
- 当 Memory 连续 N 次帮助 Task 首次 Pass → 生成扩散推荐
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from aiteamos_shared.types import MemberId, MemoryId, new_id

from ..domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryNode,
    MemoryVersion,
    Tier,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 晋升阈值常量
# ---------------------------------------------------------------------------

# Facts → Patterns 条件
FACTS_MIN_UNIQUE_TASKS = 5
FACTS_MIN_POSITIVE_RATE = 0.80
FACTS_MIN_PROJECTS = 2

# Patterns → Principles 条件
PATTERNS_MIN_DEPARTMENTS = 3
PATTERNS_MIN_CONFIDENCE = Decimal("0.85")
PATTERNS_MIN_CONFIDENCE_DAYS = 30

# 高价值扩散: 连续帮助 Task 首次 Pass 的次数阈值
SPREAD_CONSECUTIVE_PASSES = 3


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromotionEvaluation:
    """晋升评估结果。"""

    memory_id: MemoryId
    current_tier: str
    target_tier: str
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.eligible


@dataclass(frozen=True)
class PromotionCandidate:
    """系统推荐的晋升候选。"""

    memory_id: MemoryId
    title: str
    current_tier: str
    target_tier: str
    confidence: Decimal
    score: float  # 综合评分 (用于排序)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpreadRecommendation:
    """Memory 高价值扩散推荐 (PRD §3.1.4)。"""

    memory_id: MemoryId
    title: str
    consecutive_passes: int
    recommended_scope_refs: list[UUID] = field(default_factory=list)
    reason: str = ""


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class MemoryNodeRepoLike(Protocol):
    async def save(self, aggregate: MemoryNode, *, tx: Any = None) -> None: ...
    async def lock_for_update(self, memory_id: MemoryId, *, tx: Any = None) -> MemoryNode | None: ...
    async def get_by_id(self, memory_id: MemoryId, *, tx: Any = None) -> MemoryNode | None: ...


class FeedbackStoreLike(Protocol):
    """反馈数据存储协议。"""
    async def get_unique_task_count(self, memory_id: MemoryId) -> int: ...
    async def get_positive_rate(self, memory_id: MemoryId) -> float: ...
    async def get_unique_project_count(self, memory_id: MemoryId) -> int: ...
    async def get_unique_department_count(self, memory_id: MemoryId) -> int: ...
    async def get_consecutive_first_passes(self, memory_id: MemoryId) -> int: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


# ---------------------------------------------------------------------------
# MemoryTierPromotionService — 层级晋升核心服务
# ---------------------------------------------------------------------------


class MemoryTierPromotionService:
    """Memory 层级晋升服务。

    提供:
    - evaluate(): 评估单个 Memory 是否满足晋升条件
    - request_promotion(): 发起晋升申请 (创建 ReviewCase)
    - approve_promotion(): 审核通过后执行晋升
    - find_candidates(): 系统推荐晋升候选列表
    """

    def __init__(
        self,
        *,
        memory_repo: MemoryNodeRepoLike,
        feedback_store: FeedbackStoreLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = memory_repo
        self._feedback = feedback_store
        self._tx = tx_manager
        self._publisher = event_publisher

    async def evaluate(self, memory_id: MemoryId) -> PromotionEvaluation:
        """评估 Memory 是否满足晋升条件。

        Returns:
            PromotionEvaluation (eligible=True 表示满足所有条件)
        """
        mem = await self._repo.get_by_id(memory_id)
        if mem is None:
            return PromotionEvaluation(
                memory_id=memory_id,
                current_tier="unknown",
                target_tier="unknown",
                eligible=False,
                reasons=["Memory not found"],
            )

        # 非 active 状态不参与晋升
        if mem.lifecycle != LifecycleState.ACTIVE:
            return PromotionEvaluation(
                memory_id=memory_id,
                current_tier=mem.tier.value,
                target_tier=self._next_tier(mem.tier),
                eligible=False,
                reasons=[f"Lifecycle state is {mem.lifecycle}, must be active"],
            )

        if mem.tier == Tier.FACTS:
            return await self._evaluate_facts_to_patterns(mem)
        elif mem.tier == Tier.PATTERNS:
            return await self._evaluate_patterns_to_principles(mem)
        else:
            # Principles 是最高层级，无法再晋升
            return PromotionEvaluation(
                memory_id=memory_id,
                current_tier=Tier.PRINCIPLES,
                target_tier="none",
                eligible=False,
                reasons=["Principles is the highest tier"],
            )

    async def request_promotion(
        self,
        memory_id: MemoryId,
        *,
        requested_by: MemberId,
        reason: str = "",
    ) -> PromotionEvaluation:
        """发起晋升申请。

        评估条件后将申请事件发布到事件总线，
        由 Governance Context 创建 ReviewCase。

        Returns:
            评估结果 (eligible 表示是否满足自动晋升条件)
        """
        evaluation = await self.evaluate(memory_id)

        # 无论是否符合条件，都发布申请事件 (人工可 override)
        from ..domain.events import MemoryPromotionRequested

        event = MemoryPromotionRequested(
            event_type="knowledge.memory_node.promotion_requested",
            memory_id=memory_id,
            current_tier=evaluation.current_tier,
            target_tier=evaluation.target_tier,
            reason=reason or f"Promotion request from {requested_by}",
        )

        async with self._tx.transaction() as tx:
            await self._publisher.publish_events(
                [event], partition_key=str(memory_id), tx=tx,
            )

        logger.info(
            "Promotion requested: memory=%s %s→%s eligible=%s by=%s",
            memory_id, evaluation.current_tier, evaluation.target_tier,
            evaluation.eligible, requested_by,
        )
        return evaluation

    async def approve_promotion(
        self,
        memory_id: MemoryId,
        *,
        approved_by: MemberId,
    ) -> MemoryNode:
        """审核通过并执行晋升。

        操作:
        1. 修改 tier 字段
        2. 追加版本记录 (reason='tier_promotion')
        3. 发布 MemoryTierPromoted 事件

        Args:
            memory_id: Memory ID
            approved_by: 审核人 MemberId

        Returns:
            晋升后的 MemoryNode

        Raises:
            ValueError: Memory 不存在或已是最高层级
        """
        async with self._tx.transaction() as tx:
            mem = await self._repo.lock_for_update(memory_id, tx=tx)
            if mem is None:
                raise ValueError(f"Memory {memory_id} not found")

            old_tier = mem.tier
            new_tier = self._promote_tier(old_tier)
            if new_tier is None:
                raise ValueError(
                    f"Memory {memory_id} is already at highest tier ({old_tier})"
                )

            # 执行晋升
            mem.tier = new_tier

            # 追加版本记录
            version = mem.append_version(
                diff={
                    "tier_before": old_tier.value,
                    "tier_after": new_tier.value,
                },
                reason="tier_promotion",
                author_member_id=approved_by,
            )

            await self._repo.save(mem, tx=tx)

            # 发布晋升事件
            from ..domain.events import MemoryTierPromoted

            promote_event = MemoryTierPromoted(
                event_type="knowledge.memory_node.tier_promoted",
                memory_id=memory_id,
                old_tier=old_tier.value,
                new_tier=new_tier.value,
                promoted_by=approved_by,
            )

            events = [promote_event] + mem.pending_events
            mem.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(memory_id), tx=tx,
            )

        logger.info(
            "Memory promoted: id=%s %s→%s by=%s",
            memory_id, old_tier.value, new_tier.value, approved_by,
        )
        return mem

    async def find_candidates(
        self,
        *,
        limit: int = 50,
    ) -> list[PromotionCandidate]:
        """系统推荐的晋升候选列表。

        扫描 active 状态的 Facts 和 Patterns，评估其晋升潜力，
        按综合评分排序返回。
        """
        # 实际实现需要仓储提供按条件查询的能力
        # 此处为协议级实现，由 Composition Root 注入具体仓储
        logger.info("Finding promotion candidates (limit=%d)", limit)
        return []

    # -- 内部评估方法 --

    async def _evaluate_facts_to_patterns(self, mem: MemoryNode) -> PromotionEvaluation:
        """评估 Facts → Patterns 晋升条件。"""
        reasons: list[str] = []
        eligible = True

        # 条件 1: 被 ≥5 个不同 Task 使用
        unique_tasks = await self._feedback.get_unique_task_count(mem.id)
        if unique_tasks < FACTS_MIN_UNIQUE_TASKS:
            eligible = False
            reasons.append(
                f"Unique tasks: {unique_tasks} < {FACTS_MIN_UNIQUE_TASKS}"
            )

        # 条件 2: 正向反馈率 > 80%
        positive_rate = await self._feedback.get_positive_rate(mem.id)
        if positive_rate < FACTS_MIN_POSITIVE_RATE:
            eligible = False
            reasons.append(
                f"Positive rate: {positive_rate:.2%} < {FACTS_MIN_POSITIVE_RATE:.0%}"
            )

        # 条件 3: 跨 ≥2 个 Project 验证
        unique_projects = await self._feedback.get_unique_project_count(mem.id)
        if unique_projects < FACTS_MIN_PROJECTS:
            eligible = False
            reasons.append(
                f"Unique projects: {unique_projects} < {FACTS_MIN_PROJECTS}"
            )

        if eligible:
            reasons.append("All conditions met for Facts→Patterns promotion")

        return PromotionEvaluation(
            memory_id=mem.id,
            current_tier=Tier.FACTS,
            target_tier=Tier.PATTERNS,
            eligible=eligible,
            reasons=reasons,
            metrics={
                "unique_tasks": unique_tasks,
                "positive_rate": positive_rate,
                "unique_projects": unique_projects,
                "confidence": float(mem.confidence.value),
            },
        )

    async def _evaluate_patterns_to_principles(
        self, mem: MemoryNode
    ) -> PromotionEvaluation:
        """评估 Patterns → Principles 晋升条件。"""
        reasons: list[str] = []
        eligible = True

        # 条件 1: 跨 ≥3 个 Department 使用
        unique_depts = await self._feedback.get_unique_department_count(mem.id)
        if unique_depts < PATTERNS_MIN_DEPARTMENTS:
            eligible = False
            reasons.append(
                f"Unique departments: {unique_depts} < {PATTERNS_MIN_DEPARTMENTS}"
            )

        # 条件 2: 置信度 ≥ 0.85 持续 30 天
        now = datetime.now(timezone.utc)
        confidence_ok = mem.confidence.value >= PATTERNS_MIN_CONFIDENCE
        sustained_days = (now - mem.confidence.last_updated).days if confidence_ok else 0
        if not confidence_ok or sustained_days < PATTERNS_MIN_CONFIDENCE_DAYS:
            eligible = False
            reasons.append(
                f"Confidence {float(mem.confidence.value):.3f} sustained "
                f"{sustained_days}d < {PATTERNS_MIN_CONFIDENCE_DAYS}d "
                f"(min={float(PATTERNS_MIN_CONFIDENCE):.2f})"
            )

        if eligible:
            reasons.append(
                "All conditions met for Patterns→Principles promotion "
                "(human review + cross-scenario verification still required)"
            )

        return PromotionEvaluation(
            memory_id=mem.id,
            current_tier=Tier.PATTERNS,
            target_tier=Tier.PRINCIPLES,
            eligible=eligible,
            reasons=reasons,
            metrics={
                "unique_departments": unique_depts,
                "confidence": float(mem.confidence.value),
                "confidence_sustained_days": sustained_days,
            },
        )

    @staticmethod
    def _next_tier(current: Tier) -> str:
        """返回下一层级名称。"""
        if current == Tier.FACTS:
            return Tier.PATTERNS
        elif current == Tier.PATTERNS:
            return Tier.PRINCIPLES
        return "none"

    @staticmethod
    def _promote_tier(current: Tier) -> Tier | None:
        """执行层级晋升，返回新层级; 最高层返回 None。"""
        if current == Tier.FACTS:
            return Tier.PATTERNS
        elif current == Tier.PATTERNS:
            return Tier.PRINCIPLES
        return None


# ---------------------------------------------------------------------------
# MemorySpreadService — 高价值自动扩散 (PRD §3.1.4)
# ---------------------------------------------------------------------------


class MemorySpreadService:
    """Memory 高价值自动扩散推荐服务。

    当 Memory 连续 N 次帮助 Task 首次 Pass 时:
    - 生成扩散推荐 (MemorySpreadRecommendation)
    - 推荐给相似 Project 的 Member
    - 需管理者/Admin 确认后生效
    """

    def __init__(
        self,
        *,
        memory_repo: MemoryNodeRepoLike,
        feedback_store: FeedbackStoreLike,
    ):
        self._repo = memory_repo
        self._feedback = feedback_store

    async def check_spread_eligibility(
        self, memory_id: MemoryId
    ) -> SpreadRecommendation | None:
        """检查 Memory 是否满足扩散推荐条件。

        Returns:
            SpreadRecommendation 如果满足条件; 否则 None
        """
        consecutive = await self._feedback.get_consecutive_first_passes(memory_id)
        if consecutive < SPREAD_CONSECUTIVE_PASSES:
            return None

        mem = await self._repo.get_by_id(memory_id)
        if mem is None:
            return None

        return SpreadRecommendation(
            memory_id=memory_id,
            title=mem.title,
            consecutive_passes=consecutive,
            reason=(
                f"Memory helped {consecutive} consecutive tasks pass on first attempt. "
                f"Consider spreading to similar projects."
            ),
        )

    async def find_spread_candidates(
        self,
        memory_ids: list[MemoryId],
    ) -> list[SpreadRecommendation]:
        """批量检查扩散候选。"""
        recommendations: list[SpreadRecommendation] = []
        for mid in memory_ids:
            rec = await self.check_spread_eligibility(mid)
            if rec is not None:
                recommendations.append(rec)
        return recommendations
