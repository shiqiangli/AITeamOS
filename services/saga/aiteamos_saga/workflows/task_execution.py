"""
Task Execution Workflow (arch.md §3.3.2, §3.5)。

Temporal-style Saga 编排器 — Task 全生命周期:
  装配阶段 → 执行阶段 → 验证阶段 → 审核阶段

特性:
- Signal 机制: harness_callback, harness_deadline_exceeded
- ContinueAsNew: 每 50 个 Signal 触发
- 补偿栈: 每个资源占用伴随 push_compensation
- 不变量 N5: 沙箱原子性
- 不变量 N7: 资源补偿闭环

注意: 此实现使用纯 Python 抽象（非直接依赖 Temporal SDK），
使得 Workflow 逻辑可单元测试。生产部署时替换为 Temporal API。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from ..activities.definitions import ExecArgs, HarnessSyncResult, SagaActivities
from ..compensation import CompensationItem, CompensationStack, ResourceKind

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TaskOutcome
# ---------------------------------------------------------------------------


class TaskOutcomeKind(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskOutcome:
    """Workflow 执行结果。"""

    kind: TaskOutcomeKind
    reason: str = ""
    deliverable: Any = None

    @classmethod
    def success(cls, deliverable: Any = None) -> TaskOutcome:
        return cls(kind=TaskOutcomeKind.SUCCESS, deliverable=deliverable)

    @classmethod
    def failed(cls, reason: str) -> TaskOutcome:
        return cls(kind=TaskOutcomeKind.FAILED, reason=reason)

    @classmethod
    def cancelled(cls) -> TaskOutcome:
        return cls(kind=TaskOutcomeKind.CANCELLED)


# ---------------------------------------------------------------------------
# ResumePoint (ContinueAsNew checkpoint)
# ---------------------------------------------------------------------------


@dataclass
class ResumePoint:
    """ContinueAsNew 断点 — Workflow History 膨胀保护。"""

    stage: str = ""  # assembly | execution | verification | review
    harness_signals: dict[str, HarnessSyncResult] = field(default_factory=dict)
    pending_callback_tokens: list[str] = field(default_factory=list)
    signal_count: int = 0


# ---------------------------------------------------------------------------
# Workflow exceptions
# ---------------------------------------------------------------------------


class BudgetExceeded(Exception):
    """预算超限 — 不可重试。"""
    pass


class SandboxAborted(Exception):
    """沙箱中止 — 不可重试。"""
    pass


# ---------------------------------------------------------------------------
# TaskExecutionWorkflow (arch.md §3.3.2)
# ---------------------------------------------------------------------------


class TaskExecutionWorkflow:
    """Task 全生命周期 Saga 编排器。

    4 阶段: 装配 → 执行 → 验证 → 审核

    补偿链 (纪律 #11):
    - reserve_member_concurrency → release_member_concurrency
    - create_sandbox → destroy_sandbox
    - lock_skill_bundle → release_skill_bundle
    """

    MAX_SIGNALS_BEFORE_CONTINUE_AS_NEW = 50

    def __init__(
        self,
        *,
        activities: SagaActivities,
        compensation_executor: Any = None,
        compensation_failure_handler: Any = None,
    ):
        self._activities = activities
        self.harness_signals: dict[str, HarnessSyncResult] = {}
        self._signal_count = 0
        self._compensation = CompensationStack(
            executor=compensation_executor or self._default_compensation_executor,
            on_failure=compensation_failure_handler,
        )
        self._needs_continue_as_new = False
        self._checkpoint: ResumePoint | None = None

    async def _default_compensation_executor(
        self, activity: str, args: dict[str, Any]
    ) -> None:
        """Route compensation activities to the injected SagaActivities."""
        method = getattr(self._activities, activity, None)
        if method is not None:
            await method(**args)
        else:
            logger.warning(
                "Compensation activity not found: %s — skipping", activity
            )

    @property
    def compensation_stack(self) -> CompensationStack:
        return self._compensation

    @property
    def needs_continue_as_new(self) -> bool:
        return self._needs_continue_as_new

    @property
    def checkpoint(self) -> ResumePoint | None:
        return self._checkpoint

    # -- Signal handlers --

    def harness_callback(self, payload: HarnessSyncResult) -> None:
        """Harness 回调 Signal — 由 Callback Receiver 发送。"""
        self._signal_count += 1
        token = payload.callback_token or "default"
        self.harness_signals[token] = payload

        if self._signal_count >= self.MAX_SIGNALS_BEFORE_CONTINUE_AS_NEW:
            self._needs_continue_as_new = True
            self._checkpoint = self._make_checkpoint()

    def harness_deadline_exceeded(self) -> None:
        """Harness 超时 Signal。"""
        self._signal_count += 1

    def _make_checkpoint(self) -> ResumePoint:
        """生成 ContinueAsNew 断点。"""
        return ResumePoint(
            stage="verification",
            harness_signals=dict(self.harness_signals),
            pending_callback_tokens=[
                token
                for token, result in self.harness_signals.items()
                if result is None
            ],
            signal_count=self._signal_count,
        )

    # -- Main workflow --

    async def run(
        self,
        *,
        task_id: str,
        member_id: UUID,
        project_ids: list[UUID] | None = None,
        dept_id: UUID | None = None,
        declared_skills: list[UUID] | None = None,
        run_id: UUID | None = None,
        resume_from: ResumePoint | None = None,
    ) -> TaskOutcome:
        """执行 Task 全生命周期 Saga。

        成功路径: 装配 → 执行 → 验证 → 审核 → 完成
        失败路径: unwind 补偿栈 + force_fail_task
        """
        project_ids = project_ids or []
        declared_skills = declared_skills or []
        run_id = run_id or uuid4()

        # Restore from checkpoint if ContinueAsNew
        if resume_from:
            self.harness_signals = resume_from.harness_signals
            self._signal_count = resume_from.signal_count

        try:
            # === 阶段 1: 资源预留 + 补偿注册 ===

            # 1a. Reserve member concurrency
            await self._activities.reserve_member_concurrency(
                task_id=task_id, member_id=member_id
            )
            self._compensation.push(CompensationItem(
                activity="release_member_concurrency",
                args={"task_id": task_id, "member_id": member_id},
                kind=ResourceKind.MEMBER_CONCURRENCY,
                correlation_id=task_id,
            ))

            # 1b. Lock skill bundle
            if declared_skills:
                bundle_id = await self._activities.lock_skill_bundle(
                    task_id=task_id, skill_ids=declared_skills
                )
                self._compensation.push(CompensationItem(
                    activity="release_skill_bundle",
                    args={"bundle_id": bundle_id},
                    kind=ResourceKind.SKILL_BUNDLE,
                    correlation_id=bundle_id,
                ))

            # === 阶段 2: 装配 ===
            snapshot = await self._activities.assemble_context(
                task_id=task_id,
                member_id=member_id,
                project_ids=project_ids,
                dept_id=dept_id,
            )
            snapshot_id = getattr(snapshot, "id", uuid4())

            await self._activities.mark_state(
                task_id=task_id, state="running", reason="context_assembled"
            )

            # === 阶段 3: 执行 (沙箱化) ===
            exec_args = ExecArgs(
                task_id=task_id,
                snapshot_id=snapshot_id,
                run_id=run_id,
                member_id=member_id,
            )
            deliverable = await self._activities.execute_member_sandboxed(exec_args)

            await self._activities.mark_state(
                task_id=task_id, state="verifying", reason="deliverable_submitted"
            )

            # === 阶段 4: 验证 ===
            harness_result = await self._activities.invoke_harness_sync(
                deliverable=deliverable, task_id=task_id
            )

            if harness_result.is_async_pending:
                # 进入 Suspended — 等待 Signal
                await self._activities.mark_state(
                    task_id=task_id, state="suspended", reason="async_harness"
                )

                callback_token = harness_result.callback_token

                # 模拟 Signal 等待（生产环境由 Temporal wait_condition 处理）
                if callback_token in self.harness_signals:
                    harness_result = self.harness_signals[callback_token]
                else:
                    # 超时或无回调 → 失败
                    await self._activities.force_fail_task(
                        task_id=task_id, reason="harness_timeout"
                    )
                    return TaskOutcome.failed("harness_timeout")

            # === 路由 ===
            if harness_result.passed:
                await self._activities.mark_state(
                    task_id=task_id, state="in_review", reason="harness_passed"
                )
                # 审核通过（简化：直接 Done）
                await self._activities.mark_state(
                    task_id=task_id, state="done", reason="review_approved"
                )

                # 成功路径: 释放所有补偿项
                await self._compensation.unwind("workflow_completed_ok")
                return TaskOutcome.success(deliverable)
            else:
                # Harness 失败 → 重试或失败
                await self._activities.mark_state(
                    task_id=task_id, state="running", reason="harness_failed_retry"
                )
                # 简化：直接失败
                await self._activities.force_fail_task(
                    task_id=task_id, reason="harness_failed"
                )
                await self._compensation.unwind("harness_failed")
                return TaskOutcome.failed("harness_failed")

        except (BudgetExceeded, SandboxAborted, asyncio.CancelledError) as exc:
            # 失败路径: 反向释放所有已压入资源
            reason = f"workflow_failed: {type(exc).__name__}"
            try:
                await self._compensation.unwind(reason)
            except Exception:
                logger.exception("Compensation unwind failed during %s", reason)
            try:
                await self._activities.force_fail_task(
                    task_id=task_id, reason=str(exc) or reason
                )
            except Exception:
                logger.exception("force_fail_task failed during %s", reason)
            return TaskOutcome.failed(reason)

        except Exception as exc:
            # 兜底异常处理
            reason = f"workflow_error: {type(exc).__name__}"
            try:
                await self._compensation.unwind(reason)
            except Exception:
                logger.exception("Compensation unwind failed during %s", reason)
            try:
                await self._activities.force_fail_task(
                    task_id=task_id, reason=str(exc) or reason
                )
            except Exception:
                logger.exception("force_fail_task failed during %s", reason)
            return TaskOutcome.failed(reason)

    # -- Fitness assertions (arch.md §3.5.3) --

    async def assert_terminal_clean(self) -> None:
        """终态不变量 N7: 补偿栈必须为空。"""
        await self._compensation.assert_empty()
