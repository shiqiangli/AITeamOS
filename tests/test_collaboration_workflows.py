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
from aiteamos_workspace import create_run, create_task, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class CollaborationWorkflowTest(unittest.TestCase):
    def test_ask_for_help_review_request_and_resolution_are_projected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="Collaboration projection task",
                assigned_member="backend-digital",
                assignment="aiteamos-backend-runtime",
                acceptance=["collaboration records are visible by member and project"],
            )
            run = create_run(workspace, task_id=task.object_id, member="backend-digital", assignment="aiteamos-backend-runtime")
            client = TestClient(create_app(workspace))

            ask = client.post(
                "/member-messages/ask-for-help",
                json={
                    "fromMember": "backend-digital",
                    "toMembers": ["frontend-human"],
                    "question": "Need UI review before handoff.",
                    "task": task.object_id,
                    "runId": run.object_id,
                    "priority": "high",
                },
            )
            self.assertEqual(ask.status_code, 200)
            self.assertEqual(ask.json()["spec"]["messageType"], "ask-for-help")
            self.assertEqual(ask.json()["spec"]["status"], "open")
            self.assertEqual(ask.json()["spec"]["priority"], "high")

            review = client.post(
                "/member-messages/review-request",
                json={
                    "fromMember": "backend-digital",
                    "toMember": "architect",
                    "body": "Please review this collaboration API shape.",
                    "reviewKind": "architecture",
                    "task": task.object_id,
                    "runId": run.object_id,
                },
            )
            self.assertEqual(review.status_code, 200)
            self.assertEqual(review.json()["spec"]["messageType"], "review-request")
            self.assertEqual(review.json()["spec"]["audit"]["reviewKind"], "architecture")

            overview = client.get("/collaboration/overview", params={"member": "frontend-human"})
            self.assertEqual(overview.status_code, 200)
            self.assertEqual(overview.json()["summary"]["askForHelp"], 1)
            self.assertEqual(overview.json()["summary"]["openMessages"], 1)

            suggestions = client.get("/retrospectives/suggestions", params={"task": task.object_id})
            self.assertEqual(suggestions.status_code, 200)
            self.assertEqual(suggestions.json()["summary"]["candidateCount"], 1)
            candidate = suggestions.json()["candidates"][0]
            self.assertEqual(candidate["sourceRuns"], [run.object_id])
            self.assertEqual(candidate["sourceMessages"], [ask.json()["id"], review.json()["id"]])
            self.assertEqual(candidate["proposedRetrospective"]["sourceTasks"], [task.object_id])
            self.assertIn("frontend-human", candidate["participants"])
            self.assertFalse(load_workspace(workspace).team_retrospectives)

            retrospective = client.post(
                "/retrospectives",
                json={
                    "facilitatorMember": "architect",
                    "participants": ["backend-digital", "frontend-human"],
                    "sourceRuns": [run.object_id],
                    "sourceMessages": [ask.json()["id"], review.json()["id"]],
                    "summary": "Cross-member UI handoff needs earlier reviewer involvement.",
                    "lessons": ["Ask for review before context gets stale."],
                    "actionItems": ["Add review request to the handoff checklist."],
                },
            )
            self.assertEqual(retrospective.status_code, 200)
            self.assertEqual(retrospective.json()["retrospective"]["kind"], "TeamRetrospective")
            self.assertEqual(retrospective.json()["proposal"]["spec"]["status"], "pending-review")
            self.assertIn("team-retrospective:", retrospective.json()["proposal"]["spec"]["dedupeKey"])

            overview = client.get("/collaboration/overview", params={"member": "frontend-human"})
            self.assertEqual(overview.status_code, 200)
            self.assertEqual(overview.json()["summary"]["retrospectives"], 1)
            self.assertEqual(overview.json()["summary"]["proposedRetrospectives"], 1)

            task_overview = client.get("/collaboration/overview", params={"task": task.object_id})
            self.assertEqual(task_overview.status_code, 200)
            self.assertEqual(task_overview.json()["summary"]["retrospectives"], 1)

            resolved = client.post(
                f"/member-messages/{ask.json()['id']}/resolve",
                json={"actorMember": "frontend-human", "resolution": "Reviewed and replied."},
            )
            self.assertEqual(resolved.status_code, 200)
            self.assertEqual(resolved.json()["spec"]["status"], "resolved")

            index = load_workspace(workspace)
            self.assertEqual(index.member_messages[ask.json()["id"]].spec.resolvedByMember, "frontend-human")
            self.assertEqual(index.run_events[run.object_id][-1]["type"], "member.message.resolved")

    def test_mcp_request_review_is_permission_checked_and_audited(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="MCP review request task",
                assigned_member="backend-digital",
                assignment="aiteamos-backend-runtime",
                acceptance=["MCP review request creates an audited message"],
            )
            run = create_run(workspace, task_id=task.object_id, member="backend-digital", assignment="aiteamos-backend-runtime")
            client = TestClient(create_app(workspace))

            response = client.post(
                "/mcp/tools/request_review",
                json={
                    "fromMember": "backend-digital",
                    "toMember": "architect",
                    "body": "Please review the MCP-visible workflow.",
                    "reviewKind": "code",
                    "runId": run.object_id,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["permissionDecision"]["decision"], "allow")
            self.assertEqual(response.json()["message"]["spec"]["messageType"], "review-request")

            index = load_workspace(workspace)
            self.assertTrue(any(message.spec.messageType == "review-request" for message in index.member_messages.values()))

    def test_mcp_create_retrospective_is_permission_checked_and_creates_pending_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="MCP retrospective task",
                assigned_member="backend-digital",
                assignment="aiteamos-backend-runtime",
                acceptance=["MCP retrospective creates a pending memory proposal"],
            )
            run = create_run(workspace, task_id=task.object_id, member="backend-digital", assignment="aiteamos-backend-runtime")
            client = TestClient(create_app(workspace))

            response = client.post(
                "/mcp/tools/create_retrospective",
                json={
                    "facilitatorMember": "manager",
                    "participants": ["backend-digital"],
                    "sourceRuns": [run.object_id],
                    "summary": "MCP retrospective captured a team learning.",
                    "lessons": ["Use retrospectives for team-level learning before memory approval."],
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["permissionDecision"]["decision"], "allow")
            self.assertEqual(response.json()["tool"], "create_retrospective")
            self.assertEqual(response.json()["retrospective"]["kind"], "TeamRetrospective")
            self.assertEqual(response.json()["proposal"]["spec"]["status"], "pending-review")

            index = load_workspace(workspace)
            self.assertTrue(index.team_retrospectives)
            self.assertTrue(any(proposal.spec.sourceExtractorId == "team-retrospective" for proposal in index.memory_proposals.values()))

    def test_mcp_suggest_retrospectives_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            task = create_task(
                workspace,
                title="MCP retrospective suggestion task",
                assigned_member="backend-digital",
                assignment="aiteamos-backend-runtime",
                acceptance=["MCP retrospective suggestions are read-only"],
            )
            run = create_run(workspace, task_id=task.object_id, member="backend-digital", assignment="aiteamos-backend-runtime")
            client = TestClient(create_app(workspace))

            response = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "suggest_retrospectives", "arguments": {"task": task.object_id}},
                },
            )
            self.assertEqual(response.status_code, 200)
            content = response.json()["result"]["structuredContent"]
            self.assertEqual(content["summary"]["candidateCount"], 1)
            self.assertEqual(content["candidates"][0]["sourceRuns"], [run.object_id])

            index = load_workspace(workspace)
            self.assertFalse(index.team_retrospectives)
            self.assertFalse(any(proposal.spec.sourceExtractorId == "team-retrospective" for proposal in index.memory_proposals.values()))


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
