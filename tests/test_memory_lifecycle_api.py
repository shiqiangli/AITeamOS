from __future__ import annotations

from pathlib import Path
import hashlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_workspace import append_run_journal, create_run, create_task, load_workspace, propose_memory


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class MemoryLifecycleApiTest(unittest.TestCase):
    def test_reviewed_manual_memory_store_and_entry_creation_can_bind_and_inject(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Manual memory creation context injection",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                execution_mode="managed_llm",
                acceptance=["reviewed manual memory appears in context"],
            )
            run = create_run(workspace, task_id=task.object_id, mode="managed_llm")
            client = TestClient(create_app(workspace))

            store_response = client.post(
                "/memory/stores",
                json={
                    "name": "Manual Reviewed Project Memory",
                    "actorMember": "frontend-human",
                    "storeType": "project",
                    "ownerProject": "aiteamos",
                    "description": "Reviewed store created through the API.",
                    "visibility": "project",
                    "reason": "test reviewed store creation",
                },
            )
            self.assertEqual(store_response.status_code, 200)
            store_payload = store_response.json()
            store_id = store_payload["store"]["id"]
            self.assertEqual(store_id, "manual-reviewed-project-memory")
            self.assertEqual(store_payload["store"]["spec"]["createdByMember"], "frontend-human")
            self.assertEqual(store_payload["decisionAudit"]["decision"], "created-memory-store")

            entry_response = client.post(
                "/memory/entries",
                json={
                    "title": "Manual reviewed memory enters context",
                    "content": "Reviewed manually created memory should be versioned, bound, and injected through the context compiler.",
                    "actorMember": "frontend-human",
                    "store": store_id,
                    "kind": "decision",
                    "scope": "project",
                    "evidence": ["test:manual-memory-create"],
                    "confidence": 0.88,
                    "reason": "test reviewed entry creation",
                    "bindTargetType": "assignment",
                    "bindTargetId": BACKEND_ASSIGNMENT,
                },
            )
            self.assertEqual(entry_response.status_code, 200)
            entry_payload = entry_response.json()
            memory_id = entry_payload["memory"]["id"]
            self.assertEqual(entry_payload["memory"]["spec"]["store"], store_id)
            self.assertEqual(entry_payload["memory"]["spec"]["lifecycle"], "active")
            self.assertEqual(entry_payload["memory"]["spec"]["lineage"]["reviewerMember"], "frontend-human")
            self.assertEqual(entry_payload["versions"][0]["spec"]["entry"], memory_id)
            self.assertEqual(entry_payload["versions"][0]["spec"]["contentSha256"], hashlib.sha256(entry_payload["memory"]["spec"]["content"].encode("utf-8")).hexdigest())
            self.assertEqual(entry_payload["bindings"][0]["spec"]["entry"], memory_id)
            self.assertEqual(entry_payload["bindings"][0]["spec"]["targetType"], "assignment")
            self.assertEqual(entry_payload["bindings"][0]["spec"]["targetId"], BACKEND_ASSIGNMENT)

            updated = load_workspace(workspace)
            self.assertIn(store_id, updated.memory_stores)
            self.assertIn(memory_id, updated.memory_entries)
            self.assertIn(entry_payload["versions"][0]["id"], updated.memory_versions)
            self.assertIn(entry_payload["bindings"][0]["id"], updated.memory_bindings)

            preview = client.get(f"/runs/{run.object_id}/context-preview")
            self.assertEqual(preview.status_code, 200)
            self.assertIn(
                memory_id,
                {item["memory"] for item in preview.json()["manifest"]["sources"]["selectedMemory"]},
            )
            self.assertIn("Reviewed manually created memory", preview.json()["capsule"])

            digital_create = client.post(
                "/memory/entries",
                json={
                    "title": "Digital direct memory",
                    "content": "Digital members must use proposals instead of direct reviewed memory creation.",
                    "actorMember": BACKEND_MEMBER,
                    "store": store_id,
                },
            )
            self.assertEqual(digital_create.status_code, 400)
            self.assertIn("requires a human or hybrid", digital_create.json()["detail"])

    def test_memory_proposal_approval_creates_binding_and_injects_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Memory approval context injection",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                execution_mode="managed_llm",
                acceptance=["approved memory appears in the next context capsule"],
            )
            run = create_run(workspace, task_id=task.object_id, mode="managed_llm")
            evidence_path = append_run_journal(
                workspace,
                run.object_id,
                title="Verified lesson",
                body="Memory approval capsule lesson must be injected only after review approval.",
            )
            proposal = propose_memory(
                workspace,
                project="aiteamos",
                source_run=run.object_id,
                title="Memory approval capsule lesson",
                content="Approved memory from a reviewed run should be injected through an active MemoryBinding.",
                kind="procedural",
                confidence=0.92,
                evidence=[evidence_path],
                review_guidance="Human reviewed test evidence before approval.",
            )
            client = TestClient(create_app(workspace))

            queue = client.get("/memory/proposals/queue")
            approval = client.post(
                f"/memory/proposals/{proposal.object_id}/approve",
                json={"reviewerMember": "frontend-human", "reason": "test approval"},
            )

            self.assertEqual(queue.status_code, 200)
            queue_item = next(item for item in queue.json()["items"] if item["id"] == proposal.object_id)
            self.assertIn(queue_item["queueStatus"], {"ready", "ready-with-warnings"})
            self.assertEqual(approval.status_code, 200)
            approved_payload = approval.json()
            memory_id = approved_payload["memory"]["id"]
            self.assertEqual(approved_payload["proposal"]["spec"]["approvedMemory"], memory_id)
            self.assertEqual(approved_payload["proposal"]["spec"]["reviewedByMember"], "frontend-human")
            self.assertEqual(approved_payload["proposal"]["spec"]["reviewReason"], "test approval")
            self.assertEqual(approved_payload["proposal"]["spec"]["decisionAudit"][0]["decision"], "approved")
            self.assertEqual(approved_payload["proposal"]["spec"]["decisionAudit"][0]["actorMember"], "frontend-human")
            self.assertEqual(approved_payload["versions"][0]["spec"]["entry"], memory_id)
            self.assertEqual(approved_payload["versions"][0]["spec"]["createdByMember"], "frontend-human")
            self.assertEqual(approved_payload["bindings"][0]["spec"]["entry"], memory_id)
            self.assertEqual(approved_payload["bindings"][0]["spec"]["targetType"], "assignment")
            self.assertEqual(approved_payload["bindings"][0]["spec"]["targetId"], BACKEND_ASSIGNMENT)
            self.assertEqual(approved_payload["bindings"][0]["spec"]["createdByMember"], "frontend-human")

            updated = load_workspace(workspace)
            self.assertIn(memory_id, updated.memory_entries)
            self.assertIn(approved_payload["bindings"][0]["id"], updated.memory_bindings)
            self.assertEqual(updated.memory_entries[memory_id].spec.lifecycle, "active")
            self.assertEqual(updated.memory_entries[memory_id].spec.lineage.reviewerMember, "frontend-human")

            preview = client.get(f"/runs/{run.object_id}/context-preview")
            self.assertEqual(preview.status_code, 200)
            selected_memory = preview.json()["manifest"]["sources"]["selectedMemory"]
            self.assertIn(memory_id, {item["memory"] for item in selected_memory})
            self.assertIn("Approved memory from a reviewed run", preview.json()["capsule"])

            stale = client.post(
                f"/memory/entries/{memory_id}/stale",
                json={"reason": "simulate stale review gate"},
            )
            self.assertEqual(stale.status_code, 200)
            self.assertEqual(stale.json()["spec"]["lifecycle"], "stale")
            stale_preview = client.get(f"/runs/{run.object_id}/context-preview")
            self.assertIn(
                f"stale memory omitted {memory_id}",
                stale_preview.json()["manifest"]["exclusions"],
            )
            stale_decisions = stale_preview.json()["manifest"]["sourceDecisions"]
            self.assertIn(
                f"stale memory omitted {memory_id}",
                {item["reason"] for item in stale_decisions if item["outcome"] == "excluded"},
            )

            verified = client.post(
                f"/memory/entries/{memory_id}/verify",
                json={"reason": "verified again for context injection"},
            )
            self.assertEqual(verified.status_code, 200)
            self.assertEqual(verified.json()["spec"]["lifecycle"], "active")
            verified_preview = client.get(f"/runs/{run.object_id}/context-preview")
            self.assertIn(
                memory_id,
                {item["memory"] for item in verified_preview.json()["manifest"]["sources"]["selectedMemory"]},
            )

    def test_memory_proposal_repair_and_reject_are_explicit_api_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Memory repair review",
                assigned_member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                acceptance=["repair populates missing evidence before review"],
            )
            run = create_run(workspace, task_id=task.object_id)
            append_run_journal(
                workspace,
                run.object_id,
                title="Repair evidence",
                body="The run journal is safe evidence for proposal repair.",
            )
            proposal = propose_memory(
                workspace,
                project="aiteamos",
                source_run=run.object_id,
                title="Repairable memory proposal",
                content="Repair should add run evidence and confidence before the reviewer decides.",
                kind="procedural",
            )
            client = TestClient(create_app(workspace))

            repair = client.post(f"/memory/proposals/{proposal.object_id}/repair", json={"reason": "test repair"})
            reject = client.post(
                f"/memory/proposals/{proposal.object_id}/reject",
                json={"reviewerMember": "frontend-human", "reason": "not accepted"},
            )

            self.assertEqual(repair.status_code, 200)
            repaired = repair.json()["spec"]
            self.assertEqual(repaired["confidence"], 1.0)
            self.assertIn(f"runs/{run.object_id}/journal.md", repaired["evidence"])
            self.assertEqual(reject.status_code, 200)
            self.assertEqual(reject.json()["spec"]["status"], "rejected")
            self.assertEqual(reject.json()["spec"]["reviewedByMember"], "frontend-human")
            self.assertEqual(reject.json()["spec"]["reviewReason"], "not accepted")
            self.assertEqual(reject.json()["spec"]["decisionAudit"][0]["decision"], "rejected")


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
