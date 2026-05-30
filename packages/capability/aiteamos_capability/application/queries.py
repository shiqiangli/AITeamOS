"""
Capability Context — Queries (CQRS read side)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from aiteamos_shared.types import SkillId

from ..domain.models import SkillStatus


# ---------------------------------------------------------------------------
# Query Results
# ---------------------------------------------------------------------------


@dataclass
class SkillSummary:
    """Skill 列表摘要。"""

    id: SkillId
    name: str
    version: str
    description: str
    domain: str
    status: str
    circuit_state: str
    capability_tags: list[str]
    created_at: Any


@dataclass
class SkillDetail:
    """Skill 详情。"""

    id: SkillId
    name: str
    version: str
    description: str
    domain: str
    status: str
    circuit_state: str
    inputs: list[str]
    outputs: list[str]
    preconditions: list[str]
    side_effects: list[dict[str, str]]
    required_permissions: list[str]
    capability_tags: list[str]
    examples: list[str]
    references: list[str]
    quality_signals: dict[str, Any]
    manifest: dict[str, Any]
    health: dict[str, Any]
    created_at: Any


# ---------------------------------------------------------------------------
# Read-Side Repository Protocol
# ---------------------------------------------------------------------------


class SkillReadRepoLike(Protocol):
    async def list_skills(
        self,
        *,
        status: str | None = None,
        name_filter: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SkillSummary]: ...

    async def get_detail(self, skill_id: SkillId) -> SkillDetail | None: ...

    async def search_by_tag(
        self, *, tags: list[str], limit: int = 20
    ) -> list[SkillSummary]: ...


# ---------------------------------------------------------------------------
# Query Executors
# ---------------------------------------------------------------------------


class ListSkillsExecutor:
    """执行 ListSkillsQuery。"""

    def __init__(self, *, read_repo: SkillReadRepoLike):
        self._repo = read_repo

    async def execute(
        self, query: "ListSkillsQuery"
    ) -> list[SkillSummary]:
        return await self._repo.list_skills(
            status=query.status.value if query.status else None,
            name_filter=query.name_filter,
            offset=query.offset,
            limit=query.limit,
        )


class GetSkillDetailExecutor:
    """执行 GetSkillDetailQuery。"""

    def __init__(self, *, read_repo: SkillReadRepoLike):
        self._repo = read_repo

    async def execute(
        self, query: "GetSkillDetailQuery"
    ) -> SkillDetail | None:
        return await self._repo.get_detail(query.skill_id)


class SearchSkillsByTagExecutor:
    """执行 SearchSkillsByTagQuery。"""

    def __init__(self, *, read_repo: SkillReadRepoLike):
        self._repo = read_repo

    async def execute(
        self, query: "SearchSkillsByTagQuery"
    ) -> list[SkillSummary]:
        return await self._repo.search_by_tag(
            tags=query.tags, limit=query.limit
        )


# Import commands for type annotations
from .commands import GetSkillDetailQuery, ListSkillsQuery, SearchSkillsByTagQuery
