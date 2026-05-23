from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re
import subprocess

from .eval_requirements import evaluate_run_eval_suite_requirements
from .gitops import changed_paths_from_diff, validate_patch_scope
from .io import read_jsonl, read_text_if_exists
from .loader import WorkspaceIndex, load_workspace


REVIEWABLE_STATUSES = {"REVIEW", "DONE"}
ACTIVE_STATUSES = {"QUEUED", "RUNNING", "TESTING", "RECOVERING"}
BLOCKED_STATUSES = {"FAILED", "STALLED", "INGEST_INCOMPLETE", "INTERRUPTED", "CHANGES_REQUESTED"}
APPROVAL_VERDICTS = {"approved", "approve", "accepted", "accepted-with-action-items"}
CHANGE_REQUEST_VERDICTS = {"changes-requested", "change-requested", "rejected", "blocked"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:OPENAI_API_KEY|ANTHROPIC_API_KEY|GITHUB_TOKEN|GH_TOKEN|API_KEY|SECRET|TOKEN)\s*=\s*['\"]?[A-Za-z0-9_\-]{12,}"),
]
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def evaluate_run_review_gate(workspace_or_index: str | WorkspaceIndex, run_id: str) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    run_dir = index.workspace_root / "runs" / run_id
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    _check_run_status(run.spec.status, checks, blockers, warnings)
    _check_journal(index, run_id, checks, blockers)

    run_payload = run.model_dump(mode="json")
    worktree = run_payload.get("spec", {}).get("worktree")
    target = run.spec.reviewTarget.model_dump(mode="json", exclude_none=True) if run.spec.reviewTarget else None
    diff_patch_text = read_text_if_exists(run_dir / "diff.patch")
    diff_text, diff_source, diff_warning = _review_diff(index, run_id, target, diff_patch_text, worktree)
    if diff_warning:
        warnings.append(diff_warning)
        checks.append({"name": "diff-source", "status": "warn", "message": diff_warning})
    elif diff_text:
        checks.append({"name": "diff-source", "status": "pass", "message": f"Review diff is available from {diff_source}."})
    _check_review_target(target, diff_patch_text, diff_text, checks, blockers, warnings)
    _check_scope(index, run_id, target, diff_text, diff_source, checks, blockers, warnings)
    eval_suite_requirements = _check_eval_suite_requirements(index, run_id, diff_text, checks, blockers)
    _check_safety(diff_text, checks, blockers)
    _check_worktree(worktree, checks, blockers, warnings)
    _check_commands(run_dir, checks, blockers, warnings)
    _check_external_checks(run_dir, checks, blockers, warnings)
    _check_review_record(index, run_id, checks, blockers, warnings)

    ready = not blockers
    return {
        "run": run_id,
        "project": run.spec.project,
        "task": run.spec.task,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "memberKind": run.spec.memberKind,
        "readyForHumanReview": ready,
        "status": "READY_FOR_HUMAN_REVIEW" if ready else "BLOCKED",
        "summary": "Run is ready for human review." if ready else f"Run has {len(blockers)} blocker(s) before human review.",
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "evalSuiteRequirements": eval_suite_requirements,
    }


def _check_run_status(status: str, checks: list[dict[str, str]], blockers: list[str], warnings: list[str]) -> None:
    if status in REVIEWABLE_STATUSES:
        checks.append({"name": "run-status", "status": "pass", "message": f"Run status is {status}."})
        return
    if status in ACTIVE_STATUSES:
        message = f"Run is still active with status {status}."
        blockers.append(message)
        checks.append({"name": "run-status", "status": "fail", "message": message})
        return
    if status in BLOCKED_STATUSES:
        message = f"Run status {status} requires attention before review."
        blockers.append(message)
        checks.append({"name": "run-status", "status": "fail", "message": message})
        return
    message = f"Run status {status} is not a standard review state."
    warnings.append(message)
    checks.append({"name": "run-status", "status": "warn", "message": message})


def _check_journal(index: WorkspaceIndex, run_id: str, checks: list[dict[str, str]], blockers: list[str]) -> None:
    journal = index.run_journals.get(run_id, "")
    if journal.strip():
        checks.append({"name": "journal", "status": "pass", "message": "Run journal is present."})
    else:
        message = "Run journal is missing or empty."
        blockers.append(message)
        checks.append({"name": "journal", "status": "fail", "message": message})


