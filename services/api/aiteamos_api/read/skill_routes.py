"""
API Gateway — Skill Read Routes.

GET  /api/v1/skills              — 分页列表
GET  /api/v1/skills/{id}         — 详情
GET  /api/v1/skills/{id}/file    — SKILL.md 文件内容
"""

from __future__ import annotations

import os
import pathlib
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
_db: Any = None

# Project root: where .aiteamos/ lives
_PROJECT_ROOT = pathlib.Path(os.environ.get("AITEAMOS_PROJECT_ROOT", os.getcwd()))


def init_routes(
    *,
    list_executor: ListSkillsExecutor,
    detail_executor: GetSkillDetailExecutor,
    db: Any = None,
) -> None:
    global _list_executor, _detail_executor, _db
    _list_executor = list_executor
    _detail_executor = detail_executor
    _db = db


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
        "capability_tags": result.capability_tags,
        "created_at": str(result.created_at) if result.created_at else None,
    }


@router.get("/{skill_id}/file", response_model=dict[str, Any])
async def get_skill_file(
    skill_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """读取 Skill 对应的 SKILL.md 文件内容。"""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Look up skill name from DB
    row = await _db.fetchrow("SELECT name FROM skill WHERE id = $1", str(skill_id))
    if row is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"Skill {skill_id} not found")

    skill_name = row["name"]
    file_path = _PROJECT_ROOT / ".aiteamos" / "skills" / skill_name / "SKILL.md"

    if not file_path.is_file():
        return {
            "skill_id": str(skill_id),
            "skill_name": skill_name,
            "file_path": str(file_path.relative_to(_PROJECT_ROOT)),
            "content": "",
            "exists": False,
        }

    content = file_path.read_text(encoding="utf-8")
    return {
        "skill_id": str(skill_id),
        "skill_name": skill_name,
        "file_path": str(file_path.relative_to(_PROJECT_ROOT)),
        "content": content,
        "exists": True,
    }
