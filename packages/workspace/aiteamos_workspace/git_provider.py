from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
import json
import re
import shutil
import subprocess


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RepositoryRef:
    id: str
    path: Path


@dataclass(frozen=True)
class BranchRef:
    name: str
    base: str


@dataclass(frozen=True)
class WorktreeRef:
    path: Path
    branch: BranchRef


@dataclass(frozen=True)
class PullRequestInput:
    repository: RepositoryRef
    worktree: WorktreeRef
    title: str | None = None
    body: str | None = None


@dataclass(frozen=True)
class ReviewTargetRef:
    type: str
    ref: str
    url: str | None = None
    description: str | None = None
    provider: str | None = None
    fallback_reason: str | None = None

    def to_manifest_target(self) -> dict[str, str | None]:
        payload: dict[str, str | None] = {"type": self.type, "ref": self.ref}
        if self.url:
            payload["url"] = self.url
        if self.description:
            payload["description"] = self.description
        if self.provider:
            payload["provider"] = self.provider
        if self.fallback_reason:
            payload["fallbackReason"] = self.fallback_reason
        return payload


@dataclass(frozen=True)
class PullRequestChecksResult:
    source: str
    status: str
    summary: str
    checks: list[dict[str, Any]]


class GitProvider(Protocol):
    def create_worktree(self, repository: RepositoryRef, branch: BranchRef, worktree_path: Path) -> WorktreeRef:
        ...

    def get_diff(self, worktree: WorktreeRef | Path) -> str:
        ...

    def apply_patch(self, worktree: WorktreeRef | Path, diff_text: str) -> CommandResult:
        ...

    def commit_changes(self, worktree: WorktreeRef | Path, message: str) -> dict[str, str | bool]:
        ...

    def create_pull_request(self, input: PullRequestInput) -> ReviewTargetRef:
        ...

    def branch_url(self, worktree: WorktreeRef | Path, branch: str) -> str | None:
        ...

    def pull_request_checks(self, repository: RepositoryRef, target: ReviewTargetRef) -> PullRequestChecksResult:
        ...

    def merge_pull_request(self, repository: RepositoryRef, target: ReviewTargetRef, strategy: str) -> dict[str, Any]:
        ...


