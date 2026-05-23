from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import os
import re

from .artifacts import record_artifact_manifest
from .commands import has_verification_failure, run_verification_commands
from .executor import (
    _append_event,
    _maybe_propose_memory,
    call_model_with_prompt,
    worker_patch_prompt,
)
from .gitops import (
    apply_patch,
    branch_url,
    commit_worker_changes,
    create_pull_request,
    diff_worktree,
    ensure_worktree,
    validate_patch_permissions,
    validate_patch_scope,
)
from .io import read_text_if_exists, read_yaml, write_text, write_yaml
from .loader import load_workspace
from .locks import lock_status, workspace_lock
from .model_policy import evaluate_model_policy, estimate_tokens, model_policy_event
from .mutations import update_run, update_task
from .worker_readiness import evaluate_worker_readiness
from .worker_state import heartbeat_payload, touch_worker_heartbeat


def execute_worker_run(workspace_path: str | Path, run_id: str, *, create_pr: bool = False) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    start_gate = evaluate_worker_readiness(index, run_id)
    if not start_gate["ready"]:
        _append_event(index.workspace_root, run_id, {"type": "worker.start.blocked", "blockers": start_gate["blockers"], "checks": start_gate["checks"]})
        raise ValueError(start_gate["summary"])

    lock_name = f"run-{run_id}"
    initial_run = index.runs[run_id]
    initial_worker = initial_run.model_dump(mode="json").get("spec", {}).get("worker") or {}
    lock_metadata = {"run": run_id, "attemptId": initial_worker.get("attemptId"), "owner": "managed-worker"}
    try:
        lock_context = workspace_lock(index.workspace_root, lock_name, lock_metadata)
        lock_context.__enter__()
    except RuntimeError as exc:
        _append_event(index.workspace_root, run_id, {"type": "worker.locked", "error": str(exc), "lock": lock_status(index.workspace_root, lock_name)})
        raise
    try:
        index = load_workspace(workspace_path)
        run = index.runs[run_id]
        if not run.spec.modelProfile:
            raise ValueError(f"run {run_id} has no modelProfile")
        context = index.run_context_capsules.get(run_id)
        if not context:
            raise ValueError(f"run {run_id} has no context capsule")
        policy_decision = evaluate_model_policy(index, run_id, estimated_input_tokens=estimate_tokens(context))
        if not policy_decision["ready"]:
            _append_event(index.workspace_root, run_id, {"type": "model.policy.blocked", **model_policy_event(policy_decision)})
            raise ValueError(policy_decision["summary"])
        profile = index.model_profiles[policy_decision["profile"]]
        worker_options = _worker_options(run)
        worker_options["attemptId"] = worker_options.get("attemptId") or _attempt_id(run_id)
        worker_options["ownerPid"] = os.getpid()

        update_run(workspace_path, run_id, {"status": "RUNNING", "worker": heartbeat_payload(worker_options, stage="starting")})
        update_task(workspace_path, run.spec.task, {"status": "RUNNING"})
        _append_event(index.workspace_root, run_id, {"type": "worker.started", "attemptId": worker_options["attemptId"], "ownerPid": os.getpid()})

        try:
            worktree = ensure_worktree(workspace_path, run_id)
            touch_worker_heartbeat(workspace_path, run_id, stage="worktree-ready", extra={"worktree": str(worktree)})
            _append_event(index.workspace_root, run_id, {"type": "worker.worktree.ready", "worktree": str(worktree)})

            touch_worker_heartbeat(workspace_path, run_id, stage="model-call")
            prompt = worker_patch_prompt(f"{context}\n\nWorktree: `{worktree}`")
            _append_event(
                index.workspace_root,
                run_id,
                {
                    "type": "model.call.started",
                    "provider": profile.spec.provider,
                    "model": profile.spec.model,
                    "policy": policy_decision.get("policy"),
                    "estimatedInputTokens": policy_decision["estimates"]["inputTokens"],
                },
            )
            try:
                result = call_model_with_prompt(profile, prompt)
            except Exception as exc:
                _append_event(
                    index.workspace_root,
                    run_id,
                    {
                        "type": "model.call.failed",
                        "provider": profile.spec.provider,
                        "model": profile.spec.model,
                        "error": str(exc),
                    },
                )
                raise
            worker_output_path = _append_worker_output(index.workspace_root, run_id, result.text, profile.spec.provider, profile.spec.model)
            worker_output_manifest = record_artifact_manifest(
                index.workspace_root,
                run_id,
                "worker_output",
                worker_output_path,
                source_id="worker-output",
                extra={"provider": profile.spec.provider, "model": profile.spec.model},
            )
            _record_output(
                workspace_path,
                run_id,
                {
                    "type": "worker_output",
                    "path": worker_output_path,
                    "provider": profile.spec.provider,
                    "model": profile.spec.model,
                    "artifactManifest": worker_output_manifest,
                },
            )
            touch_worker_heartbeat(workspace_path, run_id, stage="model-completed")
            _append_event(
                index.workspace_root,
                run_id,
                {
                    "type": "model.call.completed",
                    "provider": result.provider,
                    "model": result.model,
                    "responseId": result.response_id,
                    "status": result.status,
                    "usage": result.usage or {},
                    "policy": policy_decision.get("policy"),
                },
            )
            _append_event(index.workspace_root, run_id, {"type": "worker.model.completed", "provider": profile.spec.provider, "model": profile.spec.model})

            diff_text = _extract_diff_block(result.text)
            if diff_text:
                latest_index = load_workspace(workspace_path)
                violations = validate_patch_scope(latest_index, run_id, diff_text)
                if violations:
                    raise ValueError("patch scope violations: " + "; ".join(violations))
                permission_violations, permission_decisions = validate_patch_permissions(latest_index, run_id, diff_text)
                if permission_decisions:
                    _append_event(index.workspace_root, run_id, {"type": "worker.patch.permission.checked", "decisions": permission_decisions})
                if permission_violations:
                    raise ValueError("patch permission violations: " + "; ".join(permission_violations))
                applied = apply_patch(worktree, diff_text)
                if applied.returncode != 0:
                    raise ValueError(f"git apply failed: {applied.stderr or applied.stdout}")
                touch_worker_heartbeat(workspace_path, run_id, stage="patch-applied")
                _append_event(index.workspace_root, run_id, {"type": "worker.patch.applied"})

            worktree_diff = diff_worktree(worktree)
            if worktree_diff:
                diff_path = f"runs/{run_id}/diff.patch"
                write_text(index.workspace_root / "runs" / run_id / "diff.patch", worktree_diff)
                diff_manifest = record_artifact_manifest(index.workspace_root, run_id, "diff_patch", diff_path, source_id="worker-diff")
                _record_output(workspace_path, run_id, {"type": "diff_patch", "path": diff_path, "artifactManifest": diff_manifest})
                touch_worker_heartbeat(workspace_path, run_id, stage="diff-created")
                _append_event(index.workspace_root, run_id, {"type": "worker.diff.created", "path": diff_path})
            if worker_options["verificationCommands"]:
                update_run(
                    workspace_path,
                    run_id,
                    {
                        "status": "TESTING",
                        "worker": {
                            **worker_options,
                            "stage": "testing",
                            "worktree": str(worktree),
                        },
                    },
                )
                update_task(workspace_path, run.spec.task, {"status": "TESTING"})
                results = run_verification_commands(
                    workspace_path,
                    run_id,
                    worktree=worktree,
                    commands=worker_options["verificationCommands"],
                    timeout_seconds=worker_options["commandTimeoutSeconds"],
                )
                if has_verification_failure(results):
                    raise ValueError("worker verification failed; inspect runs/%s/test.log" % run_id)

            if worktree_diff:
                touch_worker_heartbeat(workspace_path, run_id, stage="commit")
                commit = commit_worker_changes(workspace_path, run_id, f"AITEAMOS {run.spec.task}: {index.tasks[run.spec.task].spec.title}")
                _append_event(index.workspace_root, run_id, {"type": "worker.commit", **commit})
                if create_pr:
                    target = create_pull_request(workspace_path, run_id)
                else:
                    target = {
                        "type": "branch",
                        "url": branch_url(worktree, run.spec.branch.name if run.spec.branch else run_id),
                        "ref": run.spec.branch.name if run.spec.branch else run_id,
                        "description": "Worker changes committed locally; create PR when ready.",
                    }
                    update_run(workspace_path, run_id, {"reviewTarget": target})
                    _record_output(workspace_path, run_id, {"type": "review_target", "target": target})
            else:
                touch_worker_heartbeat(workspace_path, run_id, stage="diff-empty")
                _append_event(index.workspace_root, run_id, {"type": "worker.diff.empty"})

            _maybe_propose_memory(workspace_path, run_id, result.text)
            final_updates: dict[str, Any] = {
                "status": "REVIEW",
                "worker": {**worker_options, "stage": "review", "worktree": str(worktree), "finishedAt": _now()},
            }
            latest_run = load_workspace(workspace_path).runs[run_id]
            if not worktree_diff and not latest_run.spec.reviewTarget:
                target = {
                    "type": "external_review",
                    "ref": worker_output_path,
                    "description": "Managed worker produced no diff; review the worker output artifact.",
                }
                final_updates["reviewTarget"] = target
                _record_output(workspace_path, run_id, {"type": "review_target", "target": target})
            update_run(workspace_path, run_id, final_updates)
            update_task(workspace_path, run.spec.task, {"status": "REVIEW"})
            return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")
        except Exception as exc:
            _append_event(index.workspace_root, run_id, {"type": "worker.failed", "error": str(exc)})
            update_run(workspace_path, run_id, {"status": "FAILED", "worker": {**worker_options, "stage": "failed", "error": str(exc), "finishedAt": _now()}})
            update_task(workspace_path, run.spec.task, {"status": "FAILED"})
            raise
    finally:
        lock_context.__exit__(None, None, None)


