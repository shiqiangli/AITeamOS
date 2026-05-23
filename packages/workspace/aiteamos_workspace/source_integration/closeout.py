from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..audit import decision_audit_record
from ..gitops import branch_url
from ..loader import WorkspaceIndex, load_workspace
from ..locks import workspace_lock
from ..mutations import append_run_event, update_run
from ..worker_authorization import validate_branch_name
from .review_gate_bridge import (
    _command_error,
    _current_commit,
    _git,
    _has_non_fast_forward_blocker,
    _policy_refs,
    _source_integration_authority,
    _source_integration_decision_kind,
    evaluate_run_source_integration_gate,
)


def integrate_run_source_after_closeout(
    workspace_path: str | Path,
    run_id: str,
    *,
    actor: str,
    reason: str | None = None,
) -> dict[str, Any]:
    initial_index = load_workspace(workspace_path)
    if run_id not in initial_index.runs:
        raise KeyError(f"unknown run {run_id}")
    with workspace_lock(initial_index.workspace_root, f"source-integration-{run_id}", {"run": run_id, "actor": actor}):
        gate = evaluate_run_source_integration_gate(workspace_path, run_id, actor_member=actor)
        if gate["blockers"] or not gate["readyForSourceIntegration"]:
            raise ValueError("run is not ready for source integration: " + "; ".join(gate["blockers"] or [gate["summary"]]))

        index = load_workspace(workspace_path)
        run = index.runs[run_id]
        repo_path = Path(gate["repository"]).expanduser().resolve()
        source_branch = str(gate["sourceBranch"])
        worker_branch = str(gate["workerBranch"])
        before_sha = _current_commit(repo_path, source_branch)
        merge = _git(repo_path, "merge", "--ff-only", worker_branch)
        if merge.returncode != 0:
            raise ValueError(f"git merge --ff-only failed: {_command_error(merge)}")
        after_sha = _current_commit(repo_path, source_branch)
        actor_kind = index.members[actor].spec.kind if actor in index.members else None
        reason_text = reason or "manual dashboard source integration after reviewed run closeout"
        integrated_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        audit = decision_audit_record(
            index,
            decision_kind=_source_integration_decision_kind(actor_kind),
            decision="approved",
            actor_member=actor,
            authority=_source_integration_authority(actor_kind),
            reason=reason_text,
            source="run-source-integration",
            decided_at=integrated_at,
            policy_refs=_policy_refs(gate["permissionDecisions"]),
            evidence=[
                {"kind": "run", "run": run_id},
                {"kind": "task", "task": run.spec.task},
                {"kind": "review", "review": (run.spec.closeout or {}).get("latestReview")},
                {"kind": "repository", "path": str(repo_path), "sourceBranch": source_branch, "workerBranch": worker_branch},
            ],
            metadata={
                "gateStatus": gate["status"],
                "strategy": "local-fast-forward",
                "beforeSha": before_sha,
                "afterSha": after_sha,
            },
        )
        integration_record = {
            "status": "integrated",
            "integratedAt": integrated_at,
            "integratedByMember": actor,
            "integratedByMemberKind": actor_kind,
            "reason": reason_text,
            "strategy": "local-fast-forward",
            "repository": str(repo_path),
            "sourceBranch": source_branch,
            "workerBranch": worker_branch,
            "beforeSha": before_sha,
            "afterSha": after_sha,
            "changedPaths": gate["changedPaths"],
            "gate": {
                "status": gate["status"],
                "summary": gate["summary"],
                "warnings": gate["warnings"],
                "checks": gate["checks"],
            },
            "permissionDecisions": gate["permissionDecisions"],
            "decisionAudit": [audit],
        }
        update_run(workspace_path, run_id, {"sourceIntegration": integration_record})
        append_run_event(
            workspace_path,
            run_id,
            {
                "type": "run.source_integrated",
                "actorMember": actor,
                "actorMemberKind": actor_kind,
                "repository": str(repo_path),
                "sourceBranch": source_branch,
                "workerBranch": worker_branch,
                "beforeSha": before_sha,
                "afterSha": after_sha,
                "changedPaths": gate["changedPaths"],
                "decisionAudit": audit,
            },
        )
        return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")

