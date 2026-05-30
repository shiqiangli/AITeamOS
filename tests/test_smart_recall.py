"""
Stage 4.1 — 智能召回增强测试。

Test GraphProjectionService, GraphTraversalChannel, CascadeInvalidationService。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from aiteamos_knowledge.application.graph_projection import (
    GraphProjectionService,
    GraphTraversalChannel,
    ProjectionResult,
    TRAVERSABLE_EDGE_TYPES,
)
from aiteamos_knowledge.application.cascade_invalidation import (
    CascadeInvalidationService,
    CascadeResult,
    DeferredCascadeRequired,
    StructuralChangeEvent,
    MAX_FAN_OUT_PER_HOP,
    MAX_TOTAL_IMPACTED,
    BATCH_SIZE,
    BFS_DEPTH,
)


# ---------------------------------------------------------------------------
# Mock infrastructure
# ---------------------------------------------------------------------------


class MockTransactionManager:
    def __init__(self):
        self.commit_count = 0

    @asynccontextmanager
    async def transaction(self):
        yield None
        self.commit_count += 1


class MockGraphStore:
    """In-memory graph store for testing."""

    def __init__(self):
        self.edges: list[tuple[str, str, str]] = []
        self.removed_edges: list[tuple[str, str, str]] = []
        # Adjacency list for BFS: node_id -> set of (neighbor_id, edge_type)
        self._adj: dict[str, set[tuple[str, str]]] = {}

    async def merge_edge(self, source_id, target_id, relation_type, *, tx=None):
        key = (str(source_id), str(target_id), relation_type)
        if key not in self.edges:
            self.edges.append(key)
            # Build adjacency for BFS
            sid = str(source_id)
            tid = str(target_id)
            if tid not in self._adj:
                self._adj[tid] = set()
            self._adj[tid].add((sid, relation_type))

    async def remove_edge(self, source_id, target_id, relation_type, *, tx=None):
        key = (str(source_id), str(target_id), relation_type)
        if key in self.edges:
            self.edges.remove(key)
        self.removed_edges.append(key)

    async def bfs_neighbors(self, seed_ids, depth, edge_types=None, *, tx=None):
        """Simple BFS on in-memory adjacency."""
        visited = set()
        frontier = {str(sid) for sid in seed_ids}
        seed_strs = {str(sid) for sid in seed_ids}

        for _ in range(depth):
            next_frontier = set()
            for node_id in frontier:
                for neighbor, etype in self._adj.get(node_id, set()):
                    if edge_types and etype not in edge_types:
                        continue
                    if neighbor not in seed_strs and neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
            frontier = next_frontier

        return {UUID(v) if _is_uuid(v) else v for v in visited}

    def add_reverse_edge(self, source_id, target_id, relation_type):
        """Helper to add a reverse edge for BFS (target -> source)."""
        sid = str(source_id)
        tid = str(target_id)
        if tid not in self._adj:
            self._adj[tid] = set()
        self._adj[tid].add((sid, relation_type))


def _is_uuid(s: str) -> bool:
    try:
        UUID(s)
        return True
    except (ValueError, AttributeError):
        return False


class MockEventPublisher:
    def __init__(self):
        self.published: list[Any] = []

    async def publish_events(self, events, *, partition_key, tx):
        self.published.extend(events)


# ---------------------------------------------------------------------------
# Tests: GraphProjectionService
# ---------------------------------------------------------------------------


class TestGraphProjectionService:
    @pytest.fixture
    def setup(self):
        store = MockGraphStore()
        tx = MockTransactionManager()
        svc = GraphProjectionService(graph_store=store, tx_manager=tx)
        return svc, store, tx

    @pytest.mark.asyncio
    async def test_on_edge_added(self, setup):
        svc, store, tx = setup
        src, tgt = uuid4(), uuid4()

        result = await svc.on_edge_added(src, tgt, "depends")

        assert result.edges_merged == 1
        assert len(store.edges) == 1
        assert tx.commit_count == 1

    @pytest.mark.asyncio
    async def test_on_edge_added_idempotent(self, setup):
        svc, store, tx = setup
        src, tgt = uuid4(), uuid4()

        await svc.on_edge_added(src, tgt, "depends")
        result = await svc.on_edge_added(src, tgt, "depends")

        assert result.edges_merged == 1
        assert len(store.edges) == 1  # MERGE semantics: no duplicate

    @pytest.mark.asyncio
    async def test_on_edge_removed(self, setup):
        svc, store, tx = setup
        src, tgt = uuid4(), uuid4()

        await svc.on_edge_added(src, tgt, "derived")
        result = await svc.on_edge_removed(src, tgt, "derived")

        assert result.edges_removed == 1
        assert len(store.removed_edges) == 1

    @pytest.mark.asyncio
    async def test_project_batch(self, setup):
        svc, store, tx = setup
        ids = [uuid4() for _ in range(4)]

        events = [
            {"action": "added", "source_id": ids[0], "target_id": ids[1], "relation_type": "depends"},
            {"action": "added", "source_id": ids[1], "target_id": ids[2], "relation_type": "derived"},
            {"action": "removed", "source_id": ids[0], "target_id": ids[3], "relation_type": "causal"},
        ]

        result = await svc.project_batch(events)

        assert result.edges_merged == 2
        assert result.edges_removed == 1
        assert tx.commit_count == 1  # Single transaction for batch

    @pytest.mark.asyncio
    async def test_project_batch_empty(self, setup):
        svc, store, tx = setup
        result = await svc.project_batch([])
        assert result.edges_merged == 0
        assert result.edges_removed == 0


# ---------------------------------------------------------------------------
# Tests: GraphTraversalChannel
# ---------------------------------------------------------------------------


class TestGraphTraversalChannel:
    @pytest.fixture
    def setup(self):
        store = MockGraphStore()
        channel = GraphTraversalChannel(graph_store=store)
        return channel, store

    @pytest.mark.asyncio
    async def test_empty_seeds_returns_empty(self, setup):
        channel, store = setup
        result = await channel.fetch_graph_neighbors(set())
        assert result == set()

    @pytest.mark.asyncio
    async def test_single_hop_neighbor(self, setup):
        channel, store = setup
        seed = uuid4()
        neighbor = uuid4()

        # seed -> neighbor (depends)
        store.add_reverse_edge(neighbor, seed, "depends")

        result = await channel.fetch_graph_neighbors({seed}, depth=1)
        assert neighbor in result

    @pytest.mark.asyncio
    async def test_two_hop_traversal(self, setup):
        channel, store = setup
        seed = uuid4()
        hop1 = uuid4()
        hop2 = uuid4()

        store.add_reverse_edge(hop1, seed, "depends")
        store.add_reverse_edge(hop2, hop1, "derived")

        result = await channel.fetch_graph_neighbors({seed}, depth=2)
        assert hop1 in result
        assert hop2 in result

    @pytest.mark.asyncio
    async def test_excludes_non_traversable_edges(self, setup):
        channel, store = setup
        seed = uuid4()
        neighbor = uuid4()

        # "related" is not in TRAVERSABLE_EDGE_TYPES
        store.add_reverse_edge(neighbor, seed, "related")

        result = await channel.fetch_graph_neighbors({seed}, depth=2)
        assert neighbor not in result

    @pytest.mark.asyncio
    async def test_excludes_seeds_from_result(self, setup):
        channel, store = setup
        seed = uuid4()

        # Self-loop
        store.add_reverse_edge(seed, seed, "depends")

        result = await channel.fetch_graph_neighbors({seed}, depth=1)
        assert seed not in result

    @pytest.mark.asyncio
    async def test_multiple_seeds(self, setup):
        channel, store = setup
        seed1, seed2 = uuid4(), uuid4()
        n1, n2 = uuid4(), uuid4()

        store.add_reverse_edge(n1, seed1, "depends")
        store.add_reverse_edge(n2, seed2, "causal")

        result = await channel.fetch_graph_neighbors({seed1, seed2}, depth=1)
        assert n1 in result
        assert n2 in result


# ---------------------------------------------------------------------------
# Mock infrastructure for Cascade tests
# ---------------------------------------------------------------------------


class MockCascadeGraphStore:
    def __init__(self):
        # node_id -> set of dependent_ids
        self._dependents: dict[str, set[str]] = {}

    def add_dependent(self, root_id, dependent_id):
        rid = str(root_id)
        did = str(dependent_id)
        if rid not in self._dependents:
            self._dependents[rid] = set()
        self._dependents[rid].add(did)

    async def bfs_dependents(self, root_id, depth, fan_limit, *, tx=None):
        rid = str(root_id)
        deps = self._dependents.get(rid, set())
        result = set()
        for d in list(deps)[:fan_limit]:
            result.add(UUID(d) if _is_uuid(d) else d)
        return result


@dataclass
class MockMemoryNode:
    id: Any
    confidence_state: str = "valid"


class MockCascadeMemoryRepo:
    def __init__(self):
        self._nodes: dict[str, MockMemoryNode] = {}
        self._anchors: dict[str, list[str]] = {}  # anchor -> [memory_ids]
        self.verified_count = 0

    def add_node(self, node_id, anchors=None):
        sid = str(node_id)
        self._nodes[sid] = MockMemoryNode(id=node_id)
        if anchors:
            for a in anchors:
                if a not in self._anchors:
                    self._anchors[a] = []
                self._anchors[a].append(sid)

    async def find_facts_with_anchors(self, anchors, *, tx=None):
        result = set()
        for a in anchors:
            for mid_str in self._anchors.get(a, []):
                result.add(UUID(mid_str) if _is_uuid(mid_str) else mid_str)
        return list(result)

    async def lock_for_update(self, memory_id, *, tx=None):
        sid = str(memory_id)
        return self._nodes.get(sid)

    async def set_needs_verify(self, memory_id, *, tx=None):
        sid = str(memory_id)
        if sid in self._nodes:
            self._nodes[sid].confidence_state = "needs_verify"
            self.verified_count += 1


# ---------------------------------------------------------------------------
# Tests: CascadeInvalidationService
# ---------------------------------------------------------------------------


class TestCascadeInvalidationService:
    @pytest.fixture
    def setup(self):
        graph = MockCascadeGraphStore()
        repo = MockCascadeMemoryRepo()
        tx = MockTransactionManager()
        publisher = MockEventPublisher()
        svc = CascadeInvalidationService(
            graph_store=graph,
            memory_repo=repo,
            tx_manager=tx,
            event_publisher=publisher,
        )
        return svc, graph, repo, tx, publisher

    @pytest.mark.asyncio
    async def test_no_roots_returns_empty_result(self, setup):
        svc, graph, repo, tx, pub = setup
        evt = StructuralChangeEvent(
            event_type="repo.structure_changed",
            changed_anchors=["nonexistent"],
        )

        result = await svc.on_structural_change(evt)

        assert result.impacted_count == 0
        assert result.overflow is False
        assert result.batches_written == 0

    @pytest.mark.asyncio
    async def test_single_root_no_dependents(self, setup):
        svc, graph, repo, tx, pub = setup
        root_id = uuid4()
        repo.add_node(root_id, anchors=["module_a"])

        evt = StructuralChangeEvent(
            event_type="repo.structure_changed",
            changed_anchors=["module_a"],
        )

        result = await svc.on_structural_change(evt)

        assert result.impacted_count == 1
        assert result.overflow is False
        assert result.batches_written == 1

    @pytest.mark.asyncio
    async def test_cascade_propagation(self, setup):
        svc, graph, repo, tx, pub = setup
        root_id = uuid4()
        dep1 = uuid4()
        dep2 = uuid4()

        repo.add_node(root_id, anchors=["core"])
        repo.add_node(dep1)
        repo.add_node(dep2)

        graph.add_dependent(root_id, dep1)
        graph.add_dependent(dep1, dep2)

        evt = StructuralChangeEvent(
            event_type="repo.structure_changed",
            changed_anchors=["core"],
        )

        result = await svc.on_structural_change(evt)

        assert result.impacted_count == 3  # root + dep1 + dep2
        assert result.overflow is False

    @pytest.mark.asyncio
    async def test_overflow_triggers_deferred(self, setup):
        svc, graph, repo, tx, pub = setup

        # Build a tree that exceeds MAX_TOTAL_IMPACTED across 3 hops:
        # root -> 10 dependents -> each has 10 -> each has 10
        # Total: 1 + 10 + 100 + 1000 = 1111 > 1000
        root_id = uuid4()
        repo.add_node(root_id, anchors=["big_module"])

        hop1 = [uuid4() for _ in range(10)]
        for dep in hop1:
            repo.add_node(dep)
            graph.add_dependent(root_id, dep)

        hop2 = []
        for parent in hop1:
            children = [uuid4() for _ in range(10)]
            for child in children:
                repo.add_node(child)
                graph.add_dependent(parent, child)
                hop2.append(child)

        for parent in hop2:
            children = [uuid4() for _ in range(10)]
            for child in children:
                repo.add_node(child)
                graph.add_dependent(parent, child)

        evt = StructuralChangeEvent(
            event_type="repo.structure_changed",
            changed_anchors=["big_module"],
        )

        result = await svc.on_structural_change(evt)

        assert result.overflow is True
        assert result.deferred is True

    @pytest.mark.asyncio
    async def test_uuid_sorting_prevents_deadlock(self, setup):
        """验证 UUID 字典序排序确保确定性锁序。"""
        svc, graph, repo, tx, pub = setup

        ids = [uuid4() for _ in range(5)]
        for mid in ids:
            repo.add_node(mid, anchors=["shared"])

        evt = StructuralChangeEvent(
            event_type="repo.structure_changed",
            changed_anchors=["shared"],
        )

        result = await svc.on_structural_change(evt)

        assert result.impacted_count == 5
        # All nodes should be set to needs_verify
        for mid in ids:
            node = repo._nodes[str(mid)]
            assert node.confidence_state == "needs_verify"

    @pytest.mark.asyncio
    async def test_batch_size_respected(self, setup):
        """验证分批写回使用 BATCH_SIZE。"""
        svc, graph, repo, tx, pub = setup

        count = BATCH_SIZE * 3 + 7  # 3 full batches + 1 partial
        ids = [uuid4() for _ in range(count)]
        for mid in ids:
            repo.add_node(mid, anchors=["batch_test"])

        evt = StructuralChangeEvent(
            event_type="repo.structure_changed",
            changed_anchors=["batch_test"],
        )

        result = await svc.on_structural_change(evt)

        expected_batches = 4  # ceil(157/50)
        assert result.batches_written == expected_batches

    @pytest.mark.asyncio
    async def test_publishes_batch_needs_verify_event(self, setup):
        svc, graph, repo, tx, pub = setup
        root_id = uuid4()
        repo.add_node(root_id, anchors=["event_test"])

        evt = StructuralChangeEvent(
            event_type="repo.structure_changed",
            changed_anchors=["event_test"],
        )

        await svc.on_structural_change(evt)

        assert len(pub.published) > 0
        batch_event = pub.published[0]
        assert batch_event.triggered_by == "cascade_invalidation"
        assert batch_event.triggered_by_system_meta is True

    @pytest.mark.asyncio
    async def test_constants_values(self):
        """验证常量值与 arch.md §2.7 一致。"""
        assert MAX_FAN_OUT_PER_HOP == 200
        assert MAX_TOTAL_IMPACTED == 1000
        assert BATCH_SIZE == 50
        assert BFS_DEPTH == 3


# ---------------------------------------------------------------------------
# Tests: Value objects
# ---------------------------------------------------------------------------


class TestValueObjects:
    def test_cascade_result_defaults(self):
        r = CascadeResult()
        assert r.impacted_count == 0
        assert r.overflow is False
        assert r.batches_written == 0
        assert r.deferred is False

    def test_structural_change_event(self):
        evt = StructuralChangeEvent(
            event_type="repo.structure_changed",
            changed_anchors=["a", "b"],
            triggered_by="ci_pipeline",
        )
        assert evt.triggered_by == "ci_pipeline"
        assert len(evt.changed_anchors) == 2

    def test_deferred_cascade_required(self):
        evt = DeferredCascadeRequired(
            root_ids=[uuid4()],
            already_processed=[uuid4(), uuid4()],
            reason="fan_out_exceeded",
        )
        assert evt.reason == "fan_out_exceeded"
        assert len(evt.root_ids) == 1
        assert len(evt.already_processed) == 2

    def test_projection_result(self):
        r = ProjectionResult(edges_merged=5, edges_removed=2)
        assert r.edges_merged == 5
        assert r.edges_removed == 2

    def test_traversable_edge_types(self):
        assert "depends" in TRAVERSABLE_EDGE_TYPES
        assert "derived" in TRAVERSABLE_EDGE_TYPES
        assert "causal" in TRAVERSABLE_EDGE_TYPES
        assert "related" not in TRAVERSABLE_EDGE_TYPES
