"""
Governance Context — 测试 (plan.md §3.3)。

验证标准:
- ReviewCase 完整生命周期 (创建 → 决策)
- 已决策 case 不可重复决策
- Memory Review: approve/reject/merge
- Task Review: 审核轮次上限
- ConflictCase 检测与解决
- 冲突隔离: 未解决前标记冲突中
- DDL migration 文件存在
"""

import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from aiteamos_governance.domain.models import (
    ConflictCase,
    ConflictKind,
    DetectorKind,
    ResolutionKind,
    ReviewCase,
    ReviewTargetKind,
    Verdict,
)
from aiteamos_governance.domain.events import (
    ConflictDetected,
    ConflictResolved,
    ReviewCaseCreated,
    ReviewDecisionMade,
)
from aiteamos_governance.application.services import (
    ConflictService,
    ReviewService,
    MAX_REVIEW_ROUNDS,
)
from aiteamos_shared.types import new_id


# ---------------------------------------------------------------------------
# Mock Infrastructure
# ---------------------------------------------------------------------------


class MockTransactionManager:
    def __init__(self):
        self.tx = MagicMock()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        yield self.tx


class MockEventPublisher:
    def __init__(self):
        self.published: list[tuple[list, str]] = []

    async def publish_events(self, events: list, *, partition_key: str, tx: Any) -> None:
        self.published.append((events, partition_key))


class InMemoryReviewRepo:
    def __init__(self):
        self._store: dict[UUID, ReviewCase] = {}

    async def save(self, aggregate: ReviewCase, *, tx: Any = None) -> None:
        self._store[aggregate.id] = aggregate

    async def get_by_id(self, review_id: UUID, *, tx: Any = None) -> ReviewCase | None:
        return self._store.get(review_id)

    async def find_pending(self, *, tx: Any = None) -> list[ReviewCase]:
        return [c for c in self._store.values() if not c.is_decided]

    async def find_by_target(
        self, target_kind: str, target_id: UUID, *, tx: Any = None
    ) -> list[ReviewCase]:
        return [
            c for c in self._store.values()
            if c.target_kind.value == target_kind and c.target_id == target_id
        ]

    async def count_by_target(
        self, target_kind: str, target_id: UUID, *, tx: Any = None
    ) -> int:
        return len(await self.find_by_target(target_kind, target_id))


class InMemoryConflictRepo:
    def __init__(self):
        self._store: dict[UUID, ConflictCase] = {}

    async def save(self, aggregate: ConflictCase, *, tx: Any = None) -> None:
        self._store[aggregate.id] = aggregate

    async def get_by_id(self, conflict_id: UUID, *, tx: Any = None) -> ConflictCase | None:
        return self._store.get(conflict_id)

    async def find_unresolved(self, *, tx: Any = None) -> list[ConflictCase]:
        return [c for c in self._store.values() if not c.is_resolved]

    async def find_by_memory(self, memory_id, *, tx: Any = None) -> list[ConflictCase]:
        return [
            c for c in self._store.values()
            if c.memory_a_id == memory_id or c.memory_b_id == memory_id
        ]


# ===========================================================================
# 1. ReviewCase 聚合根测试
# ===========================================================================


