"""Tool connector routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .tool_connector_service import (
    ToolConnectorHealthResponse,
    ToolConnector,
    ToolConnectorSettingsResponse,
    ToolConnectorSettingsUpdateRequest,
    ToolConnectorUpdateRequest,
    ToolConnectorRegistryStatus,
    check_tool_connector_health,
    list_tool_connectors,
    tool_connector_settings,
    tool_connector_registry_status,
    update_tool_connector,
    update_tool_connector_settings,
)

router = APIRouter(prefix="/api/v1/tool-connectors", tags=["tool-connectors"])


@router.get("/status", response_model=ToolConnectorRegistryStatus)
async def get_tool_connector_status() -> ToolConnectorRegistryStatus:
    return tool_connector_registry_status()


@router.get("/connectors", response_model=list[ToolConnector])
async def get_tool_connectors() -> list[ToolConnector]:
    return list_tool_connectors()


@router.put("/connectors/{connector_id}", response_model=ToolConnector)
async def put_tool_connector(
    connector_id: str,
    request: ToolConnectorUpdateRequest,
) -> ToolConnector:
    try:
        return update_tool_connector(connector_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Tool connector not found: {connector_id}") from exc


@router.get("/connectors/{connector_id}/settings", response_model=ToolConnectorSettingsResponse)
async def get_tool_connector_settings(connector_id: str) -> ToolConnectorSettingsResponse:
    try:
        return tool_connector_settings(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Tool connector not found: {connector_id}") from exc


@router.put("/connectors/{connector_id}/settings", response_model=ToolConnectorSettingsResponse)
async def put_tool_connector_settings(
    connector_id: str,
    request: ToolConnectorSettingsUpdateRequest,
) -> ToolConnectorSettingsResponse:
    try:
        return update_tool_connector_settings(connector_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Tool connector not found: {connector_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/connectors/{connector_id}/health", response_model=ToolConnectorHealthResponse)
async def post_tool_connector_health(connector_id: str) -> ToolConnectorHealthResponse:
    try:
        return check_tool_connector_health(connector_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Tool connector not found: {connector_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
