"""Employee graph routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .ticket_service import (
    EmployeeAnalytics,
    EmployeeAnalyticsSummary,
    EmployeeGraphProjection,
    employee_analytics,
    employee_analytics_summary,
    employee_graph_projection,
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
