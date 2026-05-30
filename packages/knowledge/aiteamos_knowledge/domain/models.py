"""
Knowledge Context — 领域模型 (arch.md §2.2.1)。

聚合根:
- MemoryNode: Memory 主聚合根，含版本、置信度、生命周期
- MemoryEdge: 独立聚合根，关系边（v1.3 拆分，消除热门节点锁竞争）

实体:
- MemoryVersion: 版本记录，属于 MemoryNode 聚合内

值对象:
- Confidence, Provenance, MemoryContent
- Tier, Scope, LifecycleState, SourceKind, RelationType, ConfidenceState
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from aiteamos_shared.types import MemberId, MemoryId, RunId, TaskId, new_id


# ---------------------------------------------------------------------------
# 枚举值对象
# ---------------------------------------------------------------------------


class Tier(StrEnum):
    """Memory 知识层级。"""

    FACTS = "facts"
    PATTERNS = "patterns"
    PRINCIPLES = "principles"


class ScopeKind(StrEnum):
    """Memory 作用范围。"""

    PROJECT = "project"
    TECH_STACK = "tech_stack"
    DEPARTMENT = "department"
    GLOBAL = "global"


@dataclass(frozen=True)
class Scope:
    """Memory 作用域值对象。"""

    kind: ScopeKind
    ref: UUID | None = None  # 指向 project/dept/null


class LifecycleState(StrEnum):
    """Memory 生命周期状态。"""

    CANDIDATE = "candidate"
    ACTIVE = "active"
    STALE = "stale"
    NEEDS_VERIFY = "needs_verify"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"
    QUARANTINED = "quarantined"


class ConfidenceState(StrEnum):
    """置信度状态。"""

    VALID = "valid"
    NEEDS_VERIFY = "needs_verify"
    DEPRECATED = "deprecated"
    CONFLICTING = "conflicting"
    QUARANTINED = "quarantined"


class SourceKind(StrEnum):
    """Memory 来源类型。"""

    TASK_EXECUTION = "task_execution"
    HARNESS_DEBUG = "harness_debug"
    REVIEW = "review"
    MANUAL_INPUT = "manual_input"
    BULK_IMPORT = "bulk_import"


class RelationType(StrEnum):
    """Memory 关系类型。"""

    CAUSAL = "causal"
    DEPENDS = "depends"
    DERIVED = "derived"
    CONFLICTS = "conflicts"


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Confidence:
    """置信度值对象 (arch.md §2.2.1)。

    I-K-1: value ∈ [0, 1]，禁止外部直接 set。
    """

    value: Decimal = Decimal("0.500")
    state: ConfidenceState = ConfidenceState.NEEDS_VERIFY
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_decay_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not (Decimal("0") <= self.value <= Decimal("1")):
            raise ValueError(
                f"Confidence value must be in [0, 1], got {self.value}"
            )

    def with_value(
        self,
        new_value: Decimal,
        *,
        state: ConfidenceState | None = None,
        now: datetime | None = None,
    ) -> Confidence:
        """Return a new Confidence with updated value (immutable)."""
        ts = now or datetime.now(timezone.utc)
        return Confidence(
            value=new_value,
            state=state or self.state,
            last_updated=ts,
            last_decay_at=ts,
        )


@dataclass(frozen=True)
class Provenance:
    """来源值对象 (arch.md §2.2.1)。"""

    source_kind: SourceKind
    task_id: TaskId | None = None
    run_id: RunId | None = None
    member_id: MemberId | None = None
    system_meta: bool = False  # True 即被 Reflection Engine 硬性排除


@dataclass(frozen=True)
class MemoryContent:
    """Memory 内容值对象。"""

    statement: str
    applicable_when: str = ""
    counter_example: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "applicable_when": self.applicable_when,
            "counter_example": self.counter_example,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryContent:
        return cls(
            statement=data.get("statement", ""),
            applicable_when=data.get("applicable_when", ""),
            counter_example=data.get("counter_example", ""),
            tags=data.get("tags", []),
        )


# ---------------------------------------------------------------------------
# 实体: MemoryVersion（MemoryNode 聚合内）
# ---------------------------------------------------------------------------


@dataclass
class MemoryVersion:
    """版本实体，属于 MemoryNode 聚合内。"""

    version_no: int
    diff: dict[str, Any]
    reason: str
    author_member_id: MemberId
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: UUID = field(default_factory=uuid4)


# ---------------------------------------------------------------------------
# 聚合根 1: MemoryNode (arch.md §2.2.1)
# ---------------------------------------------------------------------------


class MemoryNode:
    """Memory 主聚合根。

    聚合边界内含 MemoryVersion 实体列表。
    不含 MemoryEdge — Edge 为独立聚合根 (I-K-4)。
    """

    def __init__(
        self,
        *,
        id: MemoryId | None = None,
        tier: Tier,
        scope: Scope,
        title: str,
        content: MemoryContent,
        confidence: Confidence | None = None,
        provenance: Provenance,
        lifecycle: LifecycleState = LifecycleState.CANDIDATE,
        versions: list[MemoryVersion] | None = None,
        current_version: int = 1,
        created_at: datetime | None = None,
        last_used_at: datetime | None = None,
        expire_at: datetime | None = None,
    ):
        self.id: MemoryId = id or new_id()
        self.tier = tier
        self.scope = scope
        self.title = title
        self.content = content
        self.confidence = confidence or Confidence()
        self.provenance = provenance
        self.lifecycle = lifecycle
        self.versions: list[MemoryVersion] = versions or []
        self.current_version = current_version
        self.created_at = created_at or datetime.now(timezone.utc)
        self.last_used_at = last_used_at
        self.expire_at = expire_at

        # 内部事件收集器（Handler 负责清空并发布到 Outbox）
        self._pending_events: list[Any] = []

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def _register_event(self, event: Any) -> None:
        self._pending_events.append(event)

    # -- 业务方法 --

    def update_content(
        self,
        new_content: MemoryContent,
        *,
        reason: str,
        author_member_id: MemberId,
    ) -> MemoryVersion:
        """更新 Memory 内容并追加版本记录。"""
        old_statement = self.content.statement
        self.content = new_content

        version = MemoryVersion(
            version_no=self.current_version + 1,
            diff={
                "statement_before": old_statement,
                "statement_after": new_content.statement,
            },
            reason=reason,
            author_member_id=author_member_id,
        )
        self.versions.append(version)
        self.current_version = version.version_no

        from . import events as evt

        self._register_event(
            evt.MemoryNodeUpdated(
                event_type="knowledge.memory_node.updated",
                memory_id=self.id,
                new_version=version.version_no,
                reason=reason,
            )
        )
        self._register_event(
            evt.MemoryVersionAppended(
                event_type="knowledge.memory_version.appended",
                memory_id=self.id,
                version_no=version.version_no,
                reason=reason,
            )
        )
        return version

    def append_version(
        self,
        *,
        diff: dict[str, Any],
        reason: str,
        author_member_id: MemberId,
    ) -> MemoryVersion:
        """仅追加版本记录（不修改 content）。"""
        version = MemoryVersion(
            version_no=self.current_version + 1,
            diff=diff,
            reason=reason,
            author_member_id=author_member_id,
        )
        self.versions.append(version)
        self.current_version = version.version_no

        from . import events as evt

        self._register_event(
            evt.MemoryVersionAppended(
                event_type="knowledge.memory_version.appended",
                memory_id=self.id,
                version_no=version.version_no,
                reason=reason,
            )
        )
        return version

    def change_lifecycle(self, new_state: LifecycleState) -> None:
        """变更生命周期状态。"""
        old_state = self.lifecycle
        self.lifecycle = new_state

        from . import events as evt

        self._register_event(
            evt.MemoryNodeLifecycleChanged(
                event_type="knowledge.memory_node.lifecycle_changed",
                memory_id=self.id,
                old_state=old_state,
                new_state=new_state,
            )
        )
        if new_state == LifecycleState.QUARANTINED:
            self._register_event(
                evt.MemoryQuarantinedEvent(
                    event_type="knowledge.memory_node.quarantined",
                    memory_id=self.id,
                    reason="lifecycle_change",
                )
            )

    def adjust_confidence(
        self,
        new_value: Decimal,
        *,
        state: ConfidenceState | None = None,
        now: datetime | None = None,
    ) -> None:
        """调整置信度 (必须通过 ConfidenceAdjustmentService 调用, I-K-1)。"""
        self.confidence = self.confidence.with_value(new_value, state=state, now=now)

    def mark_used(self, now: datetime | None = None) -> None:
        """记录使用时间。"""
        self.last_used_at = now or datetime.now(timezone.utc)

    def deprecate(self) -> None:
        """废弃此 Memory。"""
        self.change_lifecycle(LifecycleState.DEPRECATED)
        self.confidence = self.confidence.with_value(
            self.confidence.value,
            state=ConfidenceState.DEPRECATED,
        )

    _NON_RECALLABLE_STATES = frozenset({
        LifecycleState.QUARANTINED,
        LifecycleState.DEPRECATED,
        LifecycleState.ARCHIVED,
    })

    def is_recallable(self) -> bool:
        """是否可被召回 (I-K-3: quarantined/deprecated/archived 屏蔽, PRD §3.1.6)。"""
        return self.lifecycle not in self._NON_RECALLABLE_STATES

    def __repr__(self) -> str:
        return (
            f"MemoryNode(id={self.id}, tier={self.tier}, "
            f"title={self.title!r}, lifecycle={self.lifecycle})"
        )


# ---------------------------------------------------------------------------
# 聚合根 2: MemoryEdge (独立聚合根, arch.md §2.2.1 v1.3)
# ---------------------------------------------------------------------------


class MemoryEdge:
    """Memory 关系边 — 独立聚合根 (I-K-4, I-K-5)。

    Edge 的 CRUD 不需要锁定 source/target MemoryNode 聚合。
    """

    def __init__(
        self,
        *,
        edge_id: UUID | None = None,
        source_id: MemoryId,
        target_id: MemoryId,
        relation_type: RelationType,
        weight: Decimal = Decimal("1.000"),
        created_by: MemberId,
        created_at: datetime | None = None,
    ):
        self.edge_id: UUID = edge_id or new_id()
        self.source_id = source_id
        self.target_id = target_id
        self.relation_type = relation_type
        self.weight = weight
        self.created_by = created_by
        self.created_at = created_at or datetime.now(timezone.utc)

        self._pending_events: list[Any] = []

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def __repr__(self) -> str:
        return (
            f"MemoryEdge(edge_id={self.edge_id}, "
            f"{self.source_id} -[{self.relation_type}]-> {self.target_id})"
        )
