"""
API Gateway - Governance Command Routes.

POST /api/v1/reviews             - create review
POST /api/v1/reviews/{id}/decide - make decision
POST /api/v1/conflicts           - report conflict
POST /api/v1/conflicts/{id}/resolve - resolve conflict

All mutations go through application services to ensure:
- Event publishing (Outbox)
- Transactional safety
- Business rule enforcement
"""
from __future__ import annotations
from typing import Any
from uuid import UUID
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from ..middleware.auth import AuthContext, get_current_user
from aiteamos_governance.domain.models import (
    ConflictKind, DetectorKind,
    ResolutionKind, ReviewTargetKind, Verdict,
)

router = APIRouter(prefix="/api/v1", tags=["governance-write"])

_review_service: Any = None
_conflict_service: Any = None


def init_routes(*, review_service: Any, conflict_service: Any) -> None:
    global _review_service, _conflict_service
    _review_service = review_service
    _conflict_service = conflict_service


class CreateReviewRequest(BaseModel):
    target_kind: str
    target_id: str
    reviewer_member_id: str


class DecideReviewRequest(BaseModel):
    verdict: str
    reason: str = ""
    correction: str = ""


class ReportConflictRequest(BaseModel):
    memory_a_id: str
    memory_b_id: str
    conflict_kind: str = "semantic"
    detected_by: str = "manual"


class ResolveConflictRequest(BaseModel):
    resolution: str
    winner_id: str | None = None
    resolved_by: str | None = None


@router.post("/reviews")
async def create_review(
    body: CreateReviewRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _review_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    case = await _review_service.create_review(
        target_kind=ReviewTargetKind(body.target_kind),
        target_id=UUID(body.target_id),
        reviewer_member_id=UUID(body.reviewer_member_id),
    )
    return {"id": str(case.id), "status": "created"}


@router.post("/reviews/{review_id}/decide")
async def decide_review(
    review_id: UUID,
    body: DecideReviewRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _review_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        case = await _review_service.decide(
            review_id,
            verdict=Verdict(body.verdict),
            reason=body.reason,
            correction=body.correction or None,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))
    return {"id": str(case.id), "status": "decided", "verdict": case.verdict.value if case.verdict else None}


@router.post("/conflicts")
async def report_conflict(
    body: ReportConflictRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _conflict_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    case = await _conflict_service.report_conflict(
        memory_a_id=UUID(body.memory_a_id),
        memory_b_id=UUID(body.memory_b_id),
        conflict_kind=ConflictKind(body.conflict_kind),
        detected_by=DetectorKind(body.detected_by),
    )
    return {"id": str(case.id), "status": "reported"}


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: UUID,
    body: ResolveConflictRequest,
    user: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    if _conflict_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    try:
        case = await _conflict_service.resolve_conflict(
            conflict_id,
            resolution=ResolutionKind(body.resolution),
            winner_id=UUID(body.winner_id) if body.winner_id else None,
            resolved_by=UUID(body.resolved_by) if body.resolved_by else UUID(int=0),
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))
    return {"id": str(case.id), "status": "resolved"}
