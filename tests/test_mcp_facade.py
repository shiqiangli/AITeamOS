from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_api.routes import MCP_TOOL_MODELS
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_workspace import create_run, create_task, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class McpFacadeTest(unittest.TestCase):
    def test_json_rpc_lists_tools_and_calls_read_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
            self.assertEqual(listed.status_code, 200)
            tool_names = {tool["name"] for tool in listed.json()["result"]["tools"]}
            self.assertIn("search_docs", tool_names)
            self.assertIn("get_member", tool_names)
            self.assertIn("grant_memory", tool_names)
            self.assertIn("create_patch", tool_names)
            tools = {tool["name"]: tool for tool in listed.json()["result"]["tools"]}
            self.assertEqual(tools["record_journal"]["inputSchema"], MCP_TOOL_MODELS["record_journal"].model_json_schema())
            self.assertEqual(tools["search_docs"]["inputSchema"]["properties"]["limit"]["maximum"], 50)
            self.assertEqual(tools["propose_memory"]["inputSchema"]["properties"]["confidence"]["anyOf"][0]["maximum"], 1)

            called = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "read-call",
                    "method": "tools/call",
                    "params": {
                        "name": "search_docs",
                        "arguments": {"query": "versioned workspace", "member": "architect", "assignment": "aiteamos-architecture"},
                    },
                },
            )
            self.assertEqual(called.status_code, 200)
            result = called.json()["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(result["structuredContent"]["tool"], "search_docs")
            self.assertTrue(result["structuredContent"]["matches"])

            member = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "member-call",
                    "method": "tools/call",
                    "params": {"name": "get_member", "arguments": {"memberId": "architect"}},
                },
            )
            self.assertEqual(member.status_code, 200)
            self.assertEqual(member.json()["result"]["structuredContent"]["member"]["id"], "architect")

            invalid = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "invalid-call",
                    "method": "tools/call",
                    "params": {"name": "search_docs", "arguments": {"query": "versioned workspace", "limit": 100}},
                },
            )
            self.assertEqual(invalid.status_code, 200)
            self.assertEqual(invalid.json()["error"]["code"], -32602)
            self.assertIn("less_than_equal", invalid.json()["error"]["message"])

    def test_json_rpc_read_token_cannot_call_mutating_tool(self) -> None:
        env = {**AUTH_ENV_OFF, MCP_READ_TOKEN_ENV: MCP_READ_TOKEN_ENV}
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            client = TestClient(create_app(workspace))

            rejected = client.post(
                "/mcp",
                headers=_auth_header(MCP_READ_TOKEN_ENV),
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "record_journal",
                        "arguments": {"run_id": run.object_id, "actor_member": "backend-digital", "entry": "read token write"},
                    },
                },
            )

            self.assertEqual(rejected.status_code, 403)
            self.assertEqual(rejected.json()["scope"], "mcp-write")
            self.assertEqual(rejected.json()["acceptedTokenEnvNames"], [MCP_WRITE_TOKEN_ENV, API_TOKEN_ENV])

    def test_json_rpc_write_token_calls_mutating_tool_through_existing_gate(self) -> None:
        env = {**AUTH_ENV_OFF, MCP_WRITE_TOKEN_ENV: MCP_WRITE_TOKEN_ENV}
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            client = TestClient(create_app(workspace))

            response = client.post(
                "/mcp",
                headers=_auth_header(MCP_WRITE_TOKEN_ENV),
                json={
                    "jsonrpc": "2.0",
                    "id": "write-call",
                    "method": "tools/call",
                    "params": {
                        "name": "record_journal",
                        "arguments": {"runId": run.object_id, "actorMember": "backend-digital", "entry": "JSON-RPC journal"},
                    },
                },
            )

            self.assertEqual(response.status_code, 200)
            result = response.json()["result"]["structuredContent"]
            self.assertEqual(result["tool"], "record_journal")
            self.assertEqual(result["permissionDecision"]["decision"], "allow")
            index = load_workspace(workspace)
            self.assertIn("JSON-RPC journal", index.run_journals[run.object_id])
            self.assertEqual(index.run_events[run.object_id][-1]["type"], "journal.recorded")

    def test_json_rpc_write_token_can_grant_share_and_ask_without_memory_binding(self) -> None:
        env = {**AUTH_ENV_OFF, MCP_WRITE_TOKEN_ENV: MCP_WRITE_TOKEN_ENV}
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, env):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            client = TestClient(create_app(workspace))

            grant = client.post(
                "/mcp",
                headers=_auth_header(MCP_WRITE_TOKEN_ENV),
                json={
                    "jsonrpc": "2.0",
                    "id": "grant-call",
                    "method": "tools/call",
                    "params": {
                        "name": "grant_memory",
                        "arguments": {
                            "member": "backend-digital",
                            "grantorMember": "architect",
                            "runId": run.object_id,
                            "entries": ["team-member-baseline"],
                            "reason": "Grant through MCP facade.",
                        },
                    },
                },
            )
            self.assertEqual(grant.status_code, 200)
            self.assertEqual(grant.json()["result"]["structuredContent"]["tool"], "grant_memory")

            share = client.post(
                "/mcp",
                headers=_auth_header(MCP_WRITE_TOKEN_ENV),
                json={
                    "jsonrpc": "2.0",
                    "id": "share-call",
                    "method": "tools/call",
                    "params": {
                        "name": "share_memory",
                        "arguments": {
                            "fromMember": "architect",
                            "toMember": "backend-digital",
                            "runId": run.object_id,
                            "entries": ["team-member-baseline"],
                            "reason": "Share through MCP facade.",
                        },
                    },
                },
            )
            self.assertEqual(share.status_code, 200)
            self.assertEqual(share.json()["result"]["structuredContent"]["message"]["spec"]["messageType"], "knowledge-share")

            ask = client.post(
                "/mcp",
                headers=_auth_header(MCP_WRITE_TOKEN_ENV),
                json={
                    "jsonrpc": "2.0",
                    "id": "ask-call",
                    "method": "tools/call",
                    "params": {
                        "name": "ask_member",
                        "arguments": {
                            "fromMember": "backend-digital",
                            "toMember": "architect",
                            "question": "Can you review this API shape?",
                            "runId": run.object_id,
                        },
                    },
                },
            )
            self.assertEqual(ask.status_code, 200)
            index = load_workspace(workspace)
            self.assertGreaterEqual(len(index.memory_grants), 3)
            self.assertTrue(any(message.spec.messageType == "ask-for-help" for message in index.member_messages.values()))


def _auth_header(env_name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {env_name}"}


def _create_backend_run(workspace: Path) -> object:
    task = create_task(
        workspace,
        title="MCP facade task",
        assigned_member="backend-digital",
        assignment="aiteamos-backend-runtime",
        acceptance=["MCP facade is scoped"],
    )
    return create_run(workspace, task_id=task.object_id, member="backend-digital", assignment="aiteamos-backend-runtime")


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
