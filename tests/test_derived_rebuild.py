from __future__ import annotations

from pathlib import Path
import json
import shutil
import sqlite3
import tempfile
import unittest

from aiteamos_workspace import rebuild_database_index, rebuild_vector_index, rebuild_workspace_indexes
from tools.cli.aiteamos import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[1]


class DerivedRebuildTest(unittest.TestCase):
    def test_db_rebuild_uses_workspace_files_as_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            db_path = Path(temp_dir) / "derived.sqlite"
            _write_budget_policy(workspace)

            result = rebuild_database_index(workspace, db_path=db_path)

            self.assertTrue(result["derived"])
            self.assertEqual(result["databasePath"], str(db_path.resolve()))
            self.assertTrue(db_path.exists())

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    """
                    select project_id, member_id, assignment_id, limits_json
                    from budget_policies
                    where id = 'default-budget'
                    """
                ).fetchone()
                self.assertEqual(row[0:3], ("aiteamos", "architect", "aiteamos-architecture"))
                self.assertEqual(json.loads(row[3])["maxUsdPerRun"], 10.0)
            finally:
                conn.close()

            cli_db = Path(temp_dir) / "cli-derived.sqlite"
            self.assertEqual(
                cli_main(["db", "rebuild", "--from", str(workspace), "--output", str(cli_db)]),
                0,
            )
            self.assertTrue(cli_db.exists())
            workspace_index_db = Path(temp_dir) / "workspace-index.sqlite"
            self.assertEqual(
                cli_main(["workspace", "index", "--workspace", str(workspace), "--output", str(workspace_index_db)]),
                0,
            )
            self.assertTrue(workspace_index_db.exists())
            self.assertTrue((workspace / "indexes" / "vector_sources.json").exists())

            workspace_index = rebuild_workspace_indexes(workspace)
            self.assertTrue(workspace_index["derived"])
            self.assertEqual(workspace_index["database"]["source"], str(workspace.resolve()))
            self.assertEqual(workspace_index["vector"]["source"], str(workspace.resolve()))
            self.assertEqual(workspace_index["dashboardCache"]["status"], "not_configured")

    def test_vector_rebuild_writes_source_manifest_without_content_or_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_approved_memory(workspace)

            result = rebuild_vector_index(workspace)
            output = workspace / "indexes" / "vector_sources.json"
            chunk_output = workspace / "indexes" / "vector_chunks.json"

            self.assertTrue(result["derived"])
            self.assertFalse(result["contentStored"])
            self.assertFalse(result["embeddingsGenerated"])
            self.assertEqual(result["chunkManifestPath"], str(chunk_output))
            self.assertGreater(result["chunkCount"], 0)
            self.assertTrue(output.exists())
            self.assertTrue(chunk_output.exists())

            manifest_text = output.read_text(encoding="utf-8")
            self.assertNotIn("placeholder-value", manifest_text)
            manifest = json.loads(manifest_text)
            refs = {entry["sourceRef"] for entry in manifest["entries"]}
            self.assertIn("memory/entries/MEM-1.yaml", refs)
            self.assertTrue(any(ref.startswith("tasks/") and ref.endswith(".md") for ref in refs))
            self.assertTrue(all(entry["contentStored"] is False for entry in manifest["entries"]))
            self.assertTrue(all(entry["embeddingStatus"] == "pending-provider" for entry in manifest["entries"]))
            self.assertEqual(manifest["chunkManifest"], str(chunk_output))
            self.assertEqual(manifest["chunkCount"], result["chunkCount"])

            chunk_text = chunk_output.read_text(encoding="utf-8")
            self.assertNotIn("placeholder-value", chunk_text)
            chunk_manifest = json.loads(chunk_text)
            self.assertEqual(chunk_manifest["kind"], "DerivedVectorChunkManifest")
            self.assertEqual(chunk_manifest["chunking"]["strategy"], "deterministic-char-window")
            self.assertFalse(chunk_manifest["contentStored"])
            self.assertFalse(chunk_manifest["embeddingsGenerated"])
            self.assertEqual(chunk_manifest["embeddingModel"], None)
            self.assertGreater(len(chunk_manifest["chunks"]), 0)
            chunk_refs = {chunk["sourceRef"] for chunk in chunk_manifest["chunks"]}
            self.assertTrue(chunk_refs.issubset(refs))
            for chunk in chunk_manifest["chunks"]:
                self.assertNotIn("content", chunk)
                self.assertNotIn("text", chunk)
                self.assertFalse(chunk["contentStored"])
                self.assertEqual(chunk["embeddingStatus"], "pending-provider")
                self.assertGreaterEqual(chunk["charStart"], 0)
                self.assertGreater(chunk["charEnd"], chunk["charStart"])
                self.assertGreater(chunk["byteLength"], 0)
                self.assertGreaterEqual(chunk["tokenEstimate"], 1)
                self.assertRegex(chunk["sha256"], r"^[0-9a-f]{64}$")

            cli_output = Path(temp_dir) / "vector-sources.json"
            self.assertEqual(
                cli_main(["vector", "rebuild", "--from", str(workspace), "--output", str(cli_output)]),
                0,
            )
            self.assertTrue(cli_output.exists())
            self.assertTrue((Path(temp_dir) / "vector_chunks.json").exists())


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _write_budget_policy(workspace: Path) -> None:
    _write(
        workspace / "budget_policies" / "default-budget.yaml",
        "\n".join(
            [
                "apiVersion: aiteamos.dev/v1alpha1",
                "kind: BudgetPolicy",
                "metadata:",
                "  name: default-budget",
                "spec:",
                "  scope:",
                "    project: aiteamos",
                "    member: architect",
                "    assignment: aiteamos-architecture",
                "  limits:",
                "    maxUsdPerRun: 10.0",
                "    maxOutputTokensPerRun: 40000",
                "  rateLimit:",
                "    requestsPerMinute: 20",
                "  fallback:",
                "    allowModelFallback: true",
                "    maxFallbacksPerRun: 1",
                "  enforcement:",
                "    onSoftLimit: warn",
                "    onHardLimit: stop-run",
                "",
            ]
        ),
    )


def _write_approved_memory(workspace: Path) -> None:
    _write(
        workspace / "memory" / "entries" / "MEM-1.yaml",
        "\n".join(
            [
                "apiVersion: aiteamos.dev/v1alpha1",
                "kind: MemoryEntry",
                "metadata:",
                "  id: MEM-1",
                "spec:",
                "  store: aiteamos-project-memory",
                "  path: decisions/MEM-1.md",
                "  scope: project",
                "  source: test",
                "  kind: decision",
                "  title: Keep vector rebuild provider-free",
                "  content: EXAMPLE_TOKEN=placeholder-value should never be copied into derived vector metadata.",
                "  evidence:",
                "    - docs/architecture.md",
                "  confidence: 0.9",
                "  freshness: current",
                "  sensitivity: internal",
                "  visibility: project",
                "  lifecycle: active",
                "  relatedProjects:",
                "    - aiteamos",
                "  relatedMembers:",
                "    - architect",
                "  relatedAssignments:",
                "    - aiteamos-architecture",
                "  version: 1",
                "  embedding: {}",
                "",
            ]
        ),
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
