"""
Workforce Context — 应用层测试。

验证标准 (plan.md §1.4):
- Member 创建/归属 Department 流程
- Project 创建/归档/成员分配流程
- Skill/Memory 分配与取消分配
- 并发上限配置生效
- Outbox 事件正确写入
"""

import pytest
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

from aiteamos_shared.types import DepartmentId, MemberId, MemberKind, ProjectId, new_id
from aiteamos_workforce.domain.models import (
    Department,
    Member,
    MemberHealthMetrics,
    MemberProfile,
    Project,
    ProjectStatus,
)
from aiteamos_workforce.application.commands import (
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
from aiteamos_workforce.application.handlers import (
    ArchiveMemberHandler,
    ArchiveProjectHandler,
    AssignMemberToProjectHandler,
    AssignMemoryToMemberHandler,
    AssignSkillToMemberHandler,
    CreateDepartmentHandler,
    CreateMemberHandler,
    CreateProjectHandler,
    SetConcurrencyLimitHandler,
    UpdateDepartmentHandler,
    UpdateMemberHandler,
    UpdateProjectHandler,
)
from aiteamos_workforce.application.queries import (
    DepartmentSummary,
    ListDepartmentsExecutor,
    ListMembersExecutor,
    ListProjectsExecutor,
    MemberSummary,
    ProjectSummary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_tx_manager():
    """Create a mock transaction manager that yields an AsyncMock."""
    tx_mock = AsyncMock()

    @asynccontextmanager
    async def _tx():
        yield tx_mock

    mgr = MagicMock()
    mgr.transaction = _tx
    return mgr, tx_mock


def _make_publisher():
    return AsyncMock()


def _make_repo():
    repo = AsyncMock()
    return repo


# ---------------------------------------------------------------------------
# Department Handler Tests
# ---------------------------------------------------------------------------


class TestCreateDepartmentHandler:
    async def test_create_department(self):
        repo = _make_repo()
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = CreateDepartmentHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = CreateDepartmentCommand(name="Engineering")
        dept = await handler.handle(cmd)

        assert dept.name == "Engineering"
        repo.save.assert_awaited_once()
        pub.publish_events.assert_awaited_once()

    async def test_create_department_with_leaders(self):
        repo = _make_repo()
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = CreateDepartmentHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        leader = new_id()
        cmd = CreateDepartmentCommand(name="Ops", leader_member_id=leader)
        dept = await handler.handle(cmd)

        assert dept.leader_member_id == leader


class TestUpdateDepartmentHandler:
    async def test_update_department(self):
        dept = Department(name="Old")
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=dept)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = UpdateDepartmentHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = UpdateDepartmentCommand(department_id=dept.id, name="New")
        result = await handler.handle(cmd)

        assert result.name == "New"

    async def test_update_nonexistent_department(self):
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=None)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = UpdateDepartmentHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = UpdateDepartmentCommand(department_id=new_id(), name="X")
        with pytest.raises(ValueError, match="not found"):
            await handler.handle(cmd)


# ---------------------------------------------------------------------------
# Member Handler Tests
# ---------------------------------------------------------------------------


class TestCreateMemberHandler:
    async def test_create_ai_member(self):
        repo = _make_repo()
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = CreateMemberHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        dept_id = new_id()
        cmd = CreateMemberCommand(kind=MemberKind.AI, department_id=dept_id, display_name="Bot")
        member = await handler.handle(cmd)

        assert member.kind == MemberKind.AI
        assert member.department_id == dept_id
        repo.save.assert_awaited_once()
        pub.publish_events.assert_awaited_once()

    async def test_create_human_member(self):
        repo = _make_repo()
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = CreateMemberHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = CreateMemberCommand(kind=MemberKind.HUMAN, department_id=new_id())
        member = await handler.handle(cmd)
        assert member.kind == MemberKind.HUMAN


class TestUpdateMemberHandler:
    async def test_update_member(self):
        member = Member(kind=MemberKind.AI, department_id=new_id(), profile=MemberProfile(display_name="Old"))
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=member)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = UpdateMemberHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = UpdateMemberCommand(member_id=member.id, display_name="New")
        result = await handler.handle(cmd)
        assert result.profile.display_name == "New"

    async def test_update_nonexistent_member(self):
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=None)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = UpdateMemberHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = UpdateMemberCommand(member_id=new_id())
        with pytest.raises(ValueError, match="not found"):
            await handler.handle(cmd)


class TestArchiveMemberHandler:
    async def test_archive_member(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=member)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = ArchiveMemberHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = ArchiveMemberCommand(member_id=member.id)
        result = await handler.handle(cmd)
        assert result.is_archived is True


