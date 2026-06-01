"""
API Gateway — Skill Write Routes.

POST  /api/v1/skills              — 注册
PUT   /api/v1/skills/{id}         — 更新
PATCH /api/v1/skills/{id}/publish — 发布
PATCH /api/v1/skills/{id}/deprecate — 废弃
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aiteamos_capability.application.handlers import (
    DeprecateSkillHandler,
    PublishSkillHandler,
    RegisterSkillHandler,
    UpdateSkillHandler,
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1/skills", tags=["skill-write"])

_register_handler: RegisterSkillHandler | None = None
_publish_handler: PublishSkillHandler | None = None
_deprecate_handler: DeprecateSkillHandler | None = None
_update_handler: UpdateSkillHandler | None = None


def init_routes(
    *,
    register_handler: RegisterSkillHandler,
    publish_handler: PublishSkillHandler,
    deprecate_handler: DeprecateSkillHandler,
    update_handler: UpdateSkillHandler | None = None,
) -> None:
    global _register_handler, _publish_handler, _deprecate_handler, _update_handler
    _register_handler = register_handler
    _publish_handler = publish_handler
    _deprecate_handler = deprecate_handler
    _update_handler = update_handler


class RegisterSkillRequest(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str = ""
    domain: str = ""
    capability_tags: list[str] = Field(default_factory=list)


class DeprecateSkillRequest(BaseModel):
    reason: str = ""


class UpdateSkillRequest(BaseModel):
    description: str = ""
    domain: str = ""
    capability_tags: list[str] = Field(default_factory=list)


@router.post("", status_code=201, response_model=dict[str, Any])
async def register_skill(
    body: RegisterSkillRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _register_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_capability.application.commands import RegisterSkillCommand
    from aiteamos_shared.types import SemVer

    version = SemVer.parse(body.version)
    cmd = RegisterSkillCommand(
        name=body.name,
        version=version,
        description=body.description,
        domain=body.domain,
        capability_tags=body.capability_tags,
    )
    skill = await _register_handler.handle(cmd)
    return {"id": str(skill.id), "status": "registered"}


@router.patch("/{skill_id}/publish", response_model=dict[str, Any])
async def publish_skill(
    skill_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _publish_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_capability.application.commands import PublishSkillCommand

    cmd = PublishSkillCommand(skill_id=skill_id)  # type: ignore[arg-type]
    skill = await _publish_handler.handle(cmd)
    return {"id": str(skill.id), "status": "published"}


@router.patch("/{skill_id}/deprecate", response_model=dict[str, Any])
async def deprecate_skill(
    skill_id: UUID,
    body: DeprecateSkillRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _deprecate_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_capability.application.commands import DeprecateSkillCommand

    cmd = DeprecateSkillCommand(skill_id=skill_id, reason=body.reason)  # type: ignore[arg-type]
    skill = await _deprecate_handler.handle(cmd)
    return {"id": str(skill.id), "status": "deprecated"}


@router.put("/{skill_id}", response_model=dict[str, Any])
async def update_skill(
    skill_id: UUID,
    body: UpdateSkillRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _update_handler is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    from aiteamos_capability.application.commands import UpdateSkillCommand

    cmd = UpdateSkillCommand(
        skill_id=skill_id,  # type: ignore[arg-type]
        description=body.description,
        domain=body.domain,
        capability_tags=body.capability_tags,
    )
    skill = await _update_handler.handle(cmd)
    return {"id": str(skill.id), "status": "updated"}
