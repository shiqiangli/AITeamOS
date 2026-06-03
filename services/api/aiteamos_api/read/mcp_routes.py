"""MCP connector registry routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from httpx import HTTPStatusError, RequestError

from .mcp_service import (
    McpConnectorHealthResponse,
    McpConnector,
    McpConnectorSettingsResponse,
    McpConnectorSettingsUpdateRequest,
    McpConnectorUpdateRequest,
    McpRegistryStatus,
    check_plane_health,
    list_mcp_connectors,
    mcp_connector_settings,
    mcp_registry_status,
    update_mcp_connector,
    update_mcp_connector_settings,
)

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


@router.get("/status", response_model=McpRegistryStatus)
async def get_mcp_status() -> McpRegistryStatus:
    return mcp_registry_status()


@router.get("/connectors", response_model=list[McpConnector])
async def get_mcp_connectors() -> list[McpConnector]:
    return list_mcp_connectors()


@router.put("/connectors/{connector_id}", response_model=McpConnector)
async def put_mcp_connector(
    connector_id: str,
    request: McpConnectorUpdateRequest,
) -> McpConnector:
    try:
        return update_mcp_connector(connector_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"MCP connector not found: {connector_id}") from exc


@router.get("/connectors/{connector_id}/settings", response_model=McpConnectorSettingsResponse)
async def get_mcp_connector_settings(connector_id: str) -> McpConnectorSettingsResponse:
    try:
        return mcp_connector_settings(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"MCP connector not found: {connector_id}") from exc


@router.put("/connectors/{connector_id}/settings", response_model=McpConnectorSettingsResponse)
async def put_mcp_connector_settings(
    connector_id: str,
    request: McpConnectorSettingsUpdateRequest,
) -> McpConnectorSettingsResponse:
    try:
        return update_mcp_connector_settings(connector_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"MCP connector not found: {connector_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/connectors/{connector_id}/health", response_model=McpConnectorHealthResponse)
async def post_mcp_connector_health(connector_id: str) -> McpConnectorHealthResponse:
    try:
        if connector_id == "plane":
            return check_plane_health()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"MCP connector not found: {connector_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text[:500]) from exc
    except RequestError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=f"Health check is not implemented for connector: {connector_id}")
