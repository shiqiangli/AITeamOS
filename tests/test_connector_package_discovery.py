from __future__ import annotations

import unittest

from aiteamos_connectors import (
    ConnectorPackage,
    ENTRY_POINT_GROUP,
    BaseConnectorAdapter,
    ConnectorAdapterFixture,
    ConnectorAdapterRequest,
    ConnectorDescriptor,
    discover_connector_packages,
    evaluate_connector_adapter_fixture,
)
from aiteamos_workspace import connector_package_discovery_records


class FakeEntryPoint:
    group = ENTRY_POINT_GROUP

    def __init__(self, name: str, loaded: object | None = None, error: Exception | None = None) -> None:
        self.name = name
        self._loaded = loaded
        self._error = error

    def load(self) -> object:
        if self._error is not None:
            raise self._error
        return self._loaded


class ConnectorPackageDiscoveryTest(unittest.TestCase):
    def test_discovers_connector_package_from_entry_point_mapping(self) -> None:
        fixture = _notification_fixture()
        entry_point = FakeEntryPoint(
            "notification_demo",
            {
                "name": "notification-demo",
                "version": "1.0.0",
                "provider": "slack",
                "connectorTypes": ["chat"],
                "fixtures": [fixture],
            },
        )

        discovery = discover_connector_packages(entry_points=[entry_point], include_builtin=False)

        self.assertEqual(discovery.errors, ())
        self.assertEqual(len(discovery.packages), 1)
        package = discovery.packages[0]
        self.assertIsInstance(package, ConnectorPackage)
        self.assertEqual(package.name, "notification-demo")
        self.assertEqual(package.source, "aiteamos.connectors:notification_demo")
        self.assertEqual(package.provider, "slack")
        self.assertEqual(package.connector_types, ("chat",))
        self.assertTrue(evaluate_connector_adapter_fixture(package.fixtures[0]).passed)

    def test_entry_point_failure_is_reported_for_workspace_validation(self) -> None:
        entry_point = FakeEntryPoint("broken", error=RuntimeError("boom"))

        discovery = discover_connector_packages(entry_points=[entry_point], include_builtin=False)

        self.assertEqual(discovery.packages, ())
        self.assertEqual(len(discovery.errors), 1)
        issue = discovery.errors[0].as_issue()
        self.assertEqual(issue["severity"], "error")
        self.assertIn("failed to load", issue["message"])

    def test_workspace_bridge_reports_builtin_package_discovery(self) -> None:
        records = connector_package_discovery_records()

        self.assertIn("packages", records)
        self.assertTrue(any(package["name"] == "aiteamos.builtin.github" for package in records["packages"]))


def _notification_fixture() -> ConnectorAdapterFixture:
    return ConnectorAdapterFixture(
        id="slack.message.created",
        description="Minimal notification connector fixture.",
        adapter=BaseConnectorAdapter(provider="slack", connector_type="chat"),
        request=ConnectorAdapterRequest(
            connector_id="slack-demo",
            provider="slack",
            connector_type="chat",
            event_type="message",
            headers={"X-Slack-Request-Timestamp": "1770000000", "X-Slack-Signature": "secret-signature"},
            payload={"event_id": "evt-1", "title": "Build finished", "bot_token": "secret-token"},
        ),
        connector=ConnectorDescriptor(
            connector_id="slack-demo",
            provider="slack",
            connector_type="chat",
            secret_refs={"botTokenEnv": "AITEAMOS_CONNECTOR_TEST_SLACK_TOKEN"},
        ),
        expected_normalized_summary={
            "connector": "slack-demo",
            "provider": "slack",
            "connectorType": "chat",
            "eventType": "message",
            "title": "Build finished",
        },
        env={"AITEAMOS_CONNECTOR_TEST_SLACK_TOKEN": "secret-env-token"},
        forbidden_values=("secret-signature", "secret-token", "secret-env-token"),
    )


if __name__ == "__main__":
    unittest.main()
