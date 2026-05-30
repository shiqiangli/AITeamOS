"""
Capability Context — 领域模型 (arch.md §2.2.2)。

聚合根:
- Skill: Skill 注册、版本、健康度、熔断

值对象:
- SkillManifest, SideEffect, SkillHealth, CostEstimate
- SkillStatus, CircuitState, MutationKind
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from aiteamos_shared.types import SkillId, SemVer, new_id


# ---------------------------------------------------------------------------
# 枚举值对象
# ---------------------------------------------------------------------------


class SkillStatus(StrEnum):
    """Skill 生命周期状态。"""

    DRAFT = "draft"
    PUBLISHED = "published"
    RECALIBRATING = "recalibrating"
    DEPRECATED = "deprecated"
    CANCELLED = "cancelled"


class CircuitState(StrEnum):
    """熔断器状态。"""

    CLOSED = "closed"
    HALF_OPEN = "half_open"
    OPEN = "open"


class MutationKind(StrEnum):
    """副作用变更类型。"""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXCLUSIVE_LOCK = "exclusive_lock"


# ---------------------------------------------------------------------------
# 值对象
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SideEffect:
    """副作用声明值对象 (arch.md §4.1.2)。"""

    resource_kind: str  # filesystem | network | git | model | mcp
    resource_pattern: str  # glob 或正则
    mutation_kind: MutationKind


@dataclass(frozen=True)
class CostEstimate:
    """成本估算值对象。"""

    token_estimate: int = 0
    time_estimate_seconds: float = 0.0
    cost_usd_estimate: Decimal = Decimal("0")


@dataclass(frozen=True)
class SkillManifest:
    """Skill 元数据值对象 (arch.md §4.1.2)。"""

    name: str = ""
    version: SemVer = field(default_factory=lambda: SemVer(major=0, minor=1, patch=0))
    description: str = ""
    domain: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effects: list[SideEffect] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    capability_tags: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    quality_signals: dict[str, Any] = field(default_factory=dict)
    cost_estimate: CostEstimate = field(default_factory=CostEstimate)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": str(self.version),
            "description": self.description,
            "domain": self.domain,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "preconditions": self.preconditions,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "side_effects": [
                {
                    "resource_kind": se.resource_kind,
                    "resource_pattern": se.resource_pattern,
                    "mutation_kind": se.mutation_kind.value,
                }
                for se in self.side_effects
            ],
            "required_permissions": self.required_permissions,
            "capability_tags": self.capability_tags,
            "examples": self.examples,
            "references": self.references,
            "quality_signals": self.quality_signals,
            "cost_estimate": {
                "token_estimate": self.cost_estimate.token_estimate,
                "time_estimate_seconds": self.cost_estimate.time_estimate_seconds,
                "cost_usd_estimate": str(self.cost_estimate.cost_usd_estimate),
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillManifest:
        side_effects = [
            SideEffect(
                resource_kind=se.get("resource_kind", ""),
                resource_pattern=se.get("resource_pattern", ""),
                mutation_kind=MutationKind(se.get("mutation_kind", "read")),
            )
            for se in data.get("side_effects", [])
        ]
        cost_data = data.get("cost_estimate", {})
        return cls(
            name=data.get("name", ""),
            version=SemVer.parse(data["version"]) if "version" in data else SemVer(major=0, minor=1, patch=0),
            description=data.get("description", ""),
            domain=data.get("domain", ""),
            inputs=data.get("inputs", []),
            outputs=data.get("outputs", []),
            preconditions=data.get("preconditions", []),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            side_effects=side_effects,
            required_permissions=data.get("required_permissions", []),
            capability_tags=data.get("capability_tags", []),
            examples=data.get("examples", []),
            references=data.get("references", []),
            quality_signals=data.get("quality_signals", {}),
            cost_estimate=CostEstimate(
                token_estimate=cost_data.get("token_estimate", 0),
                time_estimate_seconds=cost_data.get("time_estimate_seconds", 0.0),
                cost_usd_estimate=Decimal(str(cost_data.get("cost_usd_estimate", "0"))),
            ),
        )


@dataclass(frozen=True)
class SkillHealth:
    """Skill 健康度值对象 (arch.md §2.2.2)。"""

    success_rate: Decimal = Decimal("1.000")
    recent_failures: int = 0
    circuit_state: CircuitState = CircuitState.CLOSED

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_rate": str(self.success_rate),
            "recent_failures": self.recent_failures,
            "circuit_state": self.circuit_state.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillHealth:
        if not data:
            return cls()
        return cls(
            success_rate=Decimal(str(data.get("success_rate", "1.000"))),
            recent_failures=data.get("recent_failures", 0),
            circuit_state=CircuitState(data.get("circuit_state", "closed")),
        )


# ---------------------------------------------------------------------------
# 聚合根: Skill (arch.md §2.2.2)
# ---------------------------------------------------------------------------


class Skill:
    """Skill 聚合根。

    不变量:
    - I-C-1: published 后 manifest schema 只能向后兼容变更
    - I-C-2: Run 启动绑定具体版本，生命周期内不动态升级
    - I-C-3: circuit_state=open 时 status 自动转 recalibrating
    """

    def __init__(
        self,
        *,
        id: SkillId | None = None,
        name: str,
        version: SemVer,
        manifest: SkillManifest,
        status: SkillStatus = SkillStatus.DRAFT,
        health: SkillHealth | None = None,
        created_at: datetime | None = None,
    ):
        self.id: SkillId = id or new_id()
        self.name = name
        self.version = version
        self.manifest = manifest
        self.status = status
        self.health = health or SkillHealth()
        self.created_at = created_at or datetime.now(timezone.utc)

        self._pending_events: list[Any] = []

    @property
    def pending_events(self) -> list[Any]:
        return list(self._pending_events)

    def clear_pending_events(self) -> None:
        self._pending_events.clear()

    def _register_event(self, event: Any) -> None:
        self._pending_events.append(event)

    # -- 业务方法 --

    def publish(self) -> None:
        """发布 Skill (draft → published)。"""
        if self.status != SkillStatus.DRAFT:
            raise ValueError(
                f"Only draft skills can be published, current status: {self.status}"
            )
        self.status = SkillStatus.PUBLISHED

        from . import events as evt

        self._register_event(
            evt.SkillPublished(
                event_type="capability.skill.published",
                skill_id=self.id,
                name=self.name,
                version=str(self.version),
            )
        )

    def deprecate(self, *, reason: str = "") -> None:
        """废弃 Skill。"""
        old_status = self.status
        self.status = SkillStatus.DEPRECATED

        from . import events as evt

        self._register_event(
            evt.SkillDeprecated(
                event_type="capability.skill.deprecated",
                skill_id=self.id,
                reason=reason,
                old_status=old_status,
            )
        )

    def cancel(self) -> None:
        """取消 Skill (仅 draft 可取消)。"""
        if self.status not in (SkillStatus.DRAFT, SkillStatus.RECALIBRATING):
            raise ValueError(
                f"Only draft/recalibrating skills can be cancelled, current: {self.status}"
            )
        old_status = self.status
        self.status = SkillStatus.CANCELLED
        from . import events as evt

        self._register_event(
            evt.SkillCancelled(
                event_type="capability.skill.cancelled",
                skill_id=self.id,
                old_status=old_status,
            )
        )

    def open_circuit(self) -> None:
        """I-C-3: 熔断触发 — status 自动转 recalibrating。"""
        self.status = SkillStatus.RECALIBRATING
        self.health = SkillHealth(
            success_rate=self.health.success_rate,
            recent_failures=self.health.recent_failures,
            circuit_state=CircuitState.OPEN,
        )

        from . import events as evt

        self._register_event(
            evt.SkillCircuitOpened(
                event_type="capability.skill.circuit_opened",
                skill_id=self.id,
                recent_failures=self.health.recent_failures,
                success_rate=float(self.health.success_rate),
            )
        )

    def close_circuit(self) -> None:
        """关闭熔断 — 恢复为 published。"""
        if self.health.circuit_state == CircuitState.CLOSED:
            return
        self.health = SkillHealth(
            success_rate=Decimal("1.000"),
            recent_failures=0,
            circuit_state=CircuitState.CLOSED,
        )
        if self.status == SkillStatus.RECALIBRATING:
            self.status = SkillStatus.PUBLISHED
        from . import events as evt

        self._register_event(
            evt.SkillCircuitClosed(
                event_type="capability.skill.circuit_closed",
                skill_id=self.id,
            )
        )

    def half_open_circuit(self) -> None:
        """半开状态 — 试探性恢复。"""
        self.health = SkillHealth(
            success_rate=self.health.success_rate,
            recent_failures=self.health.recent_failures,
            circuit_state=CircuitState.HALF_OPEN,
        )
        from . import events as evt

        self._register_event(
            evt.SkillCircuitHalfOpened(
                event_type="capability.skill.circuit_half_opened",
                skill_id=self.id,
            )
        )

    def update_manifest(self, new_manifest: SkillManifest) -> None:
        """更新 manifest。

        I-C-1: published 后 schema 只能向后兼容变更。
        破坏性变更需要升 major 版本号（由调用方负责）。
        """
        self.manifest = new_manifest

    def update_health(self, new_health: SkillHealth) -> None:
        """更新健康度指标。"""
        self.health = new_health
        # I-C-3: 如果 circuit 已 open，确保 status 同步
        if (
            new_health.circuit_state == CircuitState.OPEN
            and self.status != SkillStatus.RECALIBRATING
        ):
            self.status = SkillStatus.RECALIBRATING

    @property
    def is_assignable(self) -> bool:
        """是否可被分配给 Run。"""
        return (
            self.status == SkillStatus.PUBLISHED
            and self.health.circuit_state != CircuitState.OPEN
        )

    def __repr__(self) -> str:
        return (
            f"Skill(id={self.id}, name={self.name!r}, "
            f"v={self.version}, status={self.status})"
        )
