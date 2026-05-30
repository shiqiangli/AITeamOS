"""
Capability Context — Skill SPI Protocol (arch.md §4.1.1)。

所有 Skill 必须实现此协议；通过 Python entry-point 注册到 Skill Registry。
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .models import SkillHealth, SkillManifest


# ---------------------------------------------------------------------------
# Supporting Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillContext:
    """Skill 执行上下文。"""

    run_id: str = ""
    task_id: str = ""
    member_id: str = ""
    permissions: list[str] = field(default_factory=list)
    budget_remaining_tokens: int = 0


@dataclass(frozen=True)
class SkillReadiness:
    """Skill 预检结果。"""

    ready: bool = True
    blockers: list[str] = field(default_factory=list)
    locked_version: str = ""


@dataclass(frozen=True)
class SkillResult:
    """Skill 执行结果。"""

    success: bool = True
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    tokens_used: int = 0


@dataclass(frozen=True)
class ConflictReport:
    """Skill 冲突报告。"""

    conflict_kind: str  # schema_mismatch | resource_collision | ordering_dependency
    skill_a_name: str
    skill_b_name: str
    detail: str = ""

    @classmethod
    def resource_collision(cls, a_name: str, b_name: str, pattern: str) -> ConflictReport:
        return cls(
            conflict_kind="resource_collision",
            skill_a_name=a_name,
            skill_b_name=b_name,
            detail=f"Both skills mutate resource: {pattern}",
        )

    @classmethod
    def schema_mismatch(cls, a_name: str, b_name: str, detail: str) -> ConflictReport:
        return cls(
            conflict_kind="schema_mismatch",
            skill_a_name=a_name,
            skill_b_name=b_name,
            detail=detail,
        )


@dataclass(frozen=True)
class Fixture:
    """Hermetic fixture for offline testing."""

    name: str
    input_data: dict[str, Any] = field(default_factory=dict)
    expected_output: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SkillSPI Protocol (arch.md §4.1.1)
# ---------------------------------------------------------------------------


@runtime_checkable
class SkillSPI(Protocol):
    """所有 Skill 必须实现此协议。

    通过 Python entry-point group 'aiteamos.skills' 注册到 Skill Registry。
    设计原则:
    - 调用无状态: 不持有任何跨调用的实例字段
    - 定义可演进: Skill 升级走 SemVer
    - 副作用显式: side_effects 必须声明，否则冲突检测无法工作
    """

    @property
    @abstractmethod
    def manifest(self) -> SkillManifest:
        """返回 Skill 元数据。"""
        ...

    @abstractmethod
    def precheck(self, ctx: SkillContext) -> SkillReadiness:
        """装载前预检。"""
        ...

    @abstractmethod
    async def invoke(self, input: dict[str, Any]) -> SkillResult:
        """无状态执行。"""
        ...

    @abstractmethod
    def healthcheck(self) -> SkillHealth:
        """返回 Skill 的运行时健康度。"""
        ...

    @abstractmethod
    def conflicts_with(self, other: SkillManifest) -> ConflictReport | None:
        """声明与其他 Skill 的冲突。返回 None 表示无冲突。"""
        ...

    @classmethod
    @abstractmethod
    def fixtures(cls) -> list[Fixture]:
        """提供 hermetic fixture 用于离线测试。"""
        ...