class TestReviewCase:
    def test_create_review_case(self):
        case = ReviewCase(
            target_kind=ReviewTargetKind.TASK_DELIVERABLE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )
        assert not case.is_decided
        assert case.verdict is None
        # Creation event emitted in __init__
        assert len(case.pending_events) == 1
        assert isinstance(case.pending_events[0], ReviewCaseCreated)

    def test_decide_approve(self):
        case = ReviewCase(
            target_kind=ReviewTargetKind.MEMORY_CANDIDATE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )
        case.decide(verdict=Verdict.APPROVE, reason="Looks good")

        assert case.is_decided
        assert case.verdict == Verdict.APPROVE
        assert case.decision_at is not None
        # 2 events: creation (from __init__) + decision
        assert len(case.pending_events) == 2
        assert isinstance(case.pending_events[0], ReviewCaseCreated)
        assert isinstance(case.pending_events[1], ReviewDecisionMade)

    def test_decide_reject(self):
        case = ReviewCase(
            target_kind=ReviewTargetKind.TASK_DELIVERABLE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )
        case.decide(
            verdict=Verdict.REJECT,
            reason="Insufficient test coverage",
            correction="Add more edge case tests",
        )
        assert case.verdict == Verdict.REJECT
        assert case.correction is not None

    def test_decide_already_decided_raises(self):
        case = ReviewCase(
            target_kind=ReviewTargetKind.MEMORY_CANDIDATE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )
        case.decide(verdict=Verdict.APPROVE)

        with pytest.raises(ValueError, match="already decided"):
            case.decide(verdict=Verdict.REJECT)

    def test_decide_merge(self):
        case = ReviewCase(
            target_kind=ReviewTargetKind.MEMORY_CANDIDATE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )
        case.decide(verdict=Verdict.MERGE, reason="Duplicate of existing memory")
        assert case.verdict == Verdict.MERGE

    def test_decide_revise(self):
        case = ReviewCase(
            target_kind=ReviewTargetKind.TASK_DELIVERABLE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )
        case.decide(verdict=Verdict.REVISE, correction="Fix naming convention")
        assert case.verdict == Verdict.REVISE


# ===========================================================================
# 2. ConflictCase 聚合根测试
# ===========================================================================


class TestConflictCase:
    def test_create_conflict(self):
        case = ConflictCase(
            memory_a_id=new_id(),
            memory_b_id=new_id(),
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.AUTO_ADMISSION,
        )
        assert not case.is_resolved
        assert case.resolution is None
        # Creation event emitted in __init__
        assert len(case.pending_events) == 1
        assert isinstance(case.pending_events[0], ConflictDetected)

    def test_resolve_keep_a(self):
        case = ConflictCase(
            memory_a_id=new_id(),
            memory_b_id=new_id(),
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.PERIODIC_SCAN,
        )
        resolved_by = new_id()
        case.resolve(
            resolution=ResolutionKind.KEEP_A,
            winner_id=case.memory_a_id,
            resolved_by=resolved_by,
        )
        assert case.is_resolved
        assert case.resolution == ResolutionKind.KEEP_A
        assert case.winner_id == case.memory_a_id
        # 2 events: detection (from __init__) + resolution
        assert len(case.pending_events) == 2
        assert isinstance(case.pending_events[0], ConflictDetected)
        assert isinstance(case.pending_events[1], ConflictResolved)

    def test_resolve_already_resolved_raises(self):
        case = ConflictCase(
            memory_a_id=new_id(),
            memory_b_id=new_id(),
            conflict_kind=ConflictKind.SCOPE,
            detected_by=DetectorKind.MANUAL,
        )
        case.resolve(resolution=ResolutionKind.KEEP_B, resolved_by=new_id())

        with pytest.raises(ValueError, match="already resolved"):
            case.resolve(resolution=ResolutionKind.MERGE, resolved_by=new_id())

    def test_resolve_deprecate_both(self):
        case = ConflictCase(
            memory_a_id=new_id(),
            memory_b_id=new_id(),
            conflict_kind=ConflictKind.TEMPORAL,
            detected_by=DetectorKind.RECALL_COLLISION,
        )
        case.resolve(resolution=ResolutionKind.DEPRECATE_BOTH, resolved_by=new_id())
        assert case.resolution == ResolutionKind.DEPRECATE_BOTH
        assert case.winner_id is None


# ===========================================================================
# 3. ReviewService 测试
# ===========================================================================


