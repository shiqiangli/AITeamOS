"""
API Gateway — Task Read Routes (plan.md §2.5.1).

GET /api/v1/tasks              — 列表（支持状态/优先级/Department 筛选）
GET /api/v1/tasks/{id}         — 详情
GET /api/v1/tasks/{id}/runs    — 执行历史
GET /api/v1/tasks/queue        — 按优先级排队视图
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from aiteamos_execution.application.queries import (
    GetTaskDetailExecutor,
    ListTasksExecutor,
    TaskSummary,
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1/tasks", tags=["task-read"])

_list_executor: ListTasksExecutor | None = None
_detail_executor: GetTaskDetailExecutor | None = None


def init_routes(
    *,
    list_executor: ListTasksExecutor,
    detail_executor: GetTaskDetailExecutor,
) -> None:
    global _list_executor, _detail_executor
    _list_executor = list_executor
    _detail_executor = detail_executor


@router.get("", response_model=list[dict[str, Any]])
async def list_tasks(
    department_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    assigned_member_id: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _list_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    results = await _list_executor.execute(
        department_id=department_id,
        state=state,
        assigned_member_id=assigned_member_id,
        offset=offset,
        limit=limit,
    )
    return [_summary_to_dict(r) for r in results]


@router.get("/queue", response_model=list[dict[str, Any]])
async def get_task_queue(
    department_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """按优先级排队视图 — 仅显示 ready/assigned 状态。"""
    if _list_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    results = await _list_executor.execute(
        department_id=department_id,
        state="ready",
        offset=0,
        limit=limit,
    )
    return [_summary_to_dict(r) for r in results]


@router.get("/{task_id}", response_model=dict[str, Any])
async def get_task_detail(
    task_id: str,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _detail_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    result = await _detail_executor.execute(task_id)
    if result is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"Task {task_id} not found")
    return result


@router.get("/{task_id}/runs", response_model=list[dict[str, Any]])
async def get_task_runs(
    task_id: str,
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _detail_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    result = await _detail_executor.execute(task_id)
    if result is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"Task {task_id} not found")
    return result.get("runs", [])


def _summary_to_dict(s: TaskSummary) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "state": s.state,
        "priority": s.priority,
        "department_id": s.department_id,
        "retry_count": s.retry_count,
        "review_round": s.review_round,
        "created_at": str(s.created_at) if s.created_at else None,
    }
