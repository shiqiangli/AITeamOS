"""Execution Context — 领域异常。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaskNotFoundError(Exception):
    task_id: str

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


@dataclass
class InvalidStateTransition(Exception):
    from_state: str
    to_state: str

    def __init__(self, from_state: str, to_state: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Illegal transition: {from_state} -> {to_state}")


@dataclass
class TaskDependencyError(Exception):
    task_id: str
    dependency_id: str

    def __init__(self, task_id: str, dependency_id: str) -> None:
        self.task_id = task_id
        self.dependency_id = dependency_id
        super().__init__(f"Dependency violation: {task_id} depends on {dependency_id}")
