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
    explain_effective_permissions,
    load_workspace,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_WORKSPACE = REPO_ROOT / "examples" / "protocol-fixture" / ".aiteamos"
RUNTIME_MEMBER = "protocol-runtime-bot"
RUNTIME_ASSIGNMENT = "conversion-runtime"
VERIFY_COMMAND = (
    "python -c \"from src.pure_function import add_i32; "
    "assert add_i32('lhs', 'rhs') == 'runtime.add_i32(lhs, rhs)'\""
)
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class ExampleWorkspaceTest(unittest.TestCase):
    def test_workspace_catalog_hides_protocol_fixture_without_leaking_private_root_path(self) -> None:
        with patch.dict(os.environ, AUTH_ENV_OFF):
            client = TestClient(create_app(REPO_ROOT / ".aiteamos"))

            response = client.get("/catalog")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn(str(REPO_ROOT), response.text)
        payload = response.json()
        self.assertEqual(payload["kind"], "WorkspaceCatalog")
        options = payload["spec"]["options"]
        current = next(option for option in options if option["id"] == "current")
        self.assertTrue(current["servedByCurrentApi"])
        self.assertIsNone(current.get("relativePath"))
        self.assertIn("path-redacted", " ".join(current["warnings"]))

        self.assertFalse([option for option in options if option["id"] == "example:protocol-fixture"])

    def test_workspace_catalog_treats_protocol_fixture_as_current_only_when_served(self) -> None:
        client = TestClient(create_app(EXAMPLE_WORKSPACE))

        response = client.get("/catalog")

        self.assertEqual(response.status_code, 200)
        options = response.json()["spec"]["options"]
        current = next(option for option in options if option["id"] == "current")
        self.assertTrue(current["servedByCurrentApi"])
        self.assertEqual(current["project"], "protocol-fixture")
        self.assertEqual(current["workspaceName"], "protocol-fixture-demo")
        self.assertFalse([option for option in options if option["id"] == "example:protocol-fixture"])

    def test_protocol_demo_workspace_has_browsable_team_member_story(self) -> None:
        index = load_workspace(EXAMPLE_WORKSPACE)

        self.assertEqual(index.project.object_id, "protocol-fixture")
        self.assertFalse([issue for issue in index.health if issue["severity"] == "error"])

        member_kinds = {member.spec.kind for member in index.members.values()}
        self.assertEqual(member_kinds, {"digital", "human", "hybrid", "service"})
        self.assertIn("conversion-runtime", index.assignments)
        self.assertIn("release-handoff", index.assignments)
        self.assertIn("frontend-review", index.assignments)
        self.assertIn("ci-automation", index.assignments)

        digital_task = index.tasks["TASK-20260521T080000000"]
        digital_run = index.runs["RUN-20260521T080000000"]
        self.assertEqual(digital_task.spec.assignedMember, "protocol-runtime-bot")
        self.assertEqual(digital_task.spec.assignment, "conversion-runtime")
        self.assertEqual(digital_task.spec.status, "DONE")
        self.assertEqual(digital_run.spec.member, "protocol-runtime-bot")
        self.assertEqual(digital_run.spec.mode, "managed_llm")
        self.assertEqual(digital_run.spec.status, "FINISHED")
        self.assertIn("MP-20260521T080000000", {Path(ref).stem for ref in digital_run.spec.memoryProposals})

        hybrid_task = index.tasks["TASK-20260521T083000000"]
        hybrid_run = index.runs["RUN-20260521T083000000"]
        self.assertEqual(hybrid_task.spec.assignedMember, "protocol-release-hybrid")
        self.assertEqual(hybrid_run.spec.memberKind, "hybrid")
        self.assertEqual(hybrid_run.spec.ingest["source"], "dashboard-assisted-ingest")
        self.assertIn("HANDOFF-20260521T083000000", index.handoffs)
        self.assertIn("MSG-20260521T082000000", index.member_messages)
        self.assertIn("RETRO-20260521T085000000", index.team_retrospectives)

        proposal = index.memory_proposals["MP-20260521T080000000"]
        self.assertEqual(proposal.spec.status, "approved")
        self.assertEqual(proposal.spec.approvedMemory, "MEM-protocol-runtime-contract")
        self.assertIn("MEM-protocol-runtime-contract", index.memory_entries)
        self.assertIn("MEM-protocol-runtime-contract-v1", index.memory_versions)
        self.assertIn("bind-runtime-contract-to-runtime", index.memory_bindings)
        self.assertIn("grant-runtime-contract-to-hybrid-run", index.memory_grants)
        self.assertEqual(index.memory_entries["MEM-protocol-runtime-contract"].spec.lifecycle, "active")

        self.assertIn("protocol-memory-health-demo", index.automations)
        self.assertIn("ARUN-20260521T090000000", index.automation_runs)
        self.assertEqual(index.automation_runs["ARUN-20260521T090000000"].spec.status, "dry-run")
        self.assertIn("GIT-20260521T081200000", index.git_activities)

    def test_protocol_demo_context_preview_injects_reviewed_memory_and_handoff(self) -> None:
        client = TestClient(create_app(EXAMPLE_WORKSPACE))

        digital_preview = client.get("/runs/RUN-20260521T080000000/context-preview")
        self.assertEqual(digital_preview.status_code, 200)
        digital_payload = digital_preview.json()
        selected_memory = digital_payload["manifest"]["sources"]["selectedMemory"]
        self.assertIn("MEM-protocol-runtime-contract", {item["memory"] for item in selected_memory})
        source_decisions = digital_payload["manifest"]["sourceDecisions"]
        self.assertIn(
            "MEM-protocol-runtime-contract",
            {item["sourceRef"] for item in source_decisions if item["outcome"] == "included"},
        )
        memory_decision = next(item for item in source_decisions if item["sourceRef"] == "MEM-protocol-runtime-contract")
        self.assertEqual(memory_decision["dedupeKey"], "memory:MEM-protocol-runtime-contract")
        self.assertEqual(memory_decision["budgetBucket"], "memoryItems")
        self.assertIn("snippetPreview", memory_decision)
        self.assertEqual(memory_decision["lineStart"], 1)
        self.assertGreaterEqual(memory_decision["lineEnd"], 1)
        self.assertIn("Add i32 runtime preserves operand order", digital_payload["capsule"])
        self.assertIn("bind-runtime-contract-to-runtime", digital_payload["manifest"]["memoryBindings"])

        hybrid_preview = client.get("/runs/RUN-20260521T083000000/context-preview")
        self.assertEqual(hybrid_preview.status_code, 200)
        hybrid_payload = hybrid_preview.json()
        self.assertIn(
            "MEM-protocol-runtime-contract",
            {item["memory"] for item in hybrid_payload["manifest"]["sources"]["selectedMemory"]},
        )
        self.assertIn(
            "HANDOFF-20260521T083000000",
            {item["id"] for item in hybrid_payload["manifest"]["sources"]["handoffs"]},
        )
        self.assertIn("grant-runtime-contract-to-hybrid-run", hybrid_payload["manifest"]["memoryGrants"])

    def test_protocol_demo_can_replay_digital_worker_run_in_temp_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            temp_root = Path(temp_dir)
            workspace = _copy_example_workspace(temp_root)
            repository = _init_demo_source_repo(temp_root / "source")
            _point_example_repository_at(workspace, repository)
            _allow_local_manual_model(workspace)

            create_model_profile(
                workspace,
                name="manual-demo-worker",
                provider="local",
                model="manual",
                gateway="manual",
                invocation={"fixtureResponse": _demo_worker_fixture_response()},
                capabilities=["managed_llm"],
            )
            task = create_task(
                workspace,
                title="Replay Protocol runtime worker path",
                assigned_member=RUNTIME_MEMBER,
                assignment=RUNTIME_ASSIGNMENT,
                execution_mode="managed_llm",
                acceptance=[
                    "worker uses the conversion-runtime write scope",
                    "worker records a review target, verification log, and memory proposal",
                ],
            )
            run = create_run(
                workspace,
                task_id=task.object_id,
                model_profile="manual-demo-worker",
                mode="managed_llm",
                extra_spec={"worker": {"verificationCommands": [VERIFY_COMMAND], "commandTimeoutSeconds": 30}},
            )
            client = TestClient(create_app(workspace))

            blocked_authorization = client.get(f"/runs/{run.object_id}/worker/authorization")
            self.assertEqual(blocked_authorization.status_code, 200)
            self.assertEqual(blocked_authorization.json()["status"], "BLOCKED")
            self.assertTrue(blocked_authorization.json()["permissionApprovalRequired"])

            _approve_run_permission(workspace, run.object_id, task.object_id, {"tool": "Bash", "command": VERIFY_COMMAND})
            readiness = client.get(f"/runs/{run.object_id}/worker/readiness")
            self.assertEqual(readiness.status_code, 200)
            self.assertEqual(readiness.json()["status"], "READY")

            response = client.post(f"/runs/{run.object_id}/worker/start", json={"createPr": False})

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["spec"]["status"], "REVIEW")
            self.assertEqual(payload["spec"]["reviewTarget"]["type"], "branch")

            updated = load_workspace(workspace)
            updated_run = updated.runs[run.object_id]
            self.assertEqual(updated_run.spec.status, "REVIEW")
            self.assertEqual(updated.tasks[task.object_id].spec.status, "REVIEW")
            self.assertTrue(updated_run.spec.worker["attemptId"].startswith(f"{run.object_id}-ATTEMPT-"))
            self.assertTrue(str(updated_run.spec.worktree).startswith(str(workspace / "artifacts" / "worktrees" / run.object_id)))
            self.assertTrue((workspace / "runs" / run.object_id / "worker_output.md").exists())
            self.assertTrue((workspace / "runs" / run.object_id / "diff.patch").exists())
            self.assertTrue((workspace / "runs" / run.object_id / "test.log").exists())
            self.assertTrue((workspace / "runs" / run.object_id / "command_results.jsonl").exists())
            self.assertIn("callee = \"runtime.add_i32\"", (workspace / "runs" / run.object_id / "diff.patch").read_text(encoding="utf-8"))
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

            review_response = client.post(
                f"/runs/{run.object_id}/reviews",
                json={
                    "reviewerMember": "protocol-reviewer-human",
                    "verdict": "approved",
                    "summary": "Reviewed the isolated worker branch and approved the bounded runtime contract change.",
                },
            )
            self.assertEqual(review_response.status_code, 200, review_response.text)
            review_payload = review_response.json()
            self.assertEqual(review_payload["kind"], "Review")
            self.assertEqual(review_payload["spec"]["run"], run.object_id)
            self.assertEqual(review_payload["spec"]["task"], task.object_id)
            self.assertEqual(review_payload["spec"]["reviewerMember"], "protocol-reviewer-human")
            self.assertEqual(review_payload["spec"]["reviewerKind"], "human")
            self.assertEqual(review_payload["spec"]["verdict"], "approved")
            self.assertEqual(review_payload["spec"]["target"]["type"], "branch")
            self.assertEqual(review_payload["spec"]["findings"][0]["id"], "summary")
            self.assertEqual(review_payload["spec"]["decisionAudit"][0]["decisionKind"], "human_approval")
            review_id = review_payload["id"]

            reviewed = load_workspace(workspace)
            self.assertIn(review_id, reviewed.runs[run.object_id].spec.reviews)
            self.assertIn(review_id, reviewed.tasks[task.object_id].spec.relatedReviews)
            self.assertIn("review.recorded", [event["type"] for event in reviewed.run_events[run.object_id]])

            closeout_gate = client.get(f"/runs/{run.object_id}/closeout-gate", params={"actorMember": "protocol-reviewer-human"})
            self.assertEqual(closeout_gate.status_code, 200, closeout_gate.text)
            self.assertTrue(closeout_gate.json()["readyForCloseout"])
            self.assertEqual(closeout_gate.json()["latestReview"], review_id)
            self.assertTrue(closeout_gate.json()["permissionDecisions"])

            closeout_response = client.post(
                f"/runs/{run.object_id}/closeout",
                json={
                    "actorMember": "protocol-reviewer-human",
                    "reason": "Close reviewed public demo worker branch after human approval.",
                },
            )
            self.assertEqual(closeout_response.status_code, 200, closeout_response.text)
            self.assertEqual(closeout_response.json()["spec"]["status"], "DONE")
            self.assertEqual(closeout_response.json()["spec"]["closeout"]["latestReview"], review_id)
            self.assertEqual(closeout_response.json()["spec"]["closeout"]["decisionAudit"][0]["decisionKind"], "human_approval")
            closed = load_workspace(workspace)
            self.assertEqual(closed.runs[run.object_id].spec.status, "DONE")
            self.assertEqual(closed.tasks[task.object_id].spec.status, "DONE")
            self.assertIn("run.closed", [event["type"] for event in closed.run_events[run.object_id]])

            source_file = repository / "src" / "pure_function.py"
            self.assertNotIn("callee = \"runtime.add_i32\"", source_file.read_text(encoding="utf-8"))
            source_integration_gate = client.get(
                f"/runs/{run.object_id}/source-integration-gate",
                params={"actorMember": "protocol-reviewer-human"},
            )
            self.assertEqual(source_integration_gate.status_code, 200, source_integration_gate.text)
            self.assertTrue(source_integration_gate.json()["readyForSourceIntegration"], source_integration_gate.json())
            self.assertEqual(source_integration_gate.json()["sourceBranch"], "main")
            self.assertEqual(source_integration_gate.json()["workerBranch"], updated_run.spec.branch.name)
            self.assertIn("src/pure_function.py", source_integration_gate.json()["changedPaths"])
            self.assertTrue(source_integration_gate.json()["permissionDecisions"])

            source_integration_response = client.post(
                f"/runs/{run.object_id}/source-integration",
                json={
                    "actorMember": "protocol-reviewer-human",
                    "reason": "Integrate the reviewed public demo worker branch after closeout.",
                },
            )
            self.assertEqual(source_integration_response.status_code, 200, source_integration_response.text)
            source_integration = source_integration_response.json()["spec"]["sourceIntegration"]
            self.assertEqual(source_integration["status"], "integrated")
            self.assertEqual(source_integration["sourceBranch"], "main")
            self.assertEqual(source_integration["workerBranch"], updated_run.spec.branch.name)
            self.assertEqual(source_integration["decisionAudit"][0]["decisionKind"], "human_approval")
            integrated = load_workspace(workspace)
            self.assertEqual(integrated.runs[run.object_id].spec.sourceIntegration["status"], "integrated")
            self.assertIn("run.source_integrated", [event["type"] for event in integrated.run_events[run.object_id]])
            self.assertIn("callee = \"runtime.add_i32\"", source_file.read_text(encoding="utf-8"))

            self.assertEqual(len(updated_run.spec.memoryProposals), 1)
            proposal_id = updated_run.spec.memoryProposals[0]
            proposal = updated.memory_proposals[proposal_id]
            self.assertEqual(proposal.spec.status, "pending-review")
            self.assertEqual(proposal.spec.sourceRun, run.object_id)
            self.assertEqual(proposal.spec.sourceTask, task.object_id)
            self.assertEqual(proposal.spec.member, RUNTIME_MEMBER)
            self.assertEqual(proposal.spec.assignment, RUNTIME_ASSIGNMENT)

            repair = client.post(f"/memory/proposals/{proposal_id}/repair", json={"reason": "Add safe review evidence before approval."})
            self.assertEqual(repair.status_code, 200, repair.text)
            approval = client.post(f"/memory/proposals/{proposal_id}/approve", json={"reason": "Approve worker replay learning."})
            self.assertEqual(approval.status_code, 200, approval.text)
            memory_id = approval.json()["memory"]["id"]
            self.assertTrue(memory_id.startswith("MEM-"))
            self.assertEqual(approval.json()["proposal"]["spec"]["approvedMemory"], memory_id)
            self.assertTrue(any(binding["spec"]["entry"] == memory_id for binding in approval.json()["bindings"]))

            followup_task = create_task(
                workspace,
                title="Use reviewed Protocol worker learning",
                project="protocol-fixture",
                assigned_member=RUNTIME_MEMBER,
                assignment=RUNTIME_ASSIGNMENT,
                execution_mode="managed_llm",
                acceptance=["follow-up context includes the approved worker learning"],
            )
            followup_run = create_run(
                workspace,
                task_id=followup_task.object_id,
                member=RUNTIME_MEMBER,
                assignment=RUNTIME_ASSIGNMENT,
                model_profile="manual-demo-worker",
                mode="managed_llm",
            )
            followup_preview = client.get(f"/runs/{followup_run.object_id}/context-preview")
            self.assertEqual(followup_preview.status_code, 200, followup_preview.text)
            followup_payload = followup_preview.json()
            self.assertIn(
                memory_id,
                {item["memory"] for item in followup_payload["manifest"]["sources"]["selectedMemory"]},
            )
            self.assertIn(memory_id, followup_payload["capsule"])

            worktree_file = Path(updated_run.spec.worktree) / "src" / "pure_function.py"
            self.assertIn("callee = \"runtime.add_i32\"", worktree_file.read_text(encoding="utf-8"))
            self.assertIn("callee = \"runtime.add_i32\"", source_file.read_text(encoding="utf-8"))


