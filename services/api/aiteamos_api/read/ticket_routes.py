"""Local ticket routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .ticket_service import (
    EmployeeWorkLedger,
    Ticket,
    TicketAssetRecord,
    TicketBackendSettings,
    TicketBackendSettingsUpdateRequest,
    TicketBackendStatus,
    TicketCreateRequest,
    TicketEvent,
    TicketReportRequest,
    add_ticket_report,
    create_ticket,
    employee_work_ledger,
    get_ticket,
    get_ticket_events,
    list_tickets,
    ticket_asset_records,
    ticket_backend_settings,
    ticket_backend_status,
    update_ticket_backend_settings,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


@router.get("", response_model=list[Ticket])
async def get_tickets(status: str | None = None) -> list[Ticket]:
    try:
        return list_tickets(status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=Ticket)
async def post_ticket(request: TicketCreateRequest) -> Ticket:
    try:
        return create_ticket(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/backend", response_model=TicketBackendSettings)
async def get_ticket_backend() -> TicketBackendSettings:
    return ticket_backend_settings()


@router.put("/backend", response_model=TicketBackendSettings)
async def put_ticket_backend(request: TicketBackendSettingsUpdateRequest) -> TicketBackendSettings:
    try:
        return update_ticket_backend_settings(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status", response_model=TicketBackendStatus)
async def get_ticket_backend_status() -> TicketBackendStatus:
    return ticket_backend_status()


@router.get("/assets", response_model=list[TicketAssetRecord])
async def get_ticket_assets() -> list[TicketAssetRecord]:
    try:
        return ticket_asset_records()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/employees/{employee_id}/work", response_model=EmployeeWorkLedger)
async def get_employee_work_ledger(employee_id: str) -> EmployeeWorkLedger:
    try:
        return employee_work_ledger(employee_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{ticket_id}/events", response_model=list[TicketEvent])
async def get_ticket_event_log(ticket_id: str) -> list[TicketEvent]:
    try:
        events = get_ticket_events(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not events:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return events


@router.get("/{ticket_id}", response_model=Ticket)
async def get_ticket_detail(ticket_id: str) -> Ticket:
    try:
        item = get_ticket(ticket_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return item


@router.post("/{ticket_id}/reports", response_model=Ticket)
async def post_ticket_report(ticket_id: str, request: TicketReportRequest) -> Ticket:
    try:
        return add_ticket_report(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
