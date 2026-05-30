"""
API Gateway — Member / Project Write Routes (plan.md §1.5.3).

POST /api/v1/members                — 创建
POST /api/v1/departments            — 创建
POST /api/v1/projects               — 创建
PUT  /api/v1/projects/{id}          — 更新
POST /api/v1/projects/{id}/members  — 分配 Member 到 Project
POST /api/v1/members/{id}/skills    — 分配 Skill
POST /api/v1/members/{id}/memories  — 分配 Memory
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aiteamos_workforce.application.handlers import (
    AssignMemberToProjectHandler,
    AssignMemoryToMemberHandler,
    AssignSkillToMemberHandler,
    CreateDepartmentHandler,
    CreateMemberHandler,
    CreateProjectHandler,
    UpdateProjectHandler,
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(tags=["workforce-write"])

_create_member_handler: CreateMemberHandler | None = None
_create_department_handler: CreateDepartmentHandler | None = None
_create_project_handler: CreateProjectHandler | None = None
_update_project_handler: UpdateProjectHandler | None = None
_assign_member_handler: AssignMemberToProjectHandler | None = None
_assign_skill_handler: AssignSkillToMemberHandler | None = None
_assign_memory_handler: AssignMemoryToMemberHandler | None = None
_db: Any = None


def init_routes(
    *,
    create_member_handler: CreateMemberHandler,
    create_department_handler: CreateDepartmentHandler,
    create_project_handler: CreateProjectHandler,
    update_project_handler: UpdateProjectHandler,
    assign_member_handler: AssignMemberToProjectHandler,
    assign_skill_handler: AssignSkillToMemberHandler,
    assign_memory_handler: AssignMemoryToMemberHandler,
    db: Any = None,
) -> None:
    global _db
    global _create_member_handler, _create_department_handler
    global _create_project_handler, _update_project_handler
    global _assign_member_handler, _assign_skill_handler, _assign_memory_handler
    _create_member_handler = create_member_handler
    _create_department_handler = create_department_handler
    _create_project_handler = create_project_handler
    _update_project_handler = update_project_handler
    _assign_member_handler = assign_member_handler
    _assign_skill_handler = assign_skill_handler
    _assign_memory_handler = assign_memory_handler
    _db = db


# --- Request Bodies ---


class CreateMemberRequest(BaseModel):
    kind: str  # "ai" | "human"
    department_id: str
    display_name: str = ""
    role: str = ""
    concurrency_limit: int = 1


class CreateDepartmentRequest(BaseModel):
    name: str
    leader_member_id: Optional[str] = None
    backup_leader_member_id: Optional[str] = None


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    department_id: str
    repository_refs: list[str] = Field(default_factory=list)


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    repository_refs: Optional[list[str]] = None


class AssignMemberRequest(BaseModel):
    member_id: str


class AssignSkillRequest(BaseModel):
    skill_id: Optional[str] = None
    skill_name: Optional[str] = None


class AssignMemoryRequest(BaseModel):
    memory_id: str


@router.post("/api/v1/members", status_code=201, response_model=dict[str, Any])
async def create_member(
    body: CreateMemberRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _create_member_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_shared.types import MemberKind
    from aiteamos_workforce.application.commands import CreateMemberCommand

    cmd = CreateMemberCommand(
        kind=MemberKind(body.kind),
        department_id=UUID(body.department_id),  # type: ignore[arg-type]
        display_name=body.display_name,
        role=body.role,
        concurrency_limit=body.concurrency_limit,
    )
    member = await _create_member_handler.handle(cmd)
    return {"id": str(member.id), "status": "created"}


@router.post("/api/v1/departments", status_code=201, response_model=dict[str, Any])
async def create_department(
    body: CreateDepartmentRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _create_department_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import CreateDepartmentCommand

    cmd = CreateDepartmentCommand(
        name=body.name,
        leader_member_id=UUID(body.leader_member_id) if body.leader_member_id else None,  # type: ignore[arg-type]
        backup_leader_member_id=UUID(body.backup_leader_member_id) if body.backup_leader_member_id else None,  # type: ignore[arg-type]
    )
    dept = await _create_department_handler.handle(cmd)
    return {"id": str(dept.id), "status": "created"}


@router.post("/api/v1/projects", status_code=201, response_model=dict[str, Any])
async def create_project(
    body: CreateProjectRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _create_project_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import CreateProjectCommand

    cmd = CreateProjectCommand(
        name=body.name,
        description=body.description,
        department_id=UUID(body.department_id),  # type: ignore[arg-type]
        repository_refs=body.repository_refs,
    )
    project = await _create_project_handler.handle(cmd)
    return {"id": str(project.id), "status": "created"}


@router.put("/api/v1/projects/{project_id}", response_model=dict[str, Any])
async def update_project(
    project_id: UUID,
    body: UpdateProjectRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _update_project_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import UpdateProjectCommand

    cmd = UpdateProjectCommand(
        project_id=project_id,  # type: ignore[arg-type]
        name=body.name,
        description=body.description,
        repository_refs=body.repository_refs,
    )
    project = await _update_project_handler.handle(cmd)
    return {"id": str(project.id), "status": "updated"}


@router.post("/api/v1/projects/{project_id}/members", status_code=201, response_model=dict[str, Any])
async def assign_member_to_project(
    project_id: UUID,
    body: AssignMemberRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _assign_member_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import AssignMemberToProjectCommand

    cmd = AssignMemberToProjectCommand(
        project_id=project_id,  # type: ignore[arg-type]
        member_id=UUID(body.member_id),  # type: ignore[arg-type]
    )
    project = await _assign_member_handler.handle(cmd)
    return {"id": str(project.id), "status": "member_assigned"}


@router.post("/api/v1/members/{member_id}/skills", status_code=201, response_model=dict[str, Any])
async def assign_skill_to_member(
    member_id: UUID,
    body: AssignSkillRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _assign_skill_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import AssignSkillToMemberCommand

    skill_id = await _resolve_skill_id(body)
    cmd = AssignSkillToMemberCommand(
        member_id=member_id,  # type: ignore[arg-type]
        skill_id=skill_id,  # type: ignore[arg-type]
    )
    member = await _assign_skill_handler.handle(cmd)
    return {"id": str(member.id), "status": "skill_assigned"}


@router.post("/api/v1/members/{member_id}/memories", status_code=201, response_model=dict[str, Any])
async def assign_memory_to_member(
    member_id: UUID,
    body: AssignMemoryRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _assign_memory_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_workforce.application.commands import AssignMemoryToMemberCommand

    cmd = AssignMemoryToMemberCommand(
        member_id=member_id,  # type: ignore[arg-type]
        memory_id=UUID(body.memory_id),  # type: ignore[arg-type]
    )
    member = await _assign_memory_handler.handle(cmd)
    return {"id": str(member.id), "status": "memory_assigned"}


async def _resolve_skill_id(body: AssignSkillRequest) -> UUID:
    if body.skill_id:
        return UUID(body.skill_id)
    skill_name = (body.skill_name or "").strip()
    if not skill_name:
        raise HTTPException(status_code=422, detail="skill_name is required")
    if _db is None:
        raise HTTPException(status_code=503, detail="Skill name lookup not available")
    row = await _db.fetchrow("SELECT id FROM skill WHERE name = $1 LIMIT 1", skill_name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_name} not found")
    return UUID(str(row["id"]))
