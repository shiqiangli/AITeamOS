"""
Capability Context — Application Commands (CQRS write side).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aiteamos_shared.types import SkillId, SemVer

from ..domain.models import SkillStatus


@dataclass(frozen=True)
class RegisterSkillCommand:
    """注册 Skill — 角色能力标签。"""

    name: str
    version: SemVer
    description: str = ""
    domain: str = ""
    capability_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PublishSkillCommand:
    """发布 Skill (draft → published)。"""

    skill_id: SkillId


@dataclass(frozen=True)
class DeprecateSkillCommand:
    """废弃 Skill。"""

    skill_id: SkillId
    reason: str = ""


@dataclass(frozen=True)
class UpdateSkillCommand:
    """更新 Skill 核心属性。"""

    skill_id: SkillId
    description: str = ""
    domain: str = ""
    capability_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ListSkillsQuery:
    """Skill 列表查询。"""

    status: SkillStatus | None = None
    name_filter: str | None = None
    offset: int = 0
    limit: int = 50


@dataclass(frozen=True)
class GetSkillDetailQuery:
    """Skill 详情查询。"""

    skill_id: SkillId


@dataclass(frozen=True)
class SearchSkillsByTagQuery:
    """按标签搜索 Skill。"""

    tags: list[str]
    limit: int = 20
