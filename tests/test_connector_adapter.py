from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import unittest

from aiteamos_connectors import (
    BaseConnectorAdapter,
    ConnectorAdapter,
    ConnectorAdapterRequest,
    ConnectorDescriptor,
    run_connector_adapter,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class ConnectorAdapterContractTest(unittest.TestCase):
    def test_reference_adapter_runs_contract_without_leaking_secret_values(self) -> None:
        adapter = BaseConnectorAdapter(provider="github", connector_type="git")
        request = ConnectorAdapterRequest(
            connector_id="github-main",
            provider="github",
            connector_type="git",
            event_type="issues",
            received_at="2026-05-23T08:54:44+08:00",
            headers={
                "X-GitHub-Delivery": "delivery-123",
                "X-GitHub-Event": "issues",
                "Authorization": "Bearer never-log-this",
                "X-Hub-Signature-256": "sha256=never-log-this",
            },
            payload={
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "issue": {
                    "number": 42,
                    "title": "Normalize connector events",
                    "html_url": "https://example.invalid/issues/42",
                },
                "installation": {"id": 12345},
                "sender": {"login": "octocat"},
                "token": "payload-token",
            },
        )
        descriptor = ConnectorDescriptor(
            connector_id="github-main",
            provider="github",
            connector_type="git",
            owner_member="memory-service",
            projects=("aiteamos",),
            config={"allowedRepositories": ["example/aiteamos"]},
            secret_refs={"tokenEnv": "AITEAMOS_TEST_GITHUB_TOKEN"},
            permission_policies=("service-memory-default",),
        )

        with patch.dict("os.environ", {"AITEAMOS_TEST_GITHUB_TOKEN": "github-token-value"}, clear=False):
            result = run_connector_adapter(adapter, request, descriptor)

        self.assertIsInstance(adapter, ConnectorAdapter)
        self.assertEqual(result.admission["status"], "admitted")
        self.assertEqual(result.health["status"], "healthy")
        self.assertEqual(result.normalized_summary["repository"], "example/aiteamos")
        self.assertEqual(result.normalized_summary["number"], "42")
        self.assertTrue(result.dedupe_key.startswith("connector:github-main:"))
        self.assertEqual(result.redacted["redactedPayload"]["token"], "[REDACTED]")
        self.assertIn("X-GitHub-Delivery", result.redacted["safeHeaders"])
        self.assertNotIn("Authorization", result.redacted["safeHeaders"])
        self.assertNotIn("X-Hub-Signature-256", result.redacted["safeHeaders"])
        serialized = str(result.as_dict())
        self.assertNotIn("github-token-value", serialized)
        self.assertNotIn("never-log-this", serialized)
        self.assertNotIn("payload-token", serialized)

    def test_reference_adapter_blocks_provider_mismatch_fail_closed(self) -> None:
        adapter = BaseConnectorAdapter(provider="slack", connector_type="chat")
        request = ConnectorAdapterRequest(
            connector_id="github-main",
            provider="github",
            connector_type="git",
            event_type="issues",
            headers={"X-GitHub-Delivery": "delivery-123"},
            payload={"action": "opened"},
        )
        descriptor = ConnectorDescriptor(
            connector_id="github-main",
            provider="github",
            connector_type="git",
            secret_refs={"tokenEnv": "AITEAMOS_TEST_GITHUB_TOKEN"},
        )

        result = run_connector_adapter(adapter, request, descriptor)

        self.assertEqual(result.admission["decision"], "deny")
        self.assertEqual(result.admission["status"], "blocked")
        self.assertEqual(result.health["readiness"], "blocked")
        self.assertTrue(any("does not match adapter provider" in blocker for blocker in result.blockers))

    def test_architecture_documents_connector_adapter_boundary(self) -> None:
        text = (REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
        for required in [
            "`ConnectorAdapter`",
            "`admit`",
            "`normalize`",
            "`redact`",
            "`dedupe`",
            "`healthcheck`",
            "does not write `.aiteamos/` manifests",
            "secret values",
        ]:
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
