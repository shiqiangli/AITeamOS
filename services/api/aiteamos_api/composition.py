"""
API Gateway — Composition Root (simplified for file-first P0).

Only wires the file-backed Employee Chat Workbench routes.
All DDD bounded contexts have been removed per PRODUCT_DIRECTION.md.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .read import (
    asset_routes,
    capability_routes,
    chat_routes,
    knowledge_routes,
    memory_routes,
    repository_routes,
    settings_routes,
    ticket_routes,
    tool_connector_routes,
)

logger = logging.getLogger(__name__)


def register_routes(app: FastAPI) -> None:
    """Register the file-backed P0 API routes."""
    app.include_router(asset_routes.router)
    app.include_router(capability_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(knowledge_routes.router)
    app.include_router(tool_connector_routes.router)
    app.include_router(memory_routes.router)
    app.include_router(repository_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(ticket_routes.router)
    logger.info("Assets, capability, chat, knowledge, tool connector, memory, repository, settings, and ticket routes registered")
