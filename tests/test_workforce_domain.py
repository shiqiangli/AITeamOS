"""
Workforce Context — 领域模型测试。

验证标准 (plan.md §1.4):
- Member 创建/归属 Department 流程
- Project 创建/归档/成员分配流程
- Skill/Memory 分配与取消分配
- 并发上限配置生效
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from aiteamos_shared.types import (
    DepartmentId,
    MemberId,
    MemberKind,
    MemoryId,
    ProjectId,
    SkillId,
    new_id,
)
from aiteamos_workforce.domain.models import (
    Department,
    Member,
    MemberHealthMetrics,
    MemberProfile,
    Project,
    ProjectStatus,
    TimeoutMode,
)
from aiteamos_workforce.domain.events import (
    DepartmentCreated,
    DepartmentUpdated,
    MemberArchived,
    MemberAssignedToProject,
    MemberCreated,
    MemberUpdated,
    MemoryAssignedToMember,
    ProjectArchived,
    ProjectCreated,
    ProjectUpdated,
    SkillAssignedToMember,
)


# ---------------------------------------------------------------------------
# Department Tests
# ---------------------------------------------------------------------------


class TestDepartment:
    """Department 聚合根测试。"""

    def test_create_department(self):
        dept = Department(name="Engineering")
        assert dept.name == "Engineering"
        assert dept.id is not None
        assert dept.leader_member_id is None
        assert dept.backup_leader_member_id is None
        assert dept.created_at is not None

    def test_create_department_with_leaders(self):
        leader = new_id()
        backup = new_id()
        dept = Department(name="Ops", leader_member_id=leader, backup_leader_member_id=backup)
        assert dept.leader_member_id == leader
        assert dept.backup_leader_member_id == backup

    def test_update_department_name(self):
        dept = Department(name="Old")
        dept.update(name="New")
        assert dept.name == "New"
        assert len(dept.pending_events) == 1
        assert dept.pending_events[0].event_type == "workforce.department.updated"

    def test_update_department_leaders(self):
        dept = Department(name="Team")
        new_leader = new_id()
        dept.update(leader_member_id=new_leader)
        assert dept.leader_member_id == new_leader

    def test_clear_pending_events(self):
        dept = Department(name="Team")
        dept.update(name="Updated")
        assert len(dept.pending_events) > 0
        dept.clear_pending_events()
        assert len(dept.pending_events) == 0

    def test_department_repr(self):
        dept = Department(name="Eng")
        assert "Eng" in repr(dept)


# ---------------------------------------------------------------------------
# Member Tests
# ---------------------------------------------------------------------------


class TestMember:
    """Member 聚合根测试。"""

    def test_create_ai_member(self):
        dept_id = new_id()
        member = Member(kind=MemberKind.AI, department_id=dept_id)
        assert member.kind == MemberKind.AI
        assert member.department_id == dept_id
        assert member.id is not None
        assert member.is_archived is False
        assert member.is_available is True
        assert member.concurrency_limit == 1

    def test_create_human_member(self):
        dept_id = new_id()
        profile = MemberProfile(display_name="Alice")
        member = Member(kind=MemberKind.HUMAN, department_id=dept_id, profile=profile)
        assert member.kind == MemberKind.HUMAN
        assert member.profile.display_name == "Alice"

    def test_create_member_with_profile(self):
        profile = MemberProfile(
            display_name="Bot-1",
            role="developer",
            expertise_tags=["python", "ddd"],
            bio="AI developer",
            email="bot@aiteam.os",
        )
        member = Member(kind=MemberKind.AI, department_id=new_id(), profile=profile)
        assert member.profile.display_name == "Bot-1"
        assert member.profile.role == "developer"
        assert "python" in member.profile.expertise_tags

    def test_update_profile(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        new_profile = MemberProfile(display_name="Updated", role="lead")
        member.update_profile(new_profile)
        assert member.profile.display_name == "Updated"
        assert member.profile.role == "lead"
        assert len(member.pending_events) == 1
        assert member.pending_events[0].event_type == "workforce.member.updated"

    def test_archive_member(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        assert member.is_archived is False
        member.archive()
        assert member.is_archived is True
        assert member.archived_at is not None
        assert len(member.pending_events) == 1
        assert member.pending_events[0].event_type == "workforce.member.archived"

    def test_archive_already_archived(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        member.archive()
        events_count = len(member.pending_events)
        member.archive()  # idempotent
        assert len(member.pending_events) == events_count

    def test_member_not_available_when_archived(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        member.archive()
        assert member.is_available is False

    def test_member_repr(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        assert "Member" in repr(member)


# ---------------------------------------------------------------------------
# Concurrency Tests
# ---------------------------------------------------------------------------


class TestConcurrencyLimit:
    """并发上限配置测试。"""

    def test_default_concurrency_limit(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        assert member.concurrency_limit == 1

    def test_set_concurrency_limit(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        member.set_concurrency_limit(5)
        assert member.concurrency_limit == 5
        assert len(member.pending_events) == 1

    def test_set_invalid_concurrency_limit(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        with pytest.raises(ValueError, match="concurrency_limit must be >= 1"):
            member.set_concurrency_limit(0)

    def test_availability_respects_concurrency(self):
        member = Member(kind=MemberKind.AI, department_id=new_id(), concurrency_limit=2)
        assert member.is_available is True

        # Simulate active tasks via health metrics
        member.health = MemberHealthMetrics(active_tasks=2)
        assert member.is_available is False

        member.health = MemberHealthMetrics(active_tasks=1)
        assert member.is_available is True


# ---------------------------------------------------------------------------
# Skill Assignment Tests
# ---------------------------------------------------------------------------


class TestSkillAssignment:
    """Skill 分配与取消分配测试。"""

    def test_assign_skill(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        skill_id = new_id()
        member.assign_skill(skill_id)
        assert skill_id in member.base_skill_set
        assert len(member.pending_events) == 1
        assert member.pending_events[0].event_type == "workforce.skill_assigned"

    def test_assign_duplicate_skill_is_idempotent(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        skill_id = new_id()
        member.assign_skill(skill_id)
        member.assign_skill(skill_id)  # duplicate
        assert len(member.base_skill_set) == 1
        assert len(member.pending_events) == 1  # only first event

    def test_unassign_skill(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        skill_id = new_id()
        member.assign_skill(skill_id)
        result = member.unassign_skill(skill_id)
        assert result is True
        assert skill_id not in member.base_skill_set

    def test_unassign_nonexistent_skill(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        result = member.unassign_skill(new_id())
        assert result is False


# ---------------------------------------------------------------------------
# Memory Assignment Tests
# ---------------------------------------------------------------------------


class TestMemoryAssignment:
    """Memory 分配与取消分配测试。"""

    def test_assign_memory(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        memory_id = new_id()
        member.assign_memory(memory_id)
        assert memory_id in member.assigned_memories
        assert len(member.pending_events) == 1
        assert member.pending_events[0].event_type == "workforce.memory_assigned"

    def test_assign_duplicate_memory_is_idempotent(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        memory_id = new_id()
        member.assign_memory(memory_id)
        member.assign_memory(memory_id)
        assert len(member.assigned_memories) == 1

    def test_unassign_memory(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        memory_id = new_id()
        member.assign_memory(memory_id)
        result = member.unassign_memory(memory_id)
        assert result is True
        assert memory_id not in member.assigned_memories

    def test_unassign_nonexistent_memory(self):
        member = Member(kind=MemberKind.AI, department_id=new_id())
        result = member.unassign_memory(new_id())
        assert result is False


# ---------------------------------------------------------------------------
# Project Tests
# ---------------------------------------------------------------------------


class TestProject:
    """Project 聚合根测试。"""

    def test_create_project(self):
        dept_id = new_id()
        project = Project(name="Alpha", description="Test project", department_id=dept_id)
        assert project.name == "Alpha"
        assert project.department_id == dept_id
        assert project.status == ProjectStatus.ACTIVE
        assert project.is_archived is False

    def test_create_project_with_refs(self):
        project = Project(
            name="Beta",
            department_id=new_id(),
            repository_refs=["github.com/org/repo"],
            harness_config={"adapter": "git"},
        )
        assert "github.com/org/repo" in project.repository_refs
        assert project.harness_config["adapter"] == "git"

    def test_update_project(self):
        project = Project(name="Old", department_id=new_id())
        project.update(name="New", description="Updated")
        assert project.name == "New"
        assert project.description == "Updated"
        assert len(project.pending_events) == 1
        assert project.pending_events[0].event_type == "workforce.project.updated"

    def test_archive_project(self):
        project = Project(name="Temp", department_id=new_id())
        project.archive()
        assert project.status == ProjectStatus.ARCHIVED
        assert project.is_archived is True
        assert project.archived_at is not None
        assert len(project.pending_events) == 1
        assert project.pending_events[0].event_type == "workforce.project.archived"

    def test_archive_already_archived(self):
        project = Project(name="Temp", department_id=new_id())
        project.archive()
        events_count = len(project.pending_events)
        project.archive()  # idempotent
        assert len(project.pending_events) == events_count

    def test_assign_member_to_project(self):
        project = Project(name="Team", department_id=new_id())
        member_id = new_id()
        project.assign_member(member_id)
        assert member_id in project.member_ids
        assert len(project.pending_events) == 1
        assert project.pending_events[0].event_type == "workforce.member_assigned_to_project"

    def test_assign_duplicate_member(self):
        project = Project(name="Team", department_id=new_id())
        member_id = new_id()
        project.assign_member(member_id)
        project.assign_member(member_id)
        assert len(project.member_ids) == 1

    def test_unassign_member(self):
        project = Project(name="Team", department_id=new_id())
        member_id = new_id()
        project.assign_member(member_id)
        result = project.unassign_member(member_id)
        assert result is True
        assert member_id not in project.member_ids

    def test_unassign_nonexistent_member(self):
        project = Project(name="Team", department_id=new_id())
        result = project.unassign_member(new_id())
        assert result is False

    def test_project_repr(self):
        project = Project(name="Alpha", department_id=new_id())
        assert "Alpha" in repr(project)


# ---------------------------------------------------------------------------
# Value Object Tests
# ---------------------------------------------------------------------------


class TestMemberProfile:
    """MemberProfile 值对象测试。"""

    def test_default_profile(self):
        profile = MemberProfile()
        assert profile.display_name == ""
        assert profile.role == ""
        assert profile.expertise_tags == []

    def test_profile_to_dict_roundtrip(self):
        profile = MemberProfile(
            display_name="Bot",
            role="dev",
            expertise_tags=["python"],
            bio="AI dev",
            email="bot@test.com",
        )
        d = profile.to_dict()
        restored = MemberProfile.from_dict(d)
        assert restored.display_name == profile.display_name
        assert restored.role == profile.role
        assert restored.expertise_tags == profile.expertise_tags

    def test_from_dict_empty(self):
        profile = MemberProfile.from_dict({})
        assert profile.display_name == ""


class TestMemberHealthMetrics:
    """MemberHealthMetrics 值对象测试。"""

    def test_default_health(self):
        health = MemberHealthMetrics()
        assert health.task_success_rate == 1.0
        assert health.active_tasks == 0

    def test_health_to_dict_roundtrip(self):
        health = MemberHealthMetrics(
            task_success_rate=0.95,
            active_tasks=3,
            total_completed=50,
            avg_response_time_seconds=1.5,
        )
        d = health.to_dict()
        restored = MemberHealthMetrics.from_dict(d)
        assert restored.task_success_rate == health.task_success_rate
        assert restored.active_tasks == health.active_tasks

    def test_from_dict_empty(self):
        health = MemberHealthMetrics.from_dict({})
        assert health.task_success_rate == 1.0


# ---------------------------------------------------------------------------
# Events Tests
# ---------------------------------------------------------------------------


class TestWorkforceEvents:
    """领域事件结构测试。"""

    def test_member_created_event(self):
        evt = MemberCreated(
            event_type="workforce.member.created",
            member_id=new_id(),
            kind="ai",
            department_id=new_id(),
        )
        assert evt.event_type == "workforce.member.created"
        assert evt.member_id is not None

    def test_department_created_event(self):
        evt = DepartmentCreated(
            event_type="workforce.department.created",
            department_id=new_id(),
            name="Eng",
        )
        assert evt.event_type == "workforce.department.created"

    def test_project_created_event(self):
        evt = ProjectCreated(
            event_type="workforce.project.created",
            project_id=new_id(),
            name="Alpha",
            department_id=new_id(),
        )
        assert evt.event_type == "workforce.project.created"

    def test_skill_assigned_event(self):
        evt = SkillAssignedToMember(
            event_type="workforce.skill_assigned",
            member_id=new_id(),
            skill_id=new_id(),
        )
        assert evt.event_type == "workforce.skill_assigned"

    def test_member_assigned_to_project_event(self):
        evt = MemberAssignedToProject(
            event_type="workforce.member_assigned_to_project",
            project_id=new_id(),
            member_id=new_id(),
        )
        assert evt.event_type == "workforce.member_assigned_to_project"