def _check_review_target(
    target: dict[str, Any] | None,
    diff_patch_text: str | None,
    diff_text: str | None,
    checks: list[dict[str, str]],
    blockers: list[str],
    warnings: list[str],
) -> None:
    if not target and not diff_text:
        message = "No review target or diff.patch is available."
        blockers.append(message)
        checks.append({"name": "review-target", "status": "fail", "message": message})
        return
    if not target:
        checks.append({"name": "review-target", "status": "pass", "message": "diff.patch is available for review."})
        return

    target_type = str(target.get("type") or "")
    url = str(target.get("url") or "")
    ref = str(target.get("ref") or "")
    if target_type == "pull_request" and not url:
        message = f"{target_type} review target requires a URL."
        blockers.append(message)
        checks.append({"name": "review-target", "status": "fail", "message": message})
        return
    if target_type == "external_review" and not (url or ref):
        message = "external_review review target requires a URL or ref."
        blockers.append(message)
        checks.append({"name": "review-target", "status": "fail", "message": message})
        return
    if target_type == "branch" and not (url or ref):
        message = "branch review target requires a URL or ref."
        blockers.append(message)
        checks.append({"name": "review-target", "status": "fail", "message": message})
        return
    if target_type == "commit" and not ref:
        message = "commit review target requires a commit ref."
        blockers.append(message)
        checks.append({"name": "review-target", "status": "fail", "message": message})
        return
    if target_type == "diff_patch" and not diff_patch_text:
        message = "diff_patch review target requires diff.patch."
        blockers.append(message)
        checks.append({"name": "review-target", "status": "fail", "message": message})
        return
    if not url:
        warnings.append("Review target has no URL; use the recorded ref/worktree for manual review.")
    checks.append({"name": "review-target", "status": "pass", "message": f"Review target is {target_type or 'recorded'}."})


def _check_scope(
    index: WorkspaceIndex,
    run_id: str,
    target: dict[str, Any] | None,
    diff_text: str | None,
    diff_source: str,
    checks: list[dict[str, str]],
    blockers: list[str],
    warnings: list[str],
) -> None:
    if not diff_text:
        if _target_requires_review_diff(target):
            target_type = str((target or {}).get("type") or "code")
            message = f"No review diff was available for {target_type} assignment scope validation."
            blockers.append(message)
            checks.append({"name": "scope", "status": "fail", "message": message})
        else:
            message = "No review diff was available for assignment scope validation."
            warnings.append(message)
            checks.append({"name": "scope", "status": "warn", "message": message})
        return
    violations = validate_patch_scope(index, run_id, diff_text)
    if violations:
        message = "Patch has assignment scope violations: " + "; ".join(violations)
        blockers.append(message)
        checks.append({"name": "scope", "status": "fail", "message": message})
    else:
        checks.append({"name": "scope", "status": "pass", "message": f"{diff_source} is within the assignment write scope."})


def _check_eval_suite_requirements(
    index: WorkspaceIndex,
    run_id: str,
    diff_text: str | None,
    checks: list[dict[str, str]],
    blockers: list[str],
) -> list[dict[str, Any]]:
    changed_paths = changed_paths_from_diff(diff_text or "") if diff_text else []
    statuses = evaluate_run_eval_suite_requirements(index, run_id, changed_paths=changed_paths)
    for status in statuses:
        if status["status"] == "skip":
            continue
        message = status["message"]
        if status["status"] == "fail":
            blockers.append(message)
            checks.append({"name": "eval-suite-requirement", "status": "fail", "message": message})
        else:
            checks.append({"name": "eval-suite-requirement", "status": "pass", "message": message})
    return statuses


