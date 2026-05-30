"""
Execution Context — Task 依赖管理与优先级调度 (plan.md §2.1.3)。

- DependencyResolver: DAG 依赖解析 + 循环检测 (DFS)
- PriorityScheduler: 竞争排序 + P0 抢占
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from aiteamos_shared.types import TaskId

from .models import Task, TaskState


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


class TaskRepoLike(Protocol):
    async def get_by_id(self, id: Any, *, tx: Any = None) -> Task | None: ...


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class CircularDependencyError(Exception):
    """循环依赖检测异常。"""

    def __init__(self, cycle: list[TaskId]):
        self.cycle = cycle
        super().__init__(f"Circular dependency detected: {' → '.join(cycle)}")


class DependencyNotMetError(Exception):
    """前置依赖未满足。"""

    def __init__(self, task_id: TaskId, blocked_by: TaskId):
        super().__init__(f"Task {task_id} blocked by unfinished dependency {blocked_by}")


# ---------------------------------------------------------------------------
# DependencyResolver
# ---------------------------------------------------------------------------


class DependencyResolver:
    """Task 依赖解析器 — 有向无环图 (DAG) 校验。

    - 创建时 DFS 检查是否有环
    - 前置 Task 完成时发出 TaskDependencyResolved 事件
    - 前置 Task 失败/取消时，依赖 Task 标记 Blocked
    """

    def __init__(self, *, task_repo: TaskRepoLike):
        self._repo = task_repo

    @staticmethod
    def detect_cycle(
        start_id: TaskId,
        adjacency: dict[TaskId, list[TaskId]],
    ) -> list[TaskId] | None:
        """DFS 检测有向图中是否存在环。

        Args:
            start_id: 起始节点 ID
            adjacency: 邻接表 {task_id: [depends_on_ids]}

        Returns:
            None 若无环；环路径列表若有环
        """
        visited: set[TaskId] = set()
        rec_stack: set[TaskId] = set()
        path: list[TaskId] = []

        def _dfs(node: TaskId) -> list[TaskId] | None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    result = _dfs(neighbor)
                    if result is not None:
                        return result
                elif neighbor in rec_stack:
                    # Found cycle — extract cycle path
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]

            path.pop()
            rec_stack.discard(node)
            return None

        return _dfs(start_id)

    @staticmethod
    def validate_no_cycle(
        task_id: TaskId,
        adjacency: dict[TaskId, list[TaskId]],
    ) -> None:
        """校验添加依赖后不存在循环。

        Raises:
            CircularDependencyError: 如果检测到环
        """
        cycle = DependencyResolver.detect_cycle(task_id, adjacency)
        if cycle is not None:
            raise CircularDependencyError(cycle)

    async def check_dependencies_met(
        self, task: Task, *, tx: Any = None
    ) -> tuple[bool, list[TaskId]]:
        """检查 Task 的所有前置依赖是否已完成。

        Returns:
            (all_met, unmet_ids)
        """
        unmet: list[TaskId] = []
        for dep in task.dependencies:
            predecessor = await self._repo.get_by_id(dep.depends_on_id, tx=tx)
            if predecessor is None:
                unmet.append(dep.depends_on_id)
            elif predecessor.state not in (TaskState.DONE,):
                unmet.append(dep.depends_on_id)

        return (len(unmet) == 0, unmet)


# ---------------------------------------------------------------------------
# PriorityScheduler
# ---------------------------------------------------------------------------


class PriorityScheduler:
    """多 Task 竞争调度器 — 按优先级排序。

    规则 (plan.md §2.1.3):
    - P0 > P1 > P2 > P3
    - 同优先级按 created_at 先后
    - P0 可抢占 P3（被抢占 Task 暂停保存上下文）
    """

    # Priority ordinal: lower number = higher priority
    PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

    @classmethod
    def rank(cls, tasks: list[Task]) -> list[Task]:
        """按优先级排序 Task 列表（最高优先级在前）。

        同优先级按 created_at 升序（先创建的先执行）。
        """
        return sorted(
            tasks,
            key=lambda t: (
                cls.PRIORITY_ORDER.get(t.priority, 99),
                t.created_at,
            ),
        )

    @classmethod
    def can_preempt(cls, challenger: Task, incumbent: Task) -> bool:
        """判断 challenger 是否可抢占 incumbent。

        仅 P0 可抢占 P3。
        """
        challenger_ord = cls.PRIORITY_ORDER.get(challenger.priority, 99)
        incumbent_ord = cls.PRIORITY_ORDER.get(incumbent.priority, 99)
        # P0 (ord=0) can preempt P3 (ord=3)
        return challenger_ord == 0 and incumbent_ord == 3
