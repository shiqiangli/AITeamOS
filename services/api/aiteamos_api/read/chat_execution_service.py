"""Reusable Chat execution runtime for AITeamOS domain work.

FastAPI routes own HTTP transport. LangGraph owns the agent workbench runtime.
This service owns the AITeamOS-specific execution boundary shared by both.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from .chat_governance_service import ChatGovernanceInput, ChatGovernanceService
from .chat_models import ChatMessageRequest, ChatMessageResponse, ChatRunContext
from .execution_contract import ExecutionResult

ChatStreamEvent = tuple[str, str | ChatMessageResponse | dict[str, Any]]


class ChatExecutionRuntime:
    def __init__(
        self,
        *,
        prepare_chat_run: Callable[[ChatMessageRequest], ChatRunContext],
        enrich_context: Callable[[ChatRunContext], Awaitable[None]],
        governance_service: Callable[[], ChatGovernanceService],
        governance_input: Callable[[ChatRunContext, Path], ChatGovernanceInput],
        execution_trace_events: Callable[[ChatRunContext, Any, ExecutionResult], list[Any]],
        execution_engine_state: Callable[[ChatRunContext, ExecutionResult], dict[str, Any] | None],
        persist_chat_response: Callable[..., ChatMessageResponse],
        workspace_dir: Callable[[], Path],
        now: Callable[[], str],
        save_execution_session: Callable[..., None],
    ) -> None:
        self._prepare_chat_run = prepare_chat_run
        self._enrich_context = enrich_context
        self._governance_service = governance_service
        self._governance_input = governance_input
        self._execution_trace_events = execution_trace_events
        self._execution_engine_state = execution_engine_state
        self._persist_chat_response = persist_chat_response
        self._workspace_dir = workspace_dir
        self._now = now
        self._save_execution_session = save_execution_session

    async def run_message(self, request: ChatMessageRequest) -> ChatMessageResponse:
        context = await asyncio.to_thread(self._prepare_chat_run, request)
        await self._enrich_context(context)
        trace_path = self._trace_path(context)
        governance = self._governance_service()
        governance_input = await asyncio.to_thread(self._governance_input, context, trace_path)
        execution_request, execution_result = await governance.handle_message(governance_input)
        return await asyncio.to_thread(
            self._response_from_result,
            context,
            execution_request=execution_request,
            execution_result=execution_result,
        )

    async def stream_turn(self, request: ChatMessageRequest) -> AsyncIterator[ChatStreamEvent]:
        context = await asyncio.to_thread(self._prepare_chat_run, request)
        await self._enrich_context(context)
        trace_path = self._trace_path(context)
        governance = self._governance_service()
        governance_input = await asyncio.to_thread(self._governance_input, context, trace_path)
        execution_request = await asyncio.to_thread(
            governance.build_request,
            governance_input,
        )
        yield "start", {
            "thread_id": context.thread_id,
            "run_id": context.run_id,
            "target_employee": context.employee.model_dump(),
            "engine_thread_id": context.engine_thread_id,
            "ticket_keys": context.ticket_keys,
        }

        execution_result: ExecutionResult | None = None
        async for event in governance.dispatch_service.stream(execution_request):
            if event.event == "delta":
                text = str(event.data.get("text") or "")
                if text:
                    yield "delta", text
                    await asyncio.sleep(0)
            elif event.event == "completed":
                execution_result = ExecutionResult.model_validate(event.data)
            elif event.event == "error":
                yield "error", event.data

        if execution_result is None:
            timestamp = self._now()
            execution_result = ExecutionResult(
                request_id=execution_request.request_id,
                executor_id="none",
                status="failed",
                report="Execution stream ended before a completed result was produced.",
                output_ticket_id=execution_request.ticket_id,
                trace_ref=str(execution_request.trace_context.get("trace_ref") or ""),
                errors=[{"reason": "execution_stream_incomplete", "detail": "No completed event was produced."}],
                started_at=timestamp,
                finished_at=timestamp,
            )

        execution_result = await asyncio.to_thread(governance.ingest_result, execution_request, execution_result)
        response = await asyncio.to_thread(
            self._response_from_result,
            context,
            execution_request=execution_request,
            execution_result=execution_result,
        )
        yield "final", response

    @staticmethod
    def _trace_path(context: ChatRunContext) -> Path:
        return context.run_dirs["traces"] / f"{context.run_id}.jsonl"

    def _response_from_result(
        self,
        context: ChatRunContext,
        *,
        execution_request: Any,
        execution_result: ExecutionResult,
    ) -> ChatMessageResponse:
        extra_events = self._execution_trace_events(context, execution_request, execution_result)
        if execution_result.output_ticket_id and execution_result.output_ticket_id not in context.ticket_keys:
            context.ticket_keys.append(execution_result.output_ticket_id)
        self._save_execution_session(
            self._workspace_dir(),
            employee_id=context.employee.id,
            thread_id=context.thread_id,
            ticket_id=execution_result.output_ticket_id or (context.ticket_keys[0] if context.ticket_keys else ""),
            executor_id=execution_result.executor_id,
            executor_session_ref=execution_result.executor_session_ref,
            checkpoint_ref=execution_result.checkpoint_ref,
            last_request_id=execution_result.request_id,
            updated_at=self._now(),
        )
        engine_state = self._execution_engine_state(context, execution_result)
        return self._persist_chat_response(
            context,
            reply=execution_result.report,
            engine_state=engine_state,
            engine_thread_id=str(engine_state.get("engine_thread_id")) if engine_state else context.engine_thread_id,
            extra_trace_events=extra_events,
        )
