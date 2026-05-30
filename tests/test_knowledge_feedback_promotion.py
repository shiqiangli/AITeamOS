"""
Knowledge Context — Memory 反馈回路 + 层级晋升 + 自动提取 测试。

验证标准 (plan.md §2.6b):
- 正向反馈正确提升置信度
- 负向反馈正确降低置信度并触发"待复核"
- 元递归隔离: system_meta 反馈不参与置信度更新
- 间接系统源隔离: triggered_by_system_meta 也跳过
- Facts 不参与时间衰减 (I-K-2)
- 晋升候选推荐逻辑正确
- 晋升需审核确认
- 提取引擎正确创建候选节点
- 单 Task 候选数量限流
"""

import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from aiteamos_shared.types import MemberId, MemoryId, RunId, TaskId, new_id
from aiteamos_knowledge.domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryNode,
    MemoryVersion,
    Provenance,
    Scope,
    ScopeKind,
    SourceKind,
    Tier,
)

# ---------------------------------------------------------------------------
# Mock Infrastructure (与 test_knowledge_application.py 保持一致)
# ---------------------------------------------------------------------------


class MockTransactionManager:
    """Mock transaction manager that yields a mock transaction."""

    def __init__(self):
        self.tx = MagicMock()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        yield self.tx


class MockEventPublisher:
    """Collects published events for assertion."""

    def __init__(self):
        self.published: list[tuple[list, str]] = []

    async def publish_events(
        self, events: list, *, partition_key: str, tx: Any
    ) -> None:
        self.published.append((events, partition_key))


class InMemoryMemoryRepo:
    """In-memory Memory 仓储 (测试用)。"""

    def __init__(self):
        self._store: dict[UUID, MemoryNode] = {}

    async def save(self, aggregate: MemoryNode, *, tx: Any = None) -> None:
        self._store[aggregate.id] = aggregate

    async def lock_for_update(
        self, memory_id: MemoryId, *, tx: Any = None
    ) -> MemoryNode | None:
        return self._store.get(memory_id)

    async def get_by_id(
        self, memory_id: MemoryId, *, tx: Any = None
    ) -> MemoryNode | None:
        return self._store.get(memory_id)


class InMemoryFeedbackStore:
    """In-memory 反馈存储 (测试用)。"""

    def __init__(self):
        self._feedbacks: list = []
        self._task_ids: dict[UUID, set] = {}  # memory_id → set of task_ids
        self._project_ids: dict[UUID, set] = {}
        self._dept_ids: dict[UUID, set] = {}
        self._consecutive_passes: dict[UUID, int] = {}
        self._positive_rates: dict[UUID, float] = {}

    async def insert_feedback(self, feedback: Any, *, tx: Any = None) -> None:
        self._feedbacks.append(feedback)

    async def get_stats(self, memory_id: MemoryId):
        from aiteamos_knowledge.application.feedback import FeedbackStats

        fb_list = [f for f in self._feedbacks if f.memory_id == memory_id]
        return FeedbackStats(
            memory_id=memory_id,
            total_uses=len(fb_list),
            positive_count=sum(1 for f in fb_list if f.outcome == "positive"),
            negative_count=sum(1 for f in fb_list if f.outcome == "negative"),
            neutral_count=sum(1 for f in fb_list if f.outcome == "neutral"),
        )

    async def get_unique_task_count(self, memory_id: MemoryId) -> int:
        return len(self._task_ids.get(memory_id, set()))

    async def get_positive_rate(self, memory_id: MemoryId) -> float:
        return self._positive_rates.get(memory_id, 0.0)

    async def get_unique_project_count(self, memory_id: MemoryId) -> int:
        return len(self._project_ids.get(memory_id, set()))

    async def get_unique_department_count(self, memory_id: MemoryId) -> int:
        return len(self._dept_ids.get(memory_id, set()))

    async def get_consecutive_first_passes(self, memory_id: MemoryId) -> int:
        return self._consecutive_passes.get(memory_id, 0)

    # -- 测试辅助 --
    def set_task_ids(self, memory_id: UUID, task_ids: set):
        self._task_ids[memory_id] = task_ids

    def set_project_ids(self, memory_id: UUID, project_ids: set):
        self._project_ids[memory_id] = project_ids

    def set_dept_ids(self, memory_id: UUID, dept_ids: set):
        self._dept_ids[memory_id] = dept_ids

    def set_positive_rate(self, memory_id: UUID, rate: float):
        self._positive_rates[memory_id] = rate

    def set_consecutive_passes(self, memory_id: UUID, count: int):
        self._consecutive_passes[memory_id] = count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    *,
    node_id: UUID | None = None,
    tier: Tier = Tier.FACTS,
    confidence_value: Decimal = Decimal("0.500"),
    lifecycle: LifecycleState = LifecycleState.ACTIVE,
    last_updated: datetime | None = None,
) -> MemoryNode:
    now = datetime.now(timezone.utc)
    return MemoryNode(
        id=node_id or new_id(),
        tier=tier,
        scope=Scope(kind=ScopeKind.GLOBAL),
        title="Test Memory",
        content=MemoryContent(statement="Test statement"),
        confidence=Confidence(
            value=confidence_value,
            state=ConfidenceState.VALID,
            last_updated=last_updated or now,
            last_decay_at=last_updated or now,
        ),
        provenance=Provenance(source_kind=SourceKind.TASK_EXECUTION),
        lifecycle=lifecycle,
    )


