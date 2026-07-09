"""Optional OpenHands runtime adapter."""

from __future__ import annotations

from .external_runtime_executor import ExternalRuntimeExecutor


class OpenHandsExecutor(ExternalRuntimeExecutor):
    id = "openhands"
    display_name = "OpenHands Executor"
    capabilities = {"agent_loop", "repo:read", "repo:write", "open_source_runtime"}
    required_env = ("OPENHANDS_BASE_URL",)
    model_env = "OPENHANDS_MODEL"
    api_base_url_env = "OPENHANDS_BASE_URL"
    api_key_env_env = "OPENHANDS_API_KEY_ENV"
    http_endpoint_path_env = "OPENHANDS_INSPECT_ENDPOINT"
    working_dir_env = "OPENHANDS_WORKING_DIR"
    mode_env = "OPENHANDS_MODE"
    timeout_env = "OPENHANDS_TIMEOUT_SECONDS"
    setup_url = "https://docs.all-hands.dev/"
