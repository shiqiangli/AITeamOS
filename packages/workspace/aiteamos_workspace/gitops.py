from __future__ import annotations

from pathlib import Path
from typing import Any
import fnmatch
import re

from .git_provider import BranchRef, CommandResult, GitCliProvider, PullRequestInput, RepositoryRef
from .io import read_yaml, write_yaml
from .loader import WorkspaceIndex, load_workspace
from .permissions import explain_effective_permissions
from .worker_authorization import expected_worktree_path, validate_branch_name, validate_managed_worktree


def default_git_provider() -> GitCliProvider:
    return GitCliProvider()


def ensure_worktree(workspace_path: str | Path, run_id: str) -> Path:
    index = load_workspace(workspace_path)
    run = index.runs[run_id]
    branch = run.spec.branch.name if run.spec.branch else f"aiteamos/{run.spec.task}/{run.spec.member}/{run_id}"
    base = run.spec.branch.base if run.spec.branch else "HEAD"
    branch_violations = validate_branch_name(branch)
    if branch_violations:
        raise ValueError("unsafe worker branch: " + "; ".join(branch_violations))
    worktree = expected_worktree_path(index, run_id)
    default_git_provider().create_worktree(repository_ref(index), BranchRef(name=branch, base=base), worktree)
    _update_run_fields(workspace_path, run_id, {"worktree": str(worktree), "worker": {"branch": branch, "worktree": str(worktree)}})
    return worktree


def repository_ref(index: WorkspaceIndex) -> RepositoryRef:
    repository = next(iter(index.repositories.values()), None)
    repository_id = repository.object_id if repository else "default"
    return RepositoryRef(id=repository_id, path=repository_path(index))


def repository_path(index: WorkspaceIndex) -> Path:
    repository = next(iter(index.repositories.values()), None)
    if repository and repository.spec.localPath:
        return Path(repository.spec.localPath).expanduser().resolve()
    return index.workspace_root.parent.resolve()


def validate_patch_scope(index: WorkspaceIndex, run_id: str, diff_text: str) -> list[str]:
    run = index.runs[run_id]
    assignment = index.assignments.get(run.spec.assignment or "")
    allowed = assignment.spec.scope.write if assignment else []
    paths = changed_paths_from_diff(diff_text)
    violations: list[str] = []
    if assignment is None:
        violations.append("run has no valid assignment write scope")
        return violations
    if assignment.spec.member != run.spec.member:
        violations.append(f"assignment {assignment.object_id} belongs to {assignment.spec.member}, not {run.spec.member}")
    if not allowed:
        violations.append("assignment has no explicit write scope")
    for path in paths:
        if path.startswith("/") or ".." in Path(path).parts:
            violations.append(f"{path}: unsafe patch path")
            continue
        if path.startswith(".aiteamos/"):
            violations.append(f"{path}: .aiteamos changes must go through workspace APIs, not source patches")
            continue
        if _is_forbidden_path(path):
            violations.append(f"{path}: forbidden by safety policy")
            continue
        if allowed and not any(fnmatch.fnmatch(path, pattern) for pattern in allowed):
            violations.append(f"{path}: outside assignment write scope")
    return violations


def validate_patch_permissions(index: WorkspaceIndex, run_id: str, diff_text: str) -> tuple[list[str], list[dict[str, Any]]]:
    run = index.runs[run_id]
    paths = changed_paths_from_diff(diff_text)
    violations: list[str] = []
    decisions: list[dict[str, Any]] = []
    for path in paths:
        if path.startswith("/") or ".." in Path(path).parts:
            continue
        decision = explain_effective_permissions(
            index,
            member=run.spec.member,
            project=run.spec.project,
            assignment=run.spec.assignment,
            action={"tool": "Edit", "path": path},
            non_interactive=True,
        )
        summary = {
            "member": decision.get("member"),
            "memberKind": decision.get("memberKind"),
            "project": decision.get("project"),
            "assignment": decision.get("assignment"),
            "action": decision.get("normalizedAction"),
            "decision": decision.get("decision"),
            "reason": decision.get("reason"),
            "selectedPolicyIds": decision.get("selectedPolicyIds", []),
            "matchedRules": decision.get("matchedRules", []),
            "blockers": decision.get("blockers", []),
            "warnings": decision.get("warnings", []),
        }
        decisions.append(summary)
        if decision["decision"] != "allow" or decision["blockers"]:
            violations.append(f"{path}: edit denied by effective permissions ({decision['reason']})")
    return violations, decisions