# ===========================================================================
# 1. MemoryFeedbackCollector 测试
# ===========================================================================


class TestMemoryFeedbackCollector:
    """测试 Memory 反馈收集器。"""

    def _make_collector(self):
        from aiteamos_knowledge.application.feedback import MemoryFeedbackCollector

        return MemoryFeedbackCollector(
            feedback_store=InMemoryFeedbackStore(),
            tx_manager=MockTransactionManager(),
            event_publisher=MockEventPublisher(),
        )

    @pytest.mark.asyncio
    async def test_record_success_creates_positive_feedback(self):
        """Task 成功 → 正向反馈。"""
        from aiteamos_knowledge.application.feedback import MemoryFeedbackCollector

        store = InMemoryFeedbackStore()
        publisher = MockEventPublisher()
        collector = MemoryFeedbackCollector(
            feedback_store=store,
            tx_manager=MockTransactionManager(),
            event_publisher=publisher,
        )

        memory_ids = [new_id(), new_id()]
        feedbacks = await collector.record_task_outcome(
            memory_ids=memory_ids,
            task_run_id=new_id(),
            task_id=TaskId("TASK-20260101T120000000-ABCD"),
            outcome="success",
        )

        assert len(feedbacks) == 2
        assert all(f.outcome == "positive" for f in feedbacks)
        assert all(f.delta > 0 for f in feedbacks)
        assert len(store._feedbacks) == 2

        # 验证事件发布
        assert len(publisher.published) == 1
        events, partition_key = publisher.published[0]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_record_failure_creates_negative_feedback(self):
        """Task 失败 → 负向反馈。"""
        from aiteamos_knowledge.application.feedback import MemoryFeedbackCollector

        store = InMemoryFeedbackStore()
        publisher = MockEventPublisher()
        collector = MemoryFeedbackCollector(
            feedback_store=store,
            tx_manager=MockTransactionManager(),
            event_publisher=publisher,
        )

        memory_id = new_id()
        feedbacks = await collector.record_task_outcome(
            memory_ids=[memory_id],
            task_run_id=new_id(),
            task_id=TaskId("TASK-20260101T120000000-ABCD"),
            outcome="failure",
        )

        assert len(feedbacks) == 1
        assert feedbacks[0].outcome == "negative"
        assert feedbacks[0].delta < 0

    @pytest.mark.asyncio
    async def test_cancelled_task_creates_no_feedback(self):
        """Task 取消 → 无反馈。"""
        collector = self._make_collector()

        feedbacks = await collector.record_task_outcome(
            memory_ids=[new_id()],
            task_run_id=new_id(),
            task_id=TaskId("TASK-20260101T120000000-ABCD"),
            outcome="cancelled",
        )

        assert feedbacks == []

    @pytest.mark.asyncio
    async def test_system_meta_flag_propagated(self):
        """system_meta 标记正确传播。"""
        from aiteamos_knowledge.application.feedback import MemoryFeedbackCollector

        store = InMemoryFeedbackStore()
        collector = MemoryFeedbackCollector(
            feedback_store=store,
            tx_manager=MockTransactionManager(),
            event_publisher=MockEventPublisher(),
        )

        feedbacks = await collector.record_task_outcome(
            memory_ids=[new_id()],
            task_run_id=new_id(),
            task_id=TaskId("TASK-20260101T120000000-ABCD"),
            outcome="success",
            is_system_meta=True,
        )

        assert len(feedbacks) == 1
        assert feedbacks[0].is_system_meta is True


# ===========================================================================
# 2. ConfidenceAdjustmentService 测试
# ===========================================================================