def request_run_source_integration_remediation(
    workspace_path: str | Path,
    run_id: str,
    *,
    actor: str,
    reason: str | None = None,
) -> dict[str, Any]:
    initial_index = load_workspace(workspace_path)
    if run_id not in initial_index.runs:
        raise KeyError(f"unknown run {run_id}")
    if actor not in initial_index.members:
        raise KeyError(f"unknown source integration remediation actor member {actor}")

    with workspace_lock(initial_index.workspace_root, f"source-integration-remediation-{run_id}", {"run": run_id, "actor": actor}):
        gate = evaluate_run_source_integration_gate(workspace_path, run_id, actor_member=actor)
        if gate["readyForSourceIntegration"]:
            raise ValueError("run is ready for source integration; remediation is not required")
        if not _has_non_fast_forward_blocker(gate):
            raise ValueError("source integration remediation currently handles non-fast-forward blockers only")

        index = load_workspace(workspace_path)
        run = index.runs[run_id]
        source_integration = run.spec.sourceIntegration if isinstance(run.spec.sourceIntegration, dict) else {}
        if (
            source_integration.get("status") == "remediation-requested"
            and source_integration.get("strategy") == "conflict-resolution-worktree"
            and source_integration.get("conflictResolution")
        ):
            return run.model_dump(mode="json")

        repo_path = Path(str(gate["repository"])).expanduser().resolve()
        source_branch = str(gate.get("sourceBranch") or "")
        worker_branch = str(gate.get("workerBranch") or "")
        conflict_resolution = _prepare_conflict_resolution_worktree(index, run_id, repo_path, source_branch, worker_branch)
        remediation_branch = str(conflict_resolution["branch"])
        remediation_worktree = str(conflict_resolution["worktree"])
        conflict_files = list(conflict_resolution.get("conflictFiles") or [])
        merge_status = str(conflict_resolution["status"])
        actor_kind = index.members[actor].spec.kind
        reason_text = reason or "request conflict-resolution worktree because source branch can no longer fast-forward the worker branch"
        requested_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        target_url = branch_url(repo_path, remediation_branch) if remediation_branch else None
        remediation_target = {
            "type": "branch",
            "ref": remediation_branch,
            "url": target_url,
            "description": (
                f"Conflict-resolution branch for reconciling {worker_branch} after "
                f"{source_branch} advanced before source integration."
            ),
        }
        summary = (
            f"Conflict-resolution worktree is ready at {remediation_worktree} with "
            f"{len(conflict_files)} conflicted file(s)."
            if conflict_files
            else f"Conflict-resolution worktree is ready at {remediation_worktree}."
        )
        audit = decision_audit_record(
            index,
            decision_kind=_source_integration_decision_kind(actor_kind),
            decision="remediation-requested",
            actor_member=actor,
            authority=_source_integration_authority(actor_kind),
            reason=reason_text,
            source="run-source-integration-remediation",
            decided_at=requested_at,
            policy_refs=_policy_refs(gate["permissionDecisions"]),
            evidence=[
                {"kind": "run", "run": run_id},
                {"kind": "task", "task": run.spec.task},
                {"kind": "review", "review": (run.spec.closeout or {}).get("latestReview")},
                {"kind": "repository", "path": str(repo_path), "sourceBranch": source_branch, "workerBranch": worker_branch},
            ],
            metadata={
                "gateStatus": gate["status"],
                "strategy": "conflict-resolution-worktree",
                "blocker": "non-fast-forward",
                "remediationBranch": remediation_branch,
                "remediationWorktree": remediation_worktree,
                "mergeStatus": merge_status,
                "conflictFiles": conflict_files,
            },
        )
        remediation_record = {
            "run": run_id,
            "status": "remediation-requested",
            "summary": summary,
            "requestedAt": requested_at,
            "requestedByMember": actor,
            "requestedByMemberKind": actor_kind,
            "reason": reason_text,
            "strategy": "conflict-resolution-worktree",
            "repository": str(repo_path),
            "sourceBranch": source_branch,
            "workerBranch": worker_branch,
            "remediationBranch": remediation_branch,
            "remediationWorktree": remediation_worktree,
            "mergeStatus": merge_status,
            "baseSha": conflict_resolution.get("baseSha"),
            "sourceSha": conflict_resolution.get("sourceSha"),
            "workerSha": conflict_resolution.get("workerSha"),
            "conflictFiles": conflict_files,
            "conflictResolution": conflict_resolution,
            "changedPaths": gate["changedPaths"],
            "remediationReviewTarget": remediation_target,
            "gate": {
                "status": gate["status"],
                "summary": gate["summary"],
                "blockers": gate["blockers"],
                "warnings": gate["warnings"],
                "checks": gate["checks"],
            },
            "permissionDecisions": gate["permissionDecisions"],
            "decisionAudit": [audit],
        }
        update_run(workspace_path, run_id, {"sourceIntegration": remediation_record})
        append_run_event(
            workspace_path,
            run_id,
            {
                "type": "run.source_integration_remediation_requested",
                "actorMember": actor,
                "actorMemberKind": actor_kind,
                "repository": str(repo_path),
                "sourceBranch": source_branch,
                "workerBranch": worker_branch,
                "remediationBranch": remediation_branch,
                "remediationWorktree": remediation_worktree,
                "mergeStatus": merge_status,
                "conflictFiles": conflict_files,
                "conflictResolution": conflict_resolution,
                "changedPaths": gate["changedPaths"],
                "remediationReviewTarget": remediation_target,
                "decisionAudit": audit,
            },
        )
        return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")

