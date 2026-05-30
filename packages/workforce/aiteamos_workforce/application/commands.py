"""
Workforce Context — Application Commands + Queries (CQRS)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from aiteamos_shared.types import DepartmentId, MemberId, MemberKind, MemoryId, ProjectId, SkillId


# ---------------------------------------------------------------------------
# Department Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateDepartmentCommand:
    name: str
    leader_member_id: MemberId | None = None
    backup_leader_member_id: MemberId | None = None


@dataclass(frozen=True)
class UpdateDepartmentCommand:
    department_id: DepartmentId
    name: str | None = None
    leader_member_id: MemberId | None = None
    backup_leader_member_id: MemberId | None = None


# ---------------------------------------------------------------------------
# Member Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateMemberCommand:
    kind: MemberKind
    department_id: DepartmentId
    display_name: str = ""
    role: str = ""
    concurrency_limit: int = 1


@dataclass(frozen=True)
class UpdateMemberCommand:
    member_id: MemberId
    display_name: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class ArchiveMemberCommand:
    member_id: MemberId


@dataclass(frozen=True)
class SetConcurrencyLimitCommand:
    member_id: MemberId
    limit: int


@dataclass(frozen=True)
class AssignSkillToMemberCommand:
    member_id: MemberId
    skill_id: SkillId


@dataclass(frozen=True)
class AssignMemoryToMemberCommand:
    member_id: MemberId
    memory_id: MemoryId


# ---------------------------------------------------------------------------
# Project Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateProjectCommand:
    name: str
    description: str
    department_id: DepartmentId
    repository_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UpdateProjectCommand:
    project_id: ProjectId
    name: str | None = None
    description: str | None = None
    repository_refs: list[str] | None = None


@dataclass(frozen=True)
class ArchiveProjectCommand:
    project_id: ProjectId


@dataclass(frozen=True)
class AssignMemberToProjectCommand:
    project_id: ProjectId
    member_id: MemberId


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ListMembersQuery:
    department_id: DepartmentId | None = None
    kind: MemberKind | None = None
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True)
class GetMemberDetailQuery:
    member_id: MemberId


@dataclass(frozen=True)
class ListProjectsQuery:
    department_id: DepartmentId | None = None
    status: str | None = None
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True)
class ListDepartmentsQuery:
    offset: int = 0
    limit: int = 50
