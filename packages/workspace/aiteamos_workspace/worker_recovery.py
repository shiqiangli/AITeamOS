from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import shutil
import subprocess

from .gitops import diff_worktree
from .io import read_jsonl, read_yaml, write_text, write_yaml
from .loader import load_workspace
from .locks import lock_status
from .mutations import update_run, update_task
from .run_events import append_run_event_record
from .worker_authorization import validate_managed_worktree
from .worker_state import ACTIVE_WORKER_STATUSES


RECOVERABLE_STATUSES = {"STALLED", "FAILED", "INTERRUPTED"}


def inspect_worker_recovery(workspace_path: str | Path, run_id: str) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    report = _build_recovery_report(index, run_id)
    _write_recovery_report(index.workspace_root, run_id, report)
    _append_event(index.workspace_root, run_id, {"type": "worker.recovery.inspected", "recommendation": report["recommendation"]})
    return report


def move_worker_run_to_review(workspace_path: str | Path, run_id: str, reason: str | None = None) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    report = _build_recovery_report(index, run_id)
    if not report["reviewable"]:
        raise ValueError("run is not reviewable yet; no review target, diff.patch, or worktree diff is available")

    run_dir = index.workspace_root / "runs" / run_id
    generated_diff = _materialize_worktree_diff(report, run_dir)
    target = run.spec.reviewTarget.model_dump(mode="json", exclude_none=True) if run.spec.reviewTarget else None
    if not target and (generated_diff or (run_dir / "diff.patch").exists()):
        target = {"type": "diff_patch", "description": "Recovered run moved to review with a local diff.patch artifact."}
    elif not target and report.get("branch"):
        target = {"type": "branch", "ref": report["branch"], "description": "Recovered run moved to review using the recorded worker branch."}

    worker = dict(run.model_dump(mode="json").get("spec", {}).get("worker") or {})
    worker.update({"stage": "review-recovered", "recoveredAt": _now(), "recoveryReason": reason or "manual move to review"})
    updates: dict[str, Any] = {"status": "REVIEW", "worker": worker}
    if target:
        updates["reviewTarget"] = target
    update_run(workspace_path, run_id, updates)
    update_task(workspace_path, run.spec.task, {"status": "REVIEW"})
    report = _build_recovery_report(load_workspace(workspace_path), run_id)
    report["action"] = "move-to-review"
    report["reason"] = reason or "manual move to review"
    _write_recovery_report(index.workspace_root, run_id, report)
    _append_event(index.workspace_root, run_id, {"type": "worker.recovery.review", "reason": report["reason"], "target": target})
    return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")


def build_worker_retry_plan(workspace_path: str | Path, run_id: str, reason: str | None = None) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    report = _build_recovery_report(index, run_id)
    worker = dict(run.model_dump(mode="json").get("spec", {}).get("worker") or {})
    blockers = _retry_blockers(run, report)
    warnings = _retry_warnings(report)
    plan = {
        "generatedAt": _now(),
        "run": run_id,
        "task": run.spec.task,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "memberKind": run.spec.memberKind,
        "status": run.spec.status,
        "reason": reason or "manual retry planning",
        "previousAttemptId": worker.get("attemptId"),
        "retryable": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "resumeFromStage": _resume_stage(run.spec.status, worker),
        "preserveArtifacts": sorted(name for name, present in report["artifacts"].items() if present),
        "preserveWorktree": bool(report.get("worktreeExists")),
        "preserveContext": bool(run.spec.contextCapsule),
        "resetWorktree": False,
        "rebuildContext": False,
        "startNewAttempt": True,
        "expectedNextActions": _retry_steps(report),
    }
    _write_retry_plan(index.workspace_root, run_id, plan)
    _append_event(index.workspace_root, run_id, {"type": "worker.retry.plan", "retryable": plan["retryable"], "blockers": blockers})
    return plan


def prepare_worker_retry(workspace_path: str | Path, run_id: str, reason: str | None = None) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    if run.spec.status not in RECOVERABLE_STATUSES:
        raise ValueError(f"run {run_id} is {run.spec.status}; only stalled, failed, or interrupted runs can be retried")
    retry_plan = build_worker_retry_plan(workspace_path, run_id, reason=reason or "manual retry")
    if not retry_plan["retryable"]:
        raise ValueError("retry plan is blocked: " + "; ".join(retry_plan["blockers"]))
    worker = dict(run.model_dump(mode="json").get("spec", {}).get("worker") or {})
    previous_attempt = worker.get("attemptId")
    worker.update(
        {
            "stage": "recovering",
            "attemptId": _attempt_id(run_id),
            "previousAttemptId": previous_attempt,
            "retryPlan": f"runs/{run_id}/retry_plan.json",
            "retryPlanGeneratedAt": retry_plan["generatedAt"],
            "recoveredAt": _now(),
            "recoveryReason": reason or "manual retry",
        }
    )
    update_run(workspace_path, run_id, {"status": "RECOVERING", "worker": worker})
    update_task(workspace_path, run.spec.task, {"status": "RECOVERING"})
    report = _build_recovery_report(load_workspace(workspace_path), run_id)
    report["action"] = "retry-worker"
    report["reason"] = reason or "manual retry"
    _write_recovery_report(index.workspace_root, run_id, report)
    _append_event(index.workspace_root, run_id, {"type": "worker.recovery.retry", "reason": report["reason"]})
    return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")


