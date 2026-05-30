"""
Knowledge Context — Application Commands (CQRS write side).

Each Command is an immutable dataclass carrying intent.
Handlers in handlers.py execute the commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from aiteamos_shared.types import MemberId, MemoryId, RunId, TaskId

from ..domain.models import (
    LifecycleState,
    RelationType,
    ScopeKind,
    SourceKind,
    Tier,
)


# ---------------------------------------------------------------------------
# MemoryNode Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateMemoryNodeCommand:
    """创建 Memory 节点。"""

    tier: Tier
    scope_kind: ScopeKind
    scope_ref: UUID | None
    title: str
    statement: str
    applicable_when: str
    counter_example: str
    tags: list[str]
    source_kind: SourceKind
    task_id: TaskId | None = None
    run_id: RunId | None = None
    member_id: MemberId | None = None
    system_meta: bool = False
    initial_confidence: Decimal = Decimal("0.500")


@dataclass(frozen=True)
class UpdateMemoryContentCommand:
    """更新 Memory 内容。"""

    memory_id: MemoryId
    statement: str
    applicable_when: str
    counter_example: str
    tags: list[str]
    reason: str
    author_member_id: MemberId


@dataclass(frozen=True)
class AppendMemoryVersionCommand:
    """追加 Memory 版本（不修改 content）。"""

    memory_id: MemoryId
    diff: dict
    reason: str
    author_member_id: MemberId


@dataclass(frozen=True)
class ChangeLifecycleCommand:
    """变更 Memory 生命周期状态。"""

    memory_id: MemoryId
    new_state: LifecycleState


@dataclass(frozen=True)
class DeprecateMemoryNodeCommand:
    """废弃 Memory 节点。"""

    memory_id: MemoryId


@dataclass(frozen=True)
class MergeMemoryNodesCommand:
    """合并多个 Memory 节点。"""

    source_ids: list[MemoryId]
    target_id: MemoryId
    reason: str
    author_member_id: MemberId


# ---------------------------------------------------------------------------
# MemoryEdge Commands
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateMemoryEdgeCommand:
    """创建 Memory 关系边。"""

    source_id: MemoryId
    target_id: MemoryId
    relation_type: RelationType
    weight: Decimal = Decimal("1.000")
    created_by: MemberId = None  # type: ignore[assignment]


@dataclass(frozen=True)
class RemoveMemoryEdgeCommand:
    """移除 Memory 关系边。"""

    edge_id: UUID
