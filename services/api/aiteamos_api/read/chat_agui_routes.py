"""AG-UI compatibility endpoints for AITeamOS Chat.

These endpoints are optional compatibility protocol surfaces. The primary Chat
path stays on the LangGraph/LangChain runtime contract directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ag_ui.core import RunAgentInput
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .chat_agui_service import AguiChatCompatibilityAdapter
from .chat_execution_service import ChatStreamEvent
from .chat_models import ChatMessageRequest
from .chat_runtime_factory import build_chat_execution_runtime, run_chat_message, workspace_dir, workspace_root

router = APIRouter(prefix="/api/v1/chat", tags=["employee-chat-agui-compatibility"])

_agui_chat_adapter: AguiChatCompatibilityAdapter | None = None
_agui_chat_adapter_workspace: Path | None = None


async def _agui_send_message_payload(text: str, state: dict[str, Any], thread_id: str) -> dict[str, Any]:
    response = await run_chat_message(
        ChatMessageRequest(
            message=text,
            target_employee_id=state.get("target_employee_id"),
            thread_id=thread_id,
            ticket_key=state.get("ticket_key"),
            approval_ref=state.get("approval_ref"),
        )
    )
    return response.model_dump(mode="json")


def _stream_chat_turn(request: ChatMessageRequest) -> AsyncIterator[ChatStreamEvent]:
    return build_chat_execution_runtime().stream_turn(request)


def _get_agui_chat_adapter() -> AguiChatCompatibilityAdapter:
    global _agui_chat_adapter, _agui_chat_adapter_workspace
    workspace = workspace_root()
    if _agui_chat_adapter is None or _agui_chat_adapter_workspace != workspace:
        _agui_chat_adapter = AguiChatCompatibilityAdapter(
            workspace_root=workspace,
            workspace_dir=workspace_dir(),
            responder=_agui_send_message_payload,
            stream_turn=_stream_chat_turn,
        )
        _agui_chat_adapter_workspace = workspace
    return _agui_chat_adapter


@router.post("/agent")
async def stream_agui_chat_agent(input_data: RunAgentInput, request: Request) -> StreamingResponse:
    return _get_agui_chat_adapter().stream_response(
        input_data,
        accept=request.headers.get("accept"),
        target_employee_id=(
            request.query_params.get("target_employee_id")
            or request.headers.get("X-AITeamOS-Target-Employee-Id")
        ),
        ticket_key=(
            request.query_params.get("ticket_key")
            or request.headers.get("X-AITeamOS-Ticket-Key")
        ),
        approval_ref=(
            request.query_params.get("approval_ref")
            or request.headers.get("X-AITeamOS-Approval-Ref")
        ),
    )


@router.get("/agent/health")
async def agui_chat_agent_health() -> dict[str, Any]:
    return _get_agui_chat_adapter().health()
