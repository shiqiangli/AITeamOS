"""
Knowledge Context — Memory 反馈回路 (plan.md §2.6b.1, arch.md §2.6)。

核心职责:
1. 监听 Task 执行结果，写入 memory_feedback 记录
2. ConfidenceAdjustmentService.on_feedback(): 实时调整置信度
3. 每日批量衰减扫描 (daily_decay_sweep)
4. 元递归隔离: system_meta 反馈不参与置信度更新

衰减方程 (arch.md §2.6):
    C(t+Δt) = clamp(C_t · e^(-λ·Δt) + α·F_pos - β·F_neg, 0, 1)

参数表:
    | 参数       | Facts | Patterns | Principles |
    |------------|-------|----------|------------|
    | λ (半衰期) | 0     | 1/180d   | 1/365d     |
    | α (正反馈) | 0.05  | 0.08     | 0.05       |
    | β (负反馈) | 0.20  | 0.15     | 0.10       |
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID, uuid4

from aiteamos_shared.types import MemberId, MemoryId, RunId, TaskId, new_id

from ..domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryNode,
    Tier,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 衰减参数 (arch.md §2.6)
# ---------------------------------------------------------------------------

# λ (decay rate per day) — Facts 不衰减
DECAY_LAMBDA: dict[str, float] = {
    Tier.FACTS: 0.0,
    Tier.PATTERNS: 1.0 / 180,
    Tier.PRINCIPLES: 1.0 / 365,
}

# α (正反馈系数)
ALPHA_POS: dict[str, float] = {
    Tier.FACTS: 0.05,
    Tier.PATTERNS: 0.08,
    Tier.PRINCIPLES: 0.05,
}

# β (负反馈系数)
BETA_NEG: dict[str, float] = {
    Tier.FACTS: 0.20,
    Tier.PATTERNS: 0.15,
    Tier.PRINCIPLES: 0.10,
}

# 隔离阈值: 置信度低于此值 → needs_verify + quarantined
THRESHOLD_QUARANTINE = Decimal("0.30")

# 每日衰减批处理大小
BATCH_DECAY_SIZE = 5000


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeedbackOutcome:
    """反馈结果。"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class MemoryFeedback:
    """Memory 反馈记录 (对应 memory_feedback 表)。"""

    id: UUID
    memory_id: MemoryId
    task_run_id: UUID
    outcome: str  # positive | negative | neutral
    delta: Decimal
    reviewer_member_id: MemberId | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_system_meta: bool = False
    triggered_by_system_meta: bool = False


@dataclass(frozen=True)
class FeedbackStats:
    """Memory 反馈统计 (追踪指标)。"""

    memory_id: MemoryId
    total_uses: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0

    @property
    def positive_rate(self) -> float:
        if self.total_uses == 0:
            return 0.0
        return self.positive_count / self.total_uses

    @property
    def negative_rate(self) -> float:
        if self.total_uses == 0:
            return 0.0
        return self.negative_count / self.total_uses


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class MemoryNodeRepoLike(Protocol):
    async def save(self, aggregate: MemoryNode, *, tx: Any = None) -> None: ...
    async def lock_for_update(self, memory_id: MemoryId, *, tx: Any = None) -> MemoryNode | None: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class FeedbackStoreLike(Protocol):
    """反馈记录存储协议。"""
    async def insert_feedback(self, feedback: MemoryFeedback, *, tx: Any = None) -> None: ...
    async def get_stats(self, memory_id: MemoryId) -> FeedbackStats: ...
    async def get_unique_task_count(self, memory_id: MemoryId) -> int: ...
    async def get_unique_project_count(self, memory_id: MemoryId) -> int: ...
    async def get_unique_department_count(self, memory_id: MemoryId) -> int: ...


# ---------------------------------------------------------------------------
# MemoryFeedbackCollector — 收集 Task 执行反馈
# ---------------------------------------------------------------------------


