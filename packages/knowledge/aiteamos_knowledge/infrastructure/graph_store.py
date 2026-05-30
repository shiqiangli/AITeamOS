"""
Knowledge Context — SQL Graph Store (arch.md §2.6)。

基于 memory_edge 表的图存储实现，实现 GraphStoreLike Protocol。
支持 merge_edge (幂等写入)、remove_edge、bfs_neighbors。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from aiteamos_shared.types import MemoryId

logger = logging.getLogger(__name__)

# Default creator UUID (system) — used when no explicit creator is provided
_SYSTEM_CREATOR = UUID(int=0)


class SqlGraphStore:
    """memory_edge 表的图存储实现。"""

    _MERGE_EDGE = """
        INSERT INTO memory_edge (id, source_id, target_id, relation_type, weight, created_by)
        VALUES ($1, $2, $3, $4, 1.000, $5)
        ON CONFLICT (source_id, target_id, relation_type) DO NOTHING
    """

    _REMOVE_EDGE = """
        DELETE FROM memory_edge
        WHERE source_id = $1 AND target_id = $2 AND relation_type = $3
    """

    _BFS_NEIGHBORS = """
        WITH RECURSIVE traversal AS (
            SELECT target_id AS node_id, 1 AS hop
            FROM memory_edge
            WHERE source_id = ANY($1)
              AND ($3::text[] IS NULL OR relation_type = ANY($3))
            UNION
            SELECT e.target_id, t.hop + 1
            FROM memory_edge e
            JOIN traversal t ON e.source_id = t.node_id
            WHERE t.hop < $2
              AND ($3::text[] IS NULL OR e.relation_type = ANY($3))
        )
        SELECT DISTINCT node_id FROM traversal
        WHERE node_id != ALL($1)
    """

    def __init__(self, *, db: Any) -> None:
        self._db = db

    async def merge_edge(
        self,
        source_id: MemoryId,
        target_id: MemoryId,
        relation_type: str,
        *,
        tx: Any = None,
    ) -> None:
        executor = tx if tx else self._db
        await executor.execute(
            self._MERGE_EDGE,
            uuid4(),
            source_id,
            target_id,
            relation_type,
            _SYSTEM_CREATOR,
        )

    async def remove_edge(
        self,
        source_id: MemoryId,
        target_id: MemoryId,
        relation_type: str,
        *,
        tx: Any = None,
    ) -> None:
        executor = tx if tx else self._db
        await executor.execute(
            self._REMOVE_EDGE, source_id, target_id, relation_type
        )

    async def bfs_neighbors(
        self,
        seed_ids: set[MemoryId],
        depth: int,
        edge_types: set[str] | None = None,
        *,
        tx: Any = None,
    ) -> set[MemoryId]:
        if not seed_ids:
            return set()
        executor = tx if tx else self._db
        edge_types_list = list(edge_types) if edge_types else None
        rows = await executor.fetch(
            self._BFS_NEIGHBORS, list(seed_ids), depth, edge_types_list
        )
        return {row["node_id"] for row in rows}

    async def bfs_dependents(
        self,
        root_id: MemoryId,
        depth: int,
        fan_limit: int,
        *,
        tx: Any = None,
    ) -> set[MemoryId]:
        """反向 BFS: 找到依赖 root_id 的节点 (沿 target → source)。"""
        executor = tx if tx else self._db
        rows = await executor.fetch(
            """
            WITH RECURSIVE dependents AS (
                SELECT source_id AS node_id, 1 AS hop
                FROM memory_edge
                WHERE target_id = $1
                  AND relation_type IN ('depends', 'derived')
                LIMIT $3
                UNION
                SELECT e.source_id, d.hop + 1
                FROM memory_edge e
                JOIN dependents d ON e.target_id = d.node_id
                WHERE d.hop < $2
                  AND e.relation_type IN ('depends', 'derived')
                LIMIT $3
            )
            SELECT DISTINCT node_id FROM dependents
            WHERE node_id != $1
            """,
            root_id,
            depth,
            fan_limit,
        )
        return {row["node_id"] for row in rows}
