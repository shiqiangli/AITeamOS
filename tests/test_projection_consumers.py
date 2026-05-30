"""Tests for projection consumers and ProjectionRunner event routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from aiteamos_shared.events import VersionedDomainEvent


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeGraphStore:
    """Minimal graph store stub for testing."""

    merged_edges: list[tuple] = field(default_factory=list)
    removed_edges: list[tuple] = field(default_factory=list)

    async def merge_edge(self, source_id, target_id, relation_type, *, tx=None):
        self.merged_edges.append((source_id, target_id, relation_type))

    async def remove_edge(self, source_id, target_id, relation_type, *, tx=None):
        self.removed_edges.append((source_id, target_id, relation_type))


@dataclass
class FakeDB:
    """Minimal DB stub with watermark tracking."""

    watermark_seq: int = -1
    executed: list[str] = field(default_factory=list)

    async def fetchrow(self, query: str, *args) -> dict | None:
        if "projection_watermark" in query:
            if self.watermark_seq < 0:
                return None
            return {"last_seq": self.watermark_seq, "last_event_id": "", "processed_at": None}
        return None

    async def execute(self, query: str, *args) -> str:
        self.executed.append(query[:50])
        return ""

    async def fetch(self, query: str, *args) -> list:
        return []


def _make_event(event_type: str, seq: int = 1, **kwargs) -> VersionedDomainEvent:
    """Helper to create a test event."""
    return VersionedDomainEvent(
        event_type=event_type,
        global_seq=seq,
        **kwargs,
    )


def _make_edge_added_event(seq: int, source: UUID, target: UUID, rel: str):
    from aiteamos_knowledge.domain.events import MemoryEdgeAdded
    return MemoryEdgeAdded(
        event_type="knowledge.memory_edge.added",
        global_seq=seq,
        edge_id=uuid4(),
        source_id=source,
        target_id=target,
        relation_type=rel,
    )


def _make_edge_removed_event(seq: int, source: UUID, target: UUID, rel: str):
    from aiteamos_knowledge.domain.events import MemoryEdgeRemoved
    return MemoryEdgeRemoved(
        event_type="knowledge.memory_edge.removed",
        global_seq=seq,
        edge_id=uuid4(),
        source_id=source,
        target_id=target,
        relation_type=rel,
    )


def _make_lifecycle_event(seq: int, memory_id: UUID, old: str, new: str):
    from aiteamos_knowledge.domain.events import MemoryNodeLifecycleChanged
    return MemoryNodeLifecycleChanged(
        event_type="knowledge.memory_node.lifecycle_changed",
        global_seq=seq,
        memory_id=memory_id,
        old_state=old,
        new_state=new,
    )


# ---------------------------------------------------------------------------
# GraphEdgeProjectionConsumer tests
# ---------------------------------------------------------------------------


class TestGraphEdgeProjectionConsumer:
    async def test_edge_added_merges_to_graph(self):
        from aiteamos_knowledge.application.graph_projection_consumer import (
            GraphEdgeProjectionConsumer,
        )

        db = FakeDB()
        graph = FakeGraphStore()
        consumer = GraphEdgeProjectionConsumer(db=db, graph_store=graph)

        source = uuid4()
        target = uuid4()
        event = _make_edge_added_event(1, source, target, "depends")

        await consumer.consume(event)

        assert len(graph.merged_edges) == 1
        assert graph.merged_edges[0] == (source, target, "depends")

    async def test_edge_removed_from_graph(self):
        from aiteamos_knowledge.application.graph_projection_consumer import (
            GraphEdgeProjectionConsumer,
        )

        db = FakeDB()
        graph = FakeGraphStore()
        consumer = GraphEdgeProjectionConsumer(db=db, graph_store=graph)

        source = uuid4()
        target = uuid4()
        event = _make_edge_removed_event(1, source, target, "derived")

        await consumer.consume(event)

        assert len(graph.removed_edges) == 1
        assert graph.removed_edges[0] == (source, target, "derived")

    async def test_ignores_unrelated_events(self):
        from aiteamos_knowledge.application.graph_projection_consumer import (
            GraphEdgeProjectionConsumer,
        )

        db = FakeDB()
        graph = FakeGraphStore()
        consumer = GraphEdgeProjectionConsumer(db=db, graph_store=graph)

        event = _make_event("knowledge.memory_node.created", seq=1)
        await consumer.consume(event)

        assert len(graph.merged_edges) == 0
        assert len(graph.removed_edges) == 0

    async def test_idempotent_duplicate_skipped(self):
        from aiteamos_knowledge.application.graph_projection_consumer import (
            GraphEdgeProjectionConsumer,
        )

        db = FakeDB(watermark_seq=5)  # watermark ahead of event
        graph = FakeGraphStore()
        consumer = GraphEdgeProjectionConsumer(db=db, graph_store=graph)

        event = _make_edge_added_event(3, uuid4(), uuid4(), "depends")

        result = await consumer.consume(event)
        assert result is False  # duplicate skipped
        assert len(graph.merged_edges) == 0


# ---------------------------------------------------------------------------
# CascadeInvalidationConsumer tests
# ---------------------------------------------------------------------------


@dataclass
class FakeCascadeService:
    """Stub cascade service."""

    last_event: Any = None
    result_impacted: int = 0

    async def on_structural_change(self, evt):
        self.last_event = evt
        from aiteamos_knowledge.application.cascade_invalidation import CascadeResult
        return CascadeResult(impacted_count=self.result_impacted)


class TestCascadeInvalidationConsumer:
    async def test_triggers_on_needs_verify(self):
        from aiteamos_knowledge.application.cascade_consumer import (
            CascadeInvalidationConsumer,
        )

        db = FakeDB()
        service = FakeCascadeService()
        consumer = CascadeInvalidationConsumer(db=db, cascade_service=service)

        mid = uuid4()
        event = _make_lifecycle_event(1, mid, "active", "needs_verify")

        await consumer.consume(event)

        assert service.last_event is not None
        assert str(mid) in service.last_event.changed_anchors

    async def test_ignores_non_trigger_state(self):
        from aiteamos_knowledge.application.cascade_consumer import (
            CascadeInvalidationConsumer,
        )

        db = FakeDB()
        service = FakeCascadeService()
        consumer = CascadeInvalidationConsumer(db=db, cascade_service=service)

        event = _make_lifecycle_event(1, uuid4(), "candidate", "active")

        await consumer.consume(event)
        assert service.last_event is None

    async def test_ignores_unrelated_event_type(self):
        from aiteamos_knowledge.application.cascade_consumer import (
            CascadeInvalidationConsumer,
        )

        db = FakeDB()
        service = FakeCascadeService()
        consumer = CascadeInvalidationConsumer(db=db, cascade_service=service)

        event = _make_event("knowledge.memory_node.created", seq=1)
        await consumer.consume(event)

        assert service.last_event is None


# ---------------------------------------------------------------------------
# ProjectionRunner routing tests
# ---------------------------------------------------------------------------


@dataclass
class TrackingConsumer:
    """Consumer that tracks which events it receives."""

    from aiteamos_shared.projection import IdempotentProjectionConsumer

    consumer_id: str = "tracking-v1"
    events: list = field(default_factory=list)
    db: Any = None

    async def consume(self, event) -> bool:
        self.events.append(event)
        return True


class TestProjectionRunnerRouting:
    async def test_register_for_event_types_routes_correctly(self):
        from services.worker.aiteamos_worker.projection_runner import ProjectionRunner

        db = FakeDB()
        runner = ProjectionRunner(db=db)

        edge_consumer = TrackingConsumer(consumer_id="edge-v1")
        lifecycle_consumer = TrackingConsumer(consumer_id="lifecycle-v1")

        runner.register_for_event_types(
            edge_consumer,
            ["knowledge.memory_edge.added", "knowledge.memory_edge.removed"],
        )
        runner.register_for_event_types(
            lifecycle_consumer,
            ["knowledge.memory_node.lifecycle_changed"],
        )

        # Dispatch edge event
        edge_event = _make_event("knowledge.memory_edge.added", seq=1)
        await runner.dispatch(edge_event)

        assert len(edge_consumer.events) == 1
        assert len(lifecycle_consumer.events) == 0

        # Dispatch lifecycle event
        lc_event = _make_event(
            "knowledge.memory_node.lifecycle_changed", seq=2
        )
        await runner.dispatch(lc_event)

        assert len(edge_consumer.events) == 1
        assert len(lifecycle_consumer.events) == 1

    async def test_catch_all_consumer_receives_everything(self):
        from services.worker.aiteamos_worker.projection_runner import ProjectionRunner

        db = FakeDB()
        runner = ProjectionRunner(db=db)

        catch_all = TrackingConsumer(consumer_id="catch-all-v1")
        runner.register(catch_all)

        await runner.dispatch(_make_event("some.event", seq=1))
        await runner.dispatch(_make_event("another.event", seq=2))

        assert len(catch_all.events) == 2

    async def test_dispatch_does_not_duplicate_routed_and_catchall(self):
        from services.worker.aiteamos_worker.projection_runner import ProjectionRunner

        db = FakeDB()
        runner = ProjectionRunner(db=db)

        routed = TrackingConsumer(consumer_id="routed-v1")
        runner.register_for_event_types(routed, ["test.event"])

        event = _make_event("test.event", seq=1)
        await runner.dispatch(event)

        # routed consumer should get event exactly once
        assert len(routed.events) == 1


# ---------------------------------------------------------------------------
# TaskExecutionConsumer tests
# ---------------------------------------------------------------------------


@dataclass
class FakeExecDB:
    """DB stub that tracks execute calls."""

    watermark_seq: int = -1
    executed: list[tuple] = field(default_factory=list)

    async def fetchrow(self, query: str, *args) -> dict | None:
        if "projection_watermark" in query:
            if self.watermark_seq < 0:
                return None
            return {"last_seq": self.watermark_seq, "last_event_id": "", "processed_at": None}
        return None

    async def execute(self, query: str, *args) -> str:
        self.executed.append((query[:60], args))
        return ""

    async def fetch(self, query: str, *args) -> list:
        return []


def _business_sql(executed: list[tuple]) -> list[tuple]:
    """Filter out watermark CAS advances from executed SQL."""
    return [(q, a) for q, a in executed if "projection_watermark" not in q]


class TestTaskExecutionConsumer:
    async def test_task_created_inserts_row(self):
        from aiteamos_execution.application.task_execution_consumer import (
            TaskExecutionConsumer,
        )
        from aiteamos_execution.domain.events import TaskCreated

        db = FakeExecDB()
        consumer = TaskExecutionConsumer(db=db)

        event = TaskCreated(
            event_type="execution.task.created",
            global_seq=1,
            task_id="TASK-20260528T120000-0001",
            department_id=uuid4(),
            title="Test task",
            priority="P1",
        )
        result = await consumer.consume(event)

        assert result is True
        biz = _business_sql(db.executed)
        assert len(biz) >= 1
        assert "INSERT INTO task" in biz[0][0]

    async def test_state_changed_updates_task(self):
        from aiteamos_execution.application.task_execution_consumer import (
            TaskExecutionConsumer,
        )
        from aiteamos_execution.domain.events import TaskStateChanged

        db = FakeExecDB()
        consumer = TaskExecutionConsumer(db=db)

        event = TaskStateChanged(
            event_type="execution.task.state_changed",
            global_seq=1,
            task_id="TASK-20260528T120000-0001",
            from_state="draft",
            to_state="in_progress",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert len(biz) >= 1
        assert "UPDATE task SET state" in biz[0][0]

    async def test_run_started_inserts_run(self):
        from aiteamos_execution.application.task_execution_consumer import (
            TaskExecutionConsumer,
        )
        from aiteamos_execution.domain.events import RunStarted

        db = FakeExecDB()
        consumer = TaskExecutionConsumer(db=db)

        event = RunStarted(
            event_type="execution.run.started",
            global_seq=1,
            run_id=uuid4(),
            task_id="TASK-20260528T120000-0001",
            member_id=uuid4(),
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert len(biz) >= 1
        assert "INSERT INTO task_run" in biz[0][0]

    async def test_hard_circuit_marks_failed(self):
        from aiteamos_execution.application.task_execution_consumer import (
            TaskExecutionConsumer,
        )
        from aiteamos_execution.domain.events import TaskHardCircuitTriggered

        db = FakeExecDB()
        consumer = TaskExecutionConsumer(db=db)

        event = TaskHardCircuitTriggered(
            event_type="execution.task.hard_circuit_triggered",
            global_seq=1,
            task_id="TASK-20260528T120000-0001",
            reason="circuit_open",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert biz[0][1][-1] == "failed"

    async def test_idempotent_duplicate_skipped(self):
        from aiteamos_execution.application.task_execution_consumer import (
            TaskExecutionConsumer,
        )
        from aiteamos_execution.domain.events import TaskCreated

        db = FakeExecDB(watermark_seq=5)
        consumer = TaskExecutionConsumer(db=db)

        event = TaskCreated(
            event_type="execution.task.created",
            global_seq=3,
            task_id="TASK-20260528T120000-0001",
            department_id=uuid4(),
            title="dup",
            priority="P2",
        )
        result = await consumer.consume(event)
        assert result is False
        assert len(_business_sql(db.executed)) == 0


# ---------------------------------------------------------------------------
# ReviewGateConsumer tests
# ---------------------------------------------------------------------------


class TestReviewGateConsumer:
    async def test_review_created_inserts_row(self):
        from aiteamos_governance.application.review_gate_consumer import (
            ReviewGateConsumer,
        )
        from aiteamos_governance.domain.events import ReviewCaseCreated

        db = FakeExecDB()
        consumer = ReviewGateConsumer(db=db)

        event = ReviewCaseCreated(
            event_type="governance.review_case.created",
            global_seq=1,
            review_case_id=uuid4(),
            target_kind="task_deliverable",
            target_id=uuid4(),
            reviewer_member_id=uuid4(),
        )
        result = await consumer.consume(event)

        assert result is True
        biz = _business_sql(db.executed)
        assert "INSERT INTO review_case" in biz[0][0]

    async def test_review_decision_updates_verdict(self):
        from aiteamos_governance.application.review_gate_consumer import (
            ReviewGateConsumer,
        )
        from aiteamos_governance.domain.events import ReviewDecisionMade

        db = FakeExecDB()
        consumer = ReviewGateConsumer(db=db)

        event = ReviewDecisionMade(
            event_type="governance.review_case.decision_made",
            global_seq=1,
            review_case_id=uuid4(),
            target_kind="task_deliverable",
            target_id=uuid4(),
            verdict="approve",
            reason="looks good",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert "UPDATE review_case" in biz[0][0]

    async def test_conflict_detected_inserts(self):
        from aiteamos_governance.application.review_gate_consumer import (
            ReviewGateConsumer,
        )
        from aiteamos_governance.domain.events import ConflictDetected

        db = FakeExecDB()
        consumer = ReviewGateConsumer(db=db)

        event = ConflictDetected(
            event_type="governance.conflict_case.detected",
            global_seq=1,
            conflict_case_id=uuid4(),
            memory_a_id=uuid4(),
            memory_b_id=uuid4(),
            conflict_kind="semantic",
            detected_by="periodic_scan",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert "INSERT INTO conflict_case" in biz[0][0]

    async def test_conflict_resolved_updates(self):
        from aiteamos_governance.application.review_gate_consumer import (
            ReviewGateConsumer,
        )
        from aiteamos_governance.domain.events import ConflictResolved

        db = FakeExecDB()
        consumer = ReviewGateConsumer(db=db)

        event = ConflictResolved(
            event_type="governance.conflict_case.resolved",
            global_seq=1,
            conflict_case_id=uuid4(),
            memory_a_id=uuid4(),
            memory_b_id=uuid4(),
            resolution="keep_a",
            winner_id=uuid4(),
            resolved_by=uuid4(),
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert "UPDATE conflict_case" in biz[0][0]


# ---------------------------------------------------------------------------
# ReflectionConsumer tests
# ---------------------------------------------------------------------------


class TestReflectionConsumer:
    async def test_invocation_triggered_inserts(self):
        from aiteamos_validation.application.reflection_consumer import (
            ReflectionConsumer,
        )
        from aiteamos_validation.domain.events import HarnessInvocationTriggered

        db = FakeExecDB()
        consumer = ReflectionConsumer(db=db)

        event = HarnessInvocationTriggered(
            event_type="validation.harness_invocation.triggered",
            global_seq=1,
            invocation_id=uuid4(),
            adapter_id="pytest-adapter",
            run_id=uuid4(),
            tier="spec",
            callback_token="tok-123",
        )
        result = await consumer.consume(event)

        assert result is True
        biz = _business_sql(db.executed)
        assert "INSERT INTO harness_invocation" in biz[0][0]

    async def test_invocation_completed_updates_state(self):
        from aiteamos_validation.application.reflection_consumer import (
            ReflectionConsumer,
        )
        from aiteamos_validation.domain.events import HarnessInvocationCompleted

        db = FakeExecDB()
        consumer = ReflectionConsumer(db=db)

        event = HarnessInvocationCompleted(
            event_type="validation.harness_invocation.completed",
            global_seq=1,
            invocation_id=uuid4(),
            run_id=uuid4(),
            outcome="pass",
            callback_token="tok-123",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert "UPDATE harness_invocation" in biz[0][0]
        assert biz[0][1][1] == "done"

    async def test_flaky_outcome_sets_flaky_state(self):
        from aiteamos_validation.application.reflection_consumer import (
            ReflectionConsumer,
        )
        from aiteamos_validation.domain.events import HarnessInvocationCompleted

        db = FakeExecDB()
        consumer = ReflectionConsumer(db=db)

        event = HarnessInvocationCompleted(
            event_type="validation.harness_invocation.completed",
            global_seq=1,
            invocation_id=uuid4(),
            run_id=uuid4(),
            outcome="flaky",
            callback_token="tok-456",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert biz[0][1][1] == "flaky"

    async def test_invocation_expired(self):
        from aiteamos_validation.application.reflection_consumer import (
            ReflectionConsumer,
        )
        from aiteamos_validation.domain.events import HarnessInvocationExpired

        db = FakeExecDB()
        consumer = ReflectionConsumer(db=db)

        event = HarnessInvocationExpired(
            event_type="validation.harness_invocation.expired",
            global_seq=1,
            invocation_id=uuid4(),
            run_id=uuid4(),
            callback_token="tok-789",
            reason="gc_deadline_exceeded",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert "UPDATE harness_invocation" in biz[0][0]


# ---------------------------------------------------------------------------
# FeedbackConsumer tests
# ---------------------------------------------------------------------------


class TestFeedbackConsumer:
    async def test_positive_feedback_inserts_and_updates_confidence(self):
        from aiteamos_knowledge.application.feedback_consumer import FeedbackConsumer
        from aiteamos_knowledge.domain.events import MemoryFeedbackRecorded

        db = FakeExecDB()
        consumer = FeedbackConsumer(db=db)

        event = MemoryFeedbackRecorded(
            event_type="knowledge.memory_feedback.recorded",
            global_seq=1,
            memory_id=uuid4(),
            task_run_id=uuid4(),
            outcome="positive",
            delta=0.05,
            is_system_meta=False,
        )
        result = await consumer.consume(event)

        assert result is True
        biz = _business_sql(db.executed)
        assert len(biz) == 2
        assert "INSERT INTO memory_feedback" in biz[0][0]
        assert "UPDATE memory_node" in biz[1][0]

    async def test_negative_feedback_decays_confidence(self):
        from aiteamos_knowledge.application.feedback_consumer import FeedbackConsumer
        from aiteamos_knowledge.domain.events import MemoryFeedbackRecorded

        db = FakeExecDB()
        consumer = FeedbackConsumer(db=db)

        event = MemoryFeedbackRecorded(
            event_type="knowledge.memory_feedback.recorded",
            global_seq=1,
            memory_id=uuid4(),
            task_run_id=uuid4(),
            outcome="negative",
            delta=-0.1,
            is_system_meta=False,
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert biz[1][1][1] == -0.1

    async def test_neutral_feedback_skips_confidence_update(self):
        from aiteamos_knowledge.application.feedback_consumer import FeedbackConsumer
        from aiteamos_knowledge.domain.events import MemoryFeedbackRecorded

        db = FakeExecDB()
        consumer = FeedbackConsumer(db=db)

        event = MemoryFeedbackRecorded(
            event_type="knowledge.memory_feedback.recorded",
            global_seq=1,
            memory_id=uuid4(),
            task_run_id=uuid4(),
            outcome="neutral",
            delta=0.0,
            is_system_meta=False,
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert len(biz) == 1
        assert "INSERT INTO memory_feedback" in biz[0][0]

    async def test_ignores_unrelated_events(self):
        from aiteamos_knowledge.application.feedback_consumer import FeedbackConsumer

        db = FakeExecDB()
        consumer = FeedbackConsumer(db=db)

        event = _make_event("knowledge.memory_node.created", seq=1)
        await consumer.consume(event)

        assert len(_business_sql(db.executed)) == 0


# ---------------------------------------------------------------------------
# PromotionApprovalBridge tests
# ---------------------------------------------------------------------------


@dataclass
class FakePromotionService:
    """Stub promotion service."""

    approved: list = field(default_factory=list)
    should_raise: bool = False

    async def approve_promotion(self, memory_id, *, approved_by=None):
        if self.should_raise:
            raise ValueError("Already at highest tier")
        self.approved.append((memory_id, approved_by))
        return None


class TestPromotionApprovalBridge:
    async def test_approve_triggers_promotion(self):
        from aiteamos_knowledge.application.promotion_approval_bridge import (
            PromotionApprovalBridge,
        )
        from aiteamos_governance.domain.events import ReviewDecisionMade

        db = FakeExecDB()
        svc = FakePromotionService()
        bridge = PromotionApprovalBridge(db=db, promotion_service=svc)

        target_id = uuid4()
        event = ReviewDecisionMade(
            event_type="governance.review_case.decision_made",
            global_seq=1,
            review_case_id=uuid4(),
            target_kind="memory_promotion",
            target_id=target_id,
            verdict="approve",
            reason="excellent",
        )
        result = await bridge.consume(event)

        assert result is True
        assert len(svc.approved) == 1
        assert svc.approved[0][0] == target_id

    async def test_reject_does_not_promote(self):
        from aiteamos_knowledge.application.promotion_approval_bridge import (
            PromotionApprovalBridge,
        )
        from aiteamos_governance.domain.events import ReviewDecisionMade

        db = FakeExecDB()
        svc = FakePromotionService()
        bridge = PromotionApprovalBridge(db=db, promotion_service=svc)

        event = ReviewDecisionMade(
            event_type="governance.review_case.decision_made",
            global_seq=1,
            review_case_id=uuid4(),
            target_kind="memory_promotion",
            target_id=uuid4(),
            verdict="reject",
            reason="not ready",
        )
        await bridge.consume(event)

        assert len(svc.approved) == 0

    async def test_non_promotion_target_ignored(self):
        from aiteamos_knowledge.application.promotion_approval_bridge import (
            PromotionApprovalBridge,
        )
        from aiteamos_governance.domain.events import ReviewDecisionMade

        db = FakeExecDB()
        svc = FakePromotionService()
        bridge = PromotionApprovalBridge(db=db, promotion_service=svc)

        event = ReviewDecisionMade(
            event_type="governance.review_case.decision_made",
            global_seq=1,
            review_case_id=uuid4(),
            target_kind="task_deliverable",
            target_id=uuid4(),
            verdict="approve",
        )
        await bridge.consume(event)

        assert len(svc.approved) == 0

    async def test_promotion_failure_logged(self):
        from aiteamos_knowledge.application.promotion_approval_bridge import (
            PromotionApprovalBridge,
        )
        from aiteamos_governance.domain.events import ReviewDecisionMade

        db = FakeExecDB()
        svc = FakePromotionService(should_raise=True)
        bridge = PromotionApprovalBridge(db=db, promotion_service=svc)

        event = ReviewDecisionMade(
            event_type="governance.review_case.decision_made",
            global_seq=1,
            review_case_id=uuid4(),
            target_kind="memory_promotion",
            target_id=uuid4(),
            verdict="approve",
        )
        # Should not raise — failure is caught and logged
        await bridge.consume(event)


# ---------------------------------------------------------------------------
# SkillHealthMetricConsumer tests
# ---------------------------------------------------------------------------


@dataclass
class FakeSkillHealthDB:
    """DB stub for skill health metric consumer."""

    watermark_seq: int = -1
    executed: list[tuple] = field(default_factory=list)
    skill_rows: list[dict] = field(default_factory=list)

    async def fetchrow(self, query: str, *args) -> dict | None:
        if "projection_watermark" in query:
            if self.watermark_seq < 0:
                return None
            return {"last_seq": self.watermark_seq, "last_event_id": "", "processed_at": None}
        return None

    async def execute(self, query: str, *args) -> str:
        self.executed.append((query[:60], args))
        return ""

    async def fetch(self, query: str, *args) -> list:
        if "declared_skills" in query:
            return self.skill_rows
        return []


class TestSkillHealthMetricConsumer:
    async def test_successful_run_increments_success(self):
        from aiteamos_capability.application.health_metric_consumer import (
            SkillHealthMetricConsumer,
        )
        from aiteamos_execution.domain.events import RunFinished

        skill_id = uuid4()
        db = FakeSkillHealthDB(skill_rows=[{"skill_id": skill_id}])
        consumer = SkillHealthMetricConsumer(db=db)

        event = RunFinished(
            event_type="execution.run.finished",
            global_seq=1,
            run_id=uuid4(),
            task_id="TASK-20260528T120000-0001",
            outcome="success",
        )
        result = await consumer.consume(event)

        assert result is True
        biz = _business_sql(db.executed)
        assert len(biz) == 1
        assert "INSERT INTO skill_health_metric" in biz[0][0]
        # success_count should be 1 (args[3])
        assert biz[0][1][3] == 1
        assert biz[0][1][4] == 0  # failure_count

    async def test_failed_run_increments_failure(self):
        from aiteamos_capability.application.health_metric_consumer import (
            SkillHealthMetricConsumer,
        )
        from aiteamos_execution.domain.events import RunFinished

        skill_id = uuid4()
        db = FakeSkillHealthDB(skill_rows=[{"skill_id": skill_id}])
        consumer = SkillHealthMetricConsumer(db=db)

        event = RunFinished(
            event_type="execution.run.finished",
            global_seq=1,
            run_id=uuid4(),
            task_id="TASK-20260528T120000-0001",
            outcome="failure",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert len(biz) == 1
        assert biz[0][1][3] == 0  # success_count
        assert biz[0][1][4] == 1  # failure_count

    async def test_no_skills_no_update(self):
        from aiteamos_capability.application.health_metric_consumer import (
            SkillHealthMetricConsumer,
        )
        from aiteamos_execution.domain.events import RunFinished

        db = FakeSkillHealthDB(skill_rows=[])
        consumer = SkillHealthMetricConsumer(db=db)

        event = RunFinished(
            event_type="execution.run.finished",
            global_seq=1,
            run_id=uuid4(),
            task_id="TASK-20260528T120000-0001",
            outcome="success",
        )
        await consumer.consume(event)

        biz = _business_sql(db.executed)
        assert len(biz) == 0

    async def test_ignores_unrelated_events(self):
        from aiteamos_capability.application.health_metric_consumer import (
            SkillHealthMetricConsumer,
        )

        db = FakeSkillHealthDB()
        consumer = SkillHealthMetricConsumer(db=db)

        event = _make_event("execution.task.created", seq=1)
        await consumer.consume(event)

        assert len(_business_sql(db.executed)) == 0
