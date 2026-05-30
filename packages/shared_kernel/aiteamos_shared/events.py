"""
Shared Kernel — 版本化领域事件基类。

所有跨 Bounded Context 的领域事件必须继承 VersionedDomainEvent，
确保事件契约的版本化演进能力 (arch.md §2.1)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class VersionedDomainEvent(BaseModel):
    """Cross-context 事件强制基类。

    所有领域事件必须继承此类，保证：
    - event_type: 事件类型标识（如 'task.completed'）
    - event_version: SemVer major，破坏性变更必须升版本
    - correlation_id: 全链路追踪 ID
    - timestamp: 事件产生时间
    - global_seq: Outbox 全局序列号（由 Outbox 写入时分配）

    Config.extra = 'ignore' 实现向前兼容：
    新增可选字段不破坏旧版消费者。
    """

    event_type: str
    event_version: int = 1
    correlation_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    global_seq: int = 0  # 由 Outbox 写入时赋值，消费侧用于幂等水位

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# 便捷工厂
# ---------------------------------------------------------------------------


def create_event(
    event_cls: type[VersionedDomainEvent],
    *,
    correlation_id: UUID | None = None,
    **kwargs,
) -> VersionedDomainEvent:
    """Helper to create a domain event with auto-populated defaults.

    Usage::

        evt = create_event(TaskCompleted, task_id="TASK-...", outcome="done")
    """
    return event_cls(
        correlation_id=correlation_id or uuid4(),
        **kwargs,
    )
