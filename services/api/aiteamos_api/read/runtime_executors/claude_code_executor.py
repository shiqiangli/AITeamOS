"""Optional Claude Code runtime adapter."""

from __future__ import annotations

from .external_runtime_executor import ExternalRuntimeExecutor


class ClaudeCodeExecutor(ExternalRuntimeExecutor):
    id = "claude_code"
    display_name = "Claude Code-compatible Local CLI Executor"
    capabilities = {"agent_loop", "repo:read", "repo:write", "compatible_local_cli", "deepseek_backend", "openai_backend"}
    required_env = ()
    binary_env = ("CLAUDE_CODE_BIN",)
    command_template_env = "CLAUDE_CODE_COMMAND_TEMPLATE"
    model_env = "CLAUDE_CODE_MODEL"
    api_base_url_env = "CLAUDE_CODE_API_BASE_URL"
    api_key_env_env = "CLAUDE_CODE_API_KEY_ENV"
    working_dir_env = "CLAUDE_CODE_WORKING_DIR"
    mode_env = "CLAUDE_CODE_MODE"
    timeout_env = "CLAUDE_CODE_TIMEOUT_SECONDS"
    setup_url = ""
