"""Workbench runtime context/session boundary for LangGraph nodes.

This module is intentionally a thin adapter over the existing Chat runtime
services. It gives the Workbench graph a stable context/session/transcript
boundary without adding another chat runtime or agent loop.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .chat_action_planning_service import ChatActionPlanningService
from .chat_ai_engine_service import ChatAiEngineSettingsService
from .chat_context_enrichment_service import enrich_chat_context_with_graphiti_recall
from .chat_engine_thread_store import save_engine_thread_state
from .chat_execution_engine_state_service import build_execution_engine_state
from .chat_execution_trace_service import build_execution_trace_events
from .chat_governance_service import ChatGovernanceInput, ChatGovernanceService, build_chat_governance_input
from .chat_models import ChatMessageRequest, ChatMessageResponse, ChatRunContext, ChatTraceEvent
from .chat_run_metadata_service import build_chat_run_metadata
from .chat_run_preparation_service import ChatRunPreparationService
from .chat_thread_service import ChatThreadMetadataService
from .chat_transcript_service import persist_chat_response
from .employee_profile_service import load_employee_profiles
from .execution_contract import ExecutionRequest, ExecutionResult
from .execution_dispatch_service import ExecutionDispatchService
from .execution_session_store import save_execution_session


@dataclass(frozen=True)
class WorkbenchRuntimeDispatchInput:
    message: str
    target_employee_id: str = ""
    thread_id: str = ""
    ticket_key: str = ""
    approval_ref: str = ""
    runtime_config: dict[str, Any] = field(default_factory=dict)

    def to_chat_request(self) -> ChatMessageRequest:
        return ChatMessageRequest(
            message=self.message,
            target_employee_id=self.target_employee_id or None,
            thread_id=self.thread_id or None,
            ticket_key=self.ticket_key or None,
            approval_ref=self.approval_ref or None,
            runtime_config=dict(self.runtime_config),
        )


@dataclass(frozen=True)
class WorkbenchPreparedRun:
    chat_request: ChatMessageRequest
    context: ChatRunContext
    trace_path: Path
    governance: ChatGovernanceService
    governance_input: ChatGovernanceInput

    @property
    def approval_ref(self) -> str:
        return str(self.chat_request.approval_ref or "").strip()


class WorkbenchRuntimeContextService:
    service_id = "WorkbenchRuntimeContextService"

    def __init__(
        self,
        *,
        workspace_root: Path | None = None,
        workspace_dir: Path | None = None,
    ) -> None:
        self.workspace_root = (workspace_root or _workspace_root()).resolve()
        self.workspace_dir = (workspace_dir or (self.workspace_root / ".aiteamos")).resolve()
        self.ai_engine_service = ChatAiEngineSettingsService(
            workspace_root=self.workspace_root,
            workspace_dir=self.workspace_dir,
            now=_now,
        )
        self.preparation_service = ChatRunPreparationService(
            workspace_root=self.workspace_root,
            workspace_dir=self.workspace_dir,
            now=_now,
            allow_runtime_config_run_id=True,
        )
        self.thread_service = ChatThreadMetadataService(
            workspace_root=self.workspace_root,
            workspace_dir=self.workspace_dir,
            now=_now,
        )

    async def prepare(self, dispatch_input: WorkbenchRuntimeDispatchInput) -> WorkbenchPreparedRun:
        chat_request = dispatch_input.to_chat_request()
        context = await asyncio.to_thread(self.preparation_service.prepare, chat_request)
        for payload in await enrich_chat_context_with_graphiti_recall(
            context,
            workspace_root=self.workspace_root,
        ):
            context.trace_events.append(ChatTraceEvent(**payload))
        trace_path = self.trace_path(context)
        governance = self.chat_governance_service()
        governance_input = await asyncio.to_thread(self.chat_governance_input, context, trace_path)
        return WorkbenchPreparedRun(
            chat_request=chat_request,
            context=context,
            trace_path=trace_path,
            governance=governance,
            governance_input=governance_input,
        )

    async def persist_execution_response(
        self,
        context: ChatRunContext,
        *,
        execution_request: ExecutionRequest,
        execution_result: ExecutionResult,
    ) -> ChatMessageResponse:
        return await asyncio.to_thread(
            self._persist_execution_response_sync,
            context,
            execution_request,
            execution_result,
        )

    @staticmethod
    def trace_path(context: ChatRunContext) -> Path:
        return context.run_dirs["traces"] / f"{context.run_id}.jsonl"

    def chat_governance_service(self) -> ChatGovernanceService:
        return ChatGovernanceService(
            workspace_dir=self.workspace_dir,
            planner=ChatActionPlanningService(async_client_factory=httpx.AsyncClient),
            dispatch_service=ExecutionDispatchService(async_client_factory=httpx.AsyncClient),
        )

    def chat_governance_input(self, context: ChatRunContext, trace_path: Path) -> ChatGovernanceInput:
        return build_chat_governance_input(
            context,
            trace_path=trace_path,
            workspace_root=self.workspace_root,
            employee_profiles=load_employee_profiles(workspace_root=self.workspace_root),
        )

    def build_run_metadata(
        self,
        context: ChatRunContext,
        *,
        final_engine_thread_id: str,
        trace_events: list[ChatTraceEvent],
        trace_path: Path,
    ) -> dict[str, Any]:
        return build_chat_run_metadata(
            context,
            final_engine_thread_id=final_engine_thread_id,
            trace_events=trace_events,
            trace_path=trace_path,
            workspace_root=self.workspace_root,
            selected_model=self.ai_engine_service.selected_model,
            now=_now,
        )

    def record_chat_thread_turn(self, context: ChatRunContext, *, last_message_at: str):
        employees = [
            self.preparation_service.employee_projection.employee_summary(profile)
            for profile in load_employee_profiles(workspace_root=self.workspace_root)
        ]
        return self.thread_service.record_chat_thread_turn(
            context,
            last_message_at=last_message_at,
            employees=employees,
        )

    def _persist_execution_response_sync(
        self,
        context: ChatRunContext,
        execution_request: ExecutionRequest,
        execution_result: ExecutionResult,
    ) -> ChatMessageResponse:
        extra_events = build_execution_trace_events(context, execution_request, execution_result)
        if execution_result.output_ticket_id and execution_result.output_ticket_id not in context.ticket_keys:
            context.ticket_keys.append(execution_result.output_ticket_id)
        save_execution_session(
            self.workspace_dir,
            employee_id=context.employee.id,
            thread_id=context.thread_id,
            ticket_id=execution_result.output_ticket_id or (context.ticket_keys[0] if context.ticket_keys else ""),
            executor_id=execution_result.executor_id,
            executor_session_ref=execution_result.executor_session_ref,
            checkpoint_ref=execution_result.checkpoint_ref,
            last_request_id=execution_result.request_id,
            updated_at=_now(),
            status=execution_result.status,
            trace_ref=execution_result.trace_ref or str(execution_request.trace_context.get("trace_ref") or ""),
        )
        engine_state = build_execution_engine_state(
            context,
            execution_result,
            ai_engine_service=self.ai_engine_service,
        )
        return persist_chat_response(
            context,
            reply=execution_result.report,
            workspace_root=self.workspace_root,
            workspace_dir=self.workspace_dir,
            trace_event_model=ChatTraceEvent,
            response_model=ChatMessageResponse,
            now=_now,
            save_engine_thread_state=save_engine_thread_state,
            build_run_metadata=self.build_run_metadata,
            record_chat_thread_turn=self.record_chat_thread_turn,
            thread_index_saved_path=self.thread_service.thread_index_saved_path,
            engine_state=engine_state,
            engine_thread_id=str(engine_state.get("engine_thread_id")) if engine_state else context.engine_thread_id,
            extra_trace_events=extra_events,
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[4]
