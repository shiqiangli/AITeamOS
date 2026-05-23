from __future__ import annotations

from pathlib import Path
import json
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import create_task, load_workspace, rebuild_workspace_indexes
from aiteamos_workspace.queries import (
    get_context_capsule_for_tool,
    get_task_for_tool,
    search_docs_for_tool,
    search_memory_for_tool,
)
from aiteamos_workspace.knowledge_health import evaluate_knowledge_health
from aiteamos_workspace.vector_index import build_vector_index_records


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReadOnlyToolQueryTest(unittest.TestCase):
    def test_get_task_returns_manifest_markdown_and_links_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Read-only tool task",
                assigned_member="architect",
                assignment="aiteamos-architecture",
                markdown="EXAMPLE_TOKEN=placeholder-value\nTask body\n",
            )

            result = get_task_for_tool(workspace, task.object_id)

            self.assertEqual(result["tool"], "get_task")
            self.assertEqual(result["task"]["id"], task.object_id)
            self.assertIn("EXAMPLE_TOKEN=[REDACTED]", result["task"]["markdown"])
            self.assertNotIn("placeholder-value", result["task"]["markdown"])
            self.assertIn("runs", result["task"])
            self.assertIn("reviews", result["task"])

    def test_get_context_capsule_returns_existing_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            result = get_context_capsule_for_tool(workspace, "RUN-0001")

            self.assertEqual(result["tool"], "get_context_capsule")
            self.assertEqual(result["run"], "RUN-0001")
            self.assertEqual(result["member"], "architect")
            self.assertEqual(result["assignment"], "aiteamos-architecture")
            self.assertEqual(result["path"], "runs/RUN-0001/prompt_capsule.md")
            self.assertIn("AITEAMOS", result["content"])
            self.assertIn("contextManifest", result)

    def test_search_memory_reads_approved_and_pending_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            result = search_memory_for_tool(workspace, "shadow workspace", project="aiteamos", member="architect", assignment="aiteamos-architecture")

            self.assertEqual(result["tool"], "search_memory")
            self.assertEqual(result["member"], "architect")
            self.assertEqual(result["assignment"], "aiteamos-architecture")
            self.assertTrue(result["matches"])
            self.assertTrue(any(match["source"] == "memory-proposal" for match in result["matches"]))

    def test_search_docs_reads_project_docs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            result = search_docs_for_tool(workspace, "versioned workspace", project="aiteamos", member="architect", assignment="aiteamos-architecture")

            self.assertEqual(result["tool"], "search_docs")
            self.assertEqual(result["member"], "architect")
            self.assertEqual(result["assignment"], "aiteamos-architecture")
            self.assertTrue(result["matches"])
            self.assertTrue(any(match["path"] == "docs/architecture.md" for match in result["matches"]))

    def test_vector_and_knowledge_health_are_member_memory_fabric_projected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            entries, chunks = build_vector_index_records(index)
            health = evaluate_knowledge_health(index)
            rebuild_workspace_indexes(workspace)
            derived_sources = json.loads((workspace / "indexes" / "vector_sources.json").read_text(encoding="utf-8"))

            memory_entries = [entry for entry in entries if entry["kind"] == "memory_entry"]
            derived_memory_entries = [entry for entry in derived_sources["entries"] if entry["kind"] == "memory_entry"]
            self.assertTrue(memory_entries)
            self.assertTrue(derived_memory_entries)
            self.assertTrue(all("role" not in entry for entry in entries))
            self.assertTrue(all("role" not in chunk for chunk in chunks))
            self.assertTrue(all("role" not in entry for entry in derived_sources["entries"]))
            self.assertTrue(any(entry["member"] == "architect" and entry["assignment"] == "aiteamos-architecture" for entry in memory_entries))
            self.assertTrue(any(entry["member"] == "architect" and entry["assignment"] == "aiteamos-architecture" for entry in derived_memory_entries))
            self.assertEqual(health["summary"]["memoryEntries"], len(index.memory_entries))


class ReadOnlyToolApiTest(unittest.TestCase):
    def test_read_only_tool_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)
            task_id = sorted(index.tasks)[0]
            client = TestClient(create_app(workspace))

            task = client.get(f"/mcp/tools/get_task/{task_id}")
            self.assertEqual(task.status_code, 200)
            self.assertEqual(task.json()["tool"], "get_task")

            capsule = client.get("/mcp/tools/get_context_capsule/RUN-0001")
            self.assertEqual(capsule.status_code, 200)
            self.assertEqual(capsule.json()["run"], "RUN-0001")

            memory = client.get(
                "/mcp/tools/search_memory",
                params={"query": "shadow workspace", "member": "architect", "assignment": "aiteamos-architecture"},
            )
            self.assertEqual(memory.status_code, 200)
            self.assertTrue(memory.json()["matches"])

            docs = client.get(
                "/mcp/tools/search_docs",
                params={"query": "versioned workspace", "member": "architect", "assignment": "aiteamos-architecture"},
            )
            self.assertEqual(docs.status_code, 200)
            self.assertTrue(docs.json()["matches"])

            member_memory = client.get("/members/architect/memory", params={"query": "TeamMember"})
            self.assertEqual(member_memory.status_code, 200)
            self.assertTrue(member_memory.json()["matches"])

            project_memory = client.get("/projects/aiteamos/memory", params={"member": "architect"})
            self.assertEqual(project_memory.status_code, 200)
            self.assertTrue(project_memory.json()["matches"])

            missing = client.get("/mcp/tools/get_task/DOES-NOT-EXIST")
            self.assertEqual(missing.status_code, 404)


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
