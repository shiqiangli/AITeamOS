from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import load_workspace, workspace_health_v2
from aiteamos_workspace.io import read_yaml, write_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT / ".aiteamos"


class WorkspaceHealthV2Test(unittest.TestCase):
    def test_workspace_health_endpoint_returns_v2_operational_fields(self) -> None:
        payload = TestClient(create_app(WORKSPACE)).get("/health").json()

        self.assertEqual(payload["schemaVersion"], "WorkspaceHealthV2")
        self.assertIn("lastIndexDuration", payload)
        self.assertEqual(payload["manifestLoadFailures"], [])
        self.assertIsInstance(payload["vectorChunkCount"], int)
        self.assertGreaterEqual(payload["vectorChunkCount"], 0)
        self.assertFalse(payload["schemaVersionMismatch"])
        self.assertEqual(payload["staleWorkerLeases"], [])
        self.assertNotIn("planMilestones", payload)
        self.assertNotIn("statusSummary", payload)

    def test_workspace_health_v2_projects_stale_worker_leases_without_mutating_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            shutil.copytree(
                WORKSPACE,
                workspace,
                ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
            )
            run_path = workspace / "runs" / "RUN-0001" / "run.yaml"
            run = read_yaml(run_path)
            run["spec"]["status"] = "RUNNING"
            run["spec"]["worker"] = {
                "stage": "execute",
                "heartbeatAt": "2000-01-01T00:00:00+00:00",
                "leaseSeconds": 1,
            }
            write_yaml(run_path, run)

            payload = workspace_health_v2(load_workspace(workspace)).model_dump(mode="json")

            self.assertEqual([lease["run"] for lease in payload["staleWorkerLeases"]], ["RUN-0001"])
            self.assertEqual(payload["staleWorkerLeases"][0]["task"], "TASK-20260520T101022277")
            self.assertEqual(read_yaml(run_path)["spec"]["status"], "RUNNING")


if __name__ == "__main__":
    unittest.main()
