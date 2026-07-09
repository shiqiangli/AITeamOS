"""Optional OpenAI Codex CLI runtime adapter."""

from __future__ import annotations

import shutil
from typing import Any

from ..execution_contract import ExecutionRequest
from .external_runtime_executor import ExternalRuntimeExecutor


class CodexCliExecutor(ExternalRuntimeExecutor):
    id = "codex_cli"
    display_name = "OpenAI Codex CLI Executor"
    capabilities = {"agent_loop", "repo:read", "repo:write", "commercial_agent_backend", "compatible_local_cli"}
    required_env = ()
    binary_env = ("CODEX_CLI_BIN",)
    command_template_env = "CODEX_CLI_COMMAND_TEMPLATE"
    model_env = "CODEX_CLI_MODEL"
    api_base_url_env = "CODEX_CLI_API_BASE_URL"
    api_key_env_env = "CODEX_CLI_API_KEY_ENV"
    working_dir_env = "CODEX_CLI_WORKING_DIR"
    mode_env = "CODEX_CLI_MODE"
    timeout_env = "CODEX_CLI_TIMEOUT_SECONDS"
    default_command_template = (
        "{binary} exec --sandbox workspace-write --skip-git-repo-check "
        "--output-schema {output_schema_path} --output-last-message {output_last_message_path} -"
    )
    setup_url = "https://developers.openai.com/codex/"

    def _runtime_config(self, request: ExecutionRequest | None = None) -> dict[str, Any]:
        config = super()._runtime_config(request)
        if not config.get("binary_path"):
            discovered = shutil.which("codex")
            if discovered:
                config["binary_path"] = discovered
        return config
