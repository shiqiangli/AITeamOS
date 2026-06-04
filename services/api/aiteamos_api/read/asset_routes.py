"""All Assets routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from .knowledge_service import AssetRecord, asset_items

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


@router.get("", response_model=list[AssetRecord])
async def get_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(query=q)


@router.get("/all", response_model=list[AssetRecord])
async def get_all_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(query=q)


@router.get("/search", response_model=list[AssetRecord])
async def search_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(query=q)


@router.get("/knowledge", response_model=list[AssetRecord])
async def get_knowledge_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="knowledge", query=q)


@router.get("/knowledge/docs", response_model=list[AssetRecord])
async def get_doc_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="knowledge", asset_type="docs", query=q)


@router.get("/knowledge/memories", response_model=list[AssetRecord])
async def get_memory_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="knowledge", asset_type="memories", query=q)


@router.get("/knowledge/decisions", response_model=list[AssetRecord])
async def get_decision_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="knowledge", asset_type="decisions", query=q)


@router.get("/capabilities", response_model=list[AssetRecord])
async def get_capability_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="capabilities", query=q)


@router.get("/capabilities/skills", response_model=list[AssetRecord])
async def get_skill_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="capabilities", asset_type="skills", query=q)


@router.get("/capabilities/built-in-tools", response_model=list[AssetRecord])
async def get_built_in_tool_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="capabilities", asset_type="built-in-tools", query=q)


@router.get("/capabilities/mcp-tools", response_model=list[AssetRecord])
async def get_mcp_tool_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="capabilities", asset_type="mcp-tools", query=q)


@router.get("/review", response_model=list[AssetRecord])
async def get_review_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="review", query=q)


@router.get("/review/memories", response_model=list[AssetRecord])
async def get_memory_review_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="review", asset_type="memories", query=q)


@router.get("/review/decisions", response_model=list[AssetRecord])
async def get_decision_review_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="review", asset_type="decisions", query=q)


@router.get("/review/skills", response_model=list[AssetRecord])
async def get_skill_review_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="review", asset_type="skills", query=q)


@router.get("/review/tools", response_model=list[AssetRecord])
async def get_tool_review_assets(q: str = Query("", alias="q")) -> list[AssetRecord]:
    return asset_items(domain="review", asset_type="tools", query=q)