class TestConfidenceAdjustmentService:
    """测试置信度动态调整服务。"""

    def _make_service(self):
        from aiteamos_knowledge.application.feedback import ConfidenceAdjustmentService

        repo = InMemoryMemoryRepo()
        return (
            ConfidenceAdjustmentService(
                memory_repo=repo,
                tx_manager=MockTransactionManager(),
                event_publisher=MockEventPublisher(),
            ),
            repo,
        )

    @pytest.mark.asyncio
    async def test_positive_feedback_increases_confidence(self):
        """正向反馈提升置信度。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.500"), tier=Tier.FACTS)
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="positive",
            delta=Decimal("0.050"),
        )

        new_confidence = await svc.on_feedback(feedback)

        assert new_confidence is not None
        # Facts: alpha = 0.05 → 0.500 + 0.05 = 0.550
        assert new_confidence == Decimal("0.550")

    @pytest.mark.asyncio
    async def test_negative_feedback_decreases_confidence(self):
        """负向反馈降低置信度。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.500"), tier=Tier.FACTS)
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="negative",
            delta=Decimal("-0.150"),
        )

        new_confidence = await svc.on_feedback(feedback)

        assert new_confidence is not None
        # Facts: beta = 0.20 → 0.500 - 0.20 = 0.300
        assert new_confidence == Decimal("0.300")

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_quarantine(self):
        """置信度低于 0.30 → 隔离。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.350"), tier=Tier.FACTS)
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="negative",
            delta=Decimal("-0.150"),
        )

        new_confidence = await svc.on_feedback(feedback)

        # 0.350 - 0.20 = 0.150 < 0.30 → quarantined
        assert new_confidence is not None
        assert new_confidence == Decimal("0.150")
        updated = await repo.get_by_id(node.id)
        assert updated is not None
        assert updated.lifecycle == LifecycleState.QUARANTINED

    @pytest.mark.asyncio
    async def test_system_meta_feedback_skipped(self):
        """元递归隔离: system_meta 反馈跳过置信度更新。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.500"))
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="positive",
            delta=Decimal("0.050"),
            is_system_meta=True,
        )

        result = await svc.on_feedback(feedback)

        assert result is None
        # 置信度不变
        updated = await repo.get_by_id(node.id)
        assert updated is not None
        assert updated.confidence.value == Decimal("0.500")

    @pytest.mark.asyncio
    async def test_indirect_system_meta_feedback_skipped(self):
        """间接系统源隔离: triggered_by_system_meta 也跳过。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.500"))
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="positive",
            delta=Decimal("0.050"),
            triggered_by_system_meta=True,
        )

        result = await svc.on_feedback(feedback)

        assert result is None

    @pytest.mark.asyncio
    async def test_confidence_clamped_to_zero(self):
        """置信度下限为 0。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.100"), tier=Tier.FACTS)
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="negative",
            delta=Decimal("-0.150"),
        )

        new_confidence = await svc.on_feedback(feedback)

        # 0.100 - 0.20 = -0.100 → clamped to 0
        assert new_confidence is not None
        assert new_confidence == Decimal("0")

    @pytest.mark.asyncio
    async def test_confidence_clamped_to_one(self):
        """置信度上限为 1。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.980"), tier=Tier.FACTS)
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="positive",
            delta=Decimal("0.050"),
        )

        new_confidence = await svc.on_feedback(feedback)

        # 0.980 + 0.05 = 1.030 → clamped to 1.000
        assert new_confidence is not None
        assert new_confidence == Decimal("1")

    @pytest.mark.asyncio
    async def test_patterns_tier_uses_correct_coefficients(self):
        """Patterns 层级使用正确的系数 (α=0.08)。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.500"), tier=Tier.PATTERNS)
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="positive",
            delta=Decimal("0.050"),
        )

        new_confidence = await svc.on_feedback(feedback)

        # Patterns: alpha = 0.08 → 0.500 + 0.08 = 0.580
        assert new_confidence is not None
        assert new_confidence == Decimal("0.580")

    @pytest.mark.asyncio
    async def test_principles_tier_uses_correct_coefficients(self):
        """Principles 层级使用正确的系数 (β=0.10)。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.500"), tier=Tier.PRINCIPLES)
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="negative",
            delta=Decimal("-0.150"),
        )

        new_confidence = await svc.on_feedback(feedback)

        # Principles: beta = 0.10 → 0.500 - 0.10 = 0.400
        assert new_confidence is not None
        assert new_confidence == Decimal("0.400")

    @pytest.mark.asyncio
    async def test_neutral_feedback_no_change(self):
        """中性反馈不改变置信度。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.500"), tier=Tier.FACTS)
        await repo.save(node)

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="neutral",
            delta=Decimal("0.000"),
        )

        new_confidence = await svc.on_feedback(feedback)

        assert new_confidence is not None
        assert new_confidence == Decimal("0.500")

    @pytest.mark.asyncio
    async def test_nonexistent_memory_returns_none(self):
        """不存在的 Memory → 返回 None。"""
        from aiteamos_knowledge.application.feedback import (
            ConfidenceAdjustmentService,
            MemoryFeedback,
        )

        svc, repo = self._make_service()

        feedback = MemoryFeedback(
            id=new_id(),
            memory_id=new_id(),  # 不存在的 ID
            task_run_id=new_id(),
            outcome="positive",
            delta=Decimal("0.050"),
        )

        result = await svc.on_feedback(feedback)
        assert result is None

    @pytest.mark.asyncio
    async def test_apply_decay_facts_no_decay(self):
        """Facts (λ=0) 不参与时间衰减 (I-K-2)。"""
        svc, repo = self._make_service()
        node = _make_node(confidence_value=Decimal("0.800"), tier=Tier.FACTS)

        result = await svc.apply_decay(node)
        assert result == Decimal("0.800")

    @pytest.mark.asyncio
    async def test_apply_decay_patterns_decays(self):
        """Patterns (λ=1/180) 正确衰减。"""
        svc, repo = self._make_service()
        # 设置 last_decay_at 为 180 天前 → 应衰减约 50%
        old_time = datetime.now(timezone.utc) - timedelta(days=180)
        node = _make_node(
            confidence_value=Decimal("0.800"),
            tier=Tier.PATTERNS,
            last_updated=old_time,
        )

        result = await svc.apply_decay(node)

        # e^(-1/180 * 180) = e^(-1) ≈ 0.368
        # 0.800 * 0.368 ≈ 0.294
        assert result < Decimal("0.800")
        assert result > Decimal("0.200")

    @pytest.mark.asyncio
    async def test_apply_decay_no_time_elapsed(self):
        """无时间间隔 → 无衰减。"""
        svc, repo = self._make_service()
        now = datetime.now(timezone.utc)
        node = _make_node(
            confidence_value=Decimal("0.800"),
            tier=Tier.PATTERNS,
            last_updated=now,
        )

        result = await svc.apply_decay(node, now=now)
        assert result == Decimal("0.800")

    @pytest.mark.asyncio
    async def test_daily_decay_sweep_without_executor(self):
        """无 executor 时返回 0。"""
        svc, repo = self._make_service()
        result = await svc.daily_decay_sweep()
        assert result == 0


