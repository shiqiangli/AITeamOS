"""
API Gateway — Error Handler (plan.md §1.5.4).

统一异常响应格式，保证 API 返回结构一致。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# Domain exceptions
from aiteamos_knowledge.domain.exceptions import (
    MemoryConflictError,
    MemoryInvariantError,
    MemoryNotFoundError,
)
from aiteamos_capability.domain.exceptions import (
    SkillCircuitOpenError,
    SkillInvariantError,
    SkillNotFoundError,
)
from aiteamos_workforce.domain.exceptions import (
    ConcurrencyLimitError,
    DepartmentNotFoundError,
    MemberNotFoundError,
)
from aiteamos_execution.domain.exceptions import (
    InvalidStateTransition,
    TaskDependencyError,
    TaskNotFoundError,
)

# Governance exceptions
from aiteamos_governance.domain.exceptions import (
    ReviewAlreadyDecided,
    ReviewNotFoundError,
)

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """业务异常基类。"""

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


# Domain exception → (status_code, error_code) mapping
_NOT_FOUND_EXCEPTIONS = (
    MemoryNotFoundError,
    SkillNotFoundError,
    MemberNotFoundError,
    DepartmentNotFoundError,
    TaskNotFoundError,
    ReviewNotFoundError,
)
_INVARIANT_EXCEPTIONS = (
    MemoryInvariantError,
    SkillInvariantError,
    InvalidStateTransition,
)
_CONFLICT_EXCEPTIONS = (
    MemoryConflictError,
    ConcurrencyLimitError,
    TaskDependencyError,
    SkillCircuitOpenError,
    ReviewAlreadyDecided,
)


def register_error_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.status_code, exc.code, exc.detail)

    # Domain exception handlers
    for exc_cls in _NOT_FOUND_EXCEPTIONS:
        app.add_exception_handler(exc_cls, _make_not_found_handler(exc_cls))

    for exc_cls in _INVARIANT_EXCEPTIONS:
        app.add_exception_handler(exc_cls, _make_invariant_handler(exc_cls))

    for exc_cls in _CONFLICT_EXCEPTIONS:
        app.add_exception_handler(exc_cls, _make_conflict_handler(exc_cls))

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


def _make_not_found_handler(exc_cls: type):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(404, "NOT_FOUND", str(exc))
    return handler


def _make_invariant_handler(exc_cls: type):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(422, "INVARIANT_VIOLATION", str(exc))
    return handler


def _make_conflict_handler(exc_cls: type):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(409, "CONFLICT", str(exc))
    return handler
