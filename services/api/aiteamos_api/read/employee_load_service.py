"""Runtime Employee load projection for Chat and LangGraph context."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .execution_session_store import load_execution_sessions
from .ticket_service import Ticket, list_tickets

_TERMINAL_TICKET_STATUSES = {"validated", "completed", "done", "closed", "cancelled", "canceled"}
_INACTIVE_SESSION_STATUSES = {"completed", "done", "failed", "cancelled", "canceled", "aborted"}
_ATTENTION_SESSION_STATUSES = {"needs_approval", "waiting_approval", "approval_required", "blocked"}


def employee_current_load(
    employee_id: str,
    *,
    base_load: dict[str, Any] | None = None,
    workspace_dir: Path | None = None,
) -> dict[str, Any]:
    normalized_id = _normalize_employee_id(employee_id)
    return employee_current_loads(
        [normalized_id],
        base_loads={normalized_id: base_load or {}},
        workspace_dir=workspace_dir,
    ).get(normalized_id, _normalize_base_load(base_load))


def employee_current_loads(
    employee_ids: list[str],
    *,
    base_loads: dict[str, dict[str, Any]] | None = None,
    workspace_dir: Path | None = None,
) -> dict[str, dict[str, Any]]:
    normalized_ids = [_normalize_employee_id(employee_id) for employee_id in employee_ids if _normalize_employee_id(employee_id)]
    tickets_loaded, tickets, ticket_error = _safe_list_tickets()
    sessions_loaded, sessions, session_error = _safe_load_sessions(workspace_dir or _workspace_dir())
    return {
        employee_id: _project_employee_load(
            employee_id,
            base_load=(base_loads or {}).get(employee_id) or {},
            tickets=tickets,
            tickets_loaded=tickets_loaded,
            ticket_error=ticket_error,
            sessions=sessions,
            sessions_loaded=sessions_loaded,
            session_error=session_error,
        )
        for employee_id in normalized_ids
    }


def _project_employee_load(
    employee_id: str,
    *,
    base_load: dict[str, Any],
    tickets: list[Ticket],
    tickets_loaded: bool,
    ticket_error: str,
    sessions: dict[str, dict[str, Any]],
    sessions_loaded: bool,
    session_error: str,
) -> dict[str, Any]:
    result = _normalize_base_load(base_load)
    blockers: list[dict[str, str]] = []

    if tickets_loaded:
        active_tickets = _active_tickets_for_employee(employee_id, tickets)
        assigned_tickets = [ticket for ticket in active_tickets if _normalize_employee_id(ticket.assigned_employee_id) == employee_id]
        validation_tickets = [ticket for ticket in active_tickets if _normalize_employee_id(ticket.validation_employee_id) == employee_id]
        blocked_tickets = [ticket for ticket in active_tickets if ticket.status.strip().lower() in {"blocked", "failed"}]
        result.update(
            {
                "active_ticket_count": len(active_tickets),
                "assigned_ticket_count": len(assigned_tickets),
                "validation_ticket_count": len(validation_tickets),
                "blocked_ticket_count": len(blocked_tickets),
                "active_ticket_ids": [ticket.id for ticket in active_tickets[:8]],
                "assigned_ticket_ids": [ticket.id for ticket in assigned_tickets[:8]],
                "validation_ticket_ids": [ticket.id for ticket in validation_tickets[:8]],
                "blocked_ticket_ids": [ticket.id for ticket in blocked_tickets[:8]],
                "ticket_source": "ticket_service",
            }
        )
    elif ticket_error:
        blockers.append({"kind": "ticket", "reason": "ticket_load_unavailable", "detail": ticket_error})

    if sessions_loaded:
        active_sessions = _active_sessions_for_employee(employee_id, sessions)
        needs_approval = [
            session
            for session in active_sessions
            if str(session.get("status") or "").strip().lower() in _ATTENTION_SESSION_STATUSES
        ]
        result.update(
            {
                "active_run_count": len(active_sessions),
                "needs_approval_run_count": len(needs_approval),
                "active_run_ids": [_session_ref(session) for session in active_sessions[:8] if _session_ref(session)],
                "needs_approval_run_ids": [_session_ref(session) for session in needs_approval[:8] if _session_ref(session)],
                "runtime_source": "execution_session_store",
            }
        )
    elif session_error:
        blockers.append({"kind": "runtime_session", "reason": "runtime_session_load_unavailable", "detail": session_error})

    if blockers:
        result["load_blockers"] = blockers
    result["status"] = _status_for_load(result)
    result["updated_at"] = datetime.now(UTC).isoformat()
    result["source"] = "employee_load_service"
    return result


def _normalize_base_load(base_load: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(base_load or {})
    base["active_ticket_count"] = _safe_int(base.get("active_ticket_count"))
    base["status"] = str(base.get("status") or "available")
    base.setdefault("assigned_ticket_count", _safe_int(base.get("assigned_ticket_count")))
    base.setdefault("validation_ticket_count", _safe_int(base.get("validation_ticket_count")))
    base.setdefault("blocked_ticket_count", _safe_int(base.get("blocked_ticket_count")))
    base.setdefault("active_run_count", _safe_int(base.get("active_run_count")))
    base.setdefault("needs_approval_run_count", _safe_int(base.get("needs_approval_run_count")))
    return base


def _active_tickets_for_employee(employee_id: str, tickets: list[Ticket]) -> list[Ticket]:
    matched = [
        ticket
        for ticket in tickets
        if not _is_terminal_ticket(ticket.status)
        and (
            _normalize_employee_id(ticket.assigned_employee_id) == employee_id
            or _normalize_employee_id(ticket.validation_employee_id) == employee_id
        )
    ]
    return sorted(matched, key=lambda ticket: ticket.updated_at, reverse=True)


def _active_sessions_for_employee(employee_id: str, sessions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    matched = [
        session
        for session in sessions.values()
        if _normalize_employee_id(str(session.get("employee_id") or "")) == employee_id
        and _is_active_session(session)
    ]
    return sorted(matched, key=lambda session: str(session.get("updated_at") or ""), reverse=True)


def _safe_list_tickets() -> tuple[bool, list[Ticket], str]:
    try:
        return True, list_tickets(), ""
    except Exception as exc:
        return False, [], str(exc)


def _safe_load_sessions(workspace_dir: Path) -> tuple[bool, dict[str, dict[str, Any]], str]:
    try:
        return True, load_execution_sessions(workspace_dir), ""
    except Exception as exc:
        return False, {}, str(exc)


def _workspace_dir() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve() / ".aiteamos"
    return Path(__file__).resolve().parents[4] / ".aiteamos"


def _is_terminal_ticket(status: str) -> bool:
    return status.strip().lower() in _TERMINAL_TICKET_STATUSES


def _is_active_session(session: dict[str, Any]) -> bool:
    status = str(session.get("status") or "").strip().lower()
    return bool(status) and status not in _INACTIVE_SESSION_STATUSES


def _session_ref(session: dict[str, Any]) -> str:
    return str(
        session.get("last_request_id")
        or session.get("executor_session_ref")
        or session.get("session_key")
        or ""
    ).strip()


def _status_for_load(load: dict[str, Any]) -> str:
    if _safe_int(load.get("blocked_ticket_count")) > 0 or _safe_int(load.get("needs_approval_run_count")) > 0:
        return "needs_attention"
    if _safe_int(load.get("active_run_count")) > 0:
        return "running"
    active_ticket_count = _safe_int(load.get("active_ticket_count"))
    if active_ticket_count > 1:
        return "busy"
    if active_ticket_count == 1:
        return "active"
    return "available"


def _normalize_employee_id(value: str) -> str:
    return value.strip().lower()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