# ===========================================================================
# 3. FeedbackStats 测试
# ===========================================================================


class TestFeedbackStats:
    """测试反馈统计。"""

    def test_positive_rate(self):
        from aiteamos_knowledge.application.feedback import FeedbackStats

        stats = FeedbackStats(
            memory_id=new_id(),
            total_uses=10,
            positive_count=8,
            negative_count=2,
        )
        assert stats.positive_rate == 0.8
        assert stats.negative_rate == 0.2

    def test_zero_uses(self):
        from aiteamos_knowledge.application.feedback import FeedbackStats

        stats = FeedbackStats(memory_id=new_id())
        assert stats.positive_rate == 0.0
        assert stats.negative_rate == 0.0


# ===========================================================================
# 4. MemoryTierPromotionService 测试
# ===========================================================================


class TestMemoryTierPromotionService:
    """测试 Memory 层级晋升服务。"""

    def _make_service(self):
        from aiteamos_knowledge.application.promotion import MemoryTierPromotionService

        repo = InMemoryMemoryRepo()
        feedback = InMemoryFeedbackStore()
        return (
            MemoryTierPromotionService(
                memory_repo=repo,
                feedback_store=feedback,
                tx_manager=MockTransactionManager(),
                event_publisher=MockEventPublisher(),
            ),
            repo,
            feedback,
        )

    @pytest.mark.asyncio
    async def test_evaluate_facts_not_eligible_insufficient_tasks(self):
        """Facts 不满足条件: Task 使用数 < 5。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.FACTS)
        await repo.save(node)

        # 只被 2 个 Task 使用
        feedback.set_task_ids(node.id, {uuid4(), uuid4()})
        feedback.set_positive_rate(node.id, 0.90)
        feedback.set_project_ids(node.id, {uuid4(), uuid4()})

        evaluation = await svc.evaluate(node.id)

        assert not evaluation.eligible
        assert any("tasks" in r.lower() or "Tasks" in r for r in evaluation.reasons)

    @pytest.mark.asyncio
    async def test_evaluate_facts_not_eligible_low_positive_rate(self):
        """Facts 不满足条件: 正向反馈率 < 80%。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.FACTS)
        await repo.save(node)

        feedback.set_task_ids(node.id, {uuid4() for _ in range(5)})
        feedback.set_positive_rate(node.id, 0.60)  # < 80%
        feedback.set_project_ids(node.id, {uuid4(), uuid4()})

        evaluation = await svc.evaluate(node.id)

        assert not evaluation.eligible
        assert any("positive" in r.lower() or "Positive" in r for r in evaluation.reasons)

    @pytest.mark.asyncio
    async def test_evaluate_facts_not_eligible_insufficient_projects(self):
        """Facts 不满足条件: Project 数 < 2。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.FACTS)
        await repo.save(node)

        feedback.set_task_ids(node.id, {uuid4() for _ in range(5)})
        feedback.set_positive_rate(node.id, 0.90)
        feedback.set_project_ids(node.id, {uuid4()})  # 只有 1 个 project

        evaluation = await svc.evaluate(node.id)

        assert not evaluation.eligible
        assert any("project" in r.lower() or "Project" in r for r in evaluation.reasons)

    @pytest.mark.asyncio
    async def test_evaluate_facts_eligible(self):
        """Facts 满足所有条件 → eligible=True。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.FACTS)
        await repo.save(node)

        feedback.set_task_ids(node.id, {uuid4() for _ in range(6)})
        feedback.set_positive_rate(node.id, 0.90)
        feedback.set_project_ids(node.id, {uuid4(), uuid4(), uuid4()})

        evaluation = await svc.evaluate(node.id)

        assert evaluation.eligible
        assert evaluation.current_tier == Tier.FACTS
        assert evaluation.target_tier == Tier.PATTERNS

    @pytest.mark.asyncio
    async def test_evaluate_patterns_not_eligible_insufficient_depts(self):
        """Patterns 不满足条件: Department 数 < 3。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.PATTERNS, confidence_value=Decimal("0.900"))
        await repo.save(node)

        feedback.set_dept_ids(node.id, {uuid4(), uuid4()})  # 只有 2 个

        evaluation = await svc.evaluate(node.id)

        assert not evaluation.eligible

    @pytest.mark.asyncio
    async def test_evaluate_patterns_not_eligible_low_confidence(self):
        """Patterns 不满足条件: 置信度 < 0.85。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.PATTERNS, confidence_value=Decimal("0.700"))
        await repo.save(node)

        feedback.set_dept_ids(node.id, {uuid4() for _ in range(3)})

        evaluation = await svc.evaluate(node.id)

        assert not evaluation.eligible

    @pytest.mark.asyncio
    async def test_evaluate_patterns_eligible(self):
        """Patterns 满足所有条件 → eligible=True。"""
        svc, repo, feedback = self._make_service()
        # 置信度在 60 天前设置为 0.900
        old_time = datetime.now(timezone.utc) - timedelta(days=60)
        node = _make_node(
            tier=Tier.PATTERNS,
            confidence_value=Decimal("0.900"),
            last_updated=old_time,
        )
        await repo.save(node)

        feedback.set_dept_ids(node.id, {uuid4() for _ in range(4)})

        evaluation = await svc.evaluate(node.id)

        assert evaluation.eligible
        assert evaluation.current_tier == Tier.PATTERNS
        assert evaluation.target_tier == Tier.PRINCIPLES

    @pytest.mark.asyncio
    async def test_evaluate_principles_not_promotable(self):
        """Principles 是最高层级，不可晋升。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.PRINCIPLES)
        await repo.save(node)

        evaluation = await svc.evaluate(node.id)

        assert not evaluation.eligible
        assert "highest" in evaluation.reasons[0].lower()

    @pytest.mark.asyncio
    async def test_evaluate_nonexistent_memory(self):
        """不存在的 Memory → not eligible。"""
        svc, repo, feedback = self._make_service()

        evaluation = await svc.evaluate(new_id())

        assert not evaluation.eligible
        assert "not found" in evaluation.reasons[0].lower()

    @pytest.mark.asyncio
    async def test_evaluate_non_active_lifecycle(self):
        """非 active 状态不参与晋升。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.FACTS, lifecycle=LifecycleState.CANDIDATE)
        await repo.save(node)

        evaluation = await svc.evaluate(node.id)

        assert not evaluation.eligible

    @pytest.mark.asyncio
    async def test_approve_promotion_facts_to_patterns(self):
        """审核通过: Facts → Patterns 晋升。"""
        svc, repo, feedback = self._make_service()
        publisher = MockEventPublisher()
        from aiteamos_knowledge.application.promotion import MemoryTierPromotionService

        svc = MemoryTierPromotionService(
            memory_repo=repo,
            feedback_store=feedback,
            tx_manager=MockTransactionManager(),
            event_publisher=publisher,
        )

        node = _make_node(tier=Tier.FACTS)
        await repo.save(node)

        approved_by = new_id()
        result = await svc.approve_promotion(node.id, approved_by=approved_by)

        assert result.tier == Tier.PATTERNS
        # 版本记录追加
        assert len(result.versions) == 1
        assert result.versions[0].reason == "tier_promotion"
        assert result.current_version == 2

        # 事件发布
        assert len(publisher.published) == 1
        events, _ = publisher.published[0]
        tier_promoted_events = [
            e for e in events
            if hasattr(e, "event_type") and "tier_promoted" in e.event_type
        ]
        assert len(tier_promoted_events) == 1
        assert tier_promoted_events[0].old_tier == "facts"
        assert tier_promoted_events[0].new_tier == "patterns"

    @pytest.mark.asyncio
    async def test_approve_promotion_patterns_to_principles(self):
        """审核通过: Patterns → Principles 晋升。"""
        from aiteamos_knowledge.application.promotion import MemoryTierPromotionService

        repo = InMemoryMemoryRepo()
        feedback = InMemoryFeedbackStore()
        publisher = MockEventPublisher()
        svc = MemoryTierPromotionService(
            memory_repo=repo,
            feedback_store=feedback,
            tx_manager=MockTransactionManager(),
            event_publisher=publisher,
        )

        node = _make_node(tier=Tier.PATTERNS)
        await repo.save(node)

        result = await svc.approve_promotion(node.id, approved_by=new_id())

        assert result.tier == Tier.PRINCIPLES

    @pytest.mark.asyncio
    async def test_approve_promotion_principles_raises(self):
        """Principles 晋升 → ValueError。"""
        svc, repo, feedback = self._make_service()
        node = _make_node(tier=Tier.PRINCIPLES)
        await repo.save(node)

        with pytest.raises(ValueError, match="highest tier"):
            await svc.approve_promotion(node.id, approved_by=new_id())

    @pytest.mark.asyncio
    async def test_approve_promotion_nonexistent_raises(self):
        """不存在的 Memory → ValueError。"""
        svc, repo, feedback = self._make_service()

        with pytest.raises(ValueError, match="not found"):
            await svc.approve_promotion(new_id(), approved_by=new_id())

    @pytest.mark.asyncio
    async def test_request_promotion_publishes_event(self):
        """发起晋升申请 → 发布事件。"""
        from aiteamos_knowledge.application.promotion import MemoryTierPromotionService

        repo = InMemoryMemoryRepo()
        feedback = InMemoryFeedbackStore()
        publisher = MockEventPublisher()
        svc = MemoryTierPromotionService(
            memory_repo=repo,
            feedback_store=feedback,
            tx_manager=MockTransactionManager(),
            event_publisher=publisher,
        )

        node = _make_node(tier=Tier.FACTS)
        await repo.save(node)

        # 设置满足条件
        feedback.set_task_ids(node.id, {uuid4() for _ in range(6)})
        feedback.set_positive_rate(node.id, 0.90)
        feedback.set_project_ids(node.id, {uuid4(), uuid4()})

        evaluation = await svc.request_promotion(
            node.id, requested_by=new_id(), reason="Test promotion"
        )

        assert evaluation.eligible
        assert len(publisher.published) == 1
        events, _ = publisher.published[0]
        assert any("promotion_requested" in e.event_type for e in events)


