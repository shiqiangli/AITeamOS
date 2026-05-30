"""Workforce Context — 领域异常。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class MemberNotFoundError(Exception):
    member_id: UUID

    def __init__(self, member_id: UUID) -> None:
        self.member_id = member_id
        super().__init__(f"Member {member_id} not found")


@dataclass
class ConcurrencyLimitError(Exception):
    member_id: UUID
    current_load: int

    def __init__(self, member_id: UUID, current_load: int) -> None:
        self.member_id = member_id
        self.current_load = current_load
        super().__init__(f"Member {member_id} concurrency limit exceeded (load={current_load})")


@dataclass
class DepartmentNotFoundError(Exception):
    department_id: UUID

    def __init__(self, department_id: UUID) -> None:
        self.department_id = department_id
        super().__init__(f"Department {department_id} not found")
