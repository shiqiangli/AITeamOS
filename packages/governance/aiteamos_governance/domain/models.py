"""
Governance Context — 领域模型 (arch.md §2.2.6, plan.md §3.3)。

聚合根:
- ReviewCase: 审核案例 (Task 交付物 / Memory 候选 / Memory 修改)
- ConflictCase: Memory 冲突案例

值对象:
- ReviewTargetKind, Verdict, ConflictKind, DetectorKind, Resolution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from aiteamos_shared.types import MemberId, MemoryId, new_id


# ---------------------------------------------------------------------------
# 枚举值对象
# ---------------------------------------------------------------------------


class ReviewTargetKind(StrEnum):
    """审核目标类型。"""
    TASK_DELIVERABLE = "task_deliverable"
    MEMORY_CANDIDATE = "memory_candidate"
    MEMORY_MODIFICATION = "memory_modification"
    MEMORY_PROMOTION = "memory_promotion"


class Verdict(StrEnum):
    """审核裁定。"""
    APPROVE = "approve"
    REJECT = "reject"
    MERGE = "merge"
    REVISE = "revise"


class ConflictKind(StrEnum):
    """冲突类型。"""
    SEMANTIC = "semantic"
    SCOPE = "scope"
    TEMPORAL = "temporal"


class DetectorKind(StrEnum):
    """冲突检测方式。"""
    AUTO_ADMISSION = "auto_admission"
    PERIODIC_SCAN = "periodic_scan"
    RECALL_COLLISION = "recall_collision"
    MANUAL = "manual"


class ResolutionKind(StrEnum):
    """冲突解决方式。"""
    KEEP_A = "keep_a"
    KEEP_B = "keep_b"
    MERGE = "merge"
    DEPRECATE_BOTH = "deprecate_both"


# ---------------------------------------------------------------------------
# 聚合根 1: ReviewCase (arch.md §2.2.6)
# ---------------------------------------------------------------------------


class ReviewCase:
    """审核案例聚合根。

    管理从创建到决策的完整审核生命周期。
    支持: Task 交付物审核、Memory 候选审核、Memory 晋升审核。
    """

    def __init__(
        self,
        *,
        id: UUID | None = None,
        target_kind: ReviewTargetKind,
        target_id: UUID,
        reviewer_member_id: MemberId,
        verdict: Verdict | None = None,
        reason: str | None = None,
        correction: str | None = None,
        decision_at: datetime | None = None,
        created_at: datetime | None = None,
        triggered_by_system_meta: bool = False,
    ):
        self.id: UUID = id or new_id()
        self.target_kind = target_kind
        self.target_id = target_id
        self.reviewer_member_id = reviewer_member_id
        self.verdict = verdict
        self.reason = reason
        self.correction = correction
        self.decision_at = decision_at
        self.created_at = created_at or datetime.now(timezone.utc)
        self.triggered_by_system_meta = triggered_by_system_meta

        self._pending_events: list[Any] = []
        self._register_event(
            evt_cls_name="ReviewCaseCreated",
            event_type="governance.review_case.created",
            review_case_id=self.id,
            target_kind=self.target_kind.value,
            target_id=self.target_id,
            reviewer_member_id=self.reviewer_member_id,
        )

    def _register_event(self, *, evt_cls_name: str, **kwargs: Any) -> None:
        """Helper: import event class lazily and append to pending events."""
        from . import events as evt
        evt_cls = getattr(evt, evt_cls_name)
        self._pending_events.append(evt_cls(**kwargs))

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    @property
    def is_decided(self) -> bool:
        return self.verdict is not None

    def decide(
        self,
        *,
        verdict: Verdict,
        reason: str = "",
        correction: str | None = None,
    ) -> None:
        """做出审核决策。

        Raises:
            ValueError: 已决策的 case 不能重复决策
        """
        if self.is_decided:
            raise ValueError(
                f"ReviewCase {self.id} already decided: verdict={self.verdict}"
            )

        self.verdict = verdict
        self.reason = reason
        self.correction = correction
        self.decision_at = datetime.now(timezone.utc)

        self._register_event(
            evt_cls_name="ReviewDecisionMade",
            event_type="governance.review_case.decision_made",
            review_case_id=self.id,
            target_kind=self.target_kind.value,
            target_id=self.target_id,
            verdict=verdict.value,
            reason=reason,
        )

    def __repr__(self) -> str:
        return (
            f"ReviewCase(id={self.id}, target={self.target_kind}:{self.target_id}, "
            f"verdict={self.verdict})"
        )


# ---------------------------------------------------------------------------
# 聚合根 2: ConflictCase (arch.md §2.2.6)
# ---------------------------------------------------------------------------


class ConflictCase:
    """Memory 冲突案例聚合根。

    管理从检测到解决的冲突生命周期。
    冲突隔离: 未解决前召回路径硬屏蔽。
    """

    def __init__(
        self,
        *,
        id: UUID | None = None,
        memory_a_id: MemoryId,
        memory_b_id: MemoryId,
        conflict_kind: ConflictKind,
        detected_by: DetectorKind,
        resolution: ResolutionKind | None = None,
        winner_id: MemoryId | None = None,
        resolved_by: MemberId | None = None,
        detected_at: datetime | None = None,
        resolved_at: datetime | None = None,
    ):
        self.id: UUID = id or new_id()
        self.memory_a_id = memory_a_id
        self.memory_b_id = memory_b_id
        self.conflict_kind = conflict_kind
        self.detected_by = detected_by
        self.resolution = resolution
        self.winner_id = winner_id
        self.resolved_by = resolved_by
        self.detected_at = detected_at or datetime.now(timezone.utc)
        self.resolved_at = resolved_at

        self._pending_events: list[Any] = []
        self._register_event(
            evt_cls_name="ConflictDetected",
            event_type="governance.conflict_case.detected",
            conflict_case_id=self.id,
            memory_a_id=self.memory_a_id,
            memory_b_id=self.memory_b_id,
            conflict_kind=self.conflict_kind.value,
            detected_by=self.detected_by.value,
        )

    def _register_event(self, *, evt_cls_name: str, **kwargs: Any) -> None:
        """Helper: import event class lazily and append to pending events."""
        from . import events as evt
        evt_cls = getattr(evt, evt_cls_name)
        self._pending_events.append(evt_cls(**kwargs))

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None

    def resolve(
        self,
        *,
        resolution: ResolutionKind,
        winner_id: MemoryId | None = None,
        resolved_by: MemberId,
    ) -> None:
        """解决冲突。

        Raises:
            ValueError: 已解决的 case 不能重复解决
        """
        if self.is_resolved:
            raise ValueError(
                f"ConflictCase {self.id} already resolved"
            )

        self.resolution = resolution
        self.winner_id = winner_id
        self.resolved_by = resolved_by
        self.resolved_at = datetime.now(timezone.utc)

        self._register_event(
            evt_cls_name="ConflictResolved",
            event_type="governance.conflict_case.resolved",
            conflict_case_id=self.id,
            memory_a_id=self.memory_a_id,
            memory_b_id=self.memory_b_id,
            resolution=resolution.value,
            winner_id=winner_id,
            resolved_by=resolved_by,
        )

    def __repr__(self) -> str:
        return (
            f"ConflictCase(id={self.id}, "
            f"{self.memory_a_id} vs {self.memory_b_id}, "
            f"kind={self.conflict_kind}, resolved={self.is_resolved})"
        )
