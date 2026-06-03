"""Local ticket routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .ticket_service import (
    Ticket,
    TicketCreateRequest,
    TicketReportRequest,
    add_ticket_report,
    create_ticket,
    get_ticket,
    list_tickets,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])


@router.get("", response_model=list[Ticket])
async def get_tickets(status: str | None = None) -> list[Ticket]:
    return list_tickets(status=status)


@router.post("", response_model=Ticket)
async def post_ticket(request: TicketCreateRequest) -> Ticket:
    return create_ticket(request)


@router.get("/{ticket_id}", response_model=Ticket)
async def get_ticket_detail(ticket_id: str) -> Ticket:
    item = get_ticket(ticket_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}")
    return item


@router.post("/{ticket_id}/reports", response_model=Ticket)
async def post_ticket_report(ticket_id: str, request: TicketReportRequest) -> Ticket:
    try:
        return add_ticket_report(ticket_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Ticket not found: {ticket_id}") from exc
