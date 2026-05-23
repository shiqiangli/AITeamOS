from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_workspace import (
    build_run_assistance_bundle,
    build_run_assistance_bundle_archive,
    build_run_assistance_package,
    create_run,
    create_task,
    ingest_run_outputs,
    load_workspace,
    run_verification_commands,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class AssistedIngestTest(unittest.TestCase):
    def test_human_run_assistance_package_prepares_work_before_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_frontend_human_run(workspace)
            index = load_workspace(workspace)
            api_run_path = f"/workspaces/{index.workspace.object_id}/runs/{run.object_id}"

            package = build_run_assistance_package(index, run.object_id)

            self.assertTrue(package.readyForAssistedExecution)
            self.assertEqual(package.member, "frontend-human")
            self.assertEqual(package.memberKind, "human")
            self.assertEqual(package.assignment, "aiteamos-dashboard")
            self.assertIn("apps/dashboard/**", package.allowedWrites)
            self.assertIn("journal", package.ingestContract.requiredInputs)
            self.assertEqual(package.ingestContract.durableMutationBoundary, f"{api_run_path}/assisted-ingest")
            self.assertEqual(package.reviewContract["reviewBoundary"], f"{api_run_path}/reviews")
            self.assertIn("projectDocs", package.contextSources)
            self.assertTrue(package.entrypoints)

            client = TestClient(create_app(workspace))
            response = client.get(f"/runs/{run.object_id}/assistance-package")
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertTrue(payload["readyForAssistedExecution"])
            self.assertEqual(payload["packageKind"], "human_assisted_execution_package")
            self.assertIn("apps/dashboard/**", payload["allowedWrites"])

    def test_human_run_assistance_bundle_projects_ide_handoff_files_before_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_frontend_human_run(workspace)
            index = load_workspace(workspace)
            api_run_path = f"/workspaces/{index.workspace.object_id}/runs/{run.object_id}"

            bundle = build_run_assistance_bundle(index, run.object_id)

            self.assertTrue(bundle.ready)
            self.assertEqual(bundle.bundleKind, "human_hybrid_assisted_handoff_bundle")
            self.assertEqual(bundle.package.ingestContract.durableMutationBoundary, f"{api_run_path}/assisted-ingest")
            file_paths = {file.path for file in bundle.files}
            self.assertIn("README.md", file_paths)
            self.assertIn("context-capsule.md", file_paths)
            self.assertIn("aiteamos-handoff.json", file_paths)
            self.assertIn("assisted-ingest-template.json", file_paths)
            readme = next(file for file in bundle.files if file.path == "README.md")
            self.assertIn(f"{api_run_path}/assisted-ingest", readme.content)
            handoff = next(file for file in bundle.files if file.path == "aiteamos-handoff.json")
            handoff_payload = json.loads(handoff.content)
            self.assertEqual(handoff_payload["run"], run.object_id)
            self.assertIn("apps/dashboard/**", handoff_payload["allowedWrites"])
            template = next(file for file in bundle.files if file.path == "assisted-ingest-template.json")
            self.assertIn("memoryProposal", json.loads(template.content))

            archive_name, archive_bytes = build_run_assistance_bundle_archive(index, run.object_id)
            self.assertEqual(archive_name, f"{run.object_id}-assisted-handoff.zip")
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                self.assertIn("aiteamos-bundle.json", archive.namelist())
                self.assertIn("README.md", archive.namelist())
                self.assertIn("assisted-ingest-template.json", archive.namelist())
                archived_manifest = json.loads(archive.read("aiteamos-bundle.json").decode("utf-8"))
                self.assertEqual(archived_manifest["kind"], "AiteamosBundle")
                self.assertEqual(archived_manifest["schemaVersion"], "aiteamos-bundle.v1")
                self.assertEqual(archived_manifest["run"], run.object_id)

            client = TestClient(create_app(workspace))
            response = client.get(f"/runs/{run.object_id}/assistance-bundle")
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["fileCount"], len(bundle.files))
            self.assertEqual({file["path"] for file in payload["files"]}, file_paths)
            archive_response = client.get(f"/runs/{run.object_id}/assistance-bundle/archive")
            self.assertEqual(archive_response.status_code, 200, archive_response.text)
            self.assertEqual(archive_response.headers["content-type"], "application/zip")
            self.assertIn(f"{run.object_id}-assisted-handoff.zip", archive_response.headers["content-disposition"])
            with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
                self.assertIn("README.md", archive.namelist())
                self.assertIn("context-capsule.md", archive.namelist())

    def test_digital_run_assistance_package_is_a_blocked_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            package = build_run_assistance_package(load_workspace(workspace), run.object_id)

            self.assertFalse(package.readyForAssistedExecution)
            self.assertEqual(package.memberKind, "digital")
            self.assertIn("Assisted execution packages are only ready for human or hybrid TeamMembers.", package.blockers)

    def test_human_run_assisted_ingest_api_enters_review_and_memory_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_frontend_human_run(workspace)
            client = TestClient(create_app(workspace))

            response = client.post(
                f"/runs/{run.object_id}/assisted-ingest",
                json={
                    "journal": "Human IDE result\nSECRET_TOKEN=secret-value",
                    "diffPatch": _dashboard_safe_diff(),
                    "testLog": "pytest: ok\napi_key: EXAMPLE_API_KEY",
                    "reviewTarget": {
                        "type": "external_review",
                        "url": "https://example.invalid/reviews/aiteamos-dashboard-human",
                        "description": "Human assisted review target",
                    },
                    "memoryProposal": {
                        "title": "Human assisted ingest evidence",
                        "content": "Human assisted runs should return journal, diff, tests, review target, and reviewed memory proposal.",
                        "kind": "procedural",
                        "confidence": 0.82,
                    },
                },
            )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["spec"]["member"], "frontend-human")
            self.assertEqual(payload["spec"]["memberKind"], "human")
            self.assertEqual(payload["spec"]["status"], "REVIEW")
            self.assertEqual(payload["spec"]["reviewTarget"]["type"], "external_review")
            self.assertEqual(payload["spec"]["ingest"]["missing"], [])
            self.assertEqual(len(payload["spec"]["ingest"]["artifactManifests"]), 3)
            self.assertEqual(len(payload["spec"]["memoryProposals"]), 1)

            index = load_workspace(workspace)
            updated_run = index.runs[run.object_id]
            self.assertEqual(index.tasks[run.spec.task].spec.status, "REVIEW")
            self.assertEqual(updated_run.spec.status, "REVIEW")
            self.assertEqual(updated_run.spec.ingest["member"], "frontend-human")
            self.assertEqual(updated_run.spec.ingest["assignment"], "aiteamos-dashboard")
            self.assertIn("SECRET_TOKEN=[REDACTED]", index.run_journals[run.object_id])
            self.assertIn("api_key: [REDACTED]", (workspace / "runs" / run.object_id / "test.log").read_text(encoding="utf-8"))
            self.assertTrue(any(event["type"] == "assisted.ingest.completed" for event in index.run_events[run.object_id]))

            proposal = index.memory_proposals[payload["spec"]["memoryProposals"][0]]
            self.assertEqual(proposal.spec.member, "frontend-human")
            self.assertEqual(proposal.spec.assignment, "aiteamos-dashboard")
            self.assertEqual(proposal.spec.sourceTask, run.spec.task)
            self.assertEqual(proposal.spec.sourceRun, run.object_id)
            self.assertEqual(proposal.spec.sourceIngestId, updated_run.spec.ingest["lastIngestId"])

    def test_ingest_writes_schema_artifact_manifests_and_redacts_text_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            updated = ingest_run_outputs(
                workspace,
                run.object_id,
                journal="Assisted note\nEXAMPLE_TOKEN=EXAMPLE_TOKEN",
                diff_patch=_safe_diff(),
                test_log="api_key: EXAMPLE_API_KEY",
                review_target={"type": "branch", "url": "https://example.invalid/aiteamos/branch"},
                memory_proposal={
                    "title": "Ingest artifact discipline",
                    "content": "Assisted ingest should manifest artifacts and redact EXAMPLE_TOKEN=EXAMPLE_TOKEN.",
                    "kind": "procedural",
                },
            )

            self.assertEqual(updated.spec.status, "REVIEW")
            self.assertEqual(len(updated.spec.ingest["artifactManifests"]), 3)
            index = load_workspace(workspace)
            self.assertEqual(len(index.artifacts), 3)
            self.assertTrue(all(artifact.spec.run == run.object_id for artifact in index.artifacts.values()))
            self.assertTrue(all(artifact.spec.exportPolicy == "sanitize" for artifact in index.artifacts.values()))

            journal = (workspace / "runs" / run.object_id / "journal.md").read_text(encoding="utf-8")
            test_log = (workspace / "runs" / run.object_id / "test.log").read_text(encoding="utf-8")
            self.assertIn("EXAMPLE_TOKEN=[REDACTED]", journal)
            self.assertIn("api_key: [REDACTED]", test_log)
            self.assertNotIn("EXAMPLE_TOKEN=EXAMPLE_TOKEN", journal)
            self.assertNotIn("EXAMPLE_API_KEY", test_log)
            proposal = [
                item for item in index.memory_proposals.values() if item.spec.sourceIngestId == updated.spec.ingest["lastIngestId"]
            ][0]
            self.assertEqual(proposal.spec.member, "backend-digital")
            self.assertEqual(proposal.spec.assignment, "aiteamos-backend-runtime")
            self.assertEqual(proposal.spec.sourceTask, run.spec.task)
            self.assertIn("EXAMPLE_TOKEN=[REDACTED]", proposal.spec.content)

            event_count = len(index.run_events[run.object_id])
            artifact_count = len(index.artifacts)
            duplicate = ingest_run_outputs(
                workspace,
                run.object_id,
                journal="Assisted note\nEXAMPLE_TOKEN=EXAMPLE_TOKEN",
                diff_patch=_safe_diff(),
                test_log="api_key: EXAMPLE_API_KEY",
                review_target={"type": "branch", "url": "https://example.invalid/aiteamos/branch"},
                memory_proposal={
                    "title": "Ingest artifact discipline",
                    "content": "Assisted ingest should manifest artifacts and redact EXAMPLE_TOKEN=EXAMPLE_TOKEN.",
                    "kind": "procedural",
                },
            )
            duplicate_index = load_workspace(workspace)
            self.assertEqual(duplicate.spec.ingest["lastIngestId"], updated.spec.ingest["lastIngestId"])
            self.assertEqual(len(duplicate_index.run_events[run.object_id]), event_count)
            self.assertEqual(len(duplicate_index.artifacts), artifact_count)

    def test_ingest_rejects_secret_like_diff_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            with self.assertRaises(ValueError):
                ingest_run_outputs(
                    workspace,
                    run.object_id,
                    journal="Assisted work",
                    diff_patch=_secret_like_diff(),
                )

            self.assertFalse((workspace / "runs" / run.object_id / "diff.patch").exists())
            self.assertFalse(list((workspace / "artifacts" / "manifests").glob(f"ART-{run.object_id}-*.yaml")))

    def test_verification_commands_write_artifact_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = _copy_workspace(temp_root)
            worktree = temp_root / "worktree"
            worktree.mkdir()
            run = _create_backend_run(workspace)

            results = run_verification_commands(
                workspace,
                run.object_id,
                worktree=worktree,
                commands=["printf verification-ok"],
                timeout_seconds=30,
            )

            self.assertEqual(results[0].returncode, 0)
            index = load_workspace(workspace)
            artifacts = {artifact.spec.kind: artifact for artifact in index.artifacts.values()}
            self.assertIn("test_log", artifacts)
            self.assertIn("command_log", artifacts)
            outputs = index.runs[run.object_id].spec.outputs
            self.assertTrue(
                [
                    output
                    for output in outputs
                    if isinstance(output, dict)
                    and output.get("type") == "test_log"
                    and output.get("artifactManifest", "").startswith("artifacts/manifests/")
                ]
            )
            self.assertTrue(
                [
                    output
                    for output in outputs
                    if isinstance(output, dict)
                    and output.get("type") == "command_log"
                    and output.get("artifactManifest", "").startswith("artifacts/manifests/")
                ]
            )


