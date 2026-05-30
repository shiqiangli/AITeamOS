"""
Knowledge Context — 领域模型 + 不变量测试。

验证标准 (plan.md §1.2):
- 不变量违反时抛出明确异常
- 版本追加正确记录 diff 和 reason
- Edge 独立 CRUD 不触发 Node 锁
- MemoryNode 聚合边界不含 MemoryEdge
"""

import pytest
from decimal import Decimal
from uuid import uuid4, UUID

from aiteamos_shared.types import new_id
from aiteamos_knowledge.domain.models import (
    Confidence,
    ConfidenceState,
    LifecycleState,
    MemoryContent,
    MemoryEdge,
    MemoryNode,
    MemoryVersion,
    Provenance,
    RelationType,
    Scope,
    ScopeKind,
    SourceKind,
    Tier,
)
from aiteamos_knowledge.domain.invariants import (
    InvariantViolationError,
    assert_edge_not_in_node_aggregate,
    assert_edge_operation_no_node_lock,
    assert_recallable,
    compute_decay_factor,
    is_decay_eligible,
    is_recallable,
    validate_confidence_value,
)
from aiteamos_knowledge.domain.events import (
    MemoryNodeCreated,
    MemoryNodeUpdated,
    MemoryNodeLifecycleChanged,
    MemoryEdgeAdded,
    MemoryVersionAppended,
    MemoryQuarantinedEvent,
    MemoryFeedbackRecorded,
)
from aiteamos_knowledge.domain.services import (
    ConfidenceAdjustmentService,
    MemoryConflictDetector,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_node(
    *,
    tier: Tier = Tier.PATTERNS,
    lifecycle: LifecycleState = LifecycleState.ACTIVE,
    confidence_value: Decimal = Decimal("0.500"),
    tags: list[str] | None = None,
    title: str = "Test Memory",
) -> MemoryNode:
    return MemoryNode(
        tier=tier,
        scope=Scope(kind=ScopeKind.GLOBAL),
        title=title,
        content=MemoryContent(
            statement="Test statement",
            tags=tags or ["test"],
        ),
        confidence=Confidence(value=confidence_value),
        provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
        lifecycle=lifecycle,
    )


def _make_edge(
    *,
    source_id: UUID | None = None,
    target_id: UUID | None = None,
) -> MemoryEdge:
    return MemoryEdge(
        source_id=source_id or new_id(),
        target_id=target_id or new_id(),
        relation_type=RelationType.CAUSAL,
        created_by=new_id(),
    )


# ===========================================================================
# Test Confidence Value Object
# ===========================================================================


class TestConfidence:
    def test_valid_range(self):
        c = Confidence(value=Decimal("0.5"))
        assert c.value == Decimal("0.5")

    def test_zero_valid(self):
        c = Confidence(value=Decimal("0"))
        assert c.value == Decimal("0")

    def test_one_valid(self):
        c = Confidence(value=Decimal("1"))
        assert c.value == Decimal("1")

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="Confidence value"):
            Confidence(value=Decimal("1.5"))

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="Confidence value"):
            Confidence(value=Decimal("-0.1"))

    def test_with_value_returns_new_instance(self):
        c = Confidence(value=Decimal("0.5"))
        c2 = c.with_value(Decimal("0.8"))
        assert c.value == Decimal("0.5")  # immutable
        assert c2.value == Decimal("0.8")

    def test_with_value_state_change(self):
        c = Confidence(value=Decimal("0.5"))
        c2 = c.with_value(Decimal("0.3"), state=ConfidenceState.NEEDS_VERIFY)
        assert c2.state == ConfidenceState.NEEDS_VERIFY


# ===========================================================================
# Test MemoryContent Value Object
# ===========================================================================


class TestMemoryContent:
    def test_to_dict_roundtrip(self):
        content = MemoryContent(
            statement="test",
            applicable_when="always",
            counter_example="never",
            tags=["a", "b"],
        )
        d = content.to_dict()
        restored = MemoryContent.from_dict(d)
        assert restored.statement == content.statement
        assert restored.tags == content.tags

    def test_from_dict_defaults(self):
        content = MemoryContent.from_dict({})
        assert content.statement == ""
        assert content.tags == []


