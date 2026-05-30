"""
API Gateway — Skill Read Routes (plan.md §1.5.2).

GET /api/v1/skills       — 分页列表
GET /api/v1/skills/{id}  — 详情
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from aiteamos_capability.application.queries import (
    GetSkillDetailExecutor,
    ListSkillsExecutor,
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1/skills", tags=["skill-read"])

_list_executor: ListSkillsExecutor | None = None
_detail_executor: GetSkillDetailExecutor | None = None


def init_routes(
    *,
    list_executor: ListSkillsExecutor,
    detail_executor: GetSkillDetailExecutor,
) -> None:
    global _list_executor, _detail_executor
    _list_executor = list_executor
    _detail_executor = detail_executor


@router.get("", response_model=list[dict[str, Any]])
async def list_skills(
    status: Optional[str] = Query(None),
    name_filter: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _list_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_capability.application.commands import ListSkillsQuery
    from aiteamos_capability.domain.models import SkillStatus

    query = ListSkillsQuery(
        status=SkillStatus(status) if status else None,
        name_filter=name_filter,
        offset=offset,
        limit=limit,
    )
    results = await _list_executor.execute(query)
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "version": r.version,
            "description": r.description,
            "domain": r.domain,
            "status": r.status,
            "circuit_state": r.circuit_state,
            "capability_tags": r.capability_tags,
            "created_at": str(r.created_at) if r.created_at else None,
        }
        for r in results
    ]


@router.get("/{skill_id}", response_model=dict[str, Any])
async def get_skill_detail(
    skill_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _detail_executor is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_capability.application.commands import GetSkillDetailQuery

    query = GetSkillDetailQuery(skill_id=skill_id)  # type: ignore[arg-type]
    result = await _detail_executor.execute(query)
    if result is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"Skill {skill_id} not found")
    return {
        "id": str(result.id),
        "name": result.name,
        "version": result.version,
        "description": result.description,
        "domain": result.domain,
        "status": result.status,
        "circuit_state": result.circuit_state,
        "inputs": result.inputs,
        "outputs": result.outputs,
        "preconditions": result.preconditions,
        "side_effects": result.side_effects,
        "required_permissions": result.required_permissions,
        "capability_tags": result.capability_tags,
        "examples": result.examples,
        "references": result.references,
        "quality_signals": result.quality_signals,
        "manifest": result.manifest,
        "health": result.health,
        "created_at": str(result.created_at) if result.created_at else None,
    }
