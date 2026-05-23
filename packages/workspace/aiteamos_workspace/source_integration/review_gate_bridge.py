from __future__ import annotations

from pathlib import Path
from typing import Any
import subprocess

from ..gitops import changed_paths_from_diff, repository_path, validate_patch_scope
from ..io import read_text_if_exists
from ..loader import WorkspaceIndex, load_workspace
from ..permissions import edit_action, explain_effective_permissions
from ..review_gate import APPROVAL_VERDICTS
from ..worker_authorization import validate_branch_name, validate_managed_worktree


def evaluate_run_source_integration_gate(
    workspace_or_index: str | Path | WorkspaceIndex,
    run_id: str,
    *,
    actor_member: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    run = index.runs[run_id]
    repo_path = repository_path(index)
    source_branch = _source_branch(index, run)
    worker_branch = run.spec.branch.name if run.spec.branch else None
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    permission_decisions: list[dict[str, Any]] = []

    def check(name: str, status: str, message: str) -> None:
        checks.append({"name": name, "status": status, "message": message})
        if status == "fail":
            blockers.append(message)
        elif status == "warn":
            warnings.append(message)

    source_integration = run.spec.sourceIntegration if isinstance(run.spec.sourceIntegration, dict) else {}
    if source_integration.get("status") == "integrated":
        check("source-integration-state", "pass", "Run source changes are already integrated.")
        return {
            "run": run_id,
            "readyForSourceIntegration": False,
            "status": "INTEGRATED",
            "summary": "Run source changes are already integrated.",
            "repository": str(repo_path),
            "sourceBranch": source_integration.get("sourceBranch") or source_branch,
            "workerBranch": source_integration.get("workerBranch") or worker_branch,
            "changedPaths": source_integration.get("changedPaths") or [],
            "blockers": [],
            "warnings": warnings,
            "checks": checks,
            "permissionDecisions": permission_decisions,
        }

    if run.spec.status not in {"DONE", "FINISHED"}:
        check("run-status", "fail", f"Run must be DONE before source integration; current status is {run.spec.status}.")
    else:
        check("run-status", "pass", f"Run is {run.spec.status}.")

    closeout = run.spec.closeout if isinstance(run.spec.closeout, dict) else {}
    if closeout.get("status") != "closed":
        check("run-closeout", "fail", "Run source integration requires an audited reviewed closeout.")
    else:
        check("run-closeout", "pass", "Run has an audited closeout record.")
        review_id = closeout.get("latestReview")
        review = index.reviews.get(str(review_id)) if review_id else None
        if not review:
            check("closeout-review", "fail", "Closeout does not reference a known Review.")
        else:
            verdict = review.spec.verdict.strip().lower()
            if verdict in APPROVAL_VERDICTS and _review_is_human(index, review):
                check("closeout-review", "pass", f"Closeout Review {review_id} is a human approval.")
            elif verdict in APPROVAL_VERDICTS:
                check("closeout-review", "fail", f"Closeout Review {review_id} is approved but not by a human reviewer.")
            else:
                check("closeout-review", "fail", f"Closeout Review {review_id} is not an approval: {review.spec.verdict}.")

    if not repo_path.exists():
        check("repository", "fail", f"Repository path does not exist: {repo_path}.")
    elif not (repo_path / ".git").exists():
        check("repository", "fail", f"Repository path is not a git worktree: {repo_path}.")
    else:
        check("repository", "pass", f"Repository path is available: {repo_path}.")

    diff_text = read_text_if_exists(index.workspace_root / "runs" / run_id / "diff.patch") or ""
    changed_paths = changed_paths_from_diff(diff_text)
    if not diff_text.strip() or not changed_paths:
        check("diff-patch", "fail", "Run has no reviewable worker diff patch to integrate.")
    else:
        check("diff-patch", "pass", f"Run diff touches {len(changed_paths)} source path(s).")
        scope_violations = validate_patch_scope(index, run_id, diff_text)
        if scope_violations:
            for violation in scope_violations:
                check("assignment-write-scope", "fail", violation)
        else:
            check("assignment-write-scope", "pass", "Diff stays inside the assignment write scope.")

    worktree_value = run.model_dump(mode="json").get("spec", {}).get("worktree")
    worktree = Path(worktree_value).expanduser().resolve() if worktree_value else None
    worktree_violations = validate_managed_worktree(index, run_id, worktree)
    if worktree_violations:
        for violation in worktree_violations:
            check("worker-worktree", "fail", violation)
    elif worktree and worktree.exists():
        check("worker-worktree", "pass", f"Managed worker worktree exists: {worktree}.")
    else:
        check("worker-worktree", "fail", "Run has no existing managed worker worktree.")

    if worker_branch:
        branch_violations = validate_branch_name(worker_branch)
        if branch_violations:
            for violation in branch_violations:
                check("worker-branch", "fail", violation)
        elif not (repo_path.exists() and (repo_path / ".git").exists()):
            check("worker-branch", "fail", "Worker branch cannot be inspected until the source repository is available.")
        elif _git(repo_path, "rev-parse", "--verify", f"refs/heads/{worker_branch}").returncode != 0:
            check("worker-branch", "fail", f"Worker branch does not exist in the repository: {worker_branch}.")
        else:
            check("worker-branch", "pass", f"Worker branch exists: {worker_branch}.")
    else:
        check("worker-branch", "fail", "Run has no worker branch.")

    if repo_path.exists() and (repo_path / ".git").exists():
        current_branch = _current_branch(repo_path)
        if current_branch != source_branch:
            check("source-branch", "fail", f"Repository is on branch {current_branch}, expected {source_branch}.")
        else:
            check("source-branch", "pass", f"Repository is on source branch {source_branch}.")
        dirty = _git(repo_path, "status", "--porcelain")
        if dirty.returncode != 0:
            check("repository-status", "fail", f"Unable to inspect repository status: {_command_error(dirty)}")
        elif dirty.stdout.strip():
            check("repository-status", "fail", "Repository has uncommitted changes; source integration requires a clean branch.")
        else:
            check("repository-status", "pass", "Repository source branch is clean.")
        if worker_branch and _git(repo_path, "rev-parse", "--verify", f"refs/heads/{worker_branch}").returncode == 0:
            ancestor = _git(repo_path, "merge-base", "--is-ancestor", source_branch, worker_branch)
            if ancestor.returncode == 0:
                check("fast-forward", "pass", f"{worker_branch} can fast-forward {source_branch}.")
            else:
                check("fast-forward", "fail", f"{worker_branch} cannot fast-forward {source_branch}; create a follow-up review target instead.")

    permission_checks, permission_blockers, permission_warnings, permission_decisions = _source_permission_checks(
        index,
        run_id,
        actor_member=actor_member,
        changed_paths=changed_paths,
    )
    checks.extend(permission_checks)
    blockers.extend(permission_blockers)
    warnings.extend(permission_warnings)
    permission_decisions.extend(permission_decisions)

    ready = not blockers
    return {
        "run": run_id,
        "readyForSourceIntegration": ready,
        "status": "READY_FOR_SOURCE_INTEGRATION" if ready else "BLOCKED",
        "summary": "Run source changes can be integrated into the source branch." if ready else f"Run source integration has {len(blockers)} blocker(s).",
        "repository": str(repo_path),
        "sourceBranch": source_branch,
        "workerBranch": worker_branch,
        "changedPaths": changed_paths,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "permissionDecisions": permission_decisions,
    }

def _source_permission_checks(
    index: WorkspaceIndex,
    run_id: str,
    *,
    actor_member: str | None,
    changed_paths: list[str],
) -> tuple[list[dict[str, str]], list[str], list[str], list[dict[str, Any]]]:
    run = index.runs[run_id]
    if not actor_member:
        return (
            [
                {
                    "name": "source-integration-actor",
                    "status": "warn",
                    "message": "Source integration actor was not supplied; write permission is checked when the action is submitted.",
                }
            ],
            [],
            [],
            [],
        )
    if actor_member not in index.members:
        message = f"unknown source integration actor member {actor_member}"
        return ([{"name": "source-integration-actor", "status": "fail", "message": message}], [message], [], [])

    actor_kind = index.members[actor_member].spec.kind
    actor_assignment = run.spec.assignment
    assignment_record = index.assignments.get(actor_assignment or "") if actor_assignment else None
    if assignment_record is None or assignment_record.spec.member != actor_member:
        actor_assignment = None
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    decisions: list[dict[str, Any]] = []
    for path in changed_paths:
        decision = explain_effective_permissions(
            index,
            member=actor_member,
            project=run.spec.project,
            assignment=actor_assignment,
            action=edit_action(path),
            non_interactive=actor_kind in {"digital", "service"},
        )
        summary = {"target": "source-path", "path": path, **decision}
        decisions.append(summary)
        decision_value = decision.get("decision")
        if decision_value == "deny" or decision.get("blockers"):
            message = f"actor {actor_member} cannot integrate {path}: {decision.get('reason')}"
            blockers.append(message)
            checks.append({"name": f"source-integration-permission-{path}", "status": "fail", "message": message})
        elif decision_value == "ask":
            message = f"actor {actor_member} permission for {path} is ask; explicit source integration submission is the approval boundary."
            warnings.append(message)
            checks.append({"name": f"source-integration-permission-{path}", "status": "warn", "message": message})
        else:
            checks.append({"name": f"source-integration-permission-{path}", "status": "pass", "message": f"actor {actor_member} may integrate {path}."})
    return checks, blockers, warnings, decisions

def _source_branch(index: WorkspaceIndex, run: Any) -> str:
    repository = next(iter(index.repositories.values()), None)
    default_branch = (repository.spec.defaultBranch if repository else None) or "main"
    branch_base = run.spec.branch.base if run.spec.branch else None
    if branch_base and branch_base not in {"HEAD", "head"}:
        return branch_base
    return default_branch

def _review_is_human(index: WorkspaceIndex, review: Any) -> bool:
    reviewer_kind = getattr(review.spec, "reviewerKind", None)
    if reviewer_kind == "human":
        return True
    reviewer_member = getattr(review.spec, "reviewerMember", None)
    return bool(reviewer_member and reviewer_member in index.members and index.members[reviewer_member].spec.kind == "human")

def _current_branch(repo_path: Path) -> str:
    result = _git(repo_path, "branch", "--show-current")
    return result.stdout.strip() or "HEAD"

def _current_commit(repo_path: Path, ref: str) -> str | None:
    result = _git(repo_path, "rev-parse", ref)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None

def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)

def _command_error(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or f"exit code {result.returncode}").strip()

def _source_integration_decision_kind(actor_kind: str | None) -> str:
    if actor_kind == "service":
        return "service_policy_decision"
    if actor_kind == "digital":
        return "digital_recommendation"
    return "human_approval"

def _source_integration_authority(actor_kind: str | None) -> str:
    if actor_kind == "service":
        return "enforce"
    if actor_kind == "digital":
        return "recommend"
    return "approve"

def _policy_refs(permission_decisions: list[dict[str, Any]]) -> list[str]:
    refs: set[str] = set()
    for decision in permission_decisions:
        for policy_id in decision.get("selectedPolicyIds") or []:
            refs.add(str(policy_id))
    return sorted(refs)

def _has_non_fast_forward_blocker(gate: dict[str, Any]) -> bool:
    for check in gate.get("checks") or []:
        if not isinstance(check, dict):
            continue
        if check.get("name") == "fast-forward" and check.get("status") == "fail":
            return True
        message = str(check.get("message") or "")
        if "cannot fast-forward" in message:
            return True
    return any("cannot fast-forward" in str(blocker) for blocker in gate.get("blockers") or [])
