"""Local work item service used before Jira is introduced."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkItemReport(BaseModel):
    id: str
    reporter_member_id: str
    reporter_role: str = ""
    content: str
    evidence: list[str] = Field(default_factory=list)
    report_type: str = "progress"
    created_at: str


class WorkItem(BaseModel):
    id: str
    title: str
    description: str
    status: str = "assigned"
    assigned_member_id: str = ""
    assigned_role: str = ""
    validation_member_id: str = ""
    validation_role: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    code_repository_ids: list[str] = Field(default_factory=list)
    source_thread_id: str = ""
    source_run_id: str = ""
    reports: list[WorkItemReport] = Field(default_factory=list)
    created_at: str
    updated_at: str
    saved_path: str = ""


class WorkItemCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    assigned_member_id: str = ""
    assigned_role: str = ""
    validation_member_id: str = ""
    validation_role: str = ""
    knowledge_refs: list[str] = Field(default_factory=list)
    code_repository_ids: list[str] = Field(default_factory=list)
    source_thread_id: str = ""
    source_run_id: str = ""


class WorkItemReportRequest(BaseModel):
    reporter_member_id: str
    reporter_role: str = ""
    content: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    report_type: str = "progress"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    return Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", Path.cwd())).resolve()


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _work_items_dir() -> Path:
    path = _workspace_dir() / "work_items"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path() -> Path:
    return _work_items_dir() / "index.json"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


def _read_index() -> list[dict[str, Any]]:
    path = _index_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _write_index(items: list[WorkItem]) -> None:
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([item.model_dump(mode="json") for item in items], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_items() -> list[WorkItem]:
    return [WorkItem.model_validate(item) for item in _read_index()]


def list_work_items(status: str | None = None) -> list[WorkItem]:
    items = sorted(_load_items(), key=lambda item: item.updated_at, reverse=True)
    if status:
        items = [item for item in items if item.status == status]
    return items


def _save_item(item: WorkItem) -> WorkItem:
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
    return slug[:72] or "work"


def create_work_item(request: WorkItemCreateRequest) -> WorkItem:
    timestamp = _now()
    item_id = f"work-{_slug(request.title)}-{uuid4().hex[:6]}"
    path = _index_path()
    item = WorkItem(
        id=item_id,
        title=request.title.strip(),
        description=request.description.strip() or request.title.strip(),
        assigned_member_id=request.assigned_member_id.strip(),
        assigned_role=request.assigned_role.strip(),
        validation_member_id=request.validation_member_id.strip(),
        validation_role=request.validation_role.strip(),
        knowledge_refs=sorted({item.strip() for item in request.knowledge_refs if item.strip()}),
        code_repository_ids=sorted({item.strip() for item in request.code_repository_ids if item.strip()}),
        source_thread_id=request.source_thread_id.strip(),
        source_run_id=request.source_run_id.strip(),
        created_at=timestamp,
        updated_at=timestamp,
        saved_path=_relative(path),
    )
    return _save_item(item)


def get_work_item(work_item_id: str) -> WorkItem | None:
    return next((item for item in _load_items() if item.id == work_item_id), None)


def add_work_item_report(work_item_id: str, request: WorkItemReportRequest) -> WorkItem:
    item = get_work_item(work_item_id)
    if item is None:
        raise KeyError(work_item_id)

    timestamp = _now()
    report = WorkItemReport(
        id=f"report-{uuid4().hex[:10]}",
        reporter_member_id=request.reporter_member_id.strip(),
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
    return _save_item(item)
