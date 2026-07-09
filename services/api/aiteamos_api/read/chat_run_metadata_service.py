"""Run metadata mapping shared by Chat API and LangGraph runtime."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .chat_models import ChatRunContext, ChatTraceEvent
from .chat_response_metadata import build_run_metadata as build_run_metadata_data


def build_chat_run_metadata(
    context: ChatRunContext,
    *,
    final_engine_thread_id: str,
    trace_events: list[ChatTraceEvent],
    trace_path: Path,
    workspace_root: Path,
    selected_model: Callable[[str], str | None],
    now: Callable[[], str],
) -> dict[str, Any]:
    selected_ai_engine = context.selected_ai_engine
    return build_run_metadata_data(
        run_id=context.run_id,
        thread_id=context.thread_id,
        employee_id=context.employee.id,
        employee_display_name=context.employee.display_name,
        employee_role=context.employee.role,
        employee_default_ai_engine=context.employee.default_ai_engine,
        ticket_keys=context.ticket_keys,
        memory_refs=context.memory_refs,
        selected_ai_engine=selected_ai_engine,
        selected_model=selected_model(selected_ai_engine),
        engine_state=context.engine_state,
        final_engine_thread_id=final_engine_thread_id,
        trace_events=trace_events,
        trace_relative_path=str(trace_path.relative_to(workspace_root)),
        created_at=now(),
    )
