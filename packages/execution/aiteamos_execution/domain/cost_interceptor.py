"""
Execution Context — Cost Interceptor Chain (arch.md §3.4)。

多维度成本预算控制 + 流式 Token 计量。
Chain of Responsibility 模式，层级不变量：后置 Interceptor 不能放宽前置的 deny。

默认链:
PreActionBudgetCheck → PerActionClassLimit → PermissionRecheck →
RateLimiter → ActionInvoker → PostActionAccounting
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class BudgetExceededError(Exception):
    """预算超限 — 触发硬熔断。"""

    def __init__(self, reason: str, *, dimension: str = ""):
        self.reason = reason
        self.dimension = dimension
        super().__init__(f"Budget exceeded: {reason} (dimension={dimension})")


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


class ActionKind(StrEnum):
    """调用类别。"""
    MODEL = "model"
    TOOL = "tool"
    BASH = "bash"
    RECALL = "recall"


@dataclass(frozen=True)
class CostEstimate:
    """单次调用成本预估。"""
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: Decimal = Decimal("0")
    tool_calls: int = 0


@dataclass
class BudgetSnapshot:
    """7 维度预算（arch.md §3.4.1）。"""
    max_tokens_input: int = 100_000
    max_tokens_output: int = 50_000
    max_wall_clock_seconds: float = 3600.0
    max_compute_cost_usd: Decimal = Decimal("10.0")
    max_tool_calls: int = 200
    max_recall_tokens: int = 30_000
    max_retry_rounds: int = 3
    max_review_rounds: int = 3


@dataclass
class CostAccrual:
    """累计成本（运行时可变）。"""
    tokens_input: int = 0
    tokens_output: int = 0
    wall_clock_seconds: float = 0.0
    cost_usd: Decimal = Decimal("0")
    tool_calls: int = 0
    recall_tokens: int = 0

    def total_tokens(self) -> int:
        return self.tokens_input + self.tokens_output


@dataclass(frozen=True)
class Decision:
    """Interceptor 决策结果。"""
    is_block: bool
    reason: str = ""

    @staticmethod
    def allow() -> Decision:
        return Decision(is_block=False)

    @staticmethod
    def block(reason: str) -> Decision:
        return Decision(is_block=True, reason=reason)


@dataclass
class Action:
    """执行单元 — 每次 model/tool/bash 调用的抽象。"""
    kind: ActionKind
    name: str
    estimate: CostEstimate = field(default_factory=CostEstimate)
    is_streaming: bool = False
    _executor: Any = field(default=None, repr=False)

    async def execute(self) -> ActionResult:
        if self._executor:
            return await self._executor()
        return ActionResult(tokens_output=0, cost_usd=Decimal("0"))

    async def execute_streaming(self):
        """异步生成器 — 流式输出 chunk。"""
        if self._executor:
            async for chunk in self._executor():
                yield chunk

    async def cancel_stream(self) -> None:
        """取消流式输出。"""
        pass


@dataclass
class StreamChunk:
    """流式响应的单个 chunk。"""
    token_count: int = 1
    estimated_cost: Decimal = Decimal("0")
    content: str = ""


@dataclass
class ActionResult:
    """执行结果。"""
    tokens_output: int = 0
    tokens_input: int = 0
    cost_usd: Decimal = Decimal("0")
    tool_calls: int = 0
    elapsed_seconds: float = 0.0
    content: str = ""

    @staticmethod
    def from_stream(
        chunks: list[StreamChunk],
        total_tokens: int,
        total_cost: Decimal,
    ) -> ActionResult:
        return ActionResult(
            tokens_output=total_tokens,
            cost_usd=total_cost,
            content="".join(c.content for c in chunks),
        )


@dataclass
class RunContext:
    """执行上下文 — 贯穿整个 Interceptor 链。"""
    task_id: str
    run_id: str
    member_id: str
    budget: BudgetSnapshot
    cost_accrued: CostAccrual
    is_interactive: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Interceptor Protocol
# ---------------------------------------------------------------------------


class Interceptor(Protocol):
    """Interceptor 协议 — Chain of Responsibility 中的处理节点。"""

    async def before(self, action: Action, ctx: RunContext) -> Decision:
        """前置检查。返回 Decision.block 则中断链。"""
        ...

    async def after(
        self,
        action: Action,
        ctx: RunContext,
        result: ActionResult,
        elapsed: float,
    ) -> None:
        """后置记账 / 熔断检查。"""
        ...

    async def on_error(
        self, action: Action, ctx: RunContext, error: Exception
    ) -> None:
        """执行异常时的清理钩子。"""
        ...


# ---------------------------------------------------------------------------
# StreamingTokenMeter (arch.md §3.4.2)
# ---------------------------------------------------------------------------


class StreamingTokenMeter:
    """LLM Streaming 场景下的实时 Token 计量器。

    每累计 check_interval 个 chunk 检查一次预算，
    超限时取消流并抛出 BudgetExceededError。
    """

    def __init__(
        self,
        budget: BudgetSnapshot,
        accrued: CostAccrual,
        check_interval: int = 10,
    ):
        self.budget = budget
        self.accrued = accrued
        self.check_interval = check_interval
        self.total_tokens: int = 0
        self.total_cost_usd: Decimal = Decimal("0")
        self._chunk_count: int = 0
        self._chunks: list[StreamChunk] = []

    def record_chunk(self, chunk: StreamChunk) -> None:
        self._chunk_count += 1
        self.total_tokens += chunk.token_count
        self.total_cost_usd += chunk.estimated_cost
        self._chunks.append(chunk)

    def should_check(self) -> bool:
        return self._chunk_count % self.check_interval == 0

    def is_over_budget(self) -> bool:
        return (
            self.accrued.tokens_output + self.total_tokens
            >= self.budget.max_tokens_output
            or self.accrued.cost_usd + self.total_cost_usd
            >= self.budget.max_compute_cost_usd
        )

    def finalize(self) -> ActionResult:
        return ActionResult.from_stream(
            chunks=self._chunks,
            total_tokens=self.total_tokens,
            total_cost=self.total_cost_usd,
        )


# ---------------------------------------------------------------------------
# 具体 Interceptor 实现
# ---------------------------------------------------------------------------


class PreActionBudgetCheck:
    """1. 累计成本 vs Budget — 任一维度突破即 block (arch.md §3.4.3)。"""

    async def before(self, action: Action, ctx: RunContext) -> Decision:
        accrued = ctx.cost_accrued
        budget = ctx.budget

        if accrued.tokens_input >= budget.max_tokens_input:
            return Decision.block("input_token_exhausted")
        if accrued.tokens_output >= budget.max_tokens_output:
            return Decision.block("output_token_exhausted")
        if accrued.cost_usd >= budget.max_compute_cost_usd:
            return Decision.block("cost_exhausted")
        if accrued.wall_clock_seconds >= budget.max_wall_clock_seconds:
            return Decision.block("time_exhausted")
        if accrued.tool_calls >= budget.max_tool_calls:
            return Decision.block("tool_call_exhausted")

        return Decision.allow()

    async def after(self, action: Action, ctx: RunContext, result: ActionResult, elapsed: float) -> None:
        pass

    async def on_error(self, action: Action, ctx: RunContext, error: Exception) -> None:
        pass


class PerActionClassLimit:
    """2. 单类调用上限检查。"""

    CLASS_LIMITS: dict[ActionKind, int] = {
        ActionKind.MODEL: 100,
        ActionKind.TOOL: 50,
        ActionKind.BASH: 30,
        ActionKind.RECALL: 10,
    }

    def __init__(self) -> None:
        self._counts: dict[ActionKind, int] = {k: 0 for k in ActionKind}

    async def before(self, action: Action, ctx: RunContext) -> Decision:
        count = self._counts.get(action.kind, 0)
        limit = self.CLASS_LIMITS.get(action.kind, 100)
        if count >= limit:
            return Decision.block(f"{action.kind}_class_limit_exhausted")
        return Decision.allow()

    async def after(self, action: Action, ctx: RunContext, result: ActionResult, elapsed: float) -> None:
        self._counts[action.kind] = self._counts.get(action.kind, 0) + 1

    async def on_error(self, action: Action, ctx: RunContext, error: Exception) -> None:
        pass


class PermissionRecheck:
    """3. 非交互模式下重新评估 — ask → deny (arch.md 纪律 #8)。"""

    async def before(self, action: Action, ctx: RunContext) -> Decision:
        if not ctx.is_interactive and action.kind == ActionKind.BASH:
            # 非交互模式下 bash 操作默认拒绝（Fail-Closed）
            if ctx.extra.get("allow_bash", False) is not True:
                return Decision.block("non_interactive_bash_denied")
        return Decision.allow()

    async def after(self, action: Action, ctx: RunContext, result: ActionResult, elapsed: float) -> None:
        pass

    async def on_error(self, action: Action, ctx: RunContext, error: Exception) -> None:
        pass


class RateLimiter:
    """4. 令牌桶限流 — 防止短时间大量调用。"""

    def __init__(self, max_per_second: float = 10.0):
        self._max_rate = max_per_second
        self._tokens = max_per_second
        self._last_refill = time.monotonic()

    async def before(self, action: Action, ctx: RunContext) -> Decision:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_rate, self._tokens + elapsed * self._max_rate)
        self._last_refill = now

        if self._tokens < 1.0:
            return Decision.block("rate_limited")
        self._tokens -= 1.0
        return Decision.allow()

    async def after(self, action: Action, ctx: RunContext, result: ActionResult, elapsed: float) -> None:
        pass

    async def on_error(self, action: Action, ctx: RunContext, error: Exception) -> None:
        pass