def _review_diff(
    index: WorkspaceIndex,
    run_id: str,
    target: dict[str, Any] | None,
    diff_patch_text: str | None,
    worktree_value: str | None,
) -> tuple[str | None, str, str | None]:
    if diff_patch_text:
        return diff_patch_text, "diff.patch", None
    if not _target_requires_review_diff(target):
        return None, "not-required", None
    worktree = _worktree_for_diff(worktree_value)
    if worktree is None:
        return None, "missing", "Code review targets require a diff.patch or recorded git worktree diff for scope validation."

    worktree_diff = _git(worktree, ["diff", "--no-ext-diff"])
    if worktree_diff.returncode == 0 and worktree_diff.stdout.strip():
        return worktree_diff.stdout, "recorded worktree diff", None

    run = index.runs[run_id]
    target_type = str((target or {}).get("type") or "")
    ref = str((target or {}).get("ref") or "")
    if target_type == "commit" and ref:
        commit_diff = _git(worktree, ["show", "--format=", "--no-ext-diff", ref])
        if commit_diff.returncode == 0 and commit_diff.stdout.strip():
            return commit_diff.stdout, "review target commit", None

    branch = run.spec.branch
    base = branch.base if branch else ""
    head = ref or (branch.name if branch else "")
    if target_type in {"pull_request", "branch"} and base and head:
        for separator in ("...", ".."):
            branch_diff = _git(worktree, ["diff", "--no-ext-diff", f"{base}{separator}{head}"])
            if branch_diff.returncode == 0 and branch_diff.stdout.strip():
                return branch_diff.stdout, "review target branch", None

    return None, "missing", "Could not derive a non-empty review diff from the recorded worktree."


def _target_requires_review_diff(target: dict[str, Any] | None) -> bool:
    return str((target or {}).get("type") or "") in {"pull_request", "branch", "commit", "diff_patch"}


def _worktree_for_diff(worktree_value: str | None) -> Path | None:
    if not worktree_value:
        return None
    worktree = Path(worktree_value).expanduser()
    if not worktree.exists() or not (worktree / ".git").exists():
        return None
    return worktree


def _check_commands(run_dir: Path, checks: list[dict[str, str]], blockers: list[str], warnings: list[str]) -> None:
    command_log = run_dir / "command_results.jsonl"
    test_log = run_dir / "test.log"
    if not command_log.exists():
        if test_log.exists():
            message = "Manual test log is present, but structured command results are unavailable."
        else:
            message = "No structured verification command results are available."
        warnings.append(message)
        checks.append({"name": "verification", "status": "warn", "message": message})
        return
    results = read_jsonl(command_log)
    failed = [result for result in results if bool(result.get("timedOut")) or result.get("returncode") not in {0, None}]
    if failed:
        message = f"{len(failed)} verification command(s) failed or timed out."
        blockers.append(message)
        checks.append({"name": "verification", "status": "fail", "message": message})
    else:
        checks.append({"name": "verification", "status": "pass", "message": f"{len(results)} verification command(s) passed."})


def _check_safety(diff_text: str | None, checks: list[dict[str, str]], blockers: list[str]) -> None:
    if not diff_text:
        checks.append({"name": "safety", "status": "warn", "message": "No diff.patch was available for local safety scanning."})
        return
    added_lines = [line[1:] for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]
    secret_hits = _secret_hits(added_lines)
    conflict_hits = [line for line in added_lines if line.strip().startswith(CONFLICT_MARKERS)]
    if secret_hits:
        message = f"Potential secret material found in added lines: {', '.join(secret_hits[:3])}."
        blockers.append(message)
        checks.append({"name": "safety", "status": "fail", "message": message})
        return
    if conflict_hits:
        message = "Conflict markers were found in added lines."
        blockers.append(message)
        checks.append({"name": "safety", "status": "fail", "message": message})
        return
    paths = changed_paths_from_diff(diff_text)
    checks.append({"name": "safety", "status": "pass", "message": f"Local diff safety scan passed for {len(paths)} changed path(s)."})


