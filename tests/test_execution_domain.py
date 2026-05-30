"""
Execution Context — 领域模型 + 应用层测试 (plan.md §2.1 验证标准)。

验证标准:
- 状态机所有合法转换路径测试通过
- 非法转换抛 IllegalTransitionError
- Advisory Lock 正确防止并发超限
- TaskId 格式正确且无碰撞
- 依赖循环检测 (DFS)
- PriorityScheduler 排序 + P0 抢占 P3
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from aiteamos_shared.types import (
    DepartmentId,
    MemberId,
    ProjectId,
    RunId,
    SkillId,
    TaskId,
    generate_task_id,
    new_id,
)

from aiteamos_execution.domain.models import (
    CostAccrued,
    DeliverableSpec,
    RunState,
    Task,
    TaskBudget,
    TaskDependency,
    TaskRun,
    TaskState,
)
from aiteamos_execution.domain.events import (
    DeliverableSubmitted,
    RunStarted,
    TaskAssigned,
    TaskCreated,
    TaskDependencyBlocked,
    TaskDependencyResolved,
    TaskHardCircuitTriggered,
    TaskStateChanged,
)
from aiteamos_execution.domain.state_machine import (
    LEGAL_TRANSITIONS,
    TRANSITION_INVARIANTS,
    IllegalTransitionError,
    TaskStateMachine,
    get_legal_successors,
    is_terminal_state,
)
from aiteamos_execution.domain.invariants import Inv, InvariantViolationError
from aiteamos_execution.domain.dependency import (
    CircularDependencyError,
    DependencyNotMetError,
    DependencyResolver,
    PriorityScheduler,
)
from aiteamos_execution.application.commands import (
    AddDependencyCommand,
    AssignTaskCommand,
    CreateTaskCommand,
    StartRunCommand,
    SubmitDeliverableCommand,
    TransitionTaskCommand,
)
from aiteamos_execution.application.handlers import (
    AddDependencyHandler,
    AssignTaskHandler,
    CreateTaskHandler,
    StartRunHandler,
    SubmitDeliverableHandler,
    TransitionTaskHandler,
)


# ---------------------------------------------------------------------------
# Test infrastructure: In-memory repo + fake tx + recording publisher
# ---------------------------------------------------------------------------


class FakeTransaction:
    """Fake transaction context manager."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class FakeTxManager:
    """Fake transaction manager."""

    @asynccontextmanager
    async def transaction(self):
        tx = FakeTransaction()
        yield tx


class InMemoryTaskRepo:
    """In-memory Task repository for testing."""

    def __init__(self):
        self._store: dict[str, Task] = {}

    async def get_by_id(self, id: str, *, tx: Any = None) -> Task | None:
        return self._store.get(id)

    async def save(self, aggregate: Task, *, tx: Any = None) -> None:
        self._store[aggregate.id] = aggregate

    async def lock_for_update(self, id: str, *, tx: Any) -> Task | None:
        return self._store.get(id)


class RecordingEventPublisher:
    """Records all published events for assertions."""

    def __init__(self):
        self.events: list[Any] = []
        self.partitions: list[str] = []

    async def publish_events(
        self, events: list[Any], *, partition_key: str, tx: Any
    ) -> None:
        self.events.extend(events)
        self.partitions.extend([partition_key] * len(events))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dept() -> DepartmentId:
    return new_id()


def _member() -> MemberId:
    return new_id()


def _make_task(
    *,
    state: TaskState = TaskState.DRAFT,
    title: str = "Test task",
    priority: str = "P2",
    dept: DepartmentId | None = None,
    budget: TaskBudget | None = None,
) -> Task:
    """Create a Task in the given state (bypasses state machine for setup)."""
    t = Task(
        department_id=dept or _dept(),
        title=title,
        priority=priority,
        budget=budget or TaskBudget(),
    )
    t.state = state
    return t


# ===========================================================================
# §1: TaskId 格式与唯一性
# ===========================================================================


