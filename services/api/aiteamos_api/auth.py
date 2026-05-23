from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hmac
import json
import os


API_TOKEN_ENV = "AITEAMOS_API_TOKEN"
MCP_READ_TOKEN_ENV = "AITEAMOS_MCP_READ_TOKEN"
MCP_WRITE_TOKEN_ENV = "AITEAMOS_MCP_WRITE_TOKEN"
VIEWER_TOKEN_MAP_ENV = "AITEAMOS_VIEWER_TOKEN_MAP"

_MCP_READ_TOOL_PREFIXES = (
    "/mcp/tools/get_task/",
    "/mcp/tools/get_context_capsule/",
    "/mcp/tools/get_member/",
    "/mcp/tools/get_project/",
    "/mcp/tools/list_project_members/",
    "/mcp/tools/list_member_projects/",
)
_MCP_READ_TOOL_PATHS = (
    "/mcp/tools/search_docs",
    "/mcp/tools/search_memory",
    "/mcp/tools/get_member_memory",
    "/mcp/tools/get_project_memory",
    "/mcp/tools/list_assignments",
    "/mcp/tools/explain_permissions",
    "/mcp/tools/suggest_retrospectives",
)
_MCP_READ_TOOL_NAMES = frozenset(
    {
        "search_docs",
        "search_memory",
        "get_member",
        "get_project",
        "list_project_members",
        "list_member_projects",
        "get_member_memory",
        "get_project_memory",
        "list_assignments",
        "explain_permissions",
        "suggest_retrospectives",
        "get_task",
        "get_context_capsule",
    }
)


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    status_code: int = 200
    detail: str = "authorized"
    scope: str = "public"
    accepted_token_envs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductUserTokenBinding:
    product_user: str
    member: str | None
    token_env: str


def authorize_request(
    method: str,
    path: str,
    authorization_header: str | None,
    environ: Mapping[str, str] | None = None,
    extra_api_token_envs: tuple[str, ...] = (),
) -> AuthDecision:
    env = os.environ if environ is None else environ
    route_scope = classify_route(method, path)
    if route_scope == "public":
        return AuthDecision(allowed=True)

    return authorize_scope(route_scope, authorization_header, env, extra_api_token_envs=extra_api_token_envs)


def authorize_mcp_tool(
    tool_name: str,
    authorization_header: str | None,
    environ: Mapping[str, str] | None = None,
) -> AuthDecision:
    scope = classify_mcp_tool_scope(tool_name)
    env = os.environ if environ is None else environ
    return authorize_scope(scope, authorization_header, env)


def authorize_scope(
    route_scope: str,
    authorization_header: str | None,
    environ: Mapping[str, str] | None = None,
    extra_api_token_envs: tuple[str, ...] = (),
) -> AuthDecision:
    env = os.environ if environ is None else environ
    accepted_envs = _accepted_token_envs(route_scope, env, extra_api_token_envs)
    configured_accepted_envs = tuple(name for name in accepted_envs if _env_value(env, name))
    protection_envs = _protection_envs(route_scope, extra_api_token_envs)
    configured_protection_envs = tuple(name for name in protection_envs if _env_value(env, name))

    if not configured_protection_envs:
        return AuthDecision(allowed=True, scope=route_scope, accepted_token_envs=accepted_envs)

    if not configured_accepted_envs:
        return AuthDecision(
            allowed=False,
            status_code=403,
            detail=f"{route_scope} requires a token configured by one of: {', '.join(accepted_envs)}",
            scope=route_scope,
            accepted_token_envs=accepted_envs,
        )

    provided = _bearer_token(authorization_header)
    if provided and (
        _matches_any_token(provided, env, configured_accepted_envs)
        or (route_scope == "api" and viewer_member_from_authorization(authorization_header, env))
    ):
        return AuthDecision(allowed=True, scope=route_scope, accepted_token_envs=accepted_envs)

    return AuthDecision(
        allowed=False,
        status_code=401,
        detail=f"invalid or missing bearer token for {route_scope}; accepted token env names: {', '.join(accepted_envs)}",
        scope=route_scope,
        accepted_token_envs=accepted_envs,
    )