# ===========================================================================
# 5. MemorySpreadService 测试
# ===========================================================================


class TestMemorySpreadService:
    """测试 Memory 高价值自动扩散。"""

    @pytest.mark.asyncio
    async def test_spread_eligible(self):
        """连续 N 次首次 Pass → 生成扩散推荐。"""
        from aiteamos_knowledge.application.promotion import (
            MemorySpreadService,
            SPREAD_CONSECUTIVE_PASSES,
        )

        repo = InMemoryMemoryRepo()
        feedback = InMemoryFeedbackStore()
        svc = MemorySpreadService(memory_repo=repo, feedback_store=feedback)

        node = _make_node()
        await repo.save(node)
        feedback.set_consecutive_passes(node.id, SPREAD_CONSECUTIVE_PASSES + 1)

        rec = await svc.check_spread_eligibility(node.id)

        assert rec is not None
        assert rec.memory_id == node.id
        assert rec.consecutive_passes == SPREAD_CONSECUTIVE_PASSES + 1

    @pytest.mark.asyncio
    async def test_spread_not_eligible(self):
        """连续 Pass 次数不足 → 无推荐。"""
        from aiteamos_knowledge.application.promotion import MemorySpreadService

        repo = InMemoryMemoryRepo()
        feedback = InMemoryFeedbackStore()
        svc = MemorySpreadService(memory_repo=repo, feedback_store=feedback)

        node = _make_node()
        await repo.save(node)
        feedback.set_consecutive_passes(node.id, 1)

        rec = await svc.check_spread_eligibility(node.id)

        assert rec is None

    @pytest.mark.asyncio
    async def test_spread_nonexistent_memory(self):
        """不存在的 Memory → 无推荐。"""
        from aiteamos_knowledge.application.promotion import MemorySpreadService

        repo = InMemoryMemoryRepo()
        feedback = InMemoryFeedbackStore()
        svc = MemorySpreadService(memory_repo=repo, feedback_store=feedback)

        rec = await svc.check_spread_eligibility(new_id())
        assert rec is None

    @pytest.mark.asyncio
    async def test_find_spread_candidates_batch(self):
        """批量检查扩散候选。"""
        from aiteamos_knowledge.application.promotion import (
            MemorySpreadService,
            SPREAD_CONSECUTIVE_PASSES,
        )

        repo = InMemoryMemoryRepo()
        feedback = InMemoryFeedbackStore()
        svc = MemorySpreadService(memory_repo=repo, feedback_store=feedback)

        # 创建 3 个节点，2 个满足条件
        nodes = [_make_node() for _ in range(3)]
        for n in nodes:
            await repo.save(n)

        feedback.set_consecutive_passes(nodes[0].id, SPREAD_CONSECUTIVE_PASSES + 2)
        feedback.set_consecutive_passes(nodes[1].id, 1)  # 不满足
        feedback.set_consecutive_passes(nodes[2].id, SPREAD_CONSECUTIVE_PASSES)

        recs = await svc.find_spread_candidates([n.id for n in nodes])

        assert len(recs) == 2


