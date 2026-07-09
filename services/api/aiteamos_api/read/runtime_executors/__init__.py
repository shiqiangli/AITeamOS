"""Runtime executor adapters for AITeamOS execution dispatch."""

from .claude_agent_sdk_executor import ClaudeAgentSDKExecutor
from .claude_code_executor import ClaudeCodeExecutor
from .codex_cli_executor import CodexCliExecutor
from .cursor_executor import CursorExecutor
from .langgraph_executor import LangGraphExecutor
from .local_tool_executor import LocalToolExecutor
from .openhands_executor import OpenHandsExecutor
from .opencode_executor import OpenCodeExecutor
from .universal_employee_agent_executor import UniversalEmployeeAgentExecutor

__all__ = [
    "ClaudeAgentSDKExecutor",
    "ClaudeCodeExecutor",
    "CodexCliExecutor",
    "CursorExecutor",
    "LangGraphExecutor",
    "LocalToolExecutor",
    "OpenHandsExecutor",
    "OpenCodeExecutor",
    "UniversalEmployeeAgentExecutor",
]
