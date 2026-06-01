"""
API Gateway — Task Write Routes (plan.md §2.5.1).

POST   /api/v1/tasks                    — 创建 Task
PUT    /api/v1/tasks/{id}               — 更新
POST   /api/v1/tasks/{id}/assign        — 分配 Member
POST   /api/v1/tasks/{id}/start         — 启动执行
POST   /api/v1/tasks/{id}/submit-deliverable — 提交交付物
POST   /api/v1/tasks/{id}/cancel        — 取消
POST   /api/v1/tasks/{id}/requeue       — 重新排队 (Failed → Ready)
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aiteamos_execution.application.handlers import (
    AssignTaskHandler,
    CreateTaskHandler,
    StartRunHandler,
    SubmitDeliverableHandler,
    TransitionTaskHandler,
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1/tasks", tags=["task-write"])

_create_handler: CreateTaskHandler | None = None
_assign_handler: AssignTaskHandler | None = None
_start_handler: StartRunHandler | None = None
_submit_handler: SubmitDeliverableHandler | None = None
_transition_handler: TransitionTaskHandler | None = None
_db: Any = None


def init_routes(
    *,
    create_handler: CreateTaskHandler,
    assign_handler: AssignTaskHandler,
    start_handler: StartRunHandler,
    submit_handler: SubmitDeliverableHandler,
    transition_handler: TransitionTaskHandler,
    db: Any = None,
) -> None:
    global _create_handler, _assign_handler, _start_handler, _submit_handler, _transition_handler, _db
    _create_handler = create_handler
    _assign_handler = assign_handler
    _start_handler = start_handler
    _submit_handler = submit_handler
    _transition_handler = transition_handler
    _db = db


# --- Request Bodies ---


class CreateTaskRequest(BaseModel):
    department_id: str
    title: str
    description: str = ""
    priority: str = "P2"
    project_ids: list[str] = Field(default_factory=list)
    parent_task_id: Optional[str] = None
    declared_skills: list[str] = Field(default_factory=list)
    declared_memory_hints: list[str] = Field(default_factory=list)
    deliverable_kind: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    max_retry_count: int = 3
    max_review_rounds: int = 3


class AssignTaskRequest(BaseModel):
    member_id: str


class StartRunRequest(BaseModel):
    member_id: Optional[str] = None


class SubmitDeliverableRequest(BaseModel):
    run_id: str
    deliverable_type: str
    uri: str


@router.post("", status_code=201, response_model=dict[str, Any])
async def create_task(
    body: CreateTaskRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _create_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_execution.application.commands import CreateTaskCommand

    cmd = CreateTaskCommand(
        department_id=UUID(body.department_id),  # type: ignore[arg-type]
        title=body.title,
        description=body.description,
        priority=body.priority,
        project_ids=[UUID(p) for p in body.project_ids],  # type: ignore[arg-type]
        parent_task_id=body.parent_task_id,
        declared_skills=[UUID(s) for s in body.declared_skills],  # type: ignore[arg-type]
        declared_memory_hints=[UUID(m) for m in body.declared_memory_hints],  # type: ignore[arg-type]
        deliverable_kind=body.deliverable_kind,
        acceptance_criteria=body.acceptance_criteria,
        max_retry_count=body.max_retry_count,
        max_review_rounds=body.max_review_rounds,
    )
    task = await _create_handler.handle(cmd)
    return {"id": task.id, "state": task.state.value, "status": "created"}


@router.post("/{task_id}/assign", response_model=dict[str, Any])
async def assign_task(
    task_id: str,
    body: AssignTaskRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _assign_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_execution.application.commands import AssignTaskCommand

    cmd = AssignTaskCommand(
        task_id=task_id,
        member_id=UUID(body.member_id),  # type: ignore[arg-type]
    )
    task = await _assign_handler.handle(cmd)
    return {"id": task.id, "state": task.state.value, "assigned_member_id": body.member_id}


@router.post("/{task_id}/start", response_model=dict[str, Any])
async def start_run(
    task_id: str,
    body: StartRunRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _start_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_execution.application.commands import StartRunCommand

    member_id = UUID(body.member_id) if body.member_id else None  # type: ignore[arg-type]
    cmd = StartRunCommand(task_id=task_id, member_id=member_id)
    task = await _start_handler.handle(cmd)
    return {"id": task.id, "state": task.state.value, "runs_count": len(task.runs)}


@router.post("/{task_id}/submit-deliverable", response_model=dict[str, Any])
async def submit_deliverable(
    task_id: str,
    body: SubmitDeliverableRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _submit_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_execution.application.commands import SubmitDeliverableCommand

    cmd = SubmitDeliverableCommand(
        task_id=task_id,
        run_id=UUID(body.run_id),  # type: ignore[arg-type]
        deliverable_type=body.deliverable_type,
        uri=body.uri,
    )
    task = await _submit_handler.handle(cmd)
    return {"id": task.id, "state": task.state.value, "status": "deliverable_submitted"}


@router.post("/{task_id}/cancel", response_model=dict[str, Any])
async def cancel_task(
    task_id: str,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _transition_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_execution.application.commands import TransitionTaskCommand

    cmd = TransitionTaskCommand(
        task_id=task_id,
        to_state="cancelled",
        reason="user_cancelled",
    )
    task = await _transition_handler.handle(cmd)
    return {"id": task.id, "state": task.state.value}


@router.post("/{task_id}/requeue", response_model=dict[str, Any])
async def requeue_task(
    task_id: str,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _transition_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_execution.application.commands import TransitionTaskCommand

    cmd = TransitionTaskCommand(
        task_id=task_id,
        to_state="ready",
        reason="requeue",
    )
    task = await _transition_handler.handle(cmd)
    return {"id": task.id, "state": task.state.value}


@router.post("/{task_id}/complete-info", response_model=dict[str, Any])
async def complete_task_info(
    task_id: str,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Draft → Ready."""
    if _transition_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_execution.application.commands import TransitionTaskCommand

    cmd = TransitionTaskCommand(
        task_id=task_id,
        to_state="ready",
        reason="info_complete",
    )
    task = await _transition_handler.handle(cmd)
    return {"id": task.id, "state": task.state.value}


