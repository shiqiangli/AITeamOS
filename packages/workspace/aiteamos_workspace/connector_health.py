from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import os
import re

from aiteamos_schema import ConnectorHealthCheck

from .audit import decision_audit_record
from .io import write_yaml
from .loader import WorkspaceIndex, load_workspace, manifest_to_record


def connector_health_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    connector: str | None = None,
) -> list[dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    checks = [
        check
        for check in index.connector_health_checks.values()
        if connector is None or check.spec.connector == connector
    ]
    return [manifest_to_record(check) for check in sorted(checks, key=lambda item: item.object_id)]


def cleanup_connector_health_checks(
    workspace_path: str | Path,
    *,
    actor_member: str | None = None,
    max_age_days: int = 30,
    keep_latest_per_connector: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member and actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    now = datetime.now().astimezone()
    cutoff = now - timedelta(days=max(0, int(max_age_days)))
    latest_ids: set[str] = set()
    if keep_latest_per_connector:
        connectors = {check.spec.connector for check in index.connector_health_checks.values()}
        for connector_id in connectors:
            latest = latest_connector_health_check(index, connector_id)
            if latest is not None:
                latest_ids.add(latest.object_id)

    archived: list[str] = []
    skipped_latest: list[str] = []
    for check in sorted(index.connector_health_checks.values(), key=lambda item: item.object_id):
        if check.spec.lifecycle == "archived":
            continue
        checked_at = _parse_timestamp(check.spec.checkedAt or check.metadata.createdAt)
        if checked_at is None or checked_at > cutoff:
            continue
        if keep_latest_per_connector and check.object_id in latest_ids:
            skipped_latest.append(check.object_id)
            continue
        archived.append(check.object_id)
        if dry_run:
            continue
        retained_until = (checked_at + timedelta(days=max(0, int(max_age_days)))).isoformat(timespec="milliseconds")
        data = check.model_dump(mode="json", exclude_none=True)
        spec = data.setdefault("spec", {})
        spec["lifecycle"] = "archived"
        spec["retainedUntil"] = retained_until
        spec["archivedAt"] = now.isoformat(timespec="milliseconds")
        spec.setdefault("warnings", [])
        if "archived by connector health retention cleanup" not in spec["warnings"]:
            spec["warnings"].append("archived by connector health retention cleanup")
        spec.setdefault("decisionAudit", []).append(
            decision_audit_record(
                index,
                decision_kind="system_check",
                decision="archived",
                actor_member=actor_member,
                authority="expire",
                reason="ConnectorHealthCheck exceeded retention window and was archived in place.",
                source="connector-health-retention-cleanup",
                decided_at=now.isoformat(timespec="milliseconds"),
                evidence=[
                    {
                        "kind": "connector-health-check",
                        "connectorHealthCheck": check.object_id,
                        "connector": check.spec.connector,
                        "checkedAt": check.spec.checkedAt,
                        "maxAgeDays": max(0, int(max_age_days)),
                        "retainedUntil": retained_until,
                    }
                ],
            )
        )
        archived_check = ConnectorHealthCheck.model_validate(data)
        write_yaml(
            index.workspace_root / "connectors" / "health" / f"{archived_check.object_id}.yaml",
            archived_check.model_dump(mode="json", exclude_none=True),
        )

    return {
        "archived": archived,
        "archivedCount": len(archived),
        "skippedLatest": skipped_latest,
        "dryRun": dry_run,
        "scannedCount": len(index.connector_health_checks),
        "cutoff": cutoff.isoformat(timespec="milliseconds"),
    }


def latest_connector_health_check(
    workspace_or_index: str | Path | WorkspaceIndex,
    connector_id: str,
    *,
    include_archived: bool = False,
) -> ConnectorHealthCheck | None:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    checks = [
        check
        for check in index.connector_health_checks.values()
        if check.spec.connector == connector_id and (include_archived or check.spec.lifecycle != "archived")
    ]
    if not checks:
        return None
    return sorted(checks, key=_health_check_sort_key)[-1]


def connector_health_admission_decision(
    workspace_or_index: str | Path | WorkspaceIndex,
    connector_id: str,
    *,
    config: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    config = dict(config or {})
    require_healthy = _requires_healthy_connector(config)
    current_time = now or datetime.now().astimezone()
    latest = latest_connector_health_check(index, connector_id)
    blockers: list[str] = []
    warnings: list[str] = []
    record: dict[str, Any] = {
        "connector": connector_id,
        "policy": "require_healthy" if require_healthy else "warn_unhealthy",
    }

    if latest is None:
        message = f"connector {connector_id} has no ConnectorHealthCheck"
        if require_healthy:
            blockers.append(message)
        else:
            warnings.append(message)
        record.update({"status": "missing", "readiness": "unknown"})
        return {"record": record, "blockers": blockers, "warnings": warnings}

    checked_at = latest.spec.checkedAt or latest.metadata.createdAt
    record.update(
        {
            "latestHealthCheck": latest.object_id,
            "checkedAt": checked_at,
            "status": latest.spec.status,
            "readiness": latest.spec.readiness,
            "tokenStatus": latest.spec.tokenStatus,
            "installationStatus": latest.spec.installationStatus,
        }
    )
    unhealthy_message = (
        f"connector {connector_id} latest health check {latest.object_id} is "
        f"{latest.spec.status}/{latest.spec.readiness}"
    )
    if latest.spec.status == "blocked" or latest.spec.readiness == "blocked":
        blockers.append(f"{unhealthy_message}: {'; '.join(latest.spec.blockers) or 'blocked'}")
    elif latest.spec.status != "healthy" or latest.spec.readiness != "ready":
        if require_healthy:
            blockers.append(unhealthy_message)
        else:
            warnings.append(unhealthy_message)

    max_age_seconds = _health_max_age_seconds(config)
    checked_time = _parse_timestamp(checked_at)
    if max_age_seconds is not None and checked_time is not None:
        age_seconds = abs((current_time - checked_time).total_seconds())
        record["ageSeconds"] = int(age_seconds)
        record["maxAgeSeconds"] = max_age_seconds
        if age_seconds > max_age_seconds:
            message = f"connector {connector_id} latest health check {latest.object_id} is stale"
            if require_healthy:
                blockers.append(message)
            else:
                warnings.append(message)
    elif max_age_seconds is not None:
        message = f"connector {connector_id} latest health check {latest.object_id} has no parseable checkedAt"
        if require_healthy:
            blockers.append(message)
        else:
            warnings.append(message)

    return {"record": record, "blockers": blockers, "warnings": warnings}


def check_connector_health(
    workspace_path: str | Path,
    connector_id: str,
    *,
    actor_member: str | None = None,
    observed_repositories: list[str] | None = None,
    observed_installation_ids: list[str] | None = None,
    provider_network_called: bool | None = None,
    required_provider_scopes: list[str] | None = None,
    observed_provider_scopes: list[str] | None = None,
    provider_diagnostics: dict[str, Any] | None = None,
) -> ConnectorHealthCheck:
    index = load_workspace(workspace_path)
    if connector_id not in index.connectors:
        raise KeyError(f"unknown connector {connector_id}")
    if actor_member and actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")

    connector = index.connectors[connector_id]
    config = dict(connector.spec.config or {})
    required_secrets = _required_secret_refs(connector.spec.secretRefs or {})
    missing_secrets = [name for name, env_name in required_secrets.items() if not os.environ.get(env_name)]
    allowed_repositories = _string_list(
        config.get("allowedRepositories")
        or config.get("repositoryAllowlist")
        or config.get("repositories")
    )
    allowed_installation_ids = _string_list(config.get("allowedInstallationIds") or config.get("installationIds"))
    observed_repositories = _string_list(observed_repositories)
    observed_installation_ids = _string_list(observed_installation_ids)
    diagnostics = dict(provider_diagnostics or {})
    provider_network_called = _truthy(provider_network_called if provider_network_called is not None else diagnostics.get("providerNetworkCalled"))
    required_provider_scopes = _string_list(
        required_provider_scopes
        or config.get("requiredProviderScopes")
        or config.get("providerRequiredScopes")
        or config.get("requiredScopes")
    )
    observed_provider_scopes = _string_list(
        observed_provider_scopes
        or diagnostics.get("observedProviderScopes")
        or diagnostics.get("providerScopes")
        or diagnostics.get("scopes")
    )
    retention_policy = _retention_policy(config)

    blockers: list[str] = []
    warnings: list[str] = []
    provider_probe_blockers: list[str] = []
    if required_secrets and missing_secrets:
        blockers.append(f"missing connector secret environment refs: {', '.join(missing_secrets)}")
    if not required_secrets:
        warnings.append("connector declares no secretRefs; provider token readiness was not checked")

    disallowed_repositories = sorted(set(observed_repositories).difference(allowed_repositories)) if allowed_repositories else []
    if disallowed_repositories:
        blockers.append(f"observed repositories are outside connector allowlist: {', '.join(disallowed_repositories)}")
    elif connector.spec.connectorType in {"git", "issue"} and not allowed_repositories:
        warnings.append("connector has no repository allowlist; provider admission should stay conservative")

    disallowed_installations = sorted(set(observed_installation_ids).difference(allowed_installation_ids)) if allowed_installation_ids else []
    if disallowed_installations:
        blockers.append(f"observed provider installation ids are outside connector allowlist: {', '.join(disallowed_installations)}")
    elif connector.spec.connectorType in {"git", "issue"} and not allowed_installation_ids:
        warnings.append("connector has no provider installation id allowlist")
    elif allowed_installation_ids and not observed_installation_ids:
        warnings.append("provider installation allowlist exists but no observed installation id was supplied")

    provider_status = str(diagnostics.get("status") or "").lower()
    if provider_status in {"down", "outage", "blocked"}:
        provider_probe_blockers.append(f"provider diagnostics reported {provider_status}")
    elif provider_status in {"degraded", "rate_limited"}:
        warnings.append(f"provider diagnostics reported {provider_status}")

    if provider_network_called:
        endpoint_status = str(diagnostics.get("endpointStatus") or diagnostics.get("apiStatus") or "").lower()
        if diagnostics.get("apiReachable") is False or endpoint_status in {
            "down",
            "failed",
            "timeout",
            "unreachable",
            "dns_failure",
            "tls_failure",
        }:
            provider_probe_blockers.append("provider network probe could not reach the provider API")
        auth_status = str(
            diagnostics.get("authStatus")
            or diagnostics.get("authorizationStatus")
            or diagnostics.get("credentialStatus")
            or ""
        ).lower()
        if auth_status in {"unauthorized", "forbidden", "expired", "revoked", "invalid", "missing"}:
            provider_probe_blockers.append(f"provider credential probe reported {auth_status}")
        elif auth_status in {"limited", "partial"}:
            warnings.append(f"provider credential probe reported {auth_status}")
        rate_remaining = _int_or_none(diagnostics.get("rateLimitRemaining"))
        if rate_remaining is not None and rate_remaining <= 0:
            warnings.append("provider diagnostics reported exhausted rate limit")

    missing_provider_scopes = sorted(set(required_provider_scopes).difference(observed_provider_scopes))
    if missing_provider_scopes:
        provider_probe_blockers.append(
            f"provider credential is missing required scopes: {', '.join(missing_provider_scopes)}"
        )
    elif required_provider_scopes and provider_network_called and not observed_provider_scopes:
        warnings.append("provider network probe did not return observed provider scopes")
    elif required_provider_scopes and not provider_network_called:
        warnings.append("provider scope requirements are configured but no hosted provider probe was recorded")

    blockers.extend(provider_probe_blockers)
    if provider_network_called:
        provider_probe_status = "failed" if provider_probe_blockers else "passed"
    elif provider_probe_blockers:
        provider_probe_status = "failed"
    elif required_provider_scopes or observed_provider_scopes:
        provider_probe_status = "not_checked"
    else:
        provider_probe_status = "not_configured"

    token_status = "not_configured"
    if required_secrets:
        token_status = "missing" if missing_secrets else "present"

    installation_status = "not_configured"
    if allowed_installation_ids:
        installation_status = "mismatched" if disallowed_installations else ("authorized" if observed_installation_ids else "not_checked")

    status = "blocked" if blockers else ("degraded" if warnings else "healthy")
    readiness = "blocked" if blockers else ("degraded" if warnings else "ready")
    now = datetime.now().astimezone()
    audit = decision_audit_record(
        index,
        decision_kind="system_check",
        decision=status,
        actor_member=actor_member,
        authority="record",
        reason="Connector health check recorded provider readiness evidence.",
        source="connector-health-check",
        decided_at=now.isoformat(timespec="milliseconds"),
        evidence=[
            {
                "kind": "connector-health-check",
                "connector": connector.object_id,
                "provider": connector.spec.provider,
                "connectorType": connector.spec.connectorType,
                "project": _single_project(connector.spec.projects),
                "tokenStatus": token_status,
                "installationStatus": installation_status,
                "requiredSecretRefs": sorted(required_secrets),
                "missingSecretRefs": missing_secrets,
                "allowedRepositories": allowed_repositories,
                "observedRepositories": observed_repositories,
                "allowedInstallationIds": allowed_installation_ids,
                "observedInstallationIds": observed_installation_ids,
                "providerNetworkCalled": provider_network_called,
                "providerProbeStatus": provider_probe_status,
                "requiredProviderScopes": required_provider_scopes,
                "observedProviderScopes": observed_provider_scopes,
                "missingProviderScopes": missing_provider_scopes,
                "providerStatus": diagnostics.get("status"),
            }
        ],
    )
    check = ConnectorHealthCheck.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "ConnectorHealthCheck",
            "metadata": {
                "id": _connector_health_check_id(connector.object_id, now),
                "createdAt": now.isoformat(timespec="milliseconds"),
            },
            "spec": {
                "connector": connector.object_id,
                "provider": connector.spec.provider,
                "connectorType": connector.spec.connectorType,
                "project": _single_project(connector.spec.projects),
                "checkedAt": now.isoformat(timespec="milliseconds"),
                "status": status,
                "readiness": readiness,
                "tokenStatus": token_status,
                "installationStatus": installation_status,
                "requiredSecrets": required_secrets,
                "missingSecrets": missing_secrets,
                "allowedRepositories": allowed_repositories,
                "observedRepositories": observed_repositories,
                "allowedInstallationIds": allowed_installation_ids,
                "observedInstallationIds": observed_installation_ids,
                "providerNetworkCalled": provider_network_called,
                "providerProbeStatus": provider_probe_status,
                "requiredProviderScopes": required_provider_scopes,
                "observedProviderScopes": observed_provider_scopes,
                "missingProviderScopes": missing_provider_scopes,
                "providerDiagnostics": _safe_provider_diagnostics(diagnostics),
                "retentionPolicy": retention_policy,
                "summary": _summary(status, connector.object_id),
                "blockers": blockers,
                "warnings": warnings,
                "decisionAudit": [audit],
                "audit": {
                    "secretsStored": False,
                    "secretValuesObserved": False,
                    "providerNetworkCalled": provider_network_called,
                    "source": "hosted-provider-calibration" if provider_network_called else "local-static-check",
                },
            },
        }
    )
    write_yaml(
        index.workspace_root / "connectors" / "health" / f"{check.object_id}.yaml",
        check.model_dump(mode="json", exclude_none=True),
    )
    return check


def _connector_health_check_id(connector_id: str, now: datetime) -> str:
    safe_connector = re.sub(r"[^A-Za-z0-9_.-]+", "-", connector_id).strip("-") or "connector"
    return f"CHEALTH-{safe_connector}-{now:%Y%m%dT%H%M%S}{now.microsecond // 1000:03d}"


def _health_check_sort_key(check: ConnectorHealthCheck) -> tuple[str, str]:
    return (check.spec.checkedAt or check.metadata.createdAt or "", check.object_id)


def _requires_healthy_connector(config: dict[str, Any]) -> bool:
    if bool(config.get("requireHealthyConnector") or config.get("requireConnectorHealth")):
        return True
    policy = str(config.get("connectorHealthPolicy") or config.get("healthPolicy") or "").lower()
    return policy in {"strict", "require", "required", "require_healthy", "block_unhealthy"}


def _health_max_age_seconds(config: dict[str, Any]) -> int | None:
    value = config.get("connectorHealthMaxAgeSeconds") or config.get("healthMaxAgeSeconds")
    if value is None:
        return None
    return max(0, int(value))


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _required_secret_refs(secret_refs: dict[str, str]) -> dict[str, str]:
    return {
        str(name): str(value)
        for name, value in sorted(secret_refs.items())
        if str(name).strip() and str(value).strip()
    }


def _retention_policy(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("deliveryRetention") or config.get("providerDeliveryRetention") or config.get("retentionPolicy")
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if config.get("deliveryRetentionDays") is not None:
        return {"deliveryRetentionDays": config.get("deliveryRetentionDays")}
    return {}


def _safe_provider_diagnostics(diagnostics: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in diagnostics.items():
        lowered = str(key).lower()
        if _is_sensitive_key(lowered):
            safe[str(key)] = "[REDACTED]"
        else:
            safe[str(key)] = _redact_nested(value)
    return safe


def _redact_nested(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, nested in value.items():
            lowered = str(key).lower()
            safe[str(key)] = "[REDACTED]" if _is_sensitive_key(lowered) else _redact_nested(nested)
        return safe
    if isinstance(value, list):
        return [_redact_nested(item) for item in value]
    return value


def _is_sensitive_key(lowered_key: str) -> bool:
    return any(
        secret_word in lowered_key
        for secret_word in ["token", "secret", "authorization", "signature", "password", "key", "credential"]
    )


def _summary(status: str, connector_id: str) -> str:
    if status == "healthy":
        return f"Connector {connector_id} is ready for provider admission."
    if status == "degraded":
        return f"Connector {connector_id} is usable but has readiness warnings."
    if status == "blocked":
        return f"Connector {connector_id} is blocked until health check blockers are resolved."
    return f"Connector {connector_id} readiness is unknown."


def _single_project(projects: list[str]) -> str | None:
    return projects[0] if len(projects) == 1 else None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    if str(value).strip():
        return [str(value).strip()]
    return []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
