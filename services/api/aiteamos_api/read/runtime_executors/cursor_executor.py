"""Optional Cursor commercial agent runtime adapter."""

from __future__ import annotations

from .external_runtime_executor import ExternalRuntimeExecutor


class CursorExecutor(ExternalRuntimeExecutor):
    id = "cursor"
    display_name = "Cursor Executor"
    capabilities = {"agent_loop", "repo:read", "repo:write", "commercial_agent_backend"}
    required_env = ("CURSOR_API_KEY",)
    default_api_key_env = "CURSOR_API_KEY"
    model_env = "CURSOR_MODEL"
    api_base_url_env = "CURSOR_API_BASE_URL"
    api_key_env_env = "CURSOR_API_KEY_ENV"
    http_endpoint_path_env = "CURSOR_INSPECT_ENDPOINT"
    working_dir_env = "CURSOR_WORKING_DIR"
    mode_env = "CURSOR_MODE"
    timeout_env = "CURSOR_TIMEOUT_SECONDS"
    setup_url = "https://cursor.com/"