class ActionInvoker:
    """5. 实际调用执行器。"""

    async def before(self, action: Action, ctx: RunContext) -> Decision:
        return Decision.allow()

    async def after(self, action: Action, ctx: RunContext, result: ActionResult, elapsed: float) -> None:
        pass

    async def on_error(self, action: Action, ctx: RunContext, error: Exception) -> None:
        pass


class PostActionAccounting:
    """6. 后置记账 + 硬熔断触发检查。"""

    async def before(self, action: Action, ctx: RunContext) -> Decision:
        return Decision.allow()

    async def after(
        self,
        action: Action,
        ctx: RunContext,
        result: ActionResult,
        elapsed: float,
    ) -> None:
        # 累加成本
        ctx.cost_accrued.tokens_input += result.tokens_input
        ctx.cost_accrued.tokens_output += result.tokens_output
        ctx.cost_accrued.cost_usd += result.cost_usd
        ctx.cost_accrued.wall_clock_seconds += elapsed
        if action.kind == ActionKind.TOOL:
            ctx.cost_accrued.tool_calls += result.tool_calls or 1

        # 硬熔断检查
        if self._is_hard_breach(ctx):
            kind = self._breach_kind(ctx)
            logger.warning(
                "Hard circuit breaker triggered for task=%s run=%s: %s",
                ctx.task_id, ctx.run_id, kind,
            )
            raise BudgetExceededError(
                f"hard_circuit_breaker: {kind}",
                dimension=kind,
            )

    async def on_error(self, action: Action, ctx: RunContext, error: Exception) -> None:
        pass

    @staticmethod
    def _is_hard_breach(ctx: RunContext) -> bool:
        a, b = ctx.cost_accrued, ctx.budget
        return (
            a.tokens_input >= b.max_tokens_input
            or a.tokens_output >= b.max_tokens_output
            or a.cost_usd >= b.max_compute_cost_usd
            or a.wall_clock_seconds >= b.max_wall_clock_seconds
            or a.tool_calls >= b.max_tool_calls
        )

    @staticmethod
    def _breach_kind(ctx: RunContext) -> str:
        a, b = ctx.cost_accrued, ctx.budget
        if a.tokens_input >= b.max_tokens_input:
            return "input_token_exhausted"
        if a.tokens_output >= b.max_tokens_output:
            return "output_token_exhausted"
        if a.cost_usd >= b.max_compute_cost_usd:
            return "cost_exhausted"
        if a.wall_clock_seconds >= b.max_wall_clock_seconds:
            return "time_exhausted"
        if a.tool_calls >= b.max_tool_calls:
            return "tool_call_exhausted"
        return "unknown"


