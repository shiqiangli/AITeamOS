"""
Execution Context — 领域模型 (arch.md §2.2.4)。

聚合根:
- Task: Task 状态机 + Run + Deliverable + 依赖管理

实体:
- TaskRun: 执行记录（属于 Task 聚合内）

值对象:
- TaskState, TaskBudget, DeliverableSpec, RunState, CostAccrued
- TaskDependency
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from aiteamos_shared.types import (
    DepartmentId,
    MemberId,
    MemoryId,
    Priority,
    ProjectId,
    RunId,
    SkillId,
    TaskId,
    generate_task_id,
    new_id,
)


# ---------------------------------------------------------------------------
# 枚举值对象
# ---------------------------------------------------------------------------


class TaskState(StrEnum):
    """Task 状态机状态（arch.md §3.1）。"""

    DRAFT = "draft"
    READY = "ready"
    ASSIGNED = "assigned"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUSPENDED = "suspended"
    IN_REVIEW = "in_review"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunState(StrEnum):
    """TaskRun / Job 执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPhase(StrEnum):
    """Job 执行阶段 (arch.md T3-T4)。"""

    QUEUED = "queued"
    ASSEMBLING = "assembling"
    RENDERING = "rendering"
    CALLING = "calling"
    PROCESSING = "processing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskBudget:
    """Task 预算值对象（arch.md §3.3）。"""

    max_tokens: int = 0
    max_duration_seconds: float = 0.0
    max_cost_usd: Decimal = Decimal("0")
    max_retry_count: int = 5
    max_review_rounds: int = 3


@dataclass(frozen=True)
class DeliverableSpec:
    """交付物规格值对象。"""

    kind: str = ""  # code | document | design | config
    acceptance_criteria: list[str] = field(default_factory=list)
    output_format: str = ""


@dataclass(frozen=True)
class CostAccrued:
    """累计成本值对象。"""

    tokens_used: int = 0
    duration_seconds: float = 0.0
    cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class TaskDependency:
    """Task 依赖关系值对象。"""

    task_id: TaskId
    depends_on_id: TaskId


# ---------------------------------------------------------------------------
# 实体: TaskRun (legacy alias, 由 Job 替代)
# ---------------------------------------------------------------------------


@dataclass
class TaskRun:
    """TaskRun 实体 — legacy, 由 Job 实体替代。"""

    run_id: RunId = field(default_factory=lambda: new_id())
    task_id: TaskId = ""
    member_id: MemberId = field(default_factory=lambda: new_id())
    snapshot_id: UUID | None = None
    state: RunState = RunState.PENDING
    cost: CostAccrued = field(default_factory=CostAccrued)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


# ---------------------------------------------------------------------------
# 实体: Job — Task 的一次执行尝试 (Pre + Middle + Post)
# ---------------------------------------------------------------------------


@dataclass
class Job:
    """Job 实体 — Task 的一次执行尝试，承载完整执行可观测性。

    Pre:    rendered_prompt + context_snapshot
    Middle: phase + phase_entered_at + error
    Post:   result_report + cost
    """

    job_id: UUID = field(default_factory=lambda: new_id())
    task_id: TaskId = ""
    member_id: UUID | None = None
    llm_model_id: UUID | None = None

    # Pre
    rendered_prompt: str = ""
    context_snapshot: dict[str, Any] = field(default_factory=dict)

    # Middle
    phase: JobPhase = JobPhase.QUEUED
    phase_entered_at: datetime | None = None
    error: str = ""

    # Post
    result_report: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)

    # Meta
    state: RunState = RunState.PENDING
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def advance_phase(self, phase: JobPhase) -> None:
        """推进执行阶段。"""
        self.phase = phase
        self.phase_entered_at = datetime.now(timezone.utc)

    def mark_running(self) -> None:
        self.state = RunState.RUNNING
        self.phase = JobPhase.ASSEMBLING
        self.phase_entered_at = datetime.now(timezone.utc)

    def mark_completed(self, *, result_report: dict | None = None, cost: dict | None = None) -> None:
        self.state = RunState.COMPLETED
        self.phase = JobPhase.COMPLETED
        self.finished_at = datetime.now(timezone.utc)
        if result_report:
            self.result_report = result_report
        if cost:
            self.cost = cost

    def mark_failed(self, *, error: str = "") -> None:
        self.state = RunState.FAILED
        self.phase = JobPhase.FAILED
        self.finished_at = datetime.now(timezone.utc)
        self.error = error


# ---------------------------------------------------------------------------
# 聚合根: Task (arch.md §2.2.4)
# ---------------------------------------------------------------------------


