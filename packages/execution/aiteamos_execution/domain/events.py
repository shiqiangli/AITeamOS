"""
Execution Context — 领域事件 (arch.md §2.2.4, §3.2)。

所有事件继承 VersionedDomainEvent，通过 Outbox 同事务写入。
"""

from __future__ import annotations

from uuid import UUID

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.types import MemberId, RunId, TaskId


# ---------------------------------------------------------------------------
# Task 事件
# ---------------------------------------------------------------------------


class TaskCreated(VersionedDomainEvent):
    """Task 创建。"""

    event_type: str = "execution.task.created"
    task_id: TaskId
    department_id: UUID
    title: str
    priority: str


class TaskStateChanged(VersionedDomainEvent):
    """Task 状态变更（所有状态转换的核心事件）。"""

    event_type: str = "execution.task.state_changed"
    task_id: TaskId
    from_state: str
    to_state: str
    reason: str = ""


class TaskAssigned(VersionedDomainEvent):
    """Task 分配给 Member。"""

    event_type: str = "execution.task.assigned"
    task_id: TaskId
    member_id: MemberId


# ---------------------------------------------------------------------------
# Run 事件
# ---------------------------------------------------------------------------


class RunStarted(VersionedDomainEvent):
    """Run 开始执行。"""

    event_type: str = "execution.run.started"
    run_id: RunId
    task_id: TaskId
    member_id: MemberId


class RunFinished(VersionedDomainEvent):
    """Run 执行完毕。"""

    event_type: str = "execution.run.finished"
    run_id: RunId
    task_id: TaskId
    outcome: str  # success | failure | cancelled


# ---------------------------------------------------------------------------
# Deliverable 事件
# ---------------------------------------------------------------------------


class DeliverableSubmitted(VersionedDomainEvent):
    """交付物提交。"""

    event_type: str = "execution.deliverable.submitted"
    task_id: TaskId
    run_id: RunId
    deliverable_type: str
    uri: str


# ---------------------------------------------------------------------------
# 熔断 / 依赖事件
# ---------------------------------------------------------------------------


class TaskHardCircuitTriggered(VersionedDomainEvent):
    """硬熔断触发 — Task 强制失败。"""

    event_type: str = "execution.task.hard_circuit_triggered"
    task_id: TaskId
    reason: str


class TaskDependencyResolved(VersionedDomainEvent):
    """前置 Task 完成 → 依赖 Task 可转 Ready。"""

    event_type: str = "execution.task.dependency_resolved"
    task_id: TaskId
    resolved_dependency_id: TaskId


class TaskDependencyBlocked(VersionedDomainEvent):
    """前置 Task 失败/取消 → 依赖 Task 标记 Blocked。"""

    event_type: str = "execution.task.dependency_blocked"
    task_id: TaskId
    blocked_by_id: TaskId
