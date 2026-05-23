from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient
import yaml

from aiteamos_api import create_app
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_workspace import (
    approve_permission_request,
    create_model_profile,
    create_permission_request,
    create_run,
    create_task,
    edit_action,
    explain_effective_permissions,
    load_workspace,
)
from aiteamos_workspace.executor import ModelExecutionResult
import aiteamos_workspace.worker as worker_module


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"
VERIFY_COMMAND = "python -c \"from pathlib import Path; assert Path('packages/workspace/golden_worker.txt').read_text().strip() == 'after golden worker'\""
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class DigitalWorkerGoldenRunApiTest(unittest.TestCase):
    def test_worker_start_api_produces_reviewable_golden_run_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            temp_root = Path(temp_dir)
            workspace = _copy_workspace(temp_root)
            repository = _init_source_repo(temp_root / "source")
            _point_workspace_repository_at(workspace, repository)
            _allow_local_manual_model(workspace)

            task = create_task(
                workspace,
                title="Digital worker golden path",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                execution_mode="managed_llm",
                acceptance=["worker records diff, test log, review target, journal, and memory proposal"],
            )
            create_model_profile(
                workspace,
                name="manual-worker",
                provider="local",
                model="manual",
                capabilities=["managed_llm"],
            )
            run = create_run(
                workspace,
                task_id=task.object_id,
                model_profile="manual-worker",
                mode="managed_llm",
                extra_spec={"worker": {"verificationCommands": [VERIFY_COMMAND], "commandTimeoutSeconds": 30}},
            )
            _approve_run_permission(workspace, run.object_id, task.object_id, {"tool": "Bash", "command": VERIFY_COMMAND})
            _approve_run_permission(workspace, run.object_id, task.object_id, edit_action("packages/workspace/golden_worker.txt"))
            client = TestClient(create_app(workspace))

            with patch("aiteamos_api.routes.execute_run_with_model") as execute_model:
                execute_model.return_value = None
                model_response = client.post(f"/runs/{run.object_id}/model/execute")

            self.assertEqual(model_response.status_code, 200, model_response.text)
            execute_model.assert_called_once_with(workspace, run.object_id)

            with patch.object(worker_module, "call_model_with_prompt", side_effect=_fake_worker_model):
                response = client.post(f"/runs/{run.object_id}/worker/start", json={"createPr": False})

            self.assertEqual(response.status_code, 200, response.text)
            run_record = response.json()
            self.assertEqual(run_record["spec"]["status"], "REVIEW")
            self.assertEqual(run_record["spec"]["reviewTarget"]["type"], "branch")
            self.assertTrue(run_record["journal"])

            updated = load_workspace(workspace)
            updated_run = updated.runs[run.object_id]
            self.assertEqual(updated_run.spec.status, "REVIEW")
            self.assertEqual(updated.tasks[task.object_id].spec.status, "REVIEW")
            self.assertEqual(updated_run.spec.worker["stage"], "review")
            self.assertTrue(updated_run.spec.worker["attemptId"].startswith(f"{run.object_id}-ATTEMPT-"))
            self.assertTrue(str(updated_run.spec.worktree).startswith(str(workspace / "artifacts" / "worktrees" / run.object_id)))
            self.assertTrue((workspace / "runs" / run.object_id / "worker_output.md").exists())
            self.assertTrue((workspace / "runs" / run.object_id / "diff.patch").exists())
            self.assertTrue((workspace / "runs" / run.object_id / "test.log").exists())
            self.assertTrue((workspace / "runs" / run.object_id / "command_results.jsonl").exists())
            self.assertIn("after golden worker", (workspace / "runs" / run.object_id / "diff.patch").read_text(encoding="utf-8"))
            self.assertIn("Memory proposal:", updated.run_journals[run.object_id])

            output_types = {item["type"] for item in updated_run.spec.outputs if isinstance(item, dict)}
            self.assertIn("worker_output", output_types)
            self.assertIn("diff_patch", output_types)
            self.assertIn("test_log", output_types)
            self.assertIn("command_log", output_types)
            self.assertIn("review_target", output_types)
            event_types = [event["type"] for event in updated.run_events[run.object_id]]
            self.assertIn("worker.started", event_types)
            self.assertIn("model.call.started", event_types)
            self.assertIn("worker.patch.applied", event_types)
            self.assertIn("command.completed", event_types)
            self.assertIn("worker.commit", event_types)

            self.assertEqual(len(updated_run.spec.memoryProposals), 1)
            proposal_id = updated_run.spec.memoryProposals[0]
            proposal = updated.memory_proposals[proposal_id]
            self.assertEqual(proposal.spec.sourceRun, run.object_id)
            self.assertEqual(proposal.spec.sourceTask, task.object_id)
            self.assertEqual(proposal.spec.member, BACKEND_MEMBER)
            self.assertEqual(proposal.spec.assignment, BACKEND_ASSIGNMENT)

            worktree_file = Path(updated_run.spec.worktree) / "packages" / "workspace" / "golden_worker.txt"
            self.assertEqual(worktree_file.read_text(encoding="utf-8").strip(), "after golden worker")