def _check_worktree(
    worktree_value: str | None,
    checks: list[dict[str, str]],
    blockers: list[str],
    warnings: list[str],
) -> None:
    if not worktree_value:
        message = "No managed worktree is recorded; reviewing from diff/target only."
        warnings.append(message)
        checks.append({"name": "worktree", "status": "warn", "message": message})
        return
    worktree = Path(worktree_value).expanduser()
    if not worktree.exists():
        message = f"Recorded worktree is missing: {worktree}."
        warnings.append(message)
        checks.append({"name": "worktree", "status": "warn", "message": message})
        return
    if not (worktree / ".git").exists():
        message = f"Recorded worktree is not a git worktree: {worktree}."
        warnings.append(message)
        checks.append({"name": "worktree", "status": "warn", "message": message})
        return
    diff_check = _git(worktree, ["diff", "--check"])
    if diff_check.returncode != 0:
        message = "git diff --check failed in the recorded worktree."
        blockers.append(message)
        checks.append({"name": "worktree", "status": "fail", "message": message})
        return
    status = _git(worktree, ["status", "--porcelain"])
    if status.returncode != 0:
        message = "Could not inspect recorded worktree status."
        warnings.append(message)
        checks.append({"name": "worktree", "status": "warn", "message": message})
        return
    if status.stdout.strip():
        message = "Recorded worktree has uncommitted or untracked files."
        warnings.append(message)
        checks.append({"name": "worktree", "status": "warn", "message": message})
        return
    checks.append({"name": "worktree", "status": "pass", "message": "Recorded worktree is clean and passed git diff --check."})


def _check_external_checks(run_dir: Path, checks: list[dict[str, str]], blockers: list[str], warnings: list[str]) -> None:
    path = run_dir / "checks.json"
    if not path.exists():
        message = "External PR checks have not been refreshed."
        warnings.append(message)
        checks.append({"name": "external-checks", "status": "warn", "message": message})
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        message = "External check status file is invalid JSON."
        warnings.append(message)
        checks.append({"name": "external-checks", "status": "warn", "message": message})
        return
    status = str(payload.get("status") or "unavailable")
    summary = str(payload.get("summary") or f"External check status is {status}.")
    if status == "failed":
        blockers.append(summary)
        checks.append({"name": "external-checks", "status": "fail", "message": summary})
    elif status == "pending":
        blockers.append(summary)
        checks.append({"name": "external-checks", "status": "fail", "message": summary})
    elif status == "passed":
        checks.append({"name": "external-checks", "status": "pass", "message": summary})
    else:
        warnings.append(summary)
        checks.append({"name": "external-checks", "status": "warn", "message": summary})


def _check_review_record(
    index: WorkspaceIndex,
    run_id: str,
    checks: list[dict[str, str]],
    blockers: list[str],
    warnings: list[str],
) -> None:
    run = index.runs[run_id]
    review_ids = _linked_review_ids(index, run_id)
    if not review_ids:
        message = "No human review record is linked yet."
        warnings.append(message)
        checks.append({"name": "human-review", "status": "warn", "message": message})
        return

    latest_id = sorted(review_ids)[-1]
    latest = index.reviews[latest_id]
    verdict = latest.spec.verdict.strip().lower()
    if verdict in CHANGE_REQUEST_VERDICTS:
        message = f"Latest human review {latest_id} requested changes."
        blockers.append(message)
        checks.append({"name": "human-review", "status": "fail", "message": message})
        return
    if verdict in APPROVAL_VERDICTS:
        checks.append({"name": "human-review", "status": "pass", "message": f"Latest human review {latest_id} is {latest.spec.verdict}."})
        return

    message = f"Latest human review {latest_id} has non-final verdict {latest.spec.verdict}."
    warnings.append(message)
    checks.append({"name": "human-review", "status": "warn", "message": message})


def _linked_review_ids(index: WorkspaceIndex, run_id: str) -> list[str]:
    run = index.runs[run_id]
    review_ids = [_normalize_review_ref(ref) for ref in run.spec.reviews]
    review_ids = [review_id for review_id in review_ids if review_id in index.reviews]
    for review_id, review in index.reviews.items():
        if getattr(review.spec, "run", None) == run_id and review_id not in review_ids:
            review_ids.append(review_id)
    if not review_ids:
        review_ids = [
            review_id
            for review_id, review in index.reviews.items()
            if review.spec.task == run.spec.task and not getattr(review.spec, "run", None)
        ]
    return review_ids


def _normalize_review_ref(ref: str) -> str:
    value = str(ref).strip()
    if value.endswith(".yaml"):
        value = Path(value).stem
    return value


def _secret_hits(lines: list[str]) -> list[str]:
    hits: list[str] = []
    for line in lines:
        for pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                hits.append(match.group(0).split("=")[0])
                break
    return hits


def _git(worktree: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=worktree, capture_output=True, text=True, timeout=30, check=False)
