"""
Governance Context — 领域事件 (arch.md §2.2.6)。
"""

from __future__ import annotations

from uuid import UUID

from aiteamos_shared.events import VersionedDomainEvent


class ReviewCaseCreated(VersionedDomainEvent):
    """审核案例创建。"""

    event_type: str = "governance.review_case.created"
    review_case_id: UUID
    target_kind: str
    target_id: UUID
    reviewer_member_id: UUID


class ReviewDecisionMade(VersionedDomainEvent):
    """审核决策完成。"""

    event_type: str = "governance.review_case.decision_made"
    review_case_id: UUID
    target_kind: str
    target_id: UUID
    verdict: str  # approve | reject | merge | revise
    reason: str = ""


class ConflictDetected(VersionedDomainEvent):
    """Memory 冲突检测。"""

    event_type: str = "governance.conflict_case.detected"
    conflict_case_id: UUID
    memory_a_id: UUID
    memory_b_id: UUID
    conflict_kind: str
    detected_by: str


class ConflictResolved(VersionedDomainEvent):
    """Memory 冲突解决。"""

    event_type: str = "governance.conflict_case.resolved"
    conflict_case_id: UUID
    memory_a_id: UUID
    memory_b_id: UUID
    resolution: str
    winner_id: UUID | None = None
    resolved_by: UUID | None = None
