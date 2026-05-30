"""
Saga Workflow — 测试 (plan.md §2.3 验证标准)。

验证标准:
- Workflow happy path 测试通过（Draft → Done）
- 补偿栈在异常退出时正确 unwind
- 沙箱熔断时不留脏状态 (N5)
- Signal 正确唤醒 Suspended Workflow
- 补偿栈在终态为空 (N7)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from aiteamos_saga.activities.definitions import (
    ExecArgs,
    HarnessSyncResult,
    SagaActivities,
)
from aiteamos_saga.compensation import (
    CompensationFailure,
    CompensationItem,
    CompensationStack,
    ResourceKind,
    ResourceLeakError,
)
from aiteamos_saga.sandbox import (
    Deliverable,
    ExecutionSandbox,
    IllegalSandboxTransition,
    SandboxPool,
    SandboxState,
)
from aiteamos_saga.workflows.task_execution import (
    BudgetExceeded,
    ResumePoint,
    SandboxAborted,
    TaskExecutionWorkflow,
    TaskOutcome,
    TaskOutcomeKind,
)


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------


class MockConcurrencyManager:
    def __init__(self):
        self.reserved: list[tuple[str, UUID]] = []
        self.released: list[tuple[str, UUID]] = []

    async def reserve(self, *, task_id: str, member_id: UUID) -> None:
        self.reserved.append((task_id, member_id))

    async def release(self, *, task_id: str, member_id: UUID) -> None:
        self.released.append((task_id, member_id))


class MockContextAssembler:
    def __init__(self):
        self.call_count = 0

    async def assemble(self, *, task_id: str, member_id: UUID, **kwargs: Any) -> Any:
        self.call_count += 1
        return SimpleNamespace(id=uuid4(), task_id=task_id)


class MockHarnessGateway:
    def __init__(
        self,
        result: HarnessSyncResult | None = None,
    ):
        self._result = result or HarnessSyncResult(passed=True)

    async def invoke_sync(
        self, *, deliverable: Any, task_id: str
    ) -> HarnessSyncResult:
        return self._result


class MockTaskStateUpdater:
    def __init__(self):
        self.states: list[tuple[str, str, str]] = []

    async def mark_state(
        self, *, task_id: str, state: str, reason: str = ""
    ) -> None:
        self.states.append((task_id, state, reason))


class MockSkillBundleManager:
    def __init__(self):
        self.locked: list[str] = []
        self.released: list[str] = []

    async def lock(self, *, task_id: str, skill_ids: list[UUID]) -> str:
        bundle_id = f"bundle-{task_id}"
        self.locked.append(bundle_id)
        return bundle_id

    async def release(self, *, bundle_id: str) -> None:
        self.released.append(bundle_id)


class MockMemberExecutor:
    def __init__(self, result: Any = None, should_raise: type[Exception] | None = None):
        self._result = result or {"output": "deliverable"}
        self._raise = should_raise
        self.call_count = 0

    async def execute_sandboxed(self, args: ExecArgs) -> Any:
        self.call_count += 1
        if self._raise:
            raise self._raise("execution failed")
        return self._result


# ---------------------------------------------------------------------------
# Helper to build SagaActivities with mocks
# ---------------------------------------------------------------------------


def _build_activities(
    *,
    harness_result: HarnessSyncResult | None = None,
    executor_raise: type[Exception] | None = None,
) -> tuple[SagaActivities, dict[str, Any]]:
    mocks = {
        "concurrency": MockConcurrencyManager(),
        "assembler": MockContextAssembler(),
        "harness": MockHarnessGateway(harness_result),
        "state": MockTaskStateUpdater(),
        "skills": MockSkillBundleManager(),
        "executor": MockMemberExecutor(should_raise=executor_raise),
    }
    activities = SagaActivities(
        concurrency_manager=mocks["concurrency"],
        context_assembler=mocks["assembler"],
        harness_gateway=mocks["harness"],
        task_state_updater=mocks["state"],
        skill_bundle_manager=mocks["skills"],
        member_executor=mocks["executor"],
    )
    return activities, mocks


# ===========================================================================
# §1: CompensationStack 基础
# ===========================================================================


class TestCompensationStack:
    """补偿栈核心行为。"""

    @pytest.mark.asyncio
    async def test_push_and_unwind(self):
        """push → unwind releases in reverse order."""
        released: list[str] = []

        async def executor(activity: str, args: dict) -> None:
            released.append(activity)

        stack = CompensationStack(executor=executor)
        stack.push(CompensationItem(
            activity="release_a", args={}, kind=ResourceKind.MEMBER_CONCURRENCY
        ))
        stack.push(CompensationItem(
            activity="release_b", args={}, kind=ResourceKind.SANDBOX
        ))
        stack.push(CompensationItem(
            activity="release_c", args={}, kind=ResourceKind.SKILL_BUNDLE
        ))

        assert stack.size == 3
        await stack.unwind("test")
        assert released == ["release_c", "release_b", "release_a"]  # LIFO
        assert stack.is_empty

    @pytest.mark.asyncio
    async def test_unwind_failure_continues(self):
        """Compensation failure doesn't block subsequent items."""
        released: list[str] = []
        failures: list[CompensationFailure] = []

        async def executor(activity: str, args: dict) -> None:
            if activity == "release_b":
                raise RuntimeError("boom")
            released.append(activity)

        async def on_failure(f: CompensationFailure) -> None:
            failures.append(f)

        stack = CompensationStack(executor=executor, on_failure=on_failure)
        stack.push(CompensationItem(
            activity="release_a", args={}, kind=ResourceKind.MEMBER_CONCURRENCY
        ))
        stack.push(CompensationItem(
            activity="release_b", args={}, kind=ResourceKind.SANDBOX
        ))
        stack.push(CompensationItem(
            activity="release_c", args={}, kind=ResourceKind.SKILL_BUNDLE
        ))

        await stack.unwind("test")
        assert "release_c" in released
        assert "release_a" in released
        assert "release_b" not in released
        assert len(failures) == 1
        assert failures[0].item.activity == "release_b"
        assert stack.is_empty

    @pytest.mark.asyncio
    async def test_assert_empty_raises_on_leak(self):
        stack = CompensationStack()
        stack.push(CompensationItem(
            activity="leak", args={}, kind=ResourceKind.SANDBOX
        ))
        with pytest.raises(ResourceLeakError):
            await stack.assert_empty()

    @pytest.mark.asyncio
    async def test_assert_empty_passes_when_empty(self):
        stack = CompensationStack()
        await stack.assert_empty()  # should not raise


