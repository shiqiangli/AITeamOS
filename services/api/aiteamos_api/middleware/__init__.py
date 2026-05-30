"""API Gateway — Middleware."""

from .auth import AuthContext, get_current_user, require_admin
from .error_handler import (
    ApiError,
    ConflictError,
    InvariantViolationApiError,
    NotFoundError,
    register_error_handlers,
)