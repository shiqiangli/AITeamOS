"""
API Gateway — Job Write Routes.

POST   /api/v1/jobs              — 创建 Job (Start Task execution)
GET    /api/v1/jobs              — 列表 (支持 task_id 筛选)
GET    /api/v1/jobs/{job_id}     — 详情 (Pre + Middle + Post)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..middleware.auth import AuthContext, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/jobs", tags=["job"])

_db: Any = None


def init_routes(*, db: Any) -> None:
    global _db
    _db = db


# --- Request Bodies ---


class CreateJobRequest(BaseModel):
    task_id: str
    member_id: Optional[str] = None
    llm_model_id: Optional[str] = None


# --- Helpers ---


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert asyncpg Record to dict."""
    d = dict(row)
    for key in ("job_id", "member_id", "llm_model_id"):
        if d.get(key):
            d[key] = str(d[key])
    for key in ("context_snapshot", "result_report", "cost"):
        if d.get(key) is not None and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    if d.get("started_at"):
        d["started_at"] = str(d["started_at"])
    if d.get("finished_at"):
        d["finished_at"] = str(d["finished_at"])
    if d.get("phase_entered_at"):
        d["phase_entered_at"] = str(d["phase_entered_at"])
    if d.get("created_at"):
        d["created_at"] = str(d["created_at"])
    return d


# --- Endpoints ---


@router.post("", status_code=201, response_model=dict[str, Any])
async def create_job(
    body: CreateJobRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """创建一个 Job — Task 的一次执行尝试。"""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    member_uuid = UUID(body.member_id) if body.member_id else None
    llm_uuid = UUID(body.llm_model_id) if body.llm_model_id else None

    row = await _db.fetchrow(
        """
        INSERT INTO job (task_id, member_id, llm_model_id, phase, state)
        VALUES ($1, $2, $3, 'queued', 'pending')
        RETURNING job_id, task_id, member_id, llm_model_id, phase, state,
                  started_at, created_at
        """,
        body.task_id,
        member_uuid,
        llm_uuid,
    )
    if row is None:
        raise HTTPException(status_code=400, detail="Failed to create job")

    return _row_to_dict(row)


@router.get("", response_model=list[dict[str, Any]])
async def list_jobs(
    task_id: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """列出 Jobs (支持 task_id / state 筛选)。"""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    conditions = []
    params: list[Any] = []
    idx = 1

    if task_id:
        conditions.append(f"task_id = ${idx}")
        params.append(task_id)
        idx += 1
    if state:
        conditions.append(f"state = ${idx}")
        params.append(state)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"""
        SELECT job_id, task_id, member_id, llm_model_id, phase, state,
               error, started_at, finished_at, created_at
        FROM job {where}
        ORDER BY started_at DESC
        OFFSET ${idx} LIMIT ${idx + 1}
    """
    params.extend([offset, limit])
    rows = await _db.fetch(sql, *params)
    return [_row_to_dict(r) for r in rows]


@router.get("/{job_id}", response_model=dict[str, Any])
async def get_job_detail(
    job_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """获取 Job 详情 (Pre + Middle + Post)。"""
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    row = await _db.fetchrow(
        """
        SELECT job_id, task_id, member_id, llm_model_id,
               rendered_prompt, context_snapshot,
               phase, phase_entered_at, error,
               result_report, cost,
               state, started_at, finished_at, created_at
        FROM job WHERE job_id = $1
        """,
        job_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return _row_to_dict(row)