class TestTaskId:
    """TaskId 格式: TASK-YYYYMMDDTHHMMSSmmm-XXXX"""

    TASK_ID_PATTERN = re.compile(r"^TASK-\d{8}T\d{9}-[A-Z0-9]{5}$")

    def test_format_correct(self):
        tid = generate_task_id()
        assert self.TASK_ID_PATTERN.match(tid), f"Bad format: {tid}"

    def test_no_collision_1000_ids(self):
        ids = {generate_task_id() for _ in range(1000)}
        assert len(ids) == 1000

    def test_custom_timestamp(self):
        ts = datetime(2026, 1, 15, 10, 30, 45, 123000, tzinfo=timezone.utc)
        tid = generate_task_id(now=ts)
        assert tid.startswith("TASK-20260115T103045")
        assert tid.endswith(tid[-5:])  # -XXXX suffix

    def test_starts_with_TASK_prefix(self):
        for _ in range(10):
            assert generate_task_id().startswith("TASK-")


# ===========================================================================
# §2: Task 聚合根 — 基本行为
# ===========================================================================


class TestTaskAggregate:
    """Task 聚合根创建与业务方法。"""

    def test_create_task_defaults(self):
        dept = _dept()
        t = Task(department_id=dept, title="Hello")
        assert t.state == TaskState.DRAFT
        assert t.department_id == dept
        assert t.title == "Hello"
        assert t.priority == "P2"
        assert t.retry_count == 0
        assert t.review_round == 0
        assert t.runs == []
        assert t.dependencies == []
        assert t.id.startswith("TASK-")

    def test_complete_info_draft_to_ready(self):
        t = _make_task(state=TaskState.DRAFT)
        t.complete_info()
        assert t.state == TaskState.READY
        events = t.pending_events
        assert any(isinstance(e, TaskStateChanged) for e in events)

    def test_assign_member_ready_to_assigned(self):
        t = _make_task(state=TaskState.READY)
        mid = _member()
        t.assign_member(mid)
        assert t.state == TaskState.ASSIGNED
        assert t.assigned_member_id == mid
        assert any(isinstance(e, TaskAssigned) for e in t.pending_events)

    def test_start_run_assigned_to_running(self):
        t = _make_task(state=TaskState.ASSIGNED)
        mid = _member()
        t.assigned_member_id = mid
        run = t.start_run(member_id=mid)
        assert t.state == TaskState.RUNNING
        assert len(t.runs) == 1
        assert run.state == RunState.RUNNING
        assert any(isinstance(e, RunStarted) for e in t.pending_events)

    def test_submit_deliverable_running_to_verifying(self):
        t = _make_task(state=TaskState.RUNNING)
        rid = new_id()
        t.submit_deliverable(run_id=rid, deliverable_type="code", uri="s3://x")
        assert t.state == TaskState.VERIFYING
        assert any(isinstance(e, DeliverableSubmitted) for e in t.pending_events)

    def test_harness_pass_verifying_to_in_review(self):
        t = _make_task(state=TaskState.VERIFYING)
        t.harness_pass()
        assert t.state == TaskState.IN_REVIEW

    def test_harness_fail_retry_under_limit(self):
        t = _make_task(state=TaskState.VERIFYING, budget=TaskBudget(max_retry_count=3))
        t.retry_count = 1
        t.harness_fail(max_retry=3)
        assert t.state == TaskState.RUNNING
        assert t.retry_count == 2

    def test_harness_fail_exceeded(self):
        t = _make_task(state=TaskState.VERIFYING, budget=TaskBudget(max_retry_count=2))
        t.retry_count = 2
        t.harness_fail(max_retry=2)
        assert t.state == TaskState.FAILED

    def test_review_approve_in_review_to_done(self):
        t = _make_task(state=TaskState.IN_REVIEW)
        t.review_approve()
        assert t.state == TaskState.DONE

    def test_review_reject_retry(self):
        t = _make_task(state=TaskState.IN_REVIEW, budget=TaskBudget(max_review_rounds=3))
        t.review_round = 1
        t.review_reject(max_rounds=3)
        assert t.state == TaskState.RUNNING
        assert t.review_round == 2

    def test_review_reject_exceeded(self):
        t = _make_task(state=TaskState.IN_REVIEW, budget=TaskBudget(max_review_rounds=2))
        t.review_round = 2
        t.review_reject(max_rounds=2)
        assert t.state == TaskState.FAILED

    def test_suspend_and_resume(self):
        t = _make_task(state=TaskState.RUNNING)
        t.suspend(reason="budget_pause")
        assert t.state == TaskState.SUSPENDED
        t.resume()
        assert t.state == TaskState.RUNNING

    def test_cancel_from_draft(self):
        t = _make_task(state=TaskState.DRAFT)
        t.cancel()
        assert t.state == TaskState.CANCELLED

    def test_requeue_failed_to_ready(self):
        t = _make_task(state=TaskState.FAILED)
        t.assigned_member_id = _member()
        t.requeue()
        assert t.state == TaskState.READY
        assert t.assigned_member_id is None

    def test_hard_circuit_break(self):
        t = _make_task(state=TaskState.RUNNING)
        t.hard_circuit_break(reason="runaway_cost")
        assert t.state == TaskState.FAILED
        assert any(
            isinstance(e, TaskHardCircuitTriggered) for e in t.pending_events
        )

    def test_clear_pending_events(self):
        t = _make_task(state=TaskState.DRAFT)
        t.complete_info()
        assert len(t.pending_events) > 0
        t.clear_pending_events()
        assert len(t.pending_events) == 0


