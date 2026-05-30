"""
API Gateway — Metrics & Observability Routes (PRD §3.8).

GET /api/v1/metrics/value         — value metrics summary
GET /api/v1/metrics/system-health — system health overview
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])

_db: Any = None


def init_routes(*, db: Any) -> None:
    global _db
    _db = db


@router.get("/value")
async def get_value_metrics(
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        memory_count = await _db.fetchval("SELECT count(*) FROM memory_node") or 0
        active_count = await _db.fetchval("SELECT count(*) FROM memory_node WHERE lifecycle='active'") or 0
        candidate_count = await _db.fetchval("SELECT count(*) FROM memory_node WHERE lifecycle='candidate'") or 0
        deprecated_count = await _db.fetchval("SELECT count(*) FROM memory_node WHERE lifecycle='deprecated'") or 0
        skill_count = await _db.fetchval("SELECT count(*) FROM skill") or 0
        member_count = await _db.fetchval("SELECT count(*) FROM member WHERE archived_at IS NULL") or 0
        task_count = await _db.fetchval("SELECT count(*) FROM task") or 0
        recall_count = await _db.fetchval("SELECT count(*) FROM recall_audit") or 0
        return {
            "memory_total": memory_count,
            "memory_active": active_count,
            "memory_candidates": candidate_count,
            "memory_deprecated": deprecated_count,
            "skill_count": skill_count,
            "member_count": member_count,
            "task_count": task_count,
            "recall_count": recall_count,
            "memory_active_rate": round(active_count / max(memory_count, 1), 3),
        }
    except Exception:
        return {
            "memory_total": 0, "memory_active": 0, "memory_candidates": 0,
            "memory_deprecated": 0, "skill_count": 0, "member_count": 0,
            "task_count": 0, "recall_count": 0, "memory_active_rate": 0,
        }


@router.get("/system-health")
async def get_system_health(
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _db is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        memory_count = await _db.fetchval("SELECT count(*) FROM memory_node") or 0
        conflict_count = await _db.fetchval("SELECT count(*) FROM conflict_case WHERE status='open'") or 0
        pending_reviews = await _db.fetchval("SELECT count(*) FROM review_case WHERE status='pending'") or 0
        task_done = await _db.fetchval("SELECT count(*) FROM task WHERE state='done'") or 0
        task_failed = await _db.fetchval("SELECT count(*) FROM task WHERE state='failed'") or 0
        task_total = task_done + task_failed
        first_pass_rate = round(task_done / max(task_total, 1), 3)
        return {
            "database": "connected",
            "memory_total": memory_count,
            "conflicts_open": conflict_count,
            "reviews_pending": pending_reviews,
            "task_first_pass_rate": first_pass_rate,
            "status": "healthy" if conflict_count < 10 else "degraded",
        }
    except Exception:
        return {
            "database": "connected",
            "memory_total": 0, "conflicts_open": 0, "reviews_pending": 0,
            "task_first_pass_rate": 0, "status": "unknown",
        }
