from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import (
    artifact_store_action,
    connector_action,
    env_var_action,
    explain_effective_permissions,
    load_workspace,
    mcp_action,
    network_action,
    web_action,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"


class PermissionEngineTest(unittest.TestCase):
    def test_effective_permission_engine_orders_deny_ask_allow_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            docs = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action={"tool": "Read", "path": "/docs/architecture.md"},
            )
            self.assertEqual(docs["decisionOrder"], ["deny", "ask", "allow"])
            self.assertEqual(docs["decision"], "allow")
            self.assertEqual(docs["matchedRules"][0]["rule"], "Read(/docs/**)")
            self.assertEqual(docs["riskAssessment"]["riskLevel"], "low")
            self.assertEqual(docs["riskAssessment"]["recommendedDecision"], "allow")

            service_edit = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action={"tool": "Edit", "path": "/services/api/aiteamos_api/auth.py"},
            )
            self.assertEqual(service_edit["decision"], "ask")
            self.assertEqual(service_edit["matchedRules"][0]["rule"], "Edit(/services/**)")

            headless_service_edit = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action={"tool": "Edit", "path": "/services/api/aiteamos_api/auth.py"},
                non_interactive=True,
            )
            self.assertEqual(headless_service_edit["decision"], "deny")
            self.assertIn("non-interactive", headless_service_edit["reason"])

            git_edit = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action={"tool": "Edit", "path": "/.git/config"},
            )
            self.assertEqual(git_edit["decision"], "deny")
            self.assertEqual(git_edit["matchedRules"][0]["rule"], "Edit(/.git/**)")

    def test_effective_permission_engine_normalizes_external_action_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            web = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=web_action("https://docs.qoder.com/en/cli/permissions"),
            )
            self.assertEqual(web["normalizedAction"]["canonical"], "WebFetch(docs.qoder.com)")
            self.assertEqual(web["decision"], "ask")
            self.assertEqual(web["matchedRules"][0]["rule"], "WebFetch(docs.qoder.com)")

            headless_web = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=web_action("https://docs.qoder.com/en/cli/permissions"),
                non_interactive=True,
            )
            self.assertEqual(headless_web["decision"], "deny")
            self.assertIn("non-interactive", headless_web["reason"])

            network = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=network_action("api.github.com", port=443),
            )
            self.assertEqual(network["normalizedAction"]["canonical"], "Network(api.github.com:443)")
            self.assertEqual(network["matchedRules"][0]["rule"], "Network(api.github.com:443)")

            external_mcp = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=mcp_action("github", "create_issue"),
            )
            self.assertEqual(external_mcp["normalizedAction"]["tool"], "mcp__github__create_issue")
            self.assertEqual(external_mcp["matchedRules"][0]["rule"], "mcp__github__create_issue")

            connector = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=connector_action("github", "read", connector_type="git"),
            )
            self.assertEqual(connector["normalizedAction"]["canonical"], "Connector(github:read)")
            self.assertEqual(connector["matchedRules"][0]["rule"], "Connector(github:read)")

            artifact_store = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=artifact_store_action("local-artifacts", "write", artifact_kind="command_log"),
            )
            self.assertEqual(artifact_store["normalizedAction"]["canonical"], "ArtifactStore(local-artifacts:write)")
            self.assertEqual(artifact_store["matchedRules"][0]["rule"], "ArtifactStore(local-artifacts:write)")

    def test_effective_permission_engine_handles_env_connector_scopes_and_artifact_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            provider_secret_use = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=env_var_action("OPENAI_API_KEY", "use"),
                non_interactive=True,
            )
            self.assertEqual(provider_secret_use["normalizedAction"]["canonical"], "EnvVar(OPENAI_API_KEY:use)")
            self.assertEqual(provider_secret_use["decision"], "allow")
            self.assertEqual(provider_secret_use["matchedRules"][0]["rule"], "EnvVar(OPENAI_API_KEY:use)")

            secret_read = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=env_var_action("OPENAI_API_KEY", "read"),
                non_interactive=True,
            )
            self.assertEqual(secret_read["normalizedAction"]["canonical"], "EnvVar(OPENAI_API_KEY:read)")
            self.assertEqual(secret_read["decision"], "deny")
            self.assertEqual(secret_read["matchedRules"][0]["rule"], "EnvVar(*:read)")
            self.assertEqual(secret_read["riskAssessment"]["riskLevel"], "critical")
            self.assertEqual(secret_read["riskAssessment"]["recommendedDecision"], "deny")
            self.assertTrue(secret_read["riskAssessment"]["requiresHumanReview"])

            scoped_connector = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=connector_action("github", "read", connector_type="issue", connector_scope="issues"),
            )
            self.assertEqual(scoped_connector["normalizedAction"]["canonical"], "Connector(github:issues:read)")
            self.assertEqual(scoped_connector["decision"], "ask")
            self.assertEqual(scoped_connector["matchedRules"][0]["rule"], "Connector(github:issues:read)")
            self.assertEqual(scoped_connector["riskAssessment"]["riskLevel"], "medium")

            bounded_artifact = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=artifact_store_action(
                    "local-artifacts",
                    "write",
                    artifact_kind="command_log",
                    retention_policy="reviewed-runs",
                    redaction_mode="sanitize",
                ),
            )
            self.assertEqual(
                bounded_artifact["normalizedAction"]["canonical"],
                "ArtifactStore(local-artifacts:write:retention=reviewed-runs:redaction=sanitize)",
            )
            self.assertEqual(bounded_artifact["matchedRules"][0]["rule"], "ArtifactStore(local-artifacts:write:retention=reviewed-runs:redaction=sanitize)")

            unredacted_export = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=artifact_store_action(
                    "local-artifacts",
                    "export",
                    export_policy="include",
                    sensitivity="secret",
                ),
                non_interactive=True,
            )
            self.assertEqual(unredacted_export["decision"], "deny")
            self.assertTrue(unredacted_export["sensitiveMatches"])
            self.assertIn("ask converted to deny", unredacted_export["reason"])
            self.assertEqual(unredacted_export["riskAssessment"]["riskLevel"], "high")
            self.assertEqual(unredacted_export["riskAssessment"]["recommendedDecision"], "ask")

    def test_service_member_denies_external_action_shapes_by_default_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            index = load_workspace(workspace)

            denied = explain_effective_permissions(
                index,
                member="memory-service",
                action=mcp_action("github", "create_issue"),
                non_interactive=True,
            )
            self.assertEqual(denied["decision"], "deny")
            self.assertEqual(denied["matchedRules"], [])
            self.assertIn("ask converted to deny", denied["reason"])

    def test_api_and_mcp_explain_permission_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            get_response = client.get(
                "/permissions/effective",
                params={
                    "member": BACKEND_MEMBER,
                    "assignment": BACKEND_ASSIGNMENT,
                    "tool": "Read",
                    "path": "/docs/architecture.md",
                },
            )
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["decision"], "allow")

            post_response = client.post(
                "/permissions/explain",
                json={
                    "member": BACKEND_MEMBER,
                    "assignment": BACKEND_ASSIGNMENT,
                    "action": {"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"},
                    "nonInteractive": True,
                },
            )
            self.assertEqual(post_response.status_code, 200)
            self.assertEqual(post_response.json()["decision"], "deny")

            env_response = client.get(
                "/permissions/effective",
                params={
                    "member": BACKEND_MEMBER,
                    "assignment": BACKEND_ASSIGNMENT,
                    "tool": "EnvVar",
                    "envVar": "OPENAI_API_KEY",
                    "operation": "use",
                    "nonInteractive": True,
                },
            )
            self.assertEqual(env_response.status_code, 200)
            self.assertEqual(env_response.json()["normalizedAction"]["canonical"], "EnvVar(OPENAI_API_KEY:use)")
            self.assertEqual(env_response.json()["decision"], "allow")

            mcp_response = client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": "permission-call",
                    "method": "tools/call",
                    "params": {
                        "name": "explain_permissions",
                        "arguments": {
                            "member": "memory-service",
                            "action": {"tool": "Bash", "command": "python -m unittest discover tests"},
                        },
                    },
                },
            )
            self.assertEqual(mcp_response.status_code, 200)
            payload = mcp_response.json()["result"]["structuredContent"]
            self.assertEqual(payload["tool"], "explain_permissions")
            self.assertEqual(payload["decision"], "deny")
            self.assertEqual(payload["matchedRules"][0]["rule"], "Bash(*)")


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
