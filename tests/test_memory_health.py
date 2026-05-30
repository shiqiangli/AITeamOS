"""
Stage 4.4 — Memory 治理与健康度测试。

Test MemoryHealthService, BulkGovernanceService, ExportImportService。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest

from aiteamos_knowledge.application.health import (
    BulkGovernanceService,
    BulkOperationResult,
    ExportImportService,
    ExportPayload,
    ImportResult,
    MemoryHealthMetrics,
    MemoryHealthService,
    FRESHNESS_WINDOW_DAYS,
    DEFAULT_GC_UNUSED_DAYS,
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


class MockHealthRepo:
    def __init__(self, *, total=0, recent=0, recalled=0, deprecated=0,
                needs_verify=0, tier_dist=None):
        self._total = total
        self._recent = recent
        self._recalled = recalled
        self._deprecated = deprecated
        self._needs_verify = needs_verify
        self._tier_dist = tier_dist or {}

    async def count_total(self, *, tx=None):
        return self._total

    async def count_updated_since(self, since, *, tx=None):
        return self._recent

    async def count_by_lifecycle(self, state, *, tx=None):
        if state == "deprecated":
            return self._deprecated
        if state == "needs_verify":
            return self._needs_verify
        return 0

    async def count_recalled(self, *, tx=None):
        return self._recalled

    async def count_by_tier(self, *, tx=None):
        return dict(self._tier_dist)


class MockConflictProvider:
    def __init__(self, count=0):
        self._count = count

    async def count_unresolved(self):
        return self._count


class MockBulkRepo:
    def __init__(self):
        self._ids: list = []
        self.updated: list[tuple[list, str, str]] = []

    def set_matching_ids(self, ids):
        self._ids = ids

    async def find_ids_by_criteria(self, *, lifecycle_state=None,
                                    not_used_since=None, tier=None, tx=None):
        return list(self._ids)

    async def bulk_update_lifecycle(self, memory_ids, new_state, reason, *, tx=None):
        self.updated.append((memory_ids, new_state, reason))
        return len(memory_ids)


class MockExportRepo:
    def __init__(self, *, memories=None, skills=None, members=None):
        self._memories = memories or []
        self._skills = skills or []
        self._members = members or []

    async def export_all_memories(self, *, tx=None):
        return list(self._memories)

    async def export_all_skills(self, *, tx=None):
        return list(self._skills)

    async def export_all_members(self, *, tx=None):
        return list(self._members)


class MockImportRepo:
    def __init__(self):
        self._existing: set[str] = set()
        self.imported: list[dict] = []

    def add_existing(self, title: str):
        self._existing.add(title)

    async def memory_exists(self, title, *, tx=None):
        return title in self._existing

    async def import_memory(self, data, *, tx=None):
        self.imported.append(data)


# ---------------------------------------------------------------------------
# Tests: MemoryHealthService
# ---------------------------------------------------------------------------


class TestMemoryHealthService:
    @pytest.mark.asyncio
    async def test_empty_db_returns_zero_metrics(self):
        repo = MockHealthRepo(total=0)
        conflicts = MockConflictProvider(count=0)
        svc = MemoryHealthService(health_repo=repo, conflict_provider=conflicts)

        metrics = await svc.compute_metrics()

        assert metrics.total_count == 0
        assert metrics.freshness_rate == 0.0
        assert metrics.active_rate == 0.0
        assert metrics.stale_rate == 0.0

    @pytest.mark.asyncio
    async def test_freshness_rate(self):
        repo = MockHealthRepo(total=100, recent=30)
        conflicts = MockConflictProvider(count=0)
        svc = MemoryHealthService(health_repo=repo, conflict_provider=conflicts)

        metrics = await svc.compute_metrics()
        assert metrics.freshness_rate == 0.30

    @pytest.mark.asyncio
    async def test_active_rate(self):
        repo = MockHealthRepo(total=200, recalled=150)
        conflicts = MockConflictProvider(count=0)
        svc = MemoryHealthService(health_repo=repo, conflict_provider=conflicts)

        metrics = await svc.compute_metrics()
        assert metrics.active_rate == 0.75

    @pytest.mark.asyncio
    async def test_stale_rate(self):
        repo = MockHealthRepo(total=100, deprecated=10, needs_verify=5)
        conflicts = MockConflictProvider(count=0)
        svc = MemoryHealthService(health_repo=repo, conflict_provider=conflicts)

        metrics = await svc.compute_metrics()
        assert metrics.stale_rate == 0.15  # (10+5)/100

    @pytest.mark.asyncio
    async def test_unresolved_conflicts(self):
        repo = MockHealthRepo(total=10)
        conflicts = MockConflictProvider(count=3)
        svc = MemoryHealthService(health_repo=repo, conflict_provider=conflicts)

        metrics = await svc.compute_metrics()
        assert metrics.unresolved_conflicts == 3

    @pytest.mark.asyncio
    async def test_tier_distribution(self):
        tier_dist = {"facts": 80, "patterns": 15, "principles": 5}
        repo = MockHealthRepo(total=100, tier_dist=tier_dist)
        conflicts = MockConflictProvider(count=0)
        svc = MemoryHealthService(health_repo=repo, conflict_provider=conflicts)

        metrics = await svc.compute_metrics()
        assert metrics.tier_distribution == tier_dist

    @pytest.mark.asyncio
    async def test_all_metrics_combined(self):
        repo = MockHealthRepo(
            total=500, recent=100, recalled=400,
            deprecated=20, needs_verify=30,
            tier_dist={"facts": 400, "patterns": 80, "principles": 20},
        )
        conflicts = MockConflictProvider(count=5)
        svc = MemoryHealthService(health_repo=repo, conflict_provider=conflicts)

        metrics = await svc.compute_metrics()

        assert metrics.total_count == 500
        assert metrics.freshness_rate == 0.2
        assert metrics.active_rate == 0.8
        assert metrics.stale_rate == 0.1
        assert metrics.unresolved_conflicts == 5


# ---------------------------------------------------------------------------
# Tests: BulkGovernanceService
# ---------------------------------------------------------------------------


class TestBulkGovernanceService:
    @pytest.fixture
    def setup(self):
        repo = MockBulkRepo()
        tx = MockTransactionManager()
        svc = BulkGovernanceService(bulk_repo=repo, tx_manager=tx)
        return svc, repo, tx

    @pytest.mark.asyncio
    async def test_bulk_deprecate_no_matches(self, setup):
        svc, repo, tx = setup
        result = await svc.bulk_deprecate(tier="facts")
        assert result.affected_count == 0

    @pytest.mark.asyncio
    async def test_bulk_deprecate_with_matches(self, setup):
        svc, repo, tx = setup
        ids = [uuid4() for _ in range(5)]
        repo.set_matching_ids(ids)

        result = await svc.bulk_deprecate(tier="facts")

        assert result.affected_count == 5
        assert len(repo.updated) == 1
        assert repo.updated[0][1] == "deprecated"

    @pytest.mark.asyncio
    async def test_bulk_verify(self, setup):
        svc, repo, tx = setup
        ids = [uuid4() for _ in range(3)]
        repo.set_matching_ids(ids)

        result = await svc.bulk_verify()

        assert result.affected_count == 3
        assert repo.updated[0][1] == "active"

    @pytest.mark.asyncio
    async def test_gc_unused(self, setup):
        svc, repo, tx = setup
        ids = [uuid4() for _ in range(10)]
        repo.set_matching_ids(ids)

        result = await svc.gc_unused(unused_days=60)

        assert result.affected_count == 10
        assert repo.updated[0][2] == "gc_unused_threshold"


# ---------------------------------------------------------------------------
# Tests: ExportImportService
# ---------------------------------------------------------------------------


class TestExportImportService:
    @pytest.fixture
    def setup(self):
        export_repo = MockExportRepo(
            memories=[{"title": "m1"}, {"title": "m2"}],
            skills=[{"name": "s1"}],
            members=[{"display_name": "Alice"}],
        )
        import_repo = MockImportRepo()
        tx = MockTransactionManager()
        svc = ExportImportService(
            export_repo=export_repo, import_repo=import_repo, tx_manager=tx,
        )
        return svc, export_repo, import_repo, tx

    @pytest.mark.asyncio
    async def test_export_all(self, setup):
        svc, _, _, _ = setup
        payload = await svc.export_all()

        assert isinstance(payload, ExportPayload)
        assert len(payload.memories) == 2
        assert len(payload.skills) == 1
        assert len(payload.members) == 1
        assert payload.version == "1.0"

    @pytest.mark.asyncio
    async def test_import_memories(self, setup):
        svc, _, import_repo, _ = setup
        memories = [
            {"title": "New Memory 1", "statement": "..."},
            {"title": "New Memory 2", "statement": "..."},
        ]

        result = await svc.import_memories(memories)

        assert result.imported_count == 2
        assert result.skipped_duplicates == 0
        assert len(import_repo.imported) == 2

    @pytest.mark.asyncio
    async def test_import_skips_duplicates(self, setup):
        svc, _, import_repo, _ = setup
        import_repo.add_existing("Existing Memory")

        memories = [
            {"title": "Existing Memory", "statement": "..."},
            {"title": "New Memory", "statement": "..."},
        ]

        result = await svc.import_memories(memories)

        assert result.imported_count == 1
        assert result.skipped_duplicates == 1

    @pytest.mark.asyncio
    async def test_import_skips_empty_title(self, setup):
        svc, _, import_repo, _ = setup
        memories = [
            {"statement": "no title"},
            {"title": "Valid", "statement": "..."},
        ]

        result = await svc.import_memories(memories)

        assert result.imported_count == 1
        assert len(result.errors) == 1
        assert "without title" in result.errors[0]

    @pytest.mark.asyncio
    async def test_import_empty_list(self, setup):
        svc, _, _, _ = setup
        result = await svc.import_memories([])
        assert result.imported_count == 0
        assert result.skipped_duplicates == 0


# ---------------------------------------------------------------------------
# Tests: Value objects & Constants
# ---------------------------------------------------------------------------


class TestHealthValueObjects:
    def test_health_metrics_defaults(self):
        m = MemoryHealthMetrics()
        assert m.total_count == 0
        assert m.freshness_rate == 0.0

    def test_bulk_operation_result(self):
        r = BulkOperationResult(affected_count=5, skipped_count=2)
        assert r.affected_count == 5

    def test_export_payload_defaults(self):
        p = ExportPayload()
        assert p.version == "1.0"
        assert p.memories == []

    def test_import_result(self):
        r = ImportResult(imported_count=3, skipped_duplicates=1, conflicts_detected=0)
        assert r.imported_count == 3

    def test_constants(self):
        assert FRESHNESS_WINDOW_DAYS == 30
        assert DEFAULT_GC_UNUSED_DAYS == 90
