"""Ticket service with a local append-only event-log backend."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

CLARA_SYSTEM_EMPLOYEE_ID = "clara"
CLARA_SYSTEM_ROLE = "AI Team OS Manager"
LOCAL_TICKET_ID_RE = re.compile(r"^(?:ticket-[A-Za-z0-9_.:-]+|(?:rd|pv|arch|rel|mem|doc|ops|trace)-\d{4,})$", re.IGNORECASE)
_SAFE_NAMESPACE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,24}$")

_ROLE_NAMESPACE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rd", ("rd", "implementer", "developer", "engineer", "研发", "开发")),
    ("pv", ("pv", "qa", "verification", "validation", "harness", "验证", "测试")),
    ("arch", ("architect", "architecture", "架构")),
    ("rel", ("release", "发布")),
    ("mem", ("memory curator", "memory", "记忆")),
    ("doc", ("docs", "documentation", "knowledge", "writer", "文档", "知识")),
    ("trace", ("trace reporter", "trace", "reporter", "观测")),
)
_MANAGER_ROLES = {CLARA_SYSTEM_ROLE.lower(), "manager", "system manager", "ai team os manager"}
_KNOWN_NAMESPACES = {"rd", "pv", "arch", "rel", "mem", "doc", "ops", "trace"}


class TicketEvent(BaseModel):
    event_id: str
    ticket_id: str
    type: str
    at: str
    actor: dict[str, str] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class TicketReport(BaseModel):
    id: str
    reporter_employee_id: str
    reporter_role: str = ""
    content: str
    evidence: list[str] = Field(default_factory=list)
    report_type: str = "progress"
    created_at: str
    source_event_id: str = ""


class Ticket(BaseModel):
    id: str
    title: str
    description: str
    status: str = "assigned"
    ticket_type: str = "ops"
    assigned_employee_id: str = ""
    assigned_role: str = ""
    validation_employee_id: str = ""
    validation_role: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    code_repository_ids: list[str] = Field(default_factory=list)
    source_thread_id: str = ""
    source_run_id: str = ""
    reports: list[TicketReport] = Field(default_factory=list)
    events: list[TicketEvent] = Field(default_factory=list)
    created_at: str
    updated_at: str
    saved_path: str = ""


class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    ticket_type: str = ""
    assigned_employee_id: str = ""
    assigned_role: str = ""
    validation_employee_id: str = ""
    validation_role: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    code_repository_ids: list[str] = Field(default_factory=list)
    source_thread_id: str = ""
    source_run_id: str = ""
    actor_employee_id: str = CLARA_SYSTEM_EMPLOYEE_ID
    actor_role: str = ""


class TicketReportRequest(BaseModel):
    reporter_employee_id: str
    reporter_role: str = ""
    content: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    report_type: str = "progress"
    source_run_id: str = ""


class TicketBackendMode(BaseModel):
    id: str
    label: str
    status: str
    description: str


class TicketBackendSettings(BaseModel):
    mode: str = "local_file"
    local_file_path: str = ".aiteamos/tickets/index.json"
    saved_paths: dict[str, str] = Field(default_factory=dict)
    supported_modes: list[TicketBackendMode] = Field(default_factory=list)


class TicketBackendSettingsUpdateRequest(BaseModel):
    mode: str = "local_file"
    local_file_path: str = ".aiteamos/tickets/index.json"


class TicketBackendStatus(BaseModel):
    mode: str
    status: str
    detail: str
    ticket_count: int = 0
    local_file_path: str = ""
    saved_paths: dict[str, str] = Field(default_factory=dict)
    supported_modes: list[TicketBackendMode] = Field(default_factory=list)


class TicketWorkItem(BaseModel):
    ticket_id: str
    title: str
    status: str
    role: str
    updated_at: str
    next_action: str = ""


class EmployeeTicketReportRecord(BaseModel):
    ticket_id: str
    ticket_title: str
    report_id: str
    report_type: str
    content: str
    evidence: list[str] = Field(default_factory=list)
    created_at: str


class EmployeeWorkLedger(BaseModel):
    employee_id: str
    current_tickets: list[TicketWorkItem] = Field(default_factory=list)
    historical_tickets: list[TicketWorkItem] = Field(default_factory=list)
    reports: list[EmployeeTicketReportRecord] = Field(default_factory=list)
    validations: list[EmployeeTicketReportRecord] = Field(default_factory=list)
    blocked_records: list[EmployeeTicketReportRecord] = Field(default_factory=list)
    handoffs: list[dict[str, Any]] = Field(default_factory=list)
    contribution: dict[str, int] = Field(default_factory=dict)


class TicketAssetRecord(BaseModel):
    id: str
    kind: str
    title: str
    status: str = "active"
    source_ticket_id: str = ""
    source_employee_id: str = ""
    assigned_employees: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    return Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", Path.cwd())).resolve()


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _tickets_dir() -> Path:
    path = _workspace_dir() / "tickets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _employees_dir() -> Path:
    return _workspace_dir() / "employees"


def _backend_settings_path() -> Path:
    return _tickets_dir() / "backend.json"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


SUPPORTED_BACKENDS = [
    TicketBackendMode(
        id="local_file",
        label="Local file",
        status="ready",
        description="Append-only per-Ticket files for fast local dogfooding and repository-tracked self-improvement.",
    ),
    TicketBackendMode(
        id="plane",
        label="Plane",
        status="planned",
        description="Future Plane-backed source of truth through the Plane connector.",
    ),
    TicketBackendMode(
        id="jira",
        label="Jira",
        status="planned",
        description="Future Jira-backed source of truth if AITeamOS needs enterprise compatibility.",
    ),
]


def _default_backend_settings() -> TicketBackendSettings:
    return TicketBackendSettings(
        saved_paths={"settings": _relative(_backend_settings_path()), "local_file": ".aiteamos/tickets/index.json"},
        supported_modes=SUPPORTED_BACKENDS,
    )


def _write_backend_settings(settings: TicketBackendSettings) -> TicketBackendSettings:
    path = _backend_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mode": settings.mode,
                "local_file_path": settings.local_file_path,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    settings.saved_paths = {
        "settings": _relative(path),
        "local_file": settings.local_file_path,
    }
    settings.supported_modes = SUPPORTED_BACKENDS
    return settings


def ticket_backend_settings() -> TicketBackendSettings:
    path = _backend_settings_path()
    defaults = _default_backend_settings()
    if not path.exists():
        return defaults
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        settings = TicketBackendSettings.model_validate({**defaults.model_dump(), **payload})
    except (OSError, json.JSONDecodeError, ValueError):
        settings = defaults
    settings.supported_modes = SUPPORTED_BACKENDS
    settings.saved_paths = {
        "settings": _relative(path),
        "local_file": settings.local_file_path,
    }
    return settings


def update_ticket_backend_settings(request: TicketBackendSettingsUpdateRequest) -> TicketBackendSettings:
    supported = {entry.id for entry in SUPPORTED_BACKENDS}
    mode = request.mode.strip() or "local_file"
    if mode not in supported:
        raise ValueError(f"Unsupported Ticket backend: {mode}")
    local_file_path = request.local_file_path.strip() or ".aiteamos/tickets/index.json"
    settings = TicketBackendSettings(mode=mode, local_file_path=local_file_path)
    return _write_backend_settings(settings)


def _resolve_local_file_path(settings: TicketBackendSettings) -> Path:
    configured = Path(settings.local_file_path)
    if configured.is_absolute():
        return configured.resolve()
    return (_workspace_root() / configured).resolve()


def _normalize_namespace(value: str | None) -> str:
    namespace = (value or "").strip().lower()
    aliases = {
        "release": "rel",
        "memory": "mem",
        "docs": "doc",
        "knowledge": "doc",
        "report": "trace",
    }
    namespace = aliases.get(namespace, namespace)
    if not namespace:
        return ""
    if namespace not in _KNOWN_NAMESPACES or not _SAFE_NAMESPACE_RE.fullmatch(namespace):
        raise ValueError(f"Unsupported Ticket type: {value}")
    return namespace


def _namespace_for_role(role: str) -> str:
    normalized = role.strip().lower()
    for namespace, tokens in _ROLE_NAMESPACE_RULES:
        if any(token in normalized for token in tokens):
            return namespace
    return "ops" if any(token in normalized for token in _MANAGER_ROLES) else ""


def _role_can_manage_all(role: str) -> bool:
    normalized = role.strip().lower()
    return any(token in normalized for token in _MANAGER_ROLES)


def _employee_role(employee_id: str) -> str:
    normalized = employee_id.strip().lower()
    if not normalized:
        return ""
    if normalized == CLARA_SYSTEM_EMPLOYEE_ID:
        return CLARA_SYSTEM_ROLE
    path = _employees_dir() / f"{normalized}.yaml"
    if not path.exists():
        return ""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("role") or "")


def _resolve_actor_role(actor_employee_id: str, actor_role: str) -> str:
    explicit = actor_role.strip()
    if explicit:
        return explicit
    return _employee_role(actor_employee_id) or (CLARA_SYSTEM_ROLE if actor_employee_id.strip().lower() == CLARA_SYSTEM_EMPLOYEE_ID else "")


def _infer_ticket_namespace(request: TicketCreateRequest, actor_role: str) -> str:
    requested = _normalize_namespace(request.ticket_type)
    if requested:
        return requested
    assigned_namespace = _namespace_for_role(request.assigned_role)
    if assigned_namespace:
        return assigned_namespace
    actor_namespace = _namespace_for_role(actor_role)
    if actor_namespace:
        return actor_namespace
    return "ops"


def _ensure_namespace_authority(namespace: str, *, actor_employee_id: str, actor_role: str) -> None:
    if _role_can_manage_all(actor_role):
        return
    allowed_namespace = _namespace_for_role(actor_role)
    if allowed_namespace == namespace:
        return
    actor_label = actor_employee_id or "unknown actor"
    role_label = actor_role or "unknown role"
    raise ValueError(f"{actor_label} ({role_label}) cannot create {namespace} Tickets.")


def _terminal_status(status: str) -> bool:
    return status.lower() in {"validated", "completed", "done", "closed", "cancelled"}


def _next_action(ticket: Ticket) -> str:
    normalized = ticket.status.lower()
    if normalized in {"validated", "completed", "done", "closed"}:
        return "Ready for Clara summary"
    if normalized in {"blocked", "failed"}:
        return "Needs Clara or human unblock"
    if normalized in {"reported", "review", "pending_validation", "validation", "waiting_validation"}:
        return f"PV review by {ticket.validation_employee_id or ticket.validation_role or 'PV'}"
    return f"{ticket.assigned_employee_id or ticket.assigned_role or 'Assignee'} investigates and reports"


def _event(ticket_id: str, event_type: str, *, actor_id: str, actor_role: str, data: dict[str, Any], at: str | None = None) -> TicketEvent:
    return TicketEvent(
        event_id=f"evt-{uuid4().hex[:12]}",
        ticket_id=ticket_id,
        type=event_type,
        at=at or _now(),
        actor={"kind": "employee" if actor_id else "system", "id": actor_id, "role": actor_role},
        data=data,
    )


class TicketAdapter(Protocol):
    def list_tickets(self, status: str | None = None) -> list[Ticket]: ...

    def create_ticket(self, request: TicketCreateRequest) -> Ticket: ...

    def get_ticket(self, ticket_id: str) -> Ticket | None: ...

    def get_ticket_events(self, ticket_id: str) -> list[TicketEvent]: ...

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket: ...

    def employee_work_ledger(self, employee_id: str) -> EmployeeWorkLedger: ...

    def ticket_asset_records(self) -> list[TicketAssetRecord]: ...

    def status(self) -> TicketBackendStatus: ...


class LocalFileTicketAdapter:
    def __init__(self, settings: TicketBackendSettings):
        self.settings = settings
        self.index_path = _resolve_local_file_path(settings)
        self.root = self.index_path.parent
        self.counters_path = self.root / "counters.json"

    def _event_files(self) -> list[Path]:
        return sorted(self.root.glob("*/*.ticket.jsonl"))

    def _ticket_file(self, namespace: str, ticket_id: str) -> Path:
        return self.root / namespace / f"{ticket_id}.ticket.jsonl"

    def _ticket_file_by_id(self, ticket_id: str) -> Path | None:
        if not LOCAL_TICKET_ID_RE.fullmatch(ticket_id):
            return None
        namespace = ticket_id.split("-", maxsplit=1)[0].lower()
        path = self._ticket_file(namespace, ticket_id.lower())
        if path.exists():
            return path
        return next((candidate for candidate in self._event_files() if candidate.stem.removesuffix(".ticket") == ticket_id), None)

    def _read_events_from_file(self, path: Path) -> list[TicketEvent]:
        events: list[TicketEvent] = []
        if not path.exists():
            return events
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(TicketEvent.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValueError):
                continue
        return events

    def _append_events(self, path: Path, events: list[TicketEvent]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")
        self._write_index(self._load_items())

    def _read_counters(self) -> dict[str, int]:
        if not self.counters_path.exists():
            return {}
        try:
            payload = json.loads(self.counters_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(key): int(value) for key, value in payload.items() if isinstance(value, int)}

    def _write_counters(self, counters: dict[str, int]) -> None:
        self.counters_path.parent.mkdir(parents=True, exist_ok=True)
        self.counters_path.write_text(json.dumps(counters, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _max_existing_number(self, namespace: str) -> int:
        max_value = 0
        pattern = re.compile(rf"^{re.escape(namespace)}-(\d+)$")
        for path in self.root.glob(f"{namespace}/{namespace}-*.ticket.jsonl"):
            match = pattern.fullmatch(path.stem.removesuffix(".ticket"))
            if match:
                max_value = max(max_value, int(match.group(1)))
        return max_value

    def _next_ticket_id(self, namespace: str) -> str:
        counters = self._read_counters()
        next_number = max(counters.get(namespace, 0), self._max_existing_number(namespace)) + 1
        counters[namespace] = next_number
        self._write_counters(counters)
        return f"{namespace}-{next_number:04d}"

    def _legacy_index_rows(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            return []
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def _migrate_legacy_index_if_needed(self) -> None:
        if self._event_files():
            return
        rows = self._legacy_index_rows()
        if not rows:
            return
        for row in rows:
            try:
                ticket = Ticket.model_validate(row)
            except ValueError:
                continue
            namespace = _normalize_namespace(ticket.ticket_type) or "ops"
            ticket_id = ticket.id if LOCAL_TICKET_ID_RE.fullmatch(ticket.id) else self._next_ticket_id(namespace)
            actor_id = CLARA_SYSTEM_EMPLOYEE_ID
            actor_role = CLARA_SYSTEM_ROLE
            created = _event(
                ticket_id,
                "created",
                actor_id=actor_id,
                actor_role=actor_role,
                at=ticket.created_at,
                data={
                    "title": ticket.title,
                    "description": ticket.description,
                    "status": ticket.status,
                    "ticket_type": namespace,
                    "knowledge_refs": ticket.knowledge_refs,
                    "code_repository_ids": ticket.code_repository_ids,
                    "source_thread_id": ticket.source_thread_id,
                    "source_run_id": ticket.source_run_id,
                },
            )
            events = [created]
            if ticket.assigned_employee_id or ticket.assigned_role:
                events.append(
                    _event(
                        ticket_id,
                        "assigned",
                        actor_id=actor_id,
                        actor_role=actor_role,
                        at=ticket.created_at,
                        data={
                            "assigned_employee_id": ticket.assigned_employee_id,
                            "assigned_role": ticket.assigned_role,
                        },
                    )
                )
            for report in ticket.reports:
                events.append(
                    _event(
                        ticket_id,
                        "reported",
                        actor_id=report.reporter_employee_id,
                        actor_role=report.reporter_role,
                        at=report.created_at,
                        data={"report": report.model_dump(mode="json")},
                    )
                )
            self._append_events(self._ticket_file(namespace, ticket_id), events)

    def _write_index(self, items: list[Ticket]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _project_ticket(self, events: list[TicketEvent], path: Path) -> Ticket | None:
        if not events:
            return None
        ticket_id = events[0].ticket_id
        namespace = ticket_id.split("-", maxsplit=1)[0].lower()
        state: dict[str, Any] = {
            "id": ticket_id,
            "title": ticket_id,
            "description": "",
            "status": "open",
            "ticket_type": namespace,
            "assigned_employee_id": "",
            "assigned_role": "",
            "validation_employee_id": "",
            "validation_role": "",
            "knowledge_refs": [],
            "code_repository_ids": [],
            "source_thread_id": "",
            "source_run_id": "",
            "reports": [],
            "created_at": events[0].at,
            "updated_at": events[-1].at,
            "saved_path": _relative(path),
            "events": events,
        }
        for event in events:
            data = event.data
            state["updated_at"] = event.at
            if event.type == "created":
                state.update(
                    {
                        "title": str(data.get("title") or state["title"]),
                        "description": str(data.get("description") or data.get("title") or state["description"]),
                        "status": str(data.get("status") or state["status"]),
                        "ticket_type": str(data.get("ticket_type") or namespace),
                        "knowledge_refs": [str(item) for item in data.get("knowledge_refs", []) if str(item).strip()],
                        "code_repository_ids": [str(item) for item in data.get("code_repository_ids", []) if str(item).strip()],
                        "source_thread_id": str(data.get("source_thread_id") or ""),
                        "source_run_id": str(data.get("source_run_id") or ""),
                    }
                )
                state["created_at"] = event.at
            elif event.type == "assigned":
                state["assigned_employee_id"] = str(data.get("assigned_employee_id") or data.get("to_employee_id") or "")
                state["assigned_role"] = str(data.get("assigned_role") or data.get("to_role") or "")
            elif event.type == "validation_requested":
                state["validation_employee_id"] = str(data.get("validation_employee_id") or data.get("to_employee_id") or "")
                state["validation_role"] = str(data.get("validation_role") or data.get("to_role") or "")
            elif event.type in {"reported", "validated", "blocked"}:
                report_payload = data.get("report")
                if isinstance(report_payload, dict):
                    report = TicketReport.model_validate({**report_payload, "source_event_id": event.event_id})
                    state["reports"].append(report)
            elif event.type == "status_changed":
                state["status"] = str(data.get("to") or data.get("status") or state["status"])
            elif event.type == "asset_linked":
                target_kind = str(data.get("target_kind") or "")
                target_ref = str(data.get("target_ref") or "")
                if target_kind == "knowledge" and target_ref and target_ref not in state["knowledge_refs"]:
                    state["knowledge_refs"].append(target_ref)
                if target_kind == "repository" and target_ref and target_ref not in state["code_repository_ids"]:
                    state["code_repository_ids"].append(target_ref)
        return Ticket.model_validate(state)

    def _load_items(self) -> list[Ticket]:
        self._migrate_legacy_index_if_needed()
        items = [
            ticket
            for ticket in (self._project_ticket(self._read_events_from_file(path), path) for path in self._event_files())
            if ticket is not None
        ]
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def list_tickets(self, status: str | None = None) -> list[Ticket]:
        items = self._load_items()
        if status:
            items = [item for item in items if item.status == status]
        self._write_index(items)
        return items

    def create_ticket(self, request: TicketCreateRequest) -> Ticket:
        actor_id = request.actor_employee_id.strip() or CLARA_SYSTEM_EMPLOYEE_ID
        actor_role = _resolve_actor_role(actor_id, request.actor_role)
        namespace = _infer_ticket_namespace(request, actor_role)
        _ensure_namespace_authority(namespace, actor_employee_id=actor_id, actor_role=actor_role)

        timestamp = _now()
        item_id = self._next_ticket_id(namespace)
        initial_status = "assigned" if (request.assigned_employee_id.strip() or request.assigned_role.strip()) else "open"
        events = [
            _event(
                item_id,
                "created",
                actor_id=actor_id,
                actor_role=actor_role,
                at=timestamp,
                data={
                    "title": request.title.strip(),
                    "description": request.description.strip() or request.title.strip(),
                    "status": initial_status,
                    "ticket_type": namespace,
                    "knowledge_refs": sorted({item.strip() for item in request.knowledge_refs if item.strip()}),
                    "code_repository_ids": sorted({item.strip() for item in request.code_repository_ids if item.strip()}),
                    "source_thread_id": request.source_thread_id.strip(),
                    "source_run_id": request.source_run_id.strip(),
                },
            )
        ]
        if request.assigned_employee_id.strip() or request.assigned_role.strip():
            events.append(
                _event(
                    item_id,
                    "assigned",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    at=timestamp,
                    data={
                        "assigned_employee_id": request.assigned_employee_id.strip(),
                        "assigned_role": request.assigned_role.strip(),
                    },
                )
            )
        if request.validation_employee_id.strip() or request.validation_role.strip():
            events.append(
                _event(
                    item_id,
                    "validation_requested",
                    actor_id=actor_id,
                    actor_role=actor_role,
                    at=timestamp,
                    data={
                        "validation_employee_id": request.validation_employee_id.strip(),
                        "validation_role": request.validation_role.strip(),
                    },
                )
            )
        for ref in sorted({item.strip() for item in request.knowledge_refs if item.strip()}):
            events.append(_event(item_id, "asset_linked", actor_id=actor_id, actor_role=actor_role, at=timestamp, data={"target_kind": "knowledge", "target_ref": ref}))
        for ref in sorted({item.strip() for item in request.code_repository_ids if item.strip()}):
            events.append(_event(item_id, "asset_linked", actor_id=actor_id, actor_role=actor_role, at=timestamp, data={"target_kind": "repository", "target_ref": ref}))

        path = self._ticket_file(namespace, item_id)
        self._append_events(path, events)
        item = self.get_ticket(item_id)
        if item is None:  # Defensive; append just succeeded.
            raise ValueError(f"Ticket was not persisted: {item_id}")
        return item

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        path = self._ticket_file_by_id(ticket_id.strip())
        if path is None:
            return None
        return self._project_ticket(self._read_events_from_file(path), path)

    def get_ticket_events(self, ticket_id: str) -> list[TicketEvent]:
        path = self._ticket_file_by_id(ticket_id.strip())
        return self._read_events_from_file(path) if path is not None else []

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket:
        item = self.get_ticket(ticket_id)
        path = self._ticket_file_by_id(ticket_id.strip())
        if item is None or path is None:
            raise KeyError(ticket_id)

        timestamp = _now()
        reporter_id = request.reporter_employee_id.strip()
        reporter_role = request.reporter_role.strip() or _employee_role(reporter_id)
        report_type = request.report_type.strip() or "progress"
        report = TicketReport(
            id=f"report-{uuid4().hex[:10]}",
            reporter_employee_id=reporter_id,
            reporter_role=reporter_role,
            content=request.content.strip(),
            evidence=[entry.strip() for entry in request.evidence if entry.strip()],
            report_type=report_type,
            created_at=timestamp,
        )
        if report_type == "validation":
            event_type = "validated"
            next_status = "validated"
        elif report_type in {"blocked", "failed", "failure"}:
            event_type = "blocked"
            next_status = "blocked"
        elif report_type in {"result", "done", "completed"}:
            event_type = "reported"
            next_status = "reported"
        else:
            event_type = "reported"
            next_status = item.status

        events = [
            _event(
                item.id,
                event_type,
                actor_id=reporter_id,
                actor_role=reporter_role,
                at=timestamp,
                data={
                    "report": report.model_dump(mode="json"),
                    "source_run_id": request.source_run_id.strip(),
                },
            )
        ]
        if next_status != item.status:
            events.append(
                _event(
                    item.id,
                    "status_changed",
                    actor_id=reporter_id,
                    actor_role=reporter_role,
                    at=timestamp,
                    data={"from": item.status, "to": next_status, "reason": f"report:{report.id}"},
                )
            )
        for evidence in report.evidence:
            events.append(
                _event(
                    item.id,
                    "asset_linked",
                    actor_id=reporter_id,
                    actor_role=reporter_role,
                    at=timestamp,
                    data={"target_kind": "evidence", "target_ref": evidence, "source_report_id": report.id},
                )
            )
        self._append_events(path, events)
        updated = self.get_ticket(item.id)
        if updated is None:
            raise KeyError(ticket_id)
        return updated

    def employee_work_ledger(self, employee_id: str) -> EmployeeWorkLedger:
        normalized = employee_id.strip()
        current: dict[str, TicketWorkItem] = {}
        historical: dict[str, TicketWorkItem] = {}
        reports: list[EmployeeTicketReportRecord] = []
        validations: list[EmployeeTicketReportRecord] = []
        blocked_records: list[EmployeeTicketReportRecord] = []
        handoffs: list[dict[str, Any]] = []

        for ticket in self._load_items():
            roles: set[str] = set()
            if ticket.assigned_employee_id == normalized:
                roles.add("owner")
            if ticket.validation_employee_id == normalized:
                roles.add("validator")
            for event in ticket.events:
                actor_id = event.actor.get("id", "")
                if actor_id == normalized and event.type.startswith("handoff"):
                    roles.add("handoff")
                    handoffs.append({"ticket_id": ticket.id, "title": ticket.title, "event": event.model_dump(mode="json")})
            for report in ticket.reports:
                if report.reporter_employee_id != normalized:
                    continue
                roles.add("reporter")
                record = EmployeeTicketReportRecord(
                    ticket_id=ticket.id,
                    ticket_title=ticket.title,
                    report_id=report.id,
                    report_type=report.report_type,
                    content=report.content,
                    evidence=report.evidence,
                    created_at=report.created_at,
                )
                reports.append(record)
                if report.report_type == "validation":
                    validations.append(record)
                if report.report_type in {"blocked", "failed", "failure"}:
                    blocked_records.append(record)
            if not roles:
                continue
            item = TicketWorkItem(
                ticket_id=ticket.id,
                title=ticket.title,
                status=ticket.status,
                role=", ".join(sorted(roles)),
                updated_at=ticket.updated_at,
                next_action=_next_action(ticket),
            )
            historical[ticket.id] = item
            if not _terminal_status(ticket.status):
                current[ticket.id] = item

        return EmployeeWorkLedger(
            employee_id=normalized,
            current_tickets=sorted(current.values(), key=lambda item: item.updated_at, reverse=True),
            historical_tickets=sorted(historical.values(), key=lambda item: item.updated_at, reverse=True),
            reports=sorted(reports, key=lambda item: item.created_at, reverse=True),
            validations=sorted(validations, key=lambda item: item.created_at, reverse=True),
            blocked_records=sorted(blocked_records, key=lambda item: item.created_at, reverse=True),
            handoffs=handoffs,
            contribution={
                "ticket_count": len(historical),
                "current_ticket_count": len(current),
                "report_count": len(reports),
                "validation_count": len(validations),
                "blocked_count": len(blocked_records),
                "handoff_count": len(handoffs),
            },
        )

    def ticket_asset_records(self) -> list[TicketAssetRecord]:
        records: list[TicketAssetRecord] = []
        for ticket in self._load_items():
            scopes = [ticket.ticket_type, *ticket.knowledge_refs]
            assigned = [value for value in [ticket.assigned_employee_id, ticket.validation_employee_id] if value]
            for report in ticket.reports:
                status = "approved" if report.report_type == "validation" else "candidate"
                records.append(
                    TicketAssetRecord(
                        id=report.id,
                        kind="report",
                        title=f"{report.report_type} report for {ticket.id}",
                        status=status,
                        source_ticket_id=ticket.id,
                        source_employee_id=report.reporter_employee_id,
                        assigned_employees=assigned,
                        scopes=scopes,
                        created_at=report.created_at,
                        updated_at=report.created_at,
                        metadata={"ticket_title": ticket.title, "report": report.model_dump(mode="json")},
                    )
                )
                for index, evidence in enumerate(report.evidence):
                    records.append(
                        TicketAssetRecord(
                            id=f"{report.id}:evidence:{index}",
                            kind="evidence",
                            title=evidence,
                            status=status,
                            source_ticket_id=ticket.id,
                            source_employee_id=report.reporter_employee_id,
                            assigned_employees=assigned,
                            scopes=scopes,
                            created_at=report.created_at,
                            updated_at=report.created_at,
                            metadata={"ticket_title": ticket.title, "report_id": report.id, "evidence": evidence},
                        )
                    )
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def status(self) -> TicketBackendStatus:
        items = self._load_items()
        self._write_index(items)
        return TicketBackendStatus(
            mode=self.settings.mode,
            status="ready",
            detail="Local append-only Ticket backend is active.",
            ticket_count=len(items),
            local_file_path=_relative(self.index_path),
            saved_paths={
                "settings": _relative(_backend_settings_path()),
                "local_file": _relative(self.index_path),
                "counters": _relative(self.counters_path),
                "tickets": _relative(self.root),
            },
            supported_modes=SUPPORTED_BACKENDS,
        )


class PlannedTicketAdapter:
    def __init__(self, settings: TicketBackendSettings):
        self.settings = settings

    def _raise(self) -> None:
        raise ValueError(f"Ticket backend '{self.settings.mode}' is planned but not implemented yet.")

    def list_tickets(self, status: str | None = None) -> list[Ticket]:
        self._raise()

    def create_ticket(self, request: TicketCreateRequest) -> Ticket:
        self._raise()

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        self._raise()

    def get_ticket_events(self, ticket_id: str) -> list[TicketEvent]:
        self._raise()

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket:
        self._raise()

    def employee_work_ledger(self, employee_id: str) -> EmployeeWorkLedger:
        self._raise()

    def ticket_asset_records(self) -> list[TicketAssetRecord]:
        self._raise()

    def status(self) -> TicketBackendStatus:
        return TicketBackendStatus(
            mode=self.settings.mode,
            status="planned",
            detail=f"Ticket backend '{self.settings.mode}' is configured, but only local_file is executable in this version.",
            ticket_count=0,
            local_file_path=self.settings.local_file_path,
            saved_paths={
                "settings": _relative(_backend_settings_path()),
                "local_file": self.settings.local_file_path,
            },
            supported_modes=SUPPORTED_BACKENDS,
        )


def ticket_adapter() -> TicketAdapter:
    settings = ticket_backend_settings()
    if settings.mode == "local_file":
        return LocalFileTicketAdapter(settings)
    return PlannedTicketAdapter(settings)


def ticket_backend_status() -> TicketBackendStatus:
    return ticket_adapter().status()


def list_tickets(status: str | None = None) -> list[Ticket]:
    return ticket_adapter().list_tickets(status=status)


def create_ticket(request: TicketCreateRequest) -> Ticket:
    return ticket_adapter().create_ticket(request)


def get_ticket(ticket_id: str) -> Ticket | None:
    return ticket_adapter().get_ticket(ticket_id)


def get_ticket_events(ticket_id: str) -> list[TicketEvent]:
    return ticket_adapter().get_ticket_events(ticket_id)


def add_ticket_report(ticket_id: str, request: TicketReportRequest) -> Ticket:
    return ticket_adapter().add_ticket_report(ticket_id, request)


def employee_work_ledger(employee_id: str) -> EmployeeWorkLedger:
    return ticket_adapter().employee_work_ledger(employee_id)


def ticket_asset_records() -> list[TicketAssetRecord]:
    return ticket_adapter().ticket_asset_records()
