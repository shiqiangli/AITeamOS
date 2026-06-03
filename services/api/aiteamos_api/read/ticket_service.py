"""Ticket service with a small backend adapter boundary."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field


class TicketReport(BaseModel):
    id: str
    reporter_employee_id: str
    reporter_role: str = ""
    content: str
    evidence: list[str] = Field(default_factory=list)
    report_type: str = "progress"
    created_at: str


class Ticket(BaseModel):
    id: str
    title: str
    description: str
    status: str = "assigned"
    assigned_employee_id: str = ""
    assigned_role: str = ""
    validation_employee_id: str = ""
    validation_role: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    code_repository_ids: list[str] = Field(default_factory=list)
    source_thread_id: str = ""
    source_run_id: str = ""
    reports: list[TicketReport] = Field(default_factory=list)
    created_at: str
    updated_at: str
    saved_path: str = ""


class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    assigned_employee_id: str = ""
    assigned_role: str = ""
    validation_employee_id: str = ""
    validation_role: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    code_repository_ids: list[str] = Field(default_factory=list)
    source_thread_id: str = ""
    source_run_id: str = ""


class TicketReportRequest(BaseModel):
    reporter_employee_id: str
    reporter_role: str = ""
    content: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    report_type: str = "progress"


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
        description="File-backed Tickets for fast local dogfooding and repository-tracked self-improvement.",
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


class TicketAdapter(Protocol):
    def list_tickets(self, status: str | None = None) -> list[Ticket]: ...

    def create_ticket(self, request: TicketCreateRequest) -> Ticket: ...

    def get_ticket(self, ticket_id: str) -> Ticket | None: ...

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket: ...

    def status(self) -> TicketBackendStatus: ...


class LocalFileTicketAdapter:
    def __init__(self, settings: TicketBackendSettings):
        self.settings = settings
        self.path = _resolve_local_file_path(settings)

    def _read_index(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return payload if isinstance(payload, list) else []

    def _write_index(self, items: list[Ticket]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load_items(self) -> list[Ticket]:
        return [Ticket.model_validate(item) for item in self._read_index()]

    def _save_item(self, item: Ticket) -> Ticket:
        items = self._load_items()
        for index, current in enumerate(items):
            if current.id == item.id:
                items[index] = item
                self._write_index(items)
                return item
        items.append(item)
        self._write_index(items)
        return item

    def list_tickets(self, status: str | None = None) -> list[Ticket]:
        items = sorted(self._load_items(), key=lambda item: item.updated_at, reverse=True)
        if status:
            items = [item for item in items if item.status == status]
        return items

    def create_ticket(self, request: TicketCreateRequest) -> Ticket:
        timestamp = _now()
        item_id = f"ticket-{_slug(request.title)}-{uuid4().hex[:6]}"
        item = Ticket(
            id=item_id,
            title=request.title.strip(),
            description=request.description.strip() or request.title.strip(),
            assigned_employee_id=request.assigned_employee_id.strip(),
            assigned_role=request.assigned_role.strip(),
            validation_employee_id=request.validation_employee_id.strip(),
            validation_role=request.validation_role.strip(),
            knowledge_refs=sorted({item.strip() for item in request.knowledge_refs if item.strip()}),
            code_repository_ids=sorted({item.strip() for item in request.code_repository_ids if item.strip()}),
            source_thread_id=request.source_thread_id.strip(),
            source_run_id=request.source_run_id.strip(),
            created_at=timestamp,
            updated_at=timestamp,
            saved_path=_relative(self.path),
        )
        return self._save_item(item)

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        return next((item for item in self._load_items() if item.id == ticket_id), None)

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket:
        item = self.get_ticket(ticket_id)
        if item is None:
            raise KeyError(ticket_id)

        timestamp = _now()
        report = TicketReport(
            id=f"report-{uuid4().hex[:10]}",
            reporter_employee_id=request.reporter_employee_id.strip(),
            reporter_role=request.reporter_role.strip(),
            content=request.content.strip(),
            evidence=[entry.strip() for entry in request.evidence if entry.strip()],
            report_type=request.report_type.strip() or "progress",
            created_at=timestamp,
        )
        item.reports.append(report)
        if report.report_type == "validation":
            item.status = "validated"
        elif report.report_type in {"result", "done", "completed"}:
            item.status = "reported"
        item.updated_at = timestamp
        return self._save_item(item)

    def status(self) -> TicketBackendStatus:
        items = self._load_items()
        return TicketBackendStatus(
            mode=self.settings.mode,
            status="ready",
            detail="Local file Ticket backend is active.",
            ticket_count=len(items),
            local_file_path=_relative(self.path),
            saved_paths={
                "settings": _relative(_backend_settings_path()),
                "local_file": _relative(self.path),
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

    def add_ticket_report(self, ticket_id: str, request: TicketReportRequest) -> Ticket:
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


def _read_index() -> list[dict[str, Any]]:
    path = _resolve_local_file_path(ticket_backend_settings())
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_index(items: list[Ticket]) -> None:
    path = _resolve_local_file_path(ticket_backend_settings())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_items() -> list[Ticket]:
    return [Ticket.model_validate(item) for item in _read_index()]


def list_tickets(status: str | None = None) -> list[Ticket]:
    return ticket_adapter().list_tickets(status=status)


def _save_item(item: Ticket) -> Ticket:
    items = _load_items()
    for index, current in enumerate(items):
        if current.id == item.id:
            items[index] = item
            _write_index(items)
            return item
    items.append(item)
    _write_index(items)
    return item


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip().lower()).strip("-")
    return slug[:72] or "ticket"


def create_ticket(request: TicketCreateRequest) -> Ticket:
    return ticket_adapter().create_ticket(request)


def get_ticket(ticket_id: str) -> Ticket | None:
    return ticket_adapter().get_ticket(ticket_id)


def add_ticket_report(ticket_id: str, request: TicketReportRequest) -> Ticket:
    return ticket_adapter().add_ticket_report(ticket_id, request)
