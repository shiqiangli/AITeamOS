"""
Validation Context — Flaky 检测服务 (plan.md §3.2.3, arch.md §5.1)。

Flaky 检测类型:
- retry_diverge: 同一输入多次执行结果不一致
- retry_no_change_pass: 未修改代码重试后通过
- env_noise_code: 环境变量/时序敏感

Flaky 结果进入隔离区 (Quarantine Buffer)，不直接驱动 Memory 提炼。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..domain.models import (
    FlakySignal,
    HarnessInvocation,
    HarnessOutcome,
    HarnessResult,
    InvocationState,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Flaky 检测阈值
# ---------------------------------------------------------------------------

# 同一 callback_token 或 deliverable_ref 出现不一致结果的最小次数
MIN_DIVERGENCE_COUNT = 2

# retry_no_change_pass 检测: 连续重试次数阈值
MIN_RETRY_NO_CHANGE = 2

# 默认 flake_rate 阈值: 超过此值标记为 flaky
DEFAULT_FLAKE_RATE_THRESHOLD = 0.3


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlakyVerdict:
    """Flaky 检测结果。"""
    is_flaky: bool
    signal: FlakySignal | None = None
    reason: str = ""


# ---------------------------------------------------------------------------
# FlakyDetector — Flaky 测试检测器
# ---------------------------------------------------------------------------


class FlakyDetector:
    """Flaky 测试检测器。

    检测策略:
    1. retry_diverge: 同一 deliverable 多次验证结果不一致 (pass + fail 交替)
    2. retry_no_change_pass: 代码未变更但重试后通过
    3. env_noise: 同一运行环境多次不同结果
    """

    def detect_from_invocations(
        self,
        invocations: list[HarnessInvocation],
    ) -> FlakyVerdict:
        """从一组 invocation 中检测 flaky 信号。

        Args:
            invocations: 同一 run 的所有验证调用记录 (按时间排序)

        Returns:
            FlakyVerdict
        """
        if len(invocations) < 2:
            return FlakyVerdict(is_flaky=False)

        # 只检查已完成的调用
        completed = [
            inv for inv in invocations
            if inv.state == InvocationState.DONE and inv.result is not None
        ]
        if len(completed) < 2:
            return FlakyVerdict(is_flaky=False)

        # 策略 1: retry_diverge — 结果不一致
        outcomes = [
            inv.result.get("outcome", "") for inv in completed
        ]
        has_pass = "pass" in outcomes
        has_fail = "fail" in outcomes

        if has_pass and has_fail:
            pass_count = outcomes.count("pass")
            fail_count = outcomes.count("fail")
            total = len(outcomes)
            flake_rate = min(pass_count, fail_count) / total

            test_name = self._extract_test_name(completed)
            return FlakyVerdict(
                is_flaky=True,
                signal=FlakySignal(
                    test_name=test_name,
                    pass_count=pass_count,
                    fail_count=fail_count,
                    flake_rate=flake_rate,
                    suspected_root_cause="retry_diverge",
                ),
                reason=(
                    f"Divergent results: {pass_count} pass / {fail_count} fail "
                    f"(flake_rate={flake_rate:.2f})"
                ),
            )

        # 策略 2: retry_no_change_pass — 连续 fail 后 pass
        # (需要外部提供"代码是否变更"信息，此处通过 invocations 顺序推断)
        if len(completed) >= MIN_RETRY_NO_CHANGE:
            # 如果前 N-1 次都是 fail，最后一次 pass → 可疑
            all_but_last = outcomes[:-1]
            last = outcomes[-1]
            if all(o == "fail" for o in all_but_last) and last == "pass":
                test_name = self._extract_test_name(completed)
                return FlakyVerdict(
                    is_flaky=True,
                    signal=FlakySignal(
                        test_name=test_name,
                        pass_count=1,
                        fail_count=len(all_but_last),
                        flake_rate=1.0 / len(outcomes),
                        suspected_root_cause="retry_no_change_pass",
                    ),
                    reason=(
                        f"Passed after {len(all_but_last)} failures without code change"
                    ),
                )

        return FlakyVerdict(is_flaky=False)

    def detect_from_result(
        self,
        current_result: HarnessResult,
        previous_results: list[HarnessResult],
    ) -> FlakyVerdict:
        """从结果序列中检测 flaky。"""
        if not previous_results:
            return FlakyVerdict(is_flaky=False)

        outcomes = [r.outcome.value for r in previous_results] + [current_result.outcome.value]
        has_pass = "pass" in outcomes
        has_fail = "fail" in outcomes

        if has_pass and has_fail:
            pass_count = outcomes.count("pass")
            fail_count = outcomes.count("fail")
            total = len(outcomes)
            return FlakyVerdict(
                is_flaky=True,
                signal=FlakySignal(
                    test_name=f"invocation:{current_result.invocation_id}",
                    pass_count=pass_count,
                    fail_count=fail_count,
                    flake_rate=min(pass_count, fail_count) / total,
                    suspected_root_cause="retry_diverge",
                ),
                reason="Divergent results across invocations",
            )

        return FlakyVerdict(is_flaky=False)

    @staticmethod
    def _extract_test_name(invocations: list[HarnessInvocation]) -> str:
        """从 invocation 结果中提取测试名称。"""
        for inv in invocations:
            if inv.result and isinstance(inv.result, dict):
                metrics = inv.result.get("metrics", {})
                if isinstance(metrics, dict) and metrics.get("tests_flaky", 0) > 0:
                    return f"flaky_test:{inv.adapter_id}"
        return f"invocations:{invocations[0].adapter_id}"