# ---------------------------------------------------------------------------
# RecallTokenLimiter (arch.md §3.4.4)
# ---------------------------------------------------------------------------


class RecallTokenLimiter:
    """Context Assembler 的最后一道闸门 — 召回 Token 过载时触发摘要压缩。"""

    async def before(self, action: Action, ctx: RunContext) -> Decision:
        if action.kind == ActionKind.RECALL:
            est_tokens = action.estimate.tokens_input
            if est_tokens > ctx.budget.max_recall_tokens:
                # 触发压缩（通过 extra 标记传递给 Context Assembler）
                ctx.extra["recall_compression_triggered"] = True
                logger.warning(
                    "Recall compression triggered for task=%s: est=%d > budget=%d",
                    ctx.task_id, est_tokens, ctx.budget.max_recall_tokens,
                )
        return Decision.allow()

    async def after(self, action: Action, ctx: RunContext, result: ActionResult, elapsed: float) -> None:
        if action.kind == ActionKind.RECALL:
            ctx.cost_accrued.recall_tokens += result.tokens_output

    async def on_error(self, action: Action, ctx: RunContext, error: Exception) -> None:
        pass


# ---------------------------------------------------------------------------
# CostInterceptorChain — 链编排 (arch.md §3.4.2)
# ---------------------------------------------------------------------------


