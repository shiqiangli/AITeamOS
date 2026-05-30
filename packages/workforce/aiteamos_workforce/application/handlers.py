"""
Workforce Context — Command Handlers (CQRS write side)。
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from aiteamos_shared.types import DepartmentId, MemberId, MemberKind, ProjectId, new_id

from ..domain.events import (
    DepartmentCreated,
    MemberAssignedToProject,
    MemberCreated,
    ProjectCreated,
)
from ..domain.models import (
    Department,
    Member,
    MemberHealthMetrics,
    MemberProfile,
    Project,
    ProjectStatus,
)
from .commands import (
    ArchiveMemberCommand,
    ArchiveProjectCommand,
    AssignMemberToProjectCommand,
    AssignMemoryToMemberCommand,
    AssignSkillToMemberCommand,
    CreateDepartmentCommand,
    CreateMemberCommand,
    CreateProjectCommand,
    SetConcurrencyLimitCommand,
    UpdateDepartmentCommand,
    UpdateMemberCommand,
    UpdateProjectCommand,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class RepoLike(Protocol):
    async def get_by_id(self, id: Any, *, tx: Any = None) -> Any: ...
    async def save(self, aggregate: Any, *, tx: Any = None) -> None: ...
    async def lock_for_update(self, id: Any, *, tx: Any) -> Any: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


# ---------------------------------------------------------------------------
# Department Handlers
# ---------------------------------------------------------------------------


class CreateDepartmentHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: CreateDepartmentCommand) -> Department:
        dept = Department(
            name=cmd.name,
            leader_member_id=cmd.leader_member_id,
            backup_leader_member_id=cmd.backup_leader_member_id,
        )
        evt = DepartmentCreated(
            event_type="workforce.department.created",
            department_id=dept.id,
            name=dept.name,
        )
        async with self._tx.transaction() as tx:
            await self._repo.save(dept, tx=tx)
            all_events = [evt] + dept.pending_events
            dept.clear_pending_events()
            await self._publisher.publish_events(all_events, partition_key=str(dept.id), tx=tx)
        return dept


class UpdateDepartmentHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: UpdateDepartmentCommand) -> Department:
        async with self._tx.transaction() as tx:
            dept = await self._repo.lock_for_update(cmd.department_id, tx=tx)
            if dept is None:
                raise ValueError(f"Department {cmd.department_id} not found")
            dept.update(
                name=cmd.name,
                leader_member_id=cmd.leader_member_id,
                backup_leader_member_id=cmd.backup_leader_member_id,
            )
            await self._repo.save(dept, tx=tx)
            events = dept.pending_events
            dept.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(dept.id), tx=tx)
        return dept


# ---------------------------------------------------------------------------
# Member Handlers
# ---------------------------------------------------------------------------


class CreateMemberHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: CreateMemberCommand) -> Member:
        profile = MemberProfile(display_name=cmd.display_name, role=cmd.role)
        member = Member(
            kind=cmd.kind,
            department_id=cmd.department_id,
            profile=profile,
            concurrency_limit=cmd.concurrency_limit,
        )
        evt = MemberCreated(
            event_type="workforce.member.created",
            member_id=member.id,
            kind=member.kind,
            department_id=member.department_id,
        )
        async with self._tx.transaction() as tx:
            await self._repo.save(member, tx=tx)
            all_events = [evt] + member.pending_events
            member.clear_pending_events()
            await self._publisher.publish_events(all_events, partition_key=str(member.id), tx=tx)
        return member


class UpdateMemberHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: UpdateMemberCommand) -> Member:
        async with self._tx.transaction() as tx:
            member = await self._repo.lock_for_update(cmd.member_id, tx=tx)
            if member is None:
                raise ValueError(f"Member {cmd.member_id} not found")
            new_profile = MemberProfile(
                display_name=cmd.display_name or member.profile.display_name,
                role=cmd.role or member.profile.role,
                expertise_tags=member.profile.expertise_tags,
                bio=member.profile.bio,
                email=member.profile.email,
            )
            member.update_profile(new_profile)
            await self._repo.save(member, tx=tx)
            events = member.pending_events
            member.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(member.id), tx=tx)
        return member


class ArchiveMemberHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: ArchiveMemberCommand) -> Member:
        async with self._tx.transaction() as tx:
            member = await self._repo.lock_for_update(cmd.member_id, tx=tx)
            if member is None:
                raise ValueError(f"Member {cmd.member_id} not found")
            member.archive()
            await self._repo.save(member, tx=tx)
            events = member.pending_events
            member.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(member.id), tx=tx)
        return member


class SetConcurrencyLimitHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: SetConcurrencyLimitCommand) -> Member:
        async with self._tx.transaction() as tx:
            member = await self._repo.lock_for_update(cmd.member_id, tx=tx)
            if member is None:
                raise ValueError(f"Member {cmd.member_id} not found")
            member.set_concurrency_limit(cmd.limit)
            await self._repo.save(member, tx=tx)
            events = member.pending_events
            member.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(member.id), tx=tx)
        return member


class AssignSkillToMemberHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: AssignSkillToMemberCommand) -> Member:
        async with self._tx.transaction() as tx:
            member = await self._repo.lock_for_update(cmd.member_id, tx=tx)
            if member is None:
                raise ValueError(f"Member {cmd.member_id} not found")
            member.assign_skill(cmd.skill_id)
            await self._repo.save(member, tx=tx)
            events = member.pending_events
            member.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(member.id), tx=tx)
        return member


class AssignMemoryToMemberHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: AssignMemoryToMemberCommand) -> Member:
        async with self._tx.transaction() as tx:
            member = await self._repo.lock_for_update(cmd.member_id, tx=tx)
            if member is None:
                raise ValueError(f"Member {cmd.member_id} not found")
            member.assign_memory(cmd.memory_id)
            await self._repo.save(member, tx=tx)
            events = member.pending_events
            member.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(member.id), tx=tx)
        return member


# ---------------------------------------------------------------------------
# Project Handlers
# ---------------------------------------------------------------------------


class CreateProjectHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: CreateProjectCommand) -> Project:
        project = Project(
            name=cmd.name,
            description=cmd.description,
            department_id=cmd.department_id,
            repository_refs=cmd.repository_refs,
        )
        evt = ProjectCreated(
            event_type="workforce.project.created",
            project_id=project.id,
            name=project.name,
            department_id=project.department_id,
        )
        async with self._tx.transaction() as tx:
            await self._repo.save(project, tx=tx)
            all_events = [evt] + project.pending_events
            project.clear_pending_events()
            await self._publisher.publish_events(all_events, partition_key=str(project.id), tx=tx)
        return project


class UpdateProjectHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: UpdateProjectCommand) -> Project:
        async with self._tx.transaction() as tx:
            project = await self._repo.lock_for_update(cmd.project_id, tx=tx)
            if project is None:
                raise ValueError(f"Project {cmd.project_id} not found")
            project.update(
                name=cmd.name,
                description=cmd.description,
                repository_refs=cmd.repository_refs,
            )
            await self._repo.save(project, tx=tx)
            events = project.pending_events
            project.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(project.id), tx=tx)
        return project


class ArchiveProjectHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: ArchiveProjectCommand) -> Project:
        async with self._tx.transaction() as tx:
            project = await self._repo.lock_for_update(cmd.project_id, tx=tx)
            if project is None:
                raise ValueError(f"Project {cmd.project_id} not found")
            project.archive()
            await self._repo.save(project, tx=tx)
            events = project.pending_events
            project.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(project.id), tx=tx)
        return project


class AssignMemberToProjectHandler:
    def __init__(self, *, repo: RepoLike, tx_manager: TransactionManagerLike, event_publisher: EventPublisherLike):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: AssignMemberToProjectCommand) -> Project:
        async with self._tx.transaction() as tx:
            project = await self._repo.lock_for_update(cmd.project_id, tx=tx)
            if project is None:
                raise ValueError(f"Project {cmd.project_id} not found")
            project.assign_member(cmd.member_id)
            await self._repo.save(project, tx=tx)
            events = project.pending_events
            project.clear_pending_events()
            await self._publisher.publish_events(events, partition_key=str(project.id), tx=tx)
        return project
