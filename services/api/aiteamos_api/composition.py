"""
API Gateway composition root for the file-first 1.0 services.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from .read import (
    asset_graph_routes,
    asset_routes,
    capability_routes,
    chat_agui_routes,
    chat_routes,
    employees_routes,
    knowledge_routes,
    memory_routes,
    repository_routes,
    runtime_executor_routes,
    system_status_routes,
    ticket_routes,
    tool_connector_routes,
)

logger = logging.getLogger(__name__)


def register_routes(app: FastAPI) -> None:
    """Register the file-backed 1.0 API routes."""
    app.include_router(asset_graph_routes.router)
    app.include_router(asset_routes.router)
    app.include_router(capability_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(chat_agui_routes.router)
    app.include_router(employees_routes.router)
    app.include_router(knowledge_routes.router)
    app.include_router(tool_connector_routes.router)
    app.include_router(memory_routes.router)
    app.include_router(repository_routes.router)
    app.include_router(runtime_executor_routes.router)
    app.include_router(system_status_routes.router)
    app.include_router(ticket_routes.router)
    logger.info("Asset graph, assets, capability, chat, chat AG-UI compatibility, employees, knowledge, tool connector, memory, repository, runtime executor, system status, and ticket routes registered")
