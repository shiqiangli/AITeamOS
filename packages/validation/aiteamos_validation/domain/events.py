"""
Validation Context — 领域事件 (arch.md §2.2.5)。

所有事件继承 VersionedDomainEvent，通过 Outbox 同事务写入。
"""

from __future__ import annotations

from uuid import UUID

from aiteamos_shared.events import VersionedDomainEvent


class HarnessInvocationTriggered(VersionedDomainEvent):
    """验证调用已触发。"""

    event_type: str = "validation.harness_invocation.triggered"
    invocation_id: UUID
    adapter_id: str
    run_id: UUID
    tier: str
    callback_token: str


class HarnessInvocationCompleted(VersionedDomainEvent):
    """验证调用完成 (同步或异步回调)。"""

    event_type: str = "validation.harness_invocation.completed"
    invocation_id: UUID
    run_id: UUID
    outcome: str  # pass | fail | flaky | adapter_error
    callback_token: str


class HarnessInvocationExpired(VersionedDomainEvent):
    """验证调用过期 (GC 扫描触发, arch.md §3.3.6)。"""

    event_type: str = "validation.harness_invocation.expired"
    invocation_id: UUID
    run_id: UUID
    callback_token: str
    reason: str = "gc_deadline_exceeded"


class HarnessAdapterRegistered(VersionedDomainEvent):
    """验证适配器注册。"""

    event_type: str = "validation.harness_adapter.registered"
    adapter_id: str
    tier: str
    protocol: str
    endpoint: str


class HarnessAdapterHealthChanged(VersionedDomainEvent):
    """验证适配器健康状态变更。"""

    event_type: str = "validation.harness_adapter.health_changed"
    adapter_id: str
    ready: bool
    success_rate_24h: float
