"""
Shared Kernel — 通用类型定义、ID 类型、值对象。

所有 Bounded Context 共享的基础类型，不包含任何业务逻辑。
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, NewType
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# ID 类型 (基于 UUID)
# ---------------------------------------------------------------------------

MemoryId = Annotated[UUID, "Memory node identifier"]
SkillId = Annotated[UUID, "Skill identifier"]
EmployeeId = Annotated[UUID, "Employee (AI/Human) identifier"]
RunId = Annotated[UUID, "Task execution run identifier"]
DepartmentId = Annotated[UUID, "Department identifier"]
ProjectId = Annotated[UUID, "Project identifier"]
ReviewCaseId = Annotated[UUID, "Review case identifier"]
ConflictCaseId = Annotated[UUID, "Conflict case identifier"]
HarnessAdapterId = Annotated[str, "Harness adapter identifier (varchar PK)"]
HarnessInvocationId = Annotated[UUID, "Harness invocation identifier"]


# ---------------------------------------------------------------------------
# TaskId — 特殊格式: TASK-YYYYMMDDTHHMMSSmmm-XXXX
# ---------------------------------------------------------------------------

TaskId = NewType("TaskId", str)

_TASK_ID_ALPHABET = string.ascii_uppercase + string.digits


def generate_task_id(now: datetime | None = None) -> TaskId:
    """Generate a unique TaskId in the format TASK-YYYYMMDDTHHMMSSmmm-XXXXX.

    The timestamp component provides rough ordering; the 5-char random suffix
    prevents collisions within the same millisecond (36^5 = ~60M combinations).
    """
    ts = now or datetime.now(timezone.utc)
    # millisecond precision
    ms = ts.microsecond // 1000
    time_part = ts.strftime("%Y%m%dT%H%M%S") + f"{ms:03d}"
    suffix = "".join(secrets.choice(_TASK_ID_ALPHABET) for _ in range(5))
    return TaskId(f"TASK-{time_part}-{suffix}")


# ---------------------------------------------------------------------------
# 通用值对象
# ---------------------------------------------------------------------------


class SemVer(BaseModel):
    """Semantic version (major.minor.patch)."""

    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def parse(cls, version_str: str) -> SemVer:
        parts = version_str.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid semver: {version_str}")
        return cls(major=int(parts[0]), minor=int(parts[1]), patch=int(parts[2]))

    def is_backward_compatible_with(self, other: SemVer) -> bool:
        """Return True if *self* is backward-compatible with *other*.

        A version is backward-compatible when the major version is the same
        and the version is equal or newer.
        """
        if self.major != other.major:
            return False
        return (self.minor, self.patch) >= (other.minor, other.patch)


class Priority(StrEnum):
    """Task priority levels (P0 highest, P3 lowest)."""

    P0 = "P0"  # Critical / urgent
    P1 = "P1"  # High
    P2 = "P2"  # Medium (default)
    P3 = "P3"  # Low

    @property
    def ordinal(self) -> int:
        """Numeric ordinal for comparison (lower = higher priority)."""
        return int(self.value[1])


class EmployeeKind(StrEnum):
    """Employee type discriminator."""

    AI = "ai"
    HUMAN = "human"


class ResourceKind(StrEnum):
    """Saga compensation resource categories."""

    EMPLOYEE_CONCURRENCY = "employee_concurrency"
    SANDBOX = "sandbox"
    SKILL_BUNDLE = "skill_bundle"
    OUTBOX_EVENT = "outbox_event"
    EXTERNAL_API = "external_api"


# ---------------------------------------------------------------------------
# 通用辅助
# ---------------------------------------------------------------------------


def new_id() -> UUID:
    """Convenience wrapper for generating a new UUID v4."""
    return uuid4()
