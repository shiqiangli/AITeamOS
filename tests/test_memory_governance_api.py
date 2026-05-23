from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient
import yaml

from aiteamos_api import create_app
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class MemoryGovernanceApiTest(unittest.TestCase):
    def test_global_memory_projection_redacts_private_sensitive_records_without_viewer_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            _write_private_secret_memory(workspace)
            client = TestClient(create_app(workspace))

            public_entries = client.get("/memory/entries")
            public_stores = client.get("/memory/stores")
            public_bindings = client.get("/memory/bindings")
            public_grants = client.get("/memory/grants")
            public_proposals = client.get("/memory/proposals")

            self.assertEqual(public_entries.status_code, 200)
            self.assertNotIn("CUSTOMER-X-SECRET", str(public_entries.json()))
            secret_public = _record(public_entries.json(), "private-strategy-secret")
            self.assertTrue(secret_public["spec"]["redacted"])
            self.assertEqual(secret_public["spec"]["content"], "[redacted]")
            self.assertEqual(secret_public["spec"]["title"], "[redacted]")

            self.assertEqual(public_stores.status_code, 200)
            private_store = _record(public_stores.json(), "architect-personal-memory")
            self.assertTrue(private_store["spec"]["redacted"])
            self.assertEqual(private_store["spec"]["description"], "[redacted]")
            self.assertEqual(private_store["spec"]["acl"], {})

            self.assertEqual(public_bindings.status_code, 200)
            private_binding = _record(public_bindings.json(), "bind-private-secret-to-architect")
            self.assertTrue(private_binding["spec"]["redacted"])
            self.assertEqual(private_binding["spec"]["entry"], "[redacted]")
            self.assertEqual(private_binding["spec"]["targetId"], "[redacted]")

            self.assertEqual(public_grants.status_code, 200)
            private_grant = _record(public_grants.json(), "grant-private-secret-to-architect")
            self.assertTrue(private_grant["spec"]["redacted"])
            self.assertEqual(private_grant["spec"]["entries"], [])
            self.assertEqual(private_grant["spec"]["granteeMember"], "[redacted]")

            self.assertEqual(public_proposals.status_code, 200)
            self.assertNotIn("CUSTOMER-PROPOSAL-SECRET", str(public_proposals.json()))
            private_proposal = _record(public_proposals.json(), "private-proposal-secret")
            self.assertTrue(private_proposal["spec"]["redacted"])
            self.assertEqual(private_proposal["spec"]["content"], "[redacted]")
            self.assertEqual(private_proposal["spec"]["decisionAudit"], [])

            frontend_entries = client.get("/memory/entries", params={"viewerMember": "frontend-human"})
            frontend_proposals = client.get("/memory/proposals", params={"viewerMember": "frontend-human"})
            self.assertEqual(frontend_entries.status_code, 200)
            self.assertNotIn("CUSTOMER-X-SECRET", str(frontend_entries.json()))
            self.assertTrue(_record(frontend_entries.json(), "private-strategy-secret")["spec"]["redacted"])
            project_entry = _record(frontend_entries.json(), "team-member-baseline")
            self.assertFalse(project_entry["spec"].get("redacted", False))
            self.assertIn("TeamMember", project_entry["spec"]["content"])
            self.assertEqual(frontend_proposals.status_code, 200)
            self.assertNotIn("CUSTOMER-PROPOSAL-SECRET", str(frontend_proposals.json()))
            self.assertTrue(_record(frontend_proposals.json(), "private-proposal-secret")["spec"]["redacted"])

            architect_entries = client.get("/memory/entries", params={"viewerMember": "architect"})
            architect_stores = client.get("/memory/stores", params={"viewerMember": "architect"})
            architect_proposals = client.get("/memory/proposals", params={"viewerMember": "architect"})
            self.assertEqual(architect_entries.status_code, 200)
            self.assertIn("CUSTOMER-X-SECRET", str(architect_entries.json()))
            self.assertFalse(_record(architect_entries.json(), "private-strategy-secret")["spec"].get("redacted", False))
            self.assertFalse(_record(architect_stores.json(), "architect-personal-memory")["spec"].get("redacted", False))
            self.assertEqual(architect_proposals.status_code, 200)
            self.assertIn("CUSTOMER-PROPOSAL-SECRET", str(architect_proposals.json()))
            self.assertFalse(_record(architect_proposals.json(), "private-proposal-secret")["spec"].get("redacted", False))

    def test_scoped_memory_search_uses_authenticated_viewer_identity(self) -> None:
        env = {
            **AUTH_ENV_OFF,
            VIEWER_TOKEN_MAP_ENV: '{"frontend-human":"frontend-token","architect":"architect-token"}',
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            _write_private_secret_memory(workspace)
            client = TestClient(create_app(workspace))

            missing = client.get("/projects/aiteamos/memory", params={"query": "CUSTOMER-Y"})
            self.assertEqual(missing.status_code, 401)

            mismatch = client.get(
                "/projects/aiteamos/memory",
                params={"query": "CUSTOMER-Y", "viewerMember": "architect"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(mismatch.status_code, 403)

            frontend_project = client.get(
                "/projects/aiteamos/memory",
                params={"query": "CUSTOMER-Y"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(frontend_project.status_code, 200)
            self.assertNotIn("CUSTOMER-Y-CONFIDENTIAL", str(frontend_project.json()))
            self.assertNotIn("private-strategy-confidential", _match_ids(frontend_project.json()))
            self.assertGreaterEqual(frontend_project.json()["excludedMatches"], 1)

            architect_project = client.get(
                "/projects/aiteamos/memory",
                params={"query": "CUSTOMER-Y"},
                headers={"Authorization": "Bearer architect-token"},
            )
            self.assertEqual(architect_project.status_code, 200)
            self.assertIn("CUSTOMER-Y-CONFIDENTIAL", str(architect_project.json()))
            self.assertIn("private-strategy-confidential", _match_ids(architect_project.json()))

            frontend_member = client.get(
                "/members/architect/memory",
                params={"query": "CUSTOMER-Y"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(frontend_member.status_code, 200)
            self.assertNotIn("CUSTOMER-Y-CONFIDENTIAL", str(frontend_member.json()))

            frontend_tool = client.get(
                "/mcp/tools/get_project_memory",
                params={"projectId": "aiteamos", "query": "CUSTOMER-Y"},
                headers={"Authorization": "Bearer frontend-token"},
            )
            self.assertEqual(frontend_tool.status_code, 200)
            self.assertNotIn("CUSTOMER-Y-CONFIDENTIAL", str(frontend_tool.json()))

            architect_mcp = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "scoped-memory",
                    "method": "tools/call",
                    "params": {
                        "name": "search_memory",
                        "arguments": {"query": "CUSTOMER-Y", "project": "aiteamos"},
                    },
                },
                headers={"Authorization": "Bearer architect-token"},
            )
            self.assertEqual(architect_mcp.status_code, 200)
            self.assertIn("CUSTOMER-Y-CONFIDENTIAL", str(architect_mcp.json()))


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _write_private_secret_memory(workspace: Path) -> None:
    _write_yaml(
        workspace / "memory" / "entries" / "private-strategy-secret.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryEntry",
            "metadata": {"name": "private-strategy-secret"},
            "spec": {
                "store": "architect-personal-memory",
                "path": "private/customer-x-strategy.md",
                "title": "Customer X strategy",
                "content": "CUSTOMER-X-SECRET should never appear in unauthenticated global projections.",
                "kind": "decision",
                "scope": "member",
                "confidence": 0.9,
                "sensitivity": "secret",
                "visibility": "private",
                "acl": {"read": ["member:architect"], "write": ["member:architect"]},
                "relatedMembers": ["architect"],
                "version": 1,
                "lineage": {"authorMember": "architect"},
                "lifecycle": "active",
            },
        },
    )
    _write_yaml(
        workspace / "memory" / "entries" / "private-strategy-confidential.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryEntry",
            "metadata": {"name": "private-strategy-confidential"},
            "spec": {
                "store": "architect-personal-memory",
                "path": "private/customer-y-plan.md",
                "title": "Customer Y plan",
                "content": "CUSTOMER-Y-CONFIDENTIAL should never appear in unauthorized scoped memory search.",
                "kind": "decision",
                "scope": "member",
                "confidence": 0.9,
                "sensitivity": "confidential",
                "visibility": "private",
                "acl": {"read": ["member:architect"], "write": ["member:architect"]},
                "relatedProjects": ["aiteamos"],
                "relatedMembers": ["architect"],
                "relatedAssignments": ["aiteamos-architecture"],
                "version": 1,
                "lineage": {"authorMember": "architect"},
                "lifecycle": "active",
            },
        },
    )
    _write_yaml(
        workspace / "memory" / "bindings" / "bind-private-secret-to-architect.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryBinding",
            "metadata": {"name": "bind-private-secret-to-architect"},
            "spec": {
                "store": "architect-personal-memory",
                "entry": "private-strategy-secret",
                "targetType": "member",
                "targetId": "architect",
                "access": ["read", "reference", "inject"],
                "reason": "Private strategy reminder for architect only.",
                "status": "active",
                "createdByMember": "architect",
            },
        },
    )
    _write_yaml(
        workspace / "memory" / "grants" / "grant-private-secret-to-architect.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryGrant",
            "metadata": {"name": "grant-private-secret-to-architect"},
            "spec": {
                "granteeMember": "architect",
                "grantorMember": "architect",
                "entries": ["private-strategy-secret"],
                "access": ["read", "reference", "inject"],
                "reason": "Private task context.",
                "status": "active",
            },
        },
    )
    _write_yaml(
        workspace / "memory" / "proposals" / "private-proposal-secret.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemoryProposal",
            "metadata": {"name": "private-proposal-secret"},
            "spec": {
                "project": "aiteamos",
                "member": "architect",
                "assignment": "aiteamos-architecture",
                "store": "architect-personal-memory",
                "entryPath": "private/customer-proposal-secret.md",
                "status": "approved",
                "approvedMemory": "private-strategy-secret",
                "kind": "lesson",
                "title": "Customer proposal secret",
                "content": "CUSTOMER-PROPOSAL-SECRET should never appear in unauthorized proposal projections.",
                "evidence": ["CUSTOMER-PROPOSAL-SECRET evidence"],
                "confidence": 0.91,
                "reviewGuidance": "private reviewer guidance",
                "reviewedAt": "2026-05-22T00:00:00Z",
                "reviewedByMember": "architect",
                "reviewReason": "CUSTOMER-PROPOSAL-SECRET reason",
                "decisionAudit": [
                    {
                        "decisionKind": "human_approval",
                        "decision": "approved",
                        "actorMember": "architect",
                        "actorMemberKind": "human",
                        "authority": "approve",
                        "reason": "CUSTOMER-PROPOSAL-SECRET audit",
                    }
                ],
            },
        },
    )


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _record(records: list[dict[str, object]], record_id: str) -> dict[str, object]:
    return next(record for record in records if record["id"] == record_id)


def _match_ids(payload: dict[str, object]) -> set[str]:
    return {str(match["id"]) for match in payload.get("matches", [])}


if __name__ == "__main__":
    unittest.main()
