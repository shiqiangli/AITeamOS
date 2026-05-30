"""
pgvector 投影 — 测试 (plan.md §2.2 验证标准)。

验证标准:
- pgvector 投影幂等（重复事件不覆盖新数据）
- source_event_seq 只进不退 (N6)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from aiteamos_knowledge.domain.events import MemoryNodeUpdated
from aiteamos_knowledge.infrastructure.pgvector_projection import (
    InMemoryEmbeddingRepo,
    PgvectorProjection,
)


# ---------------------------------------------------------------------------
# Mock embedding generator
# ---------------------------------------------------------------------------


class MockEmbeddingGenerator:
    """Deterministic mock embedding generator."""

    def __init__(self, dim: int = 8):
        self._dim = dim
        self.call_count = 0
        self.last_text: str = ""

    async def generate(self, text: str) -> list[float]:
        self.call_count += 1
        self.last_text = text
        # Deterministic pseudo-embedding based on text hash
        h = hash(text) % (10**6)
        return [float(h % 100) / 100.0] * self._dim


# ---------------------------------------------------------------------------
# Fake DB for PgvectorProjection
# ---------------------------------------------------------------------------


class FakeDB:
    """Fake async DB that stores memory_node content and embedding rows."""

    def __init__(self):
        self._nodes: dict[UUID, dict] = {}
        self._embeddings: dict[UUID, dict] = {}
        self._watermarks: dict[str, dict] = {}

    def add_node(self, memory_id: UUID, content: dict) -> None:
        self._nodes[memory_id] = {"content": json.dumps(content)}

    async def fetchrow(self, query: str, *args: Any) -> Any:
        # Handle SELECT_CONTENT
        if "memory_node" in query and "SELECT" in query.upper():
            mid = args[0]
            return self._nodes.get(mid)
        # Handle GET_WATERMARK
        if "projection_watermark" in query and "SELECT" in query.upper():
            cid = args[0]
            return self._watermarks.get(cid)
        return None

    async def execute(self, query: str, *args: Any) -> Any:
        # Handle UPSERT embedding
        if "memory_embedding" in query and "INSERT" in query.upper():
            mid, embedding_str, model_version, seq = args[0], args[1], args[2], args[3]
            current = self._embeddings.get(mid)
            if current and current["source_event_seq"] >= seq:
                return  # CAS: don't overwrite with older seq
            self._embeddings[mid] = {
                "embedding": embedding_str,
                "model_version": model_version,
                "source_event_seq": seq,
            }
            return
        # Handle CAS_ADVANCE watermark
        if "projection_watermark" in query and "INSERT" in query.upper():
            cid, event_id, seq = args[0], args[1], args[2]
            current = self._watermarks.get(cid)
            if current and current["last_seq"] >= seq:
                return
            self._watermarks[cid] = {
                "last_event_id": event_id,
                "last_seq": seq,
                "processed_at": "now()",
            }
            return


# ===========================================================================
# §1: PgvectorProjection 幂等性
# ===========================================================================


class TestPgvectorProjection:
    """pgvector 投影幂等性测试。"""

    @pytest.fixture
    def embedder(self):
        return MockEmbeddingGenerator()

    @pytest.fixture
    def db(self):
        return FakeDB()

    @pytest.fixture
    def projection(self, db, embedder):
        return PgvectorProjection(db, embedding_generator=embedder)

    def _make_event(self, memory_id: UUID, seq: int) -> MemoryNodeUpdated:
        evt = MemoryNodeUpdated(
            event_type="knowledge.memory_node.updated",
            memory_id=memory_id,
            new_version=2,
            reason="test update",
        )
        evt.global_seq = seq
        return evt

    @pytest.mark.asyncio
    async def test_processes_event(self, projection, db, embedder):
        """Normal event → embedding generated and stored."""
        mid = uuid4()
        db.add_node(mid, {"statement": "Python is great"})

        evt = self._make_event(mid, seq=10)
        result = await projection.consume(evt)

        assert result is True
        assert embedder.call_count == 1
        assert embedder.last_text == "Python is great"
        assert mid in db._embeddings
        assert db._embeddings[mid]["source_event_seq"] == 10

    @pytest.mark.asyncio
    async def test_duplicate_event_skipped(self, projection, db, embedder):
        """Duplicate event (seq <= watermark) → skipped, no new embedding."""
        mid = uuid4()
        db.add_node(mid, {"statement": "Test"})

        evt1 = self._make_event(mid, seq=10)
        await projection.consume(evt1)
        assert embedder.call_count == 1

        # Same event again
        evt2 = self._make_event(mid, seq=10)
        result = await projection.consume(evt2)
        assert result is False
        assert embedder.call_count == 1  # not called again

    @pytest.mark.asyncio
    async def test_older_event_skipped(self, projection, db, embedder):
        """Older event (seq < watermark) → skipped (N6: seq only advances)."""
        mid = uuid4()
        db.add_node(mid, {"statement": "Test"})

        evt_new = self._make_event(mid, seq=20)
        await projection.consume(evt_new)

        evt_old = self._make_event(mid, seq=5)
        result = await projection.consume(evt_old)
        assert result is False
        assert db._embeddings[mid]["source_event_seq"] == 20  # unchanged

    @pytest.mark.asyncio
    async def test_newer_event_advances_seq(self, projection, db, embedder):
        """Newer event (seq > watermark) → processed, seq advances."""
        mid = uuid4()
        db.add_node(mid, {"statement": "Version 1"})

        evt1 = self._make_event(mid, seq=10)
        await projection.consume(evt1)
        assert db._embeddings[mid]["source_event_seq"] == 10

        # Update content
        db.add_node(mid, {"statement": "Version 2"})

        evt2 = self._make_event(mid, seq=20)
        result = await projection.consume(evt2)
        assert result is True
        assert db._embeddings[mid]["source_event_seq"] == 20
        assert embedder.call_count == 2
        assert embedder.last_text == "Version 2"

    @pytest.mark.asyncio
    async def test_missing_memory_skipped(self, projection, embedder):
        """Event for nonexistent memory → gracefully skipped."""
        mid = uuid4()
        evt = self._make_event(mid, seq=10)
        # Don't add node to DB
        result = await projection.consume(evt)
        assert result is True  # consumed (watermark advanced) but no embedding
        assert embedder.call_count == 0

    @pytest.mark.asyncio
    async def test_empty_statement_skipped(self, projection, db, embedder):
        """Memory with empty statement → no embedding generated."""
        mid = uuid4()
        db.add_node(mid, {"statement": ""})

        evt = self._make_event(mid, seq=10)
        result = await projection.consume(evt)
        assert result is True
        assert embedder.call_count == 0


# ===========================================================================
# §2: InMemoryEmbeddingRepo CAS
# ===========================================================================


class TestInMemoryEmbeddingRepo:
    """InMemoryEmbeddingRepo CAS 行为测试。"""

    @pytest.mark.asyncio
    async def test_upsert_new(self):
        repo = InMemoryEmbeddingRepo()
        mid = uuid4()
        ok = await repo.upsert_embedding(
            memory_id=mid,
            embedding=[0.1, 0.2],
            model_version="v1",
            source_event_seq=5,
        )
        assert ok is True
        assert await repo.get_current_seq(mid) == 5

    @pytest.mark.asyncio
    async def test_cas_advance(self):
        repo = InMemoryEmbeddingRepo()
        mid = uuid4()
        await repo.upsert_embedding(
            memory_id=mid, embedding=[0.1], model_version="v1", source_event_seq=5
        )
        ok = await repo.upsert_embedding(
            memory_id=mid, embedding=[0.2], model_version="v1", source_event_seq=10
        )
        assert ok is True
        assert await repo.get_current_seq(mid) == 10

    @pytest.mark.asyncio
    async def test_cas_reject_older(self):
        repo = InMemoryEmbeddingRepo()
        mid = uuid4()
        await repo.upsert_embedding(
            memory_id=mid, embedding=[0.1], model_version="v1", source_event_seq=10
        )
        ok = await repo.upsert_embedding(
            memory_id=mid, embedding=[0.2], model_version="v1", source_event_seq=5
        )
        assert ok is False
        assert await repo.get_current_seq(mid) == 10  # unchanged

    @pytest.mark.asyncio
    async def test_cas_reject_same(self):
        repo = InMemoryEmbeddingRepo()
        mid = uuid4()
        await repo.upsert_embedding(
            memory_id=mid, embedding=[0.1], model_version="v1", source_event_seq=10
        )
        ok = await repo.upsert_embedding(
            memory_id=mid, embedding=[0.2], model_version="v1", source_event_seq=10
        )
        assert ok is False
