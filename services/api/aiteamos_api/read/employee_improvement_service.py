"""Governed application of approved Employee improvement Assets."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .asset_candidate_service import AssetRecord, asset_records_path, list_asset_records, upsert_asset_record


class EmployeeImprovementApplyRequest(BaseModel):
    actor_employee_id: str = "clara"
    reason: str = ""
    application_note: str = ""


class EmployeeImprovementApplyResponse(BaseModel):
    employee_id: str
    asset_id: str
    status: str
    detail: str
    applied_changes: dict[str, list[str]] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    asset: AssetRecord
    ticket_report_id: str = ""
    saved_paths: dict[str, str] = Field(default_factory=dict)


def apply_employee_improvement_asset(
    employee_id: str,
    asset_id: str,
    request: EmployeeImprovementApplyRequest,
    *,
    workspace_dir: Path | None = None,
) -> EmployeeImprovementApplyResponse:
    normalized_employee_id = employee_id.strip()
    normalized_asset_id = asset_id.strip()
    if not normalized_employee_id:
        raise ValueError("Employee id is required.")
    if not normalized_asset_id:
        raise ValueError("Employee improvement Asset id is required.")

    workspace = _workspace_dir(workspace_dir)
    asset = next((item for item in list_asset_records(workspace_dir=workspace) if item.id == normalized_asset_id), None)
    if asset is None:
        raise KeyError(normalized_asset_id)
    _validate_employee_improvement_asset(asset, normalized_employee_id)

    profile_path = _employee_profile_path(normalized_employee_id, workspace_dir=workspace)
    if not profile_path.exists():
        raise KeyError(normalized_employee_id)
    profile = _read_profile(profile_path)
    timestamp = _now()
    actor_employee_id = request.actor_employee_id.strip() or "clara"
    proposed_updates = _proposed_profile_updates(asset)
    applied_changes = _apply_allowlisted_profile_updates(profile, proposed_updates)
    improvement_ref = {
        "asset_id": asset.id,
        "asset_type": asset.asset_type,
        "applied_by_employee_id": actor_employee_id,
        "applied_at": timestamp,
        "reason": request.reason.strip(),
        "source_ticket_id": _source_ticket_id(asset),
        "source_feedback_id": str(asset.provenance.get("source_feedback_id") or ""),
        "asset_review_id": str(asset.provenance.get("asset_review_id") or ""),
    }
    improvement_ref = {key: value for key, value in improvement_ref.items() if value}
    _append_unique_ref(profile, "applied_improvement_refs", improvement_ref, "asset_id")
    _append_unique_string(profile, "work_history_refs", f"asset:{asset.id}")
    profile["updated_at"] = timestamp
    _write_profile(profile_path, profile)

    ticket_report_id = _record_ticket_application_report(
        employee_id=normalized_employee_id,
        asset=asset,
        request=request,
        applied_changes=applied_changes,
    )
    updated_asset = _mark_asset_applied(
        asset,
        employee_id=normalized_employee_id,
        request=request,
        applied_changes=applied_changes,
        ticket_report_id=ticket_report_id,
        timestamp=timestamp,
        workspace_dir=workspace,
    )
    status = "applied" if any(applied_changes.values()) else "already_applied"
    return EmployeeImprovementApplyResponse(
        employee_id=normalized_employee_id,
        asset_id=asset.id,
        status=status,
        detail=_application_detail(status),
        applied_changes=applied_changes,
        profile=profile,
        asset=updated_asset,
        ticket_report_id=ticket_report_id,
        saved_paths={
            "employee_profile": _relative(profile_path, workspace_dir=workspace),
            "asset_records": _relative(asset_records_path(workspace), workspace_dir=workspace),
            **({"ticket_report": ticket_report_id} if ticket_report_id else {}),
        },
    )


def _validate_employee_improvement_asset(asset: AssetRecord, employee_id: str) -> None:
    if asset.asset_type.strip().lower() != "employee_improvement":
        raise ValueError("Only employee_improvement AssetRecords can be applied to Employee profiles.")
    if asset.status.strip().lower() not in {"approved", "accepted", "validated"}:
        raise ValueError("Only approved, accepted, or validated Employee improvement AssetRecords can be applied.")
    if asset.review_state.strip().lower() not in {"approved", "accepted", "validated"}:
        raise ValueError("Employee improvement AssetRecord must pass Asset Review before application.")
    if asset.scope_kind.strip().lower() == "employee" and asset.scope_ref.strip().lower() == employee_id.lower():
        return
    for relationship in asset.relationships:
        if not isinstance(relationship, dict):
            continue
        if (
            str(relationship.get("type") or "").strip() == "improves_employee"
            and str(relationship.get("target_kind") or "").strip().lower() == "employee"
            and str(relationship.get("target_ref") or "").strip().lower() == employee_id.lower()
        ):
            return
    raise ValueError("Employee improvement AssetRecord does not target this Employee.")


def _proposed_profile_updates(asset: AssetRecord) -> dict[str, list[str]]:
    raw = asset.provenance.get("proposed_profile_updates")
    if not isinstance(raw, dict):
        return {"skill_refs": [], "memory_scopes": [], "capability_tags": [], "personality_tags": []}
    return {
        "skill_refs": _string_items(raw.get("skill_refs")),
        "memory_scopes": _string_items(raw.get("memory_scopes")),
        "capability_tags": _string_items(raw.get("capability_tags")),
        "personality_tags": _string_items(raw.get("personality_tags")),
    }


def _apply_allowlisted_profile_updates(profile: dict[str, Any], updates: dict[str, list[str]]) -> dict[str, list[str]]:
    applied: dict[str, list[str]] = {}
    for field in ("skill_refs", "memory_scopes", "capability_tags", "personality_tags"):
        added: list[str] = []
        for value in updates.get(field, []):
            if _append_unique_string(profile, field, value):
                added.append(value)
        applied[field] = added
    return applied


def _mark_asset_applied(
    asset: AssetRecord,
    *,
    employee_id: str,
    request: EmployeeImprovementApplyRequest,
    applied_changes: dict[str, list[str]],
    ticket_report_id: str,
    timestamp: str,
    workspace_dir: Path,
) -> AssetRecord:
    actor_employee_id = request.actor_employee_id.strip() or "clara"
    application = {
        "status": "applied",
        "employee_id": employee_id,
        "applied_by_employee_id": actor_employee_id,
        "applied_at": timestamp,
        "reason": request.reason.strip(),
        "application_note": request.application_note.strip(),
        "applied_changes": applied_changes,
        "ticket_report_id": ticket_report_id,
    }
    updated = asset.model_copy(
        update={
            "provenance": {
                **asset.provenance,
                "employee_improvement_application": application,
                "employee_improvement_applied_at": timestamp,
                "employee_improvement_applied_by": actor_employee_id,
            },
            "relationships": _ensure_applied_relationship(asset.relationships, employee_id),
            "updated_at": timestamp,
        }
    )
    return upsert_asset_record(updated, workspace_dir=workspace_dir)


def _record_ticket_application_report(
    *,
    employee_id: str,
    asset: AssetRecord,
    request: EmployeeImprovementApplyRequest,
    applied_changes: dict[str, list[str]],
) -> str:
    source_ticket_id = _source_ticket_id(asset)
    if not source_ticket_id:
        return ""
    try:
        from .ticket_service import TicketReportRequest, add_ticket_report

        ticket = add_ticket_report(
            source_ticket_id,
            TicketReportRequest(
                reporter_employee_id=request.actor_employee_id.strip() or "clara",
                reporter_role="AI Team OS Manager",
                content=_ticket_report_content(employee_id, asset, request, applied_changes),
                evidence=[f"asset:{asset.id}"],
                report_type="employee_improvement_applied",
            ),
        )
    except Exception:
        return ""
    reports = [report for report in ticket.reports if report.report_type == "employee_improvement_applied"]
    return reports[-1].id if reports else ""


def _ticket_report_content(
    employee_id: str,
    asset: AssetRecord,
    request: EmployeeImprovementApplyRequest,
    applied_changes: dict[str, list[str]],
) -> str:
    changes = [
        f"{field}: {', '.join(values)}"
        for field, values in applied_changes.items()
        if values
    ]
    lines = [
        f"Applied approved Employee improvement Asset {asset.id} to {employee_id}.",
        f"Reason: {request.reason.strip() or 'Approved improvement asset application.'}",
    ]
    if request.application_note.strip():
        lines.append(f"Note: {request.application_note.strip()}")
    lines.append(f"Applied changes: {'; '.join(changes) if changes else 'profile already contained proposed updates'}")
    return "\n".join(lines)


def _source_ticket_id(asset: AssetRecord) -> str:
    provenance = asset.provenance if isinstance(asset.provenance, dict) else {}
    ticket_id = str(provenance.get("source_ticket_id") or "").strip()
    if ticket_id:
        return ticket_id
    for relationship in asset.relationships:
        if not isinstance(relationship, dict):
            continue
        if str(relationship.get("target_kind") or "").strip().lower() == "ticket":
            return str(relationship.get("target_ref") or "").strip()
    return asset.scope_ref if asset.scope_kind == "ticket" else ""


def _ensure_applied_relationship(relationships: list[dict[str, Any]], employee_id: str) -> list[dict[str, Any]]:
    existing = [
        item
        for item in relationships
        if isinstance(item, dict)
        and str(item.get("type") or "").strip() == "applied_to_employee"
        and str(item.get("target_ref") or "").strip().lower() == employee_id.lower()
    ]
    if existing:
        return relationships
    return [
        *relationships,
        {
            "type": "applied_to_employee",
            "target_kind": "employee",
            "target_ref": employee_id,
            "reason": "Approved Employee improvement Asset was applied to this Employee profile.",
        },
    ]


def _append_unique_string(profile: dict[str, Any], field: str, value: str) -> bool:
    item = str(value).strip()
    if not item:
        return False
    current = profile.get(field)
    values = [str(existing).strip() for existing in current if str(existing).strip()] if isinstance(current, list) else []
    if item.lower() in {existing.lower() for existing in values}:
        profile[field] = values
        return False
    profile[field] = [*values, item]
    return True


def _append_unique_ref(profile: dict[str, Any], field: str, ref: dict[str, Any], key: str) -> bool:
    ref_value = str(ref.get(key) or "").strip()
    if not ref_value:
        return False
    current = profile.get(field)
    values = [item for item in current if isinstance(item, dict)] if isinstance(current, list) else []
    if any(str(item.get(key) or "").strip() == ref_value for item in values):
        profile[field] = values
        return False
    profile[field] = [*values, ref]
    return True


def _application_detail(status: str) -> str:
    if status == "applied":
        return "Approved Employee improvement Asset was applied through the governed Employee profile boundary."
    return "Approved Employee improvement Asset had already been applied or proposed updates were already present."


def _read_profile(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read Employee profile: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid Employee profile: {path.name}")
    return payload


def _write_profile(path: Path, profile: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _employee_profile_path(employee_id: str, *, workspace_dir: Path) -> Path:
    safe = "".join(char for char in employee_id.strip().lower() if char.isalnum() or char in {"_", "-"})
    if not safe:
        raise ValueError("Employee id is invalid.")
    return workspace_dir / "employees" / f"{safe}.yaml"


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    items: list[str] = []
    for item in value:
        text = str(item).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        items.append(text)
    return items


def _workspace_root(workspace_dir: Path | None = None) -> Path:
    if workspace_dir is not None:
        resolved = workspace_dir.resolve()
        return resolved.parent if resolved.name == ".aiteamos" else resolved
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _workspace_dir(workspace_dir: Path | None = None) -> Path:
    explicit = workspace_dir.resolve() if workspace_dir is not None else None
    if explicit is not None and explicit.name == ".aiteamos":
        path = explicit
    else:
        path = _workspace_root(workspace_dir) / ".aiteamos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _relative(path: Path, *, workspace_dir: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root(workspace_dir)))
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(UTC).isoformat()
