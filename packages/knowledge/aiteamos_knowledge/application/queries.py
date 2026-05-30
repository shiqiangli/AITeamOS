"""
Knowledge Context — Queries (CQRS read side).

只读查询，不修改聚合状态。
直接走 PostgreSQL 读路径，不经过 Outbox。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from aiteamos_shared.types import MemoryId

from ..domain.models import LifecycleState, MemoryNode, ScopeKind, Tier


# ---------------------------------------------------------------------------
# Query Definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ListMemoryNodesQuery:
    """分页 + 筛选的 Memory 列表查询。"""

    tier: Tier | None = None
    scope_kind: ScopeKind | None = None
    lifecycle: LifecycleState | None = None
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True)
class GetMemoryNodeDetailQuery:
    """单条 Memory 详情 + 版本历史。"""

    memory_id: MemoryId


@dataclass(frozen=True)
class SearchMemoryByKeywordQuery:
    """关键词 + 标签检索。"""

    keyword: str | None = None
    tags: list[str] = field(default_factory=list)
    limit: int = 20


# ---------------------------------------------------------------------------
# Query Results
# ---------------------------------------------------------------------------


@dataclass
class MemoryNodeSummary:
    """Memory 列表摘要。"""

    id: MemoryId
    tier: str
    title: str
    lifecycle_state: str
    confidence_value: float
    scope_kind: str
    tags: list[str]
    current_version: int
    created_at: Any


@dataclass
class MemoryNodeDetail:
    """Memory 详情（含版本历史）。"""

    node: MemoryNode
    versions: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Read-Side Repository Protocol
# ---------------------------------------------------------------------------


class MemoryNodeReadRepoLike(Protocol):
    """Read-side repository protocol for queries."""

    async def list_nodes(
        self,
        *,
        tier: str | None = None,
        scope_kind: str | None = None,
        lifecycle: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[MemoryNodeSummary]: ...

    async def get_detail(self, memory_id: MemoryId) -> MemoryNodeDetail | None: ...

    async def search_by_keyword(
        self,
        *,
        keyword: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[MemoryNodeSummary]: ...


# ---------------------------------------------------------------------------
# Query Executors
# ---------------------------------------------------------------------------


class ListMemoryNodesExecutor:
    """执行 ListMemoryNodesQuery。"""

    def __init__(self, *, read_repo: MemoryNodeReadRepoLike):
        self._repo = read_repo

    async def execute(self, query: ListMemoryNodesQuery) -> list[MemoryNodeSummary]:
        return await self._repo.list_nodes(
            tier=query.tier.value if query.tier else None,
            scope_kind=query.scope_kind.value if query.scope_kind else None,
            lifecycle=query.lifecycle.value if query.lifecycle else None,
            offset=query.offset,
            limit=query.limit,
        )


class GetMemoryNodeDetailExecutor:
    """执行 GetMemoryNodeDetailQuery。"""

    def __init__(self, *, read_repo: MemoryNodeReadRepoLike):
        self._repo = read_repo

    async def execute(self, query: GetMemoryNodeDetailQuery) -> MemoryNodeDetail | None:
        return await self._repo.get_detail(query.memory_id)


class SearchMemoryByKeywordExecutor:
    """执行 SearchMemoryByKeywordQuery。"""

    def __init__(self, *, read_repo: MemoryNodeReadRepoLike):
        self._repo = read_repo

    async def execute(
        self, query: SearchMemoryByKeywordQuery
    ) -> list[MemoryNodeSummary]:
        return await self._repo.search_by_keyword(
            keyword=query.keyword,
            tags=query.tags,
            limit=query.limit,
        )