class Task:
    """Task 聚合根 — 执行上下文核心。

    不变量:
    - 状态转换必须经由 TaskStateMachine
    - 分配 Member 前必须处于 Ready 状态
    - Run 启动前必须有不可变 Snapshot
    """

    def __init__(
        self,
        *,
        id: TaskId | None = None,
        department_id: DepartmentId,
        project_ids: list[ProjectId] | None = None,
        parent_task_id: TaskId | None = None,
        state: TaskState = TaskState.DRAFT,
        priority: Priority = Priority.P2,
        title: str,
        description: str = "",
        deliverable_spec: DeliverableSpec | None = None,
        declared_skills: list[SkillId] | None = None,
        declared_memory_hints: list[MemoryId] | None = None,
        budget: TaskBudget | None = None,
        retry_count: int = 0,
        review_round: int = 0,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.id: TaskId = id or generate_task_id()
        self.department_id = department_id
        self.project_ids: list[ProjectId] = project_ids or []
        self.parent_task_id = parent_task_id
        self.state = state
        self.priority = priority
        self.title = title
        self.description = description
        self.deliverable_spec = deliverable_spec or DeliverableSpec()
        self.declared_skills: list[SkillId] = declared_skills or []
        self.declared_memory_hints: list[MemoryId] = declared_memory_hints or []
        self.budget = budget or TaskBudget()
        self.retry_count = retry_count
        self.review_round = review_round
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

        # 聚合内实体
        self.dependencies: list[TaskDependency] = []

        # 内部事件收集器
        self._pending_events: list[Any] = []

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def _register_event(self, event: Any) -> None:
        self._pending_events.append(event)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    # -- 业务方法 --

    def complete_info(self) -> None:
        """Draft → Ready: 信息完备。"""
        self._transition_to(TaskState.READY, "complete_info")

    def assign_member(self, member_id: MemberId) -> None:
        """legacy — 分配成员已由 Job 层处理。"""
        pass

    def start_run(self, *, member_id: MemberId | None = None) -> TaskRun:
        """Ready/Assigned → Running: 开始执行。

        返回一个临时 TaskRun (不持久化)，实际执行记录由 Job 承载。
        """
        self._transition_to(TaskState.RUNNING, "start_run")
        run = TaskRun(
            task_id=self.id,
            member_id=member_id or new_id(),
            state=RunState.RUNNING,
        )
        from . import events as evt

        self._register_event(
            evt.RunStarted(
                event_type="execution.run.started",
                run_id=run.run_id,
                task_id=self.id,
                member_id=run.member_id,
            )
        )
        return run

    def submit_deliverable(
        self, *, run_id: RunId, deliverable_type: str, uri: str
    ) -> None:
        """Running → Verifying: 提交交付物。"""
        self._transition_to(TaskState.VERIFYING, "submit_deliverable")
        from . import events as evt

        self._register_event(
            evt.DeliverableSubmitted(
                event_type="execution.deliverable.submitted",
                task_id=self.id,
                run_id=run_id,
                deliverable_type=deliverable_type,
                uri=uri,
            )
        )

    def harness_pass(self) -> None:
        """Verifying → InReview: Harness 验证通过。"""
        self._transition_to(TaskState.IN_REVIEW, "harness_pass")

    def harness_fail(self, *, max_retry: int = 3) -> None:
        """Verifying → Running (retry) or Failed (exceeded)."""
        if self.retry_count < max_retry:
            self.retry_count += 1
            self._transition_to(TaskState.RUNNING, "harness_fail_retry")
        else:
            self._transition_to(TaskState.FAILED, "harness_fail_exceeded")

    def review_approve(self) -> None:
        """InReview → Done: 审核通过。"""
        self._transition_to(TaskState.DONE, "review_approve")

    def review_reject(self, *, max_rounds: int = 3) -> None:
        """InReview → Running (retry) or Failed (exceeded)."""
        if self.review_round < max_rounds:
            self.review_round += 1
            self._transition_to(TaskState.RUNNING, "review_reject_retry")
        else:
            self._transition_to(TaskState.FAILED, "review_reject_exceeded")

    def suspend(self, *, reason: str = "budget_pause") -> None:
        """Running/Suspended: 暂停执行。"""
        self._transition_to(TaskState.SUSPENDED, reason)

    def resume(self) -> None:
        """Suspended → Running: 恢复执行。"""
        self._transition_to(TaskState.RUNNING, "member_resumed")

    def callback_received(self) -> None:
        """Suspended → Verifying: 异步回调收到。"""
        self._transition_to(TaskState.VERIFYING, "callback_received")

    def cancel(self) -> None:
        """→ Cancelled: 取消 Task。"""
        self._transition_to(TaskState.CANCELLED, "cancel")

    def requeue(self) -> None:
        """Failed → Ready: 重新排队。"""
        self._transition_to(TaskState.READY, "requeue")

    def hard_circuit_break(self, *, reason: str) -> None:
        """Running → Failed: 硬熔断。"""
        self._transition_to(TaskState.FAILED, "hard_circuit_breaker")
        from . import events as evt

        self._register_event(
            evt.TaskHardCircuitTriggered(
                event_type="execution.task.hard_circuit_triggered",
                task_id=self.id,
                reason=reason,
            )
        )

    # -- 内部状态转换 --

    def _transition_to(self, new_state: TaskState, reason: str) -> None:
        """内部状态转换 — 注册 TaskStateChanged 事件。"""
        old_state = self.state
        self.state = new_state
        self.touch()
        from . import events as evt

        self._register_event(
            evt.TaskStateChanged(
                event_type="execution.task.state_changed",
                task_id=self.id,
                from_state=old_state,
                to_state=new_state,
                reason=reason,
            )
        )

    def __repr__(self) -> str:
        return f"Task(id={self.id}, state={self.state}, title={self.title!r})"
