"""Route-free Chat runtime factory for LangGraph and API callers.

This module keeps the AITeamOS domain Chat runtime outside FastAPI route
modules so LangGraph Agent Server can import and execute the Workbench graph
without pulling HTTP transport, AG-UI compatibility code, or route decorators
into the graph runtime boundary.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .ai_engine_runtime_config import AiEngineRuntimeConfig
from .chat_action_planning_service import ChatActionPlanningService
from .chat_ai_engine_service import ChatAiEngineSettingsService
from .chat_context_enrichment_service import (
    build_initial_chat_context_assets,
    enrich_chat_context_with_graphiti_recall as enrich_chat_context_with_graphiti_recall_service,
)
from .chat_engine_thread_store import (
    save_engine_thread_state,
)
from .chat_execution_service import ChatExecutionRuntime
from .chat_governance_service import ChatGovernanceService, build_chat_governance_input
from .chat_run_preparation_service import ChatRunPreparationService
from .chat_models import (
    ChatEmployeeSummary,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatRunContext,
    ChatThreadSummary,
    ChatTraceEvent,
    ConversationMessage,
)
from .chat_run_metadata_service import build_chat_run_metadata
from .chat_execution_engine_state_service import build_execution_engine_state
from .chat_employee_projection_service import ChatEmployeeProjectionService
from .chat_execution_trace_service import (
    build_execution_trace_events,
    universal_context_trace_data as shared_universal_context_trace_data,
)
from .chat_skill_service import skill_titles as chat_skill_titles
from .chat_ticket_key_service import extract_ticket_keys, normalize_ticket_key
from .chat_thread_service import ChatThreadMetadataService
from .chat_transcript_service import persist_chat_response
from .employee_profile_service import load_employee_profiles
from .execution_contract import ExecutionResult
from .execution_dispatch_service import ExecutionDispatchService
from .execution_session_store import save_execution_session


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def build_chat_execution_runtime() -> ChatExecutionRuntime:
    return ChatExecutionRuntime(
        prepare_chat_run=prepare_chat_run,
        enrich_context=enrich_chat_context_with_graphiti_recall,
        governance_service=chat_governance_service,
        governance_input=chat_governance_input,
        execution_trace_events=execution_trace_events,
        execution_engine_state=execution_engine_state,
        persist_chat_response=persist_chat_response_for_context,
        workspace_dir=workspace_dir,
        now=now,
        save_execution_session=save_execution_session,
    )


async def run_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    return await build_chat_execution_runtime().run_message(request)


def now() -> str:
    return datetime.now(UTC).isoformat()


def workspace_root() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def workspace_dir() -> Path:
    return workspace_root() / ".aiteamos"


def require_safe_id(value: str, *, field: str) -> str:
    if not SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"Invalid {field}")
    return value


def employee_projection_service() -> ChatEmployeeProjectionService:
    return ChatEmployeeProjectionService(workspace_dir=workspace_dir())


def safe_thread_component(value: str) -> str:
    return ChatEmployeeProjectionService.safe_thread_component(value)


def employee_default_thread_id(employee_id: str) -> str:
    return employee_projection_service().employee_default_thread_id(employee_id)


def load_employees() -> list[dict[str, Any]]:
    return load_employee_profiles(workspace_root=workspace_root())


def employee_summary(profile: dict[str, Any]) -> ChatEmployeeSummary:
    return employee_projection_service().employee_summary(profile)


def all_employee_summaries() -> list[ChatEmployeeSummary]:
    return [employee_summary(profile) for profile in load_employees()]


def select_employee(
    profiles: list[dict[str, Any]],
    *,
    requested_employee_id: str | None,
    message: str,
) -> dict[str, Any]:
    try:
        return employee_projection_service().select_profile(
            profiles,
            requested_employee_id=requested_employee_id,
            message=message,
        )
    except KeyError as exc:
        raise ValueError(f"Employee not found: {requested_employee_id}") from exc


def chat_run_preparation_service() -> ChatRunPreparationService:
    return ChatRunPreparationService(
        workspace_root=workspace_root(),
        workspace_dir=workspace_dir(),
        now=now,
        allow_runtime_config_run_id=True,
    )


def chat_thread_service() -> ChatThreadMetadataService:
    return ChatThreadMetadataService(
        workspace_root=workspace_root(),
        workspace_dir=workspace_dir(),
        now=now,
    )


def load_thread_messages(thread_id: str, *, limit: int | None = None) -> list[ConversationMessage]:
    return chat_thread_service().load_conversation_messages(thread_id, limit=limit)


def thread_index_path() -> str:
    return chat_thread_service().thread_index_saved_path()


def conversation_path_for_thread(thread_id: str) -> str:
    return chat_thread_service().conversation_saved_path(thread_id)


def thread_summary_from_record(thread_id: str, record: dict[str, Any]) -> ChatThreadSummary:
    return chat_thread_service().thread_summary_from_record(thread_id, record)


def default_thread_title(employee: ChatEmployeeSummary, thread_id: str) -> str:
    return chat_thread_service().default_thread_title(employee, thread_id)


def infer_thread_employee_id(thread_id: str, employees: list[ChatEmployeeSummary]) -> str | None:
    return chat_thread_service().infer_thread_employee_id(thread_id, employees)


def conversation_metadata(thread_id: str, employees: list[ChatEmployeeSummary]) -> dict[str, Any]:
    return chat_thread_service().conversation_metadata(thread_id, employees)


def hydrate_thread_index() -> dict[str, Any]:
    return chat_thread_service().hydrate_thread_index(all_employee_summaries())


def record_chat_thread_turn(context: ChatRunContext, *, last_message_at: str) -> ChatThreadSummary:
    return chat_thread_service().record_chat_thread_turn(
        context,
        last_message_at=last_message_at,
        employees=all_employee_summaries(),
    )


def chat_ai_engine_service() -> ChatAiEngineSettingsService:
    return ChatAiEngineSettingsService(
        workspace_root=workspace_root(),
        workspace_dir=workspace_dir(),
        now=now,
    )


def ai_engine_runtime() -> AiEngineRuntimeConfig:
    return chat_ai_engine_service().runtime()


def selected_ai_engine_model(engine: str) -> str | None:
    return chat_ai_engine_service().selected_model(engine)


def skill_titles(skill_ids: list[str]) -> list[str]:
    return chat_skill_titles(
        skill_ids,
        workspace_root=workspace_root(),
        workspace_dir=workspace_dir(),
    )


def build_run_metadata(
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
        workspace_root=workspace_root(),
        selected_model=selected_ai_engine_model,
        now=now,
    )


async def enrich_chat_context_with_graphiti_recall(context: ChatRunContext) -> None:
    for payload in await enrich_chat_context_with_graphiti_recall_service(
        context,
        workspace_root=workspace_root(),
    ):
        context.trace_events.append(ChatTraceEvent(**payload))


def prepare_chat_run(request: ChatMessageRequest) -> ChatRunContext:
    return chat_run_preparation_service().prepare(request)


def graph_runtime_run_id(request: ChatMessageRequest) -> str:
    return chat_run_preparation_service().graph_runtime_run_id(request)


def persist_chat_response_for_context(
    context: ChatRunContext,
    *,
    reply: str,
    engine_state: dict[str, Any] | None = None,
    engine_thread_id: str | None = None,
    extra_trace_events: list[ChatTraceEvent] | None = None,
) -> ChatMessageResponse:
    return persist_chat_response(
        context,
        reply=reply,
        workspace_root=workspace_root(),
        workspace_dir=workspace_dir(),
        trace_event_model=ChatTraceEvent,
        response_model=ChatMessageResponse,
        now=now,
        save_engine_thread_state=save_engine_thread_state,
        build_run_metadata=build_run_metadata,
        record_chat_thread_turn=record_chat_thread_turn,
        thread_index_saved_path=thread_index_path,
        engine_state=engine_state,
        engine_thread_id=engine_thread_id,
        extra_trace_events=extra_trace_events,
    )


def chat_governance_service() -> ChatGovernanceService:
    return ChatGovernanceService(
        workspace_dir=workspace_dir(),
        planner=ChatActionPlanningService(async_client_factory=httpx.AsyncClient),
        dispatch_service=ExecutionDispatchService(async_client_factory=httpx.AsyncClient),
    )


def chat_governance_input(context: ChatRunContext, trace_path: Path):
    return build_chat_governance_input(
        context,
        trace_path=trace_path,
        workspace_root=workspace_root(),
        employee_profiles=load_employees(),
    )


def execution_engine_state(context: ChatRunContext, result: ExecutionResult) -> dict[str, Any] | None:
    return build_execution_engine_state(
        context,
        result,
        ai_engine_service=chat_ai_engine_service(),
    )


def universal_context_trace_data(execution_request: Any) -> dict[str, Any]:
    return shared_universal_context_trace_data(execution_request)


def execution_trace_events(
    context: ChatRunContext,
    execution_request: Any,
    execution_result: ExecutionResult,
) -> list[ChatTraceEvent]:
    return build_execution_trace_events(context, execution_request, execution_result)
