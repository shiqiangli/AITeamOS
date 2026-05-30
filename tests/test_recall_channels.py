"""
Tests for recall_channels.py — SQL 通道获取器实现。
"""

from uuid import UUID, uuid4

import pytest

from aiteamos_knowledge.infrastructure.recall_channels import (
    PgvectorTopKFetcher,
    SqlAssignedMemoryFetcher,
    SqlConflictChecker,
    SqlMemoryDetailFetcher,
    SqlRecallAuditLogger,
    SqlScopeMemoryFetcher,
)


class FakeDB:
    """Minimal async DB mock matching asyncpg interface."""

    def __init__(self, *, fetch_rows=None, execute_calls=None):
        self._fetch_rows = fetch_rows or []
        self._execute_calls: list = execute_calls if execute_calls is not None else []
        self.queries: list[tuple[str, tuple]] = []

    async def fetch(self, query, *args):
        self.queries.append((query.strip(), args))
        return self._fetch_rows

    async def execute(self, query, *args):
        self.queries.append((query.strip(), args))
        self._execute_calls.append((query.strip(), args))
        return "INSERT 0 1"


# ---------------------------------------------------------------------------
# SqlAssignedMemoryFetcher
# ---------------------------------------------------------------------------


class TestSqlAssignedMemoryFetcher:
    async def test_returns_memory_ids(self):
        mem_a, mem_b = uuid4(), uuid4()
        db = FakeDB(fetch_rows=[{"memory_id": mem_a}, {"memory_id": mem_b}])
        fetcher = SqlAssignedMemoryFetcher(db=db)

        result = await fetcher.fetch_assigned(UUID(int=1))

        assert result == {mem_a, mem_b}
        assert len(db.queries) == 1
        assert "member_memory_assignment" in db.queries[0][0]

    async def test_empty_assignment(self):
        db = FakeDB(fetch_rows=[])
        fetcher = SqlAssignedMemoryFetcher(db=db)
        assert await fetcher.fetch_assigned(UUID(int=1)) == set()


# ---------------------------------------------------------------------------
# SqlScopeMemoryFetcher
# ---------------------------------------------------------------------------


class TestSqlScopeMemoryFetcher:
    async def test_returns_scoped_ids(self):
        ids = [uuid4(), uuid4(), uuid4()]
        db = FakeDB(fetch_rows=[{"id": i} for i in ids])
        fetcher = SqlScopeMemoryFetcher(db=db)

        result = await fetcher.fetch_by_scope(
            project_ids=[UUID(int=10)], dept_id=UUID(int=20)
        )

        assert result == set(ids)
        query = db.queries[0][0]
        assert "scope_kind" in query

    async def test_none_dept_id(self):
        db = FakeDB(fetch_rows=[])
        fetcher = SqlScopeMemoryFetcher(db=db)
        result = await fetcher.fetch_by_scope(project_ids=[], dept_id=None)
        assert result == set()


# ---------------------------------------------------------------------------
# PgvectorTopKFetcher
# ---------------------------------------------------------------------------


class TestPgvectorTopKFetcher:
    async def test_returns_topk_ids(self):
        ids = [uuid4(), uuid4()]
        db = FakeDB(fetch_rows=[{"memory_id": i} for i in ids])
        fetcher = PgvectorTopKFetcher(db=db)

        result = await fetcher.fetch_vector_topk(embedding=[0.1] * 1536, k=50)

        assert result == set(ids)
        assert "memory_embedding" in db.queries[0][0]

    async def test_none_embedding_returns_empty(self):
        db = FakeDB()
        fetcher = PgvectorTopKFetcher(db=db)
        assert await fetcher.fetch_vector_topk(embedding=None, k=50) == set()

    async def test_empty_embedding_returns_empty(self):
        db = FakeDB()
        fetcher = PgvectorTopKFetcher(db=db)
        assert await fetcher.fetch_vector_topk(embedding=[], k=50) == set()


# ---------------------------------------------------------------------------
# SqlMemoryDetailFetcher
# ---------------------------------------------------------------------------


class TestSqlMemoryDetailFetcher:
    async def test_maps_to_candidates(self):
        mid = uuid4()
        db = FakeDB(
            fetch_rows=[
                {
                    "id": mid,
                    "title": "Test Memory",
                    "content": {"statement": "Hello world from test"},
                    "lifecycle_state": "active",
                    "confidence_value": "0.850",
                }
            ]
        )
        fetcher = SqlMemoryDetailFetcher(db=db)

        result = await fetcher.fetch_details({mid})

        assert len(result) == 1
        assert result[0].memory_id == mid
        assert result[0].title == "Test Memory"
        assert result[0].lifecycle_state == "active"
        assert result[0].confidence == 0.85
        assert result[0].tokens > 0

    async def test_empty_ids_returns_empty(self):
        db = FakeDB()
        fetcher = SqlMemoryDetailFetcher(db=db)
        assert await fetcher.fetch_details(set()) == []

    async def test_string_content_json_parsed(self):
        mid = uuid4()
        db = FakeDB(
            fetch_rows=[
                {
                    "id": mid,
                    "title": "JSON String",
                    "content": '{"statement": "parsed"}',
                    "lifecycle_state": "active",
                    "confidence_value": "0.500",
                }
            ]
        )
        fetcher = SqlMemoryDetailFetcher(db=db)
        result = await fetcher.fetch_details({mid})
        assert result[0].statement == "parsed"


# ---------------------------------------------------------------------------
# SqlRecallAuditLogger
# ---------------------------------------------------------------------------


class TestSqlRecallAuditLogger:
    async def test_inserts_audit_row(self):
        calls: list = []
        db = FakeDB(execute_calls=calls)
        logger_ = SqlRecallAuditLogger(db=db)

        from aiteamos_knowledge.application.recall_engine import RecallCandidate

        candidates = [
            RecallCandidate(
                memory_id=uuid4(), title="A", statement="s",
                lifecycle_state="active", confidence=0.5,
            ),
        ]
        await logger_.log_recall(
            snapshot_id=uuid4(), run_id=uuid4(), candidates=candidates
        )

        assert len(calls) == 1
        assert "recall_audit" in calls[0][0]

    async def test_none_snapshot_and_run(self):
        calls: list = []
        db = FakeDB(execute_calls=calls)
        logger_ = SqlRecallAuditLogger(db=db)
        await logger_.log_recall(snapshot_id=None, run_id=None, candidates=[])
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# SqlConflictChecker
# ---------------------------------------------------------------------------


class TestSqlConflictChecker:
    async def test_returns_conflicting_ids(self):
        mem_a, mem_b, mem_c = uuid4(), uuid4(), uuid4()
        db = FakeDB(
            fetch_rows=[
                {"memory_a_id": mem_a, "memory_b_id": mem_b},
                {"memory_a_id": mem_c, "memory_b_id": mem_a},
            ]
        )
        checker = SqlConflictChecker(db=db)

        result = await checker.get_unresolved_conflicts({mem_a, mem_b, mem_c})

        assert mem_a in result
        assert mem_b in result
        assert mem_c in result

    async def test_empty_ids_returns_empty(self):
        db = FakeDB()
        checker = SqlConflictChecker(db=db)
        assert await checker.get_unresolved_conflicts(set()) == set()

    async def test_no_conflicts(self):
        db = FakeDB(fetch_rows=[])
        checker = SqlConflictChecker(db=db)
        result = await checker.get_unresolved_conflicts({uuid4()})
        assert result == set()
