from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import json

from aiteamos_schema import RunEvent

from .io import read_yaml, write_text


RUN_EVENT_RETENTION_DAYS = 180


def append_run_event_record(workspace_root: Path, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    run_dir = workspace_root / "runs" / run_id
    run_yaml = read_yaml(run_dir / "run.yaml")
    ledger_name = run_yaml.get("spec", {}).get("eventLedger") or "events.jsonl"
    return append_run_event_to_ledger(run_dir / ledger_name, run_yaml, event)


def append_run_event_to_ledger(ledger_path: Path, run_yaml: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    lines = []
    if ledger_path.exists():
        lines = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = build_run_event_payload(run_yaml, event, sequence=len(lines) + 1)
    lines.append(json.dumps(payload, sort_keys=True, ensure_ascii=True))
    write_text(ledger_path, "\n".join(lines) + "\n")
    return payload


def build_run_event_payload(run_yaml: dict[str, Any], event: dict[str, Any], *, sequence: int) -> dict[str, Any]:
    now = datetime.now().astimezone()
    spec = run_yaml.get("spec", {}) if isinstance(run_yaml.get("spec"), dict) else {}
    retained_until = spec.get("retainedUntil") or (now + timedelta(days=RUN_EVENT_RETENTION_DAYS)).isoformat(
        timespec="milliseconds"
    )
    payload = {
        "seq": sequence,
        "ts": now.isoformat(timespec="milliseconds"),
        "lifecycle": spec.get("lifecycle", "active"),
        "retainedUntil": retained_until,
        "exportPolicy": spec.get("exportPolicy", "manifest-only"),
        **event,
    }
    if isinstance(payload.get("decisionAudit"), dict):
        payload["decisionAudit"] = [payload["decisionAudit"]]
    return RunEvent.model_validate(payload).model_dump(mode="json", exclude_none=True)