def _demo_worker_fixture_response() -> str:
    return """## Summary
Prepared a bounded demo replay change for human review.

```diff
diff --git a/src/pure_function.py b/src/pure_function.py
index 505b52d..54a6549 100644
--- a/src/pure_function.py
+++ b/src/pure_function.py
@@ -1,2 +1,3 @@
 def add_i32(lhs: str, rhs: str) -> str:
-    return f"runtime.add_i32({lhs}, {rhs})"
+    callee = "runtime.add_i32"
+    return f"{callee}({lhs}, {rhs})"
```

Memory proposal: Protocol demo worker replays should keep source edits inside the conversion-runtime assignment, produce test evidence, and route the learning through pending memory review.
"""


def _copy_example_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        EXAMPLE_WORKSPACE,
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _init_demo_source_repo(path: Path) -> Path:
    shutil.copytree(
        REPO_ROOT / "examples" / "protocol-fixture",
        path,
        ignore=shutil.ignore_patterns(".aiteamos", "__pycache__"),
    )
    init = subprocess.run(["git", "init", "-b", "main"], cwd=path, check=False, capture_output=True, text=True)
    if init.returncode != 0:
        subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "aiteamos@example.invalid"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "AITEAMOS Test"], cwd=path, check=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "initial protocol demo fixture"], cwd=path, check=True, capture_output=True, text=True)
    return path


