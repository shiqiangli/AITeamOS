"""
AITeamOS API Gateway — FastAPI Application Entry Point (file-first 1.0).

The API runs against local .aiteamos files for Chat, Tickets, Employees,
Assets, Settings, Memory, and System Status.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .composition import register_routes
from .middleware.error_handler import register_error_handlers

logger = logging.getLogger(__name__)

_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _resolve_cors_origins() -> list[str]:
    env = os.environ.get("AITEAMOS_ENV", "")
    if env == "development":
        return ["*"]
    explicit = os.environ.get("AITEAMOS_CORS_ORIGINS", "")
    if explicit:
        return [o.strip() for o in explicit.split(",") if o.strip()]
    return _DEV_ORIGINS


def create_app() -> FastAPI:
    """FastAPI application factory for the file-first 1.0 service."""

    app = FastAPI(
        title="AITeamOS API",
        description="AITeamOS — file-backed AI-team operating system REST API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS
    origins = _resolve_cors_origins()
    has_wildcard = "*" in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=not has_wildcard,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers
    register_error_handlers(app)

    # Health check
    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "mode": "file-first"}

    # OpenAPI schema
    @app.get("/api/v1/openapi.json", tags=["system"], include_in_schema=False)
    async def get_openapi_schema() -> dict:
        return app.openapi()

    # Register routes
    register_routes(app)

    logger.info("AITeamOS API application created (file-first mode)")
    return app


# Default app instance for `uvicorn aiteamos_api.main:app`
app = create_app()
