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


class SkillLifecycleApiTest(unittest.TestCase):
    def test_human_reviewed_skill_create_attach_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            created = client.post(
                "/skills",
                json={
                    "name": "Runtime Debugging",
                    "actorMember": "frontend-human",
                    "description": "Debug runtime API and dashboard issues.",
                    "ownerMember": "frontend-human",
                    "projects": ["aiteamos"],
                    "capabilities": ["runtime-debugging", "dashboard-triage"],
                    "requiredPermissions": ["service-memory-default"],
                    "lifecycle": "active",
                    "reason": "Human approved new skill capability.",
                },
            )

            self.assertEqual(created.status_code, 200)
            self.assertEqual(created.json()["skill"]["id"], "runtime-debugging")
            self.assertEqual(created.json()["skill"]["spec"]["decisionAudit"][0]["actorMember"], "frontend-human")
            self.assertEqual(created.json()["permissionDecision"]["decision"], "ask")

            attached = client.post(
                "/skills/runtime-debugging/members/frontend-human",
                json={
                    "actorMember": "frontend-human",
                    "growthSummary": "Frontend human can now own runtime debugging follow-ups.",
                    "reason": "Human approved skill assignment.",
                },
            )

            self.assertEqual(attached.status_code, 200)
            self.assertIn("runtime-debugging", attached.json()["member"]["spec"]["skills"])
            self.assertTrue(attached.json()["member"]["spec"]["growthRecords"])

            archived = client.post(
                "/skills/runtime-debugging/archive",
                json={"actorMember": "frontend-human", "reason": "Retire test skill after review."},
            )

            self.assertEqual(archived.status_code, 200)
            self.assertEqual(archived.json()["skill"]["spec"]["lifecycle"], "archived")

            index = load_workspace(workspace)
            self.assertIn("runtime-debugging", index.skills)
            self.assertIn("runtime-debugging", index.members["frontend-human"].spec.skills)
            self.assertGreaterEqual(len(index.skills["runtime-debugging"].spec.decisionAudit), 3)
            self.assertTrue((workspace / "skills" / "events.jsonl").exists())

    def test_digital_member_cannot_bypass_skill_lifecycle_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            response = client.post(
                "/skills",
                json={
                    "name": "Unreviewed Digital Skill",
                    "actorMember": "manager",
                    "ownerMember": "manager",
                    "projects": ["aiteamos"],
                    "capabilities": ["self-approval"],
                    "lifecycle": "active",
                    "reason": "Digital actor attempted governed skill mutation.",
                },
            )

            self.assertEqual(response.status_code, 403)
            self.assertFalse((workspace / "skills" / "unreviewed-digital-skill.yaml").exists())

    def test_api_skill_projections_redact_sensitive_details_without_authorized_viewer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            created = client.post(
                "/skills",
                json={
                    "name": "Sensitive Connector Operations",
                    "actorMember": "frontend-human",
                    "description": "Operate connector remediation with secret-scoped permissions.",
                    "ownerMember": "frontend-human",
                    "projects": ["aiteamos"],
                    "capabilities": ["connector-remediation"],
                    "requiredPermissions": ["digital-default"],
                    "lifecycle": "active",
                    "reason": "Human reviewed governed skill projection.",
                },
            )

            self.assertEqual(created.status_code, 200)
            skill_id = created.json()["skill"]["id"]

            public_skills = client.get("/skills").json()
            public_record = next(record for record in public_skills if record["id"] == skill_id)
            self.assertTrue(public_record["redacted"])
            self.assertEqual(public_record["spec"]["description"], "[redacted]")
            self.assertEqual(public_record["spec"]["ownerMember"], "[redacted]")
            self.assertEqual(public_record["spec"]["capabilities"], [])
            self.assertEqual(public_record["spec"]["requiredPermissions"], [])
            self.assertEqual(public_record["spec"]["decisionAudit"], [])

            public_detail = client.get(f"/skills/{skill_id}").json()
            self.assertTrue(public_detail["spec"]["redacted"])
            self.assertEqual(public_detail["spec"]["requiredPermissions"], [])

            authorized_detail = client.get(f"/skills/{skill_id}", params={"viewerMember": "frontend-human"}).json()
            self.assertNotIn("redacted", authorized_detail)
            self.assertEqual(authorized_detail["spec"]["ownerMember"], "frontend-human")
            self.assertEqual(authorized_detail["spec"]["requiredPermissions"], ["digital-default"])
            self.assertTrue(authorized_detail["spec"]["decisionAudit"])

            public_project_projection = client.get("/projects/aiteamos/skills")
            self.assertEqual(public_project_projection.status_code, 200)
            public_project_record = next(record for record in public_project_projection.json() if record["id"] == skill_id)
            self.assertTrue(public_project_record["redacted"])
            self.assertEqual(public_project_record["spec"]["requiredPermissions"], [])
            self.assertNotIn("connector-remediation", public_project_projection.text)
            self.assertNotIn("digital-default", public_project_projection.text)

            authorized_project_projection = client.get("/projects/aiteamos/skills", params={"viewerMember": "frontend-human"})
            self.assertEqual(authorized_project_projection.status_code, 200)
            authorized_project_record = next(record for record in authorized_project_projection.json() if record["id"] == skill_id)
            self.assertFalse(authorized_project_record.get("redacted", False))
            self.assertEqual(authorized_project_record["spec"]["requiredPermissions"], ["digital-default"])
            self.assertIn("connector-remediation", authorized_project_projection.text)

            authorized_member_projection = client.get("/members/frontend-human/skills", params={"viewerMember": "frontend-human"})
            self.assertEqual(authorized_member_projection.status_code, 200)
            authorized_member_record = next(record for record in authorized_member_projection.json() if record["id"] == skill_id)
            self.assertEqual(authorized_member_record["spec"]["memberFitReasons"], ["owner"])

            public_assignment_projection = client.get("/assignments/aiteamos-dashboard/skills")
            self.assertEqual(public_assignment_projection.status_code, 200)
            public_assignment_record = next(record for record in public_assignment_projection.json() if record["id"] == skill_id)
            self.assertTrue(public_assignment_record["redacted"])
            self.assertEqual(public_assignment_record["spec"]["assignmentCount"], 0)
            self.assertNotIn("connector-remediation", public_assignment_projection.text)

            authorized_assignment_projection = client.get("/assignments/aiteamos-dashboard/skills", params={"viewerMember": "frontend-human"})
            self.assertEqual(authorized_assignment_projection.status_code, 200)
            authorized_assignment_record = next(record for record in authorized_assignment_projection.json() if record["id"] == skill_id)
            self.assertFalse(authorized_assignment_record.get("redacted", False))
            self.assertIn("aiteamos-dashboard", authorized_assignment_record["spec"]["assignments"])
            self.assertIn("connector-remediation", authorized_assignment_projection.text)

            unknown_viewer = client.get("/skills", params={"viewerMember": "missing-member"})
            self.assertEqual(unknown_viewer.status_code, 404)

            unknown_scoped_viewer = client.get("/projects/aiteamos/skills", params={"viewerMember": "missing-member"})
            self.assertEqual(unknown_scoped_viewer.status_code, 404)

            unknown_assignment_viewer = client.get("/assignments/aiteamos-dashboard/skills", params={"viewerMember": "missing-member"})
            self.assertEqual(unknown_assignment_viewer.status_code, 404)


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
