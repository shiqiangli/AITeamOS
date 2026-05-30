"""
Knowledge Context — PostgreSQL Repository 实现。

PostgresMemoryNodeRepository: MemoryNode 聚合根仓储
PostgresMemoryEdgeRepository: MemoryEdge 独立聚合根仓储
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from aiteamos_shared.repository import BaseRepository, DatabasePool
from aiteamos_shared.types import MemoryId, new_id

from ..domain.models import (
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
from ..application.queries import MemoryNodeDetail, MemoryNodeSummary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MemoryNode Repository
# ---------------------------------------------------------------------------


class PostgresMemoryNodeRepository(BaseRepository[MemoryNode]):
    """MemoryNode 聚合根的 PostgreSQL 仓储实现。"""

    # -- 写入 SQL --

    UPSERT_NODE = """
        INSERT INTO memory_node (
            id, tier, scope_kind, scope_ref, title, content,
            confidence_value, confidence_state, last_decay_at,
            lifecycle_state, provenance, current_version,
            created_at, last_used_at, expire_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6::jsonb,
            $7, $8, $9,
            $10, $11::jsonb, $12,
            $13, $14, $15
        )
        ON CONFLICT (id) DO UPDATE SET
            tier = EXCLUDED.tier,
            scope_kind = EXCLUDED.scope_kind,
            scope_ref = EXCLUDED.scope_ref,
            title = EXCLUDED.title,
            content = EXCLUDED.content,
            confidence_value = EXCLUDED.confidence_value,
            confidence_state = EXCLUDED.confidence_state,
            last_decay_at = EXCLUDED.last_decay_at,
            lifecycle_state = EXCLUDED.lifecycle_state,
            provenance = EXCLUDED.provenance,
            current_version = EXCLUDED.current_version,
            last_used_at = EXCLUDED.last_used_at,
            expire_at = EXCLUDED.expire_at
    """

    UPSERT_VERSION = """
        INSERT INTO memory_version (id, memory_id, version_no, diff, reason, author_member_id, created_at)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
        ON CONFLICT (memory_id, version_no) DO NOTHING
    """

    SELECT_NODE = """
        SELECT * FROM memory_node WHERE id = $1
    """

    SELECT_NODE_FOR_UPDATE = """
        SELECT * FROM memory_node WHERE id = $1 FOR UPDATE
    """

    SELECT_VERSIONS = """
        SELECT * FROM memory_version WHERE memory_id = $1 ORDER BY version_no
    """

    # -- 读取 SQL (CQRS read side) --

    LIST_NODES = """
        SELECT id, tier, title, lifecycle_state, confidence_value,
               scope_kind, content, current_version, created_at
        FROM memory_node
        WHERE ($1::text IS NULL OR tier = $1)
          AND ($2::text IS NULL OR scope_kind = $2)
          AND ($3::text IS NULL OR lifecycle_state = $3)
        ORDER BY created_at DESC
        OFFSET $4 LIMIT $5
    """

    SEARCH_NODES = """
        SELECT id, tier, title, lifecycle_state, confidence_value,
               scope_kind, content, current_version, created_at
        FROM memory_node
        WHERE ($1::text IS NULL OR title ILIKE '%' || $1 || '%'
               OR content::text ILIKE '%' || $1 || '%')
        ORDER BY created_at DESC
        LIMIT $2
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> MemoryNode | None:
        """加载 MemoryNode 聚合（含版本列表）。"""
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT_NODE, id)
        if row is None:
            return None

        # 加载版本
        versions_rows = await executor.fetch(self.SELECT_VERSIONS, id)
        versions = [self._row_to_version(vr) for vr in versions_rows]

        return self._row_to_node(row, versions)

    async def lock_for_update(self, id: Any, *, tx: Any) -> MemoryNode | None:
        """FOR UPDATE 行锁加载。"""
        row = await tx.fetchrow(self.SELECT_NODE_FOR_UPDATE, id)
        if row is None:
            return None

        versions_rows = await tx.fetch(self.SELECT_VERSIONS, id)
        versions = [self._row_to_version(vr) for vr in versions_rows]

        return self._row_to_node(row, versions)

    async def save(self, aggregate: MemoryNode, *, tx: Any = None) -> None:
        """持久化 MemoryNode 聚合。"""
        executor = tx if tx else self._db

        content_dict = aggregate.content.to_dict()
        provenance_dict = {
            "source_kind": aggregate.provenance.source_kind.value,
            "task_id": str(aggregate.provenance.task_id) if aggregate.provenance.task_id else None,
            "run_id": str(aggregate.provenance.run_id) if aggregate.provenance.run_id else None,
            "member_id": str(aggregate.provenance.member_id) if aggregate.provenance.member_id else None,
            "system_meta": aggregate.provenance.system_meta,
        }

        await executor.execute(
            self.UPSERT_NODE,
            aggregate.id,
            aggregate.tier.value,
            aggregate.scope.kind.value,
            aggregate.scope.ref,
            aggregate.title,
            json.dumps(content_dict),
            aggregate.confidence.value,
            aggregate.confidence.state.value,
            aggregate.confidence.last_decay_at,
            aggregate.lifecycle.value,
            json.dumps(provenance_dict),
            aggregate.current_version,
            aggregate.created_at,
            aggregate.last_used_at,
            aggregate.expire_at,
        )

        # 保存版本
        for version in aggregate.versions:
            await executor.execute(
                self.UPSERT_VERSION,
                version.id,
                aggregate.id,
                version.version_no,
                json.dumps(version.diff),
                version.reason,
                version.author_member_id,
                version.created_at,
            )

    # -- Read-Side (CQRS) --

    async def list_nodes(
        self,
        *,
        tier: str | None = None,
        scope_kind: str | None = None,
        lifecycle: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[MemoryNodeSummary]:
        rows = await self._db.fetch(
            self.LIST_NODES, tier, scope_kind, lifecycle, offset, limit
        )
        return [self._row_to_summary(r) for r in rows]

    async def get_detail(self, memory_id: MemoryId) -> MemoryNodeDetail | None:
        node = await self.get_by_id(memory_id)
        if node is None:
            return None

        versions = [
            {
                "version_no": v.version_no,
                "diff": v.diff,
                "reason": v.reason,
                "author_member_id": str(v.author_member_id),
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in node.versions
        ]
        return MemoryNodeDetail(node=node, versions=versions)

    async def search_by_keyword(
        self,
        *,
        keyword: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[MemoryNodeSummary]:
        rows = await self._db.fetch(self.SEARCH_NODES, keyword, limit)
        summaries = [self._row_to_summary(r) for r in rows]

        # 标签过滤（在应用层做，数据量大时应走 pgvector 投影）
        if tags:
            tag_set = set(tags)
            summaries = [
                s for s in summaries if tag_set.intersection(set(s.tags))
            ]

        return summaries

    # -- Row Mapping --

    @staticmethod
    def _row_to_node(row: Any, versions: list[MemoryVersion]) -> MemoryNode:
        content_data = row["content"]
        if isinstance(content_data, str):
            content_data = json.loads(content_data)
        content = MemoryContent.from_dict(content_data)

        prov_data = row["provenance"]
        if isinstance(prov_data, str):
            prov_data = json.loads(prov_data)
        provenance = Provenance(
            source_kind=SourceKind(prov_data.get("source_kind", "manual_input")),
            task_id=prov_data.get("task_id"),
            run_id=prov_data.get("run_id"),
            member_id=prov_data.get("member_id"),
            system_meta=prov_data.get("system_meta", False),
        )

        confidence = Confidence(
            value=Decimal(str(row["confidence_value"])),
            state=ConfidenceState(row["confidence_state"]),
            last_updated=row["created_at"],
            last_decay_at=row["last_decay_at"],
        )

        scope = Scope(
            kind=ScopeKind(row["scope_kind"]),
            ref=row.get("scope_ref"),
        )

        return MemoryNode(
            id=row["id"],
            tier=Tier(row["tier"]),
            scope=scope,
            title=row["title"],
            content=content,
            confidence=confidence,
            provenance=provenance,
            lifecycle=LifecycleState(row["lifecycle_state"]),
            versions=versions,
            current_version=row["current_version"],
            created_at=row["created_at"],
            last_used_at=row.get("last_used_at"),
            expire_at=row.get("expire_at"),
        )

    @staticmethod
    def _row_to_version(row: Any) -> MemoryVersion:
        diff_data = row["diff"]
        if isinstance(diff_data, str):
            diff_data = json.loads(diff_data)
        return MemoryVersion(
            id=row["id"],
            version_no=row["version_no"],
            diff=diff_data,
            reason=row["reason"],
            author_member_id=row["author_member_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_summary(row: Any) -> MemoryNodeSummary:
        content_data = row["content"]
        if isinstance(content_data, str):
            content_data = json.loads(content_data)
        tags = content_data.get("tags", []) if isinstance(content_data, dict) else []

        return MemoryNodeSummary(
            id=row["id"],
            tier=row["tier"],
            title=row["title"],
            lifecycle_state=row["lifecycle_state"],
            confidence_value=float(row["confidence_value"]),
            scope_kind=row["scope_kind"],
            tags=tags,
            current_version=row["current_version"],
            created_at=row["created_at"],
        )

    # -- Cascade invalidation support --

    _FIND_BY_ANCHORS = """
        SELECT id FROM memory_node
        WHERE tier = 'facts'
          AND content::text LIKE ANY(
              SELECT '%' || unnest($1::text[]) || '%'
          )
    """

    _SET_NEEDS_VERIFY = """
        UPDATE memory_node
        SET lifecycle_state = 'needs_verify', updated_at = now()
        WHERE id = $1
    """

    # -- Expired candidate query (for auto-approval) --

    _FIND_EXPIRED_CANDIDATES = """
        SELECT mn.*, 
               (SELECT array_agg(row_to_json(mv)) 
                FROM memory_version mv WHERE mv.memory_id = mn.id) as _versions
        FROM memory_node mn
        WHERE lifecycle_state = 'candidate'
          AND created_at < $1
        ORDER BY created_at ASC
    """

    async def find_candidates_older_than(
        self, cutoff: Any, *, tx: Any = None,
    ) -> list:
        """Find candidate MemoryNodes older than cutoff datetime."""
        executor = tx if tx else self._db
        rows = await executor.fetch(self._FIND_EXPIRED_CANDIDATES, cutoff)
        results = []
        for row in rows:
            # Load versions for each node
            versions_rows = await executor.fetch(self.SELECT_VERSIONS, row["id"])
            versions = [self._row_to_version(vr) for vr in versions_rows]
            results.append(self._row_to_node(row, versions))
        return results

    async def find_facts_with_anchors(
        self, anchors: list[str], *, tx: Any = None
    ) -> list[Any]:
        """查找锚点匹配的 Facts 节点 ID。"""
        executor = tx if tx else self._db
        rows = await executor.fetch(self._FIND_BY_ANCHORS, anchors)
        return [row["id"] for row in rows]

    async def set_needs_verify(self, memory_id: Any, *, tx: Any = None) -> None:
        """将 Memory 状态设为 needs_verify。"""
        executor = tx if tx else self._db
        await executor.execute(self._SET_NEEDS_VERIFY, memory_id)


# ---------------------------------------------------------------------------
# MemoryEdge Repository
# ---------------------------------------------------------------------------


class PostgresMemoryEdgeRepository(BaseRepository[MemoryEdge]):
    """MemoryEdge 独立聚合根的 PostgreSQL 仓储实现。

    I-K-5: Edge CRUD 不需要锁定 source/target MemoryNode。
    """

    UPSERT_EDGE = """
        INSERT INTO memory_edge (id, source_id, target_id, relation_type, weight, created_by, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (id) DO UPDATE SET
            weight = EXCLUDED.weight
    """

    SELECT_EDGE = """
        SELECT * FROM memory_edge WHERE id = $1
    """

    DELETE_EDGE = """
        DELETE FROM memory_edge WHERE id = $1
    """

    SELECT_EDGES_BY_SOURCE = """
        SELECT * FROM memory_edge WHERE source_id = $1 ORDER BY created_at
    """

    SELECT_EDGES_BY_TARGET = """
        SELECT * FROM memory_edge WHERE target_id = $1 ORDER BY created_at
    """

    async def get_by_id(self, id: Any, *, tx: Any = None) -> MemoryEdge | None:
        executor = tx if tx else self._db
        row = await executor.fetchrow(self.SELECT_EDGE, id)
        if row is None:
            return None
        return self._row_to_edge(row)

    async def save(self, aggregate: MemoryEdge, *, tx: Any = None) -> None:
        executor = tx if tx else self._db
        await executor.execute(
            self.UPSERT_EDGE,
            aggregate.edge_id,
            aggregate.source_id,
            aggregate.target_id,
            aggregate.relation_type.value,
            aggregate.weight,
            aggregate.created_by,
            aggregate.created_at,
        )

    async def delete(self, edge_id: UUID, *, tx: Any = None) -> None:
        executor = tx if tx else self._db
        await executor.execute(self.DELETE_EDGE, edge_id)

    async def get_by_source(self, source_id: MemoryId, *, tx: Any = None) -> list[MemoryEdge]:
        executor = tx if tx else self._db
        rows = await executor.fetch(self.SELECT_EDGES_BY_SOURCE, source_id)
        return [self._row_to_edge(r) for r in rows]

    async def get_by_target(self, target_id: MemoryId, *, tx: Any = None) -> list[MemoryEdge]:
        executor = tx if tx else self._db
        rows = await executor.fetch(self.SELECT_EDGES_BY_TARGET, target_id)
        return [self._row_to_edge(r) for r in rows]

    @staticmethod
    def _row_to_edge(row: Any) -> MemoryEdge:
        return MemoryEdge(
            edge_id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relation_type=RelationType(row["relation_type"]),
            weight=Decimal(str(row["weight"])) if row["weight"] is not None else Decimal("1.000"),
            created_by=row["created_by"],
            created_at=row["created_at"],
        )
