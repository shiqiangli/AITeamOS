"""
Workforce Context — Queries (CQRS read side)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from aiteamos_shared.types import DepartmentId, MemberId, ProjectId


# ---------------------------------------------------------------------------
# Query Results
# ---------------------------------------------------------------------------


@dataclass
class MemberSummary:
    id: MemberId
    kind: str
    display_name: str
    role: str | None
    department_id: str
    concurrency_limit: int
    is_archived: bool
    created_at: Any


@dataclass
class DepartmentSummary:
    id: DepartmentId
    name: str
    leader_member_id: str | None
    created_at: Any


@dataclass
class ProjectSummary:
    id: ProjectId
    name: str
    department_id: str
    status: str
    member_count: int
    created_at: Any


# ---------------------------------------------------------------------------
# Read-Side Repository Protocols
# ---------------------------------------------------------------------------


class MemberReadRepoLike(Protocol):
    async def list_members(
        self, *, department_id: str | None = None, kind: str | None = None,
        offset: int = 0, limit: int = 50,
    ) -> list[MemberSummary]: ...


class DepartmentReadRepoLike(Protocol):
    async def list_departments(self, *, offset: int = 0, limit: int = 50) -> list[DepartmentSummary]: ...


class ProjectReadRepoLike(Protocol):
    async def list_projects(
        self, *, department_id: str | None = None, status: str | None = None,
        offset: int = 0, limit: int = 50,
    ) -> list[ProjectSummary]: ...


# ---------------------------------------------------------------------------
# Query Executors
# ---------------------------------------------------------------------------


class ListMembersExecutor:
    def __init__(self, *, read_repo: MemberReadRepoLike):
        self._repo = read_repo

    async def execute(self, query: "ListMembersQuery") -> list[MemberSummary]:
        return await self._repo.list_members(
            department_id=str(query.department_id) if query.department_id else None,
            kind=query.kind.value if query.kind else None,
            offset=query.offset,
            limit=query.limit,
        )


class ListDepartmentsExecutor:
    def __init__(self, *, read_repo: DepartmentReadRepoLike):
        self._repo = read_repo

    async def execute(self, query: "ListDepartmentsQuery") -> list[DepartmentSummary]:
        return await self._repo.list_departments(offset=query.offset, limit=query.limit)


class ListProjectsExecutor:
    def __init__(self, *, read_repo: ProjectReadRepoLike):
        self._repo = read_repo

    async def execute(self, query: "ListProjectsQuery") -> list[ProjectSummary]:
        return await self._repo.list_projects(
            department_id=str(query.department_id) if query.department_id else None,
            status=query.status,
            offset=query.offset,
            limit=query.limit,
        )


# Import for type annotations
from .commands import ListDepartmentsQuery, ListMembersQuery, ListProjectsQuery
