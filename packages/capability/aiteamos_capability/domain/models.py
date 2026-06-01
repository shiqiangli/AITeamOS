"""
Capability Context — 领域模型 (arch.md §2.2.2)。

Skill 是角色的能力标签，绑定到 Member，不是任务属性。

聚合根:
- Skill: 能力注册、版本、生命周期

值对象:
- SkillStatus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from aiteamos_shared.types import SkillId, SemVer, new_id


# ---------------------------------------------------------------------------
# 枚举值对象
# ---------------------------------------------------------------------------


class SkillStatus(StrEnum):
    """Skill 生命周期状态。"""

    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


# ---------------------------------------------------------------------------
# 聚合根: Skill
# ---------------------------------------------------------------------------


class Skill:
    """Skill 聚合根 — 角色的能力标签。

    Skill 绑定到 Member（通过 base_skill_set），
    表达该角色"能做什么"，而非"怎么做"。

    程序性上下文（how）通过 .aiteamos/skills/{name}/SKILL.md 文件承载。
    """

    def __init__(
        self,
        *,
        id: SkillId | None = None,
        name: str,
        version: SemVer,
        description: str = "",
        domain: str = "",
        status: SkillStatus = SkillStatus.DRAFT,
        capability_tags: list[str] | None = None,
        created_at: datetime | None = None,
    ):
        self.id: SkillId = id or new_id()
        self.name = name
        self.version = version
        self.description = description
        self.domain = domain
        self.status = status
        self.capability_tags: list[str] = capability_tags or []
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

    def update(self, *, description: str, domain: str, capability_tags: list[str]) -> None:
        """更新 Skill 的核心属性。"""
        self.description = description
        self.domain = domain
        self.capability_tags = capability_tags

    @property
    def is_assignable(self) -> bool:
        """是否可被分配给 Member。"""
        return self.status == SkillStatus.PUBLISHED

    def __repr__(self) -> str:
        return (
            f"Skill(id={self.id}, name={self.name!r}, "
            f"v={self.version}, status={self.status})"
        )