def _fake_worker_model(profile: object, prompt: str) -> ModelExecutionResult:
    assert "# Context Capsule:" in prompt
    return ModelExecutionResult(
        text="""## Summary
Prepared a bounded golden worker change for review.

```diff
diff --git a/packages/workspace/golden_worker.txt b/packages/workspace/golden_worker.txt
--- a/packages/workspace/golden_worker.txt
+++ b/packages/workspace/golden_worker.txt
@@ -1 +1 @@
-before golden worker
+after golden worker
```

Memory proposal: Digital worker golden runs should leave a reviewable diff, test log, review target, journal evidence, and pending memory proposal before closeout.
""",
        provider="local",
        model="manual",
        status="completed",
        usage={"inputTokens": 1, "outputTokens": 1},
    )


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _init_source_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    init = subprocess.run(["git", "init", "-b", "main"], cwd=path, check=False, capture_output=True, text=True)
    if init.returncode != 0:
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "aiteamos@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "AITEAMOS Test"], cwd=path, check=True)
    (path / "packages" / "workspace").mkdir(parents=True)
    (path / "packages" / "workspace" / "golden_worker.txt").write_text("before golden worker\n", encoding="utf-8")
    subprocess.run(["git", "add", "packages/workspace/golden_worker.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial golden worker fixture"], cwd=path, check=True, capture_output=True, text=True)
    return path


def _point_workspace_repository_at(workspace: Path, repository: Path) -> None:
    path = workspace / "repositories" / "aiteamos.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("spec", {})["localPath"] = str(repository)
    data["spec"]["url"] = repository.as_uri()
    data["spec"]["defaultBranch"] = "main"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _allow_local_manual_model(workspace: Path) -> None:
    path = workspace / "execution_profiles" / "digital" / "backend-digital.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    allowed = data.setdefault("spec", {}).setdefault("allowedModelProfiles", [])
    if "manual-worker" not in allowed:
        allowed.append("manual-worker")
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _approve_run_permission(workspace: Path, run_id: str, task_id: str, action: dict[str, object]) -> None:
    index = load_workspace(workspace)
    decision = explain_effective_permissions(
        index,
        member=BACKEND_MEMBER,
        project="aiteamos",
        assignment=BACKEND_ASSIGNMENT,
        action=action,
        non_interactive=True,
    )
    request = create_permission_request(
        workspace,
        member=BACKEND_MEMBER,
        project="aiteamos",
        assignment=BACKEND_ASSIGNMENT,
        task=task_id,
        run=run_id,
        requester_member="frontend-human",
        action=action,
        current_decision=decision,
        reason="Approve bounded golden worker action in temporary test workspace.",
        source="digital-worker-golden-run-test",
    )
    approve_permission_request(
        workspace,
        request.object_id,
        reviewer_member="frontend-human",
        reason="Approved for deterministic digital worker golden run test.",
    )


if __name__ == "__main__":
    unittest.main()
