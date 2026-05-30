"""
Execution Context — 不变量校验 (arch.md §3.2, plan.md §2.1.1)。

每个不变量对应状态转换矩阵中的一个校验条件。
不变量以 Inv.* 命名，遵循 arch.md §3.2 约定。
"""

from __future__ import annotations

from typing import Any, Protocol

from .models import Task, TaskState


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class InvariantViolationError(Exception):
    """不变量校验失败。"""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{code}] {message}")


# ---------------------------------------------------------------------------
# Invariant 实现
# ---------------------------------------------------------------------------


class Inv:
    """不变量校验集合（arch.md §3.2 TRANSITIONS 中的 inv 列表）。"""

    @staticmethod
    def has_required_fields(task: Task) -> None:
        """Task 必填字段校验。"""
        if not task.title:
            raise InvariantViolationError("I-E-1", "Task title is required")
        if not task.department_id:
            raise InvariantViolationError("I-E-1", "Task department_id is required")

    @staticmethod
    def has_dept(task: Task) -> None:
        """Task 必须关联 Department。"""
        if not task.department_id:
            raise InvariantViolationError("I-E-2", "Task must have department_id")

    @staticmethod
    def member_concurrency_ok(task: Task, *, active_runs_for_member: int = 0, concurrency_limit: int = 1) -> None:
        """Advisory Lock 并发守卫 (arch.md §3.2.1)。

        在实际 DB 环境中，此校验通过 PostgreSQL Advisory Lock 实现。
        此处提供纯逻辑版本用于单元测试。
        """
        if active_runs_for_member >= concurrency_limit:
            raise InvariantViolationError(
                "I-E-3",
                f"Member concurrency limit exceeded: {active_runs_for_member}/{concurrency_limit}",
            )

    @staticmethod
    def snapshot_sealed(task: Task, *, has_snapshot: bool = True) -> None:
        """不可变快照已密封 (arch.md §2.2.4 N1)。"""
        if not has_snapshot:
            raise InvariantViolationError("I-E-4", "Context snapshot must be sealed before running")

    @staticmethod
    def budget_allocated(task: Task) -> None:
        """预算已分配。"""
        if task.budget is None:
            raise InvariantViolationError("I-E-5", "Task budget must be allocated")

    @staticmethod
    def retry_under_limit(task: Task) -> None:
        """重试上限未超。"""
        if task.retry_count >= task.budget.max_retry_count:
            raise InvariantViolationError(
                "I-E-6",
                f"Retry limit exceeded: {task.retry_count}/{task.budget.max_retry_count}",
            )

    @staticmethod
    def review_round_under_limit(task: Task) -> None:
        """审核轮次上限未超。"""
        if task.review_round >= task.budget.max_review_rounds:
            raise InvariantViolationError(
                "I-E-7",
                f"Review round limit exceeded: {task.review_round}/{task.budget.max_review_rounds}",
            )

    @staticmethod
    def deliverable_submitted(task: Task, *, has_deliverable: bool = True) -> None:
        """交付物已提交。"""
        if not has_deliverable:
            raise InvariantViolationError("I-E-8", "Deliverable must be submitted")

    @staticmethod
    def skill_match(task: Task, *, member_skills: list[Any] | None = None) -> None:
        """Skill 匹配校验（简化实现）。"""
        # 完整实现需查询 Member 的 base_skill_set 与 task.declared_skills 交集
        pass
