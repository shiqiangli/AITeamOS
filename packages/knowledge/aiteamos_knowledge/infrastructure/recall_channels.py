"""
Knowledge Context — Recall 通道 SQL 实现 (arch.md §2.5)。

每个类实现 recall_engine.py 中定义的 Protocol，
直接使用 asyncpg 执行 SQL，无额外抽象层。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from aiteamos_shared.types import MemoryId

from ..application.recall_engine import RecallCandidate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL Queries
# ---------------------------------------------------------------------------

_FETCH_ASSIGNED = """
    SELECT memory_id FROM member_memory_assignment
    WHERE member_id = $1
"""

_FETCH_BY_SCOPE = """
    SELECT id FROM memory_node
    WHERE lifecycle_state IN ('active', 'needs_verify')
      AND (
          (scope_kind = 'project' AND scope_ref = ANY($1))
          OR (scope_kind = 'department' AND scope_ref = $2)
          OR scope_kind = 'global'
      )
"""

_FETCH_VECTOR_TOPK = """
    SELECT memory_id FROM memory_embedding
    ORDER BY embedding <=> $1
    LIMIT $2
"""

_FETCH_DETAILS = """
    SELECT id, title, content, lifecycle_state, confidence_value
    FROM memory_node
    WHERE id = ANY($1)
      AND lifecycle_state IN ('active', 'needs_verify')
"""

_INSERT_AUDIT = """
    INSERT INTO recall_audit (snapshot_id, run_id, memory_ids)
    VALUES ($1, $2, $3)
"""

_FETCH_UNRESOLVED_CONFLICTS = """
    SELECT memory_a_id, memory_b_id FROM conflict_case
    WHERE resolved_at IS NULL
      AND (memory_a_id = ANY($1) OR memory_b_id = ANY($1))
"""


# ---------------------------------------------------------------------------
# Concrete implementations
# ---------------------------------------------------------------------------


class SqlAssignedMemoryFetcher:
    """获取显式分配给 Member 的 Memory。"""

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def fetch_assigned(self, member_id: UUID) -> set[MemoryId]:
        rows = await self._db.fetch(_FETCH_ASSIGNED, member_id)
        return {row["memory_id"] for row in rows}


class SqlScopeMemoryFetcher:
    """按作用域匹配 Memory。"""

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def fetch_by_scope(
        self, project_ids: list[UUID], dept_id: UUID | None
    ) -> set[MemoryId]:
        rows = await self._db.fetch(_FETCH_BY_SCOPE, project_ids, dept_id)
        return {row["id"] for row in rows}


class PgvectorTopKFetcher:
    """pgvector cosine distance top-K 语义搜索。"""

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def fetch_vector_topk(
        self, embedding: list[float] | None, k: int
    ) -> set[MemoryId]:
        if not embedding:
            return set()
        rows = await self._db.fetch(_FETCH_VECTOR_TOPK, embedding, k)
        return {row["memory_id"] for row in rows}


class SqlMemoryDetailFetcher:
    """批量获取 Memory 详情，映射为 RecallCandidate。"""

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def fetch_details(
        self, memory_ids: set[MemoryId]
    ) -> list[RecallCandidate]:
        if not memory_ids:
            return []
        rows = await self._db.fetch(_FETCH_DETAILS, list(memory_ids))
        results: list[RecallCandidate] = []
        for row in rows:
            content = row["content"]
            if isinstance(content, str):
                import json
                content = json.loads(content)
            statement = content.get("statement", "") if isinstance(content, dict) else ""
            results.append(
                RecallCandidate(
                    memory_id=row["id"],
                    title=row["title"],
                    statement=statement,
                    lifecycle_state=row["lifecycle_state"],
                    confidence=float(row["confidence_value"]),
                    tokens=len(statement) // 4,
                )
            )
        return results


class SqlRecallAuditLogger:
    """召回审计日志写入。"""

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def log_recall(
        self,
        snapshot_id: UUID | None,
        run_id: UUID | None,
        candidates: list[RecallCandidate],
    ) -> None:
        ids = [c.memory_id for c in candidates]
        await self._db.execute(_INSERT_AUDIT, snapshot_id, run_id, ids)


class SqlConflictChecker:
    """检查未解决的冲突。"""

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def get_unresolved_conflicts(
        self, memory_ids: set[MemoryId]
    ) -> set[MemoryId]:
        if not memory_ids:
            return set()
        rows = await self._db.fetch(
            _FETCH_UNRESOLVED_CONFLICTS, list(memory_ids)
        )
        result: set[MemoryId] = set()
        for row in rows:
            if row["memory_a_id"] in memory_ids:
                result.add(row["memory_a_id"])
            if row["memory_b_id"] in memory_ids:
                result.add(row["memory_b_id"])
        return result
