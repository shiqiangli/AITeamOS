from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_workspace import load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class WorkspaceNamespaceApiTest(unittest.TestCase):
    def test_workspace_scoped_routes_validate_workspace_id_and_reuse_manifest_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            workspaces = client.get("/workspaces")
            self.assertEqual(workspaces.status_code, 200)
            workspace_id = workspaces.json()[0]["id"]
            self.assertEqual(workspace_id, "aiteamos-self-hosting")

            openapi_paths = client.get("/openapi.json").json()["paths"]
            self.assertIn("/workspaces/{wsId}/members", openapi_paths)
            self.assertIn("/workspaces/{wsId}/health", openapi_paths)

            unscoped_members = client.get("http://testserver/members")
            scoped_members = client.get(f"/workspaces/{workspace_id}/members")
            self.assertEqual(scoped_members.status_code, 200)
            self.assertEqual(unscoped_members.status_code, 404)

            health = client.get(f"/workspaces/{workspace_id}/health")
            self.assertEqual(health.status_code, 200)
            self.assertNotIn("planMilestones", health.json())

            summary = client.get(f"/workspaces/{workspace_id}/summary")
            self.assertEqual(summary.status_code, 200)
            self.assertIn("counts", summary.json())

            tasks = client.get(f"/workspaces/{workspace_id}/tasks")
            self.assertEqual(tasks.status_code, 200)
            self.assertTrue(tasks.json())

            created = client.post(
                f"/workspaces/{workspace_id}/members",
                json={
                    "name": "QA Human",
                    "kind": "human",
                    "profile": {"displayName": "QA Human", "title": "Human reviewer"},
                    "aboutMe": {
                        "coreCapabilities": ["test engineering"],
                        "workStyle": ["review-heavy"],
                        "workMethod": ["write-regression-before-fix"],
                    },
                    "permissionPolicies": ["service-memory-default"],
                },
            )
            self.assertEqual(created.status_code, 200)
            self.assertEqual(created.json()["id"], "qa-human")

            fetched = client.get(f"/workspaces/{workspace_id}/members/qa-human")
            self.assertEqual(fetched.status_code, 200)
            self.assertEqual(fetched.json()["spec"]["kind"], "human")

            project_members = client.get(f"/workspaces/{workspace_id}/projects/aiteamos/members")
            self.assertEqual(project_members.status_code, 200)
            self.assertTrue({member["id"] for member in project_members.json()})

            namespaced_index = client.post(f"/workspaces/{workspace_id}/index")
            self.assertEqual(namespaced_index.status_code, 200)
            self.assertTrue(namespaced_index.json()["derived"])

            unknown = client.get("/workspaces/not-this-workspace/members")
            self.assertEqual(unknown.status_code, 404)
            self.assertIn("unknown workspace", unknown.json()["detail"])

            index = load_workspace(workspace)
            self.assertIn("qa-human", index.members)


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
