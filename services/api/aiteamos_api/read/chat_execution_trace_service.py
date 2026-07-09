"""Execution trace projection shared by Chat API and LangGraph runtime."""

from __future__ import annotations

from typing import Any

from .chat_action_plan import kernel_plan_from_chat_action_plan
from .chat_models import ChatRunContext, ChatTraceEvent
from .chat_trace_utils import is_result_ingestion_command
from .execution_contract import ExecutionResult


def universal_context_trace_data(execution_request: Any) -> dict[str, Any]:
    task_context = execution_request.task_context if isinstance(execution_request.task_context, dict) else {}
    universal_context = task_context.get("universal_context") if isinstance(task_context.get("universal_context"), dict) else {}
    if not universal_context:
        return {}
    summary = universal_context.get("summary") if isinstance(universal_context.get("summary"), dict) else {}
    provenance = universal_context.get("provenance_summary") if isinstance(universal_context.get("provenance_summary"), list) else []
    backend_context = universal_context.get("backend_context") if isinstance(universal_context.get("backend_context"), dict) else {}
    ticket_backend = backend_context.get("ticket_backend") if isinstance(backend_context.get("ticket_backend"), dict) else {}

    def safe_int(raw: Any) -> int:
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "version": str(universal_context.get("version") or ""),
        "employee_id": str(summary.get("employee_id") or execution_request.employee_id),
        "ticket_id": str(summary.get("ticket_id") or execution_request.ticket_id or ""),
        "related_ticket_count": safe_int(summary.get("related_ticket_count")),
        "relevant_asset_count": safe_int(summary.get("relevant_asset_count")),
        "recalled_memory_count": safe_int(summary.get("recalled_memory_count")),
        "prior_evidence_count": safe_int(summary.get("prior_evidence_count")),
        "setup_blocker_count": safe_int(summary.get("setup_blocker_count")),
        "ticket_backend_status": str(ticket_backend.get("status") or ""),
        "provenance_summary": [
            item for item in provenance[:8]
            if isinstance(item, dict)
        ],
    }


def build_execution_trace_events(
    context: ChatRunContext,
    execution_request: Any,
    execution_result: ExecutionResult,
) -> list[ChatTraceEvent]:
    planning_events = execution_request.trace_context.get("planning_events")
    universal_context_data = universal_context_trace_data(execution_request)
    extra_events = [
        *[
            ChatTraceEvent(
                event=str(event.get("event") or "command.intent_planner.event"),
                detail=str(event.get("detail") or event.get("event") or "Planner event."),
                data=event.get("data") if isinstance(event.get("data"), dict) else {},
            )
            for event in (planning_events if isinstance(planning_events, list) else [])
            if isinstance(event, dict)
        ],
        ChatTraceEvent(
            event="chat.action_plan.completed",
            detail="Clara produced a product-level ChatActionPlan for execution dispatch.",
            data={
                **execution_request.action_plan.model_dump(mode="json"),
                "kernel_command": kernel_plan_from_chat_action_plan(execution_request.action_plan).command,
            },
        ),
        ChatTraceEvent(
            event="execution.request.created",
            detail="Created runtime ExecutionRequest from Clara governance planning.",
            data=execution_request.model_dump(mode="json"),
        ),
        *(
            [
                ChatTraceEvent(
                    event="execution.context.loaded",
                    detail="Loaded universal Employee/Ticket/Asset/Memory context for runtime execution.",
                    data=universal_context_data,
                )
            ]
            if universal_context_data
            else []
        ),
        ChatTraceEvent(
            event="execution.dispatch.completed",
            detail=f"Execution dispatch returned status={execution_result.status}.",
            data=execution_result.model_dump(mode="json"),
        ),
        ChatTraceEvent(
            event="execution.runtime.completed" if execution_result.status != "blocked" else "execution.runtime.blocked",
            detail="Runtime executor handled the Chat turn through ExecutionDispatchService.",
            data={
                "ai_engine": context.selected_ai_engine,
                "executor_id": execution_result.executor_id,
                "executor_session_ref": execution_result.executor_session_ref,
                "checkpoint_ref": execution_result.checkpoint_ref,
                "status": execution_result.status,
                "output_ticket_id": execution_result.output_ticket_id,
            },
        ),
    ]
    planner_already_skipped_command = any(
        isinstance(event, dict) and event.get("event") == "command.intent_planner.skipped"
        for event in (planning_events if isinstance(planning_events, list) else [])
    )
    if execution_request.action_plan.action == "answer_only" and not planner_already_skipped_command:
        extra_events.append(
            ChatTraceEvent(
                event="command.intercept.skipped",
                detail="No deterministic governance command was selected for this Chat turn.",
                data={
                    "reason": "answer_only_dispatch",
                    "selected_ai_engine": context.selected_ai_engine,
                    "executor_id": execution_result.executor_id,
                },
            )
        )
    for event in execution_result.tool_events:
        event_name = str(event.get("event") or "")
        if event_name.startswith("command."):
            event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
            command = event_data.get("command") if isinstance(event_data.get("command"), dict) else {}
            command_id = str(command.get("id") or event_data.get("command_id") or "")
            if is_result_ingestion_command(command_id, event):
                continue
            extra_events.append(
                ChatTraceEvent(
                    event=event_name,
                    detail=str(event.get("detail") or event_name),
                    data=event_data,
                )
            )
        elif event_name.startswith("ai_engine."):
            event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
            extra_events.append(
                ChatTraceEvent(
                    event=event_name,
                    detail=str(event.get("detail") or event_name),
                    data=event_data,
                )
            )
    if any(error.get("reason") == "ai_engine_configuration_blocker" for error in execution_result.errors):
        extra_events.append(
            ChatTraceEvent(
                event="ai_engine.remote.configuration_blocked",
                detail="Selected remote AI Engine was blocked by configuration before execution.",
                data={
                    "ai_engine": f"{context.selected_ai_engine}_configuration_blocked",
                    "selected_ai_engine": context.selected_ai_engine,
                    "executor_id": execution_result.executor_id,
                    "errors": execution_result.errors,
                },
            )
        )
    return extra_events