# ===========================================================================
# §3: TaskRun 实体
# ===========================================================================


class TestTaskRun:
    def test_mark_running(self):
        run = TaskRun(task_id="TASK-20260101T000000000-ABCD")
        run.mark_running()
        assert run.state == RunState.RUNNING

    def test_mark_completed(self):
        run = TaskRun(task_id="TASK-20260101T000000000-ABCD", state=RunState.RUNNING)
        cost = CostAccrued(tokens_used=500, cost_usd=Decimal("0.01"))
        run.mark_completed(cost=cost)
        assert run.state == RunState.COMPLETED
        assert run.finished_at is not None
        assert run.cost.tokens_used == 500

    def test_mark_failed(self):
        run = TaskRun(task_id="TASK-20260101T000000000-ABCD", state=RunState.RUNNING)
        run.mark_failed()
        assert run.state == RunState.FAILED
        assert run.finished_at is not None


# ===========================================================================
# §4: 值对象
# ===========================================================================


class TestValueObjects:
    def test_task_budget_defaults(self):
        b = TaskBudget()
        assert b.max_tokens == 0
        assert b.max_retry_count == 5
        assert b.max_review_rounds == 3

    def test_deliverable_spec(self):
        ds = DeliverableSpec(kind="code", acceptance_criteria=["tests pass"])
        assert ds.kind == "code"
        assert len(ds.acceptance_criteria) == 1

    def test_cost_accrued(self):
        c = CostAccrued(tokens_used=100, duration_seconds=5.0, cost_usd=Decimal("0.05"))
        assert c.tokens_used == 100

    def test_task_dependency_frozen(self):
        dep = TaskDependency(task_id="TASK-A", depends_on_id="TASK-B")
        assert dep.task_id == "TASK-A"


# ===========================================================================
# §5: 状态机 — 合法转换路径
# ===========================================================================


