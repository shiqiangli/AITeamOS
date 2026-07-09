"""Route-free ChatRunContext assembly for API and LangGraph runtimes."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from .chat_ai_engine_service import ChatAiEngineSettingsService
from .chat_context_enrichment_service import build_initial_chat_context_assets
from .chat_employee_projection_service import ChatEmployeeProjectionService
from .chat_engine_thread_store import engine_thread_id, engine_thread_state
from .chat_models import ChatMessageRequest, ChatRunContext, ChatTraceEvent, ConversationMessage
from .chat_skill_service import skill_titles
from .chat_thread_store import ensure_run_dirs, load_conversation_messages
from .chat_ticket_key_service import extract_ticket_keys
from .employee_profile_service import load_employee_profiles


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class ChatRunPreparationNotFoundError(LookupError):
    """Raised when a requested Chat run entity cannot be found."""


class ChatRunPreparationService:
    def __init__(
        self,
        *,
        workspace_root: Path,
        workspace_dir: Path,
        now: Callable[[], str],
        allow_runtime_config_run_id: bool = False,
    ) -> None:
        self.workspace_root = workspace_root
        self.workspace_dir = workspace_dir
        self.now = now
        self.allow_runtime_config_run_id = allow_runtime_config_run_id
        self.employee_projection = ChatEmployeeProjectionService(workspace_dir=workspace_dir)
        self.ai_engine_settings = ChatAiEngineSettingsService(
            workspace_root=workspace_root,
            workspace_dir=workspace_dir,
            now=now,
        )

    def prepare(self, request: ChatMessageRequest) -> ChatRunContext:
        profiles = load_employee_profiles(workspace_root=self.workspace_root)
        selected = self.select_profile(
            profiles,
            requested_employee_id=request.target_employee_id,
            message=request.message,
        )
        employee = self.employee_projection.employee_summary(selected)
        selected_ai_engine = self.ai_engine_settings.runtime().selected_engine_for_employee(employee.default_ai_engine)
        thread_id = self.require_safe_id(
            request.thread_id or self.employee_projection.employee_default_thread_id(employee.id),
            field="thread_id",
        )
        run_id = self.graph_runtime_run_id(request) or f"run-{uuid4().hex[:12]}"
        ticket_keys = extract_ticket_keys(request.message, request.ticket_key)
        run_dirs = ensure_run_dirs(self.workspace_dir)
        recent_messages = self.load_thread_messages(thread_id, limit=12)
        current_engine_state = engine_thread_state(self.workspace_dir, employee.id, thread_id)
        external_engine_thread_id = str(
            current_engine_state.get("engine_thread_id")
            or engine_thread_id(self.workspace_dir, employee.id, thread_id)
        )
        skill_titles = self.skill_titles(employee.skills)
        context_assets = build_initial_chat_context_assets(
            message=request.message,
            employee_id=employee.id,
            ticket_keys=ticket_keys,
        )
        memory_refs = context_assets["memory_refs"]

        trace_events = [
            ChatTraceEvent(
                event="message.received",
                detail="User message accepted.",
                data={"thread_id": thread_id, "run_id": run_id, "ticket_keys": ticket_keys},
            ),
            ChatTraceEvent(
                event="employee.selected",
                detail=f"Routed to {employee.display_name}.",
                data={
                    "employee_id": employee.id,
                    "role": employee.role,
                    "default_ai_engine": employee.default_ai_engine,
                    "selected_ai_engine": selected_ai_engine,
                },
            ),
            ChatTraceEvent(
                event="context.loaded",
                detail="Loaded bundled Employee profile, skill, memory, knowledge, capability, and recent-message context.",
                data={
                    "skills": skill_titles,
                    "memory_count": context_assets["memory_count"],
                    "knowledge_count": context_assets["knowledge_count"],
                    "memory_and_knowledge_count": len(context_assets["memories"]),
                    "recalled_memory_refs": memory_refs,
                    "recent_message_count": len(recent_messages),
                    "command_intercept_policy": os.environ.get("AITEAMOS_CHAT_KERNEL_COMMANDS", "fallback"),
                },
            ),
            ChatTraceEvent(
                event="engine_thread.resolved",
                detail="Resolved stable external AI Engine thread mapping.",
                data={
                    "ai_engine": current_engine_state.get("ai_engine", "file_stub"),
                    "engine_thread_id": external_engine_thread_id,
                },
            ),
        ]
        if ticket_keys:
            trace_events.append(
                ChatTraceEvent(
                    event="ticket.detected",
                    detail="Detected Ticket key(s) in the request.",
                    data={"ticket_keys": ticket_keys},
                )
            )

        return ChatRunContext(
            request=request,
            selected_profile=selected,
            employee=employee,
            selected_ai_engine=selected_ai_engine,
            thread_id=thread_id,
            run_id=run_id,
            ticket_keys=ticket_keys,
            run_dirs=run_dirs,
            engine_state=current_engine_state,
            engine_thread_id=external_engine_thread_id,
            skills=skill_titles,
            memories=context_assets["memories"],
            memory_refs=memory_refs,
            recent_messages=recent_messages,
            trace_events=trace_events,
        )

    def select_profile(
        self,
        profiles: list[dict],
        *,
        requested_employee_id: str | None,
        message: str,
    ) -> dict:
        try:
            return self.employee_projection.select_profile(
                profiles,
                requested_employee_id=requested_employee_id,
                message=message,
            )
        except KeyError as exc:
            raise ChatRunPreparationNotFoundError(f"Employee not found: {requested_employee_id}") from exc

    def graph_runtime_run_id(self, request: ChatMessageRequest) -> str:
        if not self.allow_runtime_config_run_id:
            return ""
        runtime_config = request.runtime_config if isinstance(request.runtime_config, dict) else {}
        if runtime_config.get("source") != "aiteamos_workbench_graph":
            return ""
        requested = str(runtime_config.get("run_id") or "").strip()
        return self.require_safe_id(requested, field="run_id") if requested else ""

    def load_thread_messages(self, thread_id: str, *, limit: int | None = None) -> list[ConversationMessage]:
        return load_conversation_messages(
            self.workspace_dir,
            thread_id,
            message_model=ConversationMessage,
            require_safe_id=lambda value: self.require_safe_id(value, field="thread_id"),
            limit=limit,
        )

    def skill_titles(self, skill_ids: list[str]) -> list[str]:
        return skill_titles(skill_ids, workspace_root=self.workspace_root, workspace_dir=self.workspace_dir)

    @staticmethod
    def require_safe_id(value: str, *, field: str) -> str:
        if not SAFE_ID_RE.fullmatch(value):
            raise ValueError(f"Invalid {field}")
        return value
