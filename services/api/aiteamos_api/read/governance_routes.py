"""
API Gateway - Governance Read Routes.

GET /api/v1/reviews              - list reviews
GET /api/v1/reviews/pending      - pending queue
GET /api/v1/reviews/{id}         - detail
GET /api/v1/reviews/by-target    - reviews by target
GET /api/v1/conflicts            - list conflicts
GET /api/v1/conflicts/unresolved - unresolved queue
GET /api/v1/conflicts/{id}       - detail
"""
from __future__ import annotations
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from ..middleware.auth import AuthContext, get_current_user

router = APIRouter(prefix="/api/v1", tags=["governance-read"])

_review_repo: Any = None
_conflict_repo: Any = None


def init_routes(*, review_repo: Any, conflict_repo: Any) -> None:
    global _review_repo, _conflict_repo
    _review_repo = review_repo
    _conflict_repo = conflict_repo


def _review_to_dict(case: Any) -> dict[str, Any]:
    v = case.verdict
    return {
        "id": str(case.id),
        "target_kind": case.target_kind.value if hasattr(case.target_kind, "value") else str(case.target_kind),
        "target_id": str(case.target_id),
        "reviewer_member_id": str(case.reviewer_member_id),
        "status": "pending" if v is None else "decided",
        "verdict": v.value if v and hasattr(v, "value") else v,
        "reason": case.reason,
        "correction": case.correction,
        "created_at": str(case.created_at) if case.created_at else None,
        "decision_at": str(case.decision_at) if case.decision_at else None,
    }


def _conflict_to_dict(case: Any) -> dict[str, Any]:
    r = case.resolution
    return {
        "id": str(case.id),
        "memory_a_id": str(case.memory_a_id),
        "memory_b_id": str(case.memory_b_id),
        "conflict_kind": case.conflict_kind.value if hasattr(case.conflict_kind, "value") else str(case.conflict_kind),
        "status": "open" if case.resolved_at is None else "resolved",
        "resolution": r.value if r and hasattr(r, "value") else r,
        "winner_id": str(case.winner_id) if case.winner_id else None,
        "detected_by": case.detected_by.value if hasattr(case.detected_by, "value") else str(case.detected_by),
        "resolved_by": str(case.resolved_by) if case.resolved_by else None,
        "detected_at": str(case.detected_at) if case.detected_at else None,
        "resolved_at": str(case.resolved_at) if case.resolved_at else None,
    }


@router.get("/reviews")
async def list_reviews(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _review_repo is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    cases = await _review_repo.find_pending(limit=limit, offset=offset)
    return [_review_to_dict(c) for c in cases]


@router.get("/reviews/pending")
async def list_pending_reviews(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _review_repo is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    cases = await _review_repo.find_pending(limit=limit, offset=offset)
    return [_review_to_dict(c) for c in cases]


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _review_repo is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    case = await _review_repo.get_by_id(review_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Review not found")
    return _review_to_dict(case)


@router.get("/reviews/by-target/{target_kind}/{target_id}")
async def get_reviews_by_target(
    target_kind: str,
    target_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _review_repo is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    cases = await _review_repo.find_by_target(target_kind, target_id)
    return [_review_to_dict(c) for c in cases]


@router.get("/conflicts")
async def list_conflicts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _conflict_repo is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    cases = await _conflict_repo.find_unresolved(limit=limit, offset=offset)
    return [_conflict_to_dict(c) for c in cases]


@router.get("/conflicts/unresolved")
async def list_unresolved_conflicts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    if _conflict_repo is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    cases = await _conflict_repo.find_unresolved(limit=limit, offset=offset)
    return [_conflict_to_dict(c) for c in cases]


@router.get("/conflicts/{conflict_id}")
async def get_conflict(
    conflict_id: UUID,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _conflict_repo is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    case = await _conflict_repo.get_by_id(conflict_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return _conflict_to_dict(case)
