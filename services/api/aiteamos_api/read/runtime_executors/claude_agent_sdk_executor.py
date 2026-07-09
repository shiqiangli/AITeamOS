"""Optional Claude Agent SDK runtime adapter."""

from __future__ import annotations

from .external_runtime_executor import ExternalRuntimeExecutor


class ClaudeAgentSDKExecutor(ExternalRuntimeExecutor):
    id = "claude_agent_sdk"
    display_name = "Claude Agent SDK Executor"
    capabilities = {"agent_loop", "repo:read", "repo:write", "official_sdk"}
    required_env = ("ANTHROPIC_API_KEY",)
    setup_url = "https://docs.anthropic.com/"