def clear_stale_worker_lock(workspace_path: str | Path, run_id: str, reason: str | None = None) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    report = _build_recovery_report(index, run_id)
    lock = report["lock"]
    if not lock.get("held"):
        raise ValueError("no worker lock is held for this run")
    if lock.get("pidAlive") is not False:
        raise ValueError("worker lock is not proven stale; inspect the active process before clearing it")

    lock_dir = index.workspace_root / "locks" / f"run-{run_id}"
    reported_path = Path(str(lock.get("path") or lock_dir)).expanduser()
    if reported_path.resolve() != lock_dir.resolve():
        raise ValueError("worker lock path does not match the expected run lock")

    shutil.rmtree(lock_dir, ignore_errors=True)
    worker = dict(run.model_dump(mode="json").get("spec", {}).get("worker") or {})
    worker.update({"stage": "stale-lock-cleared", "lockClearedAt": _now(), "lockClearReason": reason or "manual stale lock clear"})
    updates: dict[str, Any] = {"worker": worker}
    if run.spec.status in ACTIVE_WORKER_STATUSES:
        updates["status"] = "STALLED"
        update_task(workspace_path, run.spec.task, {"status": "STALLED"})
    update_run(workspace_path, run_id, updates)
    _append_event(
        index.workspace_root,
        run_id,
        {
            "type": "worker.lock.cleared",
            "reason": reason or "manual stale lock clear",
            "lock": {key: lock.get(key) for key in ["attemptId", "pid", "pidAlive", "acquiredAt", "ageSeconds"]},
            "previousStatus": run.spec.status,
        },
    )
    report = _build_recovery_report(load_workspace(workspace_path), run_id)
    report["action"] = "clear-stale-lock"
    report["reason"] = reason or "manual stale lock clear"
    _write_recovery_report(index.workspace_root, run_id, report)
    return report


def _build_recovery_report(index: Any, run_id: str) -> dict[str, Any]:
    run = index.runs[run_id]
    run_data = run.model_dump(mode="json").get("spec", {})
    worker = run_data.get("worker") or {}
    run_dir = index.workspace_root / "runs" / run_id
    worktree_value = run_data.get("worktree") or worker.get("worktree")
    worktree = Path(worktree_value).expanduser() if worktree_value else None
    worktree_violations = validate_managed_worktree(index, run_id, worktree) if worktree else []
    worktree_exists = bool(worktree and worktree.exists())
    worktree_is_git = bool(not worktree_violations and worktree_exists and (worktree / ".git").exists())
    worktree_status = _git_status(worktree) if worktree_is_git and worktree else None
    worktree_diff = diff_worktree(worktree) if worktree_is_git and worktree else ""
    has_diff = (run_dir / "diff.patch").exists() or bool(worktree_diff.strip())
    has_review_target = bool(run.spec.reviewTarget)
    events = index.run_events.get(run_id) or read_jsonl(run_dir / (run.spec.eventLedger or "events.jsonl"))
    artifacts = {
        "journal": bool(index.run_journals.get(run_id)),
        "diffPatch": (run_dir / "diff.patch").exists(),
        "testLog": (run_dir / "test.log").exists(),
        "commandLog": (run_dir / "command_results.jsonl").exists(),
        "checks": (run_dir / "checks.json").exists(),
    }
    lock = lock_status(index.workspace_root, f"run-{run_id}")
    lock_stale = bool(lock.get("held") and lock.get("pidAlive") is False)
    lock_active_or_unknown = bool(lock.get("held") and lock.get("pidAlive") is not False)
    reviewable = bool(has_diff or has_review_target)
    retryable = bool(run.spec.status in RECOVERABLE_STATUSES and run.spec.modelProfile and run.spec.contextCapsule)
    if worktree_violations:
        recommendation = "manual-investigation"
    elif lock_stale:
        recommendation = "clear-stale-lock"
    elif lock_active_or_unknown:
        recommendation = "manual-investigation"
    else:
        recommendation = "move-to-review" if reviewable else "retry-worker" if retryable else "manual-investigation"
    return {
        "generatedAt": _now(),
        "run": run_id,
        "status": run.spec.status,
        "task": run.spec.task,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "memberKind": run.spec.memberKind,
        "worker": worker,
        "lock": lock,
        "lockStale": lock_stale,
        "worktree": str(worktree) if worktree else None,
        "worktreeExists": worktree_exists,
        "worktreeManaged": not worktree_violations,
        "worktreeViolations": worktree_violations,
        "worktreeIsGit": worktree_is_git,
        "worktreeStatus": worktree_status,
        "worktreeHasDiff": bool(worktree_diff.strip()),
        "branch": run.spec.branch.name if run.spec.branch else worker.get("branch"),
        "artifacts": artifacts,
        "lastEvent": events[-1] if events else None,
        "eventCount": len(events),
        "reviewable": reviewable,
        "retryable": retryable,
        "recommendation": recommendation,
        "actions": _actions(reviewable, retryable, lock_stale, lock_active_or_unknown, bool(worktree_violations)),
    }