# ===========================================================================
# §2: ExecutionSandbox (N5)
# ===========================================================================


class TestExecutionSandbox:
    """不变量 N5: sandbox.state 只能 active → merged | destroyed。"""

    def test_initial_state_active(self):
        s = ExecutionSandbox(task_id="TASK-1")
        assert s.state == SandboxState.ACTIVE

    def test_merge_to_deliverable(self):
        s = ExecutionSandbox(run_id=uuid4(), task_id="TASK-1")
        d = s.merge_to_deliverable(deliverable_type="code", uri="s3://out")
        assert s.state == SandboxState.MERGED
        assert d.deliverable_type == "code"
        assert s.is_output_submittable()

    def test_destroy(self):
        s = ExecutionSandbox(task_id="TASK-1")
        s.destroy(reason="budget_exceeded")
        assert s.state == SandboxState.DESTROYED
        assert not s.is_output_submittable()

    def test_merged_is_terminal(self):
        s = ExecutionSandbox(task_id="TASK-1")
        s.merge_to_deliverable()
        with pytest.raises(IllegalSandboxTransition):
            s.destroy()

    def test_destroyed_is_terminal(self):
        s = ExecutionSandbox(task_id="TASK-1")
        s.destroy()
        with pytest.raises(IllegalSandboxTransition):
            s.merge_to_deliverable()

    def test_active_cannot_remerge(self):
        """Cannot go active → active."""
        s = ExecutionSandbox(task_id="TASK-1")
        # active → active not in valid transitions
        with pytest.raises(IllegalSandboxTransition):
            s._transition_to(SandboxState.ACTIVE)

    def test_destroy_clears_deliverable(self):
        s = ExecutionSandbox(task_id="TASK-1")
        s.destroy()
        assert s.deliverable is None

    @pytest.mark.asyncio
    async def test_sandbox_pool(self):
        pool = SandboxPool()
        sb = await pool.acquire(run_id=uuid4(), task_id="TASK-1")
        assert sb.state == SandboxState.ACTIVE
        await pool.release(sb)
        assert await pool.get(sb.id) is None


# ===========================================================================
# §3: Workflow Happy Path (Draft → Done)
# ===========================================================================


