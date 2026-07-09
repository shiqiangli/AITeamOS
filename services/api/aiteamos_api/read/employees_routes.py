"""Employee graph routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .employee_growth_eval_service import EmployeeGrowthEvalResponse, employee_growth_eval_report
from .employee_improvement_service import (
    EmployeeImprovementApplyRequest,
    EmployeeImprovementApplyResponse,
    apply_employee_improvement_asset,
)
from .ticket_service import (
    EmployeeAnalytics,
    EmployeeAnalyticsSummary,
    EmployeeGraphProjection,
    EmployeeImprovementCandidateRequest,
    EmployeeImprovementCandidateResponse,
    employee_analytics,
    employee_analytics_summary,
    employee_graph_projection,
    propose_employee_quality_improvement_candidate,
)

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


@router.get("/analytics/summary", response_model=EmployeeAnalyticsSummary)
async def get_employee_analytics_summary() -> EmployeeAnalyticsSummary:
    try:
        return employee_analytics_summary()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{employee_id}/analytics", response_model=EmployeeAnalytics)
async def get_employee_analytics(employee_id: str) -> EmployeeAnalytics:
    try:
        analytics = employee_analytics(employee_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if analytics is None:
        raise HTTPException(status_code=404, detail=f"Employee analytics not found: {employee_id}")
    return analytics


@router.get("/{employee_id}/graph", response_model=EmployeeGraphProjection)
async def get_employee_graph(employee_id: str) -> EmployeeGraphProjection:
    try:
        projection = employee_graph_projection(employee_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if projection is None:
        raise HTTPException(status_code=404, detail=f"Employee graph not found: {employee_id}")
    return projection


@router.get("/{employee_id}/growth-eval", response_model=EmployeeGrowthEvalResponse)
async def get_employee_growth_eval(employee_id: str) -> EmployeeGrowthEvalResponse:
    try:
        response = employee_growth_eval_report(employee_id=employee_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if response.summary.employee_id.strip().lower() != employee_id.strip().lower():
        raise HTTPException(status_code=404, detail=f"Employee growth evidence not found: {employee_id}")
    return response


@router.post(
    "/{employee_id}/quality-feedback/{feedback_id}/improvement-candidate",
    response_model=EmployeeImprovementCandidateResponse,
)
async def post_employee_quality_feedback_improvement_candidate(
    employee_id: str,
    feedback_id: str,
    request: EmployeeImprovementCandidateRequest,
) -> EmployeeImprovementCandidateResponse:
    try:
        return propose_employee_quality_improvement_candidate(employee_id, feedback_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Employee quality feedback not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{employee_id}/improvement-assets/{asset_id}/apply",
    response_model=EmployeeImprovementApplyResponse,
)
async def post_employee_improvement_asset_apply(
    employee_id: str,
    asset_id: str,
    request: EmployeeImprovementApplyRequest,
) -> EmployeeImprovementApplyResponse:
    try:
        return apply_employee_improvement_asset(employee_id, asset_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Employee improvement target not found: {exc.args[0]}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
