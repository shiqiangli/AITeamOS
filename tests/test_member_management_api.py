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
from aiteamos_workspace import create_task, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class MemberManagementApiTest(unittest.TestCase):
    def test_member_assignment_and_memory_fabric_write_endpoints_are_manifest_backed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            member = client.post(
                "/members",
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
            self.assertEqual(member.status_code, 200)
            self.assertEqual(member.json()["id"], "qa-human")
            self.assertEqual(member.json()["spec"]["kind"], "human")

            assignment = client.post(
                "/assignments",
                json={
                    "name": "AITEAMOS QA",
                    "member": "qa-human",
                    "project": "aiteamos",
                    "modules": ["tests/"],
                    "responsibilities": ["Review API and workspace protocol regressions."],
                    "scope": {"read": ["tests/**"], "write": ["tests/**"]},
                },
            )
            self.assertEqual(assignment.status_code, 200)
            self.assertEqual(assignment.json()["id"], "aiteamos-qa")

            binding = client.post(
                "/memory/bindings",
                json={
                    "name": "bind baseline to qa",
                    "store": "aiteamos-project-memory",
                    "entry": "team-member-baseline",
                    "targetType": "assignment",
                    "targetId": "aiteamos-qa",
                    "access": ["read", "reference"],
                    "createdByMember": "manager",
                },
            )
            self.assertEqual(binding.status_code, 200)
            self.assertEqual(binding.json()["spec"]["targetId"], "aiteamos-qa")

            task = create_task(
                workspace,
                title="Memory grant API task",
                assigned_member="qa-human",
                assignment="aiteamos-qa",
                acceptance=["temporary memory grant exists"],
            )
            grant = client.post(
                "/memory/grants",
                json={
                    "member": "qa-human",
                    "grantorMember": "architect",
                    "task": task.object_id,
                    "entries": ["team-member-baseline"],
                    "reason": "QA needs the team-member baseline for this task.",
                },
            )
            self.assertEqual(grant.status_code, 200)
            self.assertEqual(grant.json()["spec"]["granteeMember"], "qa-human")
            self.assertEqual(grant.json()["spec"]["entries"], ["team-member-baseline"])

            share = client.post(
                "/memory/share",
                json={
                    "fromMember": "architect",
                    "toMember": "qa-human",
                    "task": task.object_id,
                    "entries": ["team-member-baseline"],
                    "reason": "Please reuse the baseline during QA.",
                },
            )
            self.assertEqual(share.status_code, 200)
            self.assertEqual(share.json()["grant"]["spec"]["grantorMember"], "architect")
            self.assertEqual(share.json()["message"]["spec"]["messageType"], "knowledge-share")

            archived_binding = client.delete(f"/memory/bindings/{binding.json()['id']}")
            self.assertEqual(archived_binding.status_code, 200)
            self.assertEqual(archived_binding.json()["spec"]["status"], "archived")

            archived_member = client.post("/members/qa-human/archive")
            self.assertEqual(archived_member.status_code, 200)
            self.assertEqual(archived_member.json()["spec"]["profile"]["status"], "archived")

            index = load_workspace(workspace)
            self.assertEqual(index.assignments["aiteamos-qa"].spec.status, "archived")
            self.assertIn("team-member-baseline", index.memory_entries)
            self.assertIn(grant.json()["id"], index.memory_grants)
            self.assertTrue(index.member_messages)


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