# ===========================================================================
# 6. ReflectionEngine 测试
# ===========================================================================


class TestReflectionEngine:
    """测试 Memory 自动提取引擎。"""

    def _make_engine(self):
        from aiteamos_knowledge.application.extraction import ReflectionEngine

        repo = InMemoryMemoryRepo()
        publisher = MockEventPublisher()
        return (
            ReflectionEngine(
                memory_repo=repo,
                tx_manager=MockTransactionManager(),
                event_publisher=publisher,
            ),
            repo,
            publisher,
        )

    @pytest.mark.asyncio
    async def test_system_meta_skipped(self):
        """system_meta 事件不进入提取。"""
        from aiteamos_knowledge.application.extraction import ExtractionInput

        engine, repo, publisher = self._make_engine()

        input_data = ExtractionInput(
            task_id=TaskId("TASK-20260101T120000000-ABCD"),
            run_id=new_id(),
            member_id=new_id(),
            department_id=new_id(),
            run_trace={"system_meta": True},
        )

        result = await engine.extract_from_run(input_data)

        assert result == []
        assert len(repo._store) == 0

    @pytest.mark.asyncio
    async def test_parse_response_valid_json(self):
        """正确解析 JSON 响应。"""
        from aiteamos_knowledge.application.extraction import ReflectionEngine

        response = """[
            {
                "title": "Test Memory",
                "statement": "Test statement",
                "tier": "facts",
                "tags": ["test"]
            }
        ]"""

        candidates = ReflectionEngine._parse_response(response)

        assert len(candidates) == 1
        assert candidates[0].title == "Test Memory"
        assert candidates[0].tier == "facts"

    @pytest.mark.asyncio
    async def test_parse_response_markdown_code_block(self):
        """处理 markdown 代码块包裹的 JSON。"""
        from aiteamos_knowledge.application.extraction import ReflectionEngine

        response = """```json
[{"title": "Test", "statement": "stmt"}]
```"""

        candidates = ReflectionEngine._parse_response(response)

        assert len(candidates) == 1
        assert candidates[0].title == "Test"

    @pytest.mark.asyncio
    async def test_parse_response_invalid_json(self):
        """无效 JSON → 返回空列表。"""
        from aiteamos_knowledge.application.extraction import ReflectionEngine

        candidates = ReflectionEngine._parse_response("not valid json at all")
        assert candidates == []

    @pytest.mark.asyncio
    async def test_parse_response_empty_array(self):
        """空数组 → 返回空列表。"""
        from aiteamos_knowledge.application.extraction import ReflectionEngine

        candidates = ReflectionEngine._parse_response("[]")
        assert candidates == []

    @pytest.mark.asyncio
    async def test_parse_response_missing_required_fields(self):
        """缺少必要字段 → 跳过该条目。"""
        from aiteamos_knowledge.application.extraction import ReflectionEngine

        response = """[
            {"title": "Has title"},
            {"statement": "No title"},
            {"title": "Valid", "statement": "Valid statement"}
        ]"""

        candidates = ReflectionEngine._parse_response(response)

        # 只有最后一条有 title + statement
        assert len(candidates) == 1
        assert candidates[0].title == "Valid"

    @pytest.mark.asyncio
    async def test_build_candidate_node(self):
        """正确构建 Memory 候选节点。"""
        from aiteamos_knowledge.application.extraction import (
            ExtractionInput,
            MemoryCandidate,
            ReflectionEngine,
        )

        input_data = ExtractionInput(
            task_id=TaskId("TASK-20260101T120000000-ABCD"),
            run_id=new_id(),
            member_id=new_id(),
            department_id=new_id(),
            project_ids=[new_id()],
        )

        candidate = MemoryCandidate(
            title="Test",
            statement="Test statement",
            tier="patterns",
            tags=["test"],
        )

        node = ReflectionEngine._build_candidate_node(
            candidate=candidate,
            input_data=input_data,
            source_kind=SourceKind.TASK_EXECUTION,
            initial_confidence=Decimal("0.500"),
        )

        assert node.tier == Tier.PATTERNS
        assert node.lifecycle == LifecycleState.CANDIDATE
        assert node.content.statement == "Test statement"
        assert node.provenance.source_kind == SourceKind.TASK_EXECUTION
        assert node.confidence.value == Decimal("0.500")

    @pytest.mark.asyncio
    async def test_build_candidate_node_invalid_tier_defaults_to_facts(self):
        """无效 tier → 默认为 facts。"""
        from aiteamos_knowledge.application.extraction import (
            ExtractionInput,
            MemoryCandidate,
            ReflectionEngine,
        )

        input_data = ExtractionInput(
            task_id=TaskId("TASK-20260101T120000000-ABCD"),
            run_id=new_id(),
            member_id=new_id(),
            department_id=new_id(),
        )

        candidate = MemoryCandidate(
            title="Test",
            statement="Test",
            tier="invalid_tier",
        )

        node = ReflectionEngine._build_candidate_node(
            candidate=candidate,
            input_data=input_data,
            source_kind=SourceKind.TASK_EXECUTION,
            initial_confidence=Decimal("0.500"),
        )

        assert node.tier == Tier.FACTS


