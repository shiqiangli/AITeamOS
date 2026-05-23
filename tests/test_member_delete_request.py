from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import yaml

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_workspace import export_workspace_bundle, load_workspace, request_member_delete


REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET_SENTINEL = "PRIVATE_MEMBER_DELETE_SHOULD_NOT_EXPORT"
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class MemberDeleteRequestTest(unittest.TestCase):
    def test_delete_request_redacts_member_references_and_export_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _seed_member_delete_references(workspace)

            result = request_member_delete(
                workspace,
                "backend-digital",
                actor_member="frontend-human",
                reason="privacy delete request",
            )

            self.assertEqual(result["status"], "redacted")
            self.assertEqual(result["member"], "backend-digital")
            self.assertIn("RUN-20260520T104310792", result["references"]["runs"])
            self.assertIn("MSG-member-delete-secret", result["references"]["messages"])
            self.assertIn("HANDOFF-member-delete-secret", result["references"]["handoffs"])
            self.assertIn("GIT-20260521T090500000", result["references"]["gitActivity"])
            self.assertTrue(result["redactionQueue"])

            index = load_workspace(workspace)
            member = index.members["backend-digital"]
            self.assertEqual(member.spec.profile.status, "archived")
            self.assertEqual(member.spec.lifecycle, "redacted")
            self.assertEqual(member.spec.decisionAudit[-1].source, "member-delete-request")
            self.assertNotIn("Backend Digital Engineer", member.model_dump_json())

            run = index.runs["RUN-20260520T104310792"]
            self.assertEqual(run.spec.lifecycle, "redacted")
            self.assertEqual(run.spec.exportPolicy, "manifest-only")
            self.assertEqual(run.spec.decisionAudit[-1].source, "member-delete-request")
            self.assertNotIn(SECRET_SENTINEL, (workspace / "runs" / run.object_id / "journal.md").read_text(encoding="utf-8"))
            self.assertNotIn(SECRET_SENTINEL, (workspace / "runs" / run.object_id / "prompt_capsule.md").read_text(encoding="utf-8"))

            message = index.member_messages["MSG-member-delete-secret"]
            self.assertEqual(message.spec.status, "archived")
            self.assertEqual(message.spec.lifecycle, "redacted")
            self.assertEqual(message.spec.body, "Redacted by member delete request.")

            handoff = index.handoffs["HANDOFF-member-delete-secret"]
            self.assertEqual(handoff.spec.status, "cancelled")
            self.assertEqual(handoff.spec.lifecycle, "redacted")
            self.assertEqual(handoff.spec.problem, "Redacted by member delete request.")

            activity = index.git_activities["GIT-20260521T090500000"]
            self.assertEqual(activity.spec.lifecycle, "redacted")
            self.assertEqual(activity.spec.exportPolicy, "exclude")
            self.assertEqual(activity.spec.decisionAudit[-1].source, "member-delete-request")

            bundle_path = Path(temp_dir) / "workspace-export.zip"
            export_workspace_bundle(workspace, bundle_path, overwrite=True)
            exported = _zip_text(bundle_path)
            self.assertNotIn(SECRET_SENTINEL, exported)
            self.assertNotIn("Prepared reviewed branch evidence for the backend runtime implementation slice.", exported)

    def test_api_delete_request_returns_reference_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            _seed_member_delete_references(workspace)
            client = TestClient(create_app(workspace))

            response = client.post(
                "/members/backend-digital/delete-request",
                json={"actorMember": "frontend-human", "reason": "privacy delete request"},
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "redacted")
            self.assertIn("RUN-20260520T104310792", payload["references"]["runs"])
            self.assertIn("MSG-member-delete-secret", payload["references"]["messages"])
            self.assertIn("HANDOFF-member-delete-secret", payload["references"]["handoffs"])
            self.assertIn("GIT-20260521T090500000", payload["references"]["gitActivity"])
            self.assertEqual(payload["decisionAudit"]["source"], "member-delete-request")


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _seed_member_delete_references(workspace: Path) -> None:
    run_dir = workspace / "runs" / "RUN-20260520T104310792"
    (run_dir / "journal.md").write_text(f"private run journal {SECRET_SENTINEL}\n", encoding="utf-8")
    (run_dir / "prompt_capsule.md").write_text(f"private prompt capsule {SECRET_SENTINEL}\n", encoding="utf-8")
    (run_dir / "events.jsonl").write_text(f'{{"event":"secret","value":"{SECRET_SENTINEL}"}}\n', encoding="utf-8")
    _write_yaml(
        run_dir / "context_manifest.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "ContextManifest",
            "metadata": {"id": "seed-secret-context"},
            "spec": {"task": "TASK-20260520T104310792", "member": "backend-digital", "project": "aiteamos", "sources": {"secret": [SECRET_SENTINEL]}},
        },
    )
    _write_yaml(
        workspace / "im" / "messages" / "MSG-member-delete-secret.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "MemberMessage",
            "metadata": {"id": "MSG-member-delete-secret", "title": "Delete request seed message"},
            "spec": {
                "fromMember": "backend-digital",
                "toMembers": ["frontend-human"],
                "project": "aiteamos",
                "run": "RUN-20260520T104310792",
                "body": f"member-private message {SECRET_SENTINEL}",
            },
        },
    )
    _write_yaml(
        workspace / "im" / "handoffs" / "HANDOFF-member-delete-secret.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Handoff",
            "metadata": {"id": "HANDOFF-member-delete-secret", "title": "Delete request seed handoff"},
            "spec": {
                "fromMember": "backend-digital",
                "toMember": "frontend-human",
                "task": "TASK-20260520T104310792",
                "run": "RUN-20260520T104310792",
                "project": "aiteamos",
                "problem": f"member-private handoff {SECRET_SENTINEL}",
            },
        },
    )


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def _zip_text(path: Path) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as bundle:
        for name in bundle.namelist():
            if name.endswith((".yaml", ".yml", ".json", ".jsonl", ".md", ".txt")):
                chunks.append(bundle.read(name).decode("utf-8", errors="replace"))
    return "\n".join(chunks)


if __name__ == "__main__":
    unittest.main()
