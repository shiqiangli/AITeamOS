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