class TestWorkflowHappyPath:
    """Workflow 正常路径测试。"""

    @pytest.mark.asyncio
    async def test_full_happy_path(self):
        """Complete workflow: assembly → execution → verification → done."""
        activities, mocks = _build_activities(
            harness_result=HarnessSyncResult(passed=True)
        )
        wf = TaskExecutionWorkflow(activities=activities)

        mid = uuid4()
        result = await wf.run(task_id="TASK-001", member_id=mid)

        assert result.kind == TaskOutcomeKind.SUCCESS
        # Member concurrency reserved and released
        assert len(mocks["concurrency"].reserved) == 1
        assert len(mocks["concurrency"].released) == 1
        # Context assembled
        assert mocks["assembler"].call_count == 1
        # Executor ran
        assert mocks["executor"].call_count == 1
        # State transitions
        states = [s[1] for s in mocks["state"].states]
        assert "running" in states
        assert "verifying" in states
        assert "in_review" in states
        assert "done" in states
        # Compensation stack empty at terminal (N7)
        assert wf.compensation_stack.is_empty

    @pytest.mark.asyncio
    async def test_happy_path_with_skills(self):
        """Workflow with skill bundle lock/unlock."""
        activities, mocks = _build_activities(
            harness_result=HarnessSyncResult(passed=True)
        )
        wf = TaskExecutionWorkflow(activities=activities)

        skill_ids = [uuid4(), uuid4()]
        result = await wf.run(
            task_id="TASK-002",
            member_id=uuid4(),
            declared_skills=skill_ids,
        )

        assert result.kind == TaskOutcomeKind.SUCCESS
        assert len(mocks["skills"].locked) == 1
        assert len(mocks["skills"].released) == 1
        assert wf.compensation_stack.is_empty


# ===========================================================================
# §4: 补偿栈异常 unwind
# ===========================================================================


class TestCompensationUnwind:
    """补偿栈在异常退出时正确 unwind。"""

    @pytest.mark.asyncio
    async def test_budget_exceeded_unwinds(self):
        """BudgetExceeded during execution → compensation unwinds."""
        activities, mocks = _build_activities(executor_raise=BudgetExceeded)
        wf = TaskExecutionWorkflow(activities=activities)

        result = await wf.run(task_id="TASK-003", member_id=uuid4())

        assert result.kind == TaskOutcomeKind.FAILED
        assert "BudgetExceeded" in result.reason
        # Compensation released
        assert len(mocks["concurrency"].released) == 1
        # Force failed
        assert any(s[1] == "failed" for s in mocks["state"].states)
        assert wf.compensation_stack.is_empty

    @pytest.mark.asyncio
    async def test_sandbox_aborted_unwinds(self):
        """SandboxAborted → compensation unwinds."""
        activities, mocks = _build_activities(executor_raise=SandboxAborted)
        wf = TaskExecutionWorkflow(activities=activities)

        result = await wf.run(task_id="TASK-004", member_id=uuid4())

        assert result.kind == TaskOutcomeKind.FAILED
        assert wf.compensation_stack.is_empty

    @pytest.mark.asyncio
    async def test_generic_exception_unwinds(self):
        """Generic exception → compensation unwinds + force fail."""
        activities, mocks = _build_activities(executor_raise=RuntimeError)
        wf = TaskExecutionWorkflow(activities=activities)

        result = await wf.run(task_id="TASK-005", member_id=uuid4())

        assert result.kind == TaskOutcomeKind.FAILED
        assert wf.compensation_stack.is_empty

    @pytest.mark.asyncio
    async def test_harness_fail_unwinds(self):
        """Harness sync fail → compensation unwinds."""
        activities, mocks = _build_activities(
            harness_result=HarnessSyncResult(passed=False, outcome="fail")
        )
        wf = TaskExecutionWorkflow(activities=activities)

        result = await wf.run(task_id="TASK-006", member_id=uuid4())

        assert result.kind == TaskOutcomeKind.FAILED
        assert result.reason == "harness_failed"
        assert wf.compensation_stack.is_empty

    @pytest.mark.asyncio
    async def test_skill_bundle_released_on_failure(self):
        """Skill bundle released when workflow fails after lock."""
        activities, mocks = _build_activities(executor_raise=BudgetExceeded)
        wf = TaskExecutionWorkflow(activities=activities)

        await wf.run(
            task_id="TASK-007",
            member_id=uuid4(),
            declared_skills=[uuid4()],
        )

        assert len(mocks["skills"].released) == 1
        assert wf.compensation_stack.is_empty


# ===========================================================================
# §5: Signal 机制
# ===========================================================================


