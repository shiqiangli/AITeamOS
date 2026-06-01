"""
Workforce Context — 领域模型 (arch.md §2.2.3)。

聚合根:
- Member: 成员（AI/Human），组织归属，Skill/Memory 分配
- Department: 部门，负责人管理
- Project: 项目（经验生产场），关联 Repository + Harness + Members

值对象:
- MemberProfile, MemberHealthMetrics, ProjectStatus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

from aiteamos_shared.types import (
    DepartmentId,
    MemberId,
    MemberKind,
    MemoryId,
    ProjectId,
    SkillId,
    new_id,
)


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class ProjectStatus(StrEnum):
    """项目状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"
    PAUSED = "paused"


class TimeoutMode(StrEnum):
    """超时模式。"""

    NATURAL = "natural"
    BUSINESS_HOURS = "business_hours"


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemberProfile:
    """成员画像值对象。"""

    display_name: str = ""
    role: str = ""
    expertise_tags: list[str] = field(default_factory=list)
    bio: str = ""
    email: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "role": self.role,
            "expertise_tags": self.expertise_tags,
            "bio": self.bio,
            "email": self.email,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemberProfile:
        return cls(
            display_name=data.get("display_name", ""),
            role=data.get("role", ""),
            expertise_tags=data.get("expertise_tags", []),
            bio=data.get("bio", ""),
            email=data.get("email", ""),
        )


@dataclass(frozen=True)
class MemberHealthMetrics:
    """成员健康度指标。"""

    task_success_rate: float = 1.0
    active_tasks: int = 0
    total_completed: int = 0
    avg_response_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_success_rate": self.task_success_rate,
            "active_tasks": self.active_tasks,
            "total_completed": self.total_completed,
            "avg_response_time_seconds": self.avg_response_time_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemberHealthMetrics:
        if not data:
            return cls()
        return cls(
            task_success_rate=data.get("task_success_rate", 1.0),
            active_tasks=data.get("active_tasks", 0),
            total_completed=data.get("total_completed", 0),
            avg_response_time_seconds=data.get("avg_response_time_seconds", 0.0),
        )


# ---------------------------------------------------------------------------
# 聚合根 1: Department (arch.md §2.2.3)
# ---------------------------------------------------------------------------