# ===========================================================================
# 7. MemoryReviewQueue 测试
# ===========================================================================


class TestMemoryReviewQueue:
    """测试 Memory 候选审核队列。"""

    def _make_queue(self):
        from aiteamos_knowledge.application.extraction import MemoryReviewQueue

        repo = InMemoryMemoryRepo()
        return (
            MemoryReviewQueue(
                memory_repo=repo,
                tx_manager=MockTransactionManager(),
                event_publisher=MockEventPublisher(),
            ),
            repo,
        )

    @pytest.mark.asyncio
    async def test_approve_candidate(self):
        """批准: candidate → active。"""
        queue, repo = self._make_queue()
        node = _make_node(lifecycle=LifecycleState.CANDIDATE)
        await repo.save(node)

        result = await queue.approve(node.id)

        assert result.lifecycle == LifecycleState.ACTIVE

    @pytest.mark.asyncio
    async def test_approve_non_candidate_raises(self):
        """非 candidate 状态 → ValueError。"""
        queue, repo = self._make_queue()
        node = _make_node(lifecycle=LifecycleState.ACTIVE)
        await repo.save(node)

        with pytest.raises(ValueError, match="not a candidate"):
            await queue.approve(node.id)

    @pytest.mark.asyncio
    async def test_reject_candidate(self):
        """拒绝: candidate → deprecated。"""
        queue, repo = self._make_queue()
        node = _make_node(lifecycle=LifecycleState.CANDIDATE)
        await repo.save(node)

        result = await queue.reject(node.id)

        assert result.lifecycle == LifecycleState.DEPRECATED

    @pytest.mark.asyncio
    async def test_reject_non_candidate_raises(self):
        """拒绝非 candidate → ValueError。"""
        queue, repo = self._make_queue()
        node = _make_node(lifecycle=LifecycleState.ACTIVE)
        await repo.save(node)

        with pytest.raises(ValueError, match="not a candidate"):
            await queue.reject(node.id)

    @pytest.mark.asyncio
    async def test_approve_nonexistent_raises(self):
        """批准不存在的 Memory → ValueError。"""
        queue, repo = self._make_queue()

        with pytest.raises(ValueError, match="not found"):
            await queue.approve(new_id())
