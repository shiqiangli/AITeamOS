from __future__ import annotations

from typing import Any, Mapping

from aiteamos_connectors import (
    BaseConnectorAdapter,
    ConnectorAdapterFixture,
    ConnectorAdapterRequest,
    ConnectorDescriptor,
    ConnectorPackage,
)


class SlackNotificationAdapter(BaseConnectorAdapter):
    def __init__(self) -> None:
        super().__init__(provider="slack", connector_type="chat")

    def normalize(self, request: ConnectorAdapterRequest) -> dict[str, Any]:
        payload = request.payload if isinstance(request.payload, Mapping) else {}
        event = payload.get("event") if isinstance(payload.get("event"), Mapping) else {}
        normalized = {
            "connector": request.connector_id,
            "provider": request.provider,
            "connectorType": request.connector_type,
            "eventType": request.event_type,
            "receivedAt": request.received_at,
            "teamId": payload.get("team_id"),
            "eventId": payload.get("event_id"),
            "messageType": event.get("type"),
            "channel": event.get("channel"),
            "sender": event.get("user"),
            "textPreview": _preview(event.get("text")),
        }
        return {key: str(value) for key, value in normalized.items() if value not in (None, "")}


def connector_package() -> ConnectorPackage:
    return ConnectorPackage(
        name="aiteamos.reference.slack-notification",
        version="0.1.0",
        provider="slack",
        connector_types=("chat",),
        fixtures=(slack_message_fixture(),),
        source="example:slack-notification",
    )


def slack_message_fixture() -> ConnectorAdapterFixture:
    return ConnectorAdapterFixture(
        id="slack.notification.message",
        description="Fake signed Slack message event normalizes into a chat notification summary.",
        adapter=SlackNotificationAdapter(),
        request=ConnectorAdapterRequest(
            connector_id="slack-notification-demo",
            provider="slack",
            connector_type="chat",
            event_type="message",
            received_at="2026-05-23T09:07:23+08:00",
            headers={
                "X-Slack-Request-Timestamp": "1770000000",
                "X-Slack-Signature": "v0=fake-signature-secret",
                "Authorization": "Bearer fake-authorization-secret",
            },
            payload={
                "team_id": "T123",
                "event_id": "Ev123",
                "event": {
                    "type": "message",
                    "channel": "C123",
                    "user": "U123",
                    "text": "Build finished for example/aiteamos",
                },
                "botToken": "xoxb-fake-secret",
            },
        ),
        connector=ConnectorDescriptor(
            connector_id="slack-notification-demo",
            provider="slack",
            connector_type="chat",
            owner_member="memory-service",
            projects=("aiteamos",),
            secret_refs={"botTokenEnv": "AITEAMOS_SLACK_NOTIFICATION_FIXTURE_TOKEN"},
            permission_policies=("service-memory-default",),
        ),
        expected_normalized_summary={
            "connector": "slack-notification-demo",
            "provider": "slack",
            "connectorType": "chat",
            "eventType": "message",
            "receivedAt": "2026-05-23T09:07:23+08:00",
            "teamId": "T123",
            "eventId": "Ev123",
            "messageType": "message",
            "channel": "C123",
            "sender": "U123",
            "textPreview": "Build finished for example/aiteamos",
        },
        env={"AITEAMOS_SLACK_NOTIFICATION_FIXTURE_TOKEN": "fixture-slack-token"},
        forbidden_values=(
            "fixture-slack-token",
            "fake-signature-secret",
            "fake-authorization-secret",
            "xoxb-fake-secret",
        ),
    )


def _preview(value: Any, *, limit: int = 120) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]