# ===========================================================================
# Test Invariants (I-K-1 ~ I-K-5)
# ===========================================================================


class TestInvariantIK1:
    """I-K-1: confidence.value ∈ [0, 1]"""

    def test_valid_confidence(self):
        validate_confidence_value(Decimal("0.5"))

    def test_boundary_zero(self):
        validate_confidence_value(Decimal("0"))

    def test_boundary_one(self):
        validate_confidence_value(Decimal("1"))

    def test_above_one_raises(self):
        with pytest.raises(InvariantViolationError, match="I-K-1"):
            validate_confidence_value(Decimal("1.001"))

    def test_below_zero_raises(self):
        with pytest.raises(InvariantViolationError, match="I-K-1"):
            validate_confidence_value(Decimal("-0.001"))


class TestInvariantIK2:
    """I-K-2: tier=Facts 不参与时间衰减"""

    def test_facts_not_decay_eligible(self):
        node = _make_node(tier=Tier.FACTS)
        assert is_decay_eligible(node) is False

    def test_patterns_decay_eligible(self):
        node = _make_node(tier=Tier.PATTERNS)
        assert is_decay_eligible(node) is True

    def test_principles_decay_eligible(self):
        node = _make_node(tier=Tier.PRINCIPLES)
        assert is_decay_eligible(node) is True


class TestInvariantIK3:
    """I-K-3: quarantined 时召回屏蔽"""

    def test_active_is_recallable(self):
        node = _make_node(lifecycle=LifecycleState.ACTIVE)
        assert is_recallable(node) is True

    def test_quarantined_not_recallable(self):
        node = _make_node(lifecycle=LifecycleState.QUARANTINED)
        assert is_recallable(node) is False

    def test_assert_recallable_passes(self):
        node = _make_node(lifecycle=LifecycleState.ACTIVE)
        assert_recallable(node)  # no exception

    def test_assert_recallable_fails(self):
        node = _make_node(lifecycle=LifecycleState.QUARANTINED)
        with pytest.raises(InvariantViolationError, match="I-K-3"):
            assert_recallable(node)


class TestInvariantIK4:
    """I-K-4: MemoryEdge 独立聚合"""

    def test_edge_is_independent(self):
        edge = _make_edge()
        assert_edge_not_in_node_aggregate(edge)  # no exception

    def test_edge_with_node_ref_raises(self):
        edge = _make_edge()
        edge._node_aggregate = "bad"  # type: ignore
        with pytest.raises(InvariantViolationError, match="I-K-4"):
            assert_edge_not_in_node_aggregate(edge)


class TestInvariantIK5:
    """I-K-5: Edge CRUD 不锁定 Node"""

    def test_no_lock_passes(self):
        src = new_id()
        tgt = new_id()
        assert_edge_operation_no_node_lock(src, tgt, locked_ids=set())

    def test_locked_source_raises(self):
        src = new_id()
        tgt = new_id()
        with pytest.raises(InvariantViolationError, match="I-K-5"):
            assert_edge_operation_no_node_lock(src, tgt, locked_ids={src})

    def test_locked_target_raises(self):
        src = new_id()
        tgt = new_id()
        with pytest.raises(InvariantViolationError, match="I-K-5"):
            assert_edge_operation_no_node_lock(src, tgt, locked_ids={tgt})

    def test_none_locked_ids_passes(self):
        src = new_id()
        tgt = new_id()
        assert_edge_operation_no_node_lock(src, tgt, locked_ids=None)


# ===========================================================================
# Test MemoryNode Aggregate
# ===========================================================================


