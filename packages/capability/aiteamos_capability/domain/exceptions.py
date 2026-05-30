"""Capability Context — 领域异常。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class SkillNotFoundError(Exception):
    skill_id: UUID

    def __init__(self, skill_id: UUID) -> None:
        self.skill_id = skill_id
        super().__init__(f"Skill {skill_id} not found")


@dataclass
class SkillInvariantError(Exception):
    message: str

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class SkillCircuitOpenError(Exception):
    skill_id: UUID

    def __init__(self, skill_id: UUID) -> None:
        self.skill_id = skill_id
        super().__init__(f"Skill {skill_id} circuit breaker is open")
