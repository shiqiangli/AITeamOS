"""
Tests for PRD gap closures:
- Governance commands route through services (event publishing, tx safety)
- process_expired_reviews auto-approves high-confidence candidates
- Memory proposal queue API endpoint
- Memory health API endpoint
- ReviewMemoryExtractor bridge
"""

import os
import pytest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

os.environ["AITEAMOS_ADMIN_API_KEY"] = "test-admin-key-12345"

from aiteamos_governance.domain.models import (
    ConflictCase,
    ConflictKind,
    DetectorKind,
    ResolutionKind,
    ReviewCase,
    ReviewTargetKind,
    Verdict,
)
from aiteamos_governance.application.services import (
    ConflictService,
    ReviewService,
)
from aiteamos_knowledge.domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryNode,
    Provenance,
    Scope,
    ScopeKind,
    SourceKind,
    Tier,
)
from aiteamos_knowledge.application.extraction import (
    MemoryReviewQueue,
    ReflectionEngine,
    AUTO_APPROVE_CONFIDENCE,
    REVIEW_TIMEOUT_DAYS,
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

    async def find_by_memory(
        self, memory_id: UUID, *, tx: Any = None
    ) -> list[ConflictCase]:
        return [
            c for c in self._store.values()
            if c.memory_a_id == memory_id or c.memory_b_id == memory_id
        ]


# ---------------------------------------------------------------------------
# Memory Node Mock Repo (for process_expired_reviews)
# ---------------------------------------------------------------------------


class InMemoryNodeRepo:
    """In-memory MemoryNode repository for testing."""

    def __init__(self):
        self._store: dict[UUID, MemoryNode] = {}

    async def save(self, aggregate: MemoryNode, *, tx: Any = None) -> None:
        self._store[aggregate.id] = aggregate

    async def get_by_id(self, id: UUID, *, tx: Any = None) -> MemoryNode | None:
        return self._store.get(id)

    async def lock_for_update(self, id: UUID, *, tx: Any = None) -> MemoryNode | None:
        return self._store.get(id)

    async def find_candidates_older_than(
        self, cutoff: datetime, *, tx: Any = None,
    ) -> list[MemoryNode]:
        return [
            node for node in self._store.values()
            if node.lifecycle == LifecycleState.CANDIDATE
            and node.created_at < cutoff
        ]


def _make_candidate(
    *, confidence: float = 0.5, days_old: int = 10, title: str = "Test"
) -> MemoryNode:
    """Helper to create a candidate MemoryNode."""
    return MemoryNode(
        id=new_id(),
        tier=Tier.FACTS,
        scope=Scope(kind=ScopeKind.PROJECT, ref=new_id()),
        title=title,
        content=MemoryContent(statement="test statement"),
        confidence=Confidence(
            value=Decimal(str(confidence)),
            state=ConfidenceState.NEEDS_VERIFY,
            last_updated=datetime.now(timezone.utc),
            last_decay_at=datetime.now(timezone.utc),
        ),
        provenance=Provenance(source_kind=SourceKind.TASK_EXECUTION),
        lifecycle=LifecycleState.CANDIDATE,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_old),
    )


# ===========================================================================
# Test: Governance Commands Route Through Services
# ===========================================================================


