from __future__ import annotations

from pathlib import Path
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_schema import API_VERSION
from aiteamos_workspace import create_run, create_task, load_workspace
from aiteamos_workspace.io import write_yaml
from aiteamos_workspace.knowledge_health import evaluate_knowledge_health


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class MemoryHealthTest(unittest.TestCase):
    def test_memory_health_reports_orphans_and_expired_grants_and_context_excludes_them(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Expired memory grant exclusion",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                execution_mode="managed_llm",
                acceptance=["expired grant memory is not injected"],
            )
            run = create_run(workspace, task_id=task.object_id, mode="managed_llm")
            _write_expired_grant_fixture(workspace)

            health = evaluate_knowledge_health(load_workspace(workspace))

            self.assertGreaterEqual(health["summary"]["orphanedBindings"], 1)
            self.assertGreaterEqual(health["summary"]["expiredGrants"], 1)
            self.assertTrue(any(issue["kind"] == "memory-binding-orphan-entry" and issue["ref"] == "bind-missing-health-entry" for issue in health["issues"]))
            self.assertTrue(any(issue["kind"] == "memory-grant-expired" and issue["ref"] == "grant-expired-health-memory" for issue in health["issues"]))

            client = TestClient(create_app(workspace))
            response = client.get(f"/runs/{run.object_id}/context-preview")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            selected_memory_ids = {item["memory"] for item in payload["manifest"]["sources"]["selectedMemory"]}
            self.assertNotIn("expired-grant-only-memory", selected_memory_ids)
            self.assertNotIn("Expired grant only memory should never appear in a context capsule.", payload["capsule"])
            self.assertIn("expired memory grant omitted grant-expired-health-memory", payload["manifest"]["exclusions"])

    def test_memory_health_remediation_dry_run_and_apply_are_audited(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            _write_expired_grant_fixture(workspace)
            client = TestClient(create_app(workspace))

            dry_run = client.post(
                "/knowledge/health/remediation",
                json={
                    "issueKind": "memory-binding-orphan-entry",
                    "ref": "bind-missing-health-entry",
                    "action": "archive-binding",
                    "actorMember": "frontend-human",
                    "reason": "Archive orphaned health fixture after review.",
                    "dryRun": True,
                },
            )

            self.assertEqual(dry_run.status_code, 200)
            dry_payload = dry_run.json()
            self.assertFalse(dry_payload["applied"])
            self.assertEqual(dry_payload["decisionAudit"][0]["decisionKind"], "human_approval")
            self.assertEqual(load_workspace(workspace).memory_bindings["bind-missing-health-entry"].spec.status, "active")

            applied = client.post(
                "/knowledge/health/remediation",
                json={
                    "issueKind": "memory-binding-orphan-entry",
                    "ref": "bind-missing-health-entry",
                    "action": "archive-binding",
                    "actorMember": "frontend-human",
                    "reason": "Archive orphaned health fixture after review.",
                    "dryRun": False,
                },
            )

            self.assertEqual(applied.status_code, 200)
            applied_payload = applied.json()
            self.assertTrue(applied_payload["applied"])
            self.assertEqual(load_workspace(workspace).memory_bindings["bind-missing-health-entry"].spec.status, "archived")

            revoked = client.post(
                "/knowledge/health/remediation",
                json={
                    "issueKind": "memory-grant-expired",
                    "ref": "grant-expired-health-memory",
                    "action": "revoke-grant",
                    "actorMember": "frontend-human",
                    "reason": "Revoke expired health fixture after review.",
                    "dryRun": False,
                },
            )

            self.assertEqual(revoked.status_code, 200)
            self.assertTrue(revoked.json()["applied"])
            current = load_workspace(workspace)
            self.assertEqual(current.memory_grants["grant-expired-health-memory"].spec.status, "revoked")
            refreshed = evaluate_knowledge_health(current)
            self.assertFalse(any(issue["kind"] == "memory-binding-orphan-entry" and issue["ref"] == "bind-missing-health-entry" for issue in refreshed["issues"]))
            self.assertFalse(any(issue["kind"] == "memory-grant-expired" and issue["ref"] == "grant-expired-health-memory" for issue in refreshed["issues"]))


def _write_expired_grant_fixture(workspace: Path) -> None:
    write_yaml(
        workspace / "memory" / "stores" / "expired-health-store.yaml",
        {
            "apiVersion": API_VERSION,
            "kind": "MemoryStore",
            "metadata": {"id": "expired-health-store"},
            "spec": {
                "storeType": "project",
                "ownerProject": "aiteamos",
                "visibility": "project",
                "lifecycle": "active",
            },
        },
    )
    write_yaml(
        workspace / "memory" / "entries" / "expired-grant-only-memory.yaml",
        {
            "apiVersion": API_VERSION,
            "kind": "MemoryEntry",
            "metadata": {"id": "expired-grant-only-memory"},
            "spec": {
                "store": "expired-health-store",
                "path": "decisions/expired-grant-only-memory.md",
                "title": "Expired grant only memory",
                "content": "Expired grant only memory should never appear in a context capsule.",
                "kind": "decision",
                "scope": "project",
                "source": "tests/test_memory_health.py",
                "evidence": ["tests/test_memory_health.py"],
                "confidence": 0.9,
                "lastVerifiedAt": "2026-05-21T00:00:00+08:00",
                "sensitivity": "internal",
                "visibility": "project",
                "relatedProjects": ["aiteamos"],
                "relatedMembers": [BACKEND_MEMBER],
                "relatedAssignments": [BACKEND_ASSIGNMENT],
                "version": 1,
                "lineage": {"authorMember": "architect", "evidence": ["tests/test_memory_health.py"]},
                "lifecycle": "active",
            },
        },
    )
    write_yaml(
        workspace / "memory" / "grants" / "grant-expired-health-memory.yaml",
        {
            "apiVersion": API_VERSION,
            "kind": "MemoryGrant",
            "metadata": {"id": "grant-expired-health-memory"},
            "spec": {
                "granteeMember": BACKEND_MEMBER,
                "grantorMember": "architect",
                "entries": ["expired-grant-only-memory"],
                "access": ["read", "reference", "inject"],
                "reason": "Expired grant fixture must be visible in health but excluded from context.",
                "expiresAt": "2000-01-01T00:00:00+00:00",
                "status": "active",
            },
        },
    )
    write_yaml(
        workspace / "memory" / "bindings" / "bind-missing-health-entry.yaml",
        {
            "apiVersion": API_VERSION,
            "kind": "MemoryBinding",
            "metadata": {"id": "bind-missing-health-entry"},
            "spec": {
                "entry": "missing-health-entry",
                "targetType": "assignment",
                "targetId": BACKEND_ASSIGNMENT,
                "access": ["read", "reference", "inject"],
                "reason": "Orphan binding fixture for memory health.",
                "status": "active",
                "createdByMember": "manager",
            },
        },
    )


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
