"""
Validation Context — 领域模型 (arch.md §2.2.5, §4.2)。

聚合根:
- HarnessAdapter: 配置型聚合根，验证适配器注册信息
- HarnessInvocation: 运行时聚合根，验证调用生命周期

值对象:
- HarnessTier, ProtocolKind, InvocationState
- HarnessResult, HarnessOutcome, HarnessMetrics
- FlakySignal, EvidenceRef, AdapterHealth
- HarnessTicket, HarnessManifest, DeliverableRef, ValidationContext
"""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from aiteamos_shared.types import RunId, new_id


# ---------------------------------------------------------------------------
# 枚举值对象
# ---------------------------------------------------------------------------


class HarnessTier(StrEnum):
    """验证层级。"""
    SPEC = "spec"
    FUNCTIONAL = "functional"
    SYSTEM = "system"


class ProtocolKind(StrEnum):
    """适配器通信协议。"""
    SYNC = "sync"
    ASYNC = "async"


class InvocationState(StrEnum):
    """调用状态。"""
    PENDING = "pending"
    DONE = "done"
    EXPIRED = "expired"
    FLAKY = "flaky"
    ADAPTER_ERROR = "adapter_error"


class HarnessOutcome(StrEnum):
    """验证结果。"""
    PASS = "pass"
    FAIL = "fail"
    FLAKY = "flaky"
    ADAPTER_ERROR = "adapter_error"


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceRef:
    """验证证据引用 (测试日志、覆盖率报告等)。"""
    kind: str  # 'junit_xml' | 'coverage_html' | 'log_url' | 'artifact'
    uri: str
    label: str = ""


@dataclass(frozen=True)
class HarnessMetrics:
    """验证指标。"""
    duration_seconds: float = 0.0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_flaky: int = 0
    coverage_pct: float | None = None


@dataclass(frozen=True)
class FlakySignal:
    """Flaky 测试信号 (arch.md §5.1)。"""
    test_name: str
    pass_count: int = 0
    fail_count: int = 0
    flake_rate: float = 0.0  # 0.0 ~ 1.0
    suspected_root_cause: str = ""


@dataclass(frozen=True)
class AdapterHealth:
    """适配器健康状态。"""
    ready: bool = True
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    success_rate_24h: float = 1.0
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HarnessManifest:
    """适配器清单 (arch.md §4.2.1)。"""
    id: str
    tier: HarnessTier
    protocol: ProtocolKind
    endpoint: str
    auth_secret_ref: str
    callback_secret_ref: str = ""


@dataclass(frozen=True)
class DeliverableRef:
    """交付物引用。"""
    task_id: str
    run_id: str
    uri: str
    kind: str = "code_patch"  # code_patch | artifact | report


@dataclass(frozen=True)
class ValidationContext:
    """验证上下文 — 传递给 Adapter 的执行环境。"""
    task_id: str
    run_id: str
    member_id: str
    department_id: str
    project_id: str
    extra: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_run(
        *,
        task_id: str,
        run_id: str,
        member_id: str,
        department_id: str,
        project_id: str,
    ) -> ValidationContext:
        return ValidationContext(
            task_id=task_id,
            run_id=run_id,
            member_id=member_id,
            department_id=department_id,
            project_id=project_id,
        )


@dataclass(frozen=True)
class HarnessResult:
    """验证结果归一化结构 (arch.md §4.2.2)。"""
    invocation_id: UUID
    callback_token: str
    outcome: HarnessOutcome
    tier: HarnessTier
    evidence: list[EvidenceRef] = field(default_factory=list)
    metrics: HarnessMetrics = field(default_factory=HarnessMetrics)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    flaky_signal: FlakySignal | None = None
    cost_usd: Decimal = Decimal("0")
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HarnessTicket:
    """验证票据 — trigger_regression 的返回值。"""
    invocation_id: UUID
    callback_token: str
    pending: bool = False
    outcome: HarnessOutcome | None = None  # 同步时立即可读
    eta_seconds: float = 0.0
    skip_reason: str = ""
    result: HarnessResult | None = None

    @staticmethod
    def skip(*, reason: str = "no_adapter_configured", mark_unverified: bool = True) -> HarnessTicket:
        """无 Adapter 时返回 skip ticket。"""
        return HarnessTicket(
            invocation_id=uuid4(),
            callback_token="",
            pending=False,
            skip_reason=reason,
        )