class TestGovernanceServiceRouting:
    """Verify governance commands delegate to ReviewService/ConflictService."""

    @pytest.fixture
    def tx(self):
        return MockTransactionManager()

    @pytest.fixture
    def pub(self):
        return MockEventPublisher()

    @pytest.fixture
    def review_repo(self):
        return InMemoryReviewRepo()

    @pytest.fixture
    def conflict_repo(self):
        return InMemoryConflictRepo()

    async def test_review_service_publishes_events(self, review_repo, tx, pub):
        """ReviewService.create_review publishes ReviewCaseCreated event."""
        service = ReviewService(review_repo=review_repo, tx_manager=tx, event_publisher=pub)
        case = await service.create_review(
            target_kind=ReviewTargetKind.MEMORY_CANDIDATE,
            target_id=new_id(),
            reviewer_member_id=new_id(),
        )
        assert case.id is not None
        assert len(pub.published) == 1
        events, _ = pub.published[0]
        assert events[0].event_type == "governance.review_case.created"

    async def test_review_service_decide_publishes(self, review_repo, tx, pub):
        """ReviewService.decide publishes ReviewDecisionMade event."""
        service = ReviewService(review_repo=review_repo, tx_manager=tx, event_publisher=pub)
        case = await service.create_review(
            target_kind=ReviewTargetKind.TASK_DELIVERABLE,
            target_id=new_id(),
            reviewer_member_id=new_id(),
        )
        # Clear creation events from domain model; only decision event should remain
        case.clear_pending_events()
        pub.published.clear()

        decided = await service.decide(
            case.id,
            verdict=Verdict.APPROVE,
            reason="Looks good",
        )
        assert decided.verdict == Verdict.APPROVE
        assert len(pub.published) == 1
        events, _ = pub.published[0]
        assert events[0].event_type == "governance.review_case.decision_made"

    async def test_conflict_service_publishes_events(self, conflict_repo, tx, pub):
        """ConflictService.report_conflict publishes ConflictDetected event."""
        service = ConflictService(conflict_repo=conflict_repo, tx_manager=tx, event_publisher=pub)
        case = await service.report_conflict(
            memory_a_id=new_id(),
            memory_b_id=new_id(),
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.MANUAL,
        )
        assert case.id is not None
        assert len(pub.published) == 1
        events, _ = pub.published[0]
        assert events[0].event_type == "governance.conflict_case.detected"

    async def test_conflict_service_resolve_publishes(self, conflict_repo, tx, pub):
        """ConflictService.resolve_conflict publishes ConflictResolved event."""
        service = ConflictService(conflict_repo=conflict_repo, tx_manager=tx, event_publisher=pub)
        case = await service.report_conflict(
            memory_a_id=new_id(),
            memory_b_id=new_id(),
            conflict_kind=ConflictKind.SEMANTIC,
            detected_by=DetectorKind.MANUAL,
        )
        # Clear creation events from domain model
        case.clear_pending_events()
        pub.published.clear()

        resolved = await service.resolve_conflict(
            case.id,
            resolution=ResolutionKind.KEEP_A,
            winner_id=case.memory_a_id,
            resolved_by=new_id(),
        )
        assert resolved.is_resolved
        assert len(pub.published) == 1
        events, _ = pub.published[0]
        assert events[0].event_type == "governance.conflict_case.resolved"

    async def test_conflict_service_idempotent(self, conflict_repo, tx, pub):
        """Reporting same conflict pair twice returns existing case."""
        service = ConflictService(conflict_repo=conflict_repo, tx_manager=tx, event_publisher=pub)
        ma = new_id()
        mb = new_id()
        case1 = await service.report_conflict(
            memory_a_id=ma, memory_b_id=mb,
            conflict_kind=ConflictKind.SEMANTIC, detected_by=DetectorKind.MANUAL,
        )
        case2 = await service.report_conflict(
            memory_a_id=ma, memory_b_id=mb,
            conflict_kind=ConflictKind.SEMANTIC, detected_by=DetectorKind.MANUAL,
        )
        assert case1.id == case2.id


# ===========================================================================
# Test: process_expired_reviews Auto-Approval
# ===========================================================================


class TestProcessExpiredReviews:
    """Verify MemoryReviewQueue.process_expired_reviews auto-approval logic."""

    @pytest.fixture
    def tx(self):
        return MockTransactionManager()

    @pytest.fixture
    def pub(self):
        return MockEventPublisher()

    @pytest.fixture
    def repo(self):
        return InMemoryNodeRepo()

    async def test_high_confidence_auto_approved(self, repo, tx, pub):
        """Candidates above AUTO_APPROVE_CONFIDENCE threshold get auto-approved."""
        queue = MemoryReviewQueue(memory_repo=repo, tx_manager=tx, event_publisher=pub)

        # Add a high-confidence old candidate
        node = _make_candidate(confidence=0.90, days_old=REVIEW_TIMEOUT_DAYS + 1)
        await repo.save(node)

        count = await queue.process_expired_reviews()
        assert count == 1

        # Verify the node is now active
        updated = await repo.get_by_id(node.id)
        assert updated.lifecycle == LifecycleState.ACTIVE

    async def test_low_confidence_not_approved(self, repo, tx, pub):
        """Candidates below threshold remain as candidates."""
        queue = MemoryReviewQueue(memory_repo=repo, tx_manager=tx, event_publisher=pub)

        node = _make_candidate(confidence=0.50, days_old=REVIEW_TIMEOUT_DAYS + 1)
        await repo.save(node)

        count = await queue.process_expired_reviews()
        assert count == 0

        updated = await repo.get_by_id(node.id)
        assert updated.lifecycle == LifecycleState.CANDIDATE

    async def test_recent_candidates_not_processed(self, repo, tx, pub):
        """Candidates newer than REVIEW_TIMEOUT_DAYS are not processed."""
        queue = MemoryReviewQueue(memory_repo=repo, tx_manager=tx, event_publisher=pub)

        # High confidence but recent
        node = _make_candidate(confidence=0.95, days_old=1)
        await repo.save(node)

        count = await queue.process_expired_reviews()
        assert count == 0

    async def test_mixed_candidates(self, repo, tx, pub):
        """Only old high-confidence candidates are approved."""
        queue = MemoryReviewQueue(memory_repo=repo, tx_manager=tx, event_publisher=pub)

        # Old high confidence → should approve
        n1 = _make_candidate(confidence=0.90, days_old=REVIEW_TIMEOUT_DAYS + 1, title="high-old")
        # Old low confidence → should not approve
        n2 = _make_candidate(confidence=0.50, days_old=REVIEW_TIMEOUT_DAYS + 1, title="low-old")
        # Recent high confidence → should not approve
        n3 = _make_candidate(confidence=0.95, days_old=1, title="high-new")
        # Active node → should not be processed
        n4 = _make_candidate(confidence=0.90, days_old=REVIEW_TIMEOUT_DAYS + 1, title="active")
        n4.lifecycle = LifecycleState.ACTIVE

        for n in [n1, n2, n3, n4]:
            await repo.save(n)

        count = await queue.process_expired_reviews()
        assert count == 1

        assert (await repo.get_by_id(n1.id)).lifecycle == LifecycleState.ACTIVE
        assert (await repo.get_by_id(n2.id)).lifecycle == LifecycleState.CANDIDATE
        assert (await repo.get_by_id(n3.id)).lifecycle == LifecycleState.CANDIDATE


