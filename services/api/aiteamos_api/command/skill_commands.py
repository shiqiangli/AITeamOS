"""
API Gateway — Skill Write Routes (plan.md §1.5.3).

POST  /api/v1/skills              — 注册
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
)

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1/skills", tags=["skill-write"])

_register_handler: RegisterSkillHandler | None = None
_publish_handler: PublishSkillHandler | None = None
_deprecate_handler: DeprecateSkillHandler | None = None


def init_routes(
    *,
    register_handler: RegisterSkillHandler,
    publish_handler: PublishSkillHandler,
    deprecate_handler: DeprecateSkillHandler,
) -> None:
    global _register_handler, _publish_handler, _deprecate_handler
    _register_handler = register_handler
    _publish_handler = publish_handler
    _deprecate_handler = deprecate_handler


class RegisterSkillRequest(BaseModel):
    name: str
    version: str = "1.0.0"  # "major.minor.patch"
    description: str = ""
    domain: str = ""
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    side_effects: list[dict[str, str]] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    capability_tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    quality_signals: dict[str, Any] = Field(default_factory=dict)
    token_estimate: int = 0
    time_estimate_seconds: float = 0.0


class DeprecateSkillRequest(BaseModel):
    reason: str = ""


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
        inputs=body.inputs,
        outputs=body.outputs,
        preconditions=body.preconditions,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        side_effects=body.side_effects,
        required_permissions=body.required_permissions,
        capability_tags=body.capability_tags,
        examples=body.examples,
        references=body.references,
        quality_signals=body.quality_signals,
        token_estimate=body.token_estimate,
        time_estimate_seconds=body.time_estimate_seconds,
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
