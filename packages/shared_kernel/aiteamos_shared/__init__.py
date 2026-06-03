"""AITeamOS Shared Kernel — 共享内核包。

提供所有 Bounded Context 共用的基础类型、事件基类、
Outbox 模式、投影消费者、Saga 补偿栈和仓储抽象。
"""

from .events import VersionedDomainEvent, create_event
from .types import (
    EmployeeKind,
    Priority,
    ResourceKind,
    SemVer,
    TaskId,
    generate_task_id,
    new_id,
)

__all__ = [
    "VersionedDomainEvent",
    "create_event",
    "EmployeeKind",
    "Priority",
    "ResourceKind",
    "SemVer",
    "TaskId",
    "generate_task_id",
    "new_id",
]
