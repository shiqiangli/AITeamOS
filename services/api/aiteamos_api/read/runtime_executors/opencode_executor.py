"""Optional OpenCode runtime adapter."""

from __future__ import annotations

from .external_runtime_executor import ExternalRuntimeExecutor


class OpenCodeExecutor(ExternalRuntimeExecutor):
    id = "opencode"
    display_name = "OpenCode Executor"
    capabilities = {"agent_loop", "repo:read", "repo:write", "open_source_runtime", "compatible_local_cli"}
    required_env = ()
    binary_env = ("OPENCODE_BIN",)
    command_template_env = "OPENCODE_COMMAND_TEMPLATE"
    model_env = "OPENCODE_MODEL"
    api_base_url_env = "OPENCODE_API_BASE_URL"
    api_key_env_env = "OPENCODE_API_KEY_ENV"
    working_dir_env = "OPENCODE_WORKING_DIR"
    mode_env = "OPENCODE_MODE"
    timeout_env = "OPENCODE_TIMEOUT_SECONDS"
    setup_url = "https://opencode.ai/"