class GitCliProvider:
    def create_worktree(self, repository: RepositoryRef, branch: BranchRef, worktree_path: Path) -> WorktreeRef:
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        if not worktree_path.exists():
            result = _git(repository.path, ["worktree", "add", "-b", branch.name, str(worktree_path), branch.base], check=False)
            if result.returncode != 0:
                result = _git(repository.path, ["worktree", "add", str(worktree_path), branch.name], check=False)
            if result.returncode != 0:
                raise RuntimeError(f"git worktree add failed: {result.stderr or result.stdout}")
        return WorktreeRef(path=worktree_path, branch=branch)

    def get_diff(self, worktree: WorktreeRef | Path) -> str:
        result = _git(_worktree_path(worktree), ["diff"], check=False)
        return result.stdout

    def apply_patch(self, worktree: WorktreeRef | Path, diff_text: str) -> CommandResult:
        return _run(["git", "apply", "--whitespace=nowarn", "-"], cwd=_worktree_path(worktree), stdin=diff_text, check=False)

    def commit_changes(self, worktree: WorktreeRef | Path, message: str) -> dict[str, str | bool]:
        path = _worktree_path(worktree)
        _git(path, ["add", "-A", "--", "."], check=True)
        _git(path, ["reset", "-q", "--", ".aiteamos"], check=False)
        staged = _git(path, ["diff", "--cached", "--name-only"], check=True).stdout.strip()
        if not staged:
            return {"committed": False, "message": "no staged changes"}
        commit = _git(path, ["commit", "-m", message], check=False)
        if commit.returncode != 0:
            raise RuntimeError(f"git commit failed: {commit.stderr or commit.stdout}")
        sha = self.current_commit(path)
        return {"committed": True, "sha": sha or ""}

    def create_pull_request(self, input: PullRequestInput) -> ReviewTargetRef:
        path = input.worktree.path
        branch = input.worktree.branch.name or self.current_branch(path)
        base = input.worktree.branch.base or "main"
        commit = self.current_commit(path)
        remote = self.remote_url(path)

        if not remote:
            reason = "No origin remote is configured."
            return ReviewTargetRef(
                type="commit" if commit else "branch",
                ref=commit or branch,
                provider="local-git",
                fallback_reason=reason,
                description=f"{reason} Use the local worktree/branch for manual review.",
            )

        push = _git(path, ["push", "-u", "origin", branch], check=False)
        if push.returncode != 0:
            reason = "git push failed"
            return ReviewTargetRef(
                type="commit" if commit else "branch",
                ref=commit or branch,
                provider="local-git",
                fallback_reason=reason,
                description=f"{reason}; use the local worktree/branch for manual review. {_summarize_failure(push)}",
            )

        url = self.branch_url(path, branch)
        if shutil.which("gh"):
            create = _run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--fill",
                    "--base",
                    base,
                    "--head",
                    branch,
                    *(["--title", input.title] if input.title else []),
                    *(["--body", input.body] if input.body else []),
                ],
                cwd=path,
                check=False,
            )
            if create.returncode != 0:
                reason = "gh pr create failed"
                return ReviewTargetRef(
                    type="branch",
                    ref=branch,
                    url=url,
                    provider="github",
                    fallback_reason=reason,
                    description=f"Branch was pushed, but {reason}. {_summarize_failure(create)}",
                )
            pr_url = create.stdout.strip().splitlines()[-1]
            return ReviewTargetRef(type="pull_request", ref=branch, url=pr_url, provider="github")

        return ReviewTargetRef(
            type="branch",
            ref=branch,
            url=url,
            provider="github",
            fallback_reason="gh CLI is not installed",
            description="gh CLI is not installed; pushed branch for manual PR creation.",
        )

    def current_branch(self, worktree: Path) -> str:
        branch = _git(worktree, ["branch", "--show-current"], check=True).stdout.strip()
        if branch:
            return branch
        return _git(worktree, ["rev-parse", "--short", "HEAD"], check=True).stdout.strip()

    def current_commit(self, worktree: Path) -> str | None:
        result = _git(worktree, ["rev-parse", "HEAD"], check=False)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def remote_url(self, worktree: Path) -> str | None:
        result = _git(worktree, ["remote", "get-url", "origin"], check=False)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def branch_url(self, worktree: WorktreeRef | Path, branch: str) -> str | None:
        remote = self.remote_url(_worktree_path(worktree)) or ""
        match = re.match(r"git@github.com:([^/]+)/(.+?)(?:\.git)?$", remote)
        if match:
            return f"https://github.com/{match.group(1)}/{match.group(2)}/tree/{branch}"
        match = re.match(r"https://github.com/([^/]+)/(.+?)(?:\.git)?$", remote)
        if match:
            return f"https://github.com/{match.group(1)}/{match.group(2)}/tree/{branch}"
        return None

    def pull_request_checks(self, repository: RepositoryRef, target: ReviewTargetRef) -> PullRequestChecksResult:
        if target.type != "pull_request" or not target.url:
            return PullRequestChecksResult(
                source="review-target",
                status="not_applicable",
                summary="Review target is not a pull request; external checks were not refreshed.",
                checks=[],
            )
        if _target_provider(target) == "gitlab":
            return self._gitlab_pull_request_checks(repository, target)
        return self._github_pull_request_checks(repository, target)

    def _github_pull_request_checks(self, repository: RepositoryRef, target: ReviewTargetRef) -> PullRequestChecksResult:
        if not shutil.which("gh"):
            return PullRequestChecksResult(
                source="github-cli",
                status="unavailable",
                summary="gh CLI is not installed; external checks were not refreshed.",
                checks=[],
            )
        result = _run(
            ["gh", "pr", "checks", target.url, "--json", "bucket,name,state,link,workflow"],
            cwd=repository.path,
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            return PullRequestChecksResult(
                source="github-cli",
                status="unavailable",
                summary=_summarize_failure(result) or "gh pr checks failed.",
                checks=[],
            )
        try:
            raw_checks = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return PullRequestChecksResult(
                source="github-cli",
                status="unavailable",
                summary="gh returned non-JSON check output.",
                checks=[],
            )
        if not isinstance(raw_checks, list):
            return PullRequestChecksResult(
                source="github-cli",
                status="unavailable",
                summary="gh returned unexpected check output.",
                checks=[],
            )
        checks = [check for check in raw_checks if isinstance(check, dict)]
        status = _status_from_checks(checks)
        return PullRequestChecksResult(
            source="github-cli",
            status=status,
            summary=_summary_from_checks(status, checks),
            checks=checks,
        )

    def _gitlab_pull_request_checks(self, repository: RepositoryRef, target: ReviewTargetRef) -> PullRequestChecksResult:
        if not shutil.which("glab"):
            return PullRequestChecksResult(
                source="gitlab-cli",
                status="unavailable",
                summary="glab CLI is not installed; external checks were not refreshed.",
                checks=[],
            )
        target_ref = _gitlab_merge_request_ref(target)
        result = _run(["glab", "mr", "view", target_ref, "--output", "json"], cwd=repository.path, check=False, timeout=60)
        if result.returncode != 0:
            return PullRequestChecksResult(
                source="gitlab-cli",
                status="unavailable",
                summary=_summarize_failure(result) or "glab mr view failed.",
                checks=[],
            )
        try:
            raw_target = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return PullRequestChecksResult(
                source="gitlab-cli",
                status="unavailable",
                summary="glab returned non-JSON merge request output.",
                checks=[],
            )
        if not isinstance(raw_target, dict):
            return PullRequestChecksResult(
                source="gitlab-cli",
                status="unavailable",
                summary="glab returned unexpected merge request output.",
                checks=[],
            )
        checks = _gitlab_checks_from_merge_request(raw_target)
        status = _status_from_checks(checks)
        return PullRequestChecksResult(
            source="gitlab-cli",
            status=status,
            summary=_summary_from_checks(status, checks),
            checks=checks,
        )

    def merge_pull_request(self, repository: RepositoryRef, target: ReviewTargetRef, strategy: str) -> dict[str, Any]:
        provider = _target_provider(target)
        if provider == "github":
            return self._merge_github_pull_request(repository, target, strategy)
        if provider == "gitlab":
            return self._merge_gitlab_merge_request(repository, target, strategy)
        if provider != "local-git":
            raise NotImplementedError("GitProvider.merge_pull_request is not configured for external providers")
        if target.type != "pull_request":
            raise ValueError("local-git provider integration requires a pull_request review target")
        branch = target.ref.strip()
        if not branch:
            raise ValueError("local-git provider integration requires a target branch ref")
        if branch.startswith("-") or branch.startswith("/") or ".." in branch:
            raise ValueError(f"unsafe local-git branch ref: {branch}")
        if strategy not in {"merge", "ff-only"}:
            raise ValueError(f"local-git provider integration supports only merge/ff-only strategy, not {strategy}")

        check_ref = _git(repository.path, ["check-ref-format", "--branch", branch], check=False)
        if check_ref.returncode != 0:
            raise ValueError(f"invalid local-git branch ref: {_summarize_failure(check_ref)}")
        verify_ref = _git(repository.path, ["rev-parse", "--verify", f"refs/heads/{branch}"], check=False)
        if verify_ref.returncode != 0:
            raise ValueError(f"local-git branch does not exist: {branch}")
        status = _git(repository.path, ["status", "--porcelain"], check=False)
        if status.returncode != 0:
            raise RuntimeError(f"git status failed: {_summarize_failure(status)}")
        if status.stdout.strip():
            raise RuntimeError("local-git provider integration requires a clean repository worktree")

        current_branch = self.current_branch(repository.path)
        before_sha = self.current_commit(repository.path) or ""
        target_sha = verify_ref.stdout.strip()
        merge = _git(repository.path, ["merge", "--ff-only", branch], check=False)
        if merge.returncode != 0:
            raise RuntimeError(f"local-git fast-forward merge failed: {_summarize_failure(merge)}")
        after_sha = self.current_commit(repository.path) or ""
        return {
            "provider": "local-git",
            "strategy": "ff-only" if strategy == "ff-only" else "merge",
            "mergeMode": "fast-forward",
            "repository": repository.id,
            "sourceBranch": current_branch,
            "mergedRef": branch,
            "beforeSha": before_sha,
            "targetSha": target_sha,
            "afterSha": after_sha,
            "changed": before_sha != after_sha,
        }

    def _merge_github_pull_request(self, repository: RepositoryRef, target: ReviewTargetRef, strategy: str) -> dict[str, Any]:
        if target.type != "pull_request":
            raise ValueError("github provider integration requires a pull_request review target")
        if not target.url and not target.ref:
            raise ValueError("github provider integration requires a pull request URL or ref")
        if strategy not in {"merge", "squash", "rebase"}:
            raise ValueError(f"github provider integration supports merge/squash/rebase strategy, not {strategy}")
        if not shutil.which("gh"):
            raise NotImplementedError("GitHub provider merge requires gh CLI to be installed and authenticated")

        source_branch = self.symbolic_branch(repository.path)
        before_sha = self.current_commit(repository.path)
        merge_flag = {"merge": "--merge", "squash": "--squash", "rebase": "--rebase"}[strategy]
        target_ref = target.url or target.ref
        result = _run(["gh", "pr", "merge", target_ref, merge_flag], cwd=repository.path, check=False, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"github provider merge failed: {_summarize_failure(result)}")
        sync = self._reconcile_remote_source_branch(repository, source_branch, before_sha)
        return {
            "provider": "github",
            "mergeMode": strategy,
            "target": target.ref,
            "url": target.url,
            "beforeSha": before_sha,
            "afterSha": sync.get("localAfterSha"),
            **sync,
            "stdout": result.stdout.strip(),
        }

    def _merge_gitlab_merge_request(self, repository: RepositoryRef, target: ReviewTargetRef, strategy: str) -> dict[str, Any]:
        if target.type != "pull_request":
            raise ValueError("gitlab provider integration requires a pull_request review target")
        if not target.url and not target.ref:
            raise ValueError("gitlab provider integration requires a merge request URL or ref")
        if strategy not in {"merge", "squash"}:
            raise ValueError(f"gitlab provider integration supports merge/squash strategy, not {strategy}")
        if not shutil.which("glab"):
            raise NotImplementedError("GitLab provider merge requires glab CLI to be installed and authenticated")

        source_branch = self.symbolic_branch(repository.path)
        before_sha = self.current_commit(repository.path)
        target_ref = _gitlab_merge_request_ref(target)
        merge_flags = ["--squash"] if strategy == "squash" else []
        result = _run(["glab", "mr", "merge", target_ref, *merge_flags], cwd=repository.path, check=False, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"gitlab provider merge failed: {_summarize_failure(result)}")
        sync = self._reconcile_remote_source_branch(repository, source_branch, before_sha)
        return {
            "provider": "gitlab",
            "mergeMode": strategy,
            "target": target.ref,
            "url": target.url,
            "beforeSha": before_sha,
            "afterSha": sync.get("localAfterSha"),
            **sync,
            "stdout": result.stdout.strip(),
        }

    def symbolic_branch(self, worktree: Path) -> str | None:
        result = _git(worktree, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False)
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
        return branch or None

    def _reconcile_remote_source_branch(self, repository: RepositoryRef, source_branch: str | None, before_sha: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sourceBranch": source_branch,
            "remoteBranch": f"origin/{source_branch}" if source_branch else None,
            "localBeforeSha": before_sha,
            "localAfterSha": before_sha,
            "remoteSha": None,
            "sourceSynced": False,
            "sourceSyncStatus": "unavailable",
            "sourceSyncSummary": "Local source branch synchronization was not attempted.",
        }
        if not source_branch:
            payload["sourceSyncSummary"] = "Repository HEAD is detached; local source branch was not synchronized."
            return payload
        remote = self.remote_url(repository.path)
        if not remote:
            payload["sourceSyncSummary"] = "No origin remote is configured; local source branch was not synchronized."
            return payload

        status = _git(repository.path, ["status", "--porcelain"], check=False)
        if status.returncode != 0:
            payload.update(
                {
                    "sourceSyncStatus": "failed",
                    "sourceSyncSummary": f"Unable to inspect local source repository cleanliness: {_summarize_failure(status)}",
                }
            )
            return payload
        if status.stdout.strip():
            payload.update(
                {
                    "sourceSyncStatus": "blocked-dirty-worktree",
                    "sourceSyncSummary": "Local source repository has uncommitted changes; remote merge was not fast-forwarded locally.",
                }
            )
            return payload

        fetch = _git(repository.path, ["fetch", "origin", source_branch], check=False)
        if fetch.returncode != 0:
            payload.update(
                {
                    "sourceSyncStatus": "failed",
                    "sourceSyncSummary": f"Unable to fetch origin/{source_branch}: {_summarize_failure(fetch)}",
                }
            )
            return payload
        remote_sha = _git(repository.path, ["rev-parse", "FETCH_HEAD"], check=False)
        if remote_sha.returncode != 0 or not remote_sha.stdout.strip():
            payload.update(
                {
                    "sourceSyncStatus": "failed",
                    "sourceSyncSummary": f"Unable to resolve fetched origin/{source_branch}: {_summarize_failure(remote_sha)}",
                }
            )
            return payload
        remote_head = remote_sha.stdout.strip()
        payload["remoteSha"] = remote_head
        if before_sha == remote_head:
            payload.update(
                {
                    "sourceSynced": True,
                    "sourceSyncStatus": "already-current",
                    "sourceSyncSummary": f"Local {source_branch} already matches fetched origin/{source_branch}.",
                }
            )
            return payload

        ancestry = _git(repository.path, ["merge-base", "--is-ancestor", "HEAD", "FETCH_HEAD"], check=False)
        if ancestry.returncode != 0:
            payload.update(
                {
                    "sourceSyncStatus": "blocked-diverged",
                    "sourceSyncSummary": f"Fetched origin/{source_branch} is not a fast-forward of local {source_branch}; manual reconciliation is required.",
                }
            )
            return payload
        fast_forward = _git(repository.path, ["merge", "--ff-only", "FETCH_HEAD"], check=False)
        if fast_forward.returncode != 0:
            payload.update(
                {
                    "sourceSyncStatus": "failed",
                    "sourceSyncSummary": f"Unable to fast-forward local {source_branch}: {_summarize_failure(fast_forward)}",
                }
            )
            return payload
        after_sha = self.current_commit(repository.path)
        payload.update(
            {
                "localAfterSha": after_sha,
                "sourceSynced": after_sha == remote_head,
                "sourceSyncStatus": "fast-forwarded" if after_sha == remote_head else "failed",
                "sourceSyncSummary": (
                    f"Local {source_branch} fast-forwarded to fetched origin/{source_branch}."
                    if after_sha == remote_head
                    else f"Local {source_branch} did not reach fetched origin/{source_branch} after fast-forward."
                ),
            }
        )
        return payload


def _worktree_path(worktree: WorktreeRef | Path) -> Path:
    return worktree.path if isinstance(worktree, WorktreeRef) else worktree


def _target_provider(target: ReviewTargetRef) -> str | None:
    provider = (target.provider or "").strip().lower()
    if provider:
        return provider
    url = (target.url or "").lower()
    if "github.com" in url:
        return "github"
    if "gitlab" in url:
        return "gitlab"
    return None


def _gitlab_merge_request_ref(target: ReviewTargetRef) -> str:
    if target.url:
        match = re.search(r"/-/merge_requests/(\d+)(?:[/?#].*)?$", target.url)
        if match:
            return match.group(1)
        return target.url
    ref = target.ref.strip()
    return ref[1:] if ref.startswith("!") else ref


def _gitlab_checks_from_merge_request(payload: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for key in ("headPipeline", "head_pipeline", "pipeline", "latestPipeline", "latest_pipeline"):
        value = payload.get(key)
        if isinstance(value, dict):
            checks.append(_gitlab_pipeline_check(value, "pipeline"))
    for key in ("pipelines", "headPipelines", "head_pipelines"):
        value = payload.get(key)
        if isinstance(value, list):
            checks.extend(_gitlab_pipeline_check(pipeline, "pipeline") for pipeline in value if isinstance(pipeline, dict))
    return checks


def _gitlab_pipeline_check(pipeline: dict[str, Any], default_name: str) -> dict[str, Any]:
    status = _gitlab_pipeline_status(pipeline)
    name = str(pipeline.get("name") or pipeline.get("ref") or default_name)
    if pipeline.get("id") is not None:
        name = f"{name}:{pipeline['id']}"
    check: dict[str, Any] = {
        "bucket": _gitlab_status_bucket(status),
        "name": name,
        "state": status,
        "workflow": "gitlab-ci",
    }
    link = pipeline.get("webUrl") or pipeline.get("web_url") or pipeline.get("url")
    if link:
        check["link"] = str(link)
    return check


def _gitlab_pipeline_status(pipeline: dict[str, Any]) -> str:
    status = pipeline.get("status") or pipeline.get("state")
    if status:
        return str(status)
    detailed = pipeline.get("detailedStatus") or pipeline.get("detailed_status")
    if isinstance(detailed, dict):
        return str(detailed.get("group") or detailed.get("text") or detailed.get("label") or "unknown")
    if detailed:
        return str(detailed)
    return "unknown"


def _gitlab_status_bucket(status: str) -> str:
    normalized = status.lower()
    if normalized in {"success", "passed", "pass", "skipped", "skipping"}:
        return "pass"
    if normalized in {"failed", "failure", "fail", "canceled", "cancelled", "error"}:
        return "fail"
    if normalized in {"running", "pending", "created", "waiting_for_resource", "preparing", "scheduled", "manual"}:
        return "pending"
    return "unknown"


def _summarize_failure(result: CommandResult) -> str:
    text = (result.stderr or result.stdout).strip().replace("\n", " ")
    if len(text) > 240:
        text = f"{text[:237]}..."
    return text


def _status_from_checks(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return "unavailable"
    buckets = {str(check.get("bucket") or check.get("state") or "").lower() for check in checks}
    if buckets & {"fail", "failing", "failed", "failure", "cancel", "canceled", "cancelled", "error"}:
        return "failed"
    if buckets & {"pending", "running", "queued", "waiting"}:
        return "pending"
    if buckets <= {"pass", "passing", "success", "skipping", "skipped", ""}:
        return "passed"
    return "pending"


def _summary_from_checks(status: str, checks: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for check in checks:
        bucket = str(check.get("bucket") or check.get("state") or "unknown").lower()
        counts[bucket] = counts.get(bucket, 0) + 1
    details = ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "none"
    return f"External check status is {status}; {details}."


def _git(cwd: Path, args: list[str], *, check: bool = True) -> CommandResult:
    return _run(["git", *args], cwd=cwd, check=check)


def _run(command: list[str], *, cwd: Path, stdin: str | None = None, check: bool = True, timeout: int = 600) -> CommandResult:
    result = subprocess.run(command, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=timeout)
    payload = CommandResult(result.returncode, result.stdout, result.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} failed: {result.stderr or result.stdout}")
    return payload
