from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]


class DemoWorkspaceAutomationStoryTest(unittest.TestCase):
    def test_public_demo_task_planning_automation_creates_draft_task_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            automations = client.get("/automations").json()
            demo = next(item for item in automations if item["id"] == "demo-task-planning")
            self.assertEqual(demo["spec"]["targetType"], "task_planning")
            self.assertEqual(demo["spec"]["serviceMember"], "team-execution-service")
            self.assertEqual(demo["spec"]["permissionPolicies"], ["service-team-execution-demo"])

            dry_run = client.post(
                "/automations/demo-task-planning/dry-run",
                json={"actorMember": "manager"},
            )
            self.assertEqual(dry_run.status_code, 200)
            self.assertEqual(dry_run.json()["spec"]["status"], "dry-run")
            self.assertEqual(dry_run.json()["spec"]["permissionDecisions"][0]["decision"], "allow")
            self.assertIsNone(dry_run.json()["spec"].get("createdTaskPlan"))

            queued = client.post(
                "/automations/demo-task-planning/trigger",
                json={"actorMember": "manager"},
            )
            self.assertEqual(queued.status_code, 200)
            self.assertEqual(queued.json()["spec"]["status"], "queued")
            self.assertFalse(queued.json()["spec"]["dryRun"])

            executed = client.post(
                f"/automations/runs/{queued.json()['id']}/execute",
                json={"actorMember": "team-execution-service"},
            )
            self.assertEqual(executed.status_code, 200)
            payload = executed.json()
            self.assertEqual(payload["spec"]["status"], "succeeded")
            self.assertIsNotNone(payload["spec"]["createdTaskPlan"])
            self.assertIsNone(payload["spec"].get("createdTask"))
            self.assertIsNone(payload["spec"].get("createdRun"))
            self.assertTrue(
                any(
                    decision.get("action", {}).get("canonical") == "Automation(task_planning:demo-task-planning)"
                    and decision.get("decision") == "allow"
                    for decision in payload["spec"]["permissionDecisions"]
                )
            )
            self.assertTrue(
                any(
                    decision.get("action", {}).get("path") == "/.aiteamos/task_plans/**"
                    and decision.get("decision") == "allow"
                    for decision in payload["spec"]["permissionDecisions"]
                )
            )

            index = load_workspace(workspace)
            task_plan = index.task_plans[payload["spec"]["createdTaskPlan"]]
            self.assertEqual(task_plan.spec.project, "aiteamos")
            self.assertEqual(task_plan.spec.createdByMember, "team-execution-service")
            self.assertEqual(task_plan.spec.status, "draft")
            self.assertEqual(task_plan.spec.subtasks[0].assignedMember, "backend-digital")
            self.assertEqual(task_plan.spec.subtasks[0].assignment, "aiteamos-backend-runtime")
            self.assertEqual(task_plan.spec.subtasks[1].assignedMember, "frontend-human")
            self.assertEqual(task_plan.spec.subtasks[1].assignment, "aiteamos-dashboard")
            self.assertIn("task-planning-review", task_plan.spec.reviewGates)

    def test_public_demo_hybrid_assist_automation_creates_assisted_task_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            automations = client.get("/automations").json()
            demo = next(item for item in automations if item["id"] == "demo-hybrid-assist-run")
            self.assertEqual(demo["spec"]["targetType"], "hybrid_assist")
            self.assertEqual(demo["spec"]["serviceMember"], "team-execution-service")
            self.assertEqual(demo["spec"]["permissionPolicies"], ["service-team-execution-demo"])

            dry_run = client.post(
                "/automations/demo-hybrid-assist-run/dry-run",
                json={"actorMember": "frontend-human"},
            )
            self.assertEqual(dry_run.status_code, 200)
            self.assertEqual(dry_run.json()["spec"]["status"], "dry-run")
            self.assertEqual(dry_run.json()["spec"]["permissionDecisions"][0]["decision"], "allow")
            self.assertIsNone(dry_run.json()["spec"].get("createdTask"))
            self.assertIsNone(dry_run.json()["spec"].get("createdRun"))

            queued = client.post(
                "/automations/demo-hybrid-assist-run/trigger",
                json={"actorMember": "frontend-human"},
            )
            self.assertEqual(queued.status_code, 200)
            self.assertEqual(queued.json()["spec"]["status"], "queued")
            self.assertFalse(queued.json()["spec"]["dryRun"])

            executed = client.post(
                f"/automations/runs/{queued.json()['id']}/execute",
                json={"actorMember": "team-execution-service"},
            )
            self.assertEqual(executed.status_code, 200)
            payload = executed.json()
            self.assertEqual(payload["spec"]["status"], "succeeded")
            self.assertIsNotNone(payload["spec"]["createdTask"])
            self.assertIsNotNone(payload["spec"]["createdRun"])
            self.assertTrue(
                any(
                    decision.get("action", {}).get("canonical") == "Automation(hybrid_assist:demo-hybrid-assist-run)"
                    and decision.get("decision") == "allow"
                    for decision in payload["spec"]["permissionDecisions"]
                )
            )
            self.assertTrue(
                any(
                    decision.get("action", {}).get("path") == "/.aiteamos/tasks/**"
                    and decision.get("decision") == "allow"
                    for decision in payload["spec"]["permissionDecisions"]
                )
            )
            self.assertTrue(
                any(
                    decision.get("action", {}).get("path") == "/.aiteamos/runs/**"
                    and decision.get("decision") == "allow"
                    for decision in payload["spec"]["permissionDecisions"]
                )
            )

            index = load_workspace(workspace)
            task = index.tasks[payload["spec"]["createdTask"]]
            run = index.runs[payload["spec"]["createdRun"]]
            self.assertEqual(task.spec.project, "aiteamos")
            self.assertEqual(task.spec.assignedMember, "frontend-human")
            self.assertEqual(task.spec.assignment, "aiteamos-dashboard")
            self.assertEqual(task.spec.executionMode, "assisted")
            self.assertEqual(task.spec.status, "QUEUED")
            self.assertEqual(run.spec.task, task.object_id)
            self.assertEqual(run.spec.member, "frontend-human")
            self.assertEqual(run.spec.assignment, "aiteamos-dashboard")
            self.assertEqual(run.spec.mode, "assisted")
            self.assertEqual(run.spec.status, "READY")

            growth = client.get("/members/frontend-human/growth")
            self.assertEqual(growth.status_code, 200)
            growth_item = growth.json()["items"][0]
            self.assertEqual(growth_item["memberKind"], "human")
            self.assertNotIn("score", growth_item)
            action = next(item for item in growth_item["growthPlanActions"] if item["actionType"] == "complete-assisted-ingest")
            self.assertEqual(action["status"], "ready")
            self.assertIn(run.object_id, action["relatedRuns"])
            self.assertIn(task.object_id, action["relatedTasks"])
            self.assertIn(f"run:{run.object_id}", action["evidence"])

            growth_note_action = next(item for item in growth_item["growthPlanActions"] if item["actionType"] == "capture-reviewed-growth-note")
            recorded = client.post(
                "/members/frontend-human/growth-records",
                json={
                    "actorMember": "frontend-human",
                    "summary": "Practiced assisted run intake and prepared reviewable outputs.",
                    "project": "aiteamos",
                    "sourceAction": growth_note_action["id"],
                    "sourceTask": task.object_id,
                    "sourceRun": run.object_id,
                    "evidence": growth_note_action["evidence"],
                    "reason": "Reviewed non-punitive growth evidence from the hybrid assist demo.",
                },
            )
            self.assertEqual(recorded.status_code, 200)
            growth_record = recorded.json()["growthRecord"]
            self.assertEqual(growth_record["sourceAction"], growth_note_action["id"])
            self.assertEqual(growth_record["sourceTask"], task.object_id)
            self.assertEqual(growth_record["sourceRun"], run.object_id)
            self.assertEqual(growth_record["reviewedByMember"], "frontend-human")
            self.assertEqual(growth_record["decisionAudit"][0]["decisionKind"], "human_approval")
            self.assertEqual(growth_record["decisionAudit"][0]["authority"], "approve")

            digital_attempt = client.post(
                "/members/frontend-human/growth-records",
                json={
                    "actorMember": "manager",
                    "summary": "Digital actor should not directly approve growth evidence.",
                },
            )
            self.assertEqual(digital_attempt.status_code, 403)

            refreshed_growth = client.get("/members/frontend-human/growth").json()["items"][0]
            self.assertEqual(refreshed_growth["activityCounts"]["declaredGrowthRecords"], 1)
            self.assertFalse(
                any(item["actionType"] == "capture-reviewed-growth-note" for item in refreshed_growth["growthPlanActions"])
            )

    def test_public_demo_digital_execution_automation_creates_managed_task_and_run_without_worker_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            automations = client.get("/automations").json()
            demo = next(item for item in automations if item["id"] == "demo-digital-execution-run")
            self.assertEqual(demo["spec"]["targetType"], "digital_execution")
            self.assertEqual(demo["spec"]["serviceMember"], "team-execution-service")
            self.assertEqual(demo["spec"]["permissionPolicies"], ["service-team-execution-demo"])

            dry_run = client.post(
                "/automations/demo-digital-execution-run/dry-run",
                json={"actorMember": "manager"},
            )
            self.assertEqual(dry_run.status_code, 200)
            self.assertEqual(dry_run.json()["spec"]["status"], "dry-run")
            self.assertEqual(dry_run.json()["spec"]["permissionDecisions"][0]["decision"], "allow")
            self.assertIsNone(dry_run.json()["spec"].get("createdTask"))
            self.assertIsNone(dry_run.json()["spec"].get("createdRun"))

            queued = client.post(
                "/automations/demo-digital-execution-run/trigger",
                json={"actorMember": "manager"},
            )
            self.assertEqual(queued.status_code, 200)
            self.assertEqual(queued.json()["spec"]["status"], "queued")
            self.assertFalse(queued.json()["spec"]["dryRun"])

            executed = client.post(
                f"/automations/runs/{queued.json()['id']}/execute",
                json={"actorMember": "team-execution-service"},
            )
            self.assertEqual(executed.status_code, 200)
            payload = executed.json()
            self.assertEqual(payload["spec"]["status"], "succeeded")
            self.assertIsNotNone(payload["spec"]["createdTask"])
            self.assertIsNotNone(payload["spec"]["createdRun"])
            self.assertTrue(
                any(
                    decision.get("action", {}).get("canonical") == "Automation(digital_execution:demo-digital-execution-run)"
                    and decision.get("decision") == "allow"
                    for decision in payload["spec"]["permissionDecisions"]
                )
            )
            self.assertTrue(
                any(
                    decision.get("action", {}).get("path") == "/.aiteamos/tasks/**"
                    and decision.get("decision") == "allow"
                    for decision in payload["spec"]["permissionDecisions"]
                )
            )
            self.assertTrue(
                any(
                    decision.get("action", {}).get("path") == "/.aiteamos/runs/**"
                    and decision.get("decision") == "allow"
                    for decision in payload["spec"]["permissionDecisions"]
                )
            )

            index = load_workspace(workspace)
            task = index.tasks[payload["spec"]["createdTask"]]
            run = index.runs[payload["spec"]["createdRun"]]
            self.assertEqual(task.spec.project, "aiteamos")
            self.assertEqual(task.spec.assignedMember, "backend-digital")
            self.assertEqual(task.spec.assignment, "aiteamos-backend-runtime")
            self.assertEqual(task.spec.executionMode, "managed_llm")
            self.assertEqual(task.spec.status, "QUEUED")
            self.assertEqual(run.spec.task, task.object_id)
            self.assertEqual(run.spec.member, "backend-digital")
            self.assertEqual(run.spec.assignment, "aiteamos-backend-runtime")
            self.assertEqual(run.spec.mode, "managed_llm")
            self.assertEqual(run.spec.status, "READY")
            self.assertEqual(run.spec.modelProfile, "openai-gpt-5.5-xhigh")

            readiness = client.get(f"/runs/{run.object_id}/worker/readiness")
            self.assertEqual(readiness.status_code, 200)
            self.assertEqual(readiness.json()["run"], run.object_id)
            self.assertFalse(readiness.json()["lock"]["held"])
            self.assertTrue(
                any(
                    check.get("name") == "run-status" and check.get("status") == "pass"
                    for check in readiness.json()["checks"]
                )
            )
            authorization = client.get(f"/runs/{run.object_id}/worker/authorization")
            self.assertEqual(authorization.status_code, 200)
            self.assertEqual(authorization.json()["run"], run.object_id)
            self.assertEqual(authorization.json()["member"], "backend-digital")
            self.assertTrue(
                any(
                    check.get("name") == "worker-auth-mode" and check.get("status") == "pass"
                    for check in authorization.json()["checks"]
                )
            )


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    _seed_demo_automations(workspace)
    return workspace


