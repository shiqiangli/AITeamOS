from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import create_run, create_task, load_workspace
from aiteamos_workspace.tool_mutations import (
    create_patch_for_tool,
    propose_memory_for_tool,
    record_event_for_tool,
    record_handoff_for_tool,
    record_journal_for_tool,
    record_member_message_for_tool,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class MutatingToolTest(unittest.TestCase):
    def test_record_journal_appends_redacted_entry_and_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            result = record_journal_for_tool(workspace, run.object_id, "backend-digital", "EXAMPLE_TOKEN=placeholder-value\nDone.")

            self.assertEqual(result["tool"], "record_journal")
            index = load_workspace(workspace)
            journal = index.run_journals[run.object_id]
            self.assertIn("EXAMPLE_TOKEN=[REDACTED]", journal)
            self.assertNotIn("placeholder-value", journal)
            self.assertEqual(index.run_events[run.object_id][-1]["type"], "journal.recorded")
            self.assertEqual(index.run_events[run.object_id][-1]["actorMember"], "backend-digital")

    def test_record_event_generates_seq_ts_and_rejects_governance_events(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            result = record_event_for_tool(workspace, run.object_id, "backend-digital", {"type": "tool.observed", "note": "ok"})

            self.assertEqual(result["event"]["type"], "tool.observed")
            self.assertIn("seq", result["event"])
            self.assertIn("ts", result["event"])
            self.assertEqual(result["event"]["actorMember"], "backend-digital")
            with self.assertRaises(ValueError):
                record_event_for_tool(workspace, run.object_id, "backend-digital", {"type": "tool.observed", "seq": 99})
            with self.assertRaises(ValueError):
                record_event_for_tool(workspace, run.object_id, "backend-digital", {"type": "memory.approved"})
            with self.assertRaises(ValueError):
                record_event_for_tool(workspace, run.object_id, "backend-digital", {"type": "run.closed"})

    def test_propose_memory_tool_creates_pending_proposal_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            result = propose_memory_for_tool(
                workspace,
                run.object_id,
                "backend-digital",
                title="Tool memory",
                content="Keep mutating MCP tools pending-review only.",
                kind="decision",
                confidence=0.8,
            )

            proposal_id = result["proposal"]["id"]
            index = load_workspace(workspace)
            self.assertEqual(index.memory_proposals[proposal_id].spec.status, "pending-review")
            self.assertEqual(index.memory_proposals[proposal_id].spec.member, "backend-digital")
            self.assertEqual(index.memory_proposals[proposal_id].spec.assignment, "aiteamos-backend-runtime")
            self.assertEqual(index.memory_proposals[proposal_id].spec.sourceTask, run.spec.task)
            self.assertIsNone(index.memory_proposals[proposal_id].spec.approvedMemory)
            self.assertTrue([event for event in index.run_events[run.object_id] if event["type"] == "memory.proposed"])

    def test_handoff_records_event_and_optional_task_transfer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            result = record_handoff_for_tool(
                workspace,
                run.spec.task,
                "backend-digital",
                "frontend-human",
                "Frontend should review dashboard behavior.",
                run_id=run.object_id,
                ownership="transfer",
            )

            self.assertTrue(result["ownershipTransferred"])
            index = load_workspace(workspace)
            self.assertEqual(index.tasks[run.spec.task].spec.assignedMember, "frontend-human")
            self.assertEqual(index.tasks[run.spec.task].spec.assignment, "aiteamos-dashboard")
            handoff = next(iter(index.handoffs.values()))
            self.assertEqual(handoff.spec.fromMember, "backend-digital")
            self.assertEqual(handoff.spec.toMember, "frontend-human")
            self.assertEqual(index.run_events[run.object_id][-1]["type"], "handoff.recorded")
            self.assertEqual(index.run_events[run.object_id][-1]["fromMember"], "backend-digital")
            self.assertEqual(index.run_events[run.object_id][-1]["toMember"], "frontend-human")
            self.assertEqual(index.runs[run.object_id].spec.status, "READY")

    def test_member_message_is_audited_without_memory_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            result = record_member_message_for_tool(
                workspace,
                "backend-digital",
                "Need a UI pass before review.",
                to_members=["frontend-human"],
                message_type="ask-for-help",
                project="aiteamos",
                task=run.spec.task,
                run_id=run.object_id,
            )

            self.assertEqual(result["tool"], "record_member_message")
            index = load_workspace(workspace)
            message = index.member_messages[result["message"]["id"]]
            self.assertEqual(message.spec.fromMember, "backend-digital")
            self.assertEqual(message.spec.toMembers, ["frontend-human"])
            self.assertEqual(message.spec.messageType, "ask-for-help")
            self.assertEqual(index.run_events[run.object_id][-1]["type"], "member.message.recorded")

    def test_create_patch_records_diff_review_target_and_rejects_unsafe_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)

            result = create_patch_for_tool(workspace, run.object_id, "backend-digital", diff_patch=_valid_diff())

            self.assertEqual(result["tool"], "create_patch")
            self.assertTrue(result["reviewGate"]["readyForHumanReview"])
            index = load_workspace(workspace)
            updated = index.runs[run.object_id]
            self.assertEqual(updated.spec.status, "REVIEW")
            self.assertEqual(updated.spec.reviewTarget.type, "diff_patch")
            self.assertTrue((workspace / "runs" / run.object_id / "diff.patch").exists())
            with self.assertRaises(ValueError):
                create_patch_for_tool(workspace, run.object_id, "backend-digital", diff_patch=_aiteamos_diff())

    def test_mutating_tool_api_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            client = TestClient(create_app(workspace))

            journal = client.post(
                "/mcp/tools/record_journal",
                json={"runId": run.object_id, "actorMember": "backend-digital", "entry": "API journal"},
            )
            self.assertEqual(journal.status_code, 200)
            self.assertEqual(journal.json()["permissionDecision"]["decision"], "allow")

            event = client.post(
                "/mcp/tools/record_event",
                json={"runId": run.object_id, "actorMember": "backend-digital", "event": {"type": "tool.observed", "note": "api"}},
            )
            self.assertEqual(event.status_code, 200)

            memory = client.post(
                "/mcp/tools/propose_memory",
                json={"runId": run.object_id, "actorMember": "backend-digital", "title": "API memory", "content": "Pending only."},
            )
            self.assertEqual(memory.status_code, 200)
            self.assertEqual(memory.json()["proposal"]["spec"]["status"], "pending-review")

            handoff = client.post(
                "/mcp/tools/handoff",
                json={
                    "taskId": run.spec.task,
                    "fromMember": "backend-digital",
                    "toMember": "frontend-human",
                    "problem": "API handoff",
                    "runId": run.object_id,
                },
            )
            self.assertEqual(handoff.status_code, 200)

            message = client.post(
                "/mcp/tools/record_member_message",
                json={
                    "fromMember": "backend-digital",
                    "toMembers": ["frontend-human"],
                    "messageType": "knowledge-share",
                    "body": "API message",
                    "runId": run.object_id,
                },
            )
            self.assertEqual(message.status_code, 200)

            patch = client.post(
                "/mcp/tools/create_patch",
                json={"runId": run.object_id, "actorMember": "backend-digital", "diffPatch": _valid_diff()},
            )
            self.assertEqual(patch.status_code, 200)
            self.assertEqual(patch.json()["reviewGate"]["status"], "READY_FOR_HUMAN_REVIEW")

            rejected = client.post(
                "/mcp/tools/record_event",
                json={"runId": run.object_id, "actorMember": "backend-digital", "event": {"type": "merge.completed"}},
            )
            self.assertEqual(rejected.status_code, 400)

    def test_mutating_tool_api_enforces_effective_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Human MCP gate task",
                assigned_member="frontend-human",
                assignment="aiteamos-dashboard",
                acceptance=["human MCP writes require explicit allow or interactive approval"],
            )
            run = create_run(workspace, task_id=task.object_id, member="frontend-human", assignment="aiteamos-dashboard")
            client = TestClient(create_app(workspace))

            denied = client.post(
                "/mcp/tools/record_journal",
                json={"runId": run.object_id, "actorMember": "frontend-human", "entry": "human journal"},
            )

            self.assertEqual(denied.status_code, 403)
            permission = denied.json()["detail"]["permission"]
            self.assertEqual(permission["decision"], "deny")
            self.assertEqual(permission["memberKind"], "human")
            self.assertIn("non-interactive", permission["reason"])


def _create_backend_run(workspace: Path) -> object:
    task = create_task(
        workspace,
        title="Mutating tool task",
        assigned_member="backend-digital",
        assignment="aiteamos-backend-runtime",
        acceptance=["tool writes are gated"],
    )
    return create_run(workspace, task_id=task.object_id, member="backend-digital", assignment="aiteamos-backend-runtime")


def _valid_diff() -> str:
    return "\n".join(
        [
            "diff --git a/packages/workspace/tool_mutation.txt b/packages/workspace/tool_mutation.txt",
            "new file mode 100644",
            "index 0000000..1111111",
            "--- /dev/null",
            "+++ b/packages/workspace/tool_mutation.txt",
            "@@ -0,0 +1 @@",
            "+tool mutation coverage",
            "",
        ]
    )


def _aiteamos_diff() -> str:
    return "\n".join(
        [
            "diff --git a/.aiteamos/tasks/unsafe.yaml b/.aiteamos/tasks/unsafe.yaml",
            "--- a/.aiteamos/tasks/unsafe.yaml",
            "+++ b/.aiteamos/tasks/unsafe.yaml",
            "@@ -1 +1 @@",
            "-old",
            "+new",
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