def _extract_diff_block(text: str) -> str | None:
    match = re.search(r"```(?:diff|patch)\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return None
    diff = match.group(1).strip("\r\n")
    if diff and not diff.endswith("\n"):
        diff += "\n"
    return diff if diff.startswith("diff --git") or "\n+++" in diff else None


def _append_worker_output(workspace_root: Path, run_id: str, text: str, provider: str, model: str) -> str:
    run_dir = workspace_root / "runs" / run_id
    output_path = run_dir / "worker_output.md"
    journal_path = run_dir / "journal.md"
    previous = read_text_if_exists(journal_path) or f"# {run_id} Journal\n"
    now = _now()
    output = f"""# Managed Worker Result

Generated: `{now}`
Provider: `{provider}`
Model: `{model}`

{text}
"""
    write_text(output_path, output)
    section = f"""

## Managed Worker Result ({now})

Provider: `{provider}`
Model: `{model}`

{text}
"""
    write_text(journal_path, previous.rstrip() + section)
    return f"runs/{run_id}/worker_output.md"


def _record_output(workspace_path: str | Path, run_id: str, output: dict[str, Any]) -> None:
    index = load_workspace(workspace_path)
    path = index.workspace_root / "runs" / run_id / "run.yaml"
    data = read_yaml(path)
    outputs = data.setdefault("spec", {}).setdefault("outputs", [])
    outputs[:] = [
        item
        for item in outputs
        if not (isinstance(item, dict) and item.get("type") == output.get("type") and item.get("path") == output.get("path"))
    ]
    outputs.append(output)
    write_yaml(path, data)


def _worker_options(run: Any) -> dict[str, Any]:
    data = run.model_dump(mode="json").get("spec", {}).get("worker") or {}
    commands = data.get("verificationCommands") or data.get("testCommands") or []
    if isinstance(commands, str):
        commands = [line.strip() for line in commands.splitlines() if line.strip()]
    commands = [str(command).strip() for command in commands if str(command).strip()]
    timeout = data.get("commandTimeoutSeconds") or data.get("timeoutSeconds") or 120
    try:
        timeout_seconds = int(timeout)
    except (TypeError, ValueError):
        timeout_seconds = 120
    timeout_seconds = max(1, min(timeout_seconds, 1800))
    heartbeat_lease = data.get("heartbeatLeaseSeconds") or data.get("leaseSeconds") or max(300, timeout_seconds + 60)
    try:
        heartbeat_lease_seconds = int(heartbeat_lease)
    except (TypeError, ValueError):
        heartbeat_lease_seconds = max(300, timeout_seconds + 60)
    heartbeat_lease_seconds = max(10, min(heartbeat_lease_seconds, 3600))
    return {
        **_preserved_worker_fields(data),
        "verificationCommands": commands,
        "commandTimeoutSeconds": timeout_seconds,
        "heartbeatLeaseSeconds": heartbeat_lease_seconds,
        "leaseSeconds": heartbeat_lease_seconds,
    }


def _preserved_worker_fields(data: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "attemptId",
        "createPr",
        "queuedAt",
        "recoveredAt",
        "recoveryReason",
        "previousAttemptId",
    ]
    return {key: data[key] for key in keys if key in data}


def _attempt_id(run_id: str) -> str:
    compact = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f")[:-3]
    return f"{run_id}-ATTEMPT-{compact}"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