class CostInterceptorChain:
    """Cost Interceptor 链 — Chain of Responsibility。

    顺序固定：预检 → 类别限额 → 权限复检 → 限流 → 调用 → 后置记账。
    层级不变量：后置 Interceptor 不能放宽前置的 deny。
    """

    def __init__(self, interceptors: list[Any] | None = None):
        if interceptors is None:
            self.chain = [
                PreActionBudgetCheck(),
                PerActionClassLimit(),
                PermissionRecheck(),
                RateLimiter(),
                ActionInvoker(),
                PostActionAccounting(),
            ]
        else:
            self.chain = interceptors

    async def invoke(self, action: Action, ctx: RunContext) -> ActionResult:
        """执行 Action 并通过全链拦截。

        Raises:
            BudgetExceededError: 预算超限触发硬熔断
        """
        # 前置拦截
        for icpt in self.chain:
            decision = await icpt.before(action, ctx)
            if decision.is_block:
                raise BudgetExceededError(decision.reason, dimension=decision.reason)

        # 执行
        start = time.monotonic()
        try:
            if action.is_streaming:
                result = await self._invoke_with_streaming_meter(action, ctx)
            else:
                result = await action.execute()
        except BudgetExceededError:
            raise
        except Exception as e:
            for icpt in reversed(self.chain):
                await icpt.on_error(action, ctx, e)
            raise
        else:
            elapsed = time.monotonic() - start
            result.elapsed_seconds = elapsed
            for icpt in reversed(self.chain):
                await icpt.after(action, ctx, result, elapsed)
            return result

    async def _invoke_with_streaming_meter(
        self, action: Action, ctx: RunContext
    ) -> ActionResult:
        """Mid-stream Token Meter — 流式响应每 N chunk 检查预算。"""
        meter = StreamingTokenMeter(
            budget=ctx.budget,
            accrued=ctx.cost_accrued,
            check_interval=10,
        )
        async for chunk in action.execute_streaming():
            meter.record_chunk(chunk)
            if meter.should_check():
                if meter.is_over_budget():
                    await action.cancel_stream()
                    raise BudgetExceededError(
                        f"streaming_overshoot: accrued={meter.total_tokens}, "
                        f"budget={ctx.budget.max_tokens_output}",
                        dimension="output_token_exhausted",
                    )
        return meter.finalize()


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------


def create_default_chain() -> CostInterceptorChain:
    """创建默认 Interceptor 链。"""
    return CostInterceptorChain()


def create_chain_with_recall_limiter() -> CostInterceptorChain:
    """创建包含 RecallTokenLimiter 的 Interceptor 链。"""
    return CostInterceptorChain(
        interceptors=[
            PreActionBudgetCheck(),
            PerActionClassLimit(),
            PermissionRecheck(),
            RecallTokenLimiter(),
            RateLimiter(),
            ActionInvoker(),
            PostActionAccounting(),
        ]
    )
