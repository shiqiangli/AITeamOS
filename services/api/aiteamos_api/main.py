"""
AITeamOS API Gateway — FastAPI Application Entry Point (plan.md §1.5).

统一 API 入口，CQRS 读写分离路由，认证中间件。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aiteamos_shared.repository import create_pool

from .composition import ServiceContainer, build_container, build_recall_and_assembler, register_routes
from .middleware.error_handler import register_error_handlers

logger = logging.getLogger(__name__)

_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _resolve_cors_origins() -> list[str]:
    """Resolve CORS origins from environment.

    AITEAMOS_ENV=development  → allow all (*)
    AITEAMOS_CORS_ORIGINS     → comma-separated explicit list
    default                   → localhost dev origins
    """
    env = os.environ.get("AITEAMOS_ENV", "")
    if env == "development":
        return ["*"]
    explicit = os.environ.get("AITEAMOS_CORS_ORIGINS", "")
    if explicit:
        return [o.strip() for o in explicit.split(",") if o.strip()]
    return _DEV_ORIGINS


def _make_lifespan(container: ServiceContainer):
    """Create a lifespan context manager for production startup.

    Connects to PostgreSQL, wires all repos/handlers/executors into the
    container, and registers routes — all *before* the server starts
    accepting requests.  On shutdown the DB pool is closed gracefully.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database_url = os.environ.get(
            "AITEAMOS_DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/aiteamos",
        )
        try:
            db = await create_pool(database_url)
            app.state.db = db

            # Wire all repos, publishers, handlers, executors
            build_container(container, db)

            # Wire recall engine + context assembler
            execution_pub = container.get("execution_event_publisher")
            build_recall_and_assembler(
                container, db=db, tx_manager=db, event_publisher=execution_pub,
            )

            # Register routes after the container is fully populated
            register_routes(app, container)

            logger.info("AITeamOS API started — database connected")
        except (OSError, ConnectionError) as exc:
            logger.error(
                "AITeamOS API started WITHOUT database — %s", exc,
            )
            app.state.db = None
            # Register routes anyway; handlers will be None → 503 on data endpoints
            register_routes(app, container)

        yield

        # Shutdown
        db = getattr(app.state, "db", None)
        if db is not None:
            await db.close()
            logger.info("Database pool closed")

    return lifespan


def create_app(container: ServiceContainer | None = None) -> FastAPI:
    """FastAPI application factory.

    Args:
        container: Optional pre-configured ServiceContainer (for testing).
                   If None, production startup via lifespan is used.
    """
    test_mode = container is not None
    if container is None:
        container = ServiceContainer()

    lifespan = None if test_mode else _make_lifespan(container)

    app = FastAPI(
        title="AITeamOS API",
        description="Experience-driven Cognitive Operating System — REST API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS (plan.md §1.5.4)
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

    # Health check (no auth required)
    @app.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        db = getattr(app.state, "db", None)
        if db is None:
            return {"status": "degraded", "database": "unavailable"}
        return {"status": "ok", "database": "connected"}

    # OpenAPI schema endpoint (no auth required)
    @app.get("/api/v1/openapi.json", tags=["system"], include_in_schema=False)
    async def get_openapi_schema() -> dict:
        return app.openapi()

    # In test mode, routes are registered immediately with the provided container.
    # In production, routes are registered inside the lifespan after DB is ready.
    if test_mode:
        register_routes(app, container)

    logger.info("AITeamOS API application created")
    return app


# Default app instance for `uvicorn aiteamos_api.main:app`
app = create_app()
