"""
Saga Activities — Task 执行各阶段的原子操作 (arch.md §3.3.2, §3.5)。

每个 Activity 是独立可重试的单元。
占用资源的 Activity 必须有对应的补偿 Activity。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Activity result types
# ---------------------------------------------------------------------------


@dataclass
class HarnessSyncResult:
    """同步 Harness 验证结果。"""

    passed: bool
    is_async_pending: bool = False
    callback_token: str = ""
    outcome: str = ""  # pass | fail | flaky | adapter_error
    evidence_uri: str = ""
    metrics: dict[str, Any] | None = None


@dataclass
class ExecArgs:
    """沙箱执行参数。"""

    task_id: str
    snapshot_id: UUID
    run_id: UUID | None = None
    member_id: UUID | None = None


# ---------------------------------------------------------------------------
# Activity protocols — 依赖注入接口
# ---------------------------------------------------------------------------


class ConcurrencyManager(Protocol):
    """Member 并发管理。"""

    async def reserve(self, *, task_id: str, member_id: UUID) -> None: ...
    async def release(self, *, task_id: str, member_id: UUID) -> None: ...


class ContextAssemblerLike(Protocol):
    """Context Assembler ACL。"""

    async def assemble(
        self,
        *,
        task_id: str,
        member_id: UUID,
        **kwargs: Any,
    ) -> Any: ...


class HarnessGateway(Protocol):
    """Harness 验证网关。"""

    async def invoke_sync(
        self, *, deliverable: Any, task_id: str
    ) -> HarnessSyncResult: ...


class TaskStateUpdater(Protocol):
    """Task 状态更新。"""

    async def mark_state(
        self, *, task_id: str, state: str, reason: str = ""
    ) -> None: ...


class SkillBundleManager(Protocol):
    """Skill Bundle 锁定/释放。"""

    async def lock(self, *, task_id: str, skill_ids: list[UUID]) -> str: ...
    async def release(self, *, bundle_id: str) -> None: ...


class MemberExecutor(Protocol):
    """Member 沙箱执行。"""

    async def execute_sandboxed(self, args: ExecArgs) -> Any: ...


# ---------------------------------------------------------------------------
# Activity implementations
# ---------------------------------------------------------------------------


class SagaActivities:
    """Saga Activity 集合 — 所有 Activity 注入依赖。

    每个 Activity 方法对应一个独立的可重试操作。
    """

    def __init__(
        self,
        *,
        concurrency_manager: ConcurrencyManager,
        context_assembler: ContextAssemblerLike,
        harness_gateway: HarnessGateway,
        task_state_updater: TaskStateUpdater,
        skill_bundle_manager: SkillBundleManager,
        member_executor: MemberExecutor,
    ):
        self._concurrency = concurrency_manager
        self._assembler = context_assembler
        self._harness = harness_gateway
        self._state = task_state_updater
        self._skills = skill_bundle_manager
        self._executor = member_executor

    # -- Member 并发 --

    async def reserve_member_concurrency(
        self, *, task_id: str, member_id: UUID
    ) -> None:
        """正向: 占用 Member 并发名额。"""
        await self._concurrency.reserve(task_id=task_id, member_id=member_id)
        logger.info("Reserved concurrency: task=%s member=%s", task_id, member_id)

    async def release_member_concurrency(
        self, *, task_id: str, member_id: UUID
    ) -> None:
        """补偿: 释放 Member 并发名额 (幂等)。"""
        await self._concurrency.release(task_id=task_id, member_id=member_id)
        logger.info("Released concurrency: task=%s member=%s", task_id, member_id)

    # -- Context 装配 --

    async def assemble_context(
        self,
        *,
        task_id: str,
        member_id: UUID,
        **kwargs: Any,
    ) -> Any:
        """装配上下文快照。"""
        snapshot = await self._assembler.assemble(
            task_id=task_id, member_id=member_id, **kwargs
        )
        logger.info("Assembled context for task=%s", task_id)
        return snapshot

    # -- Skill Bundle --

    async def lock_skill_bundle(
        self, *, task_id: str, skill_ids: list[UUID]
    ) -> str:
        """正向: 锁定 Skill Bundle。"""
        bundle_id = await self._skills.lock(task_id=task_id, skill_ids=skill_ids)
        logger.info("Locked skill bundle %s for task=%s", bundle_id, task_id)
        return bundle_id

    async def release_skill_bundle(self, *, bundle_id: str) -> None:
        """补偿: 释放 Skill Bundle (幂等)。"""
        await self._skills.release(bundle_id=bundle_id)
        logger.info("Released skill bundle %s", bundle_id)

    # -- 沙箱执行 --

    async def execute_member_sandboxed(self, args: ExecArgs) -> Any:
        """沙箱化执行 Member 任务。"""
        result = await self._executor.execute_sandboxed(args)
        logger.info("Executed sandboxed: task=%s", args.task_id)
        return result

    # -- Harness 验证 --

    async def invoke_harness_sync(
        self, *, deliverable: Any, task_id: str
    ) -> HarnessSyncResult:
        """同步 Harness 验证。"""
        result = await self._harness.invoke_sync(
            deliverable=deliverable, task_id=task_id
        )
        logger.info(
            "Harness sync result: task=%s passed=%s async=%s",
            task_id,
            result.passed,
            result.is_async_pending,
        )
        return result

    # -- Task 状态 --

    async def mark_state(
        self, *, task_id: str, state: str, reason: str = ""
    ) -> None:
        """标记 Task 状态。"""
        await self._state.mark_state(task_id=task_id, state=state, reason=reason)

    # -- 失败处理 --

    async def force_fail_task(
        self, *, task_id: str, reason: str
    ) -> None:
        """强制 Task 失败。"""
        await self._state.mark_state(task_id=task_id, state="failed", reason=reason)
        logger.warning("Force failed task=%s: %s", task_id, reason)
