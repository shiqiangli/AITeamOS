"""
Knowledge Context — pgvector 投影消费者 (arch.md §2.5, 纪律 N6)。

消费 MemoryNodeUpdated 事件，生成 embedding 并 CAS 写入 memory_embedding 表。
source_event_seq 只进不退（不变量 N6）。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.projection import IdempotentProjectionConsumer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class EmbeddingGenerator(Protocol):
    """Embedding 生成接口（LLM embedding API 抽象）。

    测试中使用 mock 实现。
    """

    async def generate(self, text: str) -> list[float]: ...


class EmbeddingRepoLike(Protocol):
    """Embedding 仓储接口。"""

    async def upsert_embedding(
        self,
        *,
        memory_id: UUID,
        embedding: list[float],
        model_version: str,
        source_event_seq: int,
    ) -> bool:
        """CAS 写入 embedding。

        Returns True if written (seq advanced), False if skipped (seq not advanced).
        """
        ...

    async def get_current_seq(self, memory_id: UUID) -> int:
        """Get current source_event_seq for a memory_id."""
        ...


# ---------------------------------------------------------------------------
# PgvectorProjection
# ---------------------------------------------------------------------------


class PgvectorProjection(IdempotentProjectionConsumer):
    """pgvector 幂等投影消费者。

    消费 MemoryNodeUpdated 事件:
    1. 从事件中获取 Memory ID + 新版本号
    2. 获取 Memory 文本内容（通过 repo）
    3. 调用 EmbeddingGenerator 生成向量
    4. CAS 写入 memory_embedding 表（source_event_seq 只进不退）

    幂等性保障:
    - 继承 IdempotentProjectionConsumer 的 watermark 检查
    - 写入时使用 WHERE source_event_seq < EXCLUDED.source_event_seq
    """

    consumer_id: str = "pgvector-embedding-v1"

    UPSERT_SQL = """
        INSERT INTO memory_embedding (memory_id, embedding, model_version, source_event_seq, created_at)
        VALUES ($1, $2, $3, $4, now())
        ON CONFLICT (memory_id) DO UPDATE
        SET embedding = EXCLUDED.embedding,
            model_version = EXCLUDED.model_version,
            source_event_seq = EXCLUDED.source_event_seq
        WHERE memory_embedding.source_event_seq < EXCLUDED.source_event_seq
    """

    SELECT_CONTENT = """
        SELECT content FROM memory_node WHERE id = $1
    """

    def __init__(
        self,
        db: Any,
        *,
        embedding_generator: EmbeddingGenerator,
        model_version: str = "text-embedding-3-small",
    ):
        super().__init__(db)
        self._embedder = embedding_generator
        self._model_version = model_version

    async def handle_event(self, event: VersionedDomainEvent) -> None:
        """处理 MemoryNodeUpdated 事件 — 生成并写入 embedding。"""
        memory_id = getattr(event, "memory_id", None)
        if memory_id is None:
            logger.warning("PgvectorProjection: event missing memory_id, skipping")
            return

        # Fetch memory content
        row = await self._db.fetchrow(self.SELECT_CONTENT, memory_id)
        if row is None:
            logger.warning(
                "PgvectorProjection: memory %s not found, skipping", memory_id
            )
            return

        content = row["content"]
        if isinstance(content, str):
            import json
            content = json.loads(content)

        statement = content.get("statement", "") if isinstance(content, dict) else str(content)
        if not statement:
            logger.warning(
                "PgvectorProjection: memory %s has empty statement, skipping",
                memory_id,
            )
            return

        # Generate embedding
        embedding = await self._embedder.generate(statement)

        # CAS upsert — only advance source_event_seq
        await self._db.execute(
            self.UPSERT_SQL,
            memory_id,
            str(embedding),  # pgvector cast
            self._model_version,
            event.global_seq,
        )

        logger.debug(
            "PgvectorProjection: updated embedding for memory %s (seq=%d)",
            memory_id,
            event.global_seq,
        )


# ---------------------------------------------------------------------------
# In-memory implementation for testing
# ---------------------------------------------------------------------------


class InMemoryEmbeddingRepo:
    """In-memory embedding repo for testing."""

    def __init__(self):
        self._store: dict[UUID, dict[str, Any]] = {}

    async def upsert_embedding(
        self,
        *,
        memory_id: UUID,
        embedding: list[float],
        model_version: str,
        source_event_seq: int,
    ) -> bool:
        current = self._store.get(memory_id)
        if current and current["source_event_seq"] >= source_event_seq:
            return False  # CAS fail — seq not advanced
        self._store[memory_id] = {
            "embedding": embedding,
            "model_version": model_version,
            "source_event_seq": source_event_seq,
        }
        return True

    async def get_current_seq(self, memory_id: UUID) -> int:
        current = self._store.get(memory_id)
        return current["source_event_seq"] if current else 0
