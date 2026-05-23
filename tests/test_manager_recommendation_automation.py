from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import edit_action, explain_effective_permissions, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]


class ManagerRecommendationAutomationTest(unittest.TestCase):
    def test_manager_recommendation_execute_creates_message_and_optional_task_plan_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            before = load_workspace(workspace)
            task_ids_before = set(before.tasks)
            run_ids_before = set(before.runs)

            client = TestClient(create_app(workspace))
            queued = client.post(
                "/automations/aiteamos-manager-recommendation/trigger",
                json={"actorMember": "architect"},
            )
            self.assertEqual(queued.status_code, 200, queued.text)
            self.assertEqual(queued.json()["spec"]["status"], "queued")
            executed = client.post(
                f"/automations/runs/{queued.json()['id']}/execute",
                json={"actorMember": "team-execution-service"},
            )

            self.assertEqual(executed.status_code, 200, executed.text)
            payload = executed.json()
            self.assertEqual(payload["spec"]["status"], "succeeded")
            self.assertEqual(payload["spec"]["targetType"], "manager_recommendation")
            self.assertIsNotNone(payload["spec"]["createdMessage"])
            self.assertIsNotNone(payload["spec"]["createdTaskPlan"])
            self.assertIsNone(payload["spec"].get("createdTask"))
            self.assertIsNone(payload["spec"].get("createdRun"))

            after = load_workspace(workspace)
            self.assertEqual(set(after.tasks), task_ids_before)
            self.assertEqual(set(after.runs), run_ids_before)
            message = after.member_messages[payload["spec"]["createdMessage"]]
            plan = after.task_plans[payload["spec"]["createdTaskPlan"]]
            self.assertEqual(message.spec.fromMember, "aiteamos-manager")
            self.assertEqual(message.spec.toMembers, ["architect"])
            self.assertEqual(message.spec.messageType, "plan-recommendation")
            self.assertEqual(message.spec.audit["source"], "manager-recommendation")
            self.assertEqual(message.spec.audit["executorMember"], "team-execution-service")
            self.assertIn(plan.object_id, message.spec.attachments)
            self.assertEqual(plan.spec.createdByMember, "aiteamos-manager")
            self.assertEqual(plan.spec.status, "draft")
            self.assertEqual(plan.spec.subtasks[0].assignment, "aiteamos-architecture")

    def test_manager_direct_task_write_stays_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            decision = explain_effective_permissions(
                index,
                member="aiteamos-manager",
                assignment="aiteamos-manager",
                action=edit_action("/.aiteamos/tasks/TASK-MANAGER-DIRECT.yaml"),
                non_interactive=True,
            )

            self.assertEqual(decision["decision"], "deny")
            self.assertIn("ask converted to deny", decision["reason"])


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    _seed_manager_execution_policy(workspace)
    return workspace


def _seed_manager_execution_policy(workspace: Path) -> None:
    permission_payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "PermissionPolicy",
        "metadata": {"name": "service-team-execution-demo"},
        "spec": {
            "scope": {"memberKind": "service", "member": "team-execution-service"},
            "defaultMode": "deny",
            "allow": [
                {"match": "Automation(manager_recommendation:*)"},
                {"match": "Edit(/.aiteamos/im/messages/**)"},
                {"match": "Edit(/.aiteamos/task_plans/**)"},
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
    automation_path = workspace / "automations" / "aiteamos-manager-recommendation.yaml"
    automation_payload = yaml.safe_load(automation_path.read_text(encoding="utf-8"))
    automation_payload["spec"]["permissionPolicies"] = ["service-team-execution-demo"]
    automation_path.write_text(yaml.safe_dump(automation_payload, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
