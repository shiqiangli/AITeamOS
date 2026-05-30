"""Knowledge Context — 领域异常。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass
class MemoryNotFoundError(Exception):
    memory_id: UUID

    def __init__(self, memory_id: UUID) -> None:
        self.memory_id = memory_id
        super().__init__(f"Memory {memory_id} not found")


@dataclass
class MemoryInvariantError(Exception):
    message: str

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class MemoryConflictError(Exception):
    memory_a_id: UUID
    memory_b_id: UUID

    def __init__(self, memory_a_id: UUID, memory_b_id: UUID) -> None:
        self.memory_a_id = memory_a_id
        self.memory_b_id = memory_b_id
        super().__init__(f"Conflict between {memory_a_id} and {memory_b_id}")