class TestMemoryNode:
    def test_creation(self):
        node = _make_node()
        assert node.id is not None
        assert node.tier == Tier.PATTERNS
        assert node.lifecycle == LifecycleState.ACTIVE
        assert node.current_version == 1

    def test_update_content_creates_version(self):
        node = _make_node()
        member_id = new_id()
        new_content = MemoryContent(statement="Updated", tags=["updated"])

        version = node.update_content(
            new_content, reason="Test update", author_member_id=member_id
        )

        assert node.current_version == 2
        assert version.version_no == 2
        assert version.reason == "Test update"
        assert version.diff["statement_before"] == "Test statement"
        assert version.diff["statement_after"] == "Updated"
        assert len(node.versions) == 1

    def test_update_content_emits_events(self):
        node = _make_node()
        node.update_content(
            MemoryContent(statement="New"),
            reason="test",
            author_member_id=new_id(),
        )
        events = node.pending_events
        assert any(isinstance(e, MemoryNodeUpdated) for e in events)
        assert any(isinstance(e, MemoryVersionAppended) for e in events)

    def test_append_version(self):
        node = _make_node()
        member_id = new_id()
        version = node.append_version(
            diff={"key": "value"},
            reason="Metadata update",
            author_member_id=member_id,
        )
        assert version.version_no == 2
        assert node.current_version == 2
        assert len(node.versions) == 1

    def test_change_lifecycle(self):
        node = _make_node()
        node.change_lifecycle(LifecycleState.STALE)
        assert node.lifecycle == LifecycleState.STALE

        events = node.pending_events
        assert any(isinstance(e, MemoryNodeLifecycleChanged) for e in events)

    def test_change_lifecycle_to_quarantined_emits_event(self):
        node = _make_node()
        node.change_lifecycle(LifecycleState.QUARANTINED)
        events = node.pending_events
        assert any(isinstance(e, MemoryQuarantinedEvent) for e in events)

    def test_deprecate(self):
        node = _make_node()
        node.deprecate()
        assert node.lifecycle == LifecycleState.DEPRECATED
        assert node.confidence.state == ConfidenceState.DEPRECATED

    def test_adjust_confidence(self):
        node = _make_node()
        node.adjust_confidence(Decimal("0.8"))
        assert node.confidence.value == Decimal("0.8")

    def test_mark_used(self):
        node = _make_node()
        assert node.last_used_at is None
        node.mark_used()
        assert node.last_used_at is not None

    def test_is_recallable(self):
        node = _make_node(lifecycle=LifecycleState.ACTIVE)
        assert node.is_recallable() is True

        node.change_lifecycle(LifecycleState.QUARANTINED)
        assert node.is_recallable() is False

    def test_clear_pending_events(self):
        node = _make_node()
        node.change_lifecycle(LifecycleState.STALE)
        assert len(node.pending_events) > 0
        node.clear_pending_events()
        assert len(node.pending_events) == 0


# ===========================================================================
# Test MemoryEdge Aggregate
# ===========================================================================


class TestMemoryEdge:
    def test_creation(self):
        src = new_id()
        tgt = new_id()
        edge = MemoryEdge(
            source_id=src,
            target_id=tgt,
            relation_type=RelationType.DEPENDS,
            created_by=new_id(),
        )
        assert edge.source_id == src
        assert edge.target_id == tgt
        assert edge.relation_type == RelationType.DEPENDS
        assert edge.weight == Decimal("1.000")

    def test_independent_aggregate(self):
        edge = _make_edge()
        assert not hasattr(edge, "_node_aggregate")
        assert_edge_not_in_node_aggregate(edge)


# ===========================================================================
# Test Decay Factor
# ===========================================================================


class TestDecayFactor:
    def test_facts_no_decay(self):
        factor = compute_decay_factor("facts", 365.0)
        assert factor == Decimal("1")

    def test_patterns_decay(self):
        factor = compute_decay_factor("patterns", 180.0)
        # Half-life: exp(-1/180 * 180) = exp(-1) ≈ 0.368
        assert Decimal("0.3") < factor < Decimal("0.4")

    def test_principles_decay(self):
        factor = compute_decay_factor("principles", 365.0)
        # Half-life: exp(-1/365 * 365) = exp(-1) ≈ 0.368
        assert Decimal("0.3") < factor < Decimal("0.4")

    def test_zero_days_no_decay(self):
        factor = compute_decay_factor("patterns", 0.0)
        assert factor == Decimal("1")


# ===========================================================================
# Test Domain Events
# ===========================================================================


class TestDomainEvents:
    def test_memory_node_created(self):
        evt = MemoryNodeCreated(
            memory_id=new_id(),
            tier="patterns",
            title="Test",
            provenance_source_kind="manual_input",
        )
        assert evt.event_type == "knowledge.memory_node.created"

    def test_memory_edge_added(self):
        evt = MemoryEdgeAdded(
            edge_id=new_id(),
            source_id=new_id(),
            target_id=new_id(),
            relation_type="causal",
        )
        assert evt.event_type == "knowledge.memory_edge.added"

    def test_extra_fields_ignored(self):
        """VersionedDomainEvent extra='ignore' forward compatibility."""
        evt = MemoryNodeCreated(
            memory_id=new_id(),
            tier="patterns",
            title="Test",
            provenance_source_kind="manual_input",
            unknown_future_field="ignored",  # type: ignore
        )
        assert evt.event_type == "knowledge.memory_node.created"


