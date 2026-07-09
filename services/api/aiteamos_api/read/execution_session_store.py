"""Correlation store for AITeamOS execution sessions and runtime checkpoints."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def execution_sessions_path(workspace_dir: Path) -> Path:
    return workspace_dir / "execution_sessions.json"


def execution_state_snapshots_dir(workspace_dir: Path) -> Path:
    return workspace_dir / "execution_state_snapshots"


def save_execution_state_snapshot(
    workspace_dir: Path,
    *,
    source_state_ref: str,
    checkpoint_ref: str,
    executor_session_ref: str,
    current_graph_node: str,
    request: dict[str, Any],
    result: dict[str, Any],
    approval_request: dict[str, Any],
) -> str:
    """Persist a redacted graph state snapshot for approval resume."""

    normalized_ref = source_state_ref.strip()
    if not normalized_ref:
        return ""
    path = execution_state_snapshots_dir(workspace_dir) / f"{_safe_snapshot_name(normalized_ref)}.json"
    snapshot_ref = _relative_snapshot_path(workspace_dir, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source_state_ref": normalized_ref,
        "source_state_snapshot_ref": snapshot_ref,
        "checkpoint_ref": checkpoint_ref,
        "executor_session_ref": executor_session_ref,
        "current_graph_node": current_graph_node,
        "request_id": str(request.get("request_id") or ""),
        "executor_id": str(result.get("executor_id") or ""),
        "status": str(result.get("status") or ""),
        "approval_request": approval_request,
        "graph_state": _redact(
            {
                "execution_request": request,
                "current_step": current_graph_node,
                "approval_interrupt": (
                    result.get("learning_delta", {}).get("approval_interrupt")
                    if isinstance(result.get("learning_delta"), dict)
                    else {}
                ),
                "tool_events": result.get("tool_events") if isinstance(result.get("tool_events"), list) else [],
                "errors": result.get("errors") if isinstance(result.get("errors"), list) else [],
                "learning_delta": result.get("learning_delta") if isinstance(result.get("learning_delta"), dict) else {},
            }
        ),
        "snapshot_schema": "execution_state_snapshot.v1",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot_ref


def load_execution_state_snapshot(workspace_dir: Path, source_state_ref: str) -> dict[str, Any] | None:
    normalized_ref = source_state_ref.strip()
    if not normalized_ref:
        return None
    path = execution_state_snapshots_dir(workspace_dir) / f"{_safe_snapshot_name(normalized_ref)}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def save_execution_session(
    workspace_dir: Path,
    *,
    employee_id: str,
    thread_id: str,
    ticket_id: str,
    executor_id: str,
    executor_session_ref: str,
    checkpoint_ref: str,
    last_request_id: str,
    updated_at: str,
    status: str = "",
    trace_ref: str = "",
    current_graph_node: str = "",
    source_state_ref: str = "",
    tool_event_count: int = 0,
    tool_events: list[dict[str, Any]] | None = None,
    ticket_refs: list[str] | None = None,
    memory_refs: list[str] | None = None,
    context_refs: list[dict[str, Any]] | None = None,
    approval_refs: list[str] | None = None,
) -> None:
    path = execution_sessions_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    key = f"{employee_id}::{thread_id}::{ticket_id or 'none'}"
    existing = payload.get(key) if isinstance(payload.get(key), dict) else {}
    record = {
        "session_key": key,
        "employee_id": employee_id,
        "thread_id": thread_id,
        "ticket_id": ticket_id,
        "executor_id": executor_id,
        "executor_session_ref": executor_session_ref,
        "checkpoint_ref": checkpoint_ref,
        "last_request_id": last_request_id,
        "status": status,
        "trace_ref": trace_ref,
        "current_graph_node": current_graph_node,
        "source_state_ref": source_state_ref,
        "tool_event_count": tool_event_count,
        "tool_events": tool_events or [],
        "ticket_refs": sorted({item for item in ticket_refs or [] if item}),
        "memory_refs": sorted({item for item in memory_refs or [] if item}),
        "context_refs": context_refs or [],
        "approval_refs": sorted({item for item in approval_refs or [] if item}),
        "updated_at": updated_at,
    }
    if isinstance(existing, dict):
        if "control_events" in existing:
            record["control_events"] = existing["control_events"]
        if "control_state" in existing:
            record["control_state"] = existing["control_state"]
    payload[key] = record
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_execution_sessions(workspace_dir: Path) -> dict[str, dict[str, Any]]:
    path = execution_sessions_path(workspace_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): value for key, value in payload.items() if isinstance(value, dict)} if isinstance(payload, dict) else {}


def record_execution_session_control(
    workspace_dir: Path,
    *,
    ticket_id: str,
    action: str,
    actor_employee_id: str,
    reason: str,
    updated_at: str,
    session_key: str = "",
) -> list[dict[str, Any]]:
    path = execution_sessions_path(workspace_dir)
    payload = load_execution_sessions(workspace_dir)
    normalized_ticket_id = ticket_id.strip()
    normalized_session_key = session_key.strip()
    normalized_action = action.strip().lower()
    if not payload or not normalized_ticket_id:
        return []
    status_by_action = {
        "stop": "stopped",
        "pause": "paused",
        "cancel": "cancelled",
        "continue": "ready_to_continue",
    }
    control_event = {
        "action": normalized_action,
        "actor_employee_id": actor_employee_id.strip(),
        "reason": reason.strip(),
        "updated_at": updated_at,
    }
    updated: list[dict[str, Any]] = []
    for key, session in payload.items():
        if normalized_session_key and key != normalized_session_key:
            continue
        if str(session.get("ticket_id") or "").strip() != normalized_ticket_id:
            continue
        events = session.get("control_events") if isinstance(session.get("control_events"), list) else []
        session["control_events"] = [*events, control_event]
        session["control_state"] = control_event
        session["status"] = status_by_action.get(normalized_action, normalized_action or str(session.get("status") or ""))
        session["updated_at"] = updated_at
        updated.append(session)
    if updated:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return updated


def _safe_snapshot_name(value: str) -> str:
    normalized = value.strip().replace("://", "-")
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", normalized)
    return normalized.strip("-")[:180] or "state"


def _relative_snapshot_path(workspace_dir: Path, path: Path) -> str:
    try:
        return str(path.relative_to(workspace_dir))
    except ValueError:
        return str(path)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("api_key", "authorization", "token", "secret", "password")):
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
