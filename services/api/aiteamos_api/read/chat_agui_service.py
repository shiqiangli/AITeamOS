"""AG-UI compatibility adapter for AITeamOS Chat.

The main Chat runtime is LangGraph/LangChain-owned. This module isolates the
optional AG-UI protocol bridge, event stream mapping, and checkpoint
persistence so AG-UI does not leak into the primary Chat route.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any, Awaitable, Callable, TypedDict
from uuid import uuid4

from ag_ui.core import (
    MessagesSnapshotEvent,
    RunAgentInput,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
)
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .agui_chat_utils import (
    agui_message_payload,
    checkpoint_id_from_config,
    latest_agui_user_message_text,
    latest_agui_user_message_payload,
    latest_human_message_text,
    message_content_to_text,
)
from .chat_execution_service import ChatStreamEvent
from .chat_models import ChatMessageRequest, ChatMessageResponse
from .chat_streaming_utils import reply_chunks

try:  # The dependency is explicit in pyproject, but keep dev checkouts bootable.
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    SqliteSaver = None  # type: ignore[assignment]


class AiteamosChatGraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    target_employee_id: str | None
    ticket_key: str | None
    approval_ref: str | None
    aiteamos_chat_response: dict[str, Any]


AguiChatResponder = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]
AguiChatStreamRunner = Callable[[ChatMessageRequest], AsyncIterator[ChatStreamEvent]]


class AguiChatCompatibilityAdapter:
    def __init__(
        self,
        *,
        workspace_root: Path,
        workspace_dir: Path,
        responder: AguiChatResponder,
        stream_turn: AguiChatStreamRunner,
    ) -> None:
        self._bridge = AguiChatAgentBridge(
            workspace_root=workspace_root,
            workspace_dir=workspace_dir,
            responder=responder,
        )
        self._stream_turn = stream_turn

    def health(self) -> dict[str, Any]:
        return self._bridge.health()

    def stream_response(
        self,
        input_data: RunAgentInput,
        *,
        accept: str | None,
        target_employee_id: str | None,
        ticket_key: str | None,
        approval_ref: str | None = None,
    ) -> StreamingResponse:
        encoder = EventEncoder(accept=accept)
        enriched_input = self._bridge.enrich_input(
            input_data,
            target_employee_id=target_employee_id,
            ticket_key=ticket_key,
            approval_ref=approval_ref,
        )

        async def event_generator() -> AsyncIterator[str | bytes]:
            async for event in self.stream_events(enriched_input):
                yield encoder.encode(event)

        return StreamingResponse(event_generator(), media_type=encoder.get_content_type())

    async def stream_events(self, input_data: RunAgentInput) -> AsyncIterator[Any]:
        thread_id = input_data.thread_id
        run_id = input_data.run_id
        yield RunStartedEvent(thread_id=thread_id, run_id=run_id, input=input_data)

        user_text = latest_agui_user_message_text(list(input_data.messages or []))
        assistant_message_id = f"{run_id}-assistant"
        yield TextMessageStartEvent(message_id=assistant_message_id)

        accumulated = ""
        final_response: ChatMessageResponse | None = None
        try:
            if not user_text:
                accumulated = "I did not receive a user message to process."
                yield TextMessageContentEvent(message_id=assistant_message_id, delta=accumulated)
            else:
                state = self._bridge.state(input_data)
                request = ChatMessageRequest(
                    message=user_text,
                    target_employee_id=state.get("target_employee_id"),
                    thread_id=thread_id,
                    ticket_key=state.get("ticket_key"),
                    approval_ref=state.get("approval_ref"),
                )
                async for event, payload in self._stream_turn(request):
                    if event == "delta":
                        text = str(payload)
                        accumulated += text
                        yield TextMessageContentEvent(message_id=assistant_message_id, delta=text)
                    elif event == "final":
                        final_response = (
                            payload
                            if isinstance(payload, ChatMessageResponse)
                            else ChatMessageResponse.model_validate(payload)
                        )

                if final_response is not None and not accumulated:
                    for chunk in reply_chunks(final_response.reply):
                        accumulated += chunk
                        yield TextMessageContentEvent(message_id=assistant_message_id, delta=chunk)
                        await asyncio.sleep(0)

            yield TextMessageEndEvent(message_id=assistant_message_id)
            snapshot = self._bridge.state(input_data)
            if final_response is not None:
                snapshot["aiteamos_chat_response"] = final_response.model_dump(mode="json")
                snapshot["langgraph_checkpoint"] = await self._bridge.persist_checkpoint(
                    input_data,
                    final_response_payload=final_response.model_dump(mode="json"),
                    assistant_message_id=assistant_message_id,
                    assistant_text=accumulated,
                )
            yield StateSnapshotEvent(snapshot=snapshot)

            messages = [agui_message_payload(message) for message in input_data.messages or []]
            messages = [message for message in messages if message.get("role") and "content" in message]
            messages.append({"id": assistant_message_id, "role": "assistant", "content": accumulated})
            yield MessagesSnapshotEvent(messages=messages)
            yield RunFinishedEvent(thread_id=thread_id, run_id=run_id)
        except HTTPException as exc:
            yield TextMessageEndEvent(message_id=assistant_message_id)
            yield RunErrorEvent(message=str(exc.detail), code=str(exc.status_code))
        except Exception as exc:
            yield TextMessageEndEvent(message_id=assistant_message_id)
            yield RunErrorEvent(message=str(exc), code="500")


class AguiChatAgentBridge:
    def __init__(
        self,
        *,
        workspace_root: Path,
        workspace_dir: Path,
        responder: AguiChatResponder,
    ) -> None:
        self.workspace_root = workspace_root
        self.workspace_dir = workspace_dir
        self._responder = responder
        self._agent: LangGraphAgent | None = None
        self._checkpoint_connection: sqlite3.Connection | None = None
        self._checkpoint_status: dict[str, Any] = {"mode": "uninitialized"}

    def enrich_input(
        self,
        input_data: RunAgentInput,
        *,
        target_employee_id: str | None,
        ticket_key: str | None,
        approval_ref: str | None = None,
    ) -> RunAgentInput:
        state = input_data.state if isinstance(input_data.state, dict) else {}
        next_state: dict[str, Any] = dict(state)
        forwarded_props = input_data.forwarded_props if isinstance(input_data.forwarded_props, dict) else {}

        selected_employee_id = target_employee_id or forwarded_props.get("target_employee_id")
        selected_ticket_key = ticket_key or forwarded_props.get("ticket_key")
        selected_approval_ref = approval_ref or forwarded_props.get("approval_ref")
        if selected_employee_id:
            next_state["target_employee_id"] = str(selected_employee_id)
        if selected_ticket_key:
            next_state["ticket_key"] = str(selected_ticket_key)
        if selected_approval_ref:
            next_state["approval_ref"] = str(selected_approval_ref)
        return input_data.model_copy(update={"state": next_state})

    def health(self) -> dict[str, Any]:
        agent = self.agent()
        return {
            "status": "ok",
            "agent": {"name": agent.name},
            "checkpoint": self._checkpoint_status,
        }

    async def persist_checkpoint(
        self,
        input_data: RunAgentInput,
        *,
        final_response_payload: dict[str, Any] | None,
        assistant_message_id: str,
        assistant_text: str,
    ) -> dict[str, Any]:
        if final_response_payload is None:
            return {"status": "skipped", "reason": "no_final_response"}

        user_payload = latest_agui_user_message_payload(list(input_data.messages or []))
        user_text = message_content_to_text(user_payload.get("content")) if user_payload else ""
        if not user_text:
            return {"status": "skipped", "reason": "no_user_message"}

        state = self.state(input_data)
        target_employee = final_response_payload.get("target_employee")
        values: AiteamosChatGraphState = {
            "messages": [
                HumanMessage(
                    content=user_text,
                    id=str(user_payload.get("id") or f"{input_data.run_id}-user"),
                ),
                AIMessage(
                    content=assistant_text,
                    id=assistant_message_id,
                    response_metadata={"aiteamos": final_response_payload},
                ),
            ],
            "target_employee_id": (
                str(target_employee.get("id"))
                if isinstance(target_employee, dict) and target_employee.get("id")
                else None
            ),
            "ticket_key": str(state.get("ticket_key")) if state.get("ticket_key") else None,
            "aiteamos_chat_response": final_response_payload,
        }
        config: RunnableConfig = {"configurable": {"thread_id": input_data.thread_id}}

        try:
            graph = self.agent().graph
            next_config = graph.update_state(config, values, as_node="aiteamos_chat")
            snapshot = graph.get_state(next_config)
        except Exception as exc:  # Keep chat usable if checkpoint persistence fails.
            return {
                "status": "error",
                "detail": str(exc),
                "backend": self._checkpoint_status,
            }

        return {
            "status": "persisted",
            "thread_id": input_data.thread_id,
            "checkpoint_id": checkpoint_id_from_config(next_config),
            "next": list(snapshot.next),
            "backend": self._checkpoint_status,
        }

    @staticmethod
    def state(input_data: RunAgentInput) -> dict[str, Any]:
        return dict(input_data.state) if isinstance(input_data.state, dict) else {}

    def agent(self) -> LangGraphAgent:
        if self._agent is None:
            self._agent = self._build_agent()
        return self._agent

    async def _run_node(
        self,
        state: AiteamosChatGraphState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        text = latest_human_message_text(list(state.get("messages", [])))
        if not text:
            return {
                "messages": [
                    AIMessage(
                        content="I did not receive a user message to process.",
                        id=f"assistant-{uuid4().hex[:12]}",
                    )
                ]
            }

        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        thread_id = str(configurable.get("thread_id") or f"thread-{uuid4().hex[:12]}")
        payload = await self._responder(text, dict(state), thread_id)
        reply = str(payload.get("reply") or "")
        run_id = str(payload.get("run_id") or uuid4().hex[:12])
        return {
            "messages": [
                AIMessage(
                    content=reply,
                    id=f"{run_id}-assistant",
                    response_metadata={"aiteamos": payload},
                )
            ],
            "aiteamos_chat_response": payload,
        }

    def _checkpoint_path(self) -> Path:
        return self.workspace_dir / "langgraph" / "checkpoints.sqlite"

    def _build_checkpointer(self) -> Any:
        if SqliteSaver is None:
            self._checkpoint_status = {
                "mode": "memory_fallback",
                "detail": "langgraph-checkpoint-sqlite is not installed",
            }
            return InMemorySaver()

        path = self._checkpoint_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if self._checkpoint_connection is not None:
            self._checkpoint_connection.close()
        self._checkpoint_connection = sqlite3.connect(path, check_same_thread=False)
        saver = SqliteSaver(self._checkpoint_connection)
        saver.setup()
        self._checkpoint_status = {
            "mode": "sqlite",
            "path": str(path.relative_to(self.workspace_root)),
        }
        return saver

    def _build_agent(self) -> LangGraphAgent:
        builder = StateGraph(AiteamosChatGraphState)
        builder.add_node("aiteamos_chat", self._run_node)
        builder.add_edge(START, "aiteamos_chat")
        builder.add_edge("aiteamos_chat", END)
        graph = builder.compile(checkpointer=self._build_checkpointer())
        return LangGraphAgent(
            name="AITeamOS Clara",
            description="AG-UI/LangGraph bridge for file-backed AITeamOS Chat.",
            graph=graph,
        )