def _point_example_repository_at(workspace: Path, repository: Path) -> None:
    path = workspace / "repositories" / "protocol-fixture.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("spec", {})["localPath"] = str(repository)
    data["spec"]["url"] = repository.as_uri()
    data["spec"]["defaultBranch"] = "main"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _allow_local_manual_model(workspace: Path) -> None:
    path = workspace / "execution_profiles" / "digital" / "protocol-runtime-bot.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    allowed = data.setdefault("spec", {}).setdefault("allowedModelProfiles", [])
    if "manual-demo-worker" not in allowed:
        allowed.append("manual-demo-worker")
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _approve_run_permission(workspace: Path, run_id: str, task_id: str, action: dict[str, object]) -> None:
    index = load_workspace(workspace)
    decision = explain_effective_permissions(
        index,
        member=RUNTIME_MEMBER,
        project="protocol-fixture",
        assignment=RUNTIME_ASSIGNMENT,
        action=action,
        non_interactive=True,
    )
    request = create_permission_request(
        workspace,
        member=RUNTIME_MEMBER,
        project="protocol-fixture",
        assignment=RUNTIME_ASSIGNMENT,
        task=task_id,
        run=run_id,
        requester_member="protocol-reviewer-human",
        action=action,
        current_decision=decision,
        reason="Approve bounded public demo worker verification in a temporary workspace.",
        source="protocol-demo-worker-replay-test",
    )
    approve_permission_request(
        workspace,
        request.object_id,
        reviewer_member="protocol-reviewer-human",
        reason="Approved for deterministic public demo worker replay test.",
    )


if __name__ == "__main__":
    unittest.main()
