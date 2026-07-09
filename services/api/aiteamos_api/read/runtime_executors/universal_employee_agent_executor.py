"""LangGraph-backed universal employee agent runtime."""

from __future__ import annotations

from typing import Any

from .langgraph_executor import LangGraphExecutor


class UniversalEmployeeAgentExecutor(LangGraphExecutor):
    """Default Chat runtime for employee-aware answer loops.

    The executor runs the LangGraph read-tool node before generating the final
    answer. Model providers are reachable through LangGraph/LangChain provider
    wiring, not through a separate direct-LLM executor.
    """

    id = "universal_employee_agent"
    display_name = "Universal Employee Agent"
    capabilities = LangGraphExecutor.capabilities | {"employee_agent_loop", "read_tools"}

    async def health(self) -> dict[str, Any]:
        health = await super().health()
        return {
            **health,
            "executor_id": self.id,
            "detail": "LangGraph universal employee agent with read-only AITeamOS tools.",
            "capabilities": sorted(self.capabilities),
        }

    def _pre_graph_remote_answer_enabled(self) -> bool:
        return False

    def _agent_remote_answer_enabled(self) -> bool:
        return True