def _create_backend_run(workspace: Path) -> object:
    task = create_task(
        workspace,
        title="Assisted ingest task",
        assigned_member="backend-digital",
        assignment="aiteamos-backend-runtime",
        acceptance=["ingest is safe"],
    )
    return create_run(workspace, task_id=task.object_id)


def _create_frontend_human_run(workspace: Path) -> object:
    task = create_task(
        workspace,
        title="Human assisted ingest task",
        assigned_member="frontend-human",
        assignment="aiteamos-dashboard",
        execution_mode="assisted",
        acceptance=["human assisted ingest is reviewable"],
    )
    return create_run(workspace, task_id=task.object_id, mode="assisted")


def _safe_diff() -> str:
    return "\n".join(
        [
            "diff --git a/packages/workspace/ingest.txt b/packages/workspace/ingest.txt",
            "new file mode 100644",
            "index 0000000..1111111",
            "--- /dev/null",
            "+++ b/packages/workspace/ingest.txt",
            "@@ -0,0 +1 @@",
            "+assisted ingest coverage",
            "",
        ]
    )


def _dashboard_safe_diff() -> str:
    return "\n".join(
        [
            "diff --git a/apps/dashboard/assisted-ingest.txt b/apps/dashboard/assisted-ingest.txt",
            "new file mode 100644",
            "index 0000000..1111111",
            "--- /dev/null",
            "+++ b/apps/dashboard/assisted-ingest.txt",
            "@@ -0,0 +1 @@",
            "+human assisted ingest coverage",
            "",
        ]
    )


def _secret_like_diff() -> str:
    return "\n".join(
        [
            "diff --git a/packages/workspace/leak.txt b/packages/workspace/leak.txt",
            "new file mode 100644",
            "--- /dev/null",
            "+++ b/packages/workspace/leak.txt",
            "@@ -0,0 +1 @@",
            "+EXAMPLE_TOKEN=EXAMPLE_TOKEN",
            "",
        ]
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