def classify_route(method: str, path: str) -> str:
    normalized = _normalize_path(path)
    if normalized in {"/session/login", "/session/logout", "/session/renew"}:
        return "public"
    if normalized == "/session":
        return "api"
    workspace_scoped = _workspace_scoped_path(normalized)
    if workspace_scoped is not None:
        normalized = workspace_scoped
    if normalized == "/mcp":
        return "mcp-read"
    if normalized.startswith("/mcp/tools/"):
        if method.upper() == "GET" and (
            normalized in _MCP_READ_TOOL_PATHS
            or any(normalized.startswith(prefix) for prefix in _MCP_READ_TOOL_PREFIXES)
        ):
            return "mcp-read"
        return "mcp-write"
    if normalized == "/workspaces" or workspace_scoped is not None:
        return "api"
    return "public"


def classify_mcp_tool_scope(tool_name: str) -> str:
    if tool_name in _MCP_READ_TOOL_NAMES:
        return "mcp-read"
    return "mcp-write"


def viewer_member_from_authorization(
    authorization_header: str | None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    env = os.environ if environ is None else environ
    provided = _bearer_token(authorization_header)
    if not provided:
        return None
    for member, token in _viewer_token_map(env).items():
        if hmac.compare_digest(provided, token):
            return member
    return None


def api_token_from_authorization(
    authorization_header: str | None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    env = os.environ if environ is None else environ
    provided = _bearer_token(authorization_header)
    configured = _env_value(env, API_TOKEN_ENV)
    return bool(provided and configured and hmac.compare_digest(provided, configured))


def token_matches_env(
    authorization_header: str | None,
    env_name: str | None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    if not env_name:
        return False
    env = os.environ if environ is None else environ
    provided = _bearer_token(authorization_header)
    configured = _env_value(env, env_name)
    return bool(provided and configured and hmac.compare_digest(provided, configured))


def product_user_from_authorization(
    authorization_header: str | None,
    bindings: tuple[ProductUserTokenBinding, ...],
    environ: Mapping[str, str] | None = None,
) -> str | None:
    env = os.environ if environ is None else environ
    provided = _bearer_token(authorization_header)
    if not provided:
        return None
    for binding in bindings:
        configured = _env_value(env, binding.token_env)
        if configured and hmac.compare_digest(provided, configured):
            return binding.product_user
    return None


def api_auth_configured(
    environ: Mapping[str, str] | None = None,
    extra_api_token_envs: tuple[str, ...] = (),
) -> bool:
    env = os.environ if environ is None else environ
    return bool(
        _env_value(env, API_TOKEN_ENV)
        or _env_value(env, VIEWER_TOKEN_MAP_ENV)
        or any(_env_value(env, name) for name in extra_api_token_envs)
    )


def _accepted_token_envs(route_scope: str, environ: Mapping[str, str], extra_api_token_envs: tuple[str, ...]) -> tuple[str, ...]:
    if route_scope == "mcp-read":
        return (MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, API_TOKEN_ENV)
    if route_scope == "mcp-write":
        return (MCP_WRITE_TOKEN_ENV, API_TOKEN_ENV)
    if route_scope == "api":
        extra_envs = tuple(dict.fromkeys(name for name in extra_api_token_envs if name))
        if _env_value(environ, VIEWER_TOKEN_MAP_ENV):
            return tuple(dict.fromkeys((API_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV, *extra_envs)))
        return tuple(dict.fromkeys((API_TOKEN_ENV, *extra_envs)))
    return ()


def _protection_envs(route_scope: str, extra_api_token_envs: tuple[str, ...]) -> tuple[str, ...]:
    if route_scope.startswith("mcp-"):
        return (MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, API_TOKEN_ENV)
    if route_scope == "api":
        return tuple(dict.fromkeys((API_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV, *extra_api_token_envs)))
    return ()


def _normalize_path(path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    if len(path) > 1:
        path = path.rstrip("/")
    return path


def _workspace_scoped_path(path: str) -> str | None:
    parts = path.split("/", 3)
    if len(parts) < 4 or parts[1] != "workspaces" or not parts[2]:
        return None
    return f"/{parts[3]}"


def _bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        return ""
    scheme, _, token = authorization_header.strip().partition(" ")
    if scheme.lower() != "bearer" or not token:
        return ""
    return token.strip()


def _env_value(env: Mapping[str, str], name: str) -> str:
    return str(env.get(name, "") or "")


def _matches_any_token(provided: str, env: Mapping[str, str], token_envs: tuple[str, ...]) -> bool:
    return any(
        name != VIEWER_TOKEN_MAP_ENV and hmac.compare_digest(provided, _env_value(env, name))
        for name in token_envs
    )


def _viewer_token_map(env: Mapping[str, str]) -> dict[str, str]:
    raw = _env_value(env, VIEWER_TOKEN_MAP_ENV)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(member): str(token) for member, token in parsed.items() if member and token}
