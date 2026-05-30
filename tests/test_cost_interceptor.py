"""
Execution Context — Cost Interceptor Chain 测试。

验证标准 (plan.md §2.4, arch.md §3.4):
- PreActionBudgetCheck 正确拦截超限操作
- PerActionClassLimit 正确限制单类调用次数
- PermissionRecheck 非交互模式拒绝 bash
- RateLimiter 令牌桶限流
- PostActionAccounting 正确累加成本并触发硬熔断
- StreamingTokenMeter 每 N chunk 检查预算
- CostInterceptorChain 完整链路
- RecallTokenLimiter 召回 token 过载触发压缩
- 层级不变量: 后置 Interceptor 不能放宽前置的 deny
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

from aiteamos_execution.domain.cost_interceptor import (
    Action,
    ActionInvoker,
    ActionKind,
    ActionResult,
    BudgetExceededError,
    BudgetSnapshot,
    CostAccrual,
    CostEstimate,
    CostInterceptorChain,
    Decision,
    PerActionClassLimit,
    PermissionRecheck,
    PostActionAccounting,
    PreActionBudgetCheck,
    RateLimiter,
    RecallTokenLimiter,
    RunContext,
    StreamChunk,
    StreamingTokenMeter,
    create_chain_with_recall_limiter,
    create_default_chain,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(
    *,
    budget: BudgetSnapshot | None = None,
    accrued: CostAccrual | None = None,
    is_interactive: bool = True,
    extra: dict | None = None,
) -> RunContext:
    return RunContext(
        task_id="TASK-20260101T120000000-ABCD",
        run_id=str(uuid4()),
        member_id=str(uuid4()),
        budget=budget or BudgetSnapshot(),
        cost_accrued=accrued or CostAccrual(),
        is_interactive=is_interactive,
        extra=extra or {},
    )


def _make_action(
    *,
    kind: ActionKind = ActionKind.MODEL,
    name: str = "test_action",
    estimate: CostEstimate | None = None,
    executor: AsyncMock | None = None,
    is_streaming: bool = False,
) -> Action:
    return Action(
        kind=kind,
        name=name,
        estimate=estimate or CostEstimate(),
        is_streaming=is_streaming,
        _executor=executor,
    )


# ===========================================================================
# 1. Value Objects 测试
# ===========================================================================


class TestValueObjects:
    """测试值对象。"""

    def test_budget_snapshot_defaults(self):
        budget = BudgetSnapshot()
        assert budget.max_tokens_input == 100_000
        assert budget.max_tokens_output == 50_000
        assert budget.max_compute_cost_usd == Decimal("10.0")
        assert budget.max_tool_calls == 200

    def test_cost_accrual_total_tokens(self):
        accrued = CostAccrual(tokens_input=100, tokens_output=50)
        assert accrued.total_tokens() == 150

    def test_decision_allow(self):
        d = Decision.allow()
        assert not d.is_block

    def test_decision_block(self):
        d = Decision.block("reason")
        assert d.is_block
        assert d.reason == "reason"

    def test_budget_exceeded_error(self):
        err = BudgetExceededError("test reason", dimension="cost")
        assert "test reason" in str(err)
        assert err.dimension == "cost"

    def test_action_result_from_stream(self):
        chunks = [
            StreamChunk(token_count=10, content="hello "),
            StreamChunk(token_count=5, content="world"),
        ]
        result = ActionResult.from_stream(chunks, 15, Decimal("0.01"))
        assert result.tokens_output == 15
        assert result.content == "hello world"


# ===========================================================================
# 2. PreActionBudgetCheck 测试
# ===========================================================================


class TestPreActionBudgetCheck:
    """测试前置预算检查。"""

    @pytest.mark.asyncio
    async def test_allow_when_under_budget(self):
        """未超限 → allow。"""
        check = PreActionBudgetCheck()
        action = _make_action()
        ctx = _make_ctx()

        decision = await check.before(action, ctx)
        assert not decision.is_block

    @pytest.mark.asyncio
    async def test_block_input_tokens_exhausted(self):
        """输入 token 耗尽 → block。"""
        check = PreActionBudgetCheck()
        action = _make_action()
        budget = BudgetSnapshot(max_tokens_input=100)
        accrued = CostAccrual(tokens_input=100)
        ctx = _make_ctx(budget=budget, accrued=accrued)

        decision = await check.before(action, ctx)
        assert decision.is_block
        assert "input_token" in decision.reason

    @pytest.mark.asyncio
    async def test_block_output_tokens_exhausted(self):
        """输出 token 耗尽 → block。"""
        check = PreActionBudgetCheck()
        action = _make_action()
        budget = BudgetSnapshot(max_tokens_output=50)
        accrued = CostAccrual(tokens_output=50)
        ctx = _make_ctx(budget=budget, accrued=accrued)

        decision = await check.before(action, ctx)
        assert decision.is_block
        assert "output_token" in decision.reason

    @pytest.mark.asyncio
    async def test_block_cost_exhausted(self):
        """费用耗尽 → block。"""
        check = PreActionBudgetCheck()
        action = _make_action()
        budget = BudgetSnapshot(max_compute_cost_usd=Decimal("5.0"))
        accrued = CostAccrual(cost_usd=Decimal("5.0"))
        ctx = _make_ctx(budget=budget, accrued=accrued)

        decision = await check.before(action, ctx)
        assert decision.is_block
        assert "cost" in decision.reason

    @pytest.mark.asyncio
    async def test_block_time_exhausted(self):
        """时间耗尽 → block。"""
        check = PreActionBudgetCheck()
        action = _make_action()
        budget = BudgetSnapshot(max_wall_clock_seconds=60.0)
        accrued = CostAccrual(wall_clock_seconds=60.0)
        ctx = _make_ctx(budget=budget, accrued=accrued)

        decision = await check.before(action, ctx)
        assert decision.is_block
        assert "time" in decision.reason

    @pytest.mark.asyncio
    async def test_block_tool_calls_exhausted(self):
        """工具调用次数耗尽 → block。"""
        check = PreActionBudgetCheck()
        action = _make_action()
        budget = BudgetSnapshot(max_tool_calls=10)
        accrued = CostAccrual(tool_calls=10)
        ctx = _make_ctx(budget=budget, accrued=accrued)

        decision = await check.before(action, ctx)
        assert decision.is_block
        assert "tool_call" in decision.reason


# ===========================================================================
# 3. PerActionClassLimit 测试
# ===========================================================================


class TestPerActionClassLimit:
    """测试单类调用上限。"""

    @pytest.mark.asyncio
    async def test_allow_under_limit(self):
        """未达上限 → allow。"""
        limiter = PerActionClassLimit()
        action = _make_action(kind=ActionKind.MODEL)
        ctx = _make_ctx()

        decision = await limiter.before(action, ctx)
        assert not decision.is_block

    @pytest.mark.asyncio
    async def test_block_when_class_limit_reached(self):
        """达到单类上限 → block。"""
        limiter = PerActionClassLimit()
        action = _make_action(kind=ActionKind.BASH)
        ctx = _make_ctx()

        # BASH 上限 = 30
        for _ in range(30):
            await limiter.before(action, ctx)
            await limiter.after(action, ctx, ActionResult(), 0.0)

        decision = await limiter.before(action, ctx)
        assert decision.is_block
        assert "bash" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_different_kinds_counted_separately(self):
        """不同 ActionKind 分别计数。"""
        limiter = PerActionClassLimit()
        ctx = _make_ctx()

        model_action = _make_action(kind=ActionKind.MODEL)
        tool_action = _make_action(kind=ActionKind.TOOL)

        # 各调用 10 次
        for _ in range(10):
            await limiter.before(model_action, ctx)
            await limiter.after(model_action, ctx, ActionResult(), 0.0)
            await limiter.before(tool_action, ctx)
            await limiter.after(tool_action, ctx, ActionResult(), 0.0)

        # 两者都应仍然可用
        assert not (await limiter.before(model_action, ctx)).is_block
        assert not (await limiter.before(tool_action, ctx)).is_block


# ===========================================================================
# 4. PermissionRecheck 测试
# ===========================================================================


class TestPermissionRecheck:
    """测试非交互模式权限复检。"""

    @pytest.mark.asyncio
    async def test_interactive_mode_allows_bash(self):
        """交互模式 → bash 允许。"""
        recheck = PermissionRecheck()
        action = _make_action(kind=ActionKind.BASH)
        ctx = _make_ctx(is_interactive=True)

        decision = await recheck.before(action, ctx)
        assert not decision.is_block

    @pytest.mark.asyncio
    async def test_non_interactive_bash_denied(self):
        """非交互模式 + bash → 拒绝 (Fail-Closed)。"""
        recheck = PermissionRecheck()
        action = _make_action(kind=ActionKind.BASH)
        ctx = _make_ctx(is_interactive=False)

        decision = await recheck.before(action, ctx)
        assert decision.is_block
        assert "bash" in decision.reason.lower()

    @pytest.mark.asyncio
    async def test_non_interactive_bash_explicitly_allowed(self):
        """非交互模式 + allow_bash=True → 允许。"""
        recheck = PermissionRecheck()
        action = _make_action(kind=ActionKind.BASH)
        ctx = _make_ctx(is_interactive=False, extra={"allow_bash": True})

        decision = await recheck.before(action, ctx)
        assert not decision.is_block

    @pytest.mark.asyncio
    async def test_non_interactive_model_allowed(self):
        """非交互模式 + model → 允许。"""
        recheck = PermissionRecheck()
        action = _make_action(kind=ActionKind.MODEL)
        ctx = _make_ctx(is_interactive=False)

        decision = await recheck.before(action, ctx)
        assert not decision.is_block


# ===========================================================================
# 5. PostActionAccounting 测试
# ===========================================================================


class TestPostActionAccounting:
    """测试后置记账和硬熔断。"""

    @pytest.mark.asyncio
    async def test_accounting_accumulates_cost(self):
        """正确累加成本。"""
        accounting = PostActionAccounting()
        action = _make_action(kind=ActionKind.MODEL)
        ctx = _make_ctx()
        result = ActionResult(
            tokens_input=100,
            tokens_output=50,
            cost_usd=Decimal("0.01"),
        )

        await accounting.after(action, ctx, result, 1.5)

        assert ctx.cost_accrued.tokens_input == 100
        assert ctx.cost_accrued.tokens_output == 50
        assert ctx.cost_accrued.cost_usd == Decimal("0.01")
        assert ctx.cost_accrued.wall_clock_seconds == 1.5

    @pytest.mark.asyncio
    async def test_tool_call_accounting(self):
        """TOOL 类型正确累加 tool_calls。"""
        accounting = PostActionAccounting()
        action = _make_action(kind=ActionKind.TOOL)
        ctx = _make_ctx()
        result = ActionResult(tool_calls=3)

        await accounting.after(action, ctx, result, 0.5)

        assert ctx.cost_accrued.tool_calls == 3

    @pytest.mark.asyncio
    async def test_hard_circuit_breaker_triggered(self):
        """成本超限 → 硬熔断 BudgetExceededError。"""
        accounting = PostActionAccounting()
        action = _make_action(kind=ActionKind.MODEL)
        budget = BudgetSnapshot(max_tokens_output=100)
        accrued = CostAccrual(tokens_output=90)
        ctx = _make_ctx(budget=budget, accrued=accrued)

        # 这次结果会增加 20 → 超过 100
        result = ActionResult(tokens_output=20)

        with pytest.raises(BudgetExceededError, match="hard_circuit_breaker"):
            await accounting.after(action, ctx, result, 0.1)

    @pytest.mark.asyncio
    async def test_no_circuit_breaker_under_limit(self):
        """未超限 → 不触发熔断。"""
        accounting = PostActionAccounting()
        action = _make_action(kind=ActionKind.MODEL)
        budget = BudgetSnapshot(max_tokens_output=1000)
        ctx = _make_ctx(budget=budget)

        result = ActionResult(tokens_output=50)

        # 不应抛出异常
        await accounting.after(action, ctx, result, 0.1)
        assert ctx.cost_accrued.tokens_output == 50


# ===========================================================================
# 6. StreamingTokenMeter 测试
# ===========================================================================


class TestStreamingTokenMeter:
    """测试流式 Token 计量器。"""

    def test_record_chunk(self):
        budget = BudgetSnapshot()
        accrued = CostAccrual()
        meter = StreamingTokenMeter(budget, accrued, check_interval=5)

        chunk = StreamChunk(token_count=10, estimated_cost=Decimal("0.001"))
        meter.record_chunk(chunk)

        assert meter.total_tokens == 10
        assert meter._chunk_count == 1

    def test_should_check_interval(self):
        budget = BudgetSnapshot()
        accrued = CostAccrual()
        meter = StreamingTokenMeter(budget, accrued, check_interval=3)

        # 0 chunks: 0 % 3 == 0 → True (初始状态)
        assert meter.should_check()

        meter.record_chunk(StreamChunk())
        assert not meter.should_check()  # 1 chunk: 1 % 3 != 0

        meter.record_chunk(StreamChunk())
        assert not meter.should_check()  # 2 chunks: 2 % 3 != 0

        meter.record_chunk(StreamChunk())
        assert meter.should_check()  # 3 chunks: 3 % 3 == 0 → check

    def test_is_over_budget_tokens(self):
        budget = BudgetSnapshot(max_tokens_output=100)
        accrued = CostAccrual(tokens_output=80)
        meter = StreamingTokenMeter(budget, accrued)

        # 累计 25 → 80 + 25 = 105 > 100
        for _ in range(25):
            meter.record_chunk(StreamChunk(token_count=1))

        assert meter.is_over_budget()

    def test_is_over_budget_cost(self):
        budget = BudgetSnapshot(max_compute_cost_usd=Decimal("1.0"))
        accrued = CostAccrual(cost_usd=Decimal("0.8"))
        meter = StreamingTokenMeter(budget, accrued)

        meter.record_chunk(StreamChunk(estimated_cost=Decimal("0.3")))

        assert meter.is_over_budget()

    def test_not_over_budget(self):
        budget = BudgetSnapshot(max_tokens_output=1000, max_compute_cost_usd=Decimal("10.0"))
        accrued = CostAccrual()
        meter = StreamingTokenMeter(budget, accrued)

        for _ in range(5):
            meter.record_chunk(StreamChunk(token_count=1, estimated_cost=Decimal("0.001")))

        assert not meter.is_over_budget()

    def test_finalize(self):
        budget = BudgetSnapshot()
        accrued = CostAccrual()
        meter = StreamingTokenMeter(budget, accrued)

        meter.record_chunk(StreamChunk(token_count=5, content="hello "))
        meter.record_chunk(StreamChunk(token_count=3, content="world"))

        result = meter.finalize()
        assert result.tokens_output == 8
        assert result.content == "hello world"


# ===========================================================================
# 7. RecallTokenLimiter 测试
# ===========================================================================


class TestRecallTokenLimiter:
    """测试召回 Token 限流器。"""

    @pytest.mark.asyncio
    async def test_compression_triggered_when_over_budget(self):
        """召回 token 超限 → 触发压缩标记。"""
        limiter = RecallTokenLimiter()
        budget = BudgetSnapshot(max_recall_tokens=1000)
        ctx = _make_ctx(budget=budget)

        action = _make_action(
            kind=ActionKind.RECALL,
            estimate=CostEstimate(tokens_input=2000),  # > 1000
        )

        decision = await limiter.before(action, ctx)
        assert not decision.is_block  # 不阻止，只标记压缩
        assert ctx.extra.get("recall_compression_triggered") is True

    @pytest.mark.asyncio
    async def test_no_compression_under_budget(self):
        """召回 token 未超限 → 无压缩标记。"""
        limiter = RecallTokenLimiter()
        budget = BudgetSnapshot(max_recall_tokens=10000)
        ctx = _make_ctx(budget=budget)

        action = _make_action(
            kind=ActionKind.RECALL,
            estimate=CostEstimate(tokens_input=500),
        )

        decision = await limiter.before(action, ctx)
        assert not decision.is_block
        assert ctx.extra.get("recall_compression_triggered") is None

    @pytest.mark.asyncio
    async def test_non_recall_action_not_affected(self):
        """非 RECALL 操作不受影响。"""
        limiter = RecallTokenLimiter()
        ctx = _make_ctx()

        action = _make_action(kind=ActionKind.MODEL)
        decision = await limiter.before(action, ctx)
        assert not decision.is_block

    @pytest.mark.asyncio
    async def test_after_accumulates_recall_tokens(self):
        """after() 正确累加 recall_tokens。"""
        limiter = RecallTokenLimiter()
        ctx = _make_ctx()
        action = _make_action(kind=ActionKind.RECALL)
        result = ActionResult(tokens_output=500)

        await limiter.after(action, ctx, result, 0.1)
        assert ctx.cost_accrued.recall_tokens == 500


# ===========================================================================
# 8. CostInterceptorChain 完整链路测试
# ===========================================================================


class TestCostInterceptorChain:
    """测试 Interceptor 链完整流程。"""

    @pytest.mark.asyncio
    async def test_invoke_success(self):
        """正常执行 → 返回结果。"""
        chain = CostInterceptorChain(interceptors=[
            PreActionBudgetCheck(),
            ActionInvoker(),
            PostActionAccounting(),
        ])

        executor = AsyncMock(return_value=ActionResult(
            tokens_output=10, cost_usd=Decimal("0.001"),
        ))
        action = _make_action(executor=executor)
        ctx = _make_ctx()

        result = await chain.invoke(action, ctx)

        assert result.tokens_output == 10
        assert ctx.cost_accrued.tokens_output == 10

    @pytest.mark.asyncio
    async def test_invoke_blocked_by_budget_check(self):
        """预算超限 → BudgetExceededError。"""
        chain = CostInterceptorChain(interceptors=[
            PreActionBudgetCheck(),
            ActionInvoker(),
            PostActionAccounting(),
        ])

        budget = BudgetSnapshot(max_tokens_input=50)
        accrued = CostAccrual(tokens_input=50)
        ctx = _make_ctx(budget=budget, accrued=accrued)
        action = _make_action()

        with pytest.raises(BudgetExceededError):
            await chain.invoke(action, ctx)

    @pytest.mark.asyncio
    async def test_invoke_executor_error_propagates(self):
        """执行器异常 → 传播异常并调用 on_error。"""
        chain = CostInterceptorChain(interceptors=[
            PreActionBudgetCheck(),
            ActionInvoker(),
            PostActionAccounting(),
        ])

        executor = AsyncMock(side_effect=RuntimeError("boom"))
        action = _make_action(executor=executor)
        ctx = _make_ctx()

        with pytest.raises(RuntimeError, match="boom"):
            await chain.invoke(action, ctx)

    @pytest.mark.asyncio
    async def test_default_chain_creation(self):
        """create_default_chain 创建正确的链。"""
        chain = create_default_chain()
        assert len(chain.chain) == 6

    @pytest.mark.asyncio
    async def test_chain_with_recall_limiter(self):
        """create_chain_with_recall_limiter 包含 RecallTokenLimiter。"""
        chain = create_chain_with_recall_limiter()
        assert len(chain.chain) == 7
        # RecallTokenLimiter 应在 RateLimiter 之前
        types = [type(icpt).__name__ for icpt in chain.chain]
        assert "RecallTokenLimiter" in types

    @pytest.mark.asyncio
    async def test_chain_post_action_hard_breaker(self):
        """执行后成本超限 → 链触发硬熔断。"""
        chain = CostInterceptorChain(interceptors=[
            PreActionBudgetCheck(),
            ActionInvoker(),
            PostActionAccounting(),
        ])

        budget = BudgetSnapshot(max_tokens_output=50)
        accrued = CostAccrual(tokens_output=40)
        ctx = _make_ctx(budget=budget, accrued=accrued)

        executor = AsyncMock(return_value=ActionResult(tokens_output=20))
        action = _make_action(executor=executor)

        # 40 + 20 = 60 > 50 → hard circuit breaker
        with pytest.raises(BudgetExceededError, match="hard_circuit_breaker"):
            await chain.invoke(action, ctx)

    @pytest.mark.asyncio
    async def test_chain_multiple_invocations_accumulate(self):
        """多次调用正确累加成本。"""
        chain = CostInterceptorChain(interceptors=[
            PreActionBudgetCheck(),
            ActionInvoker(),
            PostActionAccounting(),
        ])

        ctx = _make_ctx()
        executor = AsyncMock(return_value=ActionResult(
            tokens_input=10, tokens_output=5, cost_usd=Decimal("0.001"),
        ))

        for _ in range(3):
            action = _make_action(executor=executor)
            await chain.invoke(action, ctx)

        assert ctx.cost_accrued.tokens_input == 30
        assert ctx.cost_accrued.tokens_output == 15
        assert ctx.cost_accrued.cost_usd == Decimal("0.003")

    @pytest.mark.asyncio
    async def test_non_interactive_bash_blocked_in_full_chain(self):
        """非交互模式 bash 在完整链中被 PermissionRecheck 拦截。"""
        chain = CostInterceptorChain(interceptors=[
            PreActionBudgetCheck(),
            PermissionRecheck(),
            ActionInvoker(),
            PostActionAccounting(),
        ])

        ctx = _make_ctx(is_interactive=False)
        action = _make_action(kind=ActionKind.BASH)

        with pytest.raises(BudgetExceededError, match="bash"):
            await chain.invoke(action, ctx)

    @pytest.mark.asyncio
    async def test_action_without_executor(self):
        """无 executor 的 Action → 返回空结果。"""
        chain = CostInterceptorChain(interceptors=[
            PreActionBudgetCheck(),
            ActionInvoker(),
            PostActionAccounting(),
        ])

        action = _make_action()  # no executor
        ctx = _make_ctx()

        result = await chain.invoke(action, ctx)
        assert result.tokens_output == 0


# ===========================================================================
# 9. RateLimiter 测试
# ===========================================================================


class TestRateLimiter:
    """测试令牌桶限流器。"""

    @pytest.mark.asyncio
    async def test_allow_under_rate(self):
        """正常速率 → allow。"""
        limiter = RateLimiter(max_per_second=10.0)
        action = _make_action()
        ctx = _make_ctx()

        decision = await limiter.before(action, ctx)
        assert not decision.is_block

    @pytest.mark.asyncio
    async def test_rapid_calls_eventually_rate_limited(self):
        """快速连续调用 → 最终被限流。"""
        limiter = RateLimiter(max_per_second=2.0)
        action = _make_action()
        ctx = _make_ctx()

        blocked = False
        for _ in range(10):
            decision = await limiter.before(action, ctx)
            if decision.is_block:
                blocked = True
                break

        assert blocked, "Expected rate limiting to kick in"
