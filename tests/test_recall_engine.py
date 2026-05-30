"""
Memory Recall Engine — 测试 (plan.md §2.2 验证标准)。

验证标准:
- 召回引擎在单通道超时时仍返回结果（降级测试）
- 排序公式正确（mock 数据验证分数计算）
- 6 阶段 pipeline 完整覆盖
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from aiteamos_knowledge.application.recall_engine import (
    MemoryRecallEngine,
    RecallBudget,
    RecallCandidate,
    RecallChannelOrchestrator,
    RecallResult,
    TaskContext,
)
from aiteamos_shared.types import MemoryId, new_id


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------


class MockAssignedFetcher:
    def __init__(self, result: set[MemoryId] | None = None, delay: float = 0):
        self._result = result or set()
        self._delay = delay

    async def fetch_assigned(self, member_id: UUID) -> set[MemoryId]:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result


class MockScopeFetcher:
    def __init__(self, result: set[MemoryId] | None = None, delay: float = 0):
        self._result = result or set()
        self._delay = delay

    async def fetch_by_scope(
        self, project_ids: list[UUID], dept_id: UUID | None
    ) -> set[MemoryId]:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result


class MockVectorFetcher:
    def __init__(self, result: set[MemoryId] | None = None, delay: float = 0):
        self._result = result or set()
        self._delay = delay

    async def fetch_vector_topk(
        self, embedding: list[float] | None, k: int
    ) -> set[MemoryId]:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result


class MockGraphFetcher:
    def __init__(self, result: set[MemoryId] | None = None, delay: float = 0):
        self._result = result or set()
        self._delay = delay

    async def fetch_graph_neighbors(
        self, seed_ids: set[MemoryId], depth: int
    ) -> set[MemoryId]:
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result


class MockDetailFetcher:
    def __init__(self, candidates: list[RecallCandidate] | None = None):
        self._candidates = {c.memory_id: c for c in (candidates or [])}

    async def fetch_details(self, memory_ids: set[MemoryId]) -> list[RecallCandidate]:
        return [self._candidates[mid] for mid in memory_ids if mid in self._candidates]


class MockAuditLogger:
    def __init__(self):
        self.logged: list[tuple[Any, Any, list[RecallCandidate]]] = []

    async def log_recall(
        self,
        snapshot_id: UUID | None,
        run_id: UUID | None,
        candidates: list[RecallCandidate],
    ) -> None:
        self.logged.append((snapshot_id, run_id, candidates))


class MockConflictChecker:
    def __init__(self, conflicts: set[MemoryId] | None = None):
        self._conflicts = conflicts or set()

    async def get_unresolved_conflicts(
        self, memory_ids: set[MemoryId]
    ) -> set[MemoryId]:
        return self._conflicts & memory_ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(
    *,
    title: str = "test",
    lifecycle: str = "active",
    confidence: float = 0.8,
    tokens: int = 100,
    assigned_weight: float = 0.0,
    cos_distance: float = 0.5,
    scope_match: float = 0.5,
    freshness: float = 0.5,
) -> RecallCandidate:
    return RecallCandidate(
        memory_id=new_id(),
        title=title,
        statement=f"Statement for {title}",
        lifecycle_state=lifecycle,
        confidence=confidence,
        tokens=tokens,
        assigned_weight=assigned_weight,
        cos_distance=cos_distance,
        scope_match=scope_match,
        freshness=freshness,
    )


def _make_ctx(**kwargs: Any) -> TaskContext:
    defaults = {
        "task_id": "TASK-20260101T000000000-AAAA",
        "member_id": uuid4(),
        "project_ids": [],
    }
    defaults.update(kwargs)
    return TaskContext(**defaults)


# ===========================================================================
# §1: RecallChannelOrchestrator — 通道降级
# ===========================================================================


class TestChannelOrchestrator:
    """验证单通道超时/异常时降级而非失败。"""

    @pytest.mark.asyncio
    async def test_all_channels_succeed(self):
        m1, m2, m3, m4 = new_id(), new_id(), new_id(), new_id()
        orch = RecallChannelOrchestrator(
            assigned_fetcher=MockAssignedFetcher({m1}),
            scope_fetcher=MockScopeFetcher({m2}),
            vector_fetcher=MockVectorFetcher({m3}),
            graph_fetcher=MockGraphFetcher({m4}),
        )
        ctx = _make_ctx()
        candidates, degraded = await orch.fetch_all_channels(ctx)
        assert m1 in candidates
        assert m2 in candidates
        assert m3 in candidates
        assert m4 in candidates
        assert degraded == []

    @pytest.mark.asyncio
    async def test_single_channel_timeout_degrades(self):
        """Graph channel with 1s delay should timeout (500ms limit)."""
        m1 = new_id()
        orch = RecallChannelOrchestrator(
            assigned_fetcher=MockAssignedFetcher({m1}),
            scope_fetcher=MockScopeFetcher(set()),
            vector_fetcher=MockVectorFetcher(set()),
            graph_fetcher=MockGraphFetcher(set(), delay=1.0),  # > 500ms timeout
        )
        ctx = _make_ctx()
        candidates, degraded = await orch.fetch_all_channels(ctx)
        assert m1 in candidates
        assert "graph" in degraded

    @pytest.mark.asyncio
    async def test_all_channels_degraded_returns_empty(self):
        """All channels timeout → empty set, all degraded."""
        orch = RecallChannelOrchestrator(
            assigned_fetcher=MockAssignedFetcher(set(), delay=2.0),
            scope_fetcher=MockScopeFetcher(set(), delay=2.0),
            vector_fetcher=MockVectorFetcher(set(), delay=2.0),
            graph_fetcher=MockGraphFetcher(set(), delay=2.0),
        )
        ctx = _make_ctx()
        candidates, degraded = await orch.fetch_all_channels(ctx)
        assert len(candidates) == 0
        assert len(degraded) == 4

    @pytest.mark.asyncio
    async def test_channel_exception_degrades(self):
        """Channel that raises exception should degrade."""

        class FailingFetcher:
            async def fetch_assigned(self, member_id):
                raise RuntimeError("DB connection lost")

        orch = RecallChannelOrchestrator(
            assigned_fetcher=FailingFetcher(),
            scope_fetcher=MockScopeFetcher(set()),
            vector_fetcher=MockVectorFetcher(set()),
            graph_fetcher=MockGraphFetcher(set()),
        )
        ctx = _make_ctx()
        candidates, degraded = await orch.fetch_all_channels(ctx)
        assert "assigned" in degraded


# ===========================================================================
# §2: MemoryRecallEngine — 6 阶段 Pipeline
# ===========================================================================


class TestRecallEngine:
    """验证 6 阶段 pipeline。"""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """Complete pipeline with mock data."""
        c1 = _make_candidate(title="high", confidence=0.9, tokens=50)
        c2 = _make_candidate(title="low", confidence=0.3, tokens=50)

        m1, m2 = c1.memory_id, c2.memory_id

        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher({m1, m2}),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([c1, c2]),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker(),
        )

        result = await engine.recall(_make_ctx(), RecallBudget(max_recall_tokens=500))
        assert len(result.memories) == 2
        assert result.total_tokens == 100
        # Higher confidence should rank first
        assert result.memories[0].confidence >= result.memories[1].confidence

    @pytest.mark.asyncio
    async def test_filter_blocks_quarantined(self):
        """Quarantined/deprecated/archived Memory filtered out."""
        c_active = _make_candidate(lifecycle="active")
        c_quar = _make_candidate(lifecycle="quarantined")
        c_dep = _make_candidate(lifecycle="deprecated")
        c_arch = _make_candidate(lifecycle="archived")

        all_ids = {c.memory_id for c in [c_active, c_quar, c_dep, c_arch]}

        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher(all_ids),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([c_active, c_quar, c_dep, c_arch]),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker(),
        )

        result = await engine.recall(_make_ctx(), RecallBudget())
        assert len(result.memories) == 1
        assert result.memories[0].memory_id == c_active.memory_id

    @pytest.mark.asyncio
    async def test_conflict_masking(self):
        """Memory with unresolved conflicts should be filtered."""
        c1 = _make_candidate()
        c2 = _make_candidate()

        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher({c1.memory_id, c2.memory_id}),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([c1, c2]),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker({c1.memory_id}),  # c1 has conflict
        )

        result = await engine.recall(_make_ctx(), RecallBudget())
        assert len(result.memories) == 1
        assert result.memories[0].memory_id == c2.memory_id

    @pytest.mark.asyncio
    async def test_budget_truncation(self):
        """Token budget trimming."""
        candidates = [
            _make_candidate(title=f"c{i}", tokens=300) for i in range(10)
        ]
        all_ids = {c.memory_id for c in candidates}

        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher(all_ids),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher(candidates),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker(),
        )

        result = await engine.recall(
            _make_ctx(), RecallBudget(max_recall_tokens=800)
        )
        # 800 / 300 = 2 full items (600 tokens), 3rd would exceed
        assert len(result.memories) <= 3
        assert result.total_tokens <= 800

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        """No candidates from any channel → empty result."""
        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher(set()),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([]),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker(),
        )

        result = await engine.recall(_make_ctx(), RecallBudget())
        assert result.memories == []
        assert result.total_tokens == 0

    @pytest.mark.asyncio
    async def test_audit_log_written(self):
        """Stage 6: audit log should be called."""
        c = _make_candidate()
        audit = MockAuditLogger()

        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher({c.memory_id}),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([c]),
            audit_logger=audit,
            conflict_checker=MockConflictChecker(),
        )

        ctx = _make_ctx(snapshot_id=uuid4(), run_id=uuid4())
        await engine.recall(ctx, RecallBudget())
        assert len(audit.logged) == 1


# ===========================================================================
# §3: 排序公式验证
# ===========================================================================


class TestRankingFormula:
    """验证排序公式正确性。"""

    def test_ranking_weights_sum_to_one(self):
        total = (
            MemoryRecallEngine.W_ASSIGNED
            + MemoryRecallEngine.W_CONFIDENCE
            + MemoryRecallEngine.W_SIMILARITY
            + MemoryRecallEngine.W_SCOPE
            + MemoryRecallEngine.W_FRESHNESS
        )
        assert abs(total - 1.0) < 1e-9

    def test_ranking_assigned_beats_unassigned(self):
        """Higher assigned_weight → higher score (all else equal)."""
        c_high = _make_candidate(assigned_weight=1.0, confidence=0.5)
        c_low = _make_candidate(assigned_weight=0.0, confidence=0.5)

        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher(set()),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([]),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker(),
        )

        engine._rank([c_high, c_low], _make_ctx())
        assert c_high.score > c_low.score

    def test_ranking_higher_confidence_wins(self):
        """Higher confidence → higher score (all else equal)."""
        c_high = _make_candidate(confidence=0.95, assigned_weight=0.5)
        c_low = _make_candidate(confidence=0.2, assigned_weight=0.5)

        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher(set()),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([]),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker(),
        )

        engine._rank([c_high, c_low], _make_ctx())
        assert c_high.score > c_low.score

    def test_ranking_lower_cos_distance_wins(self):
        """Lower cos_distance (= higher similarity) → higher score."""
        c_close = _make_candidate(cos_distance=0.1)  # very similar
        c_far = _make_candidate(cos_distance=0.9)  # dissimilar

        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher(set()),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set()),
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([]),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker(),
        )

        engine._rank([c_close, c_far], _make_ctx())
        assert c_close.score > c_far.score

    def test_min_max_normalization(self):
        """Min-max normalization: min → 0, max → 1."""
        candidates = [
            _make_candidate(confidence=0.2),
            _make_candidate(confidence=0.5),
            _make_candidate(confidence=0.8),
        ]
        MemoryRecallEngine._normalize_field(candidates, "confidence")
        assert abs(candidates[0].confidence - 0.0) < 1e-9
        assert abs(candidates[1].confidence - 0.5) < 1e-9
        assert abs(candidates[2].confidence - 1.0) < 1e-9

    def test_normalization_all_same(self):
        """When all values are the same, normalize to 0.5."""
        candidates = [
            _make_candidate(confidence=0.5),
            _make_candidate(confidence=0.5),
        ]
        MemoryRecallEngine._normalize_field(candidates, "confidence")
        assert candidates[0].confidence == 0.5
        assert candidates[1].confidence == 0.5

    @pytest.mark.asyncio
    async def test_degraded_channels_in_result(self):
        """Degraded channels reported in result."""
        c = _make_candidate()
        engine = MemoryRecallEngine(
            channel_orchestrator=RecallChannelOrchestrator(
                assigned_fetcher=MockAssignedFetcher({c.memory_id}),
                scope_fetcher=MockScopeFetcher(set()),
                vector_fetcher=MockVectorFetcher(set(), delay=2.0),  # will timeout
                graph_fetcher=MockGraphFetcher(set()),
            ),
            detail_fetcher=MockDetailFetcher([c]),
            audit_logger=MockAuditLogger(),
            conflict_checker=MockConflictChecker(),
        )
        result = await engine.recall(_make_ctx(), RecallBudget())
        assert "vector" in result.degraded_channels