# ---------------------------------------------------------------------------
# 超时规则 (arch.md §3.3.5)
# ---------------------------------------------------------------------------

TIMEOUT_RULES: dict[str, timedelta] = {
    HarnessTier.SPEC: timedelta(minutes=5),
    HarnessTier.FUNCTIONAL: timedelta(minutes=30),
    HarnessTier.SYSTEM: timedelta(hours=24),
}

# GC 安全边距 (arch.md §A.5: expire_at = triggered_at + timeout + 24h)
GC_SAFETY_MARGIN = timedelta(hours=24)


def generate_callback_token() -> str:
    """生成唯一回调令牌 (幂等键)。"""
    alphabet = string.ascii_letters + string.digits
    return "cb_" + "".join(secrets.choice(alphabet) for _ in range(48))


# ---------------------------------------------------------------------------
# 聚合根 1: HarnessAdapter (配置型)
# ---------------------------------------------------------------------------


class HarnessAdapterAggregate:
    """Harness 适配器配置聚合根 (arch.md §2.2.5)。

    配置型：注册后不频繁变更，作为路由决策的元数据源。
    """

    def __init__(
        self,
        *,
        id: str,
        tier: HarnessTier,
        protocol: ProtocolKind,
        endpoint: str,
        auth_secret_ref: str,
        callback_secret_ref: str = "",
        health: AdapterHealth | None = None,
        project_bindings: list[UUID] | None = None,
        created_at: datetime | None = None,
    ):
        self.id = id
        self.tier = tier
        self.protocol = protocol
        self.endpoint = endpoint
        self.auth_secret_ref = auth_secret_ref
        self.callback_secret_ref = callback_secret_ref
        self.health = health or AdapterHealth()
        self.project_bindings = project_bindings or []
        self.created_at = created_at or datetime.now(timezone.utc)

        self._pending_events: list[Any] = []

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def update_health(self, health: AdapterHealth) -> None:
        self.health = health
        from . import events as evt
        self._pending_events.append(evt.HarnessAdapterHealthChanged(
            event_type="validation.harness_adapter.health_changed",
            adapter_id=self.id,
            ready=health.ready,
            success_rate_24h=health.success_rate_24h,
        ))

    def bind_project(self, project_id: UUID) -> None:
        if project_id not in self.project_bindings:
            self.project_bindings.append(project_id)

    def unbind_project(self, project_id: UUID) -> None:
        if project_id in self.project_bindings:
            self.project_bindings.remove(project_id)

    def matches(self, project_id: UUID, tier: HarnessTier) -> bool:
        """是否匹配给定的 project + tier。"""
        if self.tier != tier:
            return False
        # 无绑定时匹配所有 project (全局适配器)
        if not self.project_bindings:
            return True
        return project_id in self.project_bindings

    def __repr__(self) -> str:
        return f"HarnessAdapter(id={self.id!r}, tier={self.tier}, protocol={self.protocol})"


# ---------------------------------------------------------------------------
# 聚合根 2: HarnessInvocation (运行时)
# ---------------------------------------------------------------------------


