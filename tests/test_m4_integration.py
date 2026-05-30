"""
M4 Integration Tests — Cross-context workflow acceptance (plan.md §4.7).

End-to-end integration tests verifying cross-bounded-context workflows:
1. Memory -> Graph -> Cascade: create memory, project to graph, cascade invalidation
2. Recommendation: member/skill recommendation for tasks
3. Governance: review -> conflict detection -> resolution pipeline
4. Metrics Pipeline: compute value metrics + system health
5. Infrastructure: sharded relay + zombie scanner + observability
6. Activity -> Growth: activity tracking -> statistics -> decay detection
7. Memory Health + Export/Import
8. Full Prometheus Export
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

# -- Knowledge Context
from aiteamos_knowledge.application.graph_projection import (
    GraphProjectionService,
    GraphTraversalChannel,
)
from aiteamos_knowledge.application.cascade_invalidation import (
    CascadeInvalidationService,
    StructuralChangeEvent,
)
from aiteamos_knowledge.application.health import (
    BulkGovernanceService,
    ExportImportService,
    ExportPayload,
    ImportResult,
    MemoryHealthMetrics,
    MemoryHealthService,
)

# -- Execution Context
from aiteamos_execution.application.recommender import (
    MemberRecommender,
    SkillRecommender,
    TaskProfile,
)
from aiteamos_execution.application.metrics import (
    SystemHealthService,
    ValueMetricsService,
)
from aiteamos_execution.application.zombie_scanner import ZombieTaskScanner

# -- Workforce Context
from aiteamos_workforce.application.activity import (
    ActivityEvent,
    ActivityKind,
    ActivityTrackingService,
    DecayWarning,
    GrowthStatisticsService,
    SkillDecayDetector,
)

# -- Governance Context
from aiteamos_governance.application.services import (
    ConflictService,
    ReviewService,
)
from aiteamos_governance.domain.models import (
    ConflictKind,
    DetectorKind,
    ResolutionKind,
    ReviewTargetKind,
    Verdict,
)

# -- Shared Kernel
from aiteamos_shared.outbox import ShardedOutboxRelay
from aiteamos_shared.observability import (
    AppMetrics,
    HealthChecker,
    MetricsRegistry,
)


# ===================================================================
# Shared Mocks
# ===================================================================


class MockTransactionManager:
    @asynccontextmanager
    async def transaction(self):
        yield self


class MockEventPublisher:
    def __init__(self):
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)

    async def publish_events(self, events: list[Any], *, partition_key: str, tx: Any) -> None:
        self.events.extend(events)


class InMemoryGraphStore:
    def __init__(self):
        self._edges: dict[str, list[tuple[str, str, str]]] = {}
        self._nodes: set[str] = set()

    async def merge_edge(self, source_id: str, target_id: str, edge_type: str, edge_id: str) -> None:
        self._nodes.add(source_id)
        self._nodes.add(target_id)
        if source_id not in self._edges:
            self._edges[source_id] = []
        for existing in self._edges[source_id]:
            if existing[2] == edge_id:
                return
        self._edges[source_id].append((target_id, edge_type, edge_id))

    async def remove_edge(self, edge_id: str) -> None:
        for source_id in self._edges:
            self._edges[source_id] = [e for e in self._edges[source_id] if e[2] != edge_id]

    async def fetch_neighbors(self, node_id: str, edge_types: set[str], max_depth: int = 2) -> list[dict[str, Any]]:
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(node_id, 0)]
        results: list[dict[str, Any]] = []
        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            for target, etype, eid in self._edges.get(current, []):
                if etype in edge_types and target not in visited:
                    results.append({"node_id": target, "edge_type": etype, "depth": depth + 1})
                    if depth + 1 < max_depth:
                        queue.append((target, depth + 1))
        return results

    async def bfs_neighbors(
        self, seed_ids: set[str], *, depth: int = 2, edge_types: set[str] | None = None
    ) -> set[str]:
        edge_types = edge_types or set()
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(sid, 0) for sid in seed_ids]
        neighbors: set[str] = set()
        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)
            for target, etype, _eid in self._edges.get(current, []):
                if etype in edge_types and target not in visited:
                    neighbors.add(target)
                    if d + 1 < depth:
                        queue.append((target, d + 1))
        return neighbors

    async def bfs_dependents(
        self, root_id: str, depth: int, fan_limit: int, *, tx: Any = None
    ) -> set[str]:
        """Reverse BFS: follow edges backwards to find dependents."""
        reverse_edges: dict[str, list[str]] = {}
        for src, edges in self._edges.items():
            for target, _etype, _eid in edges:
                if target not in reverse_edges:
                    reverse_edges[target] = []
                reverse_edges[target].append(src)

        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(root_id, 0)]
        dependents: set[str] = set()
        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)
            for src in reverse_edges.get(current, []):
                if src not in visited:
                    dependents.add(src)
                    if len(dependents) >= fan_limit:
                        return dependents
                    if d + 1 < depth:
                        queue.append((src, d + 1))
        return dependents


class MockMemoryRepo:
    def __init__(self):
        self._memories: dict[str, dict[str, Any]] = {}

    async def count_total(self, *, tx=None) -> int:
        return len(self._memories)

    async def count_updated_since(self, since: datetime, *, tx=None) -> int:
        return sum(1 for m in self._memories.values() if m.get("updated_at") and m["updated_at"] >= since)

    async def count_by_lifecycle(self, state: str, *, tx=None) -> int:
        return sum(1 for m in self._memories.values() if m.get("status") == state)

    async def count_recalled(self, *, tx=None) -> int:
        return sum(1 for m in self._memories.values() if m.get("recalled", False))

    async def count_by_tier(self, *, tx=None) -> dict[str, int]:
        tiers: dict[str, int] = {}
        for m in self._memories.values():
            t = m.get("tier", "unknown")
            tiers[t] = tiers.get(t, 0) + 1
        return tiers

    async def export_all_memories(self, *, tx=None) -> list[dict[str, Any]]:
        return list(self._memories.values())

    async def export_all_skills(self, *, tx=None) -> list[dict[str, Any]]:
        return []

    async def export_all_members(self, *, tx=None) -> list[dict[str, Any]]:
        return []

    async def memory_exists(self, title: str, *, tx=None) -> bool:
        return any(m.get("title") == title for m in self._memories.values())

    async def import_memory(self, data: dict[str, Any], *, tx=None) -> None:
        self._memories[data.get("id", str(uuid4()))] = data

    async def find_facts_with_anchors(self, anchors: list[str], *, tx=None) -> list[str]:
        return [m["id"] for m in self._memories.values() if m.get("title") in anchors]

    async def lock_for_update(self, memory_id: str, *, tx=None) -> dict[str, Any] | None:
        return self._memories.get(memory_id)

    async def set_needs_verify(self, memory_id: str, *, tx=None) -> None:
        if memory_id in self._memories:
            self._memories[memory_id]["status"] = "needs_verify"


class MockDB:
    def __init__(self, *, rows=None, lock_acquired=True, checkpoint_seq=None):
        self._rows = rows or []
        self._lock_acquired = lock_acquired
        self._checkpoint_seq = checkpoint_seq

    async def fetch(self, query, *args):
        return self._rows

    async def fetchrow(self, query, *args):
        if "pg_try_advisory_lock" in query:
            return {0: self._lock_acquired}
        if "last_published_seq" in query:
            return {"last_published_seq": self._checkpoint_seq} if self._checkpoint_seq else None
        return None

    async def execute(self, query, *args):
        pass


class MockKafka:
    def __init__(self):
        self.sent: list = []

    async def send(self, topic, value, key=None):
        self.sent.append((topic, value, key))


class MockActivityRepo:
    def __init__(self):
        self._events: list[ActivityEvent] = []

    async def save(self, event: ActivityEvent, *, tx=None) -> None:
        self._events.append(event)

    async def find_by_member(self, member_id, *, limit=50, offset=0, tx=None):
        results = [e for e in self._events if e.member_id == member_id]
        return results[offset : offset + limit]

    async def count_by_member_and_kind(self, member_id, kind: str, *, since=None, tx=None) -> int:
        return sum(
            1
            for e in self._events
            if e.member_id == member_id and e.event_kind.value == kind and (since is None or e.occurred_at >= since)
        )

    async def count_by_member_in_range(self, member_id, *, start: datetime, end: datetime, tx=None) -> int:
        return sum(1 for e in self._events if e.member_id == member_id and start <= e.occurred_at < end)


class MockSkillUsage:
    def __init__(self, *, failures: dict[str, int] | None = None):
        self._failures = failures or {}

    async def get_consecutive_failures(self, member_id, skill_id: str) -> int:
        return self._failures.get(skill_id, 0)


class MockConflictCounter:
    def __init__(self, *, count: int = 0):
        self._count = count

    async def count_unresolved(self) -> int:
        return self._count


class MockReviewRepo:
    def __init__(self):
        self._reviews: dict[UUID, Any] = {}

    async def save(self, aggregate, *, tx=None) -> None:
        self._reviews[aggregate.id] = aggregate

    async def get_by_id(self, review_id, *, tx=None):
        return self._reviews.get(review_id)

    async def find_pending(self, *, tx=None):
        return [r for r in self._reviews.values() if r.verdict is None]

    async def find_by_target(self, target_kind, target_id, *, tx=None):
        return [r for r in self._reviews.values() if str(r.target_kind.value) == target_kind and r.target_id == target_id]

    async def count_by_target(self, target_kind, target_id, *, tx=None) -> int:
        return len(await self.find_by_target(target_kind, target_id))


class MockConflictRepo:
    def __init__(self):
        self._conflicts: dict[UUID, Any] = {}

    async def save(self, aggregate, *, tx=None) -> None:
        self._conflicts[aggregate.id] = aggregate

    async def get_by_id(self, conflict_id, *, tx=None):
        return self._conflicts.get(conflict_id)

    async def find_unresolved(self, *, tx=None):
        return [c for c in self._conflicts.values() if c.resolution is None]

    async def find_by_memory(self, memory_id, *, tx=None):
        return [c for c in self._conflicts.values() if c.memory_a_id == memory_id or c.memory_b_id == memory_id]


class MockMemberProvider:
    async def list_active_members(self):
        return [UUID(int=1), UUID(int=2)]

    async def get_member_skills(self, member_id):
        return ["python", "testing"] if member_id == UUID(int=1) else ["javascript"]

    async def get_member_memories(self, member_id):
        return ["mem-1", "mem-2"] if member_id == UUID(int=1) else ["mem-3"]

    async def get_member_load(self, member_id):
        return 0.3 if member_id == UUID(int=1) else 0.8

    async def get_member_success_rate(self, member_id):
        return 0.9 if member_id == UUID(int=1) else 0.7


# ===================================================================
# Integration Test 1: Memory -> Graph -> Cascade
# ===================================================================


class TestMemoryGraphCascadePipeline:
    async def test_full_pipeline(self):
        graph_store = InMemoryGraphStore()
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()
        repo = MockMemoryRepo()

        projection = GraphProjectionService(graph_store=graph_store, tx_manager=tx_mgr)

        mem_a = str(UUID(int=10))
        mem_b = str(UUID(int=11))
        mem_c = str(UUID(int=12))

        edge_a_b = str(uuid4())
        edge_b_c = str(uuid4())
        await graph_store.merge_edge(mem_a, mem_b, "depends", edge_a_b)
        await graph_store.merge_edge(mem_b, mem_c, "depends", edge_b_c)

        traversal = GraphTraversalChannel(graph_store=graph_store)
        neighbors = await traversal.fetch_graph_neighbors(seed_ids={mem_a}, depth=2)
        assert mem_b in neighbors
        assert mem_c in neighbors

        cascade = CascadeInvalidationService(
            graph_store=graph_store, memory_repo=repo, tx_manager=tx_mgr, event_publisher=publisher
        )
        repo._memories[mem_a] = {"id": mem_a, "status": "active", "title": "Root"}
        repo._memories[mem_b] = {"id": mem_b, "status": "active", "title": "Dep1"}
        repo._memories[mem_c] = {"id": mem_c, "status": "active", "title": "Dep2"}

        # mem-c changes -> mem-a and mem-b depend on it (via reverse edges)
        evt = StructuralChangeEvent(
            event_type="knowledge.memory.structure_changed",
            changed_anchors=["Dep2"],
        )
        result = await cascade.on_structural_change(evt)
        assert result.impacted_count >= 2


# ===================================================================
# Integration Test 2: Recommendation
# ===================================================================


class TestRecommendationPipeline:
    async def test_member_recommendation(self):
        member_rec = MemberRecommender(member_provider=MockMemberProvider())
        task = TaskProfile(task_id="T1", department_id=UUID(int=100), declared_skills=["python", "testing"], tags=["python"])
        results = await member_rec.recommend(task, top_k=2)
        assert len(results) >= 1
        assert results[0].member_id == UUID(int=1)

    async def test_skill_recommendation(self):
        class MockTaskHistory:
            async def find_similar_tasks(self, description, tags, limit=50):
                return [
                    {"task_id": "T1", "skills": ["s1", "s2"], "outcome": "success"},
                    {"task_id": "T2", "skills": ["s1"], "outcome": "success"},
                ]

        skill_rec = SkillRecommender(task_history=MockTaskHistory())
        task = TaskProfile(task_id="T3", department_id=UUID(int=100), tags=["python"])
        results = await skill_rec.recommend(task)
        assert len(results) >= 1


# ===================================================================
# Integration Test 3: Governance
# ===================================================================


class TestGovernancePipeline:
    async def test_review_and_conflict_pipeline(self):
        tx_mgr = MockTransactionManager()
        publisher = MockEventPublisher()

        review_svc = ReviewService(review_repo=MockReviewRepo(), tx_manager=tx_mgr, event_publisher=publisher)
        conflict_svc = ConflictService(conflict_repo=MockConflictRepo(), tx_manager=tx_mgr, event_publisher=publisher)

        review_case = await review_svc.create_review(
            target_kind=ReviewTargetKind.MEMORY_CANDIDATE, target_id=uuid4(), reviewer_member_id=UUID(int=1)
        )
        assert review_case is not None

        decided = await review_svc.decide(review_id=review_case.id, verdict=Verdict.APPROVE, reason="Looks good")
        assert decided is not None

        mem_a = uuid4()
        mem_b = uuid4()
        conflict = await conflict_svc.report_conflict(
            memory_a_id=mem_a, memory_b_id=mem_b,
            conflict_kind=ConflictKind.SEMANTIC, detected_by=DetectorKind.AUTO_ADMISSION,
        )
        assert conflict is not None

        resolved = await conflict_svc.resolve_conflict(
            conflict_id=conflict.id, resolution=ResolutionKind.KEEP_A,
            winner_id=mem_a, resolved_by=UUID(int=1),
        )
        assert resolved is not None

        assert len(publisher.events) >= 3


# ===================================================================
# Integration Test 4: Metrics + Health
# ===================================================================


class TestMetricsHealthPipeline:
    async def test_full_metrics_pipeline(self):
        class MockProvider:
            async def count_tasks_avoided_rework(self, *, since):
                return 25

            async def get_onboarding_efficiency(self):
                return 0.35

            async def get_memory_active_rate(self):
                return 0.80

            async def count_unresolved_conflicts(self):
                return 1

            async def get_task_first_pass_rate(self):
                return 0.88

            async def get_avg_fix_rounds(self):
                return 1.5

            async def get_skill_health(self):
                return {"active": 20, "warning": 5, "deprecated": 3}

            async def get_validation_availability(self):
                return 0.999

            async def count_total_tasks(self):
                return 1000

            async def count_total_members(self):
                return 30

        provider = MockProvider()
        value_svc = ValueMetricsService(data_provider=provider)
        value = await value_svc.compute_value_metrics(period="monthly")
        assert value.tasks_avoided_rework == 25
        assert value.period == "monthly"

        health_svc = SystemHealthService(data_provider=provider)
        health = await health_svc.compute_health()
        assert health.task_first_pass_rate == 0.88

        metrics = AppMetrics()
        metrics.set_outbox_backlog(5)
        metrics.set_event_consumption_lag(0.5)
        text = metrics.registry.export_prometheus_text()
        assert "outbox_backlog" in text


# ===================================================================
# Integration Test 5: Infrastructure
# ===================================================================


class TestInfrastructurePipeline:
    async def test_sharded_relay_lifecycle(self):
        rows = [
            {"id": uuid4(), "event_type": "E1", "partition_key": "pk1", "payload": {}, "global_seq": 10},
            {"id": uuid4(), "event_type": "E2", "partition_key": "pk2", "payload": {}, "global_seq": 11},
        ]
        db = MockDB(rows=rows, lock_acquired=True, checkpoint_seq=5)
        kafka = MockKafka()
        relay = ShardedOutboxRelay(db=db, kafka_producer=kafka, shard_id=0, num_shards=2, instance_id="test")

        assert await relay.try_acquire_lock()
        assert await relay.load_checkpoint() == 5
        assert await relay._poll_and_publish() == 2
        assert len(kafka.sent) == 2
        assert relay.high_watermark == 11
        await relay.save_checkpoint()
        await relay.release_lock()

    async def test_zombie_scanner_integration(self):
        class MockStore:
            def __init__(self):
                self.failed: list = []

            async def find_active_tasks(self):
                return [
                    {"task_id": "TASK-Z", "state": "running", "run_id": None, "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)},
                    {"task_id": "TASK-H", "state": "running", "run_id": "active", "updated_at": datetime(2020, 1, 1, tzinfo=timezone.utc)},
                ]

            async def fail_task(self, task_id, *, reason):
                self.failed.append(task_id)

        class MockChecker:
            async def is_workflow_active(self, run_id):
                return run_id == "active"

        store = MockStore()
        scanner = ZombieTaskScanner(task_store=store, workflow_checker=MockChecker())
        result = await scanner.scan_once()
        assert result.zombie_count == 1
        assert "TASK-Z" in result.failed_task_ids

    async def test_health_check_integration(self):
        class OK:
            async def check(self):
                return True

        class Fail:
            async def check(self):
                return False

        checker = HealthChecker(version="4.7.0")
        checker.register_check("db", OK())
        checker.register_check("kafka", OK())
        checker.register_check("temporal", Fail())
        result = await checker.check()
        assert result.status == "degraded"
        assert result.checks["temporal"] == "failed"


# ===================================================================
# Integration Test 6: Activity -> Growth -> Decay
# ===================================================================


class TestActivityGrowthDecayPipeline:
    async def test_full_activity_pipeline(self):
        tx_mgr = MockTransactionManager()
        activity_repo = MockActivityRepo()
        tracking = ActivityTrackingService(activity_repo=activity_repo, tx_manager=tx_mgr)

        member_id = UUID(int=1)
        now = datetime.now(timezone.utc)

        await activity_repo.save(ActivityEvent(member_id=member_id, event_kind=ActivityKind.TASK_COMPLETED, occurred_at=now))
        await activity_repo.save(ActivityEvent(member_id=member_id, event_kind=ActivityKind.TASK_FAILED, occurred_at=now - timedelta(hours=1)))

        timeline = await activity_repo.find_by_member(member_id)
        assert len(timeline) == 2

        growth = GrowthStatisticsService(activity_repo=activity_repo)
        stats = await growth.compute_stats(member_id)
        assert stats.tasks_completed == 1
        assert stats.tasks_failed == 1
        assert stats.first_pass_rate == 0.5

        skill_usage = MockSkillUsage(failures={"skill-x": 5})
        decay = SkillDecayDetector(skill_usage=skill_usage)
        result = await decay.check_decay(member_id, "skill-x")
        assert result is not None
        assert isinstance(result, DecayWarning)
        assert result.warning_level == "critical"

    async def test_no_decay_for_healthy_skill(self):
        member_id = UUID(int=1)
        decay = SkillDecayDetector(skill_usage=MockSkillUsage(failures={"skill-y": 1}))
        result = await decay.check_decay(member_id, "skill-y")
        assert result is None


# ===================================================================
# Integration Test 7: Memory Health + Export/Import
# ===================================================================


class TestMemoryHealthExportPipeline:
    async def test_health_and_export_import(self):
        tx_mgr = MockTransactionManager()
        repo = MockMemoryRepo()
        now = datetime.now(timezone.utc)

        repo._memories["mem-1"] = {"id": "mem-1", "status": "active", "title": "Recent", "updated_at": now - timedelta(days=5), "tier": "core", "recalled": True}
        repo._memories["mem-2"] = {"id": "mem-2", "status": "active", "title": "Old", "updated_at": now - timedelta(days=60), "tier": "contextual", "recalled": False}

        health_svc = MemoryHealthService(health_repo=repo, conflict_provider=MockConflictCounter(count=2))
        metrics = await health_svc.compute_metrics()
        assert isinstance(metrics, MemoryHealthMetrics)
        assert metrics.total_count == 2

        export_svc = ExportImportService(export_repo=repo, import_repo=repo, tx_manager=tx_mgr)
        exported = await export_svc.export_all()
        assert isinstance(exported, ExportPayload)
        assert len(exported.memories) == 2

        result = await export_svc.import_memories(exported.memories)
        assert isinstance(result, ImportResult)


# ===================================================================
# Integration Test 8: Full Prometheus Export
# ===================================================================


class TestFullPrometheusExport:
    def test_comprehensive_export(self):
        metrics = AppMetrics()
        metrics.record_api_request(method="GET", path="/memories", duration=0.05, status_code=200)
        metrics.record_api_request(method="POST", path="/memories", duration=0.12, status_code=201)
        metrics.set_outbox_backlog(42)
        metrics.set_event_consumption_lag(1.5)

        text = metrics.registry.export_prometheus_text()
        assert "aiteamos_api_requests_total" in text
        assert "aiteamos_outbox_backlog" in text
        assert "42" in text
        assert "# HELP" in text
        assert "# TYPE" in text
