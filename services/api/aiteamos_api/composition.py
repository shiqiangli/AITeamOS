"""
API Gateway — Composition Root (simplified for file-first P0).

Only wires the file-backed Member Chat Workbench routes.
All DDD bounded contexts have been removed per PRODUCT_DIRECTION.md.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .read import capability_routes, chat_routes, knowledge_routes, mcp_routes, memory_routes, repository_routes, work_item_routes

logger = logging.getLogger(__name__)


def register_routes(app: FastAPI) -> None:
    """Register the file-backed P0 API routes."""
    app.include_router(capability_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(knowledge_routes.router)
    app.include_router(mcp_routes.router)
    app.include_router(memory_routes.router)
    app.include_router(repository_routes.router)
    app.include_router(work_item_routes.router)
    logger.info("Capability, chat, knowledge, MCP, memory, repository, and work item routes registered")