def _actions(reviewable: bool, retryable: bool, lock_stale: bool, lock_active_or_unknown: bool, unsafe_worktree: bool) -> list[str]:
    if unsafe_worktree:
        return ["manual-investigation"]
    if lock_stale:
        return ["clear-stale-lock"]
    if lock_active_or_unknown:
        return ["manual-investigation"]
    actions: list[str] = []
    if reviewable:
        actions.append("move-to-review")
    if retryable:
        actions.append("retry-worker")
    if not actions:
        actions.append("manual-investigation")
    return actions


def _retry_blockers(run: Any, report: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if run.spec.status not in RECOVERABLE_STATUSES:
        blockers.append(f"run status {run.spec.status} is not retryable")
    lock = report.get("lock") or {}
    if lock.get("held"):
        blockers.append("worker lock is still held; clear a PID-proven stale lock or wait for the active worker")
    if report.get("worktreeViolations"):
        blockers.extend(report["worktreeViolations"])
    if not run.spec.modelProfile:
        blockers.append("run has no modelProfile")
    if not run.spec.contextCapsule:
        blockers.append("run has no context capsule")
    return blockers


def _retry_warnings(report: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if report.get("reviewable"):
        warnings.append("run already has a diff or review target; consider moving it to review before retrying")
    if report.get("worktreeHasDiff"):
        warnings.append("recorded worktree has uncommitted diff; retry will preserve it and may create additional changes")
    return warnings


def _retry_steps(report: dict[str, Any]) -> list[str]:
    steps = [
        "preserve existing run artifacts and event ledger",
        "start a new worker attempt id",
        "reuse the existing context capsule",
    ]
    if report.get("worktreeExists"):
        steps.append("reuse the recorded worktree without deleting files")
    else:
        steps.append("create or attach the managed worktree before model execution")
    steps.extend(["call the configured model profile", "run configured verification commands", "return to REVIEW only after diff/test artifacts are recorded"])
    return steps


def _resume_stage(status: str, worker: dict[str, Any]) -> str:
    stage = str(worker.get("stage") or "")
    if stage:
        return stage
    if status == "FAILED":
        return "failed"
    if status == "STALLED":
        return "stalled"
    return "interrupted"


def _materialize_worktree_diff(report: dict[str, Any], run_dir: Path) -> bool:
    worktree_value = report.get("worktree")
    if not worktree_value or not report.get("worktreeManaged", True):
        return False
    worktree = Path(worktree_value).expanduser()
    if not worktree.exists() or not (worktree / ".git").exists():
        return False
    diff_text = diff_worktree(worktree)
    if not diff_text.strip():
        return False
    write_text(run_dir / "diff.patch", diff_text)
    return True


def _write_recovery_report(workspace_root: Path, run_id: str, report: dict[str, Any]) -> None:
    run_dir = workspace_root / "runs" / run_id
    write_text(run_dir / "recovery_report.json", json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    run_path = run_dir / "run.yaml"
    data = read_yaml(run_path)
    outputs = data.setdefault("spec", {}).setdefault("outputs", [])
    output = {"type": "recovery_report", "path": f"runs/{run_id}/recovery_report.json", "recommendation": report["recommendation"]}
    if output not in outputs:
        outputs.append(output)
    write_yaml(run_path, data)


def _write_retry_plan(workspace_root: Path, run_id: str, plan: dict[str, Any]) -> None:
    run_dir = workspace_root / "runs" / run_id
    write_text(run_dir / "retry_plan.json", json.dumps(plan, sort_keys=True, indent=2, ensure_ascii=True) + "\n")
    run_path = run_dir / "run.yaml"
    data = read_yaml(run_path)
    outputs = data.setdefault("spec", {}).setdefault("outputs", [])
    output = {"type": "retry_plan", "path": f"runs/{run_id}/retry_plan.json", "retryable": plan["retryable"]}
    if output not in outputs:
        outputs.append(output)
    write_yaml(run_path, data)


def _git_status(worktree: Path | None) -> str | None:
    if not worktree:
        return None
    result = subprocess.run(["git", "status", "--porcelain"], cwd=worktree, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _append_event(workspace_root: Path, run_id: str, event: dict[str, Any]) -> None:
    append_run_event_record(workspace_root, run_id, event)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _attempt_id(run_id: str) -> str:
    compact = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f")[:-3]
    return f"{run_id}-ATTEMPT-{compact}"
