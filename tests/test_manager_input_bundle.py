from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_schema import ManagerInputBundle
from aiteamos_workspace import load_workspace, manager_input_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]


class ManagerInputBundleTest(unittest.TestCase):
    def test_manager_input_bundle_aggregates_read_only_projections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            payload = manager_input_bundle(
                index,
                project="aiteamos",
                assignment="aiteamos-manager",
            )
            bundle = ManagerInputBundle.model_validate(payload)

            self.assertTrue(bundle.readOnly)
            self.assertEqual(bundle.manager, "aiteamos-manager")
            self.assertEqual(bundle.project, "aiteamos")
            self.assertEqual(bundle.assignment, "aiteamos-manager")
            self.assertEqual(bundle.workspaceHealth.summary["errors"], 0)
            self.assertIsInstance(bundle.reviewGates, list)
            self.assertIsInstance(bundle.connectorEscalationCandidates, list)
            self.assertIsInstance(bundle.connectorRemediationSuggestions, list)
            self.assertGreaterEqual(len(bundle.retrospectiveSuggestions), 1)
            self.assertEqual(bundle.memberGrowthSupportSignals.filters["assignment"], "aiteamos-manager")
            self.assertIn(".aiteamos/assignments/aiteamos-manager.yaml", bundle.sourceRefs)

    def test_manager_inbox_endpoint_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            before = _writable_manifest_snapshot(workspace)

            response = TestClient(create_app(workspace)).get(
                "/manager/inbox",
                params={"project": "aiteamos", "assignment": "aiteamos-manager"},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["manager"], "aiteamos-manager")
            self.assertTrue(payload["readOnly"])
            self.assertEqual(payload["memberGrowthSupportSignals"]["filters"]["assignment"], "aiteamos-manager")
            self.assertEqual(_writable_manifest_snapshot(workspace), before)

    def test_api_manager_inbox_alias_uses_same_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            response = TestClient(create_app(workspace)).get(
                "/manager/inbox",
                params={"project": "aiteamos", "assignment": "aiteamos-manager"},
            )

            self.assertEqual(response.status_code, 200)
            ManagerInputBundle.model_validate(response.json())


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _writable_manifest_snapshot(workspace: Path) -> dict[str, list[str]]:
    folders = ["tasks", "task_plans", "im", "reviews", "memory/proposals"]
    snapshot: dict[str, list[str]] = {}
    for folder in folders:
        root = workspace / folder
        snapshot[folder] = sorted(path.relative_to(workspace).as_posix() for path in root.rglob("*") if path.is_file()) if root.exists() else []
    return snapshot


if __name__ == "__main__":
    unittest.main()
