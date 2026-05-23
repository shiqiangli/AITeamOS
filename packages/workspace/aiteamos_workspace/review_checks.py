from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json

from .git_provider import ReviewTargetRef
from .gitops import default_git_provider, repository_ref
from .io import read_jsonl, read_yaml, write_text, write_yaml
from .loader import load_workspace
from .run_events import append_run_event_record


def refresh_run_checks(workspace_path: str | Path, run_id: str) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    target = run.spec.reviewTarget.model_dump(mode="json", exclude_none=True) if run.spec.reviewTarget else None
    payload = {"run": run_id, **_collect_checks(index, target)}
    run_dir = index.workspace_root / "runs" / run_id
    write_text(run_dir / "checks.json", json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    _record_output(index.workspace_root, run_id, {"type": "check_status", "path": f"runs/{run_id}/checks.json", "status": payload["status"]})
    _append_event(index.workspace_root, run_id, {"type": "checks.refreshed", "status": payload["status"], "source": payload["source"]})
    return payload


def _collect_checks(index: Any, target: dict[str, Any] | None) -> dict[str, Any]:
    now = datetime.now().astimezone().isoformat(timespec="milliseconds")
    if not target or target.get("type") != "pull_request" or not target.get("url"):
        return {
            "generatedAt": now,
            "source": "review-target",
            "status": "not_applicable",
            "summary": "Review target is not a pull request; external checks were not refreshed.",
            "target": target,
            "checks": [],
        }
    result = default_git_provider().pull_request_checks(repository_ref(index), _review_target_ref(target))
    return {
        "generatedAt": now,
        "source": result.source,
        "status": result.status,
        "summary": result.summary,
        "target": target,
        "checks": result.checks,
    }


def _review_target_ref(target: dict[str, Any]) -> ReviewTargetRef:
    return ReviewTargetRef(
        type=str(target.get("type") or "pull_request"),
        ref=str(target.get("ref") or target.get("url") or ""),
        url=str(target.get("url") or "") or None,
        description=str(target.get("description") or "") or None,
        provider=str(target.get("provider") or "") or None,
        fallback_reason=str(target.get("fallbackReason") or "") or None,
    )


def _record_output(workspace_root: Path, run_id: str, output: dict[str, Any]) -> None:
    path = workspace_root / "runs" / run_id / "run.yaml"
    data = read_yaml(path)
    outputs = data.setdefault("spec", {}).setdefault("outputs", [])
    if output not in outputs:
        outputs.append(output)
    write_yaml(path, data)


def _append_event(workspace_root: Path, run_id: str, event: dict[str, Any]) -> None:
    append_run_event_record(workspace_root, run_id, event)