class Department:
    """部门聚合根。"""

    def __init__(
        self,
        *,
        id: DepartmentId | None = None,
        name: str,
        leader_member_id: MemberId | None = None,
        backup_leader_member_id: MemberId | None = None,
        timeout_mode: TimeoutMode = TimeoutMode.NATURAL,
        timezone_str: str | None = None,
        created_at: datetime | None = None,
    ):
        self.id: DepartmentId = id or new_id()
        self.name = name
        self.leader_member_id = leader_member_id
        self.backup_leader_member_id = backup_leader_member_id
        self.timeout_mode = timeout_mode
        self.timezone_str = timezone_str
        self.created_at = created_at or datetime.now(timezone.utc)

        self._pending_events: list[Any] = []

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def _register_event(self, event: Any) -> None:
        self._pending_events.append(event)

    def update(
        self,
        *,
        name: str | None = None,
        leader_member_id: MemberId | None = None,
        backup_leader_member_id: MemberId | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if leader_member_id is not None:
            self.leader_member_id = leader_member_id
        if backup_leader_member_id is not None:
            self.backup_leader_member_id = backup_leader_member_id

        from . import events as evt

        self._register_event(
            evt.DepartmentUpdated(
                event_type="workforce.department.updated",
                department_id=self.id,
                name=self.name,
            )
        )

    def __repr__(self) -> str:
        return f"Department(id={self.id}, name={self.name!r})"


# ---------------------------------------------------------------------------
# 聚合根 2: Member (arch.md §2.2.3)
# ---------------------------------------------------------------------------


class Member:
    """成员聚合根。

    AI 受执行节点约束；Human 受时间约束。
    base_skill_set: 角色身份 Skill（持久）
    assigned_memories: 软性偏好分配
    """

    def __init__(
        self,
        *,
        id: MemberId | None = None,
        kind: MemberKind,
        department_id: DepartmentId,
        profile: MemberProfile | None = None,
        base_skill_set: list[SkillId] | None = None,
        assigned_memories: list[MemoryId] | None = None,
        health: MemberHealthMetrics | None = None,
        concurrency_limit: int = 1,
        prompt_template: str = "",
        created_at: datetime | None = None,
        archived_at: datetime | None = None,
    ):
        self.id: MemberId = id or new_id()
        self.kind = kind
        self.department_id = department_id
        self.profile = profile or MemberProfile()
        self.base_skill_set: list[SkillId] = base_skill_set or []
        self.assigned_memories: list[MemoryId] = assigned_memories or []
        self.health = health or MemberHealthMetrics()
        self.concurrency_limit = concurrency_limit
        self.prompt_template = prompt_template
        self.created_at = created_at or datetime.now(timezone.utc)
        self.archived_at = archived_at

        self._pending_events: list[Any] = []

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def _register_event(self, event: Any) -> None:
        self._pending_events.append(event)

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_available(self) -> bool:
        """成员是否可接受新任务。"""
        if self.is_archived:
            return False
        return self.health.active_tasks < self.concurrency_limit

    # -- 业务方法 --

    def update_profile(self, new_profile: MemberProfile) -> None:
        self.profile = new_profile
        from . import events as evt

        self._register_event(
            evt.MemberUpdated(
                event_type="workforce.member.updated",
                member_id=self.id,
                kind=self.kind,
            )
        )

    def set_concurrency_limit(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("concurrency_limit must be >= 1")
        self.concurrency_limit = limit
        from . import events as evt

        self._register_event(
            evt.MemberUpdated(
                event_type="workforce.member.updated",
                member_id=self.id,
                kind=self.kind,
            )
        )

    def assign_skill(self, skill_id: SkillId) -> None:
        if skill_id in self.base_skill_set:
            return
        self.base_skill_set.append(skill_id)
        from . import events as evt

        self._register_event(
            evt.SkillAssignedToMember(
                event_type="workforce.skill_assigned",
                member_id=self.id,
                skill_id=skill_id,
            )
        )

    def unassign_skill(self, skill_id: SkillId) -> bool:
        if skill_id not in self.base_skill_set:
            return False
        self.base_skill_set.remove(skill_id)
        from . import events as evt

        self._register_event(
            evt.SkillUnassignedFromMember(
                event_type="workforce.skill_unassigned",
                member_id=self.id,
                skill_id=skill_id,
            )
        )
        return True

    def assign_memory(self, memory_id: MemoryId) -> None:
        if memory_id in self.assigned_memories:
            return
        self.assigned_memories.append(memory_id)
        from . import events as evt

        self._register_event(
            evt.MemoryAssignedToMember(
                event_type="workforce.memory_assigned",
                member_id=self.id,
                memory_id=memory_id,
            )
        )

    def unassign_memory(self, memory_id: MemoryId) -> bool:
        if memory_id not in self.assigned_memories:
            return False
        self.assigned_memories.remove(memory_id)
        from . import events as evt

        self._register_event(
            evt.MemoryUnassignedFromMember(
                event_type="workforce.memory_unassigned",
                member_id=self.id,
                memory_id=memory_id,
            )
        )
        return True

    def archive(self) -> None:
        if self.is_archived:
            return
        self.archived_at = datetime.now(timezone.utc)
        from . import events as evt

        self._register_event(
            evt.MemberArchived(
                event_type="workforce.member.archived",
                member_id=self.id,
            )
        )

    def __repr__(self) -> str:
        return f"Member(id={self.id}, kind={self.kind}, dept={self.department_id})"


# ---------------------------------------------------------------------------
# 聚合根 3: Project (PRD §2.7: 经验生产场)
# ---------------------------------------------------------------------------


class Project:
    """项目聚合根 — 经验生产场。

    关联 Repository + Harness + Members。
    """

    def __init__(
        self,
        *,
        id: ProjectId | None = None,
        name: str,
        description: str = "",
        department_id: DepartmentId,
        repository_refs: list[str] | None = None,
        harness_config: dict[str, Any] | None = None,
        status: ProjectStatus = ProjectStatus.ACTIVE,
        member_ids: list[MemberId] | None = None,
        created_at: datetime | None = None,
        archived_at: datetime | None = None,
    ):
        self.id: ProjectId = id or new_id()
        self.name = name
        self.description = description
        self.department_id = department_id
        self.repository_refs: list[str] = repository_refs or []
        self.harness_config: dict[str, Any] = harness_config or {}
        self.status = status
        self.member_ids: list[MemberId] = member_ids or []
        self.created_at = created_at or datetime.now(timezone.utc)
        self.archived_at = archived_at

        self._pending_events: list[Any] = []

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def _register_event(self, event: Any) -> None:
        self._pending_events.append(event)

    @property
    def is_archived(self) -> bool:
        return self.status == ProjectStatus.ARCHIVED

    def update(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        repository_refs: list[str] | None = None,
        harness_config: dict[str, Any] | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if repository_refs is not None:
            self.repository_refs = repository_refs
        if harness_config is not None:
            self.harness_config = harness_config

        from . import events as evt

        self._register_event(
            evt.ProjectUpdated(
                event_type="workforce.project.updated",
                project_id=self.id,
                name=self.name,
            )
        )

    def assign_member(self, member_id: MemberId) -> None:
        if member_id in self.member_ids:
            return
        self.member_ids.append(member_id)
        from . import events as evt

        self._register_event(
            evt.MemberAssignedToProject(
                event_type="workforce.member_assigned_to_project",
                project_id=self.id,
                member_id=member_id,
            )
        )

    def unassign_member(self, member_id: MemberId) -> bool:
        if member_id not in self.member_ids:
            return False
        self.member_ids.remove(member_id)
        from . import events as evt

        self._register_event(
            evt.MemberUnassignedFromProject(
                event_type="workforce.member_unassigned_from_project",
                project_id=self.id,
                member_id=member_id,
            )
        )
        return True

    def archive(self) -> None:
        if self.is_archived:
            return
        self.status = ProjectStatus.ARCHIVED
        self.archived_at = datetime.now(timezone.utc)

        from . import events as evt

        self._register_event(
            evt.ProjectArchived(
                event_type="workforce.project.archived",
                project_id=self.id,
            )
        )

    def __repr__(self) -> str:
        return f"Project(id={self.id}, name={self.name!r}, status={self.status})"
