"""File-backed MCP connector registry for AITeamOS.

The registry is the Kernel-facing source of truth for connector capabilities.
Actual MCP client/server protocol integration can be attached behind these
entries without making Clara or the dashboard depend on provider-specific
configuration shapes.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_LEGACY_UNCONFIGURED_CONNECTORS = {"redmine", "ticket", "confluence"}


class McpConnector(BaseModel):
    id: str
    name: str
    status: str = "planned"
    transport: str = "mcp"
    enabled: bool = False
    configured: bool = False
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    required_settings: list[str] = Field(default_factory=list)
    server: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = ""


class McpConnectorUpdateRequest(BaseModel):
    status: str | None = None
    transport: str | None = None
    enabled: bool | None = None
    configured: bool | None = None
    description: str | None = None
    capabilities: list[str] | None = None
    permissions: list[str] | None = None
    required_settings: list[str] | None = None
    server: dict[str, Any] | None = None


class McpRegistryStatus(BaseModel):
    connector_count: int
    enabled_count: int
    configured_count: int
    ready_count: int
    saved_paths: dict[str, str] = Field(default_factory=dict)


class McpConnectorSettingsResponse(BaseModel):
    connector_id: str
    enabled: bool = False
    configured: bool = False
    base_url: str = ""
    email: str = ""
    space_key: str = ""
    workspace_slug: str = ""
    project_id: str = ""
    api_token_configured: bool = False
    saved_paths: dict[str, str] = Field(default_factory=dict)
    connector: McpConnector


class McpConnectorSettingsUpdateRequest(BaseModel):
    enabled: bool = True
    base_url: str = ""
    email: str = ""
    space_key: str = ""
    workspace_slug: str = ""
    project_id: str = ""
    api_token: str | None = None


class McpConnectorHealthResponse(BaseModel):
    connector_id: str
    status: str
    detail: str
    checked_at: str
    configured: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _registry_path() -> Path:
    return _workspace_dir() / "mcp_connectors.json"


def _connectors_dir() -> Path:
    path = _workspace_dir() / "connectors"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _connector_settings_path(connector_id: str) -> Path:
    return _connectors_dir() / f"{connector_id}.json"


def _secrets_path() -> Path:
    return _workspace_dir() / "secrets.local.json"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


def _default_connectors() -> list[McpConnector]:
    timestamp = _now()
    return [
        McpConnector(
            id="plane",
            name="Plane",
            status="planned",
            transport="rest",
            description=(
                "Selected default Ticket/Docs backend for AITeamOS; "
                "Plane tickets map to Tickets and Plane pages map to Docs."
            ),
            capabilities=[
                "tickets.search",
                "tickets.create",
                "tickets.update",
                "tickets.transition",
                "tickets.comment",
                "tickets.relate",
                "knowledge.docs.search",
                "knowledge.docs.read",
                "knowledge.docs.write",
            ],
            permissions=["tickets:read", "tickets:write", "docs:read", "docs:write"],
            required_settings=["base_url", "api_token", "workspace_slug"],
            updated_at=timestamp,
        ),
        McpConnector(
            id="github",
            name="GitHub",
            status="planned",
            description="Repository, pull request, and issue connector.",
            capabilities=["repo.search", "pull_requests.read", "issues.read"],
            permissions=["repo:read"],
            required_settings=["owner", "repo", "token"],
            updated_at=timestamp,
        ),
        McpConnector(
            id="filesystem",
            name="Filesystem",
            status="local",
            transport="local",
            enabled=True,
            configured=True,
            description="Scoped local resources already used by Knowledge and file-backed P0 data.",
            capabilities=["knowledge.docs.local_read", "knowledge.memory.local_mirror", "runtime.files.local_state"],
            permissions=["local:read"],
            updated_at=timestamp,
        ),
        McpConnector(
            id="ci-harness",
            name="CI / Harness",
            status="planned",
            description="Validation evidence and test execution connector.",
            capabilities=["validation.run", "validation.report", "harness.logs.read"],
            permissions=["ci:read", "ci:execute"],
            required_settings=["base_url", "token"],
            updated_at=timestamp,
        ),
    ]


def _connector_index(connectors: list[McpConnector]) -> dict[str, McpConnector]:
    return {connector.id: connector for connector in connectors}


def _save_connectors(connectors: list[McpConnector]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [connector.model_dump(mode="json") for connector in sorted(connectors, key=lambda item: item.id)]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_connectors() -> list[McpConnector]:
    defaults = _connector_index(_default_connectors())
    path = _registry_path()
    if not path.exists():
        connectors = list(defaults.values())
        _save_connectors(connectors)
        return connectors

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = []
    rows = data if isinstance(data, list) else []
    merged = defaults
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            connector = McpConnector.model_validate(row)
        except ValueError:
            continue
        if connector.id in _LEGACY_UNCONFIGURED_CONNECTORS and not connector.enabled and not connector.configured:
            continue
        merged[connector.id] = connector
    connectors = list(merged.values())
    _save_connectors(connectors)
    return connectors


def _require_connector_id(connector_id: str) -> str:
    normalized = connector_id.strip().lower()
    if not _SAFE_ID_RE.fullmatch(normalized):
        raise KeyError(connector_id)
    return normalized


def list_mcp_connectors() -> list[McpConnector]:
    return sorted(_load_connectors(), key=lambda item: item.id)


def mcp_registry_status() -> McpRegistryStatus:
    connectors = list_mcp_connectors()
    return McpRegistryStatus(
        connector_count=len(connectors),
        enabled_count=sum(1 for connector in connectors if connector.enabled),
        configured_count=sum(1 for connector in connectors if connector.configured),
        ready_count=sum(1 for connector in connectors if connector.enabled and connector.configured),
        saved_paths={"registry": _relative(_registry_path())},
    )


def update_mcp_connector(connector_id: str, request: McpConnectorUpdateRequest) -> McpConnector:
    normalized = _require_connector_id(connector_id)
    connectors = list_mcp_connectors()
    index = _connector_index(connectors)
    if normalized not in index:
        raise KeyError(connector_id)

    connector = index[normalized]
    update = request.model_dump(exclude_none=True)
    if "server" in update:
        server = dict(update["server"])
        for secret_key in ("api_key", "api_token", "token", "password"):
            if secret_key in server:
                server[secret_key] = "***"
        update["server"] = server
    connector = connector.model_copy(update={**update, "updated_at": _now()})
    index[normalized] = connector
    _save_connectors(list(index.values()))
    return connector


def _connector_by_id(connector_id: str) -> McpConnector:
    normalized = _require_connector_id(connector_id)
    for connector in list_mcp_connectors():
        if connector.id == normalized:
            return connector
    raise KeyError(connector_id)


def _connector_secret_key(connector_id: str, name: str) -> str:
    return f"connector_{connector_id}_{name}"


def _connector_configured(connector_id: str, settings: dict[str, Any], secrets: dict[str, Any]) -> bool:
    if connector_id == "plane":
        return bool(settings.get("base_url") and secrets.get(_connector_secret_key(connector_id, "api_token")))
    return bool(settings)


def mcp_connector_settings(connector_id: str) -> McpConnectorSettingsResponse:
    connector = _connector_by_id(connector_id)
    settings = _read_json_object(_connector_settings_path(connector.id))
    secrets = _read_json_object(_secrets_path())
    return McpConnectorSettingsResponse(
        connector_id=connector.id,
        enabled=bool(settings.get("enabled", connector.enabled)),
        configured=_connector_configured(connector.id, settings, secrets),
        base_url=str(settings.get("base_url") or ""),
        email=str(settings.get("email") or ""),
        space_key=str(settings.get("space_key") or ""),
        workspace_slug=str(settings.get("workspace_slug") or ""),
        project_id=str(settings.get("project_id") or ""),
        api_token_configured=bool(secrets.get(_connector_secret_key(connector.id, "api_token"))),
        saved_paths={
            "settings": _relative(_connector_settings_path(connector.id)),
            "secrets": _relative(_secrets_path()),
        },
        connector=connector,
    )


def update_mcp_connector_settings(
    connector_id: str,
    request: McpConnectorSettingsUpdateRequest,
) -> McpConnectorSettingsResponse:
    connector = _connector_by_id(connector_id)
    if connector.id != "plane":
        raise ValueError(f"Settings form is not implemented for connector: {connector.id}")

    settings = {
        "enabled": request.enabled,
        "base_url": request.base_url.strip().rstrip("/"),
        "workspace_slug": request.workspace_slug.strip(),
        "project_id": request.project_id.strip(),
        "updated_at": _now(),
    }
    _write_json_object(_connector_settings_path(connector.id), settings)

    secrets = _read_json_object(_secrets_path())
    if request.api_token is not None and request.api_token.strip():
        secrets[_connector_secret_key(connector.id, "api_token")] = request.api_token.strip()
    if secrets:
        _write_json_object(_secrets_path(), secrets)

    configured = _connector_configured(connector.id, settings, secrets)
    updated_connector = connector.model_copy(
        update={
            "enabled": request.enabled,
            "configured": configured,
            "status": "configured" if configured else "missing",
            "transport": "rest",
            "updated_at": _now(),
        }
    )
    index = _connector_index(list_mcp_connectors())
    index[connector.id] = updated_connector
    _save_connectors(list(index.values()))
    return mcp_connector_settings(connector.id)


def _plane_headers(settings: McpConnectorSettingsResponse) -> dict[str, str]:
    secrets = _read_json_object(_secrets_path())
    token = str(secrets.get(_connector_secret_key(settings.connector_id, "api_token")) or "")
    return {"Accept": "application/json", "X-API-Key": token}


def _plane_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _require_plane_settings() -> McpConnectorSettingsResponse:
    settings = mcp_connector_settings("plane")
    if not settings.enabled or not settings.configured:
        raise ValueError("Plane connector is not enabled or configured.")
    return settings


def check_plane_health() -> McpConnectorHealthResponse:
    settings = mcp_connector_settings("plane")
    if not settings.enabled:
        return McpConnectorHealthResponse(
            connector_id="plane",
            status="disabled",
            detail="Plane connector is disabled.",
            checked_at=_now(),
            configured=settings.configured,
        )
    if not settings.configured:
        return McpConnectorHealthResponse(
            connector_id="plane",
            status="missing",
            detail="Set Plane API base URL and API key in Settings / MCP Connectors.",
            checked_at=_now(),
            configured=False,
        )

    with httpx.Client(timeout=10.0) as client:
        response = client.get(
            _plane_url(settings.base_url, "/api/v1/users/me/"),
            headers=_plane_headers(settings),
        )
        response.raise_for_status()
        payload = response.json()

    user = payload if isinstance(payload, dict) else {}
    return McpConnectorHealthResponse(
        connector_id="plane",
        status="ready",
        detail="Plane API is reachable with the configured API key.",
        checked_at=_now(),
        configured=True,
        data={
            "base_url": settings.base_url,
            "workspace_slug": settings.workspace_slug,
            "user": {
                "id": user.get("id"),
                "email": user.get("email"),
                "display_name": user.get("display_name"),
            },
        },
    )
