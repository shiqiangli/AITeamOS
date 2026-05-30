"""
Execution Context — Application Commands (CQRS write side)。

每个 Command 是不可变数据载体，Handler 执行命令。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from aiteamos_shared.types import DepartmentId, MemberId, MemoryId, ProjectId, SkillId, TaskId


@dataclass(frozen=True)
class CreateTaskCommand:
    """创建 Task。"""

    department_id: DepartmentId
    title: str
    description: str = ""
    priority: str = "P2"
    project_ids: list[ProjectId] = field(default_factory=list)
    parent_task_id: TaskId | None = None
    declared_skills: list[SkillId] = field(default_factory=list)
    declared_memory_hints: list[MemoryId] = field(default_factory=list)
    deliverable_kind: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    max_retry_count: int = 3
    max_review_rounds: int = 3


@dataclass(frozen=True)
class TransitionTaskCommand:
    """状态转换命令。"""

    task_id: TaskId
    to_state: str
    reason: str = ""


@dataclass(frozen=True)
class AssignTaskCommand:
    """分配 Task 给 Member。"""

    task_id: TaskId
    member_id: MemberId


@dataclass(frozen=True)
class StartRunCommand:
    """启动 Run。"""

    task_id: TaskId
    member_id: MemberId | None = None


@dataclass(frozen=True)
class SubmitDeliverableCommand:
    """提交交付物。"""

    task_id: TaskId
    run_id: UUID
    deliverable_type: str
    uri: str


@dataclass(frozen=True)
class AddDependencyCommand:
    """添加 Task 依赖。"""

    task_id: TaskId
    depends_on_id: TaskId


# Read queries

@dataclass(frozen=True)
class GetTaskDetailQuery:
    task_id: TaskId


@dataclass(frozen=True)
class ListTasksQuery:
    department_id: UUID | None = None
    state: str | None = None
    assigned_member_id: UUID | None = None
    offset: int = 0
    limit: int = 50