# --- Update ---


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    deliverable_kind: Optional[str] = None
    max_retry_count: Optional[int] = None
    max_review_rounds: Optional[int] = None


@router.put("/{task_id}", response_model=dict[str, Any])
async def update_task(
    task_id: str,
    body: UpdateTaskRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Update editable fields of a task."""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    fields: list[str] = []
    values: list[Any] = []
    idx = 1

    if body.title is not None:
        fields.append(f"title = ${idx}")
        values.append(body.title)
        idx += 1
    if body.description is not None:
        fields.append(f"description = ${idx}")
        values.append(body.description)
        idx += 1
    if body.priority is not None:
        fields.append(f"priority = ${idx}")
        values.append(body.priority)
        idx += 1

    # JSONB column: deliverable_spec (kind)
    if body.deliverable_kind is not None:
        fields.append(
            f"deliverable_spec = jsonb_set(COALESCE(deliverable_spec, '{{}}'::jsonb), '{{kind}}', to_jsonb(${idx}::text))"
        )
        values.append(body.deliverable_kind)
        idx += 1

    # JSONB column: budget (max_retry_count, max_review_rounds) — merge into one SET
    budget_patch: dict[str, Any] = {}
    if body.max_retry_count is not None:
        budget_patch["max_retry_count"] = body.max_retry_count
    if body.max_review_rounds is not None:
        budget_patch["max_review_rounds"] = body.max_review_rounds
    if budget_patch:
        import json as _json
        fields.append(
            f"budget = COALESCE(budget, '{{}}'::jsonb) || ${idx}::jsonb"
        )
        values.append(_json.dumps(budget_patch))
        idx += 1

    if not fields:
        return {"id": task_id, "status": "no_changes"}

    fields.append("updated_at = now()")
    sql = f"UPDATE task SET {', '.join(fields)} WHERE id = ${idx} RETURNING id, title, state"
    values.append(task_id)

    row = await _db.fetchrow(sql, *values)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return {"id": str(row["id"]), "title": row["title"], "state": row["state"], "status": "updated"}