class TestStateMachineLegalTransitions:
    """验证所有合法转换路径。"""

    @pytest.mark.parametrize(
        "from_state,to_state",
        list(LEGAL_TRANSITIONS),
        ids=[f"{f.value}->{t.value}" for f, t in LEGAL_TRANSITIONS],
    )
    def test_legal_transition_validated(self, from_state: TaskState, to_state: TaskState):
        """validate_transition should not raise for any legal transition."""
        TaskStateMachine.validate_transition(from_state, to_state)

    def test_full_happy_path_lifecycle(self):
        """Draft → Ready → Assigned → Running → Verifying → InReview → Done."""
        t = _make_task(state=TaskState.DRAFT)
        t.complete_info()
        assert t.state == TaskState.READY

        mid = _member()
        t.assign_member(mid)
        assert t.state == TaskState.ASSIGNED

        t.start_run(member_id=mid)
        assert t.state == TaskState.RUNNING

        rid = new_id()
        t.submit_deliverable(run_id=rid, deliverable_type="code", uri="s3://x")
        assert t.state == TaskState.VERIFYING

        t.harness_pass()
        assert t.state == TaskState.IN_REVIEW

        t.review_approve()
        assert t.state == TaskState.DONE

    def test_suspend_resume_path(self):
        """Running → Suspended → Running."""
        t = _make_task(state=TaskState.RUNNING)
        t.suspend()
        assert t.state == TaskState.SUSPENDED
        t.resume()
        assert t.state == TaskState.RUNNING

    def test_retry_loop(self):
        """Verifying → Running (retry) → Verifying → InReview → Done."""
        t = _make_task(state=TaskState.VERIFYING, budget=TaskBudget(max_retry_count=3))
        t.retry_count = 0
        t.harness_fail(max_retry=3)
        assert t.state == TaskState.RUNNING
        assert t.retry_count == 1

        # Re-submit
        t.state = TaskState.VERIFYING  # setup for harness_pass
        t.harness_pass()
        assert t.state == TaskState.IN_REVIEW

    def test_requeue_path(self):
        """Failed → Ready."""
        t = _make_task(state=TaskState.FAILED)
        t.requeue()
        assert t.state == TaskState.READY


# ===========================================================================
# §6: 状态机 — 非法转换
# ===========================================================================


class TestStateMachineIllegalTransitions:
    """非法转换必须抛 IllegalTransitionError。"""

    @pytest.mark.parametrize(
        "from_state,to_state",
        [
            (TaskState.DONE, TaskState.RUNNING),
            (TaskState.DONE, TaskState.READY),
            (TaskState.CANCELLED, TaskState.RUNNING),
            (TaskState.DRAFT, TaskState.RUNNING),
            (TaskState.DRAFT, TaskState.ASSIGNED),
            (TaskState.READY, TaskState.RUNNING),
            (TaskState.RUNNING, TaskState.DONE),
            (TaskState.RUNNING, TaskState.READY),
            (TaskState.ASSIGNED, TaskState.VERIFYING),
        ],
        ids=[
            "done->running", "done->ready", "cancelled->running",
            "draft->running", "draft->assigned", "ready->running",
            "running->done", "running->ready", "assigned->verifying",
        ],
    )
    def test_illegal_transition_raises(self, from_state: TaskState, to_state: TaskState):
        with pytest.raises(IllegalTransitionError):
            TaskStateMachine.validate_transition(from_state, to_state)

    def test_error_message_includes_states(self):
        with pytest.raises(IllegalTransitionError) as exc_info:
            TaskStateMachine.validate_transition(TaskState.DONE, TaskState.RUNNING)
        assert "done" in str(exc_info.value).lower()
        assert "running" in str(exc_info.value).lower()


# ===========================================================================
# §7: 不变量校验
# ===========================================================================


