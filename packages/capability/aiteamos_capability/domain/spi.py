"""
Capability Context — Skill SPI Protocol。

所有 Skill 实现需要遵循的基本协议。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Supporting Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillContext:
    """Skill 执行上下文。"""

    run_id: str = ""
    task_id: str = ""
    member_id: str = ""


@dataclass(frozen=True)
class SkillResult:
    """Skill 执行结果。"""

    success: bool = True
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""


# ---------------------------------------------------------------------------
# SkillSPI Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SkillSPI(Protocol):
    """所有 Skill 必须实现此协议。"""

    @property
    def name(self) -> str:
        """Skill 名称。"""
        ...

    @property
    def domain(self) -> str:
        """Skill 所属领域。"""
        ...

    async def invoke(self, input: dict[str, Any]) -> SkillResult:
        """执行 Skill。"""
        ...
