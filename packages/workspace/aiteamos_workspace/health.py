from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from aiteamos_schema import API_VERSION, WorkspaceHealth

from .indexer import default_index_metadata_path, default_vector_chunks_path
from .loader import WorkspaceIndex
from .worker_state import ACTIVE_WORKER_STATUSES, DEFAULT_HEARTBEAT_LEASE_SECONDS, worker_lease_expired


def workspace_health_v2(index: WorkspaceIndex) -> WorkspaceHealth:
    summary = workspace_health_counts(index.health)
    return WorkspaceHealth(
        issues=index.health,
        summary=summary,
        lastIndexDuration=_last_index_duration(index.workspace_root),
        manifestLoadFailures=_manifest_load_failures(index.health),
        vectorChunkCount=_vector_chunk_count(index.workspace_root),
        schemaVersionMismatch=index.workspace.spec.protocolVersion != API_VERSION,
        staleWorkerLeases=_stale_worker_leases(index),
    )


def workspace_health_counts(issues: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "issues": len(issues),
        "errors": sum(1 for issue in issues if issue.get("severity") == "error"),
        "warnings": sum(1 for issue in issues if issue.get("severity") == "warning"),
    }


def _last_index_duration(workspace_root: Path) -> float | None:
    metadata = _read_json(default_index_metadata_path(workspace_root))
    duration = metadata.get("lastRebuildDurationSeconds")
    if isinstance(duration, (int, float)):
        return float(duration)
    return None


def _manifest_load_failures(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        issue
        for issue in issues
        if issue.get("severity") == "error" and issue.get("kind") in {"manifest", "manifest_load", "schema", "workspace_layout"}
    ]


def _vector_chunk_count(workspace_root: Path) -> int:
    chunks = _read_json(default_vector_chunks_path(workspace_root))
    items = chunks.get("chunks")
    if isinstance(items, list):
        return len(items)
    counts = chunks.get("counts")
    if isinstance(counts, dict) and isinstance(counts.get("total"), int):
        return int(counts["total"])
    return 0


def _stale_worker_leases(index: WorkspaceIndex) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    for run_id, run in sorted(index.runs.items()):
        if str(run.spec.status).upper() not in ACTIVE_WORKER_STATUSES:
            continue
        worker = run.model_dump(mode="json").get("spec", {}).get("worker")
        if not isinstance(worker, dict) or not worker_lease_expired(worker):
            continue
        stale.append(
            {
                "run": run_id,
                "task": run.spec.task,
                "member": run.spec.member,
                "assignment": run.spec.assignment,
                "status": run.spec.status,
                "stage": worker.get("stage"),
                "heartbeatAt": worker.get("heartbeatAt"),
                "leaseSeconds": _lease_seconds(worker),
            }
        )
    return stale


def _lease_seconds(worker: dict[str, Any]) -> int:
    try:
        return int(worker.get("leaseSeconds") or DEFAULT_HEARTBEAT_LEASE_SECONDS)
    except (TypeError, ValueError):
        return DEFAULT_HEARTBEAT_LEASE_SECONDS


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
