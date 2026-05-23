from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHITECTURE = REPO_ROOT / "docs" / "architecture.md"
WORKSPACE = REPO_ROOT / ".aiteamos"

REFERENCE_DIRECTORIES = [
    "repositories",
    "members",
    "teams",
    "role_templates",
    "assignments",
    "execution_profiles/digital",
    "execution_profiles/human",
    "execution_profiles/hybrid",
    "execution_profiles/service",
    "tasks",
    "task_plans",
    "runs",
    "reviews",
    "memory/stores",
    "memory/entries",
    "memory/versions",
    "memory/bindings",
    "memory/grants",
    "memory/proposals",
    "memory/reviews",
    "learning_extractions",
    "skills",
    "connectors/health",
    "permissions",
    "permission_requests",
    "permission_grants",
    "automations/events",
    "automations/provider_deliveries",
    "automations/leases",
    "automations/runs",
    "automations/approvals",
    "activity",
    "git_activity/imports",
    "git_activity/correlations",
    "im/messages",
    "im/handoffs",
    "im/retrospectives",
    "artifact_stores",
    "artifacts/manifests",
    "eval_suites",
    "eval_results",
    "model_profiles",
    "budget_policies",
]


class SelfHostingReferenceWorkspaceTest(unittest.TestCase):
    def test_architecture_self_hosting_reference_workspace_is_target_only(self) -> None:
        text = ARCHITECTURE.read_text(encoding="utf-8")
        marker = "### Self-hosting reference workspace"
        self.assertIn(marker, text)
        section = text.split(marker, 1)[1].split("\n### ", 1)[0]

        forbidden_gap_phrases = [
            "当前与推荐",
            "current-vs-target",
            "missing directories",
            "缺：",
        ]
        for phrase in forbidden_gap_phrases:
            self.assertNotIn(phrase, section)

        missing_from_architecture = [path for path in REFERENCE_DIRECTORIES if f"  {path.split('/')[-1]}/" not in section]
        self.assertEqual(missing_from_architecture, [])

    def test_embedded_workspace_materializes_reference_directories(self) -> None:
        missing = [path for path in REFERENCE_DIRECTORIES if not (WORKSPACE / path).is_dir()]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
