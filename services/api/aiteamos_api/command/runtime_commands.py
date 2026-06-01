"""
API Gateway - Runtime Resource Write Routes.

LLM models and agent profiles are neutral resources. Tasks can reference them
without making either resource owned by a member.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1", tags=["runtime-write"])

_db: Any = None


def init_routes(*, db: Any) -> None:
    global _db
    _db = db


class CreateLlmModelRequest(BaseModel):
    name: str
    provider: str
    model_id: str
    endpoint_type: str = "chat"
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    supports_tools: bool = False
    supports_json: bool = False
    input_cost_per_1m: Optional[float] = None
    output_cost_per_1m: Optional[float] = None
    capability_tags: list[str] = Field(default_factory=list)
    status: str = "active"
    notes: Optional[str] = None


class CreateAgentProfileRequest(BaseModel):
    name: str
    description: str = ""
    runtime_kind: str = "llm_agent"
    default_llm_model_id: Optional[UUID] = None
    system_prompt: str = ""
    tool_names: list[str] = Field(default_factory=list)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    safety_policy: dict[str, Any] = Field(default_factory=dict)
    status: str = "active"


class AssignTaskRuntimeRequest(BaseModel):
    llm_model_id: Optional[UUID] = None
    agent_profile_id: Optional[UUID] = None


@router.post("/llm-models", status_code=201, response_model=dict[str, Any])
async def create_llm_model(
    body: CreateLlmModelRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if not body.name.strip() or not body.provider.strip() or not body.model_id.strip():
        raise HTTPException(status_code=422, detail="name, provider, and model_id are required")
    try:
        row = await _db.fetchrow(
            """
            INSERT INTO llm_model (
                name, provider, model_id, endpoint_type, context_window,
                max_output_tokens, supports_tools, supports_json,
                input_cost_per_1m, output_cost_per_1m, capability_tags,
                status, notes
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8,
                $9, $10, $11,
                $12, $13
            )
            RETURNING *
            """,
            body.name.strip(),
            body.provider.strip(),
            body.model_id.strip(),
            body.endpoint_type.strip() or "chat",
            body.context_window or 0,
            body.max_output_tokens or 0,
            body.supports_tools,
            body.supports_json,
            body.input_cost_per_1m or 0,
            body.output_cost_per_1m or 0,
            body.capability_tags,
            body.status,
            body.notes or "",
        )
    except Exception as exc:  # pragma: no cover - asyncpg class may be absent in unit tests
        _raise_write_error(exc, duplicate_detail=f"LLM model {body.name} already exists")
    return _llm_model_to_dict(row)


@router.post("/agent-profiles", status_code=201, response_model=dict[str, Any])
async def create_agent_profile(
    body: CreateAgentProfileRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="name is required")
    try:
        row = await _db.fetchrow(
            """
            INSERT INTO agent_profile (
                name, description, runtime_kind, default_llm_model_id,
                system_prompt, tool_names, memory_policy, safety_policy, status
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7::jsonb, $8::jsonb, $9
            )
            RETURNING *
            """,
            body.name.strip(),
            body.description,
            body.runtime_kind,
            body.default_llm_model_id,
            body.system_prompt,
            body.tool_names,
            json.dumps(body.memory_policy),
            json.dumps(body.safety_policy),
            body.status,
        )
    except Exception as exc:  # pragma: no cover - asyncpg class may be absent in unit tests
        _raise_write_error(exc, duplicate_detail=f"Agent profile {body.name} already exists")
    return _agent_profile_to_dict(row)


def _raise_write_error(
    exc: Exception,
    *,
    duplicate_detail: str | None = None,
    foreign_key_detail: str | None = None,
) -> None:
    exc_name = exc.__class__.__name__
    if exc_name == "UniqueViolationError":
        raise HTTPException(status_code=409, detail=duplicate_detail or "Name already exists") from exc
    if exc_name == "ForeignKeyViolationError":
        raise HTTPException(status_code=422, detail=foreign_key_detail or "Referenced resource not found") from exc
    raise exc


def _llm_model_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "provider": row["provider"],
        "model_id": row["model_id"],
        "endpoint_type": row["endpoint_type"],
        "context_window": row["context_window"],
        "max_output_tokens": row["max_output_tokens"],
        "supports_tools": row["supports_tools"],
        "supports_json": row["supports_json"],
        "input_cost_per_1m": _number_or_none(row["input_cost_per_1m"]),
        "output_cost_per_1m": _number_or_none(row["output_cost_per_1m"]),
        "capability_tags": list(row["capability_tags"] or []),
        "status": row["status"],
        "notes": row["notes"],
        "created_at": str(row["created_at"]) if row["created_at"] else None,
        "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
    }


def _agent_profile_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "runtime_kind": row["runtime_kind"],
        "default_llm_model_id": str(row["default_llm_model_id"]) if row["default_llm_model_id"] else None,
        "system_prompt": row["system_prompt"],
        "tool_names": list(row["tool_names"] or []),
        "memory_policy": _json_value(row["memory_policy"], {}),
        "safety_policy": _json_value(row["safety_policy"], {}),
        "status": row["status"],
        "created_at": str(row["created_at"]) if row["created_at"] else None,
        "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
    }


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value