class TestReviewService:
    def _make_service(self):
        repo = InMemoryReviewRepo()
        publisher = MockEventPublisher()
        return (
            ReviewService(
                review_repo=repo,
                tx_manager=MockTransactionManager(),
                event_publisher=publisher,
            ),
            repo,
            publisher,
        )

    @pytest.mark.asyncio
    async def test_create_review(self):
        svc, repo, publisher = self._make_service()
        target_id = uuid4()

        case = await svc.create_review(
            target_kind=ReviewTargetKind.TASK_DELIVERABLE,
            target_id=target_id,
            reviewer_member_id=new_id(),
        )

        assert case.id is not None
        assert not case.is_decided
        assert len(repo._store) == 1
        assert len(publisher.published) == 1

    @pytest.mark.asyncio
    async def test_decide_review(self):
        svc, repo, publisher = self._make_service()
        case = await svc.create_review(
            target_kind=ReviewTargetKind.MEMORY_CANDIDATE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )

        decided = await svc.decide(
            case.id, verdict=Verdict.APPROVE, reason="Good quality"
        )

        assert decided.is_decided
        assert decided.verdict == Verdict.APPROVE
        # 2 次 publish: create + decide
        assert len(publisher.published) == 2

    @pytest.mark.asyncio
    async def test_decide_nonexistent_raises(self):
        svc, _, _ = self._make_service()
        with pytest.raises(ValueError, match="not found"):
            await svc.decide(uuid4(), verdict=Verdict.APPROVE)

    @pytest.mark.asyncio
    async def test_check_review_limit(self):
        svc, repo, _ = self._make_service()
        target_id = uuid4()

        # 创建 MAX_REVIEW_ROUNDS 个审核
        for _ in range(MAX_REVIEW_ROUNDS):
            await svc.create_review(
                target_kind=ReviewTargetKind.TASK_DELIVERABLE,
                target_id=target_id,
                reviewer_member_id=new_id(),
            )

        exceeded = await svc.check_review_limit(
            ReviewTargetKind.TASK_DELIVERABLE, target_id
        )
        assert exceeded is True

    @pytest.mark.asyncio
    async def test_check_review_limit_not_exceeded(self):
        svc, _, _ = self._make_service()
        exceeded = await svc.check_review_limit(
            ReviewTargetKind.TASK_DELIVERABLE, uuid4()
        )
        assert exceeded is False

    @pytest.mark.asyncio
    async def test_get_pending(self):
        svc, _, _ = self._make_service()
        await svc.create_review(
            target_kind=ReviewTargetKind.MEMORY_CANDIDATE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )
        case2 = await svc.create_review(
            target_kind=ReviewTargetKind.TASK_DELIVERABLE,
            target_id=uuid4(),
            reviewer_member_id=new_id(),
        )
        await svc.decide(case2.id, verdict=Verdict.APPROVE)

        pending = await svc.get_pending()
        assert len(pending) == 1


# ===========================================================================
# 4. ConflictService 测试
# ===========================================================================


