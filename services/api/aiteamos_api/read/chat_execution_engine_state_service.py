"""Execution engine-state mapping shared by Chat API and LangGraph runtime."""

from __future__ import annotations

from typing import Any, Protocol

from .chat_models import ChatRunContext
from .execution_contract import ExecutionResult


class ExecutionEngineStateService(Protocol):
    def execution_engine_state(
        self,
        *,
        employee_id: str,
        current_state: dict[str, Any],
        result: ExecutionResult,
    ) -> dict[str, Any] | None: ...


def build_execution_engine_state(
    context: ChatRunContext,
    result: ExecutionResult,
    *,
    ai_engine_service: ExecutionEngineStateService,
) -> dict[str, Any] | None:
    return ai_engine_service.execution_engine_state(
        employee_id=context.employee.id,
        current_state=context.engine_state,
        result=result,
    )
