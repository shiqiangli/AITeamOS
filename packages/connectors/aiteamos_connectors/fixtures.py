from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import os
from typing import Any, Iterator, Mapping

from .adapter import BaseConnectorAdapter, ConnectorAdapter, ConnectorAdapterRequest, ConnectorDescriptor, run_connector_adapter


@dataclass(frozen=True)
class ConnectorAdapterFixture:
    id: str
    description: str
    adapter: ConnectorAdapter
    request: ConnectorAdapterRequest
    connector: ConnectorDescriptor
    expected_normalized_summary: Mapping[str, Any]
    env: Mapping[str, str] = field(default_factory=dict)
    expected_admission_status: str = "admitted"
    expected_health_status: str = "healthy"
    forbidden_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConnectorAdapterFixtureResult:
    id: str
    provider: str
    event_type: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def connector_adapter_fixtures() -> list[ConnectorAdapterFixture]:
    return [
        ConnectorAdapterFixture(
            id="github.issue.opened",
            description="Signed GitHub issue-opened webhook normalizes into a safe provider-neutral summary.",
            adapter=BaseConnectorAdapter(provider="github", connector_type="git"),
            request=ConnectorAdapterRequest(
                connector_id="github-main",
                provider="github",
                connector_type="git",
                event_type="issues",
                received_at="2026-05-23T09:00:22+08:00",
                headers={
                    "X-GitHub-Delivery": "fixture-delivery-001",
                    "X-GitHub-Event": "issues",
                    "X-Hub-Signature-256": "sha256=fixture-signature-secret",
                    "Authorization": "Bearer fixture-auth-secret",
                },
                payload={
                    "action": "opened",
                    "repository": {"full_name": "example/aiteamos"},
                    "issue": {
                        "number": 7,
                        "title": "Connector fixtures should validate during workspace checks",
                        "html_url": "https://example.invalid/example/aiteamos/issues/7",
                    },
                    "installation": {"id": 12345},
                    "sender": {"login": "octocat"},
                    "token": "fixture-payload-secret",
                },
            ),
            connector=ConnectorDescriptor(
                connector_id="github-main",
                provider="github",
                connector_type="git",
                owner_member="memory-service",
                projects=("aiteamos",),
                config={
                    "allowedRepositories": ["example/aiteamos"],
                    "allowedInstallationIds": ["12345"],
                },
                secret_refs={"webhookSecretEnv": "AITEAMOS_CONNECTOR_FIXTURE_SECRET"},
                permission_policies=("service-memory-default",),
            ),
            expected_normalized_summary={
                "connector": "github-main",
                "provider": "github",
                "connectorType": "git",
                "eventType": "issues",
                "receivedAt": "2026-05-23T09:00:22+08:00",
                "action": "opened",
                "repository": "example/aiteamos",
                "number": "7",
                "title": "Connector fixtures should validate during workspace checks",
                "installationId": "12345",
                "sender": "octocat",
                "url": "https://example.invalid/example/aiteamos/issues/7",
            },
            env={"AITEAMOS_CONNECTOR_FIXTURE_SECRET": "fixture-secret-value"},
            forbidden_values=(
                "fixture-secret-value",
                "fixture-signature-secret",
                "fixture-auth-secret",
                "fixture-payload-secret",
            ),
        )
    ]


def evaluate_connector_adapter_fixtures(
    fixtures: list[ConnectorAdapterFixture] | None = None,
) -> list[ConnectorAdapterFixtureResult]:
    return [evaluate_connector_adapter_fixture(fixture) for fixture in (fixtures or connector_adapter_fixtures())]


def evaluate_connector_adapter_fixture(fixture: ConnectorAdapterFixture) -> ConnectorAdapterFixtureResult:
    failures: list[str] = []
    warnings: list[str] = []
    with _patched_env(fixture.env):
        result = run_connector_adapter(fixture.adapter, fixture.request, fixture.connector)
    if result.admission.get("status") != fixture.expected_admission_status:
        failures.append(
            f"expected admission {fixture.expected_admission_status}, got {result.admission.get('status')}"
        )
    if result.health.get("status") != fixture.expected_health_status:
        failures.append(f"expected health {fixture.expected_health_status}, got {result.health.get('status')}")
    if result.normalized_summary != dict(fixture.expected_normalized_summary):
        failures.append("normalized summary did not match fixture expectation")
    if result.redacted.get("audit", {}).get("rawPayloadStored") is not False:
        failures.append("redaction audit must report rawPayloadStored=false")
    safe_headers = {str(name).lower() for name in result.redacted.get("safeHeaders", {})}
    if any("signature" in name or "authorization" in name for name in safe_headers):
        failures.append("safe headers include signature or authorization material")
    serialized = str(result.as_dict())
    for forbidden in fixture.forbidden_values:
        if forbidden in serialized:
            failures.append(f"secret value leaked into fixture result: {forbidden}")
    if not result.dedupe_key.startswith(f"connector:{fixture.request.connector_id}:"):
        failures.append("dedupe key does not use the connector namespace")
    if result.warnings:
        warnings.extend(result.warnings)
    return ConnectorAdapterFixtureResult(
        id=fixture.id,
        provider=fixture.request.provider,
        event_type=fixture.request.event_type,
        passed=not failures,
        failures=failures,
        warnings=warnings,
    )


@contextmanager
def _patched_env(values: Mapping[str, str]) -> Iterator[None]:
    previous: dict[str, str | None] = {name: os.environ.get(name) for name in values}
    try:
        for name, value in values.items():
            os.environ[str(name)] = str(value)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
