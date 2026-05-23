from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from aiteamos_workspace import explain_effective_permissions, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]


class ManagerMemberProtocolTest(unittest.TestCase):
    def test_aiteamos_manager_member_assignment_and_role_template_are_materialized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            self.assertIn("aiteamos-manager", index.members)
            self.assertEqual(index.members["aiteamos-manager"].spec.kind, "digital")
            self.assertIn("aiteamos-manager", index.members["aiteamos-manager"].spec.defaultAssignments)
            self.assertIn("manager", index.role_templates)
            self.assertIn("TaskPlan manifests", index.role_templates["manager"].spec.defaultOutputs)

            self.assertIn("aiteamos-manager", index.assignments)
            assignment = index.assignments["aiteamos-manager"]
            self.assertEqual(assignment.spec.member, "aiteamos-manager")
            self.assertEqual(assignment.spec.roleTemplate, "manager")
            self.assertIn(".aiteamos/task_plans/**", assignment.spec.scope.write)
            self.assertIn(".aiteamos/im/messages/**", assignment.spec.scope.write)
            self.assertNotIn(".aiteamos/tasks/**", assignment.spec.scope.write)
            self.assertIn(".aiteamos/tasks/**", assignment.spec.scope.requiresHumanReview)
            self.assertIn("bind-aiteamos-project-memory-to-manager", assignment.spec.memoryBindings)

            self.assertIn("aiteamos-manager", index.digital_execution_profiles)
            execution = index.digital_execution_profiles["aiteamos-manager"]
            self.assertEqual(execution.spec.member, "aiteamos-manager")
            self.assertEqual(execution.spec.defaultModelProfile, "openai-gpt-5.5-xhigh")
            self.assertIn("openai-gpt-5.5-xhigh", execution.spec.allowedModelProfiles)
            self.assertIn("aiteamos-manager", index.model_profiles["openai-gpt-5.5-xhigh"].spec.defaultForMembers)
            self.assertIn("aiteamos-manager", index.model_profiles["openai-gpt-5.5-xhigh"].spec.defaultForAssignments)

    def test_manager_direct_task_edit_fails_closed_in_non_interactive_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            decision = explain_effective_permissions(
                index,
                member="aiteamos-manager",
                assignment="aiteamos-manager",
                action={"tool": "Edit", "path": "/.aiteamos/tasks/TASK-20260522T151345634.yaml"},
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
    return workspace


if __name__ == "__main__":
    unittest.main()
