"""File-backed Tool Connector registry for AITeamOS.

The registry is the Kernel-facing source of truth for connector capabilities.
Actual MCP client/server protocol integration can be attached behind these
entries without making Clara or the dashboard depend on source-specific
configuration shapes.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class ToolConnector(BaseModel):
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


class ToolConnectorUpdateRequest(BaseModel):
    status: str | None = None
    transport: str | None = None
    enabled: bool | None = None
    configured: bool | None = None
    description: str | None = None
    capabilities: list[str] | None = None
    permissions: list[str] | None = None
    required_settings: list[str] | None = None
    server: dict[str, Any] | None = None


class ToolConnectorRegistryStatus(BaseModel):
    connector_count: int
    enabled_count: int
    configured_count: int
    ready_count: int
    saved_paths: dict[str, str] = Field(default_factory=dict)


class ToolConnectorSettingsResponse(BaseModel):
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
    connector: ToolConnector


class ToolConnectorSettingsUpdateRequest(BaseModel):
    enabled: bool = True
    base_url: str = ""
    email: str = ""
    space_key: str = ""
    workspace_slug: str = ""
    project_id: str = ""


class ToolConnectorHealthResponse(BaseModel):
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
    return _workspace_dir() / "tool_connectors.json"


def _connectors_dir() -> Path:
    path = _workspace_dir() / "connectors"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _connector_settings_path(connector_id: str) -> Path:
    return _connectors_dir() / f"{connector_id}.json"


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_workspace_root()))
    except ValueError:
        return str(path)


def _default_connectors() -> list[ToolConnector]:
    timestamp = _now()
    return [
        ToolConnector(
            id="mcp-server",
            name="MCP Server",
            status="planned",
            transport="mcp",
            description=(
                "Generic MCP server entry point. Configure a server command or URL, "
                "then discovered tools are projected into Assets / Capabilities / MCP Tools."
            ),
            capabilities=[],
            permissions=[],
            required_settings=["server_command_or_url"],
            updated_at=timestamp,
        ),
        ToolConnector(
            id="github",
            name="GitHub",
            status="planned",
            description="Repository, pull request, and issue connector.",
            capabilities=["repo.search", "pull_requests.read", "issues.read"],
            permissions=["repo:read"],
            required_settings=["owner", "repo"],
            updated_at=timestamp,
        ),
        ToolConnector(
            id="ci-harness",
            name="CI / Harness",
            status="planned",
            description="Validation evidence and test execution connector.",
            capabilities=["validation.run", "validation.report", "harness.logs.read"],
            permissions=["ci:read", "ci:execute"],
            required_settings=["base_url"],
            updated_at=timestamp,
        ),
    ]


def _connector_index(connectors: list[ToolConnector]) -> dict[str, ToolConnector]:
    return {connector.id: connector for connector in connectors}


def _save_connectors(connectors: list[ToolConnector]) -> None:
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


def _load_connectors() -> list[ToolConnector]:
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
            connector = ToolConnector.model_validate(row)
        except ValueError:
            continue
        if connector.id not in defaults:
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


def list_tool_connectors() -> list[ToolConnector]:
    return sorted(_load_connectors(), key=lambda item: item.id)


def tool_connector_registry_status() -> ToolConnectorRegistryStatus:
    connectors = list_tool_connectors()
    return ToolConnectorRegistryStatus(
        connector_count=len(connectors),
        enabled_count=sum(1 for connector in connectors if connector.enabled),
        configured_count=sum(1 for connector in connectors if connector.configured),
        ready_count=sum(1 for connector in connectors if connector.enabled and connector.configured),
        saved_paths={"registry": _relative(_registry_path())},
    )


def update_tool_connector(connector_id: str, request: ToolConnectorUpdateRequest) -> ToolConnector:
    normalized = _require_connector_id(connector_id)
    connectors = list_tool_connectors()
    index = _connector_index(connectors)
    if normalized not in index:
        raise KeyError(connector_id)

    connector = index[normalized]
    update = request.model_dump(exclude_none=True)
    if "server" in update:
        server = dict(update["server"])
        for secret_key in ("api_key", "api_token", "token", "password"):
            server.pop(secret_key, None)
        update["server"] = server
    connector = connector.model_copy(update={**update, "updated_at": _now()})
    index[normalized] = connector
    _save_connectors(list(index.values()))
    return connector


def _connector_by_id(connector_id: str) -> ToolConnector:
    normalized = _require_connector_id(connector_id)
    for connector in list_tool_connectors():
        if connector.id == normalized:
            return connector
    raise KeyError(connector_id)


def _connector_secret_env(connector_id: str, name: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", connector_id.upper()).strip("_")
    return f"AITEAMOS_{normalized}_{name.upper()}"


def _connector_secret_configured(connector_id: str, name: str) -> bool:
    return bool(os.environ.get(_connector_secret_env(connector_id, name)))


def _connector_configured(connector_id: str, settings: dict[str, Any]) -> bool:
    return bool(settings)


def tool_connector_settings(connector_id: str) -> ToolConnectorSettingsResponse:
    connector = _connector_by_id(connector_id)
    settings = _read_json_object(_connector_settings_path(connector.id))
    return ToolConnectorSettingsResponse(
        connector_id=connector.id,
        enabled=bool(settings.get("enabled", connector.enabled)),
        configured=_connector_configured(connector.id, settings),
        base_url=str(settings.get("base_url") or ""),
        email=str(settings.get("email") or ""),
        space_key=str(settings.get("space_key") or ""),
        workspace_slug=str(settings.get("workspace_slug") or ""),
        project_id=str(settings.get("project_id") or ""),
        api_token_configured=_connector_secret_configured(connector.id, "api_token"),
        saved_paths={
            "settings": _relative(_connector_settings_path(connector.id)),
        },
        connector=connector,
    )


def update_tool_connector_settings(
    connector_id: str,
    request: ToolConnectorSettingsUpdateRequest,
) -> ToolConnectorSettingsResponse:
    connector = _connector_by_id(connector_id)
    settings = {
        "enabled": request.enabled,
        "base_url": request.base_url.strip().rstrip("/"),
        "email": request.email.strip(),
        "space_key": request.space_key.strip(),
        "workspace_slug": request.workspace_slug.strip(),
        "project_id": request.project_id.strip(),
        "updated_at": _now(),
    }
    _write_json_object(_connector_settings_path(connector.id), settings)

    configured = _connector_configured(connector.id, settings)
    updated_connector = connector.model_copy(
        update={
            "enabled": request.enabled,
            "configured": configured,
            "status": "configured" if configured else "missing",
            "updated_at": _now(),
        }
    )
    index = _connector_index(list_tool_connectors())
    index[connector.id] = updated_connector
    _save_connectors(list(index.values()))
    return tool_connector_settings(connector.id)


def check_tool_connector_health(connector_id: str) -> ToolConnectorHealthResponse:
    settings = tool_connector_settings(connector_id)
    if not settings.enabled:
        return ToolConnectorHealthResponse(
            connector_id=settings.connector_id,
            status="disabled",
            detail=f"{settings.connector.name} connector is disabled.",
            checked_at=_now(),
            configured=settings.configured,
        )
    if not settings.configured:
        return ToolConnectorHealthResponse(
            connector_id=settings.connector_id,
            status="missing",
            detail=f"{settings.connector.name} connector is enabled but not configured.",
            checked_at=_now(),
            configured=False,
        )
    return ToolConnectorHealthResponse(
        connector_id=settings.connector_id,
        status="ready",
        detail=f"{settings.connector.name} connector has local settings. Adapter-level health checks are not attached yet.",
        checked_at=_now(),
        configured=True,
        data={
            "base_url": settings.base_url,
            "workspace_slug": settings.workspace_slug,
            "transport": settings.connector.transport,
        },
    )
