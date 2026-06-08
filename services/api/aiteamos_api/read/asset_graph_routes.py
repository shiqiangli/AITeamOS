"""Asset graph status routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .ticket_service import AssetGraphStatus, asset_graph_status

router = APIRouter(prefix="/api/v1/asset-graph", tags=["asset-graph"])


@router.get("/status", response_model=AssetGraphStatus)
async def get_asset_graph_status() -> AssetGraphStatus:
    try:
        return asset_graph_status()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
