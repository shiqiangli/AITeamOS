from __future__ import annotations

from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import (
    append_run_event,
    build_context_capsule,
    build_run_launch_plan,
    evaluate_model_policy,
    evaluate_worker_authorization,
    evaluate_worker_readiness,
    index_workspace,
    inspect_worker_recovery,
    load_workspace,
    rebuild_workspace_indexes,
    summarize_model_costs,
    task_execution_queue,
    workspace_action_board,
)
from aiteamos_workspace.gitops import validate_patch_scope


REPO_ROOT = Path(__file__).resolve().parents[1]


class TeamMemberWorkspaceTest(unittest.TestCase):
    def test_workspace_loads_team_members_assignments_and_memory_fabric(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("indexes", "artifacts/blob", "artifacts/cache"),
            )

            index = load_workspace(workspace)

            self.assertFalse([issue for issue in index.health if issue["severity"] == "error"])
            self.assertIn("architect", index.members)
            self.assertEqual(index.members["architect"].spec.kind, "digital")
            self.assertIn("frontend-human", index.members)
            self.assertEqual(index.members["frontend-human"].spec.kind, "human")
            self.assertIn("aiteamos-architecture", index.assignments)
            self.assertEqual(index.assignments["aiteamos-architecture"].spec.member, "architect")
            self.assertIn("aiteamos-project-memory", index.memory_stores)
            self.assertIn("team-member-baseline", index.memory_entries)
            self.assertIn("grant-team-member-baseline-to-current-task", index.memory_grants)
            self.assertTrue(all(task.spec.assignedMember for task in index.tasks.values()))
            self.assertTrue(all(run.spec.member for run in index.runs.values()))

    def test_derived_index_exposes_project_member_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            db_path = Path(temp_dir) / "aiteamos.sqlite"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("indexes", "artifacts/blob", "artifacts/cache"),
            )

            index = index_workspace(workspace, db_path=db_path)
            self.assertGreaterEqual(len(index.members), 4)

            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    "select project_id, member_id, assignment_count, task_count, run_count from project_member_views order by member_id"
                ).fetchall()
            finally:
                conn.close()

            member_ids = {row[1] for row in rows}
            self.assertIn("architect", member_ids)
            self.assertIn("backend-digital", member_ids)
            self.assertTrue([row for row in rows if row[1] == "architect" and row[2] >= 1 and row[3] >= 1 and row[4] >= 1])

    def test_api_projects_employees_memory_permissions_and_automations(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("indexes", "artifacts/blob", "artifacts/cache"),
            )
            rebuild_workspace_indexes(workspace, db_path=Path(temp_dir) / "aiteamos.sqlite")

            client = TestClient(create_app(workspace))

            self.assertEqual(client.get("/health").json()["summary"]["errors"], 0)
            members = client.get("/members").json()
            self.assertTrue([member for member in members if member["id"] == "architect" and member["spec"]["kind"] == "digital"])
            self.assertTrue([member for member in members if member["id"] == "frontend-human" and member["spec"]["kind"] == "human"])
            project_members = client.get("/projects/aiteamos/members").json()
            self.assertTrue([member for member in project_members if member["id"] == "backend-digital"])
            self.assertTrue(client.get("/memory/stores").json())
            self.assertTrue(client.get("/memory/bindings").json())
            self.assertTrue(client.get("/memory/grants").json())
            self.assertTrue(client.get("/automations").json())
            self.assertTrue(client.get("/skills").json())
            self.assertTrue(client.get("/permissions").json())
            effective = client.get("/permissions/effective", params={"member": "backend-digital", "project": "aiteamos"}).json()
            self.assertEqual(effective["decisionOrder"], ["deny", "ask", "allow"])

            queue = client.get("/tasks/queue").json()
            self.assertTrue([item for item in queue["items"] if item["assignedMember"] == "architect"])
            launch = client.get("/tasks/TASK-20260520T101022277/launch-plan").json()
            self.assertTrue(launch["canCreateRun"])
            self.assertEqual(launch["selectedMember"], "architect")
            preview = client.get("/runs/RUN-0001/context-preview").json()
            self.assertEqual(preview["manifest"]["member"], "architect")
            self.assertIn("TeamMember is the durable identity", preview["capsule"])
            model_gate = client.get("/runs/RUN-0001/model/readiness").json()
            self.assertEqual(model_gate["member"], "architect")
            worker_gate = client.get("/runs/RUN-0001/worker/authorization").json()
            self.assertEqual(worker_gate["assignment"], "aiteamos-architecture")
            actions = client.get("/actions").json()
            self.assertTrue(actions["items"])
            self.assertFalse([item for item in actions["items"] if "role" in item])
            costs = client.get("/models/costs").json()
            self.assertEqual(costs["source"], "workspace-event-ledger")

    def test_context_compiler_uses_member_assignment_and_memory_fabric(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("indexes", "artifacts/blob", "artifacts/cache"),
            )

            index = load_workspace(workspace)
            result = build_context_capsule(
                index,
                run_id="RUN-0001",
                task_id="TASK-20260520T101022277",
                member_id="architect",
                assignment_id="aiteamos-architecture",
                model_profile="openai-gpt-5.5-xhigh",
                branch_name="aiteamos/TASK-20260520T101022277/architect/RUN-0001",
            )

            self.assertEqual(result.manifest["member"], "architect")
            self.assertEqual(result.manifest["assignment"], "aiteamos-architecture")
            self.assertIn("bind-aiteamos-project-memory-to-architecture", result.manifest["memoryBindings"])
            self.assertIn("member_identity", result.manifest["sourcePriority"])
            self.assertIn("## Member Identity", result.capsule)
            self.assertIn("## Current Assignment Contract", result.capsule)
            self.assertIn("TeamMember is the durable identity", result.capsule)

    def test_task_queue_and_launch_plan_are_member_centric(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("indexes", "artifacts/blob", "artifacts/cache"),
            )

            index = load_workspace(workspace)
            queue = task_execution_queue(index)
            items = {item["id"]: item for item in queue["items"]}
            self.assertEqual(items["TASK-20260520T101022277"]["assignedMember"], "architect")
            self.assertNotIn("assigned" + "Role", items["TASK-20260520T101022277"])
            self.assertEqual(items["TASK-20260520T101022277"]["memberModelProfile"], "openai-gpt-5.5-xhigh")

            plan = build_run_launch_plan(index, "TASK-20260520T101022277")
            self.assertTrue(plan["canCreateRun"])
            self.assertEqual(plan["selectedMember"], "architect")
            self.assertEqual(plan["selectedAssignment"], "aiteamos-architecture")
            self.assertIn("/architect/", plan["branchPreview"])

    def test_execution_safety_gates_are_member_assignment_centric(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("indexes", "artifacts/blob", "artifacts/cache"),
            )

            index = load_workspace(workspace)
            policy = evaluate_model_policy(index, "RUN-0001")
            self.assertEqual(policy["member"], "architect")
            self.assertEqual(policy["assignment"], "aiteamos-architecture")
            self.assertEqual(policy["profile"], "openai-gpt-5.5-xhigh")
            self.assertEqual(policy["profileSource"], "execution-profile")
            self.assertEqual(policy["policy"], "default-budget")

            auth = evaluate_worker_authorization(index, "RUN-0001")
            check_names = {check["name"] for check in auth["checks"]}
            self.assertIn("worker-auth-member", check_names)
            self.assertIn("worker-auth-assignment", check_names)
            self.assertIn("worker-auth-permissions", check_names)
            self.assertNotIn("worker-auth-role", check_names)
            self.assertFalse(auth["ready"])
            self.assertTrue([message for message in auth["blockers"] if "not a managed worker mode" in message])

            readiness = evaluate_worker_readiness(index, "RUN-0001")
            self.assertFalse(readiness["ready"])
            self.assertTrue([check for check in readiness["checks"] if check["name"] == "run-mode" and check["status"] == "fail"])

            allowed_diff = "diff --git a/docs/architecture.md b/docs/architecture.md\n--- a/docs/architecture.md\n+++ b/docs/architecture.md\n"
            denied_diff = "diff --git a/services/api/aiteamos_api/auth.py b/services/api/aiteamos_api/auth.py\n--- a/services/api/aiteamos_api/auth.py\n+++ b/services/api/aiteamos_api/auth.py\n"
            self.assertEqual(validate_patch_scope(index, "RUN-0001", allowed_diff), [])
            self.assertTrue([message for message in validate_patch_scope(index, "RUN-0001", denied_diff) if "outside assignment write scope" in message])

    def test_operations_projections_are_member_assignment_centric(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            shutil.copytree(
                REPO_ROOT / ".aiteamos",
                workspace,
                ignore=shutil.ignore_patterns("indexes", "artifacts/blob", "artifacts/cache"),
            )

            board = workspace_action_board(load_workspace(workspace))
            self.assertTrue(board["items"])
            self.assertFalse([item for item in board["items"] if "role" in item])
            self.assertTrue(
                [
                    item
                    for item in board["items"]
                    if item["targetType"] == "memory-proposal"
                    and item["member"] == "architect"
                    and item["assignment"] == "aiteamos-architecture"
                ]
            )

            append_run_event(
                workspace,
                "RUN-0001",
                {
                    "type": "model.call.completed",
                    "provider": "openai",
                    "model": "gpt-5.5",
                    "costUsd": 0.25,
                    "usage": {"input_tokens": 1000, "output_tokens": 200, "total_tokens": 1200},
                },
            )
            costs = summarize_model_costs(workspace)
            self.assertEqual(costs["byRun"][0]["member"], "architect")
            self.assertEqual(costs["byRun"][0]["assignment"], "aiteamos-architecture")
            self.assertNotIn("role", costs["byRun"][0])

            report = inspect_worker_recovery(workspace, "RUN-0001")
            self.assertEqual(report["member"], "architect")
            self.assertEqual(report["assignment"], "aiteamos-architecture")
            self.assertEqual(report["memberKind"], "digital")
            self.assertNotIn("role", report)


if __name__ == "__main__":
    unittest.main()
