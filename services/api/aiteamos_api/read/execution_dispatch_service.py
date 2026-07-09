"""Executor selection and dispatch for runtime-first Chat execution."""

from __future__ import annotations

from contextlib import suppress
from collections.abc import AsyncIterator
from typing import Any

from .execution_contract import ExecutionEvent, ExecutionRequest, ExecutionResult
from .runtime_executors.claude_agent_sdk_executor import ClaudeAgentSDKExecutor
from .runtime_executors.claude_code_executor import ClaudeCodeExecutor
from .runtime_executors.codex_cli_executor import CodexCliExecutor
from .runtime_executors.base import RuntimeExecutor, blocked_result
from .runtime_executors.cursor_executor import CursorExecutor
from .langchain_model_provider import LangChainModelProvider
from .runtime_executors.langgraph_executor import LangGraphExecutor
from .runtime_executors.local_tool_executor import LocalToolExecutor
from .runtime_executors.openhands_executor import OpenHandsExecutor
from .runtime_executors.opencode_executor import OpenCodeExecutor
from .runtime_executors.universal_employee_agent_executor import UniversalEmployeeAgentExecutor


class ExecutionDispatchService:
    def __init__(
        self,
        executors: list[RuntimeExecutor] | None = None,
        *,
        async_client_factory: Any | None = None,
        model_provider: LangChainModelProvider | None = None,
    ) -> None:
        self.executors: dict[str, RuntimeExecutor] = {
            executor.id: executor
            for executor in (
                executors
                or [
                    LocalToolExecutor(),
                    UniversalEmployeeAgentExecutor(async_client_factory=async_client_factory, model_provider=model_provider),
                    LangGraphExecutor(async_client_factory=async_client_factory, model_provider=model_provider),
                    ClaudeAgentSDKExecutor(),
                    ClaudeCodeExecutor(),
                    CodexCliExecutor(),
                    CursorExecutor(),
                    OpenHandsExecutor(),
                    OpenCodeExecutor(),
                ]
            )
        }

    async def dispatch(self, request: ExecutionRequest) -> ExecutionResult:
        blocker = self._binding_blocker(request)
        executor_id = self._executor_id(request)
        executor = self.executors.get(executor_id)
        if executor is None:
            return blocked_result(request, executor_id="none", reason="executor_unavailable", detail="No runtime executor is configured.")
        if blocker:
            result = blocked_result(request, executor_id=executor.id, reason=blocker, detail=self._binding_blocker_detail(request, blocker))
            if request.action_plan.action == "terminal_run":
                result = result.model_copy(
                    update={
                        "tool_events": [
                            {
                                "event": "command.blocked",
                                "detail": result.report,
                                "data": {
                                    "command": {"id": "terminal.run:run", "capability": "terminal.run", "operation": "run"},
                                    "reason": blocker,
                                },
                            }
                        ]
                    }
                )
            return result
        return await executor.run(request)

    async def stream(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]:
        blocker = self._binding_blocker(request)
        executor_id = self._executor_id(request)
        executor = self.executors.get(executor_id)
        if executor is None:
            result = blocked_result(request, executor_id="none", reason="executor_unavailable", detail="No runtime executor is configured.")
            yield ExecutionEvent(event="blocked", request_id=request.request_id, data={"errors": result.errors, "report": result.report})
            yield ExecutionEvent(event="completed", request_id=request.request_id, data=result.model_dump(mode="json"))
            return
        if blocker:
            result = blocked_result(request, executor_id=executor.id, reason=blocker, detail=self._binding_blocker_detail(request, blocker))
            yield ExecutionEvent(event="blocked", request_id=request.request_id, data={"errors": result.errors, "report": result.report})
            yield ExecutionEvent(event="completed", request_id=request.request_id, data=result.model_dump(mode="json"))
            return
        async for event in executor.stream(request):
            yield event

    def _executor_id(self, request: ExecutionRequest) -> str:
        requested = self._requested_executor_id(request)
        if requested == "langgraph":
            return "langgraph"
        if requested == "universal_employee_agent":
            return "universal_employee_agent"
        if requested in {"claude_agent_sdk", "claude_code", "codex_cli", "cursor", "openhands", "opencode"}:
            return requested
        if request.action_plan.action in {
            "list_employees",
            "create_employee",
            "edit_employee_profile",
            "delete_employee",
            "list_skills",
            "create_skill",
            "assign_skill_to_employee",
            "delete_skill",
            "inspect_permissions",
            "search_knowledge",
            "self_bootstrap_close",
            "self_bootstrap_start",
            "self_bootstrap_summary",
            "list_code_repositories",
            "inspect_code_repository",
            "terminal_run",
        }:
            return "local_tool"
        return "universal_employee_agent"

    async def aclose(self) -> None:
        for executor in self.executors.values():
            close = getattr(executor, "aclose", None)
            if close is None:
                continue
            with suppress(Exception):
                await close()

    def _requested_executor_id(self, request: ExecutionRequest) -> str:
        requested = str(
            request.permission_policy.get("executor_id")
            or request.permission_policy.get("selected_executor")
            or request.permission_policy.get("selected_ai_engine")
            or ""
        ).strip()
        aliases = {
            "claude-code": "claude_code",
            "claude_agent": "claude_agent_sdk",
            "claude-agent-sdk": "claude_agent_sdk",
            "codex": "codex_cli",
            "codex-cli": "codex_cli",
            "open-hands": "openhands",
            "open-code": "opencode",
        }
        return aliases.get(requested, requested)

    def _binding_blocker(self, request: ExecutionRequest) -> str:
        binding = request.ticket_binding
        if binding.required and binding.mode == "existing" and not (binding.ticket_id or request.ticket_id):
            return "Ticket binding is required before dispatch."
        if binding.mode == "create" and not binding.required:
            return ""
        if binding.mode not in {"existing", "create", "none"}:
            return f"Unsupported Ticket binding mode: {binding.mode}"
        return ""

    def _binding_blocker_detail(self, request: ExecutionRequest, blocker: str) -> str:
        if request.action_plan.action == "terminal_run" and "Ticket binding is required" in blocker:
            return "terminal.run requires a Ticket binding before command execution."
        return blocker