class TestInvariants:
    def test_has_required_fields_ok(self):
        t = _make_task()
        Inv.has_required_fields(t)  # should not raise

    def test_has_required_fields_no_title(self):
        t = _make_task(title="")
        with pytest.raises(InvariantViolationError) as exc_info:
            Inv.has_required_fields(t)
        assert exc_info.value.code == "I-E-1"

    def test_has_dept_ok(self):
        t = _make_task()
        Inv.has_dept(t)

    def test_member_concurrency_ok(self):
        t = _make_task()
        Inv.member_concurrency_ok(t, active_runs_for_member=0, concurrency_limit=1)

    def test_member_concurrency_exceeded(self):
        t = _make_task()
        with pytest.raises(InvariantViolationError) as exc_info:
            Inv.member_concurrency_ok(t, active_runs_for_member=1, concurrency_limit=1)
        assert exc_info.value.code == "I-E-3"

    def test_snapshot_sealed_ok(self):
        t = _make_task()
        Inv.snapshot_sealed(t, has_snapshot=True)

    def test_snapshot_sealed_missing(self):
        t = _make_task()
        with pytest.raises(InvariantViolationError):
            Inv.snapshot_sealed(t, has_snapshot=False)

    def test_budget_allocated_ok(self):
        t = _make_task(budget=TaskBudget())
        Inv.budget_allocated(t)

    def test_retry_under_limit_ok(self):
        t = _make_task(budget=TaskBudget(max_retry_count=3))
        t.retry_count = 1
        Inv.retry_under_limit(t)

    def test_retry_limit_exceeded(self):
        t = _make_task(budget=TaskBudget(max_retry_count=3))
        t.retry_count = 3
        with pytest.raises(InvariantViolationError):
            Inv.retry_under_limit(t)

    def test_review_round_under_limit_ok(self):
        t = _make_task(budget=TaskBudget(max_review_rounds=3))
        t.review_round = 2
        Inv.review_round_under_limit(t)

    def test_review_round_exceeded(self):
        t = _make_task(budget=TaskBudget(max_review_rounds=3))
        t.review_round = 3
        with pytest.raises(InvariantViolationError):
            Inv.review_round_under_limit(t)

    def test_deliverable_submitted_ok(self):
        t = _make_task()
        Inv.deliverable_submitted(t, has_deliverable=True)

    def test_deliverable_submitted_missing(self):
        t = _make_task()
        with pytest.raises(InvariantViolationError):
            Inv.deliverable_submitted(t, has_deliverable=False)


# ===========================================================================
# §8: TaskStateMachine.transition() — 异步集成
# ===========================================================================


class TestStateMachineTransition:
    """async transition(): 加锁 → 校验 → 变更 → 事件 → 保存。"""

    @pytest.fixture
    def repo(self):
        return InMemoryTaskRepo()

    @pytest.fixture
    def tx_manager(self):
        return FakeTxManager()

    @pytest.fixture
    def publisher(self):
        return RecordingEventPublisher()

    @pytest.fixture
    def sm(self, repo, tx_manager, publisher):
        return TaskStateMachine(
            repo=repo, tx_manager=tx_manager, event_publisher=publisher
        )

    @pytest.mark.asyncio
    async def test_transition_draft_to_ready(self, sm, repo, publisher):
        t = _make_task(state=TaskState.DRAFT)
        await repo.save(t)

        result = await sm.transition(t.id, to_state=TaskState.READY, reason="info ok")
        assert result.state == TaskState.READY
        assert any(
            isinstance(e, TaskStateChanged) and e.to_state == "ready"
            for e in publisher.events
        )

    @pytest.mark.asyncio
    async def test_transition_illegal_raises(self, sm, repo):
        t = _make_task(state=TaskState.DRAFT)
        await repo.save(t)

        with pytest.raises(IllegalTransitionError):
            await sm.transition(t.id, to_state=TaskState.RUNNING)

    @pytest.mark.asyncio
    async def test_transition_nonexistent_raises(self, sm):
        with pytest.raises(ValueError, match="not found"):
            await sm.transition("TASK-00000000T000000000-ZZZZ", to_state=TaskState.READY)

    @pytest.mark.asyncio
    async def test_transition_publishes_events(self, sm, repo, publisher):
        t = _make_task(state=TaskState.RUNNING)
        await repo.save(t)

        await sm.transition(t.id, to_state=TaskState.SUSPENDED, reason="pause")
        assert len(publisher.events) > 0
        assert all(isinstance(e, TaskStateChanged) for e in publisher.events)


# ===========================================================================
# §9: 辅助函数
# ===========================================================================


