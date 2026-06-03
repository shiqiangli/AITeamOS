"""
API Gateway — Composition Root (simplified for file-first P0).

Only wires the file-backed Member Chat Workbench routes.
All DDD bounded contexts have been removed per PRODUCT_DIRECTION.md.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .read import chat_routes

logger = logging.getLogger(__name__)


def register_routes(app: FastAPI) -> None:
    """Register the file-backed P0 API routes."""
    app.include_router(chat_routes.router)
    logger.info("Chat routes registered")