# ===========================================================================
# Test ConfidenceAdjustmentService
# ===========================================================================


class TestConfidenceAdjustmentService:
    @pytest.fixture
    def mock_repo(self):
        from unittest.mock import AsyncMock

        repo = AsyncMock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return ConfidenceAdjustmentService(repository=mock_repo)

    @pytest.mark.asyncio
    async def test_system_meta_skipped(self, service, mock_repo):
        """元递归隔离: system_meta 反馈不参与置信度。"""
        evt = MemoryFeedbackRecorded(
            memory_id=new_id(),
            task_run_id=new_id(),
            outcome="positive",
            delta=0.1,
            is_system_meta=True,
        )
        result = await service.on_feedback(evt)
        assert result is None
        mock_repo.lock_for_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_positive_feedback_increases(self, service, mock_repo):
        """正反馈提升置信度。"""
        node = _make_node(confidence_value=Decimal("0.5"))
        mock_repo.lock_for_update.return_value = node

        evt = MemoryFeedbackRecorded(
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="positive",
            delta=0.1,
        )
        result = await service.on_feedback(evt)
        assert result is not None
        assert result.confidence.value > Decimal("0.5")

    @pytest.mark.asyncio
    async def test_negative_feedback_decreases(self, service, mock_repo):
        """负反馈降低置信度。"""
        node = _make_node(confidence_value=Decimal("0.5"))
        mock_repo.lock_for_update.return_value = node

        evt = MemoryFeedbackRecorded(
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="negative",
            delta=-0.1,
        )
        result = await service.on_feedback(evt)
        assert result is not None
        assert result.confidence.value < Decimal("0.5")

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_needs_verify(self, service, mock_repo):
        """置信度低于阈值触发 needs_verify。"""
        node = _make_node(confidence_value=Decimal("0.31"))
        mock_repo.lock_for_update.return_value = node

        evt = MemoryFeedbackRecorded(
            memory_id=node.id,
            task_run_id=new_id(),
            outcome="negative",
            delta=-0.1,
        )
        result = await service.on_feedback(evt)
        assert result is not None
        assert result.confidence.value < Decimal("0.3")
        assert result.lifecycle == LifecycleState.NEEDS_VERIFY

    @pytest.mark.asyncio
    async def test_decay_facts_skipped(self, service, mock_repo):
        """I-K-2: Facts 不参与衰减。"""
        node = _make_node(tier=Tier.FACTS, confidence_value=Decimal("0.8"))
        result = await service.apply_decay(node, days_elapsed=365.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_decay_patterns(self, service, mock_repo):
        """Patterns 参与衰减。"""
        node = _make_node(tier=Tier.PATTERNS, confidence_value=Decimal("0.8"))
        mock_repo.save.return_value = None
        result = await service.apply_decay(node, days_elapsed=180.0)
        assert result is not None
        assert result.confidence.value < Decimal("0.8")


# ===========================================================================
# Test MemoryConflictDetector
# ===========================================================================


class TestMemoryConflictDetector:
    @pytest.fixture
    def mock_repo(self):
        from unittest.mock import AsyncMock
        return AsyncMock()

    @pytest.fixture
    def detector(self, mock_repo):
        return MemoryConflictDetector(repository=mock_repo)

    @pytest.mark.asyncio
    async def test_no_candidates_no_conflicts(self, detector):
        node = _make_node()
        conflicts = await detector.detect_semantic_conflicts(node)
        assert conflicts == []

    @pytest.mark.asyncio
    async def test_high_tag_overlap_detected(self, detector):
        node_a = _make_node(tags=["python", "fastapi", "async", "ddd"])
        node_b = _make_node(tags=["python", "fastapi", "async", "ddd"])

        conflicts = await detector.detect_semantic_conflicts(
            node_a, candidates=[node_b], threshold=0.8
        )
        assert len(conflicts) == 1
        assert conflicts[0].conflict_kind == "semantic"

    @pytest.mark.asyncio
    async def test_low_tag_overlap_no_conflict(self, detector):
        node_a = _make_node(tags=["python"])
        node_b = _make_node(tags=["java", "spring"])

        conflicts = await detector.detect_semantic_conflicts(
            node_a, candidates=[node_b], threshold=0.8
        )
        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_scope_conflict_detected(self, detector):
        node_a = MemoryNode(
            tier=Tier.PATTERNS,
            scope=Scope(kind=ScopeKind.PROJECT, ref=new_id()),
            title="Coding Standard",
            content=MemoryContent(statement="Use type hints"),
            provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
        )
        node_b = MemoryNode(
            tier=Tier.PATTERNS,
            scope=Scope(kind=ScopeKind.DEPARTMENT, ref=new_id()),
            title="Coding Standard",
            content=MemoryContent(statement="No type hints needed"),
            provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
        )

        conflicts = await detector.detect_scope_conflicts(
            node_a, candidates=[node_b]
        )
        assert len(conflicts) == 1
        assert conflicts[0].conflict_kind == "scope"

    @pytest.mark.asyncio
    async def test_quarantined_candidate_skipped(self, detector):
        node_a = _make_node(tags=["python", "fastapi"])
        node_b = _make_node(
            tags=["python", "fastapi"],
            lifecycle=LifecycleState.QUARANTINED,
        )

        conflicts = await detector.detect_semantic_conflicts(
            node_a, candidates=[node_b], threshold=0.8
        )
        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_temporal_conflict_detected(self, detector):
        """Same title + same tier + contradictory lifecycle states → temporal conflict."""
        node_active = MemoryNode(
            tier=Tier.FACTS,
            scope=Scope(kind=ScopeKind.GLOBAL),
            title="Python version",
            content=MemoryContent(statement="Use Python 3.12"),
            provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
            lifecycle=LifecycleState.ACTIVE,
        )
        node_deprecated = MemoryNode(
            tier=Tier.FACTS,
            scope=Scope(kind=ScopeKind.PROJECT, ref=new_id()),
            title="Python version",
            content=MemoryContent(statement="Use Python 3.10"),
            provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
            lifecycle=LifecycleState.DEPRECATED,
        )

        conflicts = await detector.detect_temporal_conflicts(
            node_active, candidates=[node_deprecated]
        )
        assert len(conflicts) == 1
        assert conflicts[0].conflict_kind == "temporal"

    @pytest.mark.asyncio
    async def test_no_temporal_conflict_same_state(self, detector):
        """Same lifecycle state → no temporal conflict."""
        node_a = MemoryNode(
            tier=Tier.FACTS,
            scope=Scope(kind=ScopeKind.GLOBAL),
            title="Python version",
            content=MemoryContent(statement="Use Python 3.12"),
            provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
            lifecycle=LifecycleState.ACTIVE,
        )
        node_b = MemoryNode(
            tier=Tier.FACTS,
            scope=Scope(kind=ScopeKind.GLOBAL),
            title="Python version",
            content=MemoryContent(statement="Use Python 3.11"),
            provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
            lifecycle=LifecycleState.ACTIVE,
        )

        conflicts = await detector.detect_temporal_conflicts(
            node_a, candidates=[node_b]
        )
        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_no_temporal_conflict_different_title(self, detector):
        """Different title → no temporal conflict."""
        node_a = MemoryNode(
            tier=Tier.FACTS,
            scope=Scope(kind=ScopeKind.GLOBAL),
            title="Python version",
            content=MemoryContent(statement="Use Python 3.12"),
            provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
            lifecycle=LifecycleState.ACTIVE,
        )
        node_b = MemoryNode(
            tier=Tier.FACTS,
            scope=Scope(kind=ScopeKind.GLOBAL),
            title="Java version",
            content=MemoryContent(statement="Use Java 21"),
            provenance=Provenance(source_kind=SourceKind.MANUAL_INPUT),
            lifecycle=LifecycleState.DEPRECATED,
        )

        conflicts = await detector.detect_temporal_conflicts(
            node_a, candidates=[node_b]
        )
        assert len(conflicts) == 0
