"""Skill usage ledger for governed Skill assets."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

SKILL_USAGE_USEFULNESS_STATUSES = {"unreviewed", "used", "irrelevant", "harmful", "promoted"}
SKILL_USAGE_USEFULNESS_ALIASES = {
    "useful": "used",
    "not_useful": "irrelevant",
    "not-useful": "irrelevant",
    "not useful": "irrelevant",
    "neutral": "irrelevant",
    "promote": "promoted",
}


class SkillUsageRecord(BaseModel):
    id: str
    skill_id: str
    employee_id: str
    run_id: str
    thread_id: str = ""
    ticket_keys: list[str] = Field(default_factory=list)
    source_kind: str = "chat_context"
    source_ref: str = ""
    trace_path: str = ""
    usefulness_status: str = "unreviewed"
    provenance: dict[str, Any] = Field(default_factory=dict)
    used_at: str = ""


class SkillUsageReviewRequest(BaseModel):
    usefulness_status: str = Field(min_length=1)
    reviewer_employee_id: str = "clara"
    reason: str = ""


class SkillUsageReviewResponse(BaseModel):
    record: SkillUsageRecord
    summary: dict[str, Any] = Field(default_factory=dict)
    saved_paths: dict[str, str] = Field(default_factory=dict)


def record_skill_usage(
    *,
    workspace_dir: Path,
    skill_ids: list[str],
    employee_id: str,
    run_id: str,
    thread_id: str = "",
    ticket_keys: list[str] | None = None,
    trace_path: str = "",
    source_kind: str = "chat_context",
) -> list[dict[str, Any]]:
    normalized_skills = _unique_strings(skill_ids)
    if not normalized_skills or not employee_id.strip() or not run_id.strip():
        return []

    records = _load_records(workspace_dir)
    by_key = {(record.skill_id, record.run_id, record.employee_id): index for index, record in enumerate(records)}
    timestamp = _now()
    refs: list[dict[str, Any]] = []
    for skill_id in normalized_skills:
        record = SkillUsageRecord(
            id=f"skill-usage-{_safe_id(skill_id)}-{_safe_id(run_id)}-{_safe_id(employee_id)}",
            skill_id=skill_id,
            employee_id=employee_id,
            run_id=run_id,
            thread_id=thread_id,
            ticket_keys=_unique_strings(ticket_keys or []),
            source_kind=source_kind,
            source_ref=trace_path or run_id,
            trace_path=trace_path,
            usefulness_status="unreviewed",
            provenance={
                "skill_id": skill_id,
                "source_employee_id": employee_id,
                "source_run_id": run_id,
                "source_thread_id": thread_id,
                "source_ticket_ids": _unique_strings(ticket_keys or []),
                "source_trace_path": trace_path,
                "why_recorded": "Skill was loaded into an Employee Chat runtime context.",
            },
            used_at=timestamp,
        )
        key = (record.skill_id, record.run_id, record.employee_id)
        if key in by_key:
            records[by_key[key]] = record
        else:
            records.append(record)
            by_key[key] = len(records) - 1
        refs.append(_usage_ref(record))
    _save_records(workspace_dir, records)
    return refs


def review_skill_usage(
    *,
    workspace_dir: Path,
    usage_id: str,
    request: SkillUsageReviewRequest,
) -> SkillUsageReviewResponse:
    normalized_usage_id = usage_id.strip()
    if not normalized_usage_id:
        raise KeyError(usage_id)
    try:
        usefulness_status = _normalize_usefulness_status(request.usefulness_status, allow_unreviewed=False)
    except ValueError as exc:
        raise ValueError(
            "Skill usage usefulness status must be one of: "
            + ", ".join(sorted(SKILL_USAGE_USEFULNESS_STATUSES - {"unreviewed"}))
            + ". Legacy aliases useful, not_useful, neutral, and promote are accepted."
        ) from exc

    records = _load_records(workspace_dir)
    index = next((idx for idx, record in enumerate(records) if record.id == normalized_usage_id), -1)
    if index < 0:
        raise KeyError(normalized_usage_id)

    timestamp = _now()
    current = records[index]
    provenance = dict(current.provenance)
    reviews = provenance.get("reviews") if isinstance(provenance.get("reviews"), list) else []
    reviews.append(
        {
            "reviewed_at": timestamp,
            "reviewer_employee_id": request.reviewer_employee_id.strip() or "clara",
            "usefulness_status": usefulness_status,
            "reason": request.reason.strip(),
        }
    )
    reviewed = current.model_copy(
        update={
            "usefulness_status": usefulness_status,
            "provenance": {
                **provenance,
                "last_reviewed_at": timestamp,
                "last_reviewer_employee_id": request.reviewer_employee_id.strip() or "clara",
                "last_usefulness_status": usefulness_status,
                "last_usefulness_reason": request.reason.strip(),
                "reviews": reviews[-20:],
            },
        }
    )
    records[index] = reviewed
    _save_records(workspace_dir, records)
    return SkillUsageReviewResponse(
        record=reviewed,
        summary=skill_usage_summary(workspace_dir, reviewed.skill_id),
        saved_paths={"skill_usage": _relative_path(_records_path(workspace_dir))},
    )


def skill_usage_summary(workspace_dir: Path, skill_id: str, *, limit: int = 8) -> dict[str, Any]:
    normalized_id = skill_id.strip()
    records = [record for record in _load_records(workspace_dir) if record.skill_id == normalized_id]
    records.sort(key=lambda record: record.used_at, reverse=True)
    usefulness_stats: dict[str, int] = {}
    for record in records:
        status = _normalize_usefulness_status(record.usefulness_status or "unreviewed", allow_unreviewed=True)
        usefulness_stats[status] = usefulness_stats.get(status, 0) + 1
    latest = records[0] if records else None
    latest_reviewed = next((record for record in records if record.usefulness_status != "unreviewed"), None)
    stats_payload: dict[str, Any] = {}
    if records:
        stats_payload = {
            **usefulness_stats,
            "status_counts": usefulness_stats,
            "used_count": usefulness_stats.get("used", 0),
            "irrelevant_count": usefulness_stats.get("irrelevant", 0),
            "harmful_count": usefulness_stats.get("harmful", 0),
            "promoted_count": usefulness_stats.get("promoted", 0),
            "unreviewed_count": usefulness_stats.get("unreviewed", 0),
            "last_usefulness_status": latest_reviewed.usefulness_status if latest_reviewed else (latest.usefulness_status if latest else ""),
            "last_reviewed_at": str(latest_reviewed.provenance.get("last_reviewed_at") or "") if latest_reviewed else "",
            "last_reviewer_employee_id": str(latest_reviewed.provenance.get("last_reviewer_employee_id") or "") if latest_reviewed else "",
        }
    return {
        "usage_count": len(records),
        "last_used_at": latest.used_at if latest else "",
        "last_used_by_employee_id": latest.employee_id if latest else "",
        "last_used_run_id": latest.run_id if latest else "",
        "last_used_ticket_id": latest.ticket_keys[0] if latest and latest.ticket_keys else "",
        "usefulness_stats": stats_payload,
        "usage_history": [_usage_ref(record) for record in records[:limit]],
    }


def _usage_ref(record: SkillUsageRecord) -> dict[str, Any]:
    return {
        "usage_id": record.id,
        "skill_id": record.skill_id,
        "employee_id": record.employee_id,
        "source_run_id": record.run_id,
        "source_thread_id": record.thread_id,
        "source_ticket_ids": list(record.ticket_keys),
        "source_trace_path": record.trace_path,
        "usefulness_status": record.usefulness_status,
        "reviewed_at": str(record.provenance.get("last_reviewed_at") or ""),
        "reviewer_employee_id": str(record.provenance.get("last_reviewer_employee_id") or ""),
        "usefulness_reason": str(record.provenance.get("last_usefulness_reason") or ""),
        "used_at": record.used_at,
    }


def _records_path(workspace_dir: Path) -> Path:
    return workspace_dir / "assets" / "skill_usage.json"


def _load_records(workspace_dir: Path) -> list[SkillUsageRecord]:
    path = _records_path(workspace_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    records: list[SkillUsageRecord] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            records.append(SkillUsageRecord.model_validate(item))
        except Exception:
            continue
    return records


def _save_records(workspace_dir: Path, records: list[SkillUsageRecord]) -> None:
    path = _records_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([record.model_dump(mode="json") for record in records], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _safe_id(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip()).strip("-") or "unknown"


def _normalize_usefulness_status(value: str, *, allow_unreviewed: bool) -> str:
    normalized = value.strip().lower().replace("-", "_")
    normalized = SKILL_USAGE_USEFULNESS_ALIASES.get(normalized, normalized)
    if normalized == "unreviewed" and allow_unreviewed:
        return normalized
    allowed = SKILL_USAGE_USEFULNESS_STATUSES if allow_unreviewed else SKILL_USAGE_USEFULNESS_STATUSES - {"unreviewed"}
    if normalized not in allowed:
        raise ValueError(normalized)
    return normalized


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(path.parents[1]))
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(UTC).isoformat()