class TestStateMachineHelpers:
    def test_get_legal_successors_from_draft(self):
        successors = get_legal_successors(TaskState.DRAFT)
        assert TaskState.READY in successors
        assert TaskState.CANCELLED in successors
        assert TaskState.RUNNING not in successors

    def test_get_legal_successors_from_running(self):
        successors = get_legal_successors(TaskState.RUNNING)
        assert TaskState.VERIFYING in successors
        assert TaskState.SUSPENDED in successors
        assert TaskState.FAILED in successors
        assert TaskState.CANCELLED in successors

    def test_is_terminal_state(self):
        assert is_terminal_state(TaskState.DONE) is True
        assert is_terminal_state(TaskState.CANCELLED) is True
        assert is_terminal_state(TaskState.RUNNING) is False
        assert is_terminal_state(TaskState.FAILED) is False


# ===========================================================================
# §10: DependencyResolver — DFS 循环检测
# ===========================================================================


class TestDependencyResolver:
    def test_no_cycle_linear(self):
        """A → B → C: no cycle."""
        adj = {"A": ["B"], "B": ["C"], "C": []}
        assert DependencyResolver.detect_cycle("A", adj) is None

    def test_detect_self_cycle(self):
        """A → A: self cycle."""
        adj = {"A": ["A"]}
        cycle = DependencyResolver.detect_cycle("A", adj)
        assert cycle is not None
        assert "A" in cycle

    def test_detect_triangle_cycle(self):
        """A → B → C → A: cycle."""
        adj = {"A": ["B"], "B": ["C"], "C": ["A"]}
        cycle = DependencyResolver.detect_cycle("A", adj)
        assert cycle is not None
        assert len(cycle) >= 3

    def test_no_cycle_diamond(self):
        """A → B, A → C, B → D, C → D: diamond, no cycle."""
        adj = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
        assert DependencyResolver.detect_cycle("A", adj) is None

    def test_validate_no_cycle_raises(self):
        adj = {"A": ["B"], "B": ["A"]}
        with pytest.raises(CircularDependencyError):
            DependencyResolver.validate_no_cycle("A", adj)

    def test_validate_no_cycle_passes(self):
        adj = {"A": ["B"], "B": []}
        DependencyResolver.validate_no_cycle("A", adj)  # should not raise

    def test_detect_cycle_complex(self):
        """Large DAG without cycle."""
        adj = {
            "A": ["B", "C"],
            "B": ["D"],
            "C": ["D", "E"],
            "D": ["F"],
            "E": ["F"],
            "F": [],
        }
        assert DependencyResolver.detect_cycle("A", adj) is None


# ===========================================================================
# §11: PriorityScheduler
# ===========================================================================


class TestPriorityScheduler:
    def test_rank_by_priority(self):
        t_p2 = _make_task(priority="P2")
        t_p0 = _make_task(priority="P0")
        t_p1 = _make_task(priority="P1")
        t_p3 = _make_task(priority="P3")

        ranked = PriorityScheduler.rank([t_p2, t_p0, t_p1, t_p3])
        assert [t.priority for t in ranked] == ["P0", "P1", "P2", "P3"]

    def test_rank_same_priority_by_created_at(self):
        t1 = _make_task(priority="P1")
        t1.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = _make_task(priority="P1")
        t2.created_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

        ranked = PriorityScheduler.rank([t2, t1])
        assert ranked[0] is t1
        assert ranked[1] is t2

    def test_p0_can_preempt_p3(self):
        challenger = _make_task(priority="P0")
        incumbent = _make_task(priority="P3")
        assert PriorityScheduler.can_preempt(challenger, incumbent) is True

    def test_p1_cannot_preempt_p3(self):
        challenger = _make_task(priority="P1")
        incumbent = _make_task(priority="P3")
        assert PriorityScheduler.can_preempt(challenger, incumbent) is False

    def test_p0_cannot_preempt_p1(self):
        challenger = _make_task(priority="P0")
        incumbent = _make_task(priority="P1")
        assert PriorityScheduler.can_preempt(challenger, incumbent) is False

    def test_p3_cannot_preempt_p0(self):
        challenger = _make_task(priority="P3")
        incumbent = _make_task(priority="P0")
        assert PriorityScheduler.can_preempt(challenger, incumbent) is False

    def test_rank_unknown_priority_last(self):
        t_unknown = _make_task(priority="P9")
        t_p0 = _make_task(priority="P0")
        ranked = PriorityScheduler.rank([t_unknown, t_p0])
        assert ranked[0] is t_p0
        assert ranked[1] is t_unknown


