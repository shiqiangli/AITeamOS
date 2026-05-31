"""
API Gateway - Runtime Resource Read Routes.

Neutral LLM models and agent profiles that can be selected by tasks.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1", tags=["runtime-read"])

_db: Any = None


def init_routes(*, db: Any) -> None:
    global _db
    _db = db


@router.get("/llm-models", response_model=list[dict[str, Any]])
async def list_llm_models(
    status: Optional[str] = Query(None),
    name_filter: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    rows = await _db.fetch(
        """
        SELECT *
        FROM llm_model
        WHERE ($1::text IS NULL OR status = $1)
          AND ($2::text IS NULL OR name ILIKE '%' || $2 || '%')
        ORDER BY created_at DESC
        OFFSET $3 LIMIT $4
        """,
        status,
        name_filter,
        offset,
        limit,
    )
    return [_llm_model_to_dict(row) for row in rows]


@router.get("/llm-models/{model_id}", response_model=dict[str, Any])
async def get_llm_model(
    model_id: str,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    row = await _db.fetchrow("SELECT * FROM llm_model WHERE id = $1", model_id)
    if row is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"LLM model {model_id} not found")
    return _llm_model_to_dict(row)


@router.get("/agent-profiles", response_model=list[dict[str, Any]])
async def list_agent_profiles(
    status: Optional[str] = Query(None),
    name_filter: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    rows = await _db.fetch(
        """
        SELECT *
        FROM agent_profile
        WHERE ($1::text IS NULL OR status = $1)
          AND ($2::text IS NULL OR name ILIKE '%' || $2 || '%')
        ORDER BY created_at DESC
        OFFSET $3 LIMIT $4
        """,
        status,
        name_filter,
        offset,
        limit,
    )
    return [_agent_profile_to_dict(row) for row in rows]


@router.get("/agent-profiles/{profile_id}", response_model=dict[str, Any])
async def get_agent_profile(
    profile_id: str,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    row = await _db.fetchrow("SELECT * FROM agent_profile WHERE id = $1", profile_id)
    if row is None:
        from ..middleware.error_handler import NotFoundError
        raise NotFoundError(detail=f"Agent profile {profile_id} not found")
    return _agent_profile_to_dict(row)


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
        "created_at": _datetime_or_none(row["created_at"]),
        "updated_at": _datetime_or_none(row["updated_at"]),
    }


def _agent_profile_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "runtime_kind": row["runtime_kind"],
        "default_llm_model_id": _uuid_or_none(row["default_llm_model_id"]),
        "system_prompt": row["system_prompt"],
        "tool_names": list(row["tool_names"] or []),
        "memory_policy": _json_value(row["memory_policy"], {}),
        "safety_policy": _json_value(row["safety_policy"], {}),
        "status": row["status"],
        "created_at": _datetime_or_none(row["created_at"]),
        "updated_at": _datetime_or_none(row["updated_at"]),
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


def _uuid_or_none(value: Any) -> str | None:
    return str(value) if value else None


def _datetime_or_none(value: Any) -> str | None:
    return str(value) if value else None
