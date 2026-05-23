from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import os
from typing import Any, Mapping, Protocol, runtime_checkable


SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "key",
    "password",
    "private",
    "secret",
    "signature",
    "token",
)

SAFE_HEADER_NAMES = {
    "x-github-delivery",
    "x-github-event",
    "x-gitlab-event",
    "x-gitlab-event-uuid",
    "x-request-id",
    "x-slack-request-timestamp",
    "x-slack-retry-num",
    "x-slack-retry-reason",
}

DELIVERY_ID_HEADERS = (
    "x-github-delivery",
    "x-gitlab-event-uuid",
    "x-request-id",
)


@dataclass(frozen=True)
class ConnectorAdapterRequest:
    connector_id: str
    provider: str
    event_type: str
    connector_type: str = "other"
    headers: Mapping[str, Any] = field(default_factory=dict)
    payload: Any = field(default_factory=dict)
    received_at: str | None = None
    config: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorDescriptor:
    connector_id: str
    provider: str
    connector_type: str = "other"
    owner_member: str | None = None
    projects: tuple[str, ...] = ()
    config: Mapping[str, Any] = field(default_factory=dict)
    secret_refs: Mapping[str, str] = field(default_factory=dict)
    permission_policies: tuple[str, ...] = ()

    @classmethod
    def from_manifest(cls, connector: Any) -> "ConnectorDescriptor":
        spec = getattr(connector, "spec", None)
        connector_id = (
            getattr(connector, "object_id", None)
            or _metadata_value(connector, "id")
            or _metadata_value(connector, "name")
            or _mapping_value(connector, "id")
            or _mapping_value(connector, "name")
        )
        if spec is None and isinstance(connector, Mapping):
            spec = connector.get("spec", {})
        return cls(
            connector_id=str(connector_id or ""),
            provider=str(_spec_value(spec, "provider") or ""),
            connector_type=str(_spec_value(spec, "connectorType") or "other"),
            owner_member=_optional_string(_spec_value(spec, "ownerMember")),
            projects=tuple(str(item) for item in (_spec_value(spec, "projects") or []) if str(item)),
            config=dict(_spec_value(spec, "config") or {}),
            secret_refs=dict(_spec_value(spec, "secretRefs") or {}),
            permission_policies=tuple(
                str(item) for item in (_spec_value(spec, "permissionPolicies") or []) if str(item)
            ),
        )


