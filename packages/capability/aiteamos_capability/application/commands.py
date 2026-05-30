"""
Capability Context — Application Commands (CQRS write side).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiteamos_shared.types import SkillId, SemVer

from ..domain.models import SkillStatus


@dataclass(frozen=True)
class RegisterSkillCommand:
    """注册 Skill。"""

    name: str
    version: SemVer
    description: str
    domain: str
    inputs: list[str]
    outputs: list[str]
    preconditions: list[str]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effects: list[dict[str, str]]  # [{resource_kind, resource_pattern, mutation_kind}]
    required_permissions: list[str]
    capability_tags: list[str]
    examples: list[str]
    references: list[str]
    quality_signals: dict[str, Any]
    token_estimate: int = 0
    time_estimate_seconds: float = 0.0


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
class UpdateSkillManifestCommand:
    """更新 Skill Manifest (需校验向后兼容)。"""

    skill_id: SkillId
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effects: list[dict[str, str]]
    required_permissions: list[str]
    capability_tags: list[str]
    domain: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    preconditions: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    quality_signals: dict[str, Any] = field(default_factory=dict)
    description: str = ""


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