class TestSignalMechanism:
    """Signal 正确唤醒 Suspended Workflow。"""

    @pytest.mark.asyncio
    async def test_async_harness_with_signal(self):
        """Async harness → signal callback → workflow resumes."""
        # First call returns async_pending, signal provides the real result
        token = "ct-abc123"
        activities, mocks = _build_activities(
            harness_result=HarnessSyncResult(
                passed=False, is_async_pending=True, callback_token=token
            )
        )
        wf = TaskExecutionWorkflow(activities=activities)

        # Pre-load signal before run (simulating callback arriving quickly)
        wf.harness_callback(HarnessSyncResult(
            passed=True, callback_token=token, outcome="pass"
        ))

        result = await wf.run(task_id="TASK-008", member_id=uuid4())
        assert result.kind == TaskOutcomeKind.SUCCESS

    @pytest.mark.asyncio
    async def test_async_harness_timeout(self):
        """Async harness with no signal → timeout → failed."""
        activities, mocks = _build_activities(
            harness_result=HarnessSyncResult(
                passed=False, is_async_pending=True, callback_token="ct-missing"
            )
        )
        wf = TaskExecutionWorkflow(activities=activities)

        result = await wf.run(task_id="TASK-009", member_id=uuid4())
        assert result.kind == TaskOutcomeKind.FAILED
        assert "harness_timeout" in result.reason


# ===========================================================================
# §6: ContinueAsNew
# ===========================================================================


class TestContinueAsNew:
    """ContinueAsNew 在 50 个 Signal 后触发。"""

    def test_continue_as_new_at_50_signals(self):
        activities, _ = _build_activities()
        wf = TaskExecutionWorkflow(activities=activities)

        for i in range(50):
            wf.harness_callback(HarnessSyncResult(
                passed=True, callback_token=f"ct-{i}"
            ))

        assert wf.needs_continue_as_new is True
        assert wf.checkpoint is not None
        assert wf.checkpoint.signal_count == 50

    def test_no_continue_as_new_under_50(self):
        activities, _ = _build_activities()
        wf = TaskExecutionWorkflow(activities=activities)

        for i in range(49):
            wf.harness_callback(HarnessSyncResult(
                passed=True, callback_token=f"ct-{i}"
            ))

        assert wf.needs_continue_as_new is False


# ===========================================================================
# §7: 不变量 N7 — 终态补偿栈为空
# ===========================================================================


class TestTerminalCompensation:
    """不变量 N7: Workflow 终态时补偿栈必须为空。"""

    @pytest.mark.asyncio
    async def test_success_terminal_empty_stack(self):
        activities, _ = _build_activities(
            harness_result=HarnessSyncResult(passed=True)
        )
        wf = TaskExecutionWorkflow(activities=activities)
        await wf.run(task_id="TASK-N7-1", member_id=uuid4())
        await wf.assert_terminal_clean()

    @pytest.mark.asyncio
    async def test_failure_terminal_empty_stack(self):
        activities, _ = _build_activities(executor_raise=BudgetExceeded)
        wf = TaskExecutionWorkflow(activities=activities)
        await wf.run(task_id="TASK-N7-2", member_id=uuid4())
        await wf.assert_terminal_clean()

    @pytest.mark.asyncio
    async def test_harness_fail_terminal_empty_stack(self):
        activities, _ = _build_activities(
            harness_result=HarnessSyncResult(passed=False)
        )
        wf = TaskExecutionWorkflow(activities=activities)
        await wf.run(task_id="TASK-N7-3", member_id=uuid4())
        await wf.assert_terminal_clean()


# ===========================================================================
# §8: Compensation fitness (arch.md §3.5.3)
# ===========================================================================


class TestCompensationFitness:
    """补偿完整性断言。"""

    @pytest.mark.asyncio
    async def test_every_resource_activity_has_compensation(self):
        """每个占用资源的 Activity 之后都有 push_compensation。

        通过 happy path 验证: reserve → push, lock → push。
        """
        activities, mocks = _build_activities(
            harness_result=HarnessSyncResult(passed=True)
        )
        wf = TaskExecutionWorkflow(activities=activities)

        # With skills
        await wf.run(
            task_id="TASK-FIT",
            member_id=uuid4(),
            declared_skills=[uuid4()],
        )

        # All resources released
        assert len(mocks["concurrency"].released) == 1
        assert len(mocks["skills"].released) == 1
        assert wf.compensation_stack.is_empty
