"""
File-backed Employee Chat routes.

P0 intentionally avoids database dependencies. Employee profiles, conversation
history, trace events, and external AI Engine thread mappings live under the
local .aiteamos workspace directory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any, TypeVar

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from .chat_action_plan import (
    kernel_plan_from_chat_action_plan as _kernel_plan_from_chat_action_plan,
    normalize_chat_action_plan as _normalize_chat_action_plan,
)
from .chat_models import (
    ChatAiEngineSettings,
    ChatAiEngineSettingsRequest,
    ChatAiEngineUpdateRequest,
    ChatEmployeeAiEngineUpdateRequest,
    ChatEmployeeSummary,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSkillSummary,
    ChatThreadActivateRequest,
    ChatThreadCreateRequest,
    ChatThreadListResponse,
    ChatThreadSummary,
    ConversationResponse,
)
from .chat_execution_service import ChatExecutionRuntime, ChatStreamEvent
from .chat_runtime_factory import build_chat_execution_runtime
from .chat_surface_service import ChatSurfaceError, ChatSurfaceService
from .chat_streaming_utils import sse_payload as _sse_payload

router = APIRouter(prefix="/api/v1/chat", tags=["employee-chat"])

T = TypeVar("T")


def _chat_surface_service() -> ChatSurfaceService:
    return ChatSurfaceService()


def _surface_call(callback: Callable[[], T]) -> T:
    try:
        return callback()
    except ChatSurfaceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/employees", response_model=list[ChatEmployeeSummary])
async def list_chat_employees() -> list[ChatEmployeeSummary]:
    return _surface_call(lambda: _chat_surface_service().list_employees())


@router.put("/employees/{employee_id}/ai-engine", response_model=ChatEmployeeSummary)
async def update_chat_employee_ai_engine(
    employee_id: str,
    request: ChatEmployeeAiEngineUpdateRequest,
) -> ChatEmployeeSummary:
    return _surface_call(lambda: _chat_surface_service().update_employee_ai_engine(employee_id, request))


@router.get("/skills", response_model=list[ChatSkillSummary])
async def list_chat_skills() -> list[ChatSkillSummary]:
    return _surface_call(lambda: _chat_surface_service().list_skills())


@router.get("/ai-engines", response_model=ChatAiEngineSettings)
async def get_chat_ai_engines() -> ChatAiEngineSettings:
    return _surface_call(lambda: _chat_surface_service().ai_engine_settings())


@router.put("/ai-engines", response_model=ChatAiEngineSettings)
async def update_chat_ai_engines(request: ChatAiEngineSettingsRequest) -> ChatAiEngineSettings:
    return _surface_call(lambda: _chat_surface_service().update_ai_engine_settings(request))


@router.put("/ai-engines/{engine_id}", response_model=ChatAiEngineSettings)
async def update_chat_ai_engine(
    engine_id: str,
    request: ChatAiEngineUpdateRequest,
) -> ChatAiEngineSettings:
    return _surface_call(lambda: _chat_surface_service().update_ai_engine(engine_id, request))


@router.get("/threads", response_model=ChatThreadListResponse)
async def list_chat_threads(employee_id: str) -> ChatThreadListResponse:
    return _surface_call(lambda: _chat_surface_service().list_threads(employee_id))


@router.post("/threads", response_model=ChatThreadSummary)
async def create_chat_thread(request: ChatThreadCreateRequest) -> ChatThreadSummary:
    return _surface_call(lambda: _chat_surface_service().create_thread(request))


@router.post("/threads/{thread_id}/activate", response_model=ChatThreadSummary)
async def activate_chat_thread(thread_id: str, request: ChatThreadActivateRequest) -> ChatThreadSummary:
    return _surface_call(lambda: _chat_surface_service().activate_thread(thread_id, request))


@router.delete("/threads/{thread_id}")
async def delete_chat_thread(thread_id: str) -> dict[str, Any]:
    return _surface_call(lambda: _chat_surface_service().delete_thread(thread_id))


@router.get("/threads/{thread_id}", response_model=ConversationResponse)
async def get_chat_thread(thread_id: str) -> ConversationResponse:
    return _surface_call(lambda: _chat_surface_service().get_thread(thread_id))


def get_chat_execution_runtime() -> ChatExecutionRuntime:
    return build_chat_execution_runtime()


async def run_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    return await get_chat_execution_runtime().run_message(request)


@router.post("/messages", response_model=ChatMessageResponse)
async def send_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    return await run_chat_message(request)


async def _stream_chat_turn(
    request: ChatMessageRequest,
) -> AsyncIterator[ChatStreamEvent]:
    async for event in get_chat_execution_runtime().stream_turn(request):
        yield event


@router.post("/messages/stream")
async def stream_chat_message(request: ChatMessageRequest) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        try:
            started = False
            async for event, payload in _stream_chat_turn(request):
                if event == "start":
                    started = True
                    yield _sse_payload("start", payload)
                elif event == "delta":
                    yield _sse_payload("delta", {"text": payload})
                elif event == "final":
                    response = payload if isinstance(payload, ChatMessageResponse) else ChatMessageResponse.model_validate(payload)
                    if not started:
                        yield _sse_payload(
                            "start",
                            {
                                "thread_id": response.thread_id,
                                "run_id": response.run_id,
                                "target_employee": response.target_employee.model_dump(),
                                "engine_thread_id": response.engine_thread_id,
                                "ticket_keys": response.ticket_keys,
                            },
                        )
                    yield _sse_payload("final", response.model_dump())
        except HTTPException as exc:
            yield _sse_payload("error", {"status_code": exc.status_code, "detail": exc.detail})
        except Exception as exc:
            yield _sse_payload("error", {"status_code": 500, "detail": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")