@dataclass(frozen=True)
class ConnectorAdapterResult:
    connector: str
    provider: str
    event_type: str
    admission: dict[str, Any]
    normalized_summary: dict[str, Any]
    redacted: dict[str, Any]
    dedupe_key: str
    health: dict[str, Any]
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@runtime_checkable
class ConnectorAdapter(Protocol):
    provider: str | None
    connector_type: str

    def admit(self, request: ConnectorAdapterRequest) -> dict[str, Any]:
        ...

    def normalize(self, request: ConnectorAdapterRequest) -> dict[str, Any]:
        ...

    def redact(self, request: ConnectorAdapterRequest, normalized: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def dedupe(
        self,
        request: ConnectorAdapterRequest,
        normalized: Mapping[str, Any],
        redacted: Mapping[str, Any],
    ) -> str:
        ...

    def healthcheck(self, connector: ConnectorDescriptor, *, observed: Mapping[str, Any] | None = None) -> dict[str, Any]:
        ...


class BaseConnectorAdapter:
    def __init__(self, *, provider: str | None = None, connector_type: str = "other") -> None:
        self.provider = provider
        self.connector_type = connector_type

    def admit(self, request: ConnectorAdapterRequest) -> dict[str, Any]:
        blockers: list[str] = []
        warnings: list[str] = []
        if not request.connector_id:
            blockers.append("connector id is required")
        if not request.provider:
            blockers.append("provider is required")
        if self.provider and request.provider != self.provider:
            blockers.append(f"request provider {request.provider} does not match adapter provider {self.provider}")
        if self.connector_type != "other" and request.connector_type != self.connector_type:
            blockers.append(
                f"request connector type {request.connector_type} does not match adapter type {self.connector_type}"
            )
        if not _safe_headers(request.headers):
            warnings.append("request carries no safe provider headers")
        return {
            "status": "blocked" if blockers else "admitted",
            "decision": "deny" if blockers else "allow",
            "connector": request.connector_id,
            "provider": request.provider,
            "connectorType": request.connector_type,
            "eventType": request.event_type,
            "blockers": blockers,
            "warnings": warnings,
            "audit": {
                "rawPayloadStored": False,
                "signatureStored": False,
                "secretValuesObserved": False,
            },
        }

    def normalize(self, request: ConnectorAdapterRequest) -> dict[str, Any]:
        payload = request.payload if isinstance(request.payload, Mapping) else {}
        repository = _nested_value(payload, ("repository", "full_name")) or _nested_value(payload, ("project", "path_with_namespace"))
        subject = (
            _nested_value(payload, ("issue", "title"))
            or _nested_value(payload, ("pull_request", "title"))
            or _nested_value(payload, ("merge_request", "title"))
            or _string_value(payload, "title")
        )
        number = (
            _nested_value(payload, ("issue", "number"))
            or _nested_value(payload, ("pull_request", "number"))
            or _nested_value(payload, ("merge_request", "iid"))
            or _string_value(payload, "number")
        )
        url = (
            _nested_value(payload, ("issue", "html_url"))
            or _nested_value(payload, ("pull_request", "html_url"))
            or _nested_value(payload, ("merge_request", "url"))
            or _string_value(payload, "url")
            or _string_value(payload, "html_url")
        )
        normalized = {
            "connector": request.connector_id,
            "provider": request.provider,
            "connectorType": request.connector_type,
            "eventType": request.event_type,
            "receivedAt": request.received_at,
            "action": _string_value(payload, "action"),
            "repository": _optional_string(repository),
            "number": _optional_string(number),
            "title": _optional_string(subject),
            "ref": _string_value(payload, "ref"),
            "before": _string_value(payload, "before"),
            "after": _string_value(payload, "after"),
            "installationId": _optional_string(_nested_value(payload, ("installation", "id"))),
            "sender": _optional_string(_nested_value(payload, ("sender", "login"))),
            "url": _optional_string(url),
        }
        return {key: value for key, value in normalized.items() if value not in (None, "")}

    def redact(self, request: ConnectorAdapterRequest, normalized: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "safeHeaders": _safe_headers(request.headers),
            "normalizedSummary": _redact_nested(dict(normalized)),
            "redactedPayload": _redact_nested(request.payload),
            "audit": {
                "rawPayloadStored": False,
                "signatureStored": False,
                "authorizationStored": False,
                "secretValuesObserved": False,
            },
        }

    def dedupe(
        self,
        request: ConnectorAdapterRequest,
        normalized: Mapping[str, Any],
        redacted: Mapping[str, Any],
    ) -> str:
        external_id = _delivery_id(request.headers) or _payload_external_id(request.payload)
        evidence = {
            "connector": request.connector_id,
            "provider": request.provider,
            "eventType": request.event_type,
            "externalId": external_id,
            "summary": dict(normalized),
            "safeHeaders": dict(redacted.get("safeHeaders", {})),
        }
        digest = sha256(_stable_json(evidence).encode("utf-8")).hexdigest()[:24]
        return f"connector:{request.connector_id}:{digest}"

    def healthcheck(self, connector: ConnectorDescriptor, *, observed: Mapping[str, Any] | None = None) -> dict[str, Any]:
        observed = dict(observed or {})
        blockers: list[str] = []
        warnings: list[str] = []
        required_secrets = {str(name): str(env_name) for name, env_name in connector.secret_refs.items() if str(env_name)}
        missing_secrets = [name for name, env_name in required_secrets.items() if not os.environ.get(env_name)]
        if missing_secrets:
            blockers.append(f"missing connector secret environment refs: {', '.join(sorted(missing_secrets))}")
        if not required_secrets:
            warnings.append("connector declares no secretRefs; provider token readiness was not checked")
        if self.provider and connector.provider and connector.provider != self.provider:
            blockers.append(f"connector provider {connector.provider} does not match adapter provider {self.provider}")
        if self.connector_type != "other" and connector.connector_type != self.connector_type:
            blockers.append(
                f"connector type {connector.connector_type} does not match adapter type {self.connector_type}"
            )
        provider_status = str(observed.get("status") or observed.get("providerStatus") or "").lower()
        if provider_status in {"blocked", "down", "outage"}:
            blockers.append(f"provider diagnostics reported {provider_status}")
        elif provider_status in {"degraded", "rate_limited"}:
            warnings.append(f"provider diagnostics reported {provider_status}")
        return {
            "connector": connector.connector_id,
            "provider": connector.provider,
            "connectorType": connector.connector_type,
            "status": "blocked" if blockers else ("degraded" if warnings else "healthy"),
            "readiness": "blocked" if blockers else ("degraded" if warnings else "ready"),
            "tokenStatus": "missing" if missing_secrets else ("present" if required_secrets else "not_configured"),
            "requiredSecrets": required_secrets,
            "missingSecrets": sorted(missing_secrets),
            "blockers": blockers,
            "warnings": warnings,
            "audit": {
                "secretValuesObserved": False,
                "providerNetworkCalled": bool(observed.get("providerNetworkCalled", False)),
            },
        }


def run_connector_adapter(
    adapter: ConnectorAdapter,
    request: ConnectorAdapterRequest,
    connector: ConnectorDescriptor | Mapping[str, Any] | Any,
    *,
    observed_health: Mapping[str, Any] | None = None,
) -> ConnectorAdapterResult:
    descriptor = connector if isinstance(connector, ConnectorDescriptor) else ConnectorDescriptor.from_manifest(connector)
    admission = adapter.admit(request)
    normalized = adapter.normalize(request)
    redacted = adapter.redact(request, normalized)
    dedupe_key = adapter.dedupe(request, normalized, redacted)
    health = adapter.healthcheck(descriptor, observed=observed_health)
    blockers = _unique_strings(admission.get("blockers", []), health.get("blockers", []))
    warnings = _unique_strings(admission.get("warnings", []), health.get("warnings", []))
    return ConnectorAdapterResult(
        connector=request.connector_id,
        provider=request.provider,
        event_type=request.event_type,
        admission=admission,
        normalized_summary=normalized,
        redacted=redacted,
        dedupe_key=dedupe_key,
        health=health,
        blockers=blockers,
        warnings=warnings,
    )


def _safe_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for name, value in headers.items():
        lowered = str(name).lower()
        if lowered in SAFE_HEADER_NAMES:
            safe[str(name)] = str(value)
        elif not _is_sensitive_key(lowered) and lowered.startswith("x-"):
            safe[str(name)] = str(value)
    return safe


def _delivery_id(headers: Mapping[str, Any]) -> str | None:
    lowered = {str(name).lower(): str(value) for name, value in headers.items()}
    for header in DELIVERY_ID_HEADERS:
        if lowered.get(header):
            return lowered[header]
    return None


def _payload_external_id(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for key in ("delivery_id", "event_id", "id"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _redact_nested(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            redacted[str(key)] = "[REDACTED]" if _is_sensitive_key(str(key).lower()) else _redact_nested(nested)
        return redacted
    if isinstance(value, list):
        return [_redact_nested(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_nested(item) for item in value)
    return value


def _is_sensitive_key(lowered_key: str) -> bool:
    return any(part in lowered_key for part in SENSITIVE_KEY_PARTS)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _nested_value(payload: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for part in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _string_value(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return _optional_string(value)


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _metadata_value(connector: Any, key: str) -> Any:
    metadata = getattr(connector, "metadata", None)
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return getattr(metadata, key, None)


def _mapping_value(connector: Any, key: str) -> Any:
    if isinstance(connector, Mapping):
        return connector.get(key) or (connector.get("metadata") or {}).get(key)
    return None


def _spec_value(spec: Any, key: str) -> Any:
    if isinstance(spec, Mapping):
        return spec.get(key)
    return getattr(spec, key, None)


def _unique_strings(*groups: Any) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for group in groups:
        for item in group or []:
            text = str(item)
            if text not in seen:
                seen.add(text)
                values.append(text)
    return values
