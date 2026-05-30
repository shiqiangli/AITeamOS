"""
Knowledge Context — 领域事件 (arch.md §2.2.1)。

所有事件继承 VersionedDomainEvent，通过 Outbox 同事务写入。
"""

from __future__ import annotations

from uuid import UUID

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.types import MemoryId

from .models import LifecycleState


# ---------------------------------------------------------------------------
# MemoryNode 事件
# ---------------------------------------------------------------------------


class MemoryNodeCreated(VersionedDomainEvent):
    """Memory 节点创建。"""

    event_type: str = "knowledge.memory_node.created"
    memory_id: MemoryId
    tier: str
    title: str
    provenance_source_kind: str


class MemoryNodeUpdated(VersionedDomainEvent):
    """Memory 节点内容更新。"""

    event_type: str = "knowledge.memory_node.updated"
    memory_id: MemoryId
    new_version: int
    reason: str


class MemoryNodeLifecycleChanged(VersionedDomainEvent):
    """Memory 生命周期状态变更。"""

    event_type: str = "knowledge.memory_node.lifecycle_changed"
    memory_id: MemoryId
    old_state: LifecycleState
    new_state: LifecycleState


# ---------------------------------------------------------------------------
# MemoryEdge 事件
# ---------------------------------------------------------------------------


class MemoryEdgeAdded(VersionedDomainEvent):
    """Memory 关系边添加。"""

    event_type: str = "knowledge.memory_edge.added"
    edge_id: UUID
    source_id: MemoryId
    target_id: MemoryId
    relation_type: str


class MemoryEdgeRemoved(VersionedDomainEvent):
    """Memory 关系边移除。"""

    event_type: str = "knowledge.memory_edge.removed"
    edge_id: UUID
    source_id: MemoryId
    target_id: MemoryId
    relation_type: str


# ---------------------------------------------------------------------------
# MemoryVersion 事件
# ---------------------------------------------------------------------------


class MemoryVersionAppended(VersionedDomainEvent):
    """Memory 版本追加。"""

    event_type: str = "knowledge.memory_version.appended"
    memory_id: MemoryId
    version_no: int
    reason: str


# ---------------------------------------------------------------------------
# 置信度 / 隔离 事件
# ---------------------------------------------------------------------------


class MemoryQuarantinedEvent(VersionedDomainEvent):
    """Memory 被隔离（置信度过低或手动隔离）。"""

    event_type: str = "knowledge.memory_node.quarantined"
    memory_id: MemoryId
    reason: str  # 'low_confidence' | 'lifecycle_change' | 'manual'


class MemoryBatchNeedsVerifyEvent(VersionedDomainEvent):
    """批量 Memory 进入 needs_verify 状态（级联失效/衰减触发）。"""

    event_type: str = "knowledge.memory_batch.needs_verify"
    memory_ids: list[MemoryId]
    triggered_by: str  # 'cascade_invalidation' | 'daily_decay'
    triggered_by_system_meta: bool = False


class MemoryFeedbackRecorded(VersionedDomainEvent):
    """Memory 反馈记录（驱动置信度演进）。"""

    event_type: str = "knowledge.memory_feedback.recorded"
    memory_id: MemoryId
    task_run_id: UUID
    outcome: str  # 'positive' | 'negative' | 'neutral'
    delta: float
    is_system_meta: bool = False


class MemoryTierPromoted(VersionedDomainEvent):
    """Memory 层级晋升（Facts→Patterns / Patterns→Principles）。"""

    event_type: str = "knowledge.memory_node.tier_promoted"
    memory_id: MemoryId
    old_tier: str
    new_tier: str
    promoted_by: UUID | None = None  # 审核人 MemberId


class MemoryPromotionRequested(VersionedDomainEvent):
    """Memory 晋升申请（等待人工审核）。"""

    event_type: str = "knowledge.memory_node.promotion_requested"
    memory_id: MemoryId
    current_tier: str
    target_tier: str
    reason: str
