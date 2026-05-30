"""
Capability Context — 领域事件 (arch.md §2.2.2, §4.1)。
"""

from __future__ import annotations

from aiteamos_shared.events import VersionedDomainEvent
from aiteamos_shared.types import SkillId


class SkillRegistered(VersionedDomainEvent):
    """Skill 注册。"""

    event_type: str = "capability.skill.registered"
    skill_id: SkillId
    name: str
    version: str


class SkillPublished(VersionedDomainEvent):
    """Skill 发布。"""

    event_type: str = "capability.skill.published"
    skill_id: SkillId
    name: str
    version: str


class SkillDeprecated(VersionedDomainEvent):
    """Skill 废弃。"""

    event_type: str = "capability.skill.deprecated"
    skill_id: SkillId
    reason: str
    old_status: str


class SkillCircuitOpened(VersionedDomainEvent):
    """Skill 熔断触发。"""

    event_type: str = "capability.skill.circuit_opened"
    skill_id: SkillId
    recent_failures: int
    success_rate: float


class SkillCircuitClosed(VersionedDomainEvent):
    """Skill 熔断关闭 — 恢复正常。"""

    event_type: str = "capability.skill.circuit_closed"
    skill_id: SkillId


class SkillCircuitHalfOpened(VersionedDomainEvent):
    """Skill 熔断半开 — 试探性恢复。"""

    event_type: str = "capability.skill.circuit_half_opened"
    skill_id: SkillId


class SkillCancelled(VersionedDomainEvent):
    """Skill 取消。"""

    event_type: str = "capability.skill.cancelled"
    skill_id: SkillId
    old_status: str
