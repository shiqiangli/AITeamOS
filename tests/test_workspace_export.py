from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
import unittest
import zipfile

import yaml

from aiteamos_schema.models import KIND_TO_MODEL
from aiteamos_workspace import export_workspace_bundle
from aiteamos_workspace.artifacts import record_artifact_manifest
from tools.cli.aiteamos import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[1]


class WorkspaceExportTest(unittest.TestCase):
    def test_sanitized_export_excludes_derived_and_sensitive_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            output = Path(temp_dir) / "aiteamos-sanitized.zip"
            run_dir = workspace / "runs" / "RUN-0001"

            _write(workspace / "indexes" / "derived.sqlite", "derived database")
            _write(workspace / "artifacts" / "blob" / "raw.bin", "raw blob")
            _write(workspace / "artifacts" / "cache" / "cached.txt", "cached content")
            _write(workspace / "artifacts" / "worktrees" / "RUN-0001" / "file.txt", "worktree content")
            _write(
                workspace / "artifacts" / "manifests" / "artifact.yaml",
                "\n".join(
                    [
                        "apiVersion: aiteamos.dev/v1alpha1",
                        "kind: Artifact",
                        "metadata:",
                        "  id: artifact",
                        "spec:",
                        "  run: RUN-0001",
                        "  kind: small_log",
                        "  uri: runs/RUN-0001/small.log",
                        "",
                    ]
                ),
            )
            _write(run_dir / "raw_provider_response.json", '{"provider":"example"}\n')
            _write(run_dir / "model_output.md", "raw model body that should stay out of sanitized export\n")
            model_manifest = record_artifact_manifest(
                workspace,
                "RUN-0001",
                "model_output",
                "runs/RUN-0001/model_output.md",
                source_id="model-output",
            )
            _write(run_dir / "screenshot.png", "not really an image")
            _write(run_dir / "embedding.npy", "not really an embedding")
            _write(run_dir / "test.log", "L" * 128)
            _write(run_dir / "small.log", "small log")
            _write(workspace / "tasks" / "sanitized-secret.md", "EXAMPLE_TOKEN=placeholder-value\n")

            result = export_workspace_bundle(workspace, output, max_log_bytes=32)

            self.assertTrue(result["sanitized"])
            with zipfile.ZipFile(output) as bundle:
                names = set(bundle.namelist())
                archive_text = "\n".join(bundle.read(name).decode("utf-8", errors="replace") for name in sorted(names))
                self.assertIn(".aiteamos/workspace.yaml", names)
                self.assertIn(".aiteamos/artifacts/manifests/artifact.yaml", names)
                self.assertIn(f".aiteamos/{model_manifest}", names)
                self.assertIn(".aiteamos/runs/RUN-0001/small.log", names)
                self.assertIn(".aiteamos/tasks/sanitized-secret.md", names)
                self.assertNotIn(".aiteamos/indexes/derived.sqlite", names)
                self.assertNotIn(".aiteamos/artifacts/blob/raw.bin", names)
                self.assertNotIn(".aiteamos/artifacts/cache/cached.txt", names)
                self.assertNotIn(".aiteamos/artifacts/worktrees/RUN-0001/file.txt", names)
                self.assertNotIn(".aiteamos/runs/RUN-0001/raw_provider_response.json", names)
                self.assertNotIn(".aiteamos/runs/RUN-0001/model_output.md", names)
                self.assertNotIn(".aiteamos/runs/RUN-0001/screenshot.png", names)
                self.assertNotIn(".aiteamos/runs/RUN-0001/embedding.npy", names)
                self.assertNotIn(".aiteamos/runs/RUN-0001/test.log", names)

                redacted = bundle.read(".aiteamos/tasks/sanitized-secret.md").decode("utf-8")
                self.assertIn("EXAMPLE_TOKEN=[REDACTED]", redacted)
                self.assertNotIn("placeholder-value", redacted)
                model_manifest_text = bundle.read(f".aiteamos/{model_manifest}").decode("utf-8")
                self.assertIn("exportPolicy: manifest_only", model_manifest_text)
                self.assertNotIn("raw model body", archive_text)

                manifest = json.loads(bundle.read("AITEAMOS_EXPORT_MANIFEST.json").decode("utf-8"))
                self.assertTrue(manifest["sanitized"])
                reasons = {item["reason"] for item in manifest["excludedFiles"]}
                self.assertIn("derived-database", reasons)
                self.assertIn("artifact-blob-or-worktree", reasons)
                self.assertIn("raw-provider-response", reasons)
                self.assertIn("artifact-manifest-only", reasons)
                self.assertIn("screenshot-or-video", reasons)
                self.assertIn("embedding-or-vector-state", reasons)
                self.assertIn("long-log", reasons)

    def test_sanitized_export_respects_git_activity_export_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            output = Path(temp_dir) / "aiteamos-sanitized.zip"

            _write_git_activity(
                workspace,
                "GIT-EXPORT-INCLUDE",
                export_policy="include",
                summary="Included GitActivity retains active provider detail.",
                external_id="provider-include-secret",
                url="https://github.com/example/private/pull/42",
                refs=["refs/heads/include-private-ref"],
            )
            _write_git_activity(
                workspace,
                "GIT-EXPORT-SANITIZE",
                export_policy="sanitize",
                summary="Sanitized GitActivity mentions private customer branch.",
                external_id="provider-sanitize-secret",
                url="https://github.com/example/private/pull/43",
                refs=["refs/heads/customer-secret-ref"],
            )
            _write_git_activity(
                workspace,
                "GIT-EXPORT-MANIFEST",
                export_policy="manifest-only",
                summary="Manifest-only GitActivity must omit provider detail.",
                external_id="provider-manifest-secret",
                url="https://github.com/example/private/pull/44",
                refs=["refs/heads/manifest-only-secret-ref"],
            )
            _write_git_activity(
                workspace,
                "GIT-EXPORT-ARCHIVED",
                lifecycle="archived",
                export_policy="include",
                summary="Archived GitActivity must still redact private detail.",
                external_id="provider-archived-secret",
                url="https://github.com/example/private/pull/45",
                refs=["refs/heads/archived-secret-ref"],
            )
            _write_git_activity(
                workspace,
                "GIT-EXPORT-EXCLUDE",
                lifecycle="redacted",
                export_policy="exclude",
                summary="Excluded GitActivity must not appear in the bundle.",
                external_id="provider-exclude-secret",
                url="https://github.com/example/private/pull/46",
                refs=["refs/heads/exclude-secret-ref"],
            )

            export_workspace_bundle(workspace, output)

            with zipfile.ZipFile(output) as bundle:
                names = set(bundle.namelist())
                self.assertIn(".aiteamos/git_activity/GIT-EXPORT-INCLUDE.yaml", names)
                self.assertIn(".aiteamos/git_activity/GIT-EXPORT-SANITIZE.yaml", names)
                self.assertIn(".aiteamos/git_activity/GIT-EXPORT-MANIFEST.yaml", names)
                self.assertIn(".aiteamos/git_activity/GIT-EXPORT-ARCHIVED.yaml", names)
                self.assertNotIn(".aiteamos/git_activity/GIT-EXPORT-EXCLUDE.yaml", names)

                include_text = bundle.read(".aiteamos/git_activity/GIT-EXPORT-INCLUDE.yaml").decode("utf-8")
                self.assertIn("include-private-ref", include_text)
                self.assertIn("provider-include-secret", include_text)

                sanitize_text = bundle.read(".aiteamos/git_activity/GIT-EXPORT-SANITIZE.yaml").decode("utf-8")
                self.assertIn("redacted-ref:", sanitize_text)
                self.assertIn("redacted:external:", sanitize_text)
                self.assertIn("redacted:url:", sanitize_text)
                self.assertNotIn("customer-secret-ref", sanitize_text)
                self.assertNotIn("provider-sanitize-secret", sanitize_text)
                self.assertNotIn("private/pull/43", sanitize_text)

                manifest_text = bundle.read(".aiteamos/git_activity/GIT-EXPORT-MANIFEST.yaml").decode("utf-8")
                self.assertIn("member: backend-digital", manifest_text)
                self.assertIn("project: aiteamos", manifest_text)
                self.assertIn("exportPolicy: manifest-only", manifest_text)
                self.assertNotIn("provider-manifest-secret", manifest_text)
                self.assertNotIn("manifest-only-secret-ref", manifest_text)
                self.assertNotIn("private/pull/44", manifest_text)

                archived_text = bundle.read(".aiteamos/git_activity/GIT-EXPORT-ARCHIVED.yaml").decode("utf-8")
                self.assertIn("lifecycle: archived", archived_text)
                self.assertIn("redacted-ref:", archived_text)
                self.assertNotIn("archived-secret-ref", archived_text)
                self.assertNotIn("provider-archived-secret", archived_text)

                manifest = json.loads(bundle.read("AITEAMOS_EXPORT_MANIFEST.json").decode("utf-8"))
                self.assertIn(
                    {"path": ".aiteamos/git_activity/GIT-EXPORT-EXCLUDE.yaml", "reason": "git-activity-export-exclude"},
                    manifest["excludedFiles"],
                )

    def test_manifest_export_policy_contract_covers_every_manifest_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            output = Path(temp_dir) / "aiteamos-sanitized.zip"
            policies = ("include", "sanitize", "manifest-only", "exclude")

            for kind in sorted(KIND_TO_MODEL):
                for policy in policies:
                    _write_policy_fixture(workspace, kind, policy)

            export_workspace_bundle(workspace, output)

            with zipfile.ZipFile(output) as bundle:
                names = set(bundle.namelist())
                manifest = json.loads(bundle.read("AITEAMOS_EXPORT_MANIFEST.json").decode("utf-8"))
                excluded = {item["path"]: item["reason"] for item in manifest["excludedFiles"]}

                for kind in sorted(KIND_TO_MODEL):
                    with self.subTest(kind=kind, policy="include"):
                        include_path = _policy_fixture_archive_path(kind, "include")
                        self.assertIn(include_path, names)
                        include_text = bundle.read(include_path).decode("utf-8")
                        self.assertIn(f"DG85_PUBLIC_{kind}_include", include_text)
                        self.assertIn(f"DG85_PRIVATE_{kind}_include", include_text)
                        self.assertNotIn(f"DG85_TOKEN_{kind}_include", include_text)

                    with self.subTest(kind=kind, policy="sanitize"):
                        sanitize_path = _policy_fixture_archive_path(kind, "sanitize")
                        self.assertIn(sanitize_path, names)
                        sanitize_text = bundle.read(sanitize_path).decode("utf-8")
                        self.assertIn("exportRedactionReason: export-policy:sanitize;lifecyc", sanitize_text)
                        self.assertIn(f"DG85_PUBLIC_{kind}_sanitize", sanitize_text)
                        self.assertNotIn(f"DG85_PRIVATE_{kind}_sanitize", sanitize_text)
                        self.assertNotIn(f"DG85_TOKEN_{kind}_sanitize", sanitize_text)
                        self.assertNotIn(f"DG85_URL_{kind}_sanitize", sanitize_text)

                    with self.subTest(kind=kind, policy="manifest-only"):
                        manifest_only_path = _policy_fixture_archive_path(kind, "manifest-only")
                        self.assertIn(manifest_only_path, names)
                        manifest_only_text = bundle.read(manifest_only_path).decode("utf-8")
                        self.assertIn(f"kind: {kind}", manifest_only_text)
                        self.assertIn("exportPolicy: manifest-only", manifest_only_text)
                        self.assertIn("decisionAudit:", manifest_only_text)
                        self.assertNotIn(f"DG85_PUBLIC_{kind}_manifest-only", manifest_only_text)
                        self.assertNotIn(f"DG85_PRIVATE_{kind}_manifest-only", manifest_only_text)
                        self.assertNotIn(f"DG85_TOKEN_{kind}_manifest-only", manifest_only_text)
                        self.assertNotIn(f"DG85_URL_{kind}_manifest-only", manifest_only_text)

                    with self.subTest(kind=kind, policy="exclude"):
                        exclude_path = _policy_fixture_archive_path(kind, "exclude")
                        self.assertNotIn(exclude_path, names)
                        self.assertEqual(excluded.get(exclude_path), "manifest-export-exclude")

    def test_export_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            output = Path(temp_dir) / "aiteamos-sanitized.zip"

            export_workspace_bundle(workspace, output)

            with self.assertRaises(FileExistsError):
                export_workspace_bundle(workspace, output)

            export_workspace_bundle(workspace, output, overwrite=True)
            self.assertTrue(output.exists())

    def test_cli_workspace_export_writes_requested_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            output = Path(temp_dir) / "cli-export.zip"

            result = cli_main(["workspace", "export", "--workspace", str(workspace), "--output", str(output)])

            self.assertEqual(result, 0)
            with zipfile.ZipFile(output) as bundle:
                self.assertIn("AITEAMOS_EXPORT_MANIFEST.json", bundle.namelist())
                manifest = json.loads(bundle.read("AITEAMOS_EXPORT_MANIFEST.json").decode("utf-8"))
                self.assertEqual(manifest["kind"], "WorkspaceExport")
                self.assertTrue(manifest["sanitized"])


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(REPO_ROOT / ".aiteamos", workspace, ignore=shutil.ignore_patterns("__pycache__"))
    return workspace


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_policy_fixture(workspace: Path, kind: str, policy: str) -> None:
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": kind,
        "metadata": {"id": f"DG85-{kind}-{policy}", "title": f"DG85 {kind} {policy}"},
        "spec": {
            "project": "aiteamos",
            "member": "backend-digital",
            "task": "TASK-20260523T063321242",
            "lifecycle": "active",
            "exportPolicy": policy,
            "decisionAudit": [
                {
                    "source": "dg-85-export-policy-test",
                    "actorMember": "aiteamos-manager",
                    "decision": f"exercise-{policy}",
                    "decidedAt": "2026-05-23T06:33:21+08:00",
                    "reason": "Verify export bundle policy behavior without mutating source manifests.",
                }
            ],
            "publicDetail": f"DG85_PUBLIC_{kind}_{policy}",
            "privateNotes": f"DG85_PRIVATE_{kind}_{policy}",
            "rawPayload": {"token": f"DG85_TOKEN_{kind}_{policy}"},
            "url": f"https://example.invalid/DG85_URL_{kind}_{policy}",
        },
    }
    path = workspace / "export_policy_fixtures" / policy / f"{kind}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def _policy_fixture_archive_path(kind: str, policy: str) -> str:
    return f".aiteamos/export_policy_fixtures/{policy}/{kind}.yaml"


def _write_git_activity(
    workspace: Path,
    activity_id: str,
    *,
    lifecycle: str = "active",
    export_policy: str,
    summary: str,
    external_id: str,
    url: str,
    refs: list[str],
) -> None:
    _write(
        workspace / "git_activity" / f"{activity_id}.yaml",
        "\n".join(
            [
                "apiVersion: aiteamos.dev/v1alpha1",
                "kind: GitActivity",
                "metadata:",
                f"  id: {activity_id}",
                "spec:",
                "  member: backend-digital",
                "  project: aiteamos",
                "  repository: aiteamos",
                "  assignment: aiteamos-backend-runtime",
                "  activityType: pull-request",
                "  provider: github",
                f"  externalId: {external_id}",
                f"  url: {url}",
                "  occurredAt: \"2026-05-21T10:30:00+08:00\"",
                f"  summary: {summary}",
                "  refs:",
                *[f"    - {ref}" for ref in refs],
                "  evidence:",
                "    - runs/RUN-20260520T104310792/run.yaml",
                "  visibility: project",
                f"  lifecycle: {lifecycle}",
                f"  exportPolicy: {export_policy}",
                "",
            ]
        ),
    )


if __name__ == "__main__":
    unittest.main()
