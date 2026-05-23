from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import json
import shutil
import subprocess
import tempfile
import time
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import git_provider as git_provider_module
from aiteamos_workspace import create_run, create_task, load_workspace, update_run
from aiteamos_workspace.gitops import create_pull_request
from aiteamos_workspace.git_provider import (
    BranchRef,
    CommandResult,
    GitCliProvider,
    PullRequestInput,
    RepositoryRef,
    ReviewTargetRef,
    WorktreeRef,
)
from aiteamos_workspace.io import read_yaml, write_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"


class GitProviderTest(unittest.TestCase):
    def test_provider_returns_commit_review_target_without_remote(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")
            provider = GitCliProvider()

            target = provider.create_pull_request(
                PullRequestInput(
                    repository=RepositoryRef(id="repo", path=repo),
                    worktree=WorktreeRef(path=repo, branch=BranchRef(name=provider.current_branch(repo), base="main")),
                    title="Review target",
                )
            )

            self.assertEqual(target.type, "commit")
            self.assertTrue(target.ref)
            self.assertIsNone(target.url)
            self.assertEqual(target.provider, "local-git")
            self.assertEqual(target.fallback_reason, "No origin remote is configured.")
            self.assertIn("No origin remote", target.description or "")

    def test_provider_derives_github_branch_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")
            _git(repo, ["remote", "add", "origin", "git@github.com:example/aiteamos.git"])

            url = GitCliProvider().branch_url(repo, "aiteamos/RUN-1")

            self.assertEqual(url, "https://github.com/example/aiteamos/tree/aiteamos/RUN-1")

    def test_provider_does_not_wire_auto_merge(self) -> None:
        provider = GitCliProvider()

        with self.assertRaises(NotImplementedError):
            provider.merge_pull_request(
                RepositoryRef(id="repo", path=Path.cwd()),
                ReviewTargetRef(type="pull_request", ref="branch", url="https://example.invalid/pr/1"),
                "squash",
            )

    def test_provider_merges_github_pull_request_with_gh_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")
            provider = GitCliProvider()
            original_run = git_provider_module._run

            def run_command(command: list[str], **kwargs: object) -> CommandResult:
                if command[:3] == ["gh", "pr", "merge"]:
                    return CommandResult(0, "Merged pull request #9\n", "")
                return original_run(command, **kwargs)

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/gh"),
                patch.object(git_provider_module, "_run", side_effect=run_command) as run_command_mock,
            ):
                result = provider.merge_pull_request(
                    RepositoryRef(id="repo", path=repo),
                    ReviewTargetRef(type="pull_request", provider="github", ref="aiteamos/provider-source-integration", url="https://github.com/example/aiteamos/pull/9"),
                    "merge",
                )

            self.assertEqual(result["provider"], "github")
            self.assertEqual(result["mergeMode"], "merge")
            self.assertEqual(result["target"], "aiteamos/provider-source-integration")
            self.assertEqual(result["url"], "https://github.com/example/aiteamos/pull/9")
            self.assertEqual(result["stdout"], "Merged pull request #9")
            self.assertFalse(result["sourceSynced"])
            self.assertEqual(result["sourceSyncStatus"], "unavailable")
            self.assertIn("No origin remote", result["sourceSyncSummary"])
            gh_calls = [call for call in run_command_mock.call_args_list if call.args[0][:3] == ["gh", "pr", "merge"]]
            self.assertEqual(len(gh_calls), 1)
            self.assertEqual(gh_calls[0].args[0], ["gh", "pr", "merge", "https://github.com/example/aiteamos/pull/9", "--merge"])

    def test_provider_merges_github_pull_request_and_reconciles_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo = _init_repo(temp_root / "repo")
            origin = temp_root / "origin.git"
            _git(temp_root, ["init", "--bare", str(origin)])
            _git(repo, ["remote", "add", "origin", str(origin)])
            _git(repo, ["push", "-u", "origin", "main"])
            _git(origin, ["symbolic-ref", "HEAD", "refs/heads/main"])

            remote_work = temp_root / "remote-work"
            _git(temp_root, ["clone", str(origin), str(remote_work)])
            _git(remote_work, ["config", "user.email", "aiteamos@example.invalid"])
            _git(remote_work, ["config", "user.name", "AITEAMOS Provider Test"])
            (remote_work / "provider.txt").write_text("merged remotely\n", encoding="utf-8")
            _git(remote_work, ["add", "provider.txt"])
            _git(remote_work, ["commit", "-m", "simulate provider merge"])
            _git(remote_work, ["push", "origin", "main"])
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=remote_work,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            before_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            original_run = git_provider_module._run

            def run_command(command: list[str], **kwargs: object) -> CommandResult:
                if command[:3] == ["gh", "pr", "merge"]:
                    return CommandResult(0, "Merged pull request #9\n", "")
                return original_run(command, **kwargs)

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/gh"),
                patch.object(git_provider_module, "_run", side_effect=run_command),
            ):
                result = GitCliProvider().merge_pull_request(
                    RepositoryRef(id="repo", path=repo),
                    ReviewTargetRef(type="pull_request", provider="github", ref="aiteamos/provider-source-integration", url="https://github.com/example/aiteamos/pull/9"),
                    "merge",
                )

            self.assertEqual(result["provider"], "github")
            self.assertEqual(result["beforeSha"], before_sha)
            self.assertEqual(result["remoteSha"], remote_sha)
            self.assertEqual(result["afterSha"], remote_sha)
            self.assertEqual(result["localAfterSha"], remote_sha)
            self.assertTrue(result["sourceSynced"])
            self.assertEqual(result["sourceSyncStatus"], "fast-forwarded")
            self.assertEqual((repo / "provider.txt").read_text(encoding="utf-8"), "merged remotely\n")

    def test_provider_merges_gitlab_merge_request_with_glab_cli(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")
            provider = GitCliProvider()
            original_run = git_provider_module._run

            def run_command(command: list[str], **kwargs: object) -> CommandResult:
                if command[:3] == ["glab", "mr", "merge"]:
                    return CommandResult(0, "Merged merge request !9\n", "")
                return original_run(command, **kwargs)

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/glab"),
                patch.object(git_provider_module, "_run", side_effect=run_command) as run_command_mock,
            ):
                result = provider.merge_pull_request(
                    RepositoryRef(id="repo", path=repo),
                    ReviewTargetRef(
                        type="pull_request",
                        ref="aiteamos/provider-source-integration",
                        url="https://gitlab.com/example/aiteamos/-/merge_requests/9",
                    ),
                    "merge",
                )

            self.assertEqual(result["provider"], "gitlab")
            self.assertEqual(result["mergeMode"], "merge")
            self.assertEqual(result["target"], "aiteamos/provider-source-integration")
            self.assertEqual(result["url"], "https://gitlab.com/example/aiteamos/-/merge_requests/9")
            self.assertEqual(result["stdout"], "Merged merge request !9")
            self.assertFalse(result["sourceSynced"])
            self.assertEqual(result["sourceSyncStatus"], "unavailable")
            self.assertIn("No origin remote", result["sourceSyncSummary"])
            glab_calls = [call for call in run_command_mock.call_args_list if call.args[0][:3] == ["glab", "mr", "merge"]]
            self.assertEqual(len(glab_calls), 1)
            self.assertEqual(glab_calls[0].args[0], ["glab", "mr", "merge", "9"])

    def test_provider_merges_gitlab_merge_request_and_reconciles_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            repo = _init_repo(temp_root / "repo")
            origin = temp_root / "origin.git"
            _git(temp_root, ["init", "--bare", str(origin)])
            _git(repo, ["remote", "add", "origin", str(origin)])
            _git(repo, ["push", "-u", "origin", "main"])
            _git(origin, ["symbolic-ref", "HEAD", "refs/heads/main"])

            remote_work = temp_root / "remote-work"
            _git(temp_root, ["clone", str(origin), str(remote_work)])
            _git(remote_work, ["config", "user.email", "aiteamos@example.invalid"])
            _git(remote_work, ["config", "user.name", "AITEAMOS Provider Test"])
            (remote_work / "provider.txt").write_text("merged remotely by GitLab\n", encoding="utf-8")
            _git(remote_work, ["add", "provider.txt"])
            _git(remote_work, ["commit", "-m", "simulate GitLab provider merge"])
            _git(remote_work, ["push", "origin", "main"])
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=remote_work,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            before_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            original_run = git_provider_module._run

            def run_command(command: list[str], **kwargs: object) -> CommandResult:
                if command[:3] == ["glab", "mr", "merge"]:
                    return CommandResult(0, "Merged merge request !9\n", "")
                return original_run(command, **kwargs)

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/glab"),
                patch.object(git_provider_module, "_run", side_effect=run_command),
            ):
                result = GitCliProvider().merge_pull_request(
                    RepositoryRef(id="repo", path=repo),
                    ReviewTargetRef(
                        type="pull_request",
                        provider="gitlab",
                        ref="aiteamos/provider-source-integration",
                        url="https://gitlab.com/example/aiteamos/-/merge_requests/9",
                    ),
                    "merge",
                )

            self.assertEqual(result["provider"], "gitlab")
            self.assertEqual(result["beforeSha"], before_sha)
            self.assertEqual(result["remoteSha"], remote_sha)
            self.assertEqual(result["afterSha"], remote_sha)
            self.assertEqual(result["localAfterSha"], remote_sha)
            self.assertTrue(result["sourceSynced"])
            self.assertEqual(result["sourceSyncStatus"], "fast-forwarded")
            self.assertEqual((repo / "provider.txt").read_text(encoding="utf-8"), "merged remotely by GitLab\n")

    def test_provider_merges_local_git_pull_request_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")
            source_file = repo / "provider.txt"
            source_file.write_text("base\n", encoding="utf-8")
            _git(repo, ["add", "provider.txt"])
            _git(repo, ["commit", "-m", "add provider fixture"])
            _git(repo, ["checkout", "-b", "aiteamos/provider-local"])
            source_file.write_text("local provider merge\n", encoding="utf-8")
            _git(repo, ["add", "provider.txt"])
            _git(repo, ["commit", "-m", "provider local change"])
            target_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            _git(repo, ["checkout", "main"])
            before_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = GitCliProvider().merge_pull_request(
                RepositoryRef(id="repo", path=repo),
                ReviewTargetRef(type="pull_request", provider="local-git", ref="aiteamos/provider-local"),
                "merge",
            )

            self.assertEqual(result["provider"], "local-git")
            self.assertEqual(result["mergeMode"], "fast-forward")
            self.assertEqual(result["beforeSha"], before_sha)
            self.assertEqual(result["targetSha"], target_sha)
            self.assertEqual(result["afterSha"], target_sha)
            self.assertTrue(result["changed"])
            self.assertEqual(source_file.read_text(encoding="utf-8"), "local provider merge\n")

    def test_provider_pr_checks_degrades_when_gh_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")

            with patch.object(git_provider_module.shutil, "which", return_value=None):
                result = GitCliProvider().pull_request_checks(
                    RepositoryRef(id="repo", path=repo),
                    ReviewTargetRef(type="pull_request", ref="branch", url="https://github.com/example/aiteamos/pull/1"),
                )

            self.assertEqual(result.source, "github-cli")
            self.assertEqual(result.status, "unavailable")
            self.assertEqual(result.checks, [])
            self.assertIn("gh CLI is not installed", result.summary)

    def test_provider_pr_checks_reads_status_through_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")
            checks = [
                {"bucket": "pass", "name": "lint", "state": "SUCCESS", "link": "https://example.invalid/lint"},
                {"bucket": "fail", "name": "test", "state": "FAILURE", "workflow": "ci"},
            ]

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/gh"),
                patch.object(git_provider_module, "_run", return_value=CommandResult(0, json.dumps(checks), "")) as run,
            ):
                result = GitCliProvider().pull_request_checks(
                    RepositoryRef(id="repo", path=repo),
                    ReviewTargetRef(type="pull_request", ref="branch", url="https://github.com/example/aiteamos/pull/1"),
                )

            self.assertEqual(result.source, "github-cli")
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.checks, checks)
            self.assertIn("fail=1", result.summary)
            self.assertEqual(run.call_args.kwargs["cwd"], repo)
            self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def test_provider_pr_checks_reads_gitlab_pipeline_status_through_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")
            merge_request = {
                "title": "Provider checks",
                "headPipeline": {
                    "id": 72,
                    "status": "success",
                    "ref": "aiteamos/provider-source-integration",
                    "webUrl": "https://gitlab.com/example/aiteamos/-/pipelines/72",
                },
            }

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/glab"),
                patch.object(git_provider_module, "_run", return_value=CommandResult(0, json.dumps(merge_request), "")) as run,
            ):
                result = GitCliProvider().pull_request_checks(
                    RepositoryRef(id="repo", path=repo),
                    ReviewTargetRef(type="pull_request", ref="aiteamos/provider-checks", url="https://gitlab.com/example/aiteamos/-/merge_requests/7"),
                )

            self.assertEqual(result.source, "gitlab-cli")
            self.assertEqual(result.status, "passed")
            self.assertEqual(result.checks[0]["bucket"], "pass")
            self.assertEqual(result.checks[0]["state"], "success")
            self.assertEqual(result.checks[0]["workflow"], "gitlab-ci")
            self.assertEqual(result.checks[0]["link"], "https://gitlab.com/example/aiteamos/-/pipelines/72")
            self.assertIn("pass=1", result.summary)
            self.assertEqual(run.call_args.args[0], ["glab", "mr", "view", "7", "--output", "json"])
            self.assertEqual(run.call_args.kwargs["cwd"], repo)
            self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def test_provider_pr_checks_reports_gitlab_failed_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _init_repo(Path(temp_dir) / "repo")
            merge_request = {
                "headPipeline": {
                    "id": 73,
                    "status": "failed",
                    "webUrl": "https://gitlab.com/example/aiteamos/-/pipelines/73",
                },
            }

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/glab"),
                patch.object(git_provider_module, "_run", return_value=CommandResult(0, json.dumps(merge_request), "")),
            ):
                result = GitCliProvider().pull_request_checks(
                    RepositoryRef(id="repo", path=repo),
                    ReviewTargetRef(type="pull_request", provider="gitlab", ref="!7", url="https://gitlab.com/example/aiteamos/-/merge_requests/7"),
                )

            self.assertEqual(result.source, "gitlab-cli")
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.checks[0]["bucket"], "fail")
            self.assertIn("fail=1", result.summary)

    def test_gitops_create_pull_request_persists_fallback_review_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            task = create_task(
                workspace,
                title="Provider fallback task",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
            )
            time.sleep(0.01)
            run = create_run(workspace, task_id=task.object_id)

            fake_worktree = _init_repo(workspace / "artifacts" / "worktrees" / run.object_id)
            (fake_worktree / "packages" / "workspace").mkdir(parents=True)
            (fake_worktree / "packages" / "workspace" / "provider.txt").write_text("before\n", encoding="utf-8")
            _git(fake_worktree, ["add", "packages/workspace/provider.txt"])
            _git(fake_worktree, ["commit", "-m", "provider test"])
            (fake_worktree / "packages" / "workspace" / "provider.txt").write_text("after\n", encoding="utf-8")

            update_run(
                workspace,
                run.object_id,
                {
                    "status": "STALLED",
                    "worktree": str(fake_worktree),
                    "worker": {"stage": "stalled", "worktree": str(fake_worktree), "branch": run.spec.branch.name},
                },
            )

            target = create_pull_request(workspace, run.object_id, title="Provider fallback")

            self.assertEqual(target["type"], "commit")
            self.assertEqual(target["provider"], "local-git")
            self.assertEqual(target["fallbackReason"], "No origin remote is configured.")
            self.assertIn("No origin remote", target["description"])
            index = load_workspace(workspace)
            stored = index.runs[run.object_id].spec.reviewTarget
            self.assertIsNotNone(stored)
            self.assertEqual(stored.type, "commit")
            self.assertTrue(
                [
                    output
                    for output in index.runs[run.object_id].spec.outputs
                    if isinstance(output, dict) and output.get("type") == "review_target"
                ]
            )

    def test_api_refreshes_run_review_target_checks_for_review_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            task = create_task(
                workspace,
                title="Refresh provider review checks",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
            )
            time.sleep(0.01)
            run = create_run(workspace, task_id=task.object_id)
            run_dir = workspace / "runs" / run.object_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "journal.md").write_text("Reviewed provider check refresh.\n", encoding="utf-8")
            (run_dir / "diff.patch").write_text(
                "\n".join(
                    [
                        "diff --git a/packages/workspace/provider.txt b/packages/workspace/provider.txt",
                        "new file mode 100644",
                        "index 0000000..e69de29",
                        "--- /dev/null",
                        "+++ b/packages/workspace/provider.txt",
                        "@@ -0,0 +1 @@",
                        "+provider check",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            update_run(
                workspace,
                run.object_id,
                {
                    "status": "REVIEW",
                    "journal": "journal.md",
                    "reviewTarget": {
                        "type": "pull_request",
                        "url": "https://github.com/example/aiteamos/pull/7",
                        "ref": "aiteamos/provider-checks",
                    },
                },
            )
            checks = [
                {"bucket": "pass", "name": "lint", "state": "SUCCESS", "link": "https://example.invalid/lint"},
                {"bucket": "fail", "name": "unit", "state": "FAILURE", "workflow": "ci"},
            ]

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/gh"),
                patch.object(git_provider_module, "_run", return_value=CommandResult(0, json.dumps(checks), "")),
            ):
                client = TestClient(create_app(workspace))
                response = client.post(f"/runs/{run.object_id}/review-checks/refresh")

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["run"], run.object_id)
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["source"], "github-cli")
            self.assertTrue((run_dir / "checks.json").exists())

            refreshed = load_workspace(workspace)
            outputs = refreshed.runs[run.object_id].spec.outputs
            self.assertTrue([output for output in outputs if output.get("type") == "check_status" and output.get("status") == "failed"])
            self.assertIn("checks.refreshed", [event["type"] for event in refreshed.run_events[run.object_id]])

            gate_response = TestClient(create_app(workspace)).get(f"/runs/{run.object_id}/review-gate")
            self.assertEqual(gate_response.status_code, 200, gate_response.text)
            gate = gate_response.json()
            self.assertFalse(gate["readyForHumanReview"])
            external_checks = [check for check in gate["checks"] if check["name"] == "external-checks"]
            self.assertTrue(external_checks)
            self.assertEqual(external_checks[0]["status"], "fail")
            self.assertIn("failed", external_checks[0]["message"])

    def test_api_refreshes_gitlab_run_review_target_checks_for_review_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            task = create_task(
                workspace,
                title="Refresh GitLab provider review checks",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
            )
            time.sleep(0.01)
            run = create_run(workspace, task_id=task.object_id)
            run_dir = workspace / "runs" / run.object_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "journal.md").write_text("Reviewed GitLab provider check refresh.\n", encoding="utf-8")
            (run_dir / "diff.patch").write_text(
                "\n".join(
                    [
                        "diff --git a/packages/workspace/provider.txt b/packages/workspace/provider.txt",
                        "new file mode 100644",
                        "index 0000000..e69de29",
                        "--- /dev/null",
                        "+++ b/packages/workspace/provider.txt",
                        "@@ -0,0 +1 @@",
                        "+provider check",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            update_run(
                workspace,
                run.object_id,
                {
                    "status": "REVIEW",
                    "journal": "journal.md",
                    "reviewTarget": {
                        "type": "pull_request",
                        "url": "https://gitlab.com/example/aiteamos/-/merge_requests/7",
                        "ref": "aiteamos/provider-checks",
                    },
                },
            )
            merge_request = {
                "headPipeline": {
                    "id": 72,
                    "status": "success",
                    "ref": "aiteamos/provider-checks",
                    "webUrl": "https://gitlab.com/example/aiteamos/-/pipelines/72",
                },
            }

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/glab"),
                patch.object(git_provider_module, "_run", return_value=CommandResult(0, json.dumps(merge_request), "")) as run_command,
            ):
                client = TestClient(create_app(workspace))
                response = client.post(f"/runs/{run.object_id}/review-checks/refresh")

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["run"], run.object_id)
            self.assertEqual(payload["status"], "passed")
            self.assertEqual(payload["source"], "gitlab-cli")
            self.assertEqual(payload["checks"][0]["bucket"], "pass")
            self.assertEqual(run_command.call_args.args[0], ["glab", "mr", "view", "7", "--output", "json"])
            self.assertTrue((run_dir / "checks.json").exists())

            refreshed = load_workspace(workspace)
            outputs = refreshed.runs[run.object_id].spec.outputs
            self.assertTrue([output for output in outputs if output.get("type") == "check_status" and output.get("status") == "passed"])
            self.assertIn("checks.refreshed", [event["type"] for event in refreshed.run_events[run.object_id]])

            gate_response = TestClient(create_app(workspace)).get(f"/runs/{run.object_id}/review-gate")
            self.assertEqual(gate_response.status_code, 200, gate_response.text)
            gate = gate_response.json()
            external_checks = [check for check in gate["checks"] if check["name"] == "external-checks"]
            self.assertTrue(external_checks)
            self.assertEqual(external_checks[0]["status"], "pass")
            self.assertIn("passed", external_checks[0]["message"])

    def test_api_requests_non_fast_forward_source_integration_remediation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            repo = _init_repo(temp_root / "repo")
            _point_workspace_repository_at(workspace, repo)
            (repo / "packages" / "workspace").mkdir(parents=True)
            source_file = repo / "packages" / "workspace" / "provider.txt"
            source_file.write_text("base\n", encoding="utf-8")
            _git(repo, ["add", "packages/workspace/provider.txt"])
            _git(repo, ["commit", "-m", "add provider fixture"])

            task = create_task(
                workspace,
                title="Non fast-forward source integration",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
            )
            time.sleep(0.01)
            run = create_run(workspace, task_id=task.object_id)
            worker_branch = run.spec.branch.name
            _git(repo, ["checkout", "-b", worker_branch])
            source_file.write_text("worker branch\n", encoding="utf-8")
            _git(repo, ["add", "packages/workspace/provider.txt"])
            _git(repo, ["commit", "-m", "worker source change"])
            _git(repo, ["checkout", "main"])
            source_file.write_text("source branch advanced\n", encoding="utf-8")
            _git(repo, ["add", "packages/workspace/provider.txt"])
            _git(repo, ["commit", "-m", "advance source branch"])
            before_source = source_file.read_text(encoding="utf-8")

            worktree = workspace / "artifacts" / "worktrees" / run.object_id
            worktree.parent.mkdir(parents=True, exist_ok=True)
            _git(repo, ["worktree", "add", str(worktree), worker_branch])
            diff = subprocess.run(
                ["git", "diff", f"main..{worker_branch}", "--", "packages/workspace/provider.txt"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            run_dir = workspace / "runs" / run.object_id
            (run_dir / "diff.patch").write_text(diff, encoding="utf-8")
            update_run(
                workspace,
                run.object_id,
                {
                    "status": "REVIEW",
                    "worktree": str(worktree),
                    "worker": {"stage": "review", "worktree": str(worktree), "branch": worker_branch},
                    "reviewTarget": {"type": "branch", "ref": worker_branch, "description": "Review the worker branch before source integration."},
                },
            )

            client = TestClient(create_app(workspace))
            review_response = client.post(
                f"/runs/{run.object_id}/reviews",
                json={
                    "reviewerMember": "frontend-human",
                    "verdict": "approved",
                    "summary": "Approved the worker branch before source integration remediation.",
                },
            )
            self.assertEqual(review_response.status_code, 200, review_response.text)
            closeout_response = client.post(
                f"/runs/{run.object_id}/closeout",
                json={"actorMember": "frontend-human", "reason": "Close reviewed branch before source integration remediation."},
            )
            self.assertEqual(closeout_response.status_code, 200, closeout_response.text)

            gate_response = client.get(
                f"/runs/{run.object_id}/source-integration-gate",
                params={"actorMember": "frontend-human"},
            )
            self.assertEqual(gate_response.status_code, 200, gate_response.text)
            gate = gate_response.json()
            self.assertFalse(gate["readyForSourceIntegration"])
            self.assertTrue(any(check["name"] == "fast-forward" and check["status"] == "fail" for check in gate["checks"]))

            remediation_response = client.post(
                f"/runs/{run.object_id}/source-integration-remediation",
                json={"actorMember": "frontend-human", "reason": "Source branch advanced; request a follow-up review target."},
            )
            self.assertEqual(remediation_response.status_code, 200, remediation_response.text)
            remediation = remediation_response.json()["spec"]["sourceIntegration"]
            self.assertEqual(remediation["status"], "remediation-requested")
            self.assertEqual(remediation["strategy"], "conflict-resolution-worktree")
            self.assertEqual(remediation["sourceBranch"], "main")
            self.assertEqual(remediation["workerBranch"], worker_branch)
            self.assertTrue(remediation["remediationBranch"].startswith("aiteamos/remediation/"))
            self.assertEqual(remediation["mergeStatus"], "conflicts-detected")
            self.assertEqual(remediation["conflictFiles"], ["packages/workspace/provider.txt"])
            self.assertEqual(remediation["conflictResolution"]["status"], "conflicts-detected")
            self.assertEqual(remediation["conflictResolution"]["sourceSha"], remediation["sourceSha"])
            self.assertEqual(remediation["conflictResolution"]["workerSha"], remediation["workerSha"])
            self.assertEqual(remediation["remediationReviewTarget"]["type"], "branch")
            self.assertEqual(remediation["remediationReviewTarget"]["ref"], remediation["remediationBranch"])
            self.assertEqual(remediation["decisionAudit"][0]["source"], "run-source-integration-remediation")
            self.assertEqual(source_file.read_text(encoding="utf-8"), before_source)
            remediation_worktree = Path(remediation["remediationWorktree"])
            self.assertTrue(remediation_worktree.exists())
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=remediation_worktree,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertIn("UU packages/workspace/provider.txt", status)

            refreshed = load_workspace(workspace)
            self.assertEqual(refreshed.runs[run.object_id].spec.sourceIntegration["status"], "remediation-requested")
            remediation_events = [
                event for event in refreshed.run_events[run.object_id] if event["type"] == "run.source_integration_remediation_requested"
            ]
            self.assertTrue(remediation_events)
            self.assertEqual(remediation_events[-1]["remediationBranch"], remediation["remediationBranch"])

    def test_api_requests_provider_source_integration_without_merging_provider_pr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            task = create_task(
                workspace,
                title="Provider source integration request",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
            )
            time.sleep(0.01)
            run = create_run(workspace, task_id=task.object_id)
            run_dir = workspace / "runs" / run.object_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "journal.md").write_text("Reviewed provider source integration request.\n", encoding="utf-8")
            (run_dir / "diff.patch").write_text(
                "\n".join(
                    [
                        "diff --git a/packages/workspace/provider_pr.txt b/packages/workspace/provider_pr.txt",
                        "new file mode 100644",
                        "index 0000000..e69de29",
                        "--- /dev/null",
                        "+++ b/packages/workspace/provider_pr.txt",
                        "@@ -0,0 +1 @@",
                        "+provider integration",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            update_run(
                workspace,
                run.object_id,
                {
                    "status": "REVIEW",
                    "journal": "journal.md",
                    "reviewTarget": {
                        "type": "pull_request",
                        "provider": "github",
                        "url": "https://github.com/example/aiteamos/pull/9",
                        "ref": "aiteamos/provider-source-integration",
                    },
                },
            )
            passed_checks = [
                {"bucket": "pass", "name": "lint", "state": "SUCCESS"},
                {"bucket": "pass", "name": "unit", "state": "SUCCESS"},
            ]
            client = TestClient(create_app(workspace))
            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/gh"),
                patch.object(git_provider_module, "_run", return_value=CommandResult(0, json.dumps(passed_checks), "")),
            ):
                checks_response = client.post(f"/runs/{run.object_id}/review-checks/refresh")
            self.assertEqual(checks_response.status_code, 200, checks_response.text)
            self.assertEqual(checks_response.json()["status"], "passed")

            review_response = client.post(
                f"/runs/{run.object_id}/reviews",
                json={
                    "reviewerMember": "frontend-human",
                    "verdict": "approved",
                    "summary": "Approved the provider pull request after checks passed.",
                },
            )
            self.assertEqual(review_response.status_code, 200, review_response.text)
            closeout_response = client.post(
                f"/runs/{run.object_id}/closeout",
                json={"actorMember": "frontend-human", "reason": "Close reviewed PR before provider source integration request."},
            )
            self.assertEqual(closeout_response.status_code, 200, closeout_response.text)

            with patch.object(GitCliProvider, "merge_pull_request", side_effect=AssertionError("provider merge must not be called")):
                provider_response = client.post(
                    f"/runs/{run.object_id}/provider-source-integration",
                    json={"actorMember": "frontend-human", "reason": "Queue provider merge request after reviewed closeout."},
                )
            self.assertEqual(provider_response.status_code, 200, provider_response.text)
            source_integration = provider_response.json()["spec"]["sourceIntegration"]
            self.assertEqual(source_integration["status"], "provider-integration-requested")
            self.assertEqual(source_integration["strategy"], "provider-review-target")
            self.assertEqual(source_integration["provider"], "github")
            self.assertEqual(source_integration["reviewTarget"]["type"], "pull_request")
            self.assertEqual(source_integration["providerChecks"]["status"], "passed")
            self.assertEqual(source_integration["decisionAudit"][0]["source"], "run-provider-source-integration")

            refreshed = load_workspace(workspace)
            self.assertEqual(refreshed.runs[run.object_id].spec.sourceIntegration["status"], "provider-integration-requested")
            self.assertIn("run.provider_source_integration_requested", [event["type"] for event in refreshed.run_events[run.object_id]])

            with patch.object(GitCliProvider, "merge_pull_request", side_effect=AssertionError("dry-run must not call provider merge")):
                dry_run_response = client.post(
                    f"/runs/{run.object_id}/provider-source-integration/execute",
                    json={"actorMember": "frontend-human", "reason": "Preflight provider merge request.", "dryRun": True},
                )
            self.assertEqual(dry_run_response.status_code, 200, dry_run_response.text)
            dry_run_integration = dry_run_response.json()["spec"]["sourceIntegration"]
            self.assertEqual(dry_run_integration["status"], "provider-integration-requested")
            self.assertEqual(dry_run_integration["providerExecution"]["status"], "dry-run-passed")
            self.assertTrue(dry_run_integration["providerExecution"]["dryRun"])
            self.assertEqual(dry_run_integration["providerExecution"]["decisionAudit"][0]["source"], "run-provider-source-integration-execution")

            with patch.object(
                GitCliProvider,
                "merge_pull_request",
                side_effect=NotImplementedError("provider merge is not configured"),
            ) as merge:
                unsupported_response = client.post(
                    f"/runs/{run.object_id}/provider-source-integration/execute",
                    json={"actorMember": "frontend-human", "reason": "Attempt provider merge after preflight.", "dryRun": False},
                )
            self.assertEqual(unsupported_response.status_code, 200, unsupported_response.text)
            merge.assert_called_once()
            unsupported_integration = unsupported_response.json()["spec"]["sourceIntegration"]
            self.assertEqual(unsupported_integration["status"], "provider-integration-requested")
            self.assertEqual(unsupported_integration["providerExecution"]["status"], "unsupported")
            self.assertFalse(unsupported_integration["providerExecution"]["dryRun"])
            self.assertIn("not configured", unsupported_integration["providerExecution"]["error"])
            self.assertEqual(len(unsupported_integration["providerExecutionHistory"]), 2)

            refreshed_after_execution = load_workspace(workspace)
            event_types = [event["type"] for event in refreshed_after_execution.run_events[run.object_id]]
            self.assertIn("run.provider_source_integration_preflight_passed", event_types)
            self.assertIn("run.provider_source_integration_execution_unsupported", event_types)

    def test_api_executes_github_provider_source_integration_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            repo = _init_repo(temp_root / "repo")
            origin = temp_root / "origin.git"
            _git(temp_root, ["init", "--bare", str(origin)])
            _git(repo, ["remote", "add", "origin", str(origin)])
            _git(repo, ["push", "-u", "origin", "main"])
            _git(origin, ["symbolic-ref", "HEAD", "refs/heads/main"])
            remote_work = temp_root / "remote-work"
            _git(temp_root, ["clone", str(origin), str(remote_work)])
            _git(remote_work, ["config", "user.email", "aiteamos@example.invalid"])
            _git(remote_work, ["config", "user.name", "AITEAMOS Provider Test"])
            (remote_work / "provider_pr.txt").write_text("merged by GitHub provider\n", encoding="utf-8")
            _git(remote_work, ["add", "provider_pr.txt"])
            _git(remote_work, ["commit", "-m", "simulate GitHub provider merge"])
            _git(remote_work, ["push", "origin", "main"])
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=remote_work,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            _point_workspace_repository_at(workspace, repo)

            task = create_task(
                workspace,
                title="GitHub provider source integration success",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
            )
            time.sleep(0.01)
            run = create_run(workspace, task_id=task.object_id)
            run_dir = workspace / "runs" / run.object_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "journal.md").write_text("Reviewed GitHub provider source integration request.\n", encoding="utf-8")
            (run_dir / "diff.patch").write_text(
                "\n".join(
                    [
                        "diff --git a/packages/workspace/provider_pr.txt b/packages/workspace/provider_pr.txt",
                        "new file mode 100644",
                        "index 0000000..e69de29",
                        "--- /dev/null",
                        "+++ b/packages/workspace/provider_pr.txt",
                        "@@ -0,0 +1 @@",
                        "+provider integration",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "checks.json").write_text(
                json.dumps({"status": "passed", "summary": "GitHub checks passed.", "checks": [{"name": "unit", "bucket": "pass"}]}),
                encoding="utf-8",
            )
            update_run(
                workspace,
                run.object_id,
                {
                    "status": "REVIEW",
                    "journal": "journal.md",
                    "reviewTarget": {
                        "type": "pull_request",
                        "provider": "github",
                        "url": "https://github.com/example/aiteamos/pull/9",
                        "ref": "aiteamos/provider-source-integration",
                    },
                },
            )

            client = TestClient(create_app(workspace))
            review_response = client.post(
                f"/runs/{run.object_id}/reviews",
                json={
                    "reviewerMember": "frontend-human",
                    "verdict": "approved",
                    "summary": "Approved the GitHub pull request after checks passed.",
                },
            )
            self.assertEqual(review_response.status_code, 200, review_response.text)
            closeout_response = client.post(
                f"/runs/{run.object_id}/closeout",
                json={"actorMember": "frontend-human", "reason": "Close reviewed GitHub PR before provider integration."},
            )
            self.assertEqual(closeout_response.status_code, 200, closeout_response.text)
            provider_response = client.post(
                f"/runs/{run.object_id}/provider-source-integration",
                json={"actorMember": "frontend-human", "reason": "Queue GitHub provider merge after reviewed closeout."},
            )
            self.assertEqual(provider_response.status_code, 200, provider_response.text)
            original_run = git_provider_module._run

            def run_command(command: list[str], **kwargs: object) -> CommandResult:
                if command[:3] == ["gh", "pr", "merge"]:
                    return CommandResult(0, "Merged pull request #9\n", "")
                return original_run(command, **kwargs)

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/gh"),
                patch.object(git_provider_module, "_run", side_effect=run_command) as run_command_mock,
            ):
                execute_response = client.post(
                    f"/runs/{run.object_id}/provider-source-integration/execute",
                    json={"actorMember": "frontend-human", "reason": "Execute reviewed GitHub provider merge.", "dryRun": False},
                )

            self.assertEqual(execute_response.status_code, 200, execute_response.text)
            gh_calls = [call for call in run_command_mock.call_args_list if call.args[0][:3] == ["gh", "pr", "merge"]]
            self.assertEqual(len(gh_calls), 1)
            integration = execute_response.json()["spec"]["sourceIntegration"]
            self.assertEqual(integration["status"], "provider-integrated")
            execution = integration["providerExecution"]
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(execution["provider"], "github")
            self.assertFalse(execution["dryRun"])
            self.assertEqual(execution["providerResult"]["provider"], "github")
            self.assertEqual(execution["providerResult"]["url"], "https://github.com/example/aiteamos/pull/9")
            self.assertEqual(execution["providerResult"]["stdout"], "Merged pull request #9")
            self.assertTrue(execution["providerResult"]["sourceSynced"])
            self.assertEqual(execution["providerResult"]["sourceSyncStatus"], "fast-forwarded")
            self.assertEqual(execution["providerResult"]["remoteSha"], remote_sha)
            self.assertEqual((repo / "provider_pr.txt").read_text(encoding="utf-8"), "merged by GitHub provider\n")

            refreshed = load_workspace(workspace)
            self.assertEqual(refreshed.runs[run.object_id].spec.sourceIntegration["status"], "provider-integrated")
            self.assertIn("run.provider_source_integrated", [event["type"] for event in refreshed.run_events[run.object_id]])

    def test_api_executes_gitlab_provider_source_integration_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            repo = _init_repo(temp_root / "repo")
            origin = temp_root / "origin.git"
            _git(temp_root, ["init", "--bare", str(origin)])
            _git(repo, ["remote", "add", "origin", str(origin)])
            _git(repo, ["push", "-u", "origin", "main"])
            _git(origin, ["symbolic-ref", "HEAD", "refs/heads/main"])
            remote_work = temp_root / "remote-work"
            _git(temp_root, ["clone", str(origin), str(remote_work)])
            _git(remote_work, ["config", "user.email", "aiteamos@example.invalid"])
            _git(remote_work, ["config", "user.name", "AITEAMOS Provider Test"])
            (remote_work / "provider_pr.txt").write_text("merged by GitLab provider\n", encoding="utf-8")
            _git(remote_work, ["add", "provider_pr.txt"])
            _git(remote_work, ["commit", "-m", "simulate GitLab provider merge"])
            _git(remote_work, ["push", "origin", "main"])
            remote_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=remote_work,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            _point_workspace_repository_at(workspace, repo)

            task = create_task(
                workspace,
                title="GitLab provider source integration success",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
            )
            time.sleep(0.01)
            run = create_run(workspace, task_id=task.object_id)
            run_dir = workspace / "runs" / run.object_id
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "journal.md").write_text("Reviewed GitLab provider source integration request.\n", encoding="utf-8")
            (run_dir / "diff.patch").write_text(
                "\n".join(
                    [
                        "diff --git a/packages/workspace/provider_pr.txt b/packages/workspace/provider_pr.txt",
                        "new file mode 100644",
                        "index 0000000..e69de29",
                        "--- /dev/null",
                        "+++ b/packages/workspace/provider_pr.txt",
                        "@@ -0,0 +1 @@",
                        "+provider integration",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "checks.json").write_text(
                json.dumps({"status": "passed", "summary": "GitLab checks passed.", "checks": [{"name": "unit", "bucket": "pass"}]}),
                encoding="utf-8",
            )
            update_run(
                workspace,
                run.object_id,
                {
                    "status": "REVIEW",
                    "journal": "journal.md",
                    "reviewTarget": {
                        "type": "pull_request",
                        "url": "https://gitlab.com/example/aiteamos/-/merge_requests/9",
                        "ref": "aiteamos/provider-source-integration",
                    },
                },
            )

            client = TestClient(create_app(workspace))
            review_response = client.post(
                f"/runs/{run.object_id}/reviews",
                json={
                    "reviewerMember": "frontend-human",
                    "verdict": "approved",
                    "summary": "Approved the GitLab merge request after checks passed.",
                },
            )
            self.assertEqual(review_response.status_code, 200, review_response.text)
            closeout_response = client.post(
                f"/runs/{run.object_id}/closeout",
                json={"actorMember": "frontend-human", "reason": "Close reviewed GitLab MR before provider integration."},
            )
            self.assertEqual(closeout_response.status_code, 200, closeout_response.text)
            provider_response = client.post(
                f"/runs/{run.object_id}/provider-source-integration",
                json={"actorMember": "frontend-human", "reason": "Queue GitLab provider merge after reviewed closeout."},
            )
            self.assertEqual(provider_response.status_code, 200, provider_response.text)
            self.assertEqual(provider_response.json()["spec"]["sourceIntegration"]["provider"], "gitlab")
            original_run = git_provider_module._run

            def run_command(command: list[str], **kwargs: object) -> CommandResult:
                if command[:3] == ["glab", "mr", "merge"]:
                    return CommandResult(0, "Merged merge request !9\n", "")
                return original_run(command, **kwargs)

            with (
                patch.object(git_provider_module.shutil, "which", return_value="/usr/bin/glab"),
                patch.object(git_provider_module, "_run", side_effect=run_command) as run_command_mock,
            ):
                execute_response = client.post(
                    f"/runs/{run.object_id}/provider-source-integration/execute",
                    json={"actorMember": "frontend-human", "reason": "Execute reviewed GitLab provider merge.", "dryRun": False},
                )

            self.assertEqual(execute_response.status_code, 200, execute_response.text)
            glab_calls = [call for call in run_command_mock.call_args_list if call.args[0][:3] == ["glab", "mr", "merge"]]
            self.assertEqual(len(glab_calls), 1)
            self.assertEqual(glab_calls[0].args[0], ["glab", "mr", "merge", "9"])
            integration = execute_response.json()["spec"]["sourceIntegration"]
            self.assertEqual(integration["status"], "provider-integrated")
            execution = integration["providerExecution"]
            self.assertEqual(execution["status"], "succeeded")
            self.assertEqual(execution["provider"], "gitlab")
            self.assertFalse(execution["dryRun"])
            self.assertEqual(execution["providerResult"]["provider"], "gitlab")
            self.assertEqual(execution["providerResult"]["url"], "https://gitlab.com/example/aiteamos/-/merge_requests/9")
            self.assertEqual(execution["providerResult"]["stdout"], "Merged merge request !9")
            self.assertTrue(execution["providerResult"]["sourceSynced"])
            self.assertEqual(execution["providerResult"]["sourceSyncStatus"], "fast-forwarded")
            self.assertEqual(execution["providerResult"]["remoteSha"], remote_sha)
            self.assertEqual((repo / "provider_pr.txt").read_text(encoding="utf-8"), "merged by GitLab provider\n")

            refreshed = load_workspace(workspace)
            self.assertEqual(refreshed.runs[run.object_id].spec.sourceIntegration["status"], "provider-integrated")
            self.assertIn("run.provider_source_integrated", [event["type"] for event in refreshed.run_events[run.object_id]])

    def test_api_executes_local_provider_source_integration_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = temp_root / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            repo = _init_repo(temp_root / "repo")
            _point_workspace_repository_at(workspace, repo)
            (repo / "packages" / "workspace").mkdir(parents=True)
            source_file = repo / "packages" / "workspace" / "provider_pr.txt"
            source_file.write_text("base\n", encoding="utf-8")
            _git(repo, ["add", "packages/workspace/provider_pr.txt"])
            _git(repo, ["commit", "-m", "add local provider fixture"])

            task = create_task(
                workspace,
                title="Local provider source integration success",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
            )
            time.sleep(0.01)
            run = create_run(workspace, task_id=task.object_id)
            worker_branch = run.spec.branch.name
            _git(repo, ["checkout", "-b", worker_branch])
            source_file.write_text("integrated by local provider\n", encoding="utf-8")
            _git(repo, ["add", "packages/workspace/provider_pr.txt"])
            _git(repo, ["commit", "-m", "local provider source change"])
            target_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            _git(repo, ["checkout", "main"])
            before_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            run_dir = workspace / "runs" / run.object_id
            run_dir.mkdir(parents=True, exist_ok=True)
            diff = subprocess.run(
                ["git", "diff", f"main..{worker_branch}", "--", "packages/workspace/provider_pr.txt"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            (run_dir / "journal.md").write_text("Reviewed local provider source integration request.\n", encoding="utf-8")
            (run_dir / "diff.patch").write_text(diff, encoding="utf-8")
            (run_dir / "checks.json").write_text(
                json.dumps({"status": "passed", "summary": "Local provider checks passed.", "checks": [{"name": "unit", "bucket": "pass"}]}),
                encoding="utf-8",
            )
            update_run(
                workspace,
                run.object_id,
                {
                    "status": "REVIEW",
                    "journal": "journal.md",
                    "reviewTarget": {
                        "type": "pull_request",
                        "provider": "local-git",
                        "url": f"local-git://{run.object_id}",
                        "ref": worker_branch,
                    },
                },
            )

            client = TestClient(create_app(workspace))
            review_response = client.post(
                f"/runs/{run.object_id}/reviews",
                json={
                    "reviewerMember": "frontend-human",
                    "verdict": "approved",
                    "summary": "Approved the local provider pull request after checks passed.",
                },
            )
            self.assertEqual(review_response.status_code, 200, review_response.text)
            closeout_response = client.post(
                f"/runs/{run.object_id}/closeout",
                json={"actorMember": "frontend-human", "reason": "Close reviewed local provider PR before provider integration."},
            )
            self.assertEqual(closeout_response.status_code, 200, closeout_response.text)
            provider_response = client.post(
                f"/runs/{run.object_id}/provider-source-integration",
                json={"actorMember": "frontend-human", "reason": "Queue local provider merge after reviewed closeout."},
            )
            self.assertEqual(provider_response.status_code, 200, provider_response.text)
            self.assertEqual(source_file.read_text(encoding="utf-8"), "base\n")

            execute_response = client.post(
                f"/runs/{run.object_id}/provider-source-integration/execute",
                json={"actorMember": "frontend-human", "reason": "Execute reviewed local provider merge.", "dryRun": False},
            )

            self.assertEqual(execute_response.status_code, 200, execute_response.text)
            integration = execute_response.json()["spec"]["sourceIntegration"]
            self.assertEqual(integration["status"], "provider-integrated")
            execution = integration["providerExecution"]
            self.assertEqual(execution["status"], "succeeded")
            self.assertFalse(execution["dryRun"])
            self.assertEqual(execution["provider"], "local-git")
            self.assertEqual(execution["providerResult"]["beforeSha"], before_sha)
            self.assertEqual(execution["providerResult"]["targetSha"], target_sha)
            self.assertEqual(execution["providerResult"]["afterSha"], target_sha)
            self.assertEqual(source_file.read_text(encoding="utf-8"), "integrated by local provider\n")

            refreshed = load_workspace(workspace)
            self.assertEqual(refreshed.runs[run.object_id].spec.sourceIntegration["status"], "provider-integrated")
            self.assertIn("run.provider_source_integrated", [event["type"] for event in refreshed.run_events[run.object_id]])


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, ["init", "-b", "main"])
    _git(path, ["config", "user.email", "aiteamos@example.invalid"])
    _git(path, ["config", "user.name", "AITEAMOS Provider Test"])
    (path / "README.md").write_text("# Provider Test\n", encoding="utf-8")
    _git(path, ["add", "README.md"])
    _git(path, ["commit", "-m", "initial"])
    return path


def _point_workspace_repository_at(workspace: Path, repo: Path) -> None:
    path = workspace / "repositories" / "aiteamos.yaml"
    data = read_yaml(path)
    data.setdefault("spec", {})["localPath"] = str(repo)
    data["spec"]["url"] = repo.as_uri()
    data["spec"]["defaultBranch"] = "main"
    write_yaml(path, data)


def _git(cwd: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