class TestSetConcurrencyLimitHandler:
    async def test_set_concurrency_limit(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=member)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = SetConcurrencyLimitHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = SetConcurrencyLimitCommand(member_id=member.id, limit=5)
        result = await handler.handle(cmd)
        assert result.concurrency_limit == 5


class TestAssignSkillHandler:
    async def test_assign_skill(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=member)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = AssignSkillToMemberHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        skill_id = new_id()
        cmd = AssignSkillToMemberCommand(member_id=member.id, skill_id=skill_id)
        result = await handler.handle(cmd)
        assert skill_id in result.base_skill_set


class TestAssignMemoryHandler:
    async def test_assign_memory(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=member)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = AssignMemoryToMemberHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        memory_id = new_id()
        cmd = AssignMemoryToMemberCommand(member_id=member.id, memory_id=memory_id)
        result = await handler.handle(cmd)
        assert memory_id in result.assigned_memories


# ---------------------------------------------------------------------------
# Project Handler Tests
# ---------------------------------------------------------------------------


class TestCreateProjectHandler:
    async def test_create_project(self):
        repo = _make_repo()
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = CreateProjectHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        dept_id = new_id()
        cmd = CreateProjectCommand(name="Alpha", description="Test", department_id=dept_id)
        project = await handler.handle(cmd)

        assert project.name == "Alpha"
        assert project.department_id == dept_id
        repo.save.assert_awaited_once()
        pub.publish_events.assert_awaited_once()


class TestUpdateProjectHandler:
    async def test_update_project(self):
        project = Project(name="Old", department_id=new_id())
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=project)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = UpdateProjectHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = UpdateProjectCommand(project_id=project.id, name="New")
        result = await handler.handle(cmd)
        assert result.name == "New"


class TestArchiveProjectHandler:
    async def test_archive_project(self):
        project = Project(name="Temp", department_id=new_id())
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=project)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = ArchiveProjectHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        cmd = ArchiveProjectCommand(project_id=project.id)
        result = await handler.handle(cmd)
        assert result.status == ProjectStatus.ARCHIVED


class TestAssignMemberToProjectHandler:
    async def test_assign_member(self):
        project = Project(name="Team", department_id=new_id())
        repo = _make_repo()
        repo.lock_for_update = AsyncMock(return_value=project)
        tx_mgr, tx = _make_tx_manager()
        pub = _make_publisher()
        handler = AssignMemberToProjectHandler(repo=repo, tx_manager=tx_mgr, event_publisher=pub)

        member_id = new_id()
        cmd = AssignMemberToProjectCommand(project_id=project.id, member_id=member_id)
        result = await handler.handle(cmd)
        assert member_id in result.member_ids


# ---------------------------------------------------------------------------
# Query Executor Tests
# ---------------------------------------------------------------------------


class TestListMembersExecutor:
    async def test_list_members(self):
        summaries = [
            MemberSummary(
                id=new_id(), kind="ai", display_name="Bot",
                department_id=str(new_id()), concurrency_limit=3,
                is_archived=False, created_at=None,
            )
        ]
        read_repo = AsyncMock()
        read_repo.list_members = AsyncMock(return_value=summaries)
        executor = ListMembersExecutor(read_repo=read_repo)

        from aiteamos_workforce.application.commands import ListMembersQuery

        result = await executor.execute(ListMembersQuery())
        assert len(result) == 1
        assert result[0].display_name == "Bot"


class TestListDepartmentsExecutor:
    async def test_list_departments(self):
        summaries = [
            DepartmentSummary(
                id=new_id(), name="Eng",
                leader_member_id=None, created_at=None,
            )
        ]
        read_repo = AsyncMock()
        read_repo.list_departments = AsyncMock(return_value=summaries)
        executor = ListDepartmentsExecutor(read_repo=read_repo)

        from aiteamos_workforce.application.commands import ListDepartmentsQuery

        result = await executor.execute(ListDepartmentsQuery())
        assert len(result) == 1


class TestListProjectsExecutor:
    async def test_list_projects(self):
        summaries = [
            ProjectSummary(
                id=new_id(), name="Alpha",
                department_id=str(new_id()), status="active",
                member_count=3, created_at=None,
            )
        ]
        read_repo = AsyncMock()
        read_repo.list_projects = AsyncMock(return_value=summaries)
        executor = ListProjectsExecutor(read_repo=read_repo)

        from aiteamos_workforce.application.commands import ListProjectsQuery

        result = await executor.execute(ListProjectsQuery())
        assert len(result) == 1