def changed_paths_from_diff(diff_text: str) -> list[str]:
    paths: set[str] = set()
    for line in diff_text.splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            path = line[4:].strip()
            if path == "/dev/null":
                continue
            path = re.sub(r"^[ab]/", "", path)
            if path.startswith("/") or ".." in Path(path).parts:
                paths.add(path)
            else:
                paths.add(path)
    return sorted(paths)


def apply_patch(worktree: Path, diff_text: str) -> CommandResult:
    return default_git_provider().apply_patch(worktree, diff_text)


def diff_worktree(worktree: Path) -> str:
    return default_git_provider().get_diff(worktree)


def commit_worker_changes(workspace_path: str | Path, run_id: str, message: str) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    run = index.runs[run_id]
    worktree_value = run.model_dump(mode="json").get("spec", {}).get("worktree")
    worktree = Path(worktree_value or ensure_worktree(workspace_path, run_id))
    violations = validate_managed_worktree(index, run_id, worktree)
    if violations:
        raise ValueError("unsafe worker worktree: " + "; ".join(violations))
    result = default_git_provider().commit_changes(worktree, message)
    if result.get("committed"):
        _record_output(workspace_path, run_id, {"type": "commit", "sha": result["sha"]})
    return result


def create_pull_request(workspace_path: str | Path, run_id: str, title: str | None = None, body: str | None = None) -> dict[str, Any]:
    """Create the strongest available review target without bypassing human review.

    GitHub PRs are preferred, but missing remotes, push failures, or a missing
    `gh` CLI should not make an otherwise reviewable run unrecoverable.
    """
    index = load_workspace(workspace_path)
    run = index.runs[run_id]
    worktree_value = run.model_dump(mode="json").get("spec", {}).get("worktree")
    worktree = Path(worktree_value or ensure_worktree(workspace_path, run_id))
    branch = run.spec.branch.name if run.spec.branch else current_branch(worktree)
    base = run.spec.branch.base if run.spec.branch else "main"
    branch_violations = validate_branch_name(branch)
    worktree_violations = validate_managed_worktree(index, run_id, worktree)
    if branch_violations or worktree_violations:
        raise ValueError("unsafe PR review target: " + "; ".join(branch_violations + worktree_violations))
    provider = default_git_provider()
    target = provider.create_pull_request(
        PullRequestInput(
            repository=repository_ref(index),
            worktree=provider.create_worktree(repository_ref(index), BranchRef(name=branch, base=base), worktree),
            title=title,
            body=body,
        )
    ).to_manifest_target()
    _persist_review_target(workspace_path, run_id, target)
    return target


def current_branch(worktree: Path) -> str:
    return default_git_provider().current_branch(worktree)


def current_commit(worktree: Path) -> str | None:
    return default_git_provider().current_commit(worktree)


def remote_url(worktree: Path) -> str | None:
    return default_git_provider().remote_url(worktree)


def branch_url(worktree: Path, branch: str) -> str | None:
    return default_git_provider().branch_url(worktree, branch)


def fallback_review_target(target_type: str, ref: str, url: str | None, description: str) -> dict[str, Any]:
    return {"type": target_type, "url": url, "ref": ref, "description": description}


def _persist_review_target(workspace_path: str | Path, run_id: str, target: dict[str, Any]) -> None:
    _update_run_fields(workspace_path, run_id, {"status": "REVIEW", "reviewTarget": target})
    _record_output(workspace_path, run_id, {"type": "review_target", "target": target})


def _record_output(workspace_path: str | Path, run_id: str, output: dict[str, Any]) -> None:
    index = load_workspace(workspace_path)
    path = index.workspace_root / "runs" / run_id / "run.yaml"
    data = read_yaml(path)
    outputs = data.setdefault("spec", {}).setdefault("outputs", [])
    outputs.append(output)
    write_yaml(path, data)


def _update_run_fields(workspace_path: str | Path, run_id: str, patch: dict[str, Any]) -> None:
    index = load_workspace(workspace_path)
    path = index.workspace_root / "runs" / run_id / "run.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    spec.update(patch)
    write_yaml(path, data)


def _is_forbidden_path(path: str) -> bool:
    lowered = path.lower()
    return ".env" in lowered or "secret" in lowered or "production" in lowered