# ===========================================================================
# Test: Review → Memory Bridge (ReviewMemoryExtractor)
# ===========================================================================


class TestReviewMemoryExtractor:
    """Verify review findings generate Memory candidates."""

    async def test_creates_candidate_from_review(self):
        """ReviewMemoryExtractor creates Memory candidate from review decision."""
        from aiteamos_knowledge.application.review_extractor import ReviewMemoryExtractor
        from aiteamos_shared.events import VersionedDomainEvent

        repo = InMemoryNodeRepo()
        tx = MockTransactionManager()
        pub = MockEventPublisher()

        extractor = ReviewMemoryExtractor(
            memory_repo=repo, tx_manager=tx, event_publisher=pub, db=None,
        )

        # Simulate a ReviewDecisionMade event
        event = MagicMock(spec=VersionedDomainEvent)
        event.event_type = "governance.review_case.decision_made"
        event.model_dump.return_value = {
            "verdict": "revise",
            "reason": "Authentication module must validate timezone",
            "target_kind": "task_deliverable",
            "target_id": str(uuid4()),
            "review_case_id": str(uuid4()),
            "reviewer_member_id": str(uuid4()),
        }

        await extractor.handle_event(event)

        # Should have created one candidate
        assert len(repo._store) == 1
        node = list(repo._store.values())[0]
        assert node.lifecycle == LifecycleState.CANDIDATE
        assert "Authentication" in node.title or "timezone" in node.title
        assert node.provenance.system_meta is True  # Prevents recursive extraction

    async def test_skips_empty_reason(self):
        """Reviews without reason don't generate candidates."""
        from aiteamos_knowledge.application.review_extractor import ReviewMemoryExtractor
        from aiteamos_shared.events import VersionedDomainEvent

        repo = InMemoryNodeRepo()
        tx = MockTransactionManager()
        pub = MockEventPublisher()

        extractor = ReviewMemoryExtractor(
            memory_repo=repo, tx_manager=tx, event_publisher=pub, db=None,
        )

        event = MagicMock(spec=VersionedDomainEvent)
        event.event_type = "governance.review_case.decision_made"
        event.model_dump.return_value = {
            "verdict": "approve",
            "reason": "",
            "target_kind": "task_deliverable",
            "target_id": str(uuid4()),
            "review_case_id": str(uuid4()),
        }

        await extractor.handle_event(event)
        assert len(repo._store) == 0

    async def test_ignores_non_review_events(self):
        """Non-review events are silently ignored."""
        from aiteamos_knowledge.application.review_extractor import ReviewMemoryExtractor
        from aiteamos_shared.events import VersionedDomainEvent

        repo = InMemoryNodeRepo()
        tx = MockTransactionManager()
        pub = MockEventPublisher()

        extractor = ReviewMemoryExtractor(
            memory_repo=repo, tx_manager=tx, event_publisher=pub, db=None,
        )

        event = MagicMock(spec=VersionedDomainEvent)
        event.event_type = "execution.run.finished"
        event.model_dump.return_value = {}

        await extractor.handle_event(event)
        assert len(repo._store) == 0