def _seed_demo_automations(workspace: Path) -> None:
    permission_payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "PermissionPolicy",
        "metadata": {"name": "service-team-execution-demo"},
        "spec": {
            "scope": {"memberKind": "service", "member": "team-execution-service"},
            "defaultMode": "deny",
            "allow": [
                {"match": "Automation(task_planning:*)"},
                {"match": "Automation(hybrid_assist:*)"},
                {"match": "Automation(digital_execution:*)"},
                {"match": "Edit(/.aiteamos/task_plans/**)"},
                {"match": "Edit(/.aiteamos/tasks/**)"},
                {"match": "Edit(/.aiteamos/runs/**)"},
            ],
            "ask": [],
            "deny": [
                {"match": "WebFetch"},
                {"match": "Network(*)"},
                {"match": "EnvVar(*)"},
                {"match": "Edit(/.git/**)"},
            ],
            "sensitivePaths": [".env", ".git/**", "*.pem"],
        },
    }
    (workspace / "permissions" / "service-team-execution-demo.yaml").write_text(
        yaml.safe_dump(permission_payload, sort_keys=False),
        encoding="utf-8",
    )
    automations = {
        "demo-task-planning": {
            "targetType": "task_planning",
            "ownerMember": "manager",
            "target": {
                "project": "aiteamos",
                "goal": "Draft a reviewable task plan for the next implementation slice.",
                "title": "Demo task planning workflow",
                "status": "draft",
                "subtasks": [
                    {
                        "title": "Backend protocol follow-up",
                        "assignedMember": "backend-digital",
                        "assignment": "aiteamos-backend-runtime",
                        "priority": "normal",
                        "acceptance": ["Backend task remains scoped to workspace/runtime files."],
                    },
                    {
                        "title": "Dashboard review follow-up",
                        "assignedMember": "frontend-human",
                        "assignment": "aiteamos-dashboard",
                        "priority": "normal",
                        "acceptance": ["Dashboard task remains UI-review scoped."],
                    },
                ],
                "reviewGates": ["task-planning-review"],
            },
        },
        "demo-hybrid-assist-run": {
            "targetType": "hybrid_assist",
            "ownerMember": "frontend-human",
            "target": {
                "project": "aiteamos",
                "assignedMember": "frontend-human",
                "assignment": "aiteamos-dashboard",
                "title": "Demo hybrid assisted dashboard workflow",
                "mode": "assisted",
                "executionMode": "assisted",
                "acceptance": ["Assisted task and run are created for the human dashboard member."],
            },
        },
        "demo-digital-execution-run": {
            "targetType": "digital_execution",
            "ownerMember": "manager",
            "target": {
                "project": "aiteamos",
                "assignedMember": "backend-digital",
                "assignment": "aiteamos-backend-runtime",
                "title": "Demo managed backend workflow",
                "mode": "managed_llm",
                "executionMode": "managed_llm",
                "acceptance": ["Managed task and READY run are created without starting a worker."],
            },
        },
    }
    for name, spec in automations.items():
        payload = {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Automation",
            "metadata": {"name": name},
            "spec": {
                "ownerMember": spec["ownerMember"],
                "serviceMember": "team-execution-service",
                "project": "aiteamos",
                "targetType": spec["targetType"],
                "target": spec["target"],
                "triggers": [{"triggerType": "manual", "config": {}}],
                "dryRun": False,
                "status": "active",
                "permissionPolicies": ["service-team-execution-demo"],
                "approvalGates": [],
            },
        }
        (workspace / "automations" / f"{name}.yaml").write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