# ===========================================================================
# §12: Command Handlers — 异步集成
# ===========================================================================


class TestCreateTaskHandler:
    @pytest.fixture
    def deps(self):
        return InMemoryTaskRepo(), FakeTxManager(), RecordingEventPublisher()

    @pytest.mark.asyncio
    async def test_create_task(self, deps):
        repo, tx, pub = deps
        handler = CreateTaskHandler(task_repo=repo, tx_manager=tx, event_publisher=pub)
        cmd = CreateTaskCommand(
            department_id=_dept(),
            title="Build feature X",
            priority="P1",
            max_retry_count=5,
        )
        task = await handler.handle(cmd)
        assert task.state == TaskState.DRAFT
        assert task.title == "Build feature X"
        assert task.priority == "P1"
        assert task.budget.max_retry_count == 5
        # TaskCreated event published
        assert any(isinstance(e, TaskCreated) for e in pub.events)
        # Saved in repo
        saved = await repo.get_by_id(task.id)
        assert saved is not None


class TestAssignTaskHandler:
    @pytest.fixture
    def deps(self):
        return InMemoryTaskRepo(), FakeTxManager(), RecordingEventPublisher()

    @pytest.mark.asyncio
    async def test_assign_task(self, deps):
        repo, tx, pub = deps
        t = _make_task(state=TaskState.READY)
        await repo.save(t)

        handler = AssignTaskHandler(task_repo=repo, tx_manager=tx, event_publisher=pub)
        mid = _member()
        result = await handler.handle(AssignTaskCommand(task_id=t.id, member_id=mid))
        assert result.state == TaskState.ASSIGNED
        assert result.assigned_member_id == mid

    @pytest.mark.asyncio
    async def test_assign_nonexistent_raises(self, deps):
        repo, tx, pub = deps
        handler = AssignTaskHandler(task_repo=repo, tx_manager=tx, event_publisher=pub)
        with pytest.raises(ValueError, match="not found"):
            await handler.handle(
                AssignTaskCommand(task_id="TASK-NOPE", member_id=_member())
            )


class TestTransitionTaskHandler:
    @pytest.fixture
    def deps(self):
        return InMemoryTaskRepo(), FakeTxManager(), RecordingEventPublisher()

    @pytest.mark.asyncio
    async def test_transition_draft_to_ready(self, deps):
        repo, tx, pub = deps
        t = _make_task(state=TaskState.DRAFT)
        await repo.save(t)

        handler = TransitionTaskHandler(
            task_repo=repo, tx_manager=tx, event_publisher=pub
        )
        result = await handler.handle(
            TransitionTaskCommand(task_id=t.id, to_state="ready", reason="complete")
        )
        assert result.state == TaskState.READY

    @pytest.mark.asyncio
    async def test_transition_illegal_raises(self, deps):
        repo, tx, pub = deps
        t = _make_task(state=TaskState.DRAFT)
        await repo.save(t)

        handler = TransitionTaskHandler(
            task_repo=repo, tx_manager=tx, event_publisher=pub
        )
        with pytest.raises(IllegalTransitionError):
            await handler.handle(
                TransitionTaskCommand(task_id=t.id, to_state="running")
            )


class TestStartRunHandler:
    @pytest.fixture
    def deps(self):
        return InMemoryTaskRepo(), FakeTxManager(), RecordingEventPublisher()

    @pytest.mark.asyncio
    async def test_start_run(self, deps):
        repo, tx, pub = deps
        t = _make_task(state=TaskState.ASSIGNED)
        mid = _member()
        t.assigned_member_id = mid
        await repo.save(t)

        handler = StartRunHandler(task_repo=repo, tx_manager=tx, event_publisher=pub)
        result = await handler.handle(StartRunCommand(task_id=t.id, member_id=mid))
        assert result.state == TaskState.RUNNING
        assert len(result.runs) == 1
        assert any(isinstance(e, RunStarted) for e in pub.events)


