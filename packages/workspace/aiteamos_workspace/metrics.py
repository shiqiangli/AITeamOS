from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json

from .costs import summarize_model_costs
from .indexer import default_index_metadata_path
from .loader import WorkspaceIndex, load_workspace


def render_prometheus_metrics(workspace_or_index: str | Path | WorkspaceIndex) -> str:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    lines: list[str] = []
    _append_run_state_metrics(lines, index)
    _append_model_cost_metrics(lines, index)
    _append_index_rebuild_metrics(lines, index)
    _append_worker_heartbeat_metrics(lines, index)
    return "\n".join(lines) + "\n"


def _append_run_state_metrics(lines: list[str], index: WorkspaceIndex) -> None:
    _append_help(lines, "aiteamos_run_state_total", "Current number of Run manifests grouped by state.")
    _append_type(lines, "aiteamos_run_state_total", "gauge")
    counts: dict[str, int] = {}
    for run in index.runs.values():
        state = str(run.spec.status or "UNKNOWN").upper()
        counts[state] = counts.get(state, 0) + 1
    for state, count in sorted(counts.items()):
        _append_sample(lines, "aiteamos_run_state_total", count, {"state": state})
    if not counts:
        _append_sample(lines, "aiteamos_run_state_total", 0, {"state": "NONE"})


def _append_model_cost_metrics(lines: list[str], index: WorkspaceIndex) -> None:
    _append_help(lines, "aiteamos_model_call_cost_usd_total", "Cumulative model call cost recorded in run event ledgers.")
    _append_type(lines, "aiteamos_model_call_cost_usd_total", "counter")
    rows = summarize_model_costs(index)["byModel"]
    if not rows:
        _append_sample(
            lines,
            "aiteamos_model_call_cost_usd_total",
            0.0,
            {"provider": "unknown", "model": "unknown"},
        )
        return
    for row in sorted(rows, key=lambda item: (item["provider"], item["model"])):
        _append_sample(
            lines,
            "aiteamos_model_call_cost_usd_total",
            row["costUsd"],
            {"provider": row["provider"], "model": row["model"]},
        )


def _append_index_rebuild_metrics(lines: list[str], index: WorkspaceIndex) -> None:
    _append_help(lines, "aiteamos_index_rebuild_seconds", "Duration in seconds of the most recent workspace index rebuild.")
    _append_type(lines, "aiteamos_index_rebuild_seconds", "gauge")
    metadata = _read_index_metadata(index)
    _append_sample(lines, "aiteamos_index_rebuild_seconds", float(metadata.get("lastRebuildDurationSeconds") or 0.0))


def _append_worker_heartbeat_metrics(lines: list[str], index: WorkspaceIndex) -> None:
    _append_help(lines, "aiteamos_worker_heartbeat_lag_seconds", "Seconds since the latest worker heartbeat for each run.")
    _append_type(lines, "aiteamos_worker_heartbeat_lag_seconds", "gauge")
    now = datetime.now().astimezone()
    emitted = False
    for run_id, run in sorted(index.runs.items()):
        worker = run.model_dump(mode="json").get("spec", {}).get("worker")
        if not isinstance(worker, dict):
            continue
        heartbeat_at = _parse_time(str(worker.get("heartbeatAt") or ""))
        if heartbeat_at is None:
            continue
        lag_seconds = max(0.0, (now - heartbeat_at).total_seconds())
        _append_sample(
            lines,
            "aiteamos_worker_heartbeat_lag_seconds",
            round(lag_seconds, 3),
            {
                "run": run_id,
                "member": run.spec.member,
                "assignment": run.spec.assignment or "",
                "status": str(run.spec.status or "UNKNOWN").upper(),
                "stage": str(worker.get("stage") or ""),
            },
        )
        emitted = True
    if not emitted:
        _append_sample(
            lines,
            "aiteamos_worker_heartbeat_lag_seconds",
            0.0,
            {"run": "none", "member": "", "assignment": "", "status": "idle", "stage": ""},
        )


def _read_index_metadata(index: WorkspaceIndex) -> dict[str, Any]:
    metadata_path = default_index_metadata_path(index.workspace_root)
    if not metadata_path.exists():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_help(lines: list[str], name: str, description: str) -> None:
    lines.append(f"# HELP {name} {description}")


def _append_type(lines: list[str], name: str, metric_type: str) -> None:
    lines.append(f"# TYPE {name} {metric_type}")


def _append_sample(lines: list[str], name: str, value: int | float, labels: dict[str, str] | None = None) -> None:
    label_text = ""
    if labels:
        label_text = "{" + ",".join(f'{key}="{_escape_label(value)}"' for key, value in labels.items()) + "}"
    lines.append(f"{name}{label_text} {_format_value(value)}")


def _escape_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_value(value: int | float) -> str:
    if isinstance(value, int):
        return str(value)
    return f"{float(value):.8f}".rstrip("0").rstrip(".") or "0"


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed
