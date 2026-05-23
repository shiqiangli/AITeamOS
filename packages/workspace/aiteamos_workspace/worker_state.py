from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import json

from .io import read_jsonl, read_yaml, write_text, write_yaml
from .loader import load_workspace
from .run_events import append_run_event_record


ACTIVE_WORKER_STATUSES = {"QUEUED", "RUNNING", "TESTING", "RECOVERING"}
DEFAULT_HEARTBEAT_LEASE_SECONDS = 300


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def heartbeat_payload(
    worker: dict[str, Any] | None = None,
    *,
    stage: str | None = None,
    lease_seconds: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(worker or {})
    if stage:
        payload["stage"] = stage
    if extra:
        payload.update(extra)
    payload["heartbeatAt"] = now_iso()
    payload["leaseSeconds"] = int(lease_seconds or payload.get("leaseSeconds") or DEFAULT_HEARTBEAT_LEASE_SECONDS)
    return payload


def touch_worker_heartbeat(
    workspace_path: str | Path,
    run_id: str,
    *,
    stage: str | None = None,
    lease_seconds: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run_dir = index.workspace_root / "runs" / run_id
    run_path = run_dir / "run.yaml"
    data = read_yaml(run_path)
    spec = data.setdefault("spec", {})
    worker = heartbeat_payload(
        spec.get("worker") or {},
        stage=stage,
        lease_seconds=lease_seconds,
        extra=extra,
    )
    spec["worker"] = worker
    write_yaml(run_path, data)
    _append_event(index.workspace_root, run_id, {"type": "worker.heartbeat", "stage": worker.get("stage"), "heartbeatAt": worker["heartbeatAt"]})
    return worker


def reconcile_worker_leases(workspace_path: str | Path) -> list[str]:
    index = load_workspace(workspace_path)
    stalled: list[str] = []
    for run_id, run in index.runs.items():
        if run.spec.status not in ACTIVE_WORKER_STATUSES:
            continue
        worker = run.model_dump(mode="json").get("spec", {}).get("worker") or {}
        if not worker_lease_expired(worker):
            continue
        run_path = index.workspace_root / "runs" / run_id / "run.yaml"
        data = read_yaml(run_path)
        spec = data.setdefault("spec", {})
        previous_status = spec.get("status")
        worker_data = dict(spec.get("worker") or {})
        worker_data["stage"] = "stalled"
        worker_data["previousStatus"] = previous_status
        worker_data["stalledAt"] = now_iso()
        spec["status"] = "STALLED"
        spec["worker"] = worker_data
        write_yaml(run_path, data)
        _mark_task_status(index.workspace_root, run.spec.task, "STALLED")
        _append_event(
            index.workspace_root,
            run_id,
            {
                "type": "worker.stalled",
                "previousStatus": previous_status,
                "heartbeatAt": worker_data.get("heartbeatAt"),
                "leaseSeconds": worker_data.get("leaseSeconds"),
            },
        )
        stalled.append(run_id)
    return stalled


def worker_lease_expired(worker: dict[str, Any]) -> bool:
    heartbeat_at = worker.get("heartbeatAt")
    if not heartbeat_at:
        return False
    heartbeat = _parse_time(str(heartbeat_at))
    if not heartbeat:
        return False
    try:
        lease_seconds = int(worker.get("leaseSeconds") or DEFAULT_HEARTBEAT_LEASE_SECONDS)
    except (TypeError, ValueError):
        lease_seconds = DEFAULT_HEARTBEAT_LEASE_SECONDS
    return datetime.now().astimezone() > heartbeat + timedelta(seconds=max(1, lease_seconds))


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _mark_task_status(workspace_root: Path, task_id: str, status: str) -> None:
    task_path = workspace_root / "tasks" / f"{task_id}.yaml"
    if not task_path.exists():
        return
    task = read_yaml(task_path)
    task.setdefault("spec", {})["status"] = status
    write_yaml(task_path, task)


def _append_event(workspace_root: Path, run_id: str, event: dict[str, Any]) -> None:
    append_run_event_record(workspace_root, run_id, event)