def _prepare_conflict_resolution_worktree(
    index: WorkspaceIndex,
    run_id: str,
    repo_path: Path,
    source_branch: str,
    worker_branch: str,
) -> dict[str, Any]:
    if not source_branch or not worker_branch:
        raise ValueError("source integration remediation requires source and worker branches")

    remediation_branch = _source_remediation_branch_name(run_id)
    branch_violations = validate_branch_name(remediation_branch)
    if branch_violations:
        raise ValueError("unsafe remediation branch: " + "; ".join(branch_violations))

    worktree = _source_remediation_worktree_path(index, run_id)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    source_sha = _current_commit(repo_path, source_branch)
    worker_sha = _current_commit(repo_path, worker_branch)
    base_sha = _merge_base(repo_path, source_branch, worker_branch)

    created = False
    if worktree.exists():
        if not (worktree / ".git").exists():
            raise ValueError(f"remediation worktree path already exists but is not a git worktree: {worktree}")
    else:
        branch_exists = _git(repo_path, "rev-parse", "--verify", f"refs/heads/{remediation_branch}").returncode == 0
        if branch_exists:
            add = _git(repo_path, "worktree", "add", str(worktree), remediation_branch)
        else:
            add = _git(repo_path, "worktree", "add", "-b", remediation_branch, str(worktree), source_branch)
        if add.returncode != 0:
            raise ValueError(f"unable to create source integration remediation worktree: {_command_error(add)}")
        created = True

    merge_result: subprocess.CompletedProcess[str] | None = None
    if _should_attempt_remediation_merge(worktree, source_sha, created):
        merge_result = _git(worktree, "merge", "--no-commit", "--no-ff", worker_branch)

    conflict_files = _git_lines(worktree, "diff", "--name-only", "--diff-filter=U")
    status_lines = _git_lines(worktree, "status", "--porcelain")
    merge_head = _git(worktree, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    merge_error = _command_error(merge_result) if merge_result and merge_result.returncode != 0 else None
    if conflict_files:
        merge_status = "conflicts-detected"
    elif merge_result and merge_result.returncode == 0:
        merge_status = "merge-prepared"
    elif merge_head.returncode == 0 and status_lines:
        merge_status = "merge-prepared"
    elif status_lines:
        merge_status = "worktree-modified"
    else:
        merge_status = "worktree-ready"

    return {
        "status": merge_status,
        "branch": remediation_branch,
        "worktree": str(worktree),
        "sourceBranch": source_branch,
        "workerBranch": worker_branch,
        "baseSha": base_sha,
        "sourceSha": source_sha,
        "workerSha": worker_sha,
        "conflictFiles": conflict_files,
        "statusLines": status_lines,
        "mergeAttempted": merge_result is not None,
        "mergeError": merge_error,
        "instructions": (
            "Resolve conflicts in this worktree, commit the remediation branch, "
            "then submit the remediation branch as a reviewed source-integration target."
        ),
    }

def _should_attempt_remediation_merge(worktree: Path, source_sha: str | None, created: bool) -> bool:
    merge_head = _git(worktree, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    if merge_head.returncode == 0:
        return False
    if created:
        return True
    status = _git(worktree, "status", "--porcelain")
    if status.returncode != 0 or status.stdout.strip():
        return False
    head_sha = _current_commit(worktree, "HEAD")
    return bool(source_sha and head_sha == source_sha)

def _source_remediation_branch_name(run_id: str) -> str:
    safe_run_id = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in run_id).strip("-")
    return f"aiteamos/remediation/{safe_run_id or 'run'}"

def _source_remediation_worktree_path(index: WorkspaceIndex, run_id: str) -> Path:
    safe_run_id = "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in run_id).strip("-")
    return (index.workspace_root / "artifacts" / "worktrees" / f"{safe_run_id or 'run'}-source-remediation").resolve()

def _merge_base(repo_path: Path, left: str, right: str) -> str | None:
    result = _git(repo_path, "merge-base", left, right)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None

def _git_lines(cwd: Path, *args: str) -> list[str]:
    result = _git(cwd, *args)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
