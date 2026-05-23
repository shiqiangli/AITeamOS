from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

from aiteamos_workspace import (
    approve_permission_request,
    create_model_profile,
    create_run,
    create_task,
    execute_run_with_model,
    execute_worker_run,
    evaluate_model_execution_readiness,
    evaluate_run_review_gate,
    evaluate_worker_authorization,
    evaluate_worker_readiness,
    has_verification_failure,
    inspect_worker_recovery,
    load_workspace,
    request_run_worker_permission,
    run_verification_commands,
    update_run,
)
from aiteamos_workspace.gitops import validate_patch_permissions, validate_patch_scope


REPO_ROOT = Path(__file__).resolve().parents[1]


class WorkerSafetyTest(unittest.TestCase):
    def test_managed_model_executor_rejects_assisted_and_manual_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = _create_backend_task(workspace, "Assisted mode model guard", ["no direct model call"])
            run = create_run(workspace, task_id=task.object_id, mode="assisted")

            with self.assertRaisesRegex(ValueError, "not managed_llm"):
                execute_run_with_model(workspace, run.object_id)

            events = load_workspace(workspace).run_events[run.object_id]
            self.assertTrue([event for event in events if event["type"] == "model.execution.blocked" and event["mode"] == "assisted"])

    def test_managed_worker_modes_require_matching_member_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Human member cannot start managed LLM",
                assigned_member="frontend-human",
                assignment="aiteamos-dashboard",
                acceptance=["blocked"],
            )
            create_model_profile(workspace, name="manual-profile", provider="local", model="manual")
            run = create_run(workspace, task_id=task.object_id, model_profile="manual-profile", mode="managed_llm")

            readiness = evaluate_worker_readiness(workspace, run.object_id)
            authorization = evaluate_worker_authorization(workspace, run.object_id)
            model_readiness = evaluate_model_execution_readiness(workspace, run.object_id)

            self.assertFalse(readiness["ready"])
            self.assertTrue([check for check in readiness["checks"] if check["name"] == "run-mode-member-kind" and check["status"] == "fail"])
            self.assertFalse(authorization["ready"])
            self.assertTrue([check for check in authorization["checks"] if check["name"] == "worker-auth-mode-member-kind" and check["status"] == "fail"])
            self.assertFalse(model_readiness["ready"])
            self.assertTrue([check for check in model_readiness["checks"] if check["name"] == "run-mode-member-kind" and check["status"] == "fail"])

    def test_service_mode_uses_automation_control_plane_not_generic_worker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Service mode stays in automation control plane",
                assigned_member="memory-service",
                assignment="aiteamos-memory-service",
                acceptance=["blocked from generic worker"],
            )
            run = create_run(workspace, task_id=task.object_id, mode="service")

            readiness = evaluate_worker_readiness(workspace, run.object_id)
            authorization = evaluate_worker_authorization(workspace, run.object_id)

            self.assertFalse(readiness["ready"])
            self.assertTrue([check for check in readiness["checks"] if check["name"] == "run-mode" and check["status"] == "fail"])
            self.assertFalse(authorization["ready"])
            self.assertTrue([check for check in authorization["checks"] if check["name"] == "worker-auth-mode" and check["status"] == "fail"])

    def test_worker_start_blocks_missing_write_scope_before_worktree_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _clear_assignment_write_scope(workspace, "aiteamos-backend-runtime")
            task = _create_backend_task(workspace, "No write scope worker", ["blocked"])
            create_model_profile(workspace, name="manual-profile", provider="local", model="manual")
            run = create_run(workspace, task_id=task.object_id, model_profile="manual-profile", mode="managed_llm")

            with self.assertRaises(ValueError):
                execute_worker_run(workspace, run.object_id)

            index = load_workspace(workspace)
            self.assertEqual(index.runs[run.object_id].spec.status, "READY")
            self.assertFalse((workspace / "artifacts" / "worktrees" / run.object_id).exists())
            self.assertTrue([event for event in index.run_events[run.object_id] if event["type"] == "worker.start.blocked"])

    def test_patch_scope_blocks_empty_scope_and_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _clear_assignment_write_scope(workspace, "aiteamos-backend-runtime")
            task = _create_backend_task(workspace, "Patch scope worker", ["blocked"])
            create_model_profile(workspace, name="manual-profile", provider="local", model="manual")
            run = create_run(workspace, task_id=task.object_id, model_profile="manual-profile", mode="managed_llm")
            diff_text = "\n".join(
                [
                    "diff --git a/.aiteamos/tasks/x.yaml b/.aiteamos/tasks/x.yaml",
                    "--- a/.aiteamos/tasks/x.yaml",
                    "+++ b/.aiteamos/tasks/x.yaml",
                    "@@ -1 +1 @@",
                    "-old",
                    "+new",
                    "diff --git a/../escape.txt b/../escape.txt",
                    "--- a/../escape.txt",
                    "+++ b/../escape.txt",
                    "@@ -1 +1 @@",
                    "-old",
                    "+new",
                ]
            )

            violations = validate_patch_scope(load_workspace(workspace), run.object_id, diff_text)

            self.assertTrue([item for item in violations if "no explicit write scope" in item])
            self.assertTrue([item for item in violations if ".aiteamos changes" in item])
            self.assertTrue([item for item in violations if "unsafe patch path" in item])

    def test_review_gate_requires_diff_for_code_review_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = _create_backend_task(workspace, "Review gate diff source", ["scope checked"])
            run = create_run(workspace, task_id=task.object_id)
            update_run(workspace, run.object_id, {"status": "REVIEW", "reviewTarget": {"type": "branch", "ref": "feature/no-diff"}})

            missing_diff_gate = evaluate_run_review_gate(workspace, run.object_id)

            self.assertFalse(missing_diff_gate["readyForHumanReview"])
            self.assertEqual(missing_diff_gate["member"], "backend-digital")
            self.assertEqual(missing_diff_gate["assignment"], "aiteamos-backend-runtime")
            self.assertTrue([check for check in missing_diff_gate["checks"] if check["name"] == "scope" and check["status"] == "fail"])

            reviewable_run = create_run(workspace, task_id=task.object_id)
            worktree = _init_scoped_repo(workspace / "artifacts" / "worktrees" / reviewable_run.object_id)
            (worktree / "packages" / "workspace" / "review_gate.txt").write_text("after\n", encoding="utf-8")
            subprocess.run(["git", "add", "packages/workspace/review_gate.txt"], cwd=worktree, check=True)
            subprocess.run(["git", "commit", "-m", "review gate scoped change"], cwd=worktree, check=True, capture_output=True, text=True)
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=worktree, check=True, capture_output=True, text=True).stdout.strip()
            update_run(
                workspace,
                reviewable_run.object_id,
                {
                    "status": "REVIEW",
                    "worktree": str(worktree),
                    "reviewTarget": {"type": "commit", "ref": sha},
                },
            )

            derived_diff_gate = evaluate_run_review_gate(workspace, reviewable_run.object_id)

            self.assertTrue(derived_diff_gate["readyForHumanReview"])
            self.assertTrue([check for check in derived_diff_gate["checks"] if check["name"] == "diff-source" and check["status"] == "pass"])
            self.assertTrue([check for check in derived_diff_gate["checks"] if check["name"] == "scope" and check["status"] == "pass"])

    def test_verification_command_policy_blocks_privileged_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = _copy_workspace(temp_root)
            task = _create_backend_task(workspace, "Command policy worker", ["blocked"])
            create_model_profile(workspace, name="manual-profile", provider="local", model="manual")
            run = create_run(workspace, task_id=task.object_id, model_profile="manual-profile", mode="managed_llm")

            results = run_verification_commands(
                workspace,
                run.object_id,
                worktree=temp_root,
                commands=["git push origin HEAD", "python3 -c 'print(1)'"],
            )

            self.assertTrue(has_verification_failure(results))
            self.assertEqual(results[0].returncode, 126)
            self.assertEqual(results[1].returncode, 126)
            self.assertEqual(results[1].permissionDecision["decision"], "deny")
            self.assertIn("non-interactive", results[1].permissionDecision["reason"])
            events = load_workspace(workspace).run_events[run.object_id]
            self.assertTrue([event for event in events if event["type"] == "command.blocked"])

    def test_worker_authorization_explains_command_permission_denial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = _create_backend_task(workspace, "Command permission worker", ["permission explained"])
            create_model_profile(workspace, name="manual-profile", provider="local", model="manual")
            run = create_run(workspace, task_id=task.object_id, model_profile="manual-profile", mode="managed_llm")
            update_run(workspace, run.object_id, {"worker": {"verificationCommands": ["python3 -c 'print(1)'"]}})

            authorization = evaluate_worker_authorization(workspace, run.object_id)

            self.assertFalse(authorization["ready"])
            self.assertTrue([check for check in authorization["checks"] if check["name"] == "worker-auth-action-bash" and check["status"] == "fail"])
            self.assertEqual(authorization["permissionDecisions"][0]["action"]["canonical"], "Bash(python3 -c 'print(1)')")
            self.assertEqual(authorization["permissionDecisions"][0]["decision"], "deny")
            self.assertTrue(authorization["permissionApprovalRequired"])
            self.assertEqual(authorization["permissionApprovalOutcome"], "request-required")
            permission_request = request_run_worker_permission(
                workspace,
                run.object_id,
                actor_member="frontend-human",
                action_canonical="Bash(python3 -c 'print(1)')",
                dry_run=False,
            )["permissionRequest"]
            self.assertEqual(permission_request["kind"], "PermissionRequest")
            self.assertEqual(permission_request["spec"]["source"], "run-worker-authorization-permission-request")
            self.assertEqual(permission_request["spec"]["run"], run.object_id)
            self.assertEqual(permission_request["spec"]["action"]["canonical"], "Bash(python3 -c 'print(1)')")
            pending_authorization = evaluate_worker_authorization(workspace, run.object_id)
            self.assertEqual(pending_authorization["pendingPermissionRequestIds"], [permission_request["id"]])
            approve_permission_request(workspace, permission_request["id"], reviewer_member="frontend-human")
            approved_authorization = evaluate_worker_authorization(workspace, run.object_id)
            self.assertEqual(approved_authorization["permissionDecisions"][0]["decision"], "allow")
            self.assertFalse(approved_authorization["permissionApprovalRequired"])

    def test_worker_patch_permission_denies_unapproved_edit_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = _create_backend_task(workspace, "Patch permission worker", ["permission checked"])
            create_model_profile(workspace, name="manual-profile", provider="local", model="manual")
            run = create_run(workspace, task_id=task.object_id, model_profile="manual-profile", mode="managed_llm")
            diff_text = "\n".join(
                [
                    "diff --git a/packages/workspace/worker_permission.txt b/packages/workspace/worker_permission.txt",
                    "new file mode 100644",
                    "--- /dev/null",
                    "+++ b/packages/workspace/worker_permission.txt",
                    "@@ -0,0 +1 @@",
                    "+permission coverage",
                    "",
                ]
            )

            violations, decisions = validate_patch_permissions(load_workspace(workspace), run.object_id, diff_text)

            self.assertTrue(violations)
            self.assertIn("edit denied by effective permissions", violations[0])
            self.assertEqual(decisions[0]["decision"], "deny")
            self.assertIn("non-interactive", decisions[0]["reason"])

    def test_recovery_requires_manual_investigation_for_unmanaged_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = _copy_workspace(temp_root)
            task = _create_backend_task(workspace, "Recovery safety worker", ["manual investigation"])
            create_model_profile(workspace, name="manual-profile", provider="local", model="manual")
            run = create_run(workspace, task_id=task.object_id, model_profile="manual-profile", mode="managed_llm")
            fake_worktree = _init_repo(temp_root / "external-worktree")
            (fake_worktree / "recovered.txt").write_text("after\n", encoding="utf-8")
            update_run(
                workspace,
                run.object_id,
                {"status": "STALLED", "worktree": str(fake_worktree), "worker": {"worktree": str(fake_worktree), "stage": "stalled"}},
            )

            report = inspect_worker_recovery(workspace, run.object_id)

            self.assertEqual(report["recommendation"], "manual-investigation")
            self.assertFalse(report["worktreeManaged"])
            self.assertTrue(report["worktreeViolations"])
            self.assertFalse(report["reviewable"])


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _create_backend_task(workspace: Path, title: str, acceptance: list[str]) -> object:
    return create_task(
        workspace,
        title=title,
        assigned_member="backend-digital",
        assignment="aiteamos-backend-runtime",
        acceptance=acceptance,
    )


def _clear_assignment_write_scope(workspace: Path, assignment: str) -> None:
    path = workspace / "assignments" / f"{assignment}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("spec", {}).setdefault("scope", {})["write"] = []
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "aiteamos@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "AITEAMOS Test"], cwd=path, check=True)
    (path / "recovered.txt").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "recovered.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True, text=True)
    return path


def _init_scoped_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "aiteamos@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "AITEAMOS Test"], cwd=path, check=True)
    (path / "packages" / "workspace").mkdir(parents=True)
    (path / "packages" / "workspace" / "review_gate.txt").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "packages/workspace/review_gate.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=path, check=True, capture_output=True, text=True)
    return path


if __name__ == "__main__":
    unittest.main()
