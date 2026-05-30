"""
Execution Context — Task 状态机 (arch.md §3.1, §3.2)。

完整状态转换矩阵 + 不变量校验 + 事件发布。
所有状态转换必须经由此状态机；绕过 transition() 直接 set state 视为系统级故障。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from .invariants import InvariantViolationError, Inv
from .models import Task, TaskState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class IllegalTransitionError(Exception):
    """非法状态转换。"""

    def __init__(self, from_state: str, to_state: str):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal transition: {from_state} → {to_state}"
        )


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


# ---------------------------------------------------------------------------
# 转换不变量映射 (arch.md §3.2 TRANSITIONS)
# ---------------------------------------------------------------------------

# 每条转换对应的不变量校验函数列表
# 实际调用时 Inv 方法需要 task 参数；此处存储静态方法引用
TRANSITION_INVARIANTS: dict[tuple[TaskState, TaskState], list[str]] = {
    (TaskState.DRAFT, TaskState.READY): ["has_required_fields", "has_dept"],
    (TaskState.DRAFT, TaskState.CANCELLED): [],
    (TaskState.READY, TaskState.ASSIGNED): ["member_concurrency_ok"],
    (TaskState.READY, TaskState.CANCELLED): [],
    (TaskState.ASSIGNED, TaskState.RUNNING): ["snapshot_sealed", "budget_allocated"],
    (TaskState.ASSIGNED, TaskState.CANCELLED): [],
    (TaskState.RUNNING, TaskState.VERIFYING): ["deliverable_submitted"],
    (TaskState.RUNNING, TaskState.SUSPENDED): [],
    (TaskState.RUNNING, TaskState.FAILED): [],
    (TaskState.RUNNING, TaskState.CANCELLED): [],
    (TaskState.VERIFYING, TaskState.SUSPENDED): [],
    (TaskState.VERIFYING, TaskState.IN_REVIEW): [],
    (TaskState.VERIFYING, TaskState.RUNNING): ["retry_under_limit"],
    (TaskState.VERIFYING, TaskState.FAILED): [],
    (TaskState.SUSPENDED, TaskState.VERIFYING): [],
    (TaskState.SUSPENDED, TaskState.RUNNING): [],
    (TaskState.SUSPENDED, TaskState.FAILED): [],
    (TaskState.SUSPENDED, TaskState.CANCELLED): [],
    (TaskState.IN_REVIEW, TaskState.DONE): [],
    (TaskState.IN_REVIEW, TaskState.RUNNING): ["review_round_under_limit"],
    (TaskState.IN_REVIEW, TaskState.FAILED): [],
    (TaskState.FAILED, TaskState.READY): [],
    (TaskState.FAILED, TaskState.CANCELLED): [],
}

# 合法转换集合（快速查找）
LEGAL_TRANSITIONS: set[tuple[TaskState, TaskState]] = set(TRANSITION_INVARIANTS.keys())


# ---------------------------------------------------------------------------
# TaskStateMachine
# ---------------------------------------------------------------------------


class TaskStateMachine:
    """Task 状态机 — 所有状态转换的唯一入口。

    使用方式::

        sm = TaskStateMachine(repo=task_repo, tx_manager=tx, event_publisher=pub)
        task = await sm.transition(task_id, to_state=TaskState.READY, reason="info complete")
    """

    def __init__(
        self,
        *,
        repo: TaskRepoLike,
        tx_manager: TransactionManagerLike,
        event_publisher: EventPublisherLike,
    ):
        self._repo = repo
        self._tx = tx_manager
        self._publisher = event_publisher

    @staticmethod
    def validate_transition(from_state: TaskState, to_state: TaskState) -> None:
        """校验转换是否合法（不加载聚合，纯静态检查）。"""
        if (from_state, to_state) not in LEGAL_TRANSITIONS:
            raise IllegalTransitionError(from_state.value, to_state.value)

    @staticmethod
    def check_invariants(task: Task, from_state: TaskState, to_state: TaskState) -> None:
        """执行转换对应的不变量校验。"""
        inv_names = TRANSITION_INVARIANTS.get((from_state, to_state), [])
        for inv_name in inv_names:
            inv_fn = getattr(Inv, inv_name, None)
            if inv_fn is not None:
                inv_fn(task)

    async def transition(
        self,
        task_id: str,
        *,
        to_state: TaskState,
        reason: str = "",
    ) -> Task:
        """执行状态转换: 加锁 → 校验 → 变更 → 事件 → 保存。

        Args:
            task_id: Task ID
            to_state: 目标状态
            reason: 转换原因

        Returns:
            更新后的 Task 聚合

        Raises:
            IllegalTransitionError: 非法转换
            InvariantViolationError: 不变量校验失败
            ValueError: Task 不存在
        """
        async with self._tx.transaction() as tx:
            task = await self._repo.lock_for_update(task_id, tx=tx)
            if task is None:
                raise ValueError(f"Task {task_id} not found")

            from_state = task.state

            # 1. 合法性校验
            self.validate_transition(from_state, to_state)

            # 2. 不变量校验
            self.check_invariants(task, from_state, to_state)

            # 3. 状态变更 + 事件注册
            task._transition_to(to_state, reason)

            # 4. 保存
            await self._repo.save(task, tx=tx)

            # 5. 发布事件（Outbox 同事务）
            events = task.pending_events
            task.clear_pending_events()
            await self._publisher.publish_events(
                events, partition_key=str(task.id), tx=tx
            )

        logger.info(
            "Task %s: %s → %s (reason=%s)",
            task_id, from_state.value, to_state.value, reason,
        )
        return task


# ---------------------------------------------------------------------------
# 辅助函数: 获取合法后继状态
# ---------------------------------------------------------------------------


def get_legal_successors(state: TaskState) -> list[TaskState]:
    """返回从给定状态出发的所有合法后继状态。"""
    return [to for (frm, to) in LEGAL_TRANSITIONS if frm == state]


def is_terminal_state(state: TaskState) -> bool:
    """判断是否为终止状态。"""
    return state in (TaskState.DONE, TaskState.CANCELLED)
