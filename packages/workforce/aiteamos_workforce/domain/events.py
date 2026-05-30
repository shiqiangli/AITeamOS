"""
Workforce Context — 领域事件 (arch.md §2.2.3)。
"""

from __future__ import annotations

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.types import DepartmentId, MemberId, MemberKind, MemoryId, ProjectId, SkillId


# ---------------------------------------------------------------------------
# Member 事件
# ---------------------------------------------------------------------------


class MemberCreated(VersionedDomainEvent):
    event_type: str = "workforce.member.created"
    member_id: MemberId
    kind: MemberKind
    department_id: DepartmentId


class MemberUpdated(VersionedDomainEvent):
    event_type: str = "workforce.member.updated"
    member_id: MemberId
    kind: MemberKind


class MemberArchived(VersionedDomainEvent):
    event_type: str = "workforce.member.archived"
    member_id: MemberId


# ---------------------------------------------------------------------------
# Department 事件
# ---------------------------------------------------------------------------


class DepartmentCreated(VersionedDomainEvent):
    event_type: str = "workforce.department.created"
    department_id: DepartmentId
    name: str


class DepartmentUpdated(VersionedDomainEvent):
    event_type: str = "workforce.department.updated"
    department_id: DepartmentId
    name: str


# ---------------------------------------------------------------------------
# Project 事件
# ---------------------------------------------------------------------------


class ProjectCreated(VersionedDomainEvent):
    event_type: str = "workforce.project.created"
    project_id: ProjectId
    name: str
    department_id: DepartmentId


class ProjectUpdated(VersionedDomainEvent):
    event_type: str = "workforce.project.updated"
    project_id: ProjectId
    name: str


class ProjectArchived(VersionedDomainEvent):
    event_type: str = "workforce.project.archived"
    project_id: ProjectId


# ---------------------------------------------------------------------------
# 分配事件
# ---------------------------------------------------------------------------


class SkillAssignedToMember(VersionedDomainEvent):
    event_type: str = "workforce.skill_assigned"
    member_id: MemberId
    skill_id: SkillId


class MemoryAssignedToMember(VersionedDomainEvent):
    event_type: str = "workforce.memory_assigned"
    member_id: MemberId
    memory_id: MemoryId


class MemberAssignedToProject(VersionedDomainEvent):
    event_type: str = "workforce.member_assigned_to_project"
    project_id: ProjectId
    member_id: MemberId


# ---------------------------------------------------------------------------
# 取消分配事件
# ---------------------------------------------------------------------------


class SkillUnassignedFromMember(VersionedDomainEvent):
    event_type: str = "workforce.skill_unassigned"
    member_id: MemberId
    skill_id: SkillId


class MemoryUnassignedFromMember(VersionedDomainEvent):
    event_type: str = "workforce.memory_unassigned"
    member_id: MemberId
    memory_id: MemoryId


class MemberUnassignedFromProject(VersionedDomainEvent):
    event_type: str = "workforce.member_unassigned_from_project"
    project_id: ProjectId
    member_id: MemberId
