"""
Execution Context — Application Queries (CQRS read side)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from aiteamos_shared.types import TaskId


@dataclass
class TaskSummary:
    """Task 列表投影。"""

    id: str
    title: str
    state: str
    priority: str
    assigned_member_id: str | None
    department_id: str
    retry_count: int
    review_round: int
    created_at: Any
    assigned_llm_model_id: str | None = None
    assigned_agent_profile_id: str | None = None


class TaskReadRepoLike(Protocol):
    async def list_tasks(
        self,
        *,
        department_id: str | None = None,
        state: str | None = None,
        assigned_member_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[TaskSummary]: ...

    async def get_task_detail(self, task_id: str) -> Any | None: ...


class ListTasksExecutor:
    """查询 Task 列表。"""

    def __init__(self, *, read_repo: TaskReadRepoLike):
        self._repo = read_repo

    async def execute(
        self,
        *,
        department_id: str | None = None,
        state: str | None = None,
        assigned_member_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[TaskSummary]:
        return await self._repo.list_tasks(
            department_id=department_id,
            state=state,
            assigned_member_id=assigned_member_id,
            offset=offset,
            limit=limit,
        )


class GetTaskDetailExecutor:
    """查询 Task 详情。"""

    def __init__(self, *, read_repo: TaskReadRepoLike):
        self._repo = read_repo

    async def execute(self, task_id: str) -> Any | None:
        return await self._repo.get_task_detail(task_id)
