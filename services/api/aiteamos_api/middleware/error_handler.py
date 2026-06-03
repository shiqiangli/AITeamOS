"""
API Gateway — Error Handler (file-first P0).

Unified error response format for the file-backed API.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Business error base class."""

    def __init__(self, *, status_code: int = 400, detail: str = "", code: str = "BAD_REQUEST"):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)


class NotFoundError(ApiError):
    def __init__(self, *, detail: str = "Resource not found"):
        super().__init__(status_code=404, detail=detail, code="NOT_FOUND")


class ConflictError(ApiError):
    def __init__(self, *, detail: str = "Resource conflict"):
        super().__init__(status_code=409, detail=detail, code="CONFLICT")


class InvariantViolationApiError(ApiError):
    """Domain invariant violation → 422."""

    def __init__(self, *, detail: str = "Invariant violation"):
        super().__init__(status_code=422, detail=detail, code="INVARIANT_VIOLATION")


def _error_response(status_code: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "detail": detail}},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register global error handlers."""

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        detail = str(exc)
        if detail.startswith("[I-"):
            return _error_response(422, "INVARIANT_VIOLATION", detail)
        return _error_response(400, "BAD_REQUEST", detail)

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, ApiError):
            return _error_response(exc.status_code, exc.code, exc.detail)
        logger.exception("Unhandled exception: %s", exc)
        return _error_response(500, "INTERNAL_ERROR", "Internal server error")