class TestConflictService:
    def _make_service(self):
        repo = InMemoryConflictRepo()
        publisher = MockEventPublisher()
        return (
            ConflictService(
                conflict_repo=repo,
                tx_manager=MockTransactionManager(),
                event_publisher=publisher,
            ),
            repo,
            publisher,
        )

    @pytest.mark.asyncio
    async def test_report_conflict(self):
        svc, repo, publisher = self._make_service()
        mem_a, mem_b = new_id(), new_id()

        case = await svc.report_conflict(
            memory_a_id=mem_a,
            memory_b_id=mem_b,
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.AUTO_ADMISSION,
        )

        assert case.memory_a_id == mem_a
        assert case.memory_b_id == mem_b
        assert not case.is_resolved
        assert len(repo._store) == 1
        assert len(publisher.published) == 1

    @pytest.mark.asyncio
    async def test_report_conflict_idempotent(self):
        svc, repo, _ = self._make_service()
        mem_a, mem_b = new_id(), new_id()

        case1 = await svc.report_conflict(
            memory_a_id=mem_a, memory_b_id=mem_b,
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.AUTO_ADMISSION,
        )
        case2 = await svc.report_conflict(
            memory_a_id=mem_a, memory_b_id=mem_b,
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.AUTO_ADMISSION,
        )

        assert case1.id == case2.id
        assert len(repo._store) == 1

    @pytest.mark.asyncio
    async def test_resolve_conflict(self):
        svc, repo, publisher = self._make_service()
        mem_a, mem_b = new_id(), new_id()
        case = await svc.report_conflict(
            memory_a_id=mem_a, memory_b_id=mem_b,
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.PERIODIC_SCAN,
        )

        resolved = await svc.resolve_conflict(
            case.id,
            resolution=ResolutionKind.KEEP_A,
            winner_id=mem_a,
            resolved_by=new_id(),
        )

        assert resolved.is_resolved
        assert resolved.resolution == ResolutionKind.KEEP_A

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_raises(self):
        svc, _, _ = self._make_service()
        with pytest.raises(ValueError, match="not found"):
            await svc.resolve_conflict(
                uuid4(), resolution=ResolutionKind.KEEP_A, resolved_by=new_id()
            )

    @pytest.mark.asyncio
    async def test_is_memory_in_conflict(self):
        svc, _, _ = self._make_service()
        mem_a = new_id()
        await svc.report_conflict(
            memory_a_id=mem_a, memory_b_id=new_id(),
            conflict_kind=ConflictKind.SCOPE,
            detected_by=DetectorKind.MANUAL,
        )

        assert await svc.is_memory_in_conflict(mem_a) is True
        assert await svc.is_memory_in_conflict(new_id()) is False

    @pytest.mark.asyncio
    async def test_is_memory_not_in_conflict_after_resolve(self):
        svc, _, _ = self._make_service()
        mem_a = new_id()
        case = await svc.report_conflict(
            memory_a_id=mem_a, memory_b_id=new_id(),
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.RECALL_COLLISION,
        )
        await svc.resolve_conflict(
            case.id, resolution=ResolutionKind.MERGE, resolved_by=new_id()
        )

        assert await svc.is_memory_in_conflict(mem_a) is False

    @pytest.mark.asyncio
    async def test_get_unresolved(self):
        svc, _, _ = self._make_service()
        case1 = await svc.report_conflict(
            memory_a_id=new_id(), memory_b_id=new_id(),
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.AUTO_ADMISSION,
        )
        case2 = await svc.report_conflict(
            memory_a_id=new_id(), memory_b_id=new_id(),
            conflict_kind=ConflictKind.SCOPE,
            detected_by=DetectorKind.PERIODIC_SCAN,
        )
        await svc.resolve_conflict(
            case1.id, resolution=ResolutionKind.KEEP_A, resolved_by=new_id()
        )

        unresolved = await svc.get_unresolved()
        assert len(unresolved) == 1
        assert unresolved[0].id == case2.id


# ===========================================================================
# 5. Domain Events 测试
# ===========================================================================


class TestGovernanceEvents:
    def test_review_case_created(self):
        evt = ReviewCaseCreated(
            event_type="governance.review_case.created",
            review_case_id=uuid4(),
            target_kind="task_deliverable",
            target_id=uuid4(),
            reviewer_member_id=uuid4(),
        )
        assert evt.event_type == "governance.review_case.created"

    def test_review_decision_made(self):
        evt = ReviewDecisionMade(
            event_type="governance.review_case.decision_made",
            review_case_id=uuid4(),
            target_kind="memory_candidate",
            target_id=uuid4(),
            verdict="approve",
            reason="Good quality",
        )
        assert evt.verdict == "approve"

    def test_conflict_detected(self):
        evt = ConflictDetected(
            event_type="governance.conflict_case.detected",
            conflict_case_id=uuid4(),
            memory_a_id=uuid4(),
            memory_b_id=uuid4(),
            conflict_kind="semantic",
            detected_by="auto_admission",
        )
        assert evt.conflict_kind == "semantic"

    def test_conflict_resolved(self):
        evt = ConflictResolved(
            event_type="governance.conflict_case.resolved",
            conflict_case_id=uuid4(),
            memory_a_id=uuid4(),
            memory_b_id=uuid4(),
            resolution="keep_a",
            winner_id=uuid4(),
        )
        assert evt.resolution == "keep_a"


# ===========================================================================
# 6. Migration 存在性检查
# ===========================================================================


class TestMigrationExists:
    def test_migration_007_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), "..", "migrations", "007_governance_context.sql"
        )
        assert os.path.exists(path)