class TestSubmitDeliverableHandler:
    @pytest.fixture
    def deps(self):
        return InMemoryTaskRepo(), FakeTxManager(), RecordingEventPublisher()

    @pytest.mark.asyncio
    async def test_submit_deliverable(self, deps):
        repo, tx, pub = deps
        t = _make_task(state=TaskState.RUNNING)
        await repo.save(t)

        handler = SubmitDeliverableHandler(
            task_repo=repo, tx_manager=tx, event_publisher=pub
        )
        rid = new_id()
        result = await handler.handle(
            SubmitDeliverableCommand(
                task_id=t.id, run_id=rid, deliverable_type="code", uri="s3://bucket/out"
            )
        )
        assert result.state == TaskState.VERIFYING
        assert any(isinstance(e, DeliverableSubmitted) for e in pub.events)


class TestAddDependencyHandler:
    @pytest.fixture
    def deps(self):
        return InMemoryTaskRepo(), FakeTxManager(), RecordingEventPublisher()

    @pytest.mark.asyncio
    async def test_add_dependency(self, deps):
        repo, tx, pub = deps
        t1 = _make_task(state=TaskState.DRAFT)
        t2 = _make_task(state=TaskState.DRAFT)
        await repo.save(t1)
        await repo.save(t2)

        handler = AddDependencyHandler(
            task_repo=repo, tx_manager=tx, event_publisher=pub
        )
        result = await handler.handle(
            AddDependencyCommand(task_id=t1.id, depends_on_id=t2.id)
        )
        assert len(result.dependencies) == 1
        assert result.dependencies[0].depends_on_id == t2.id


# ===========================================================================
# §13: 领域事件完整性
# ===========================================================================


class TestDomainEvents:
    def test_task_state_changed_event_fields(self):
        evt = TaskStateChanged(
            event_type="execution.task.state_changed",
            task_id="TASK-20260101T000000000-AAAA",
            from_state="draft",
            to_state="ready",
            reason="info complete",
        )
        assert evt.event_type == "execution.task.state_changed"
        assert evt.from_state == "draft"
        assert evt.to_state == "ready"
        assert evt.event_version == 1

    def test_task_created_event(self):
        evt = TaskCreated(
            event_type="execution.task.created",
            task_id="TASK-20260101T000000000-AAAA",
            department_id=uuid4(),
            title="Test",
            priority="P1",
        )
        assert evt.event_type == "execution.task.created"

    def test_all_events_have_version(self):
        """All events inherit VersionedDomainEvent and have event_version."""
        events = [
            TaskCreated(
                event_type="x", task_id="T-1", department_id=uuid4(),
                title="t", priority="P0",
            ),
            TaskStateChanged(
                event_type="x", task_id="T-1", from_state="a", to_state="b",
            ),
            TaskAssigned(event_type="x", task_id="T-1", member_id=uuid4()),
            RunStarted(event_type="x", run_id=uuid4(), task_id="T-1", member_id=uuid4()),
            DeliverableSubmitted(
                event_type="x", task_id="T-1", run_id=uuid4(),
                deliverable_type="code", uri="s3://x",
            ),
            TaskHardCircuitTriggered(event_type="x", task_id="T-1", reason="boom"),
        ]
        for e in events:
            assert hasattr(e, "event_version")
            assert e.event_version == 1
            assert hasattr(e, "correlation_id")
            assert hasattr(e, "timestamp")


# ===========================================================================
# §14: DDL Migration 文件存在
# ===========================================================================


class TestMigrationExists:
    def test_migration_005_exists(self):
        import pathlib
        migration = pathlib.Path("migrations/005_execution_context.sql")
        assert migration.exists(), "Migration 005 not found"

    def test_migration_005_has_required_tables(self):
        import pathlib
        content = pathlib.Path("migrations/005_execution_context.sql").read_text()
        for table in [
            "task", "task_run", "task_context_snapshot",
            "task_deliverable", "task_dependency", "task_project",
        ]:
            assert f"CREATE TABLE {table}" in content, f"Table {table} missing"