class MemoryFeedbackCollector:
    """监听 Task 执行结果，收集 Memory 使用反馈。

    职责:
    - Task 通过且使用了某 Memory → positive 反馈
    - Task 失败且使用了某 Memory → negative 反馈
    - 写入 memory_feedback 记录
    - 发布 MemoryFeedbackRecorded 事件
    """

    def __init__(
        self,
        *,
        feedback_store: FeedbackStoreLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._store = feedback_store
        self._tx = tx_manager
        self._publisher = event_publisher

    async def record_task_outcome(
        self,
        *,
        memory_ids: list[MemoryId],
        task_run_id: UUID,
        task_id: TaskId,
        outcome: str,
        is_system_meta: bool = False,
        triggered_by_system_meta: bool = False,
    ) -> list[MemoryFeedback]:
        """记录 Task 执行结果对 Memory 的反馈。

        Args:
            memory_ids: 本次 Task 使用过的 Memory ID 列表
            task_run_id: Task Run ID
            task_id: Task ID
            outcome: 'success' | 'failure' | 'cancelled'
            is_system_meta: 是否为系统元活动
            triggered_by_system_meta: 是否由系统元活动间接触发

        Returns:
            创建的反馈记录列表
        """
        if outcome == "cancelled":
            return []

        feedback_outcome = (
            FeedbackOutcome.POSITIVE
            if outcome == "success"
            else FeedbackOutcome.NEGATIVE
        )

        feedbacks: list[MemoryFeedback] = []
        async with self._tx.transaction() as tx:
            for memory_id in memory_ids:
                delta = self._compute_delta(feedback_outcome)
                feedback = MemoryFeedback(
                    id=new_id(),
                    memory_id=memory_id,
                    task_run_id=task_run_id,
                    outcome=feedback_outcome,
                    delta=delta,
                    is_system_meta=is_system_meta,
                    triggered_by_system_meta=triggered_by_system_meta,
                )
                await self._store.insert_feedback(feedback, tx=tx)
                feedbacks.append(feedback)

            # 发布事件
            from ..domain.events import MemoryFeedbackRecorded

            events = []
            for fb in feedbacks:
                events.append(MemoryFeedbackRecorded(
                    event_type="knowledge.memory_feedback.recorded",
                    memory_id=fb.memory_id,
                    task_run_id=fb.task_run_id,
                    outcome=fb.outcome,
                    delta=float(fb.delta),
                    is_system_meta=fb.is_system_meta,
                ))
            if events:
                await self._publisher.publish_events(
                    events,
                    partition_key=str(task_id),
                    tx=tx,
                )

        logger.info(
            "Recorded %d feedbacks for task=%s outcome=%s",
            len(feedbacks), task_id, outcome,
        )
        return feedbacks

    @staticmethod
    def _compute_delta(outcome: str) -> Decimal:
        """计算反馈 delta (简化: 正值=正向, 负值=负向)。"""
        if outcome == FeedbackOutcome.POSITIVE:
            return Decimal("0.050")
        elif outcome == FeedbackOutcome.NEGATIVE:
            return Decimal("-0.150")
        return Decimal("0.000")


# ---------------------------------------------------------------------------
# ConfidenceAdjustmentService — 实时置信度调整 (arch.md §2.6)
# ---------------------------------------------------------------------------


class ConfidenceAdjustmentService:
    """置信度动态调整服务。

    双通道实现:
    1. 通道 1: 实时事件驱动 (MemoryFeedbackRecorded → on_feedback)
    2. 通道 2: 每日批处理衰减 (daily_decay_sweep)

    元递归隔离:
    - is_system_meta=True → 跳过置信度更新
    - triggered_by_system_meta=True → 跳过置信度更新 (间接因果链)
    """

    def __init__(
        self,
        *,
        memory_repo: MemoryNodeRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = memory_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def on_feedback(self, feedback: MemoryFeedback) -> Decimal | None:
        """通道 1: 实时事件驱动 — 处理单条反馈调整置信度。

        Args:
            feedback: 反馈记录

        Returns:
            新的置信度值; 如果跳过则返回 None
        """
        # 元递归隔离: system_meta 反馈不参与置信度
        if feedback.is_system_meta:
            logger.debug("Skipping system_meta feedback for memory=%s", feedback.memory_id)
            return None

        # 间接系统源隔离 (arch.md §5.2.2)
        if feedback.triggered_by_system_meta:
            logger.debug(
                "Skipping indirect system_meta feedback for memory=%s",
                feedback.memory_id,
            )
            return None

        async with self._tx.transaction() as tx:
            mem = await self._repo.lock_for_update(feedback.memory_id, tx=tx)
            if mem is None:
                logger.warning("Memory %s not found for feedback", feedback.memory_id)
                return None

            old_value = mem.confidence.value
            new_value = self._compute_step(mem, feedback)

            # I-K-1: 通过 adjust_confidence 方法更新
            new_state = None
            if new_value < THRESHOLD_QUARANTINE:
                new_state = ConfidenceState.NEEDS_VERIFY

            mem.adjust_confidence(new_value, state=new_state)

            # 低置信度 → 隔离
            if new_value < THRESHOLD_QUARANTINE:
                mem.change_lifecycle(LifecycleState.QUARANTINED)
                logger.info(
                    "Memory %s quarantined: confidence %.3f < %.3f",
                    feedback.memory_id, float(new_value), float(THRESHOLD_QUARANTINE),
                )

            await self._repo.save(mem, tx=tx)

            # 发布聚合产生的事件
            events = mem.pending_events
            mem.clear_pending_events()
            if events:
                await self._publisher.publish_events(
                    events, partition_key=str(feedback.memory_id), tx=tx,
                )

        logger.debug(
            "Confidence adjusted: memory=%s old=%.3f new=%.3f outcome=%s",
            feedback.memory_id, float(old_value), float(new_value), feedback.outcome,
        )
        return new_value

    async def apply_decay(self, memory: MemoryNode, *, now: datetime | None = None) -> Decimal:
        """对单个 Memory 应用时间衰减。

        Facts (λ=0) 不参与时间衰减 (I-K-2)。

        Returns:
            衰减后的置信度值
        """
        current_time = now or datetime.now(timezone.utc)
        tier_key = memory.tier.value if isinstance(memory.tier, Tier) else str(memory.tier)
        lam = DECAY_LAMBDA.get(tier_key, 0.0)

        # Facts 不衰减
        if lam == 0.0:
            return memory.confidence.value

        # 计算时间差 (天)
        delta_days = (current_time - memory.confidence.last_decay_at).total_seconds() / 86400.0
        if delta_days <= 0:
            return memory.confidence.value

        # C(t+Δt) = C_t · e^(-λ·Δt)  (纯衰减，不含反馈项)
        old_value = float(memory.confidence.value)
        decayed = old_value * math.exp(-lam * delta_days)
        new_value = Decimal(str(max(0.0, min(1.0, decayed))))

        return new_value

    @staticmethod
    def _compute_step(memory: MemoryNode, feedback: MemoryFeedback) -> Decimal:
        """单步置信度调整 (arch.md §2.6 方程简化版 — 不含时间衰减部分)。

        C_new = clamp(C_t + α·F_pos - β·F_neg, 0, 1)
        """
        tier_key = memory.tier.value if isinstance(memory.tier, Tier) else str(memory.tier)
        alpha = Decimal(str(ALPHA_POS.get(tier_key, 0.05)))
        beta = Decimal(str(BETA_NEG.get(tier_key, 0.10)))

        current = memory.confidence.value

        if feedback.outcome == FeedbackOutcome.POSITIVE:
            new_value = current + alpha
        elif feedback.outcome == FeedbackOutcome.NEGATIVE:
            new_value = current - beta
        else:
            new_value = current

        # clamp to [0, 1]
        return max(Decimal("0"), min(Decimal("1"), new_value))

    async def daily_decay_sweep(
        self,
        *,
        decay_executor: Any = None,
    ) -> int:
        """通道 2: 每日批处理时间衰减 (arch.md §2.6)。

        按 id 游标分批推进，每批限 BATCH_DECAY_SIZE 行。
        Facts 不参与衰减 (I-K-2: λ=0)。

        Args:
            decay_executor: 提供 execute_batch_decay SQL 能力的仓储/执行器。
                需要实现 execute_batch_decay(sql, cursor_id, batch_size) 方法。
                如果为 None 则返回 0 (无操作)。

        Returns:
            衰减的总行数
        """
        if decay_executor is None:
            logger.info("No decay executor provided, skipping daily decay sweep")
            return 0

        BATCH_SIZE = BATCH_DECAY_SIZE
        cursor_id = UUID(int=0)
        total = 0

        # 衰减 SQL (arch.md §2.6)
        DECAY_SQL = """
            WITH batch AS (
                SELECT id FROM memory_node
                WHERE id > $1
                  AND lifecycle_state IN ('active', 'needs_verify')
                  AND tier != 'facts'
                  AND last_decay_at < now() - INTERVAL '1 day'
                ORDER BY id LIMIT $2
            )
            UPDATE memory_node SET
                confidence_value = GREATEST(0,
                    confidence_value * EXP(-(
                        CASE tier
                            WHEN 'patterns' THEN 1.0/180
                            WHEN 'principles' THEN 1.0/365
                        END
                    ) * EXTRACT(EPOCH FROM (now() - last_decay_at)) / 86400)
                ),
                last_decay_at = now()
            FROM batch WHERE memory_node.id = batch.id
            RETURNING memory_node.id
        """

        while True:
            affected = await decay_executor.execute_batch_decay(
                DECAY_SQL, cursor_id, BATCH_SIZE
            )
            if not affected:
                break
            total += len(affected)
            cursor_id = max(affected)

        if total > 0:
            logger.info("Daily decay sweep completed: %d rows affected", total)

        return total
