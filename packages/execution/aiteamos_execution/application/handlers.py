"""
Execution Context — Command Handlers (CQRS write side)。

每个 Handler 负责:
1. 从仓储加载聚合
2. 执行不变量校验
3. 修改聚合状态
4. 发出领域事件（通过 Outbox 同事务写入）
5. 保存聚合
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from aiteamos_shared.types import TaskId, new_id

from ..domain.events import TaskCreated
from ..domain.models import (
    DeliverableSpec,
    Task,
    TaskBudget,
    TaskDependency,
    TaskState,
)
from .commands import (
    AddDependencyCommand,
    AssignTaskCommand,
    CreateTaskCommand,
    StartRunCommand,
    SubmitDeliverableCommand,
    TransitionTaskCommand,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class TaskRepoLike(Protocol):
    async def get_by_id(self, id: Any, *, tx: Any = None) -> Task | None: ...
    async def save(self, aggregate: Task, *, tx: Any = None) -> None: ...
    async def lock_for_update(self, id: Any, *, tx: Any) -> Task | None: ...


class TransactionManagerLike(Protocol):
    def transaction(self) -> Any: ...


class EventPublisherLike(Protocol):
    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None: ...


class ContextAssemblerLike(Protocol):
    async def assemble(
        self,
        *,
        task_id: str,
        member_id: Any,
        project_ids: list[Any] | None = None,
        dept_id: Any | None = None,
        declared_skills: list[Any] | None = None,
        max_recall_tokens: int = 8000,
        run_id: Any | None = None,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# CreateTaskHandler
# ---------------------------------------------------------------------------


class CreateTaskHandler:
    """处理 CreateTaskCommand。"""

    def __init__(
        self,
        *,
        task_repo: TaskRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = task_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: CreateTaskCommand) -> Task:
        budget = TaskBudget(
            max_retry_count=cmd.max_retry_count,
            max_review_rounds=cmd.max_review_rounds,
        )
        deliverable_spec = DeliverableSpec(
            kind=cmd.deliverable_kind,
            acceptance_criteria=cmd.acceptance_criteria,
        )

        task = Task(
            department_id=cmd.department_id,
            project_ids=cmd.project_ids,
            parent_task_id=cmd.parent_task_id,
            priority=cmd.priority,
            title=cmd.title,
            description=cmd.description,
            deliverable_spec=deliverable_spec,
            declared_skills=cmd.declared_skills,
            declared_memory_hints=cmd.declared_memory_hints,
            budget=budget,
        )

        created_event = TaskCreated(
            event_type="execution.task.created",
            task_id=task.id,
            department_id=task.department_id,
            title=task.title,
            priority=task.priority,
        )

        async with self._tx.transaction() as tx:
            await self._repo.save(task, tx=tx)
            all_events = [created_event] + task.pending_events
            task.clear_pending_events()
            await self._publisher.publish_events(
                all_events, partition_key=str(task.id), tx=tx
            )

        logger.info("Created Task %s (title=%s)", task.id, task.title)
        return task


# ---------------------------------------------------------------------------
# AssignTaskHandler
# ---------------------------------------------------------------------------


class AssignTaskHandler:
    """处理 AssignTaskCommand — Ready → Assigned。"""

    def __init__(
        self,
        *,
        task_repo: TaskRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = task_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: AssignTaskCommand) -> Task:
        async with self._tx.transaction() as tx:
            task = await self._repo.lock_for_update(cmd.task_id, tx=tx)
            if task is None:
                raise ValueError(f"Task {cmd.task_id} not found")
            task.assign_member(cmd.member_id)
            await self._repo.save(task, tx=tx)
            events = task.pending_events
            task.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(task.id), tx=tx
            )
        return task


# ---------------------------------------------------------------------------
# TransitionTaskHandler
# ---------------------------------------------------------------------------


class TransitionTaskHandler:
    """处理 TransitionTaskCommand — 通用状态转换。"""

    def __init__(
        self,
        *,
        task_repo: TaskRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = task_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: TransitionTaskCommand) -> Task:
        from ..domain.state_machine import TaskStateMachine, IllegalTransitionError

        async with self._tx.transaction() as tx:
            task = await self._repo.lock_for_update(cmd.task_id, tx=tx)
            if task is None:
                raise ValueError(f"Task {cmd.task_id} not found")

            to_state = TaskState(cmd.to_state)

            # 校验
            TaskStateMachine.validate_transition(task.state, to_state)
            TaskStateMachine.check_invariants(task, task.state, to_state)

            # 变更
            task._transition_to(to_state, cmd.reason)

            # 保存 + 发布
            await self._repo.save(task, tx=tx)
            events = task.pending_events
            task.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(task.id), tx=tx
            )
        return task


# ---------------------------------------------------------------------------
# StartRunHandler
# ---------------------------------------------------------------------------


class StartRunHandler:
    """处理 StartRunCommand — Assigned → Running。"""

    def __init__(
        self,
        *,
        task_repo: TaskRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
        context_assembler: ContextAssemblerLike | None = None,
    ):
        self._repo = task_repo
        self._tx = tx_manager
        self._publisher = event_publisher
        self._context_assembler = context_assembler

    async def handle(self, cmd: StartRunCommand) -> Task:
        async with self._tx.transaction() as tx:
            task = await self._repo.lock_for_update(cmd.task_id, tx=tx)
            if task is None:
                raise ValueError(f"Task {cmd.task_id} not found")
            run = task.start_run(member_id=cmd.member_id)
            await self._repo.save(task, tx=tx)
            events = task.pending_events
            task.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(task.id), tx=tx
            )

        # Assemble context snapshot (Memory + Skill) after run starts
        if self._context_assembler is not None:
            try:
                await self._context_assembler.assemble(
                    task_id=str(task.id),
                    member_id=run.member_id,
                    project_ids=task.project_ids,
                    dept_id=task.department_id,
                    declared_skills=task.declared_skills,
                    run_id=run.run_id,
                )
            except Exception:
                logger.warning(
                    "ContextAssembler failed for task %s run %s; "
                    "run continues without sealed snapshot",
                    task.id,
                    run.run_id,
                    exc_info=True,
                )

        return task


# ---------------------------------------------------------------------------
# SubmitDeliverableHandler
# ---------------------------------------------------------------------------


class SubmitDeliverableHandler:
    """处理 SubmitDeliverableCommand — Running → Verifying。"""

    def __init__(
        self,
        *,
        task_repo: TaskRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = task_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: SubmitDeliverableCommand) -> Task:
        async with self._tx.transaction() as tx:
            task = await self._repo.lock_for_update(cmd.task_id, tx=tx)
            if task is None:
                raise ValueError(f"Task {cmd.task_id} not found")
            task.submit_deliverable(
                run_id=cmd.run_id,
                deliverable_type=cmd.deliverable_type,
                uri=cmd.uri,
            )
            await self._repo.save(task, tx=tx)
            events = task.pending_events
            task.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(task.id), tx=tx
            )
        return task


# ---------------------------------------------------------------------------
# AddDependencyHandler
# ---------------------------------------------------------------------------


class AddDependencyHandler:
    """处理 AddDependencyCommand — 添加前置依赖 + 循环检测。"""

    def __init__(
        self,
        *,
        task_repo: TaskRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = task_repo
        self._tx = tx_manager
        self._publisher = event_publisher

    async def handle(self, cmd: AddDependencyCommand) -> Task:
        from ..domain.dependency import DependencyResolver

        async with self._tx.transaction() as tx:
            task = await self._repo.lock_for_update(cmd.task_id, tx=tx)
            if task is None:
                raise ValueError(f"Task {cmd.task_id} not found")

            # 添加依赖
            dep = TaskDependency(task_id=cmd.task_id, depends_on_id=cmd.depends_on_id)
            task.dependencies.append(dep)

            await self._repo.save(task, tx=tx)
            events = task.pending_events
            task.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(task.id), tx=tx
            )
        return task