class HarnessInvocation:
    """验证调用聚合根 (arch.md §2.2.5)。

    运行时：每次 trigger 产生一条记录，追踪从 pending → done/expired 的生命周期。
    """

    def __init__(
        self,
        *,
        id: UUID | None = None,
        adapter_id: str,
        run_id: UUID,
        deliverable_ref: str,
        callback_token: str | None = None,
        state: InvocationState = InvocationState.PENDING,
        tier: str = "system",
        triggered_at: datetime | None = None,
        completed_at: datetime | None = None,
        expire_at: datetime | None = None,
        result: dict[str, Any] | None = None,
        flaky_signal: dict[str, Any] | None = None,
        archived_at: datetime | None = None,
    ):
        self.id: UUID = id or new_id()
        self.adapter_id = adapter_id
        self.run_id = run_id
        self.deliverable_ref = deliverable_ref
        self.callback_token = callback_token or generate_callback_token()
        self.state = state
        self.tier = tier
        self.triggered_at = triggered_at or datetime.now(timezone.utc)
        self.completed_at = completed_at
        self.expire_at = expire_at or self._default_expire()
        self.result = result
        self.flaky_signal = flaky_signal
        self.archived_at = archived_at

        self._pending_events: list[Any] = []
        from . import events as evt
        self._pending_events.append(evt.HarnessInvocationTriggered(
            event_type="validation.harness_invocation.triggered",
            invocation_id=self.id,
            adapter_id=self.adapter_id,
            run_id=self.run_id,
            tier=self.tier,
            callback_token=self.callback_token,
        ))

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def _default_expire(self) -> datetime:
        """默认过期时间: triggered_at + system tier timeout + 24h safety margin。"""
        timeout = TIMEOUT_RULES.get(HarnessTier.SYSTEM, timedelta(hours=24))
        return self.triggered_at + timeout + GC_SAFETY_MARGIN

    @staticmethod
    def from_ticket(
        ticket: HarnessTicket,
        adapter_id: str,
        *,
        run_id: UUID,
        deliverable_ref: str,
        tier: HarnessTier,
    ) -> HarnessInvocation:
        """从 HarnessTicket 创建 Invocation。"""
        timeout = TIMEOUT_RULES.get(tier, timedelta(hours=24))
        triggered_at = datetime.now(timezone.utc)
        return HarnessInvocation(
            id=ticket.invocation_id,
            adapter_id=adapter_id,
            run_id=run_id,
            deliverable_ref=deliverable_ref,
            callback_token=ticket.callback_token,
            state=InvocationState.PENDING,
            tier=tier.value,
            triggered_at=triggered_at,
            expire_at=triggered_at + timeout + GC_SAFETY_MARGIN,
        )

    def mark_done(self, result: HarnessResult) -> None:
        """标记完成。"""
        if self.state != InvocationState.PENDING:
            raise ValueError(f"Cannot complete invocation in state={self.state}")
        self.state = InvocationState.DONE
        self.completed_at = datetime.now(timezone.utc)
        self.result = {
            "outcome": result.outcome.value,
            "tier": result.tier.value,
            "metrics": {
                "duration_seconds": result.metrics.duration_seconds,
                "tests_passed": result.metrics.tests_passed,
                "tests_failed": result.metrics.tests_failed,
                "tests_flaky": result.metrics.tests_flaky,
            },
            "cost_usd": str(result.cost_usd),
        }
        if result.flaky_signal:
            self.flaky_signal = {
                "test_name": result.flaky_signal.test_name,
                "pass_count": result.flaky_signal.pass_count,
                "fail_count": result.flaky_signal.fail_count,
                "flake_rate": result.flaky_signal.flake_rate,
            }

        from . import events as evt
        self._pending_events.append(evt.HarnessInvocationCompleted(
            event_type="validation.harness_invocation.completed",
            invocation_id=self.id,
            run_id=self.run_id,
            outcome=result.outcome.value,
            callback_token=self.callback_token,
        ))

    def mark_expired(self) -> None:
        """标记过期 (GC 扫描触发)。"""
        if self.state != InvocationState.PENDING:
            return  # 幂等: 非 pending 状态忽略
        self.state = InvocationState.EXPIRED
        self.completed_at = datetime.now(timezone.utc)

        from . import events as evt
        self._pending_events.append(evt.HarnessInvocationExpired(
            event_type="validation.harness_invocation.expired",
            invocation_id=self.id,
            run_id=self.run_id,
            callback_token=self.callback_token,
            reason="gc_deadline_exceeded",
        ))

    def mark_adapter_error(self, *, diagnostics: dict[str, Any] | None = None) -> None:
        """标记适配器错误。"""
        if self.state != InvocationState.PENDING:
            return
        self.state = InvocationState.ADAPTER_ERROR
        self.completed_at = datetime.now(timezone.utc)
        self.result = {"outcome": "adapter_error", "diagnostics": diagnostics or {}}

    def archive(self) -> None:
        """软删除 (归档)。"""
        self.archived_at = datetime.now(timezone.utc)

    def is_terminal(self) -> bool:
        return self.state in (
            InvocationState.DONE,
            InvocationState.EXPIRED,
            InvocationState.ADAPTER_ERROR,
        )

    def __repr__(self) -> str:
        return (
            f"HarnessInvocation(id={self.id}, adapter={self.adapter_id!r}, "
            f"state={self.state})"
        )
