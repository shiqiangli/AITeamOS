"""Pydantic models for Employee Chat API surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ChatEmployeeSummary(BaseModel):
    id: str
    display_name: str
    kind: str = "ai"
    role: str
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    skill_refs: list[str] = Field(default_factory=list)
    capability_tags: list[str] = Field(default_factory=list)
    personality_tags: list[str] = Field(default_factory=list)
    memory_scopes: list[str] = Field(default_factory=list)
    preferred_runtime: str = ""
    permission_policy: dict[str, Any] = Field(default_factory=dict)
    handoff_policy: dict[str, Any] = Field(default_factory=dict)
    current_load: dict[str, Any] = Field(default_factory=dict)
    ai_engine_mode: str = "external_or_file_stub"
    default_ai_engine: str = "system"
    preserve_engine_thread: bool = True
    default_thread_id: str = ""


class ChatSkillSummary(BaseModel):
    id: str
    title: str
    description: str = ""
    content: str = ""
    assigned_employees: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    saved_path: str
    source: str = "local"
    usage_count: int = 0
    last_used_at: str = ""
    last_used_by_employee_id: str = ""
    last_used_run_id: str = ""
    last_used_ticket_id: str = ""
    usefulness_stats: dict[str, Any] = Field(default_factory=dict)
    usage_history: list[dict[str, Any]] = Field(default_factory=list)


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    target_employee_id: str | None = None
    thread_id: str | None = None
    ticket_key: str | None = None
    approval_ref: str | None = None
    runtime_config: dict[str, Any] = Field(default_factory=dict)


class ChatTraceEvent(BaseModel):
    event: str
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    thread_id: str
    run_id: str
    target_employee: ChatEmployeeSummary
    engine_thread_id: str
    ticket_keys: list[str]
    reply: str
    trace_events: list[ChatTraceEvent]
    run_metadata: dict[str, Any] = Field(default_factory=dict)
    saved_paths: dict[str, str]


class ConversationMessage(BaseModel):
    timestamp: str
    role: str
    content: str
    employee_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    thread_id: str
    messages: list[ConversationMessage]
    thread: ChatThreadSummary | None = None


class ChatThreadSummary(BaseModel):
    id: str
    employee_id: str
    title: str
    created_at: str
    updated_at: str
    last_message_at: str | None = None
    message_count: int = 0
    archived: bool = False
    saved_path: str = ""


class ChatThreadListResponse(BaseModel):
    employee_id: str
    active_thread_id: str
    threads: list[ChatThreadSummary]


class ChatThreadCreateRequest(BaseModel):
    employee_id: str
    title: str | None = None


class ChatThreadActivateRequest(BaseModel):
    employee_id: str | None = None


class ChatAiEngineConfigField(BaseModel):
    id: str
    label: str
    kind: str = "text"
    value: str | bool | int | None = None
    placeholder: str = ""
    options: list[str] = Field(default_factory=list)
    required: bool = False
    secret: bool = False
    read_only: bool = False
    help: str = ""


class ChatAiEngineRecord(BaseModel):
    id: str
    display_name: str
    kind: str
    description: str = ""
    support_status: str = "supported"
    config_status: str = "not_configured"
    auth_kind: str = "none"
    base_url: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    thinking: str | None = None
    speed: str | None = None
    context_window: int | None = None
    max_tokens: int | None = None
    enabled: bool = True
    editable: bool = True
    active: bool = False
    api_key_configured: bool = False
    status: str = "missing"
    secret_env_vars: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    model_options: list[str] = Field(default_factory=list)
    thinking_options: list[str] = Field(default_factory=list)
    config_fields: list[ChatAiEngineConfigField] = Field(default_factory=list)
    chat_options: list[ChatAiEngineConfigField] = Field(default_factory=list)
    health_detail: str = ""


class ChatAiEngineUpdateRequest(BaseModel):
    model: str | None = None
    thinking: str | None = None
    speed: str | None = None
    context_window: int | None = None
    max_tokens: int | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    enabled: bool | None = None
    activate: bool = False


class ChatAiEngineSettings(BaseModel):
    active_engine: str = "deepseek"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: str = "enabled"
    openai_model: str = "gpt-5.5"
    fallback_on_error: bool = True
    engines: dict[str, ChatAiEngineRecord] = Field(default_factory=dict)
    api_keys_configured: dict[str, bool] = Field(default_factory=dict)
    catalog_order: list[str] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class ChatAiEngineSettingsRequest(BaseModel):
    active_engine: str = "deepseek"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: str = "enabled"
    openai_model: str = "gpt-5.5"
    fallback_on_error: bool = True


class ChatEmployeeAiEngineUpdateRequest(BaseModel):
    default_ai_engine: str = "system"


@dataclass
class ChatRunContext:
    request: ChatMessageRequest
    selected_profile: dict[str, Any]
    employee: ChatEmployeeSummary
    selected_ai_engine: str
    thread_id: str
    run_id: str
    ticket_keys: list[str]
    run_dirs: dict[str, Path]
    engine_state: dict[str, Any]
    engine_thread_id: str
    skills: list[str]
    memories: list[str]
    memory_refs: list[dict[str, Any]]
    recent_messages: list[ConversationMessage]
    trace_events: list[ChatTraceEvent]
