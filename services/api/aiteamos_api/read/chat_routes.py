"""
File-backed Employee Chat routes.

P0 intentionally avoids database dependencies. Employee profiles, conversation
history, trace events, and external AI Engine thread mappings live under the
local .aiteamos workspace directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Callable, TypedDict
from uuid import uuid4

import httpx
import yaml
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
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from .agui_chat_utils import (
    agui_message_payload as _agui_message_payload,
    checkpoint_id_from_config as _checkpoint_id_from_config,
    latest_agui_user_message_payload as _latest_agui_user_message_payload,
    latest_agui_user_message_text as _latest_agui_user_message_text,
    latest_human_message_text as _latest_human_message_text,
    message_content_to_text as _message_content_to_text,
    reply_chunks as _reply_chunks,
    sse_payload as _sse_payload,
)
from .ai_engine_catalog import AI_ENGINE_CATALOG, SUPPORTED_AI_ENGINE_IDS
from .ai_engine_clients import (
    call_deepseek_chat_completion as _call_deepseek_chat_completion,
    call_openai_responses as _call_openai_responses,
    extract_openai_text as _extract_openai_text,
)
from .ai_engine_config_store import (
    ai_engine_file_payload as _store_ai_engine_file_payload,
    ai_engine_secrets as _store_ai_engine_secrets,
    field_value as _field_value,
    load_ai_engine_config as _store_load_ai_engine_config,
    normalize_int_setting as _normalize_int_setting,
    normalize_openai_reasoning_effort as _normalize_openai_reasoning_effort,
    normalize_openai_speed as _normalize_openai_speed,
    normalize_thinking as _normalize_thinking,
    secret_configured as _secret_configured,
    write_json_file as _write_json_file,
)
from .ai_engine_context import (
    build_ai_engine_context_gate as _build_ai_engine_context_gate,
    build_employee_agent_context_bundle as _build_employee_agent_context_bundle,
    format_context_list as _format_context_list,
    message_prefers_chinese as _message_prefers_chinese,
    trim_context_text as _trim_context_text,
)
from .ai_engine_errors import (
    build_ai_engine_configuration_reply as _build_ai_engine_configuration_reply,
    safe_ai_engine_error_summary as _safe_ai_engine_error_summary,
)
from .ai_engine_runtime_config import AiEngineRuntimeConfig as _AiEngineRuntimeConfig
from .ai_engine_selection import (
    normalize_ai_engine as _normalize_ai_engine,
    normalize_employee_default_ai_engine as _normalize_employee_default_ai_engine,
)
from .chat_action_plan import (
    ChatKernelCommandPlan,
    chat_action_plan_from_kernel_plan as _chat_action_plan_from_kernel_plan,
    kernel_plan_from_chat_action_plan as _kernel_plan_from_chat_action_plan,
    normalize_chat_action_plan as _normalize_chat_action_plan,
    normalize_kernel_command_plan as _normalize_kernel_command_plan,
    plan_trace_data as _plan_trace_data,
)
from .chat_trace_utils import (
    append_jsonl as _append_jsonl,
)
from .chat_thread_store import (
    conversation_path as _store_conversation_path,
    conversation_saved_path as _store_conversation_saved_path,
    ensure_run_dirs as _store_ensure_run_dirs,
    load_conversation_messages as _store_load_conversation_messages,
    load_thread_index as _store_load_thread_index,
    thread_index_path as _store_thread_index_path,
    thread_index_saved_path as _store_thread_index_saved_path,
    thread_title_from_message as _store_thread_title_from_message,
    threads_dir as _store_threads_dir,
    write_thread_index as _store_write_thread_index,
)
from .chat_tool_args import (
    clean_extracted_value as _clean_extracted_value_data,
    dedupe as _dedupe_data,
    listify_tool_arg as _listify_tool_arg_data,
    split_list_value as _split_list_value_data,
    stringify_tool_arg as _stringify_tool_arg_data,
    tool_arg as _tool_arg_data,
)
from .chat_kernel_catalog import (
    COMMAND_PLANNING_SIGNAL_RE as _COMMAND_PLANNING_SIGNAL_RE,
    COMMAND_ID_TO_CHAT_ACTION as _COMMAND_ID_TO_CHAT_ACTION,
    KERNEL_COMMAND_SPECS as _KERNEL_COMMAND_SPECS,
)
from .chat_kernel_execution import (
    kernel_command_from_handler_result as _kernel_command_from_handler_result_data,
    kernel_command_from_plan as _kernel_command_from_plan_data,
    kernel_policy_blocked_reply as _kernel_policy_blocked_reply,
    kernel_policy_blocked_result as _kernel_policy_blocked_result,
)
from .chat_kernel_permission_utils import (
    build_permissions_reply as _build_permissions_reply,
    command_access_rows as _command_access_rows,
)
from .chat_kernel_planning import (
    chat_kernel_command_intercept_enabled as _chat_kernel_command_intercept_enabled_data,
    local_kernel_heuristics_allowed as _local_kernel_heuristics_allowed_data,
    should_use_llm_command_planner as _should_use_llm_command_planner_data,
)
from .chat_kernel_reply_utils import build_blocked_command_reply as _build_blocked_command_reply
from .chat_response_metadata import (
    ai_engine_event_metadata as _ai_engine_event_metadata_data,
    build_run_metadata as _build_run_metadata_data,
    build_stub_reply as _build_stub_reply,
)
from . import chat_request_classifiers as _request_classifier
from .chat_terminal_utils import (
    extract_terminal_command_line as _extract_terminal_command_line,
    is_terminal_run_request as _is_terminal_run_request,
    terminal_argv_from_command as _terminal_argv_from_command,
    terminal_cwd_from_raw as _terminal_cwd_from_raw,
    terminal_evidence_ref as _terminal_evidence_ref,
    terminal_reply as _terminal_reply,
    terminal_report_content as _terminal_report_content,
    run_terminal_command_collect as _run_terminal_command_collect,
    validate_terminal_workspace_args as _validate_terminal_workspace_args,
)
from .chat_engine_thread_store import (
    delete_engine_thread_states as _delete_engine_thread_states,
    delete_thread_engine_state_mappings as _delete_thread_engine_state_mappings,
    engine_thread_id as _engine_thread_id,
    engine_thread_state as _engine_thread_state,
    save_engine_thread_state as _save_engine_thread_state,
)
from .capability_service import local_kernel_command_ids, local_kernel_command_prompt, local_kernel_command_union
from .kernel_command_service import (
    KernelCommand,
    KernelCommandSpec,
    evaluate_kernel_policy,
    expand_employee_permissions,
)
from .knowledge_service import knowledge_snippets, search_knowledge_sync
from .memory_service import propose_memory_from_chat_turn, recall_memory_records, record_memory_recall_usage, search_memory
from .repository_service import CodeRepository, get_code_repository, inspect_code_repository, list_code_repositories
from .ticket_service import (
    TicketCreateRequest,
    TicketReportRequest,
    TicketValidationRequest,
    add_ticket_report,
    create_ticket,
    get_ticket,
    list_tickets,
    request_ticket_validation,
    self_bootstrap_learning_summary,
)
from .validation_skill_catalog import VALIDATION_SKILL_DEFINITIONS, ValidationSkillDefinition

try:  # The dependency is explicit in pyproject, but keep dev checkouts bootable.
    from langgraph.checkpoint.sqlite import SqliteSaver
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    SqliteSaver = None  # type: ignore[assignment]

router = APIRouter(prefix="/api/v1/chat", tags=["employee-chat"])

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_LOCAL_TICKET_ID_RE = re.compile(r"\b(?:ticket-[A-Za-z0-9_.:-]+|(?:rd|pv|arch|rel|mem|doc|ops|trace)-\d{4,})\b", re.IGNORECASE)
_TICKET_KEY_RE = re.compile(
    r"\b[A-Z][A-Z0-9]+-\d+\b|\b(?:ticket-[A-Za-z0-9_.:-]+|(?:rd|pv|arch|rel|mem|doc|ops|trace)-\d{4,})\b",
    re.IGNORECASE,
)
_DELETE_EMPLOYEE_EN_RE = re.compile(r"\b(delete|remove|drop)\b.*\b(employee|profile|user|employee)\b")
_ASSIGN_SKILL_EN_RE = re.compile(r"\b(assign|add|give|attach)\b.*\bskill\b.*\b(to|for)\b")
_DELETE_SKILL_EN_RE = re.compile(r"\b(delete|remove|drop)\b.*\bskill\b")
_FILE_PATH_RE = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:css|html|json|md|py|sh|toml|ts|tsx|txt|yaml|yml)"
)
CLARA_SYSTEM_EMPLOYEE_ID = "clara"
CLARA_SYSTEM_DISPLAY_NAME = "Clara"
CLARA_SYSTEM_ROLE = "AI Team OS Manager"
_CORE_EMPLOYEE_GAPS: dict[str, tuple[str, ...]] = {
    "AI Architect": ("architect", "架构"),
    "AI PV": ("pv", "verification", "验证"),
    "AI Release": ("release", "发布"),
    "AI QA / Harness Runner": ("qa", "harness", "test runner", "测试"),
    "AI Memory Curator": ("memory curator", "memory", "记忆"),
}
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AI Architect", ("architect", "架构")),
    ("AI PV", ("ai pv", " pv", "verification", "验证")),
    ("AI Release", ("release", "发布")),
    ("AI QA / Harness Runner", ("qa", "harness", "test runner", "测试")),
    ("AI Memory Curator", ("memory curator", "memory", "记忆")),
    ("AI RD / Implementer", ("implementer", "developer", "engineer", " rd", "研发", "开发")),
    ("AI Team OS Manager", ("clara", "ai team os", "os manager", "系统管理", "团队运营")),
)
_ROLE_DEFAULT_SKILLS: dict[str, list[str]] = {
    "AI Team OS Manager": [
        "ticket-specification",
        "employee-ticket-flow-design",
        "technical-decision",
        "validation-strategy",
        "product-model-review",
    ],
    "AI Architect": ["system-architecture-design", "architecture-review", "technical-decision", "product-model-review"],
    "AI PV": ["test-engineering", "validation-strategy", "evidence-review", "regression-check", "product-model-review"],
    "AI Release": ["resource-planning", "validation-strategy", "evidence-review", "regression-check"],
    "AI QA / Harness Runner": ["test-engineering", "validation-strategy", "evidence-review", "regression-check"],
    "AI Memory Curator": ["technical-decision"],
    "AI RD / Implementer": ["backend-api-implementation", "frontend-api-integration", "test-engineering"],
}


class ChatEmployeeSummary(BaseModel):
    id: str
    display_name: str
    kind: str = "ai"
    role: str
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
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


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    target_employee_id: str | None = None
    thread_id: str | None = None
    ticket_key: str | None = None


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
    thread: "ChatThreadSummary | None" = None


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


class AiteamosChatGraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    target_employee_id: str | None
    ticket_key: str | None
    aiteamos_chat_response: dict[str, Any]


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


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _workspace_root() -> Path:
    explicit = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def _workspace_dir() -> Path:
    return _workspace_root() / ".aiteamos"


def _ai_engine_settings_path() -> Path:
    return _workspace_dir() / "ai_engines.json"


def _require_employee_default_ai_engine(value: str) -> str:
    raw = (value or "").strip().lower()
    engine = _normalize_employee_default_ai_engine(value)
    allowed = {"", "active", "default", "global", "settings", "system", "system_default", "fallback", "file_stub", "file-stub", *SUPPORTED_AI_ENGINE_IDS}
    if raw in allowed:
        return engine
    raise HTTPException(status_code=400, detail=f"Unsupported Employee default AI Engine: {value}")


def _require_ai_engine(value: str) -> str:
    engine = (value or "").strip().lower()
    if engine not in AI_ENGINE_CATALOG:
        raise HTTPException(status_code=400, detail=f"Unsupported AI Engine: {value}")
    if engine not in SUPPORTED_AI_ENGINE_IDS:
        raise HTTPException(status_code=400, detail=f"AI Engine is not configurable yet: {value}")
    return engine


def _ai_engine_config() -> dict[str, Any]:
    return _store_load_ai_engine_config(_ai_engine_settings_path())


def _ai_engine_secrets() -> dict[str, str]:
    return _store_ai_engine_secrets(_ai_engine_config())


def _ai_engine_runtime() -> _AiEngineRuntimeConfig:
    return _AiEngineRuntimeConfig(config=_ai_engine_config(), secrets=_ai_engine_secrets())


def _config_fields(
    *,
    catalog: dict[str, Any],
    engine_config: dict[str, Any],
    editable: bool,
    field_key: str,
) -> list[ChatAiEngineConfigField]:
    fields = catalog.get(field_key) if isinstance(catalog.get(field_key), list) else []
    result: list[ChatAiEngineConfigField] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        field_id = str(field.get("id") or "")
        if not field_id:
            continue
        result.append(
            ChatAiEngineConfigField(
                id=field_id,
                label=str(field.get("label") or field_id.replace("_", " ").title()),
                kind=str(field.get("kind") or "text"),
                value=_field_value(engine_config, field_id),
                placeholder=str(field.get("placeholder") or ""),
                options=[str(option) for option in field.get("options", [])],
                required=bool(field.get("required", False)),
                secret=bool(field.get("secret", False)),
                read_only=bool(field.get("read_only", False)) or not editable,
                help=str(field.get("help") or ""),
            )
        )
    return result


def _ai_engine_records(config: dict[str, Any], secrets: dict[str, str]) -> dict[str, ChatAiEngineRecord]:
    active_engine = str(config["active_engine"])
    engine_configs = config.get("engine_configs") if isinstance(config.get("engine_configs"), dict) else {}
    records: dict[str, ChatAiEngineRecord] = {}
    for engine_id, catalog in AI_ENGINE_CATALOG.items():
        engine_config = engine_configs.get(engine_id) if isinstance(engine_configs.get(engine_id), dict) else {}
        support_status = str(catalog.get("support_status") or "planned")
        editable = support_status == "supported"
        api_key_configured = _secret_configured(engine_config)
        if support_status == "planned":
            config_status = "planned"
        elif api_key_configured:
            config_status = "configured"
        else:
            config_status = "missing_secret"
        secret_env_vars = [str(engine_config["api_key_env"])] if engine_config.get("api_key_env") else []
        health_detail = {
            "configured": "Ready for Chat selection.",
            "missing_secret": "Configuration is saved, but the referenced API key environment variable is missing.",
            "planned": "Catalog entry is visible for planning, but the adapter is not enabled yet.",
        }.get(config_status, "Status has not been checked.")
        records[engine_id] = ChatAiEngineRecord(
            id=engine_id,
            display_name=str(catalog.get("display_name") or engine_id),
            kind=str(catalog.get("kind") or "llm_api"),
            description=str(catalog.get("description") or ""),
            support_status=support_status,
            config_status=config_status,
            auth_kind=str(catalog.get("auth_kind") or "none"),
            base_url=str(engine_config.get("base_url") or "") or None,
            api_key_env=str(engine_config.get("api_key_env") or "") or None,
            model=str(engine_config.get("model") or "") or None,
            thinking=str(engine_config.get("thinking") or "") or None,
            speed=str(engine_config.get("speed") or "") or None,
            context_window=int(engine_config["context_window"]) if engine_config.get("context_window") is not None else None,
            max_tokens=int(engine_config["max_tokens"]) if engine_config.get("max_tokens") is not None else None,
            enabled=bool(engine_config.get("enabled", True)),
            editable=editable,
            active=active_engine == engine_id,
            api_key_configured=api_key_configured,
            status=config_status,
            secret_env_vars=secret_env_vars,
            capabilities=[str(capability) for capability in catalog.get("capabilities", [])],
            model_options=[str(option) for option in catalog.get("model_options", [])],
            thinking_options=[str(option) for option in catalog.get("thinking_options", [])],
            config_fields=_config_fields(catalog=catalog, engine_config=engine_config, editable=editable, field_key="config_fields"),
            chat_options=_config_fields(catalog=catalog, engine_config=engine_config, editable=editable, field_key="chat_options"),
            health_detail=health_detail,
        )
    return records


def _ai_engine_file_payload(config: dict[str, Any]) -> dict[str, Any]:
    return _store_ai_engine_file_payload(config, updated_at=_now())


def _ai_engine_settings_response() -> ChatAiEngineSettings:
    config = _ai_engine_config()
    secrets = _ai_engine_secrets()
    records = _ai_engine_records(config, secrets)
    return ChatAiEngineSettings(
        **config,
        engines=records,
        api_keys_configured={
            engine_id: record.api_key_configured
            for engine_id, record in records.items()
        },
        catalog_order=list(AI_ENGINE_CATALOG.keys()),
        saved_paths={
            "ai_engines": str(_ai_engine_settings_path().relative_to(_workspace_root())),
        },
    )


def _require_safe_id(value: str, *, field: str) -> str:
    if not _SAFE_ID_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


def _safe_thread_component(value: str) -> str:
    component = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip()).strip("-")
    return component[:80] or "employee"


def _employee_default_thread_id(employee_id: str) -> str:
    return _require_safe_id(f"employee-{_safe_thread_component(employee_id)}-default", field="thread_id")


def _is_clara_system_employee_id(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized == CLARA_SYSTEM_EMPLOYEE_ID


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read {path.name}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail=f"Invalid employee profile: {path.name}")
    return data


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _normalize_employee_profile(profile: dict[str, Any], path: Path) -> dict[str, Any]:
    normalized = dict(profile)
    profile_id = str(normalized.get("id") or path.stem)
    normalized["id"] = profile_id

    if _is_clara_system_employee_id(profile_id):
        default_profile = _default_clara_profile()
        normalized["id"] = CLARA_SYSTEM_EMPLOYEE_ID
        normalized["display_name"] = CLARA_SYSTEM_DISPLAY_NAME
        normalized["kind"] = "ai"
        normalized["role"] = CLARA_SYSTEM_ROLE
        normalized["summary"] = default_profile["summary"]
        normalized["personality"] = default_profile["personality"]
        normalized["responsibilities"] = default_profile["responsibilities"]
        if not normalized.get("skills"):
            normalized["skills"] = _default_skills_for_role(CLARA_SYSTEM_ROLE)
        normalized["permissions"] = default_profile["permissions"]

        ai_engine = normalized.get("ai_engine") if isinstance(normalized.get("ai_engine"), dict) else {}
        ai_engine = dict(ai_engine)
        engine_identity = str(ai_engine.get("engine_identity") or "").strip()
        if not engine_identity:
            ai_engine["engine_identity"] = CLARA_SYSTEM_EMPLOYEE_ID
        ai_engine["preserve_engine_thread"] = True
        normalized["ai_engine"] = ai_engine
        normalized["system"] = {"protected": True, "bootstrap": True}

    kind = str(normalized.get("kind") or "ai")
    role = str(normalized.get("role") or "AI Employee")
    permissions = normalized.get("permissions")
    if not isinstance(permissions, list) or not permissions:
        normalized["permissions"] = _default_permissions(kind, role)

    ai_engine = normalized.get("ai_engine") if isinstance(normalized.get("ai_engine"), dict) else {}
    ai_engine = dict(ai_engine)
    ai_engine.setdefault("mode", "human" if kind == "human" else "external_or_file_stub")
    ai_engine.setdefault("engine_identity", profile_id)
    ai_engine.setdefault("preserve_engine_thread", True)
    ai_engine["default_engine"] = _normalize_employee_default_ai_engine(
        str(ai_engine.get("default_engine") or ai_engine.get("default_ai_engine") or "system")
    )
    normalized["ai_engine"] = ai_engine

    return normalized


def _ensure_clara_system_employee() -> dict[str, Any]:
    profile_path = _employee_profile_path(CLARA_SYSTEM_EMPLOYEE_ID)
    if profile_path.exists():
        raw_profile = _read_yaml(profile_path)
    else:
        raw_profile = _default_clara_profile()
    normalized = _normalize_employee_profile(raw_profile, profile_path)
    if raw_profile != normalized or not profile_path.exists():
        normalized["updated_at"] = _now()
        normalized.setdefault("created_at", _now())
        _write_yaml(profile_path, normalized)
    return normalized


def _load_employees() -> list[dict[str, Any]]:
    employees_dir = _employees_dir()
    _ensure_clara_system_employee()

    employees_by_id: dict[str, dict[str, Any]] = {}
    for path in sorted(employees_dir.glob("*.yaml")):
        profile = _normalize_employee_profile(_read_yaml(path), path)
        profile_id = str(profile.get("id") or path.stem).lower()
        existing = employees_by_id.get(profile_id)
        if existing is None or path.stem == profile.get("id"):
            employees_by_id[profile_id] = profile

    return list(employees_by_id.values()) or [_ensure_clara_system_employee()]


def _default_clara_profile() -> dict[str, Any]:
    return {
        "id": CLARA_SYSTEM_EMPLOYEE_ID,
        "display_name": CLARA_SYSTEM_DISPLAY_NAME,
        "kind": "ai",
        "role": CLARA_SYSTEM_ROLE,
        "summary": (
            "User-facing AI Team OS Manager for Ticket flow, delegation, validation, "
            "assets, and final reporting."
        ),
        "personality": "Calm, concise, explicit about blockers, and careful with handoffs.",
        "responsibilities": [
            "Understand human goals and turn them into traceable Tickets with owner, validator, context, and acceptance criteria.",
            "Route Tickets to the right AI Employee, request handoffs or PV validation, and keep the Ticket event ledger current.",
            "Summarize reports, evidence, decisions, blockers, and next actions back to the human.",
            "Govern Ticket-flow assets such as Skills, Memories, Decisions, Reports, Evidence, Knowledge access, and Capabilities.",
        ],
        "skills": _default_skills_for_role(CLARA_SYSTEM_ROLE),
        "ai_engine": {
            "mode": "external_or_file_stub",
            "engine_identity": CLARA_SYSTEM_EMPLOYEE_ID,
            "default_engine": "system",
            "preserve_engine_thread": True,
        },
        "permissions": [
            "chat",
            "manage_employees",
            "manage_skills",
            "manage_memory",
            "manage_knowledge",
            "manage_tickets",
            "read_local_assets",
            "route_employee",
            "run_terminal",
            "write_trace",
        ],
        "system": {"protected": True, "bootstrap": True},
        "created_at": _now(),
        "updated_at": _now(),
    }


def _employee_summary(profile: dict[str, Any]) -> ChatEmployeeSummary:
    ai_engine = profile.get("ai_engine") if isinstance(profile.get("ai_engine"), dict) else {}
    employee_id = str(profile.get("id", ""))
    return ChatEmployeeSummary(
        id=employee_id,
        display_name=str(profile.get("display_name") or profile.get("id") or "Unknown"),
        kind=str(profile.get("kind", "ai")),
        role=str(profile.get("role", "AI Employee")),
        summary=str(profile.get("summary", "")),
        skills=[str(skill) for skill in profile.get("skills", [])],
        ai_engine_mode=str(ai_engine.get("mode", "external_or_file_stub")),
        default_ai_engine=_normalize_employee_default_ai_engine(str(ai_engine.get("default_engine") or "system")),
        preserve_engine_thread=bool(ai_engine.get("preserve_engine_thread", True)),
        default_thread_id=_employee_default_thread_id(employee_id),
    )


def _employees_dir() -> Path:
    return _workspace_dir() / "employees"


def _skills_dir() -> Path:
    return _workspace_dir() / "skills"


def _employee_profile_path(employee_id: str) -> Path:
    employee_id = _require_safe_id(employee_id, field="employee_id")
    return _employees_dir() / f"{employee_id}.yaml"


def _skill_dir(skill_id: str) -> Path:
    skill_id = _require_safe_id(skill_id, field="skill_id")
    return _skills_dir() / skill_id


def _skill_file_path(skill_id: str) -> Path:
    return _skill_dir(skill_id) / "SKILL.md"


def _employee_sort_key(employee: ChatEmployeeSummary) -> tuple[int, str]:
    if _is_clara_system_employee_id(employee.id):
        return (0, employee.display_name.lower())
    return (1, employee.display_name.lower())


def _clean_extracted_value(value: str) -> str:
    return _clean_extracted_value_data(value)


def _extract_first(patterns: list[str], message: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            value = _clean_extracted_value(match.group(1))
            if value:
                return value
    return None


def _slugify_employee_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = f"employee-{uuid4().hex[:8]}"
    return _require_safe_id(slug[:80], field="employee_id")


def _slugify_skill_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = f"skill-{uuid4().hex[:8]}"
    return _require_safe_id(slug[:80], field="skill_id")


def _split_list_value(value: str) -> list[str]:
    return _split_list_value_data(value)


def _stringify_tool_arg(value: Any) -> str | None:
    return _stringify_tool_arg_data(value)


def _listify_tool_arg(value: Any) -> list[str] | None:
    return _listify_tool_arg_data(value)


def _tool_arg(plan: ChatKernelCommandPlan | None, *names: str) -> Any:
    if plan is None:
        return None
    return _tool_arg_data(plan.arguments, *names)


def _tool_str_arg(plan: ChatKernelCommandPlan | None, *names: str) -> str | None:
    return _stringify_tool_arg(_tool_arg(plan, *names))


def _tool_list_arg(plan: ChatKernelCommandPlan | None, *names: str) -> list[str] | None:
    return _listify_tool_arg(_tool_arg(plan, *names))


def _dedupe(values: list[str]) -> list[str]:
    return _dedupe_data(values)


def _extract_employee_display_name(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:名字叫|名为|叫做|叫)\s*([A-Za-z][A-Za-z0-9_. -]{0,63}|[\u4e00-\u9fff]{1,16})",
            r"(?:display_name|name)\s*[:=：]\s*([A-Za-z][A-Za-z0-9_. -]{0,63})",
            r"\b(?:named|called)\s+([A-Za-z][A-Za-z0-9_. -]{0,63})",
            r"\bcreate_employee\s+([A-Za-z][A-Za-z0-9_. -]{0,63})",
        ],
        message,
    )


def _extract_new_display_name(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:名字|display_name|name)\s*(?:改成|改为|更新为|设置为|to|=|:|：)\s*([A-Za-z][A-Za-z0-9_. -]{0,63}|[\u4e00-\u9fff]{1,16})",
        ],
        message,
    )


def _extract_explicit_employee_id(message: str) -> str | None:
    value = _extract_first(
        [
            r"\b(?:employee_id|id)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
            r"(?:成员\s*id|成员ID)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
        ],
        message,
    )
    return _slugify_employee_id(value) if value else None


def _extract_employee_kind(message: str) -> str:
    normalized = message.lower()
    if any(token in normalized for token in ("human", "user", "人类", "用户")):
        return "human"
    return "ai"


def _normalize_role_value(value: str) -> str:
    lower = f" {value.lower()} "
    for role, keywords in _ROLE_KEYWORDS:
        if any(keyword in lower for keyword in keywords):
            return role
    return value.strip() or "AI Employee"


def _extract_employee_role(message: str, *, require_role_marker: bool = False) -> str | None:
    explicit = _extract_first(
        [
            r"(?:角色|定位|role)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^,，。;；\n]+)",
        ],
        message,
    )
    if explicit:
        return _normalize_role_value(explicit)
    if require_role_marker:
        return None

    lower = f" {message.lower()} "
    if re.search(r"(?<![a-z0-9])pv(?![a-z0-9])", lower):
        return "AI PV"
    for role, keywords in _ROLE_KEYWORDS:
        if any(keyword in lower for keyword in keywords):
            return role
    return None


def _extract_summary(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:summary|简介|摘要|描述)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^,，。;；\n]+)",
            r"(?:负责|职责是|职责为)\s*([^,，。;；\n]+)",
        ],
        message,
    )


def _extract_skills_value(message: str) -> list[str] | None:
    value = _extract_first(
        [
            r"(?:skills?|技能)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([^。;；\n]+)",
        ],
        message,
    )
    return _split_list_value(value) if value else None


def _extract_add_skills_value(message: str) -> list[str] | None:
    value = _extract_first(
        [
            r"(?:添加|增加|分配|add|assign)\s*(?:skills?|技能)\s*[:=：]?\s*([^。;；\n]+)",
        ],
        message,
    )
    return _split_list_value(value) if value else None


def _extract_ai_engine_mode(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:ai_engine|AI Engine|运行引擎|运行模式)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([A-Za-z0-9_.:-]{1,80})",
        ],
        message,
    )


def _extract_skill_name(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:skill|技能)\s*(?:id|ID)?\s*[:=：]\s*([A-Za-z0-9_. -]{1,80})",
            r"(?:创建|新增|添加|新建)\s*(?:一个|1个)?\s*(?:公开|本地)?\s*(?:skill|技能)[,，\s]*(?:叫|名为|名字叫|named|called)?\s*([A-Za-z][A-Za-z0-9_. -]{0,79}|[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9_. -]{0,31})",
            r"\bcreate_skill\s+([A-Za-z][A-Za-z0-9_. -]{0,79})",
        ],
        message,
    )


def _extract_existing_skill_id(message: str) -> str | None:
    explicit = _extract_first(
        [
            r"(?:skill_id|skill id|技能\s*id|技能ID)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
        ],
        message,
    )
    if explicit:
        return _slugify_skill_id(explicit)

    normalized = message.lower()
    for skill in _load_skills():
        if re.search(rf"\b{re.escape(skill.id.lower())}\b", normalized):
            return skill.id
        if skill.title.lower() in normalized:
            return skill.id
    return None


def _extract_skill_target(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:删除|移除|删掉|delete|remove|drop)\s*(?:skill|技能)\s*[,，:：]?\s*([A-Za-z0-9_. -]{1,80})",
            r"(?:skill|技能)\s*([A-Za-z0-9_. -]{1,80})\s*(?:删除|移除|删掉|delete|remove|drop)",
        ],
        message,
    )


def _extract_skill_description(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:description|summary|用途|用于|用来|描述|说明)\s*(?:是|为|:|：)?\s*([^。;；\n]+)",
            r"(?:负责|能力是|能力为)\s*([^。;；\n]+)",
        ],
        message,
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _maybe_append_chat_action_plan_trace(context: ChatRunContext, plan: ChatKernelCommandPlan) -> None:
    if plan.command not in _COMMAND_ID_TO_CHAT_ACTION:
        return
    action_plan = _chat_action_plan_from_kernel_plan(plan)
    context.trace_events.append(
        ChatTraceEvent(
            event="chat.action_plan.completed",
            detail=f"Planned ChatActionPlan action: {action_plan.action}.",
            data={
                **action_plan.model_dump(),
                "kernel_command": plan.command,
            },
        )
    )

def _should_use_llm_command_planner(context: ChatRunContext) -> bool:
    return _should_use_llm_command_planner_data(
        message=context.request.message,
        selected_ai_engine=context.selected_ai_engine,
        has_deepseek_api_key=bool(_ai_engine_secrets()["deepseek_api_key"]),
    )


def _local_kernel_heuristics_allowed(context: ChatRunContext) -> bool:
    return _local_kernel_heuristics_allowed_data(
        mode=os.environ.get("AITEAMOS_CHAT_KERNEL_COMMANDS", "fallback"),
        selected_ai_engine=context.selected_ai_engine,
    )


async def _call_deepseek_command_planner(context: ChatRunContext) -> ChatKernelCommandPlan:
    employees = [_employee_summary(profile).model_dump() for profile in _load_employees()]
    skills = [skill.model_dump() for skill in _load_skills()]
    runtime = _ai_engine_runtime()
    request_body: dict[str, Any] = {
        "model": runtime.deepseek_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are AITeamOS Clara's Kernel command planner. "
                    "Classify the user's message into exactly one Kernel command. "
                    "Do not answer the user. Return only a JSON object.\n\n"
                    f"Allowed commands:\n{local_kernel_command_prompt()}\n\n"
                    "JSON schema:\n"
                    "{"
                    f"\"command\":\"{local_kernel_command_union(include_none=True)}\","
                    "\"arguments\":{},"
                    "\"confidence\":0.0,"
                    "\"reason\":\"short reason\""
                    "}\n\n"
                    "Arguments for employees.manage:create: display_name, employee_id, kind, role, summary, responsibility, skills. "
                    "Arguments for employees.manage:update: target_employee_id or target_employee_name, display_name, role, "
                    "summary, skills, add_skills, ai_engine_mode. "
                    "Arguments for employees.manage:delete: target_employee_id or target_employee_name. "
                    "Arguments for assets.manage:create_skill: skill_id, title, description, body. "
                    "Arguments for assets.manage:assign_skill: skill_id or skill_name, target_employee_id or target_employee_name. "
                    "Arguments for assets.manage:delete_skill: skill_id or skill_name. "
                    "Arguments for knowledge.search:search: query. "
                    "Arguments for tickets.manage:create: title, description, ticket_type, target_employee_id or target_employee_name, "
                    "assigned_role, validation_employee_id, validation_role, code_repository_ids or code_repository_name. "
                    "Arguments for tickets.manage:report: ticket_id, reporter_employee_id, reporter_role, content, "
                    "report_type, evidence. "
                    "Arguments for tickets.manage:request_validation: ticket_id, validation_employee_id, "
                    "validation_employee_name, validation_role, content. "
                    "Arguments for tickets.manage:request_human_review: ticket_id, content, reason, "
                    "reviewer_employee_id or reviewer_employee_name, evidence. "
                    "Arguments for tickets.manage:self_bootstrap_summary: optional scope or theme. "
                    "Arguments for repositories.list:list: none. "
                    "Arguments for repositories.inspect:inspect: ticket_id, code_repository_id or code_repository_name, "
                    "query, file_path or file_paths. "
                    "Arguments for terminal.run:run: command, cwd, ticket_id. terminal.run requires ticket_id. "
                    "Arguments for kernel.permissions:inspect: target_employee_id or target_employee_name. "
                    "Map PV, verification, regression, and harness triage roles to role='AI PV'. "
                    "Map release Tickets to role='AI Release'. Map QA or harness runner to role='AI QA / Harness Runner'. "
                    "Use kind='ai' for AI employee/employee requests and kind='human' only for human user/employee requests. "
                    "Choose a command only when the user intends to inspect or change AITeamOS local employee profiles "
                    "or Ticket-flow assets. Choose knowledge.search:search when the user asks Clara to read docs, "
                    "memories, decisions, or team knowledge. Choose tickets.manage:create when the user asks Clara "
                    "to delegate or plan a Ticket for an employee role. Choose repositories.list:list when the user asks "
                    "what code repositories, repos, GitHub/Gitea repositories, or local repository paths are configured. "
                    "Choose repositories.inspect:inspect when an RD, PV, QA, Architect, or other non-Clara employee is asked "
                    "to inspect, search, read, review, or analyze configured repository files. "
                    "Choose terminal.run:run only when the user explicitly asks to run a terminal command in the workspace and binds it to a Ticket. "
                    "Choose kernel.permissions:inspect when the user asks what permissions, authorization, or commands Clara "
                    "or another Employee has. "
                    "Choose tickets.manage:request_validation when Clara asks PV or another validator to review an existing Ticket. "
                    "Choose tickets.manage:request_human_review when the user asks for human review, human approval, "
                    "or manual review of a specific Ticket. "
                    "Choose tickets.manage:self_bootstrap_summary when the user asks what AITeamOS learned, "
                    "which approved assets were reused, or what the next self-bootstrap batch should do. "
                    "Choose tickets.manage:report when an employee or Clara records a result, validation report, "
                    "or validation failure for an existing Ticket. Use report_type='validation' for a passed "
                    "validation and report_type='validation_failed' for a failed validation."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": context.request.message,
                        "target_employee": context.employee.model_dump(),
                        "existing_employees": employees,
                        "existing_skills": skills,
                        "recent_messages": [
                            message.model_dump(mode="json") for message in context.recent_messages[-8:]
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "stream": False,
        "max_tokens": 600,
        "thinking": {"type": runtime.deepseek_thinking_type()},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{runtime.deepseek_base_url()}/chat/completions",
            headers={
                "Authorization": f"Bearer {runtime.secrets.get('deepseek_api_key', '')}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"DeepSeek command planner failed: {response.status_code} {response.text[:300]}")

    payload = response.json()
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("DeepSeek command planner returned no choices")
    message_payload = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message_payload.get("content") if isinstance(message_payload, dict) else None
    if not isinstance(content, str):
        raise RuntimeError("DeepSeek command planner returned no content")
    json_payload = _extract_json_object(content)
    if json_payload is None:
        raise RuntimeError("DeepSeek command planner returned invalid JSON")
    return _normalize_kernel_command_plan(json_payload, source="deepseek_command_planner")


def _heuristic_kernel_command_plan(message: str) -> ChatKernelCommandPlan:
    if _is_permission_inspection_request(message):
        return ChatKernelCommandPlan(
            command="kernel.permissions:inspect",
            confidence=0.65,
            reason="Matched Kernel permission inspection fallback.",
        )
    if _is_terminal_run_request(message):
        command_line = _extract_terminal_command_line(message)
        return ChatKernelCommandPlan(
            command="terminal.run:run",
            arguments={"command": command_line} if command_line else {},
            confidence=0.55 if command_line else 0.45,
            reason="Matched terminal command fallback.",
        )
    if _is_request_ticket_validation_request(message):
        return ChatKernelCommandPlan(
            command="tickets.manage:request_validation",
            confidence=0.45,
            reason="Matched local ticket validation-request fallback.",
        )
    if _is_request_human_review_request(message):
        return ChatKernelCommandPlan(
            command="tickets.manage:request_human_review",
            confidence=0.45,
            reason="Matched local human-review request fallback.",
        )
    if _is_self_bootstrap_summary_request(message):
        return ChatKernelCommandPlan(
            command="tickets.manage:self_bootstrap_summary",
            confidence=0.5,
            reason="Matched local self-bootstrap learning summary fallback.",
        )
    if _is_record_ticket_report_request(message):
        return ChatKernelCommandPlan(
            command="tickets.manage:report",
            confidence=0.45,
            reason="Matched local ticket report fallback.",
        )
    if _is_list_code_repositories_request(message):
        return ChatKernelCommandPlan(
            command="repositories.list:list",
            confidence=0.45,
            reason="Matched local list-code-repositories fallback.",
        )
    if _is_inspect_code_repository_request(message):
        return ChatKernelCommandPlan(
            command="repositories.inspect:inspect",
            confidence=0.45,
            reason="Matched local inspect-code-repository fallback.",
        )
    if _is_list_tickets_request(message):
        return ChatKernelCommandPlan(command="tickets.manage:list", confidence=0.45, reason="Matched local list-tickets fallback.")
    if _is_create_ticket_request(message):
        return ChatKernelCommandPlan(command="tickets.manage:create", confidence=0.45, reason="Matched local create-ticket fallback.")
    if _is_search_knowledge_request(message):
        return ChatKernelCommandPlan(command="knowledge.search:search", confidence=0.45, reason="Matched local search-knowledge fallback.")
    if _is_create_skill_request(message):
        return ChatKernelCommandPlan(command="assets.manage:create_skill", confidence=0.45, reason="Matched local create-skill fallback.")
    if _is_assign_skill_request(message):
        return ChatKernelCommandPlan(
            command="assets.manage:assign_skill",
            confidence=0.45,
            reason="Matched local assign-skill fallback.",
        )
    if _is_delete_skill_request(message):
        return ChatKernelCommandPlan(command="assets.manage:delete_skill", confidence=0.45, reason="Matched local delete-skill fallback.")
    if _is_list_skills_request(message):
        return ChatKernelCommandPlan(command="assets.manage:list_skills", confidence=0.45, reason="Matched local list-skills fallback.")
    if _is_create_employee_request(message):
        return ChatKernelCommandPlan(command="employees.manage:create", confidence=0.45, reason="Matched local create-employee fallback.")
    if _is_delete_employee_request(message):
        return ChatKernelCommandPlan(command="employees.manage:delete", confidence=0.45, reason="Matched local delete-employee fallback.")
    if _is_edit_employee_profile_request(message):
        return ChatKernelCommandPlan(
            command="employees.manage:update",
            confidence=0.45,
            reason="Matched local edit-employee fallback.",
        )
    if _is_list_employees_request(message):
        return ChatKernelCommandPlan(command="employees.manage:list", confidence=0.45, reason="Matched local list-employees fallback.")
    return ChatKernelCommandPlan(command="none", confidence=0, reason="No local command fallback matched.")


async def _plan_kernel_command_intent(context: ChatRunContext) -> ChatKernelCommandPlan:
    if _should_use_llm_command_planner(context):
        try:
            plan = await _call_deepseek_command_planner(context)
            context.trace_events.append(
                ChatTraceEvent(
                    event="command.intent_planner.completed",
                    detail="Planned Kernel command intent through DeepSeek.",
                    data=plan.model_dump(),
                )
            )
            _maybe_append_chat_action_plan_trace(context, plan)
            if plan.command != "none" and plan.confidence >= 0.5:
                return plan
        except Exception as exc:
            context.trace_events.append(
                ChatTraceEvent(
                    event="command.intent_planner.failed",
                    detail="LLM command planner failed.",
                    data={"source": "deepseek_command_planner", "error": str(exc)[:300]},
                )
            )

    if not _local_kernel_heuristics_allowed(context):
        plan = ChatKernelCommandPlan(
            command="none",
            confidence=0,
            reason="Remote AI Engine mode requires an explicit LLM ChatActionPlan; local heuristics were not used.",
            source="remote_action_plan_required",
        )
        _maybe_append_chat_action_plan_trace(context, plan)
        context.trace_events.append(
            ChatTraceEvent(
                event="command.intent_planner.skipped",
                detail="No explicit remote action plan was available; Kernel command execution was skipped.",
                data=plan.model_dump(),
            )
        )
        return plan

    plan = _heuristic_kernel_command_plan(context.request.message)
    _maybe_append_chat_action_plan_trace(context, plan)
    if plan.command != "none":
        context.trace_events.append(
            ChatTraceEvent(
                event="command.intent_planner.fallback",
                detail="Planned Kernel command intent through local fallback heuristics.",
                data=plan.model_dump(),
            )
        )
    return plan


def _default_summary(display_name: str, role: str, responsibility: str | None) -> str:
    if responsibility:
        return f"{display_name} focuses on {responsibility}."
    if role == "AI PV":
        return "Verification-focused AI Employee for regression, harness, and failing case triage."
    if role == "AI Release":
        return "Release-focused AI Employee for build, packaging, integration, and release-flow analysis."
    if role == "AI Architect":
        return "Architecture-focused AI Employee for system design, tradeoff analysis, and boundary review."
    if role == "AI QA / Harness Runner":
        return "QA-focused AI Employee for test execution, harness evidence, and validation reporting."
    if role == "AI Memory Curator":
        return "Memory-focused AI Employee for extracting reusable team knowledge from Ticket traces."
    if role == "AI RD / Implementer":
        return "Implementation-focused AI Employee for code changes, bug fixing, and engineering handoff reports."
    return f"File-backed {role} profile."


def _default_responsibilities(role: str, responsibility: str | None) -> list[str]:
    if responsibility:
        return [responsibility]
    defaults = {
        "AI PV": ["Triage regression and harness failures.", "Summarize verification evidence and blockers."],
        "AI Release": ["Analyze build, packaging, and release-flow issues.", "Coordinate release evidence and risks."],
        "AI Architect": ["Review architecture boundaries and tradeoffs.", "Escalate unclear system decisions."],
        "AI QA / Harness Runner": ["Run or interpret validation evidence.", "Report pass/fail signals clearly."],
        "AI Memory Curator": ["Extract memory candidates from traces.", "Keep reusable knowledge scoped and evidence-backed."],
        "AI RD / Implementer": ["Investigate bounded engineering Tickets.", "Implement changes and report verification results."],
    }
    return defaults.get(role, ["Handle delegated AITeamOS Tickets within profile boundaries."])


def _default_permissions(kind: str, role: str) -> list[str]:
    if kind == "human":
        return ["chat", "read_local_assets"]
    permissions = ["chat", "read_local_assets", "write_trace"]
    if role == "AI RD / Implementer":
        permissions.append("propose_code_change")
    if role in {"AI PV", "AI QA / Harness Runner", "AI Release"}:
        permissions.append("read_validation_evidence")
    return permissions


def _default_handoff_rules(role: str) -> list[str]:
    rules = ["Ask for human approval before destructive or externally visible actions."]
    if role != CLARA_SYSTEM_ROLE:
        rules.append("Escalate cross-employee coordination needs to Clara.")
    if role != "AI Architect":
        rules.append("Escalate architecture ambiguity to AI Architect.")
    if role not in {"AI PV", "AI QA / Harness Runner"}:
        rules.append("Ask AI PV or AI QA to validate regression and harness evidence.")
    return rules


def _default_skills_for_role(role: str) -> list[str]:
    return list(_ROLE_DEFAULT_SKILLS.get(role, []))


def _build_employee_profile(
    *,
    employee_id: str,
    display_name: str,
    kind: str,
    role: str,
    summary: str,
    skills: list[str],
    responsibility: str | None,
) -> dict[str, Any]:
    ai_engine_mode = "human" if kind == "human" else "external_or_file_stub"
    return {
        "id": employee_id,
        "display_name": display_name,
        "kind": kind,
        "role": role,
        "summary": summary,
        "personality": "Concise, evidence-driven, and explicit about blockers.",
        "responsibilities": _default_responsibilities(role, responsibility),
        "skills": skills,
        "memory_scopes": ["global", "aiteamos"] if role == CLARA_SYSTEM_ROLE else ["aiteamos", f"employee:{employee_id}"],
        "ai_engine": {
            "mode": ai_engine_mode,
            "engine_identity": employee_id,
            "default_engine": "system",
            "preserve_engine_thread": True,
        },
        "permissions": _default_permissions(kind, role),
        "handoff_rules": _default_handoff_rules(role),
        "created_at": _now(),
        "updated_at": _now(),
    }


def _find_employee_profile(employee_id_or_name: str) -> tuple[Path, dict[str, Any]] | None:
    _ensure_clara_system_employee()
    lookup = employee_id_or_name.strip().lower()
    employees_dir = _employees_dir()
    if not employees_dir.exists():
        return None
    for path in sorted(employees_dir.glob("*.yaml")):
        profile = _read_yaml(path)
        profile_id = str(profile.get("id") or path.stem)
        display_name = str(profile.get("display_name") or profile_id)
        if lookup in {profile_id.lower(), display_name.lower()}:
            profile.setdefault("id", profile_id)
            return path, profile
    return None


def _extract_edit_employee_target(message: str, context: ChatRunContext) -> str | None:
    explicit_id = _extract_explicit_employee_id(message)
    if explicit_id:
        return explicit_id

    normalized = message.lower()
    profiles = sorted((_employee_summary(profile) for profile in _load_employees()), key=_employee_sort_key)
    ordered_profiles = [
        *[employee for employee in profiles if employee.id != context.employee.id],
        *[employee for employee in profiles if employee.id == context.employee.id],
    ]
    for employee in ordered_profiles:
        if re.search(rf"\b{re.escape(employee.id.lower())}\b", normalized):
            return employee.id
        if employee.display_name.lower() in normalized:
            return employee.id

    if context.employee.id != "clara":
        return context.employee.id
    return None


def _is_list_employees_request(message: str) -> bool:
    return _request_classifier.is_list_employees_request(message)


def _is_create_employee_request(message: str) -> bool:
    return _request_classifier.is_create_employee_request(message)


def _is_edit_employee_profile_request(message: str) -> bool:
    return _request_classifier.is_edit_employee_profile_request(message)


def _is_delete_employee_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "delete_employee" in normalized:
        return True
    if _DELETE_EMPLOYEE_EN_RE.search(normalized):
        return True

    compact = re.sub(r"\s+", "", normalized)
    if any(token in compact for token in ("skill", "skills", "技能")):
        return False
    has_delete_token = any(
        token in compact
        for token in ("删除", "移除", "删掉", "remove", "delete", "drop")
    )
    if not has_delete_token:
        return False
    if any(token in compact for token in ("成员", "员工", "employee", "employee", "profile", "用户", "user")):
        return True

    for profile in _load_employees():
        employee = _employee_summary(profile)
        if re.search(rf"\b{re.escape(employee.id.lower())}\b", normalized):
            return True
        if employee.display_name.lower() in normalized:
            return True
    return False


def _is_list_skills_request(message: str) -> bool:
    return _request_classifier.is_list_skills_request(message)


def _is_create_skill_request(message: str) -> bool:
    return _request_classifier.is_create_skill_request(message)


def _is_assign_skill_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "assign_skill_to_employee" in normalized:
        return True
    if _ASSIGN_SKILL_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    has_skill_reference = any(token in compact for token in ("skill", "skills", "技能"))
    if not has_skill_reference and _extract_existing_skill_id(message) is None:
        return False
    if any(token in compact for token in ("summary", "role", "ai_engine", "运行引擎", "名字", "角色", "摘要", "描述", "改成", "改为")):
        return False
    if not any(token in compact for token in ("分配", "关联", "添加", "增加", "assign", "attach")):
        return False
    if any(token in compact for token in ("成员", "employee", "员工")):
        return True
    return any(
        employee.id.lower() in normalized or employee.display_name.lower() in normalized
        for employee in (_employee_summary(profile) for profile in _load_employees())
    )


def _is_delete_skill_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "delete_skill" in normalized:
        return True
    if _DELETE_SKILL_EN_RE.search(normalized):
        return True

    compact = re.sub(r"\s+", "", normalized)
    has_delete_token = any(token in compact for token in ("删除", "移除", "删掉", "remove", "delete", "drop"))
    if not has_delete_token:
        return False
    if any(token in compact for token in ("skill", "skills", "技能")):
        return True
    return _extract_existing_skill_id(message) is not None


def _is_search_knowledge_request(message: str) -> bool:
    return _request_classifier.is_search_knowledge_request(message)


def _is_create_ticket_request(message: str) -> bool:
    return _request_classifier.is_create_ticket_request(message)


def _is_list_tickets_request(message: str) -> bool:
    return _request_classifier.is_list_tickets_request(message)


def _is_record_ticket_report_request(message: str) -> bool:
    return _request_classifier.is_record_ticket_report_request(message)


def _is_request_ticket_validation_request(message: str) -> bool:
    return _request_classifier.is_request_ticket_validation_request(message)


def _is_request_human_review_request(message: str) -> bool:
    return _request_classifier.is_request_human_review_request(message)


def _is_list_code_repositories_request(message: str) -> bool:
    return _request_classifier.is_list_code_repositories_request(message)


def _is_inspect_code_repository_request(message: str) -> bool:
    return _request_classifier.is_inspect_code_repository_request(message)


def _is_permission_inspection_request(message: str) -> bool:
    return _request_classifier.is_permission_inspection_request(
        message,
        is_human_review_request=_is_request_human_review_request(message),
    )


def _is_self_bootstrap_summary_request(message: str) -> bool:
    return _request_classifier.is_self_bootstrap_summary_request(message)


def _is_kernel_command_request(message: str) -> bool:
    return (
        _is_permission_inspection_request(message)
        or _is_self_bootstrap_summary_request(message)
        or _is_create_employee_request(message)
        or _is_edit_employee_profile_request(message)
        or _is_delete_employee_request(message)
        or _is_list_employees_request(message)
        or _is_list_skills_request(message)
        or _is_create_skill_request(message)
        or _is_assign_skill_request(message)
        or _is_delete_skill_request(message)
        or _is_search_knowledge_request(message)
        or _is_create_ticket_request(message)
        or _is_list_tickets_request(message)
        or _is_request_ticket_validation_request(message)
        or _is_request_human_review_request(message)
        or _is_self_bootstrap_summary_request(message)
        or _is_record_ticket_report_request(message)
        or _is_list_code_repositories_request(message)
        or _is_inspect_code_repository_request(message)
        or _is_terminal_run_request(message)
    )


def _is_remote_kernel_action_request(message: str) -> bool:
    normalized = message.strip().lower()
    compact = re.sub(r"\s+", "", normalized)
    if _is_permission_inspection_request(message):
        return False
    if any(
        token in compact
        for token in (
            "能不能",
            "能否",
            "可以吗",
            "能处理",
            "能做什么",
            "可以做什么",
            "具备哪些",
        )
    ):
        return False
    return (
        _is_create_employee_request(message)
        or _is_edit_employee_profile_request(message)
        or _is_delete_employee_request(message)
        or _is_list_employees_request(message)
        or _is_list_skills_request(message)
        or _is_create_skill_request(message)
        or _is_assign_skill_request(message)
        or _is_delete_skill_request(message)
        or _is_search_knowledge_request(message)
        or _is_create_ticket_request(message)
        or _is_list_tickets_request(message)
        or _is_request_ticket_validation_request(message)
        or _is_request_human_review_request(message)
        or _is_record_ticket_report_request(message)
        or _is_list_code_repositories_request(message)
        or _is_inspect_code_repository_request(message)
        or _is_terminal_run_request(message)
    )


def _detect_employee_gaps(employees: list[ChatEmployeeSummary]) -> list[str]:
    haystack = "\n".join(
        f"{employee.id} {employee.display_name} {employee.role} {employee.summary}".lower()
        for employee in employees
    )
    return [
        label
        for label, keywords in _CORE_EMPLOYEE_GAPS.items()
        if not any(keyword.lower() in haystack for keyword in keywords)
    ]


def _list_employees_tool_result() -> dict[str, Any]:
    employees = sorted((_employee_summary(profile) for profile in _load_employees()), key=_employee_sort_key)
    employee_payloads = [employee.model_dump() for employee in employees]
    return {
        "count": len(employees),
        "employees": employee_payloads,
        "gaps": _detect_employee_gaps(employees),
        "deep_links": {
            "employees": "#/employees",
            **{f"employee:{employee.id}": f"#/employees/{employee.id}" for employee in employees},
        },
    }


def _build_list_employees_reply(tool_result: dict[str, Any]) -> str:
    employees = tool_result["employees"]
    gaps = tool_result["gaps"]
    deep_links = tool_result["deep_links"]
    lines = [
        f"我找到了 {tool_result['count']} 个成员。",
        "",
        "成员列表：",
    ]

    for employee in employees:
        skill_count = len(employee["skills"])
        summary = employee["summary"] or "No summary"
        lines.append(
            f"- {employee['display_name']} ({employee['id']}) - {employee['role']}；"
            f"{skill_count} skill(s)；ai_engine: {employee['ai_engine_mode']}；{summary}"
        )

    lines.append("")
    if gaps:
        lines.append("当前明显缺口：")
        lines.extend(f"- {gap}" for gap in gaps)
    else:
        lines.append("当前没有发现明显的内置角色缺口。")

    lines.extend([
        "",
        "建议下一步：",
        "- 如果要推进具体 Ticket，可以直接点名成员，例如：Alex，请推进 Ticket SV-1234 并汇报结果。",
        "- 如果要补齐团队拓扑，可以先创建 PV / Release / QA 等成员，再分配对应 Skills。",
        "",
        "查看入口：",
        f"- Employees: {deep_links['employees']}",
    ])
    for employee in employees:
        employee_link = deep_links[f"employee:{employee['id']}"]
        lines.append(f"- {employee['display_name']}: {employee_link}")

    return "\n".join(lines)


def _list_skills_tool_result() -> dict[str, Any]:
    skills = sorted(_load_skills(), key=lambda skill: skill.id)
    return {
        "count": len(skills),
        "skills": [skill.model_dump() for skill in skills],
        "deep_links": {
            "skills": "#/assets/capabilities/skills",
            **{f"skill:{skill.id}": f"#/assets/capabilities/skills/{skill.id}" for skill in skills},
        },
    }


def _build_list_skills_reply(tool_result: dict[str, Any]) -> str:
    skills = tool_result["skills"]
    deep_links = tool_result["deep_links"]
    lines = [
        f"我找到了 {tool_result['count']} 个 Skills。",
        "",
        "Skills 列表：",
    ]
    if not skills:
        lines.append("- none")
    for skill in skills:
        assigned = ", ".join(skill["assigned_employees"]) if skill["assigned_employees"] else "unassigned"
        description = skill["description"] or "No description"
        lines.append(
            f"- {skill['title']} ({skill['id']})；assigned: {assigned}；"
            f"resources: {len(skill['resources'])}；{description}"
        )

    lines.extend([
        "",
        "建议下一步：",
        "- 如果要新增可复用能力，可以让我创建一个本地 SKILL.md。",
        "- 如果要让某个成员使用它，可以让我把 Skill 分配给对应 Employee。",
        "",
        "查看入口：",
        f"- Skills: {deep_links['skills']}",
    ])
    for skill in skills:
        skill_link = deep_links[f"skill:{skill['id']}"]
        lines.append(f"- {skill['title']}: {skill_link}")

    return "\n".join(lines)


def _list_code_repositories_tool_result() -> dict[str, Any]:
    repositories = list_code_repositories()
    return {
        "count": len(repositories),
        "repositories": [repository.model_dump(mode="json") for repository in repositories],
        "deep_links": {"code_repositories": "#/settings/code-repositories"},
    }


def _build_list_code_repositories_reply(tool_result: dict[str, Any]) -> str:
    repositories = tool_result["repositories"]
    lines = [
        f"我找到了 {tool_result['count']} 个代码仓库配置。",
        "",
        "代码仓库：",
    ]
    if not repositories:
        lines.append("- none")
    for repository in repositories:
        branch = repository["current_branch"] or repository["default_branch"] or "-"
        plane_scope = "/".join(
            item for item in (repository["plane_workspace_slug"], repository["plane_project_id"]) if item
        ) or "-"
        lines.append(
            f"- {repository['name']} ({repository['id']})；source={repository['provider']}；"
            f"status={repository['status']}；branch={branch}；Plane={plane_scope}\n"
            f"  {repository['location']}"
        )

    lines.extend([
        "",
        "说明：",
        "- Clara 只使用这些 repo 配置作为 Ticket context，不直接读取代码。",
        "- RD/PV Employee 会通过 repo tools、Tool Connectors 或 AI Engines 读取、修改和验证代码。",
        "",
        "查看入口：",
        f"- Code Repositories: {tool_result['deep_links']['code_repositories']}",
    ])
    return "\n".join(lines)


def _actor_permissions(context: ChatRunContext) -> list[str]:
    raw_permissions = context.selected_profile.get("permissions")
    if not isinstance(raw_permissions, list):
        return []
    return [str(permission) for permission in raw_permissions if str(permission).strip()]


def _command_from_handler_result(
    context: ChatRunContext,
    *,
    handler_name: str,
    result: dict[str, Any],
) -> tuple[KernelCommand, KernelCommandSpec]:
    return _kernel_command_from_handler_result_data(
        handler_name=handler_name,
        result=result,
        ticket_keys=context.ticket_keys,
    )


def _persist_kernel_command_response(
    context: ChatRunContext,
    *,
    handler_name: str,
    reply: str,
    result: dict[str, Any],
    completed: bool,
) -> ChatMessageResponse:
    suffix = "completed" if completed else "blocked"
    command, spec = _command_from_handler_result(context, handler_name=handler_name, result=result)
    policy = evaluate_kernel_policy(command, spec=spec, actor_permissions=_actor_permissions(context))
    command_payload = command.model_dump()
    policy_payload = policy.model_dump()
    result_payload = {
        **result,
        "command": command_payload,
        "kernel_policy": policy_payload,
    }
    return _persist_chat_response(
        context,
        reply=reply,
        extra_trace_events=[
            ChatTraceEvent(
                event="command.called",
                detail=f"Resolved {command.id} through Kernel command executor.",
                data={
                    "requested_by": context.employee.id,
                    "command": command_payload,
                    "kernel_policy": policy_payload,
                },
            ),
            ChatTraceEvent(
                event=f"command.{suffix}",
                detail=result.get("detail", f"{command.id} {suffix}."),
                data=result_payload,
            ),
        ],
    )


def _employee_from_plan_or_name(plan: ChatKernelCommandPlan | None, *names: str) -> ChatEmployeeSummary | None:
    for name in names:
        value = _tool_str_arg(plan, name)
        if value:
            found = _find_employee_profile(value)
            if found is not None:
                return _employee_summary(found[1])
    return None


def _employee_for_role(role: str | None) -> ChatEmployeeSummary | None:
    normalized_role = _normalize_role_value(role or "").lower()
    employees = sorted((_employee_summary(profile) for profile in _load_employees()), key=_employee_sort_key)
    for employee in employees:
        if employee.role.lower() == normalized_role:
            return employee
    for employee in employees:
        if normalized_role and normalized_role in employee.role.lower():
            return employee
    return None


def _default_ticket_assignee(message: str) -> tuple[ChatEmployeeSummary | None, str]:
    lower = f" {message.lower()} "
    if any(token in lower for token in (" architect", "architecture", "架构")):
        return _employee_for_role("AI Architect"), "AI Architect"
    if re.search(r"(?<![a-z0-9])pv(?![a-z0-9])", lower) or any(token in lower for token in ("验证", "validation", "test")):
        return _employee_for_role("AI PV") or _employee_for_role("AI QA / Harness Runner"), "AI PV"
    if any(token in lower for token in ("release", "发布")):
        return _employee_for_role("AI Release"), "AI Release"
    return _employee_for_role("AI RD / Implementer"), "AI RD / Implementer"


def _explicit_delegated_employee(message: str) -> ChatEmployeeSummary | None:
    profiles = sorted((_employee_summary(profile) for profile in _load_employees()), key=_employee_sort_key)
    for employee in profiles:
        names = [re.escape(employee.id), re.escape(employee.display_name)]
        for name in names:
            if re.search(rf"(?:交给|派给|委派给|assign\s+to|delegate\s+to)\s*{name}\b", message, re.IGNORECASE):
                return employee
    return None


def _extract_ticket_id(message: str, plan: ChatKernelCommandPlan | None) -> str | None:
    explicit = _tool_str_arg(plan, "ticket_id", "id")
    if explicit:
        return explicit
    match = _LOCAL_TICKET_ID_RE.search(message)
    return match.group(0) if match else None


def _ticket_title(message: str, plan: ChatKernelCommandPlan | None) -> str:
    title = _tool_str_arg(plan, "title", "summary")
    if title:
        return title[:120]
    cleaned = re.sub(r"^(Clara|clara|@Clara|@clara)[,，:\s]*", "", message.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:96] or "AITeamOS delegated ticket"


def _message_mentions_repo_context(message: str) -> bool:
    lower = message.strip().lower()
    compact = re.sub(r"\s+", "", lower)
    if any(token in compact for token in ("代码仓库", "代码库", "仓库")):
        return True
    return bool(re.search(r"\b(repos?|repositories|repository|codebase)\b", lower))


def _match_repository(value: str, repositories: list[CodeRepository]) -> CodeRepository | None:
    lookup = value.strip().lower()
    if not lookup:
        return None
    for repository in repositories:
        if lookup in {repository.id.lower(), repository.name.lower()}:
            return repository
    for repository in repositories:
        location = repository.location.lower()
        if lookup and (lookup in location or lookup in repository.name.lower()):
            return repository
    return None


def _code_repository_ids_from_plan_or_message(plan: ChatKernelCommandPlan | None, message: str) -> list[str]:
    repositories = list_code_repositories()
    enabled_repositories = [repository for repository in repositories if repository.enabled]
    matched: list[str] = []

    def add_match(value: str) -> None:
        repository = _match_repository(value, repositories)
        if repository is not None and repository.id not in matched:
            matched.append(repository.id)

    for value in _tool_list_arg(plan, "code_repository_ids", "repository_ids", "repo_ids") or []:
        add_match(value)
    for key in (
        "code_repository_id",
        "repository_id",
        "repo_id",
        "code_repository_name",
        "repository_name",
        "repo_name",
    ):
        value = _tool_str_arg(plan, key)
        if value:
            add_match(value)

    if not matched:
        for repository in enabled_repositories:
            if repository.id.lower() in message.lower() or repository.name.lower() in message.lower():
                matched.append(repository.id)
        # Mentioning the local path or remote URL is also an explicit selection.
        for repository in enabled_repositories:
            if repository.id not in matched and repository.location and repository.location.lower() in message.lower():
                matched.append(repository.id)

    if not matched and _message_mentions_repo_context(message) and len(enabled_repositories) == 1:
        matched.append(enabled_repositories[0].id)

    return matched


def _extract_repo_file_paths(message: str, plan: ChatKernelCommandPlan | None) -> list[str]:
    values = _tool_list_arg(plan, "file_paths", "paths") or []
    for key in ("file_path", "path"):
        value = _tool_str_arg(plan, key)
        if value:
            values.append(value)
    values.extend(match.group(0) for match in _FILE_PATH_RE.finditer(message))
    return _dedupe([value.strip().lstrip("/") for value in values if value.strip()])


def _resolve_inspection_repository(
    *,
    plan: ChatKernelCommandPlan | None,
    message: str,
    ticket_id: str | None,
) -> CodeRepository | None:
    repositories = list_code_repositories()
    for key in (
        "code_repository_id",
        "repository_id",
        "repo_id",
        "code_repository_name",
        "repository_name",
        "repo_name",
    ):
        value = _tool_str_arg(plan, key)
        if value:
            found = _match_repository(value, repositories)
            if found is not None:
                return found

    ticket = get_ticket(ticket_id) if ticket_id else None
    if ticket is not None:
        for repo_id in ticket.code_repository_ids:
            found = get_code_repository(repo_id)
            if found is not None:
                return found

    for repository in repositories:
        lower = message.lower()
        if repository.id.lower() in lower or repository.name.lower() in lower:
            return repository

    enabled = [repository for repository in repositories if repository.enabled]
    if len(enabled) == 1 and (_message_mentions_repo_context(message) or ticket is not None):
        return enabled[0]
    return None


def _inspection_query(context: ChatRunContext, plan: ChatKernelCommandPlan | None) -> str:
    return _tool_str_arg(plan, "query", "q", "search") or context.request.message


def _complete_search_knowledge_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    query = _tool_str_arg(plan, "query", "q") or context.request.message
    response = search_knowledge_sync(query, limit=8)
    lines = [
        f"我搜索了 Knowledge，query: {query}",
        "",
        "结果：",
    ]
    if not response.results:
        lines.append("- 没有找到匹配的 Docs / Decisions / Memories。")
    for item in response.results:
        lines.append(
            f"- [{item.source_type}] {item.title} ({item.source_ref})；score={item.score:.2f}\n"
            f"  {item.content[:260]}"
        )
    lines.extend(["", "入口：", "- Knowledge Docs: #/assets/knowledge/docs"])

    result = {
        "status": "completed",
        "detail": "Searched local Knowledge docs, decisions, and approved memories.",
        "query": query,
        "results": [item.model_dump(mode="json") for item in response.results],
        "deep_links": {"knowledge_docs": "#/assets/knowledge/docs"},
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="search_knowledge",
        reply="\n".join(lines),
        result=result,
        completed=True,
    )


def _complete_list_tickets_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    items = list_tickets()
    lines = [f"我找到了 {len(items)} 个 Tickets。", ""]
    if not items:
        lines.append("- none")
    for item in items:
        lines.append(
            f"- {item.id}: {item.title}；status={item.status}；assigned={item.assigned_employee_id or item.assigned_role or '-'}；"
            f"validation={item.validation_employee_id or item.validation_role or '-'}；"
            f"repos={len(item.code_repository_ids)}；reports={len(item.reports)}"
        )
    lines.extend(["", "入口：", "- Tickets: #/tickets/tickets"])
    result = {
        "status": "completed",
        "detail": "Listed Tickets.",
        "tickets": [item.model_dump(mode="json") for item in items],
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="list_tickets",
        reply="\n".join(lines),
        result=result,
        completed=True,
    )


def _complete_self_bootstrap_summary_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    summary = self_bootstrap_learning_summary()
    lines = [
        "这是 AITeamOS 当前 self-bootstrap learning summary：",
        "",
        (
            f"- Tickets: {summary.ticket_count}；validated={summary.validated_ticket_count}；"
            f"blocked={summary.blocked_ticket_count}；needs_evidence={summary.tickets_missing_required_evidence}"
        ),
        (
            f"- Assets: candidates={summary.memory_candidates_produced}；approved_candidates={summary.approved_memory_candidates}；"
            f"recalled={summary.approved_memories_recalled}；graphiti_recalled={summary.graphiti_memories_recalled}；"
            f"useful_recall={summary.useful_memory_recalls}；"
            f"stale_or_superseded={summary.stale_or_superseded_assets}"
        ),
        f"- Learning delta: {summary.learning_delta}",
    ]
    if summary.tickets:
        lines.extend(["", "需要关注的 Ticket："])
        for ticket in summary.tickets[:5]:
            lines.append(
                f"- {ticket.ticket_id}: {ticket.title}；status={ticket.status}；"
                f"evidence={ticket.evidence_count}；recalled={ticket.approved_memories_recalled}；"
                f"next={ticket.next_learning_action}"
            )
    lines.extend(["", "入口：", "- Tickets: #/tickets/tickets"])
    result = {
        "status": "completed",
        "detail": "Summarized self-bootstrap learning facts.",
        "self_bootstrap_summary": summary.model_dump(mode="json"),
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="self_bootstrap_summary",
        reply="\n".join(lines),
        result=result,
        completed=True,
    )


def _complete_list_code_repositories_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    tool_result = _list_code_repositories_tool_result()
    result = {
        "status": "completed",
        "detail": "Listed configured code repositories.",
        **tool_result,
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="list_code_repositories",
        reply=_build_list_code_repositories_reply(tool_result),
        result=result,
        completed=True,
    )


def _inspection_report_content(repository_id: str, query: str, matches: list[dict[str, Any]], files: list[dict[str, Any]]) -> str:
    lines = [
        f"Repository inspection completed for {repository_id}.",
        f"Query: {query}",
        "",
        "Evidence:",
    ]
    if matches:
        for match in matches[:8]:
            lines.append(f"- {match['path']}:{match['line']} {match['excerpt']}")
    if files:
        for file in files[:3]:
            lines.append(f"- read {file['path']} ({len(file['content'])} chars)")
    if not matches and not files:
        lines.append("- No matching text files found.")
    return "\n".join(lines)


def _complete_inspect_code_repository_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    if context.employee.id == CLARA_SYSTEM_EMPLOYEE_ID:
        return _persist_kernel_command_response(
            context,
            handler_name="inspect_code_repository",
            reply=_build_blocked_command_reply(
                "inspect_code_repository",
                "Clara 是 control-plane manager，不直接读取代码仓库状态。",
                "请把 Ticket 委派给 Alex/RD/PV，例如：Alex，请检查 ticket-xxx 里的 AITeamOS repo 并写回报告。",
            ),
            result={"status": "blocked", "detail": "Clara cannot directly inspect repository state.", "plan": _plan_trace_data(plan)},
            completed=False,
        )

    message = context.request.message
    ticket_id = _extract_ticket_id(message, plan)
    repository = _resolve_inspection_repository(plan=plan, message=message, ticket_id=ticket_id)
    if repository is None:
        return _persist_kernel_command_response(
            context,
            handler_name="inspect_code_repository",
            reply=_build_blocked_command_reply(
                "inspect_code_repository",
                "没有识别到可用代码仓库。",
                "请先在 Settings / Code Repositories 配置 repo，或在消息中包含 repo id / repo name / ticket id。",
            ),
            result={"status": "blocked", "detail": "Missing repository context.", "plan": _plan_trace_data(plan)},
            completed=False,
        )

    query = _inspection_query(context, plan)
    file_paths = _extract_repo_file_paths(message, plan)
    try:
        inspection = inspect_code_repository(repository, query=query, file_paths=file_paths)
    except ValueError as exc:
        return _persist_kernel_command_response(
            context,
            handler_name="inspect_code_repository",
            reply=_build_blocked_command_reply(
                "inspect_code_repository",
                str(exc),
                "请确认 repo 是 enabled local repository，并且文件路径位于该 repo 内部。",
            ),
            result={
                "status": "blocked",
                "detail": str(exc),
                "repository_id": repository.id,
                "plan": _plan_trace_data(plan),
            },
            completed=False,
        )

    matches = [match.model_dump(mode="json") for match in inspection.matches]
    files = [file.model_dump(mode="json") for file in inspection.files]
    lines = [
        f"{context.employee.display_name} 已检查代码仓库。",
        "",
        f"- Repository: {repository.name} ({repository.id})",
        f"- Status: {inspection.status}",
        f"- Query: {query}",
        f"- Matches: {len(matches)}",
        f"- Files read: {len(files)}",
        "",
        "主要证据：",
    ]
    if not matches and not files:
        lines.append("- 未找到匹配的文本文件或可读文件。")
    for match in matches[:8]:
        lines.append(f"- {match['path']}:{match['line']} {match['excerpt']}")
    for file in files[:2]:
        excerpt = file["content"][:600].strip()
        lines.append(f"- Read {file['path']}:\n  {excerpt}")

    recorded_item = None
    if ticket_id and inspection.status == "completed":
        try:
            report_content = _inspection_report_content(repository.id, query, matches, files)
            recorded_item = add_ticket_report(
                ticket_id,
                TicketReportRequest(
                    reporter_employee_id=context.employee.id,
                    reporter_role=context.employee.role,
                    content=report_content,
                    evidence=[
                        f"repo:{repository.id}",
                        *[f"{match['path']}:{match['line']}" for match in matches[:8]],
                        *[f"file:{file['path']}" for file in files[:3]],
                    ],
                    report_type="repo_inspection",
                    source_run_id=context.run_id,
                ),
            )
            lines.extend(["", f"已写回 Ticket report: {recorded_item.id}"])
        except KeyError:
            lines.extend(["", f"未写回 Ticket：没有找到 {ticket_id}。"])

    result = {
        "status": inspection.status,
        "detail": inspection.detail,
        "repository": inspection.repository.model_dump(mode="json"),
        "query": query,
        "matches": matches,
        "files": files,
        "ticket": recorded_item.model_dump(mode="json") if recorded_item is not None else None,
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="inspect_code_repository",
        reply="\n".join(lines),
        result=result,
        completed=inspection.status == "completed",
    )


def _complete_create_ticket_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    assignee = _employee_from_plan_or_name(plan, "target_employee_id", "target_employee_name", "assigned_employee_id", "assignee")
    assigned_role = _tool_str_arg(plan, "assigned_role", "role")
    if assignee is None:
        assignee = _explicit_delegated_employee(message)
    if assignee is None:
        assignee, inferred_role = _default_ticket_assignee(message)
        assigned_role = assigned_role or inferred_role
    else:
        assigned_role = assigned_role or assignee.role

    validation_employee = _employee_from_plan_or_name(plan, "validation_employee_id", "validation_employee_name", "pv_employee_id")
    validation_role = _tool_str_arg(plan, "validation_role") or "AI PV"
    if validation_employee is None and assigned_role != "AI PV":
        validation_employee = _employee_for_role("AI PV") or _employee_for_role("AI QA / Harness Runner")
    if validation_employee is not None:
        validation_role = validation_employee.role

    code_repository_ids = _code_repository_ids_from_plan_or_message(plan, message)
    knowledge = search_knowledge_sync(message, limit=5)
    knowledge_refs = [f"{item.source_type}:{item.id}" for item in knowledge.results]
    try:
        item = create_ticket(
            TicketCreateRequest(
                title=_ticket_title(message, plan),
                description=_tool_str_arg(plan, "description", "body") or message,
                ticket_type=_tool_str_arg(plan, "ticket_type", "type", "namespace") or "",
                assigned_employee_id=assignee.id if assignee else "",
                assigned_role=assigned_role or "",
                validation_employee_id=validation_employee.id if validation_employee else "",
                validation_role=validation_role if validation_employee else validation_role,
                knowledge_refs=knowledge_refs,
                code_repository_ids=code_repository_ids,
                source_thread_id=context.thread_id,
                source_run_id=context.run_id,
                actor_employee_id=context.employee.id,
                actor_role=context.employee.role,
            )
        )
    except ValueError as exc:
        return _persist_kernel_command_response(
            context,
            handler_name="create_ticket",
            reply=_build_blocked_command_reply(
                "create_ticket",
                str(exc),
                "请让 Clara 创建跨域 Ticket，或让对应 role 的 Employee 创建自己的 Ticket namespace。",
            ),
            result={"status": "blocked", "detail": str(exc), "plan": _plan_trace_data(plan)},
            completed=False,
        )

    lines = [
        "已创建 Ticket。",
        "",
        f"- ID: {item.id}",
        f"- Title: {item.title}",
        f"- Assigned: {item.assigned_employee_id or item.assigned_role or '-'}",
        f"- Validation: {item.validation_employee_id or item.validation_role or '-'}",
        f"- Knowledge refs: {len(item.knowledge_refs)}",
        f"- Code repositories: {', '.join(item.code_repository_ids) if item.code_repository_ids else '-'}",
    ]
    if item.external_url:
        lines.append(f"- External link: {item.external_url}")
    lines.extend([
        "",
        "下一步：被分派的 Employee 应基于这些 Knowledge refs、自己的 Skills/Memory 和必要的 repo 状态执行；PV 负责验证后写回报告。",
    ])
    result = {
        "status": "completed",
        "detail": "Created a delegated Ticket.",
        "ticket": item.model_dump(mode="json"),
        "knowledge_results": [entry.model_dump(mode="json") for entry in knowledge.results],
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="create_ticket",
        reply="\n".join(lines),
        result=result,
        completed=True,
    )


def _complete_record_ticket_report_tool(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None = None,
) -> ChatMessageResponse:
    ticket_id = _extract_ticket_id(context.request.message, plan)
    if not ticket_id:
        return _persist_kernel_command_response(
            context,
            handler_name="record_ticket_report",
            reply=_build_blocked_command_reply(
                "record_ticket_report",
                "没有识别到 ticket id。",
                "请包含类似 ticket-xxx 的 Ticket ID。",
            ),
            result={"status": "blocked", "detail": "Missing ticket_id.", "plan": _plan_trace_data(plan)},
            completed=False,
        )

    reporter = _employee_from_plan_or_name(plan, "reporter_employee_id", "reporter_employee_name") or context.employee
    content = _tool_str_arg(plan, "content", "report") or context.request.message
    report_type = _tool_str_arg(plan, "report_type") or ("validation" if "验证" in context.request.message else "progress")
    evidence = _tool_list_arg(plan, "evidence") or []
    try:
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=reporter.id,
                reporter_role=reporter.role,
                content=content,
                evidence=evidence,
                report_type=report_type,
                source_run_id=context.run_id,
            ),
        )
    except KeyError:
        return _persist_kernel_command_response(
            context,
            handler_name="record_ticket_report",
            reply=_build_blocked_command_reply(
                "record_ticket_report",
                f"没有找到 Ticket: {ticket_id}",
                "请先让我列出 Tickets，或确认 ID 是否正确。",
            ),
            result={"status": "blocked", "detail": "Ticket not found.", "ticket_id": ticket_id},
            completed=False,
        )

    reply = (
        "已记录 Ticket 报告。\n\n"
        f"- ID: {item.id}\n"
        f"- Status: {item.status}\n"
        f"- Reporter: {reporter.display_name} ({reporter.role})\n"
        f"- Reports: {len(item.reports)}"
    )
    result = {
        "status": "completed",
        "detail": "Recorded a Ticket report.",
        "ticket": item.model_dump(mode="json"),
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="record_ticket_report",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_request_ticket_validation_tool(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None = None,
) -> ChatMessageResponse:
    ticket_id = _extract_ticket_id(context.request.message, plan)
    if not ticket_id:
        return _persist_kernel_command_response(
            context,
            handler_name="request_ticket_validation",
            reply=_build_blocked_command_reply(
                "request_ticket_validation",
                "没有识别到 ticket id。",
                "请包含类似 rd-0001 的 Ticket ID，并说明要交给谁验证。",
            ),
            result={"status": "blocked", "detail": "Missing ticket_id.", "plan": _plan_trace_data(plan)},
            completed=False,
        )

    validation_employee = _employee_from_plan_or_name(
        plan,
        "validation_employee_id",
        "validation_employee_name",
        "target_employee_id",
        "target_employee_name",
        "pv_employee_id",
    )
    validation_role = _tool_str_arg(plan, "validation_role", "role", "assigned_role") or "AI PV"
    if validation_employee is None:
        validation_employee = _employee_for_role(validation_role) or _employee_for_role("AI PV") or _employee_for_role("AI QA / Harness Runner")
    if validation_employee is not None:
        validation_role = validation_employee.role

    content = _tool_str_arg(plan, "content", "reason", "request") or context.request.message
    try:
        item = request_ticket_validation(
            ticket_id,
            TicketValidationRequest(
                validation_employee_id=validation_employee.id if validation_employee else "",
                validation_role=validation_role,
                content=content,
                actor_employee_id=context.employee.id,
                actor_role=context.employee.role,
                source_run_id=context.run_id,
            ),
        )
    except KeyError:
        return _persist_kernel_command_response(
            context,
            handler_name="request_ticket_validation",
            reply=_build_blocked_command_reply(
                "request_ticket_validation",
                f"没有找到 Ticket: {ticket_id}",
                "请先让我列出 Tickets，或确认 ID 是否正确。",
            ),
            result={"status": "blocked", "detail": "Ticket not found.", "ticket_id": ticket_id, "plan": _plan_trace_data(plan)},
            completed=False,
        )
    except ValueError as exc:
        return _persist_kernel_command_response(
            context,
            handler_name="request_ticket_validation",
            reply=_build_blocked_command_reply(
                "request_ticket_validation",
                str(exc),
                "请确认 Ticket backend 已就绪，并提供验证 Employee 或 role。",
            ),
            result={"status": "blocked", "detail": str(exc), "ticket_id": ticket_id, "plan": _plan_trace_data(plan)},
            completed=False,
        )

    reply = (
        "已请求 Ticket 验证。\n\n"
        f"- ID: {item.id}\n"
        f"- Status: {item.status}\n"
        f"- Validator: {item.validation_employee_id or item.validation_role or validation_role}\n"
        f"- External link: {item.external_url or '-'}"
    )
    result = {
        "status": "completed",
        "detail": "Requested Ticket validation.",
        "ticket": item.model_dump(mode="json"),
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="request_ticket_validation",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_request_human_review_tool(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None = None,
) -> ChatMessageResponse:
    ticket_id = _extract_ticket_id(context.request.message, plan)
    if not ticket_id:
        return _persist_kernel_command_response(
            context,
            handler_name="request_human_review",
            reply=_build_blocked_command_reply(
                "request_human_review",
                "没有识别到 ticket id。",
                "请包含类似 rd-0001 的 Ticket ID，并说明需要人类复核的原因。",
            ),
            result={"status": "blocked", "detail": "Missing ticket_id.", "plan": _plan_trace_data(plan)},
            completed=False,
        )

    reviewer = _employee_from_plan_or_name(
        plan,
        "reviewer_employee_id",
        "reviewer_employee_name",
        "human_employee_id",
        "human_employee_name",
        "target_employee_id",
        "target_employee_name",
    )
    reviewer_label = (
        reviewer.display_name
        if reviewer is not None
        else (_tool_str_arg(plan, "reviewer", "human_reviewer", "reviewer_name") or "human")
    )
    reason = _tool_str_arg(plan, "reason", "content", "request") or context.request.message
    evidence = _tool_list_arg(plan, "evidence") or []
    content = (
        "Human review requested.\n\n"
        f"Reviewer: {reviewer_label}\n"
        f"Reason: {reason}"
    )
    try:
        item = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id=context.employee.id,
                reporter_role=context.employee.role,
                content=content,
                evidence=evidence,
                report_type="human_review_requested",
                source_run_id=context.run_id,
            ),
        )
    except KeyError:
        return _persist_kernel_command_response(
            context,
            handler_name="request_human_review",
            reply=_build_blocked_command_reply(
                "request_human_review",
                f"没有找到 Ticket: {ticket_id}",
                "请先让我列出 Tickets，或确认 ID 是否正确。",
            ),
            result={"status": "blocked", "detail": "Ticket not found.", "ticket_id": ticket_id, "plan": _plan_trace_data(plan)},
            completed=False,
        )
    except ValueError as exc:
        return _persist_kernel_command_response(
            context,
            handler_name="request_human_review",
            reply=_build_blocked_command_reply(
                "request_human_review",
                str(exc),
                "请确认 Ticket Backend 已就绪，且这个 Ticket 可追加 review report。",
            ),
            result={"status": "blocked", "detail": str(exc), "ticket_id": ticket_id, "plan": _plan_trace_data(plan)},
            completed=False,
        )

    reply = (
        "已请求 Human Review。\n\n"
        f"- ID: {item.id}\n"
        f"- Status: {item.status}\n"
        f"- Reviewer: {reviewer_label}\n"
        f"- Requested by: {context.employee.display_name} ({context.employee.role})\n"
        f"- External link: {item.external_url or '-'}"
    )
    result = {
        "status": "completed",
        "detail": "Requested human review for a Ticket.",
        "ticket": item.model_dump(mode="json"),
        "reviewer": reviewer.model_dump(mode="json") if reviewer is not None else {"label": reviewer_label},
        "report_type": "human_review_requested",
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="request_human_review",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_create_employee_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    display_name = _tool_str_arg(plan, "display_name", "name") or _extract_employee_display_name(message)
    if not display_name:
        result = {
            "status": "blocked",
            "reason": "missing_display_name",
            "detail": "Employee display name was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_command_reply(
            "create_employee",
            "没有识别到成员名字。",
            "Clara，请创建一个 AI PV 成员，名字叫 Victor，负责 regression 和 harness fail triage。",
        )
        return _persist_kernel_command_response(
            context,
            handler_name="create_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    employee_id = _extract_explicit_employee_id(message) or _slugify_employee_id(display_name)
    planned_employee_id = _tool_str_arg(plan, "employee_id", "id")
    if planned_employee_id:
        employee_id = _slugify_employee_id(planned_employee_id)
    existing = _find_employee_profile(employee_id) or _find_employee_profile(display_name)
    if existing:
        existing_summary = _employee_summary(existing[1])
        result = {
            "status": "blocked",
            "reason": "employee_already_exists",
            "detail": f"Employee already exists: {existing_summary.id}",
            "employee": existing_summary.model_dump(),
            "deep_links": {
                "employee": f"#/employees/{existing_summary.id}",
                "employees": "#/employees",
            },
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有创建新成员，因为 {existing_summary.display_name} 已经存在。\n\n"
            f"- Employee: {existing_summary.display_name} ({existing_summary.id})\n"
            f"- Role: {existing_summary.role}\n"
            f"- 查看：#/employees/{existing_summary.id}\n\n"
            "如果你想修改它，可以说：Clara，请把 "
            f"{existing_summary.display_name} 的 summary 改成 ..."
        )
        return _persist_kernel_command_response(
            context,
            handler_name="create_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    kind = (_tool_str_arg(plan, "kind") or _extract_employee_kind(message)).lower()
    kind = "human" if kind == "human" else "ai"
    planned_role = _tool_str_arg(plan, "role")
    role = _normalize_role_value(planned_role) if planned_role else _extract_employee_role(message)
    role = role or ("Human Employee" if kind == "human" else "AI Employee")
    responsibility = _tool_str_arg(plan, "responsibility") or _extract_summary(message)
    summary = _tool_str_arg(plan, "summary") or _default_summary(display_name, role, responsibility)
    skills = _tool_list_arg(plan, "skills") or _extract_skills_value(message) or _default_skills_for_role(role)
    profile = _build_employee_profile(
        employee_id=employee_id,
        display_name=display_name,
        kind=kind,
        role=role,
        summary=summary,
        skills=_dedupe(skills),
        responsibility=responsibility,
    )
    profile_path = _employee_profile_path(employee_id)
    _write_yaml(profile_path, profile)

    employee = _employee_summary(profile)
    result = {
        "status": "completed",
        "detail": f"Created employee profile: {employee.id}",
        "employee": employee.model_dump(),
        "saved_path": str(profile_path.relative_to(_workspace_root())),
        "deep_links": {
            "employee": f"#/employees/{employee.id}",
            "employees": "#/employees",
        },
        "plan": _plan_trace_data(plan),
    }
    reply = (
        f"已创建成员 {employee.display_name}。\n\n"
        f"- ID: {employee.id}\n"
        f"- Type: {employee.kind}\n"
        f"- Role: {employee.role}\n"
        f"- Skills: {', '.join(employee.skills) if employee.skills else 'none'}\n"
        f"- Profile: {result['saved_path']}\n"
        f"- 查看：#/employees/{employee.id}\n\n"
        "下一步可以直接点名它协作，或让我继续编辑它的 profile。"
    )
    return _persist_kernel_command_response(
        context,
        handler_name="create_employee",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_edit_employee_profile_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    target_id = (
        _tool_str_arg(plan, "target_employee_id", "employee_id", "id")
        or _tool_str_arg(plan, "target_employee_name", "display_name", "name")
        or _extract_edit_employee_target(message, context)
    )
    if not target_id:
        result = {
            "status": "blocked",
            "reason": "missing_target_employee",
            "detail": "Target employee was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_command_reply(
            "edit_employee_profile",
            "没有识别到要编辑哪个成员。",
            "Clara，请把 Alex 的 summary 改成 Implementation owner for backend API Tickets。",
        )
        return _persist_kernel_command_response(
            context,
            handler_name="edit_employee_profile",
            reply=reply,
            result=result,
            completed=False,
        )

    found = _find_employee_profile(target_id)
    if not found:
        result = {
            "status": "blocked",
            "reason": "employee_not_found",
            "detail": f"Employee not found: {target_id}",
            "deep_links": {"employees": "#/employees"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到成员 {target_id}，所以没有修改 profile。\n\n"
            "你可以先让我列出所有成员，或先创建这个成员。\n"
            "- Employees: #/employees"
        )
        return _persist_kernel_command_response(
            context,
            handler_name="edit_employee_profile",
            reply=reply,
            result=result,
            completed=False,
        )

    profile_path, profile = found
    updates: dict[str, Any] = {}
    new_display_name = _tool_str_arg(plan, "new_display_name", "display_name", "name") or _extract_new_display_name(message)
    planned_role = _tool_str_arg(plan, "role")
    new_role = _normalize_role_value(planned_role) if planned_role else _extract_employee_role(message, require_role_marker=True)
    new_summary = _tool_str_arg(plan, "summary") or _extract_summary(message)
    replace_skills = _tool_list_arg(plan, "skills") or _extract_skills_value(message)
    add_skills = _tool_list_arg(plan, "add_skills") or _extract_add_skills_value(message)
    ai_engine_mode = _tool_str_arg(plan, "ai_engine_mode", "ai_engine.mode") or _extract_ai_engine_mode(message)

    if _is_clara_system_employee_id(str(profile.get("id") or profile_path.stem)):
        protected_updates: dict[str, str] = {}
        if new_display_name and new_display_name != CLARA_SYSTEM_DISPLAY_NAME:
            protected_updates["display_name"] = CLARA_SYSTEM_DISPLAY_NAME
        if new_role and new_role != CLARA_SYSTEM_ROLE:
            protected_updates["role"] = CLARA_SYSTEM_ROLE
        if protected_updates:
            result = {
                "status": "blocked",
                "reason": "protected_system_employee_fields",
                "detail": "Clara's system identity fields cannot be changed.",
                "protected_fields": protected_updates,
                "deep_links": {"employee": "#/employees/clara", "employees": "#/employees"},
                "plan": _plan_trace_data(plan),
            }
            reply = (
                "没有修改 Clara 的系统身份字段。\n\n"
                "原因：Clara 是 AITeamOS 的系统默认 Employee，display name 和 role 固定为 "
                f"{CLARA_SYSTEM_DISPLAY_NAME} / {CLARA_SYSTEM_ROLE}。\n"
                "- 查看：#/employees/clara"
            )
            return _persist_kernel_command_response(
                context,
                handler_name="edit_employee_profile",
                reply=reply,
                result=result,
                completed=False,
            )

    if new_display_name:
        profile["display_name"] = new_display_name
        updates["display_name"] = new_display_name
    if new_role:
        profile["role"] = new_role
        updates["role"] = new_role
    if new_summary:
        profile["summary"] = new_summary
        updates["summary"] = new_summary
    if replace_skills is not None:
        profile["skills"] = _dedupe(replace_skills)
        updates["skills"] = profile["skills"]
    elif add_skills:
        current_skills = [str(skill) for skill in profile.get("skills", [])]
        profile["skills"] = _dedupe([*current_skills, *add_skills])
        updates["skills"] = profile["skills"]
    if ai_engine_mode:
        ai_engine = profile.get("ai_engine") if isinstance(profile.get("ai_engine"), dict) else {}
        ai_engine["mode"] = ai_engine_mode
        profile["ai_engine"] = ai_engine
        updates["ai_engine.mode"] = ai_engine_mode

    if not updates:
        result = {
            "status": "blocked",
            "reason": "no_supported_updates",
            "detail": "No supported employee profile fields were found in the request.",
            "supported_fields": ["display_name", "role", "summary", "skills", "ai_engine.mode"],
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_command_reply(
            "edit_employee_profile",
            "没有识别到可更新字段。",
            "Clara，请把 Alex 的 role 改成 AI RD / Implementer，并添加技能 test-engineering。",
        )
        return _persist_kernel_command_response(
            context,
            handler_name="edit_employee_profile",
            reply=reply,
            result=result,
            completed=False,
        )

    profile["updated_at"] = _now()
    _write_yaml(profile_path, profile)
    employee = _employee_summary(profile)
    result = {
        "status": "completed",
        "detail": f"Updated employee profile: {employee.id}",
        "employee": employee.model_dump(),
        "updates": updates,
        "saved_path": str(profile_path.relative_to(_workspace_root())),
        "deep_links": {
            "employee": f"#/employees/{employee.id}",
            "employees": "#/employees",
        },
        "plan": _plan_trace_data(plan),
    }
    changed = "\n".join(f"- {key}: {value}" for key, value in updates.items())
    reply = (
        f"已更新成员 {employee.display_name} 的 profile。\n\n"
        f"{changed}\n\n"
        f"- Profile: {result['saved_path']}\n"
        f"- 查看：#/employees/{employee.id}"
    )
    return _persist_kernel_command_response(
        context,
        handler_name="edit_employee_profile",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_delete_employee_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    target_id = (
        _tool_str_arg(plan, "target_employee_id", "employee_id", "id")
        or _tool_str_arg(plan, "target_employee_name", "display_name", "name")
        or _extract_edit_employee_target(message, context)
    )
    if not target_id:
        result = {
            "status": "blocked",
            "reason": "missing_target_employee",
            "detail": "Target employee was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_command_reply(
            "delete_employee",
            "没有识别到要删除哪个成员。",
            "Clara，请删除成员 Victor。",
        )
        return _persist_kernel_command_response(
            context,
            handler_name="delete_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    found = _find_employee_profile(target_id)
    if not found:
        result = {
            "status": "blocked",
            "reason": "employee_not_found",
            "detail": f"Employee not found: {target_id}",
            "deep_links": {"employees": "#/employees"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到成员 {target_id}，所以没有删除任何 profile。\n\n"
            "你可以先让我列出所有成员。\n"
            "- Employees: #/employees"
        )
        return _persist_kernel_command_response(
            context,
            handler_name="delete_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    profile_path, profile = found
    employee = _employee_summary(profile)
    if employee.id == CLARA_SYSTEM_EMPLOYEE_ID:
        result = {
            "status": "blocked",
            "reason": "protected_employee",
            "detail": "Clara is the protected default system employee and cannot be deleted.",
            "employee": employee.model_dump(),
            "deep_links": {"employee": "#/employees/clara", "employees": "#/employees"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            "没有删除 Clara。\n\n"
            "原因：Clara 是 AITeamOS 的系统默认 Employee，负责团队运营与系统资产管理，永远不允许删除。\n"
            "- 查看：#/employees/clara"
        )
        return _persist_kernel_command_response(
            context,
            handler_name="delete_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    relative_profile_path = str(profile_path.relative_to(_workspace_root()))
    try:
        profile_path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot delete employee profile: {employee.id}") from exc
    removed_engine_thread_keys = _delete_engine_thread_states(_workspace_dir(), employee.id)
    archived_thread_ids = _archive_employee_thread_metadata(employee.id)

    result = {
        "status": "completed",
        "detail": f"Deleted employee profile: {employee.id}",
        "employee": employee.model_dump(),
        "deleted_path": relative_profile_path,
        "engine_thread_keys_removed": removed_engine_thread_keys,
        "archived_thread_ids": archived_thread_ids,
        "retained_evidence": ["conversations", "traces"],
        "deep_links": {"employees": "#/employees"},
        "plan": _plan_trace_data(plan),
    }
    reply = (
        f"已删除成员 {employee.display_name}。\n\n"
        f"- ID: {employee.id}\n"
        f"- Profile: {relative_profile_path}\n"
        f"- 清理 AI Engine thread 映射：{len(removed_engine_thread_keys)} 条\n"
        f"- 归档 chat threads：{len(archived_thread_ids)} 条\n"
        "- 历史 conversation 和 trace 已保留，用于审计。\n"
        "- Employees: #/employees"
    )
    return _persist_kernel_command_response(
        context,
        handler_name="delete_employee",
        reply=reply,
        result=result,
        completed=True,
    )


def _default_skill_body(skill_id: str, title: str, description: str) -> str:
    return (
        f"# {title}\n\n"
        f"> {description or f'AITeamOS reusable skill: {skill_id}.'}\n\n"
        "## When To Use\n\n"
        "- Use this skill when Ticket work matches the description above.\n\n"
        "## Procedure\n\n"
        "1. Clarify the goal, constraints, and expected evidence.\n"
        "2. Apply the relevant product context and tools.\n"
        "3. Report outcome, evidence, blockers, and next actions.\n"
    )


def _complete_create_skill_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    title = (
        _tool_str_arg(plan, "title", "display_name", "name")
        or _extract_skill_name(message)
    )
    if not title:
        result = {
            "status": "blocked",
            "reason": "missing_skill_title",
            "detail": "Skill title was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_command_reply(
            "create_skill",
            "没有识别到 Skill 名称。",
            "Clara，请创建一个 Skill，名字叫 nightly-regression-log-triage，用于分析 nightly regression log。",
        )
        return _persist_kernel_command_response(
            context,
            handler_name="create_skill",
            reply=reply,
            result=result,
            completed=False,
        )

    planned_skill_id = _tool_str_arg(plan, "skill_id", "id")
    skill_id = _slugify_skill_id(planned_skill_id or title)
    existing = _find_skill(skill_id) or _find_skill(title)
    if existing:
        result = {
            "status": "blocked",
            "reason": "skill_already_exists",
            "detail": f"Skill already exists: {existing.id}",
            "skill": existing.model_dump(),
            "deep_links": {"skill": f"#/assets/capabilities/skills/{existing.id}", "skills": "#/assets/capabilities/skills"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有创建新 Skill，因为 {existing.title} 已经存在。\n\n"
            f"- Skill: {existing.title} ({existing.id})\n"
            f"- 查看：#/assets/capabilities/skills/{existing.id}\n\n"
            "如果要分配它，可以说：Clara，请把 "
            f"{existing.id} 分配给 Alex。"
        )
        return _persist_kernel_command_response(
            context,
            handler_name="create_skill",
            reply=reply,
            result=result,
            completed=False,
        )

    description = (
        _tool_str_arg(plan, "description", "summary", "purpose")
        or _extract_skill_description(message)
        or f"AITeamOS reusable skill: {skill_id}."
    )
    body = _tool_str_arg(plan, "body", "instructions") or _default_skill_body(skill_id, title, description)
    skill_path = _skill_file_path(skill_id)
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(body.strip() + "\n", encoding="utf-8")
    skill = _skill_summary(skill_path)

    result = {
        "status": "completed",
        "detail": f"Created skill: {skill.id}",
        "skill": skill.model_dump(),
        "saved_path": str(skill_path.relative_to(_workspace_root())),
        "deep_links": {"skill": f"#/assets/capabilities/skills/{skill.id}", "skills": "#/assets/capabilities/skills"},
        "plan": _plan_trace_data(plan),
    }
    reply = (
        f"已创建 Skill {skill.title}。\n\n"
        f"- ID: {skill.id}\n"
        f"- Description: {skill.description or 'none'}\n"
        f"- Profile: {result['saved_path']}\n"
        f"- 查看：#/assets/capabilities/skills/{skill.id}\n\n"
        "下一步可以把它分配给一个或多个 Employees。"
    )
    return _persist_kernel_command_response(
        context,
        handler_name="create_skill",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_assign_skill_to_employee_tool(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None = None,
) -> ChatMessageResponse:
    message = context.request.message
    skill_lookup = (
        _tool_str_arg(plan, "skill_id", "id")
        or _tool_str_arg(plan, "skill_name", "title", "name")
        or _extract_existing_skill_id(message)
    )
    target_id = (
        _tool_str_arg(plan, "target_employee_id", "employee_id")
        or _tool_str_arg(plan, "target_employee_name", "display_name", "employee_name")
        or _extract_edit_employee_target(message, context)
    )
    if not skill_lookup:
        result = {
            "status": "blocked",
            "reason": "missing_skill",
            "detail": "Skill was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_command_reply(
            "assign_skill_to_employee",
            "没有识别到要分配哪个 Skill。",
            "Clara，请把 test-engineering 分配给 Alex。",
        )
        return _persist_kernel_command_response(
            context,
            handler_name="assign_skill_to_employee",
            reply=reply,
            result=result,
            completed=False,
        )
    if not target_id:
        result = {
            "status": "blocked",
            "reason": "missing_target_employee",
            "detail": "Target employee was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_command_reply(
            "assign_skill_to_employee",
            "没有识别到要分配给哪个成员。",
            "Clara，请把 test-engineering 分配给 Alex。",
        )
        return _persist_kernel_command_response(
            context,
            handler_name="assign_skill_to_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    skill = _find_skill(skill_lookup)
    if not skill:
        result = {
            "status": "blocked",
            "reason": "skill_not_found",
            "detail": f"Skill not found: {skill_lookup}",
            "deep_links": {"skills": "#/assets/capabilities/skills"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到 Skill {skill_lookup}，所以没有分配。\n\n"
            "你可以先让我列出所有 Skills，或先创建这个 Skill。\n"
            "- Skills: #/assets/capabilities/skills"
        )
        return _persist_kernel_command_response(
            context,
            handler_name="assign_skill_to_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    found = _find_employee_profile(target_id)
    if not found:
        result = {
            "status": "blocked",
            "reason": "employee_not_found",
            "detail": f"Employee not found: {target_id}",
            "deep_links": {"employees": "#/employees"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到成员 {target_id}，所以没有分配 Skill。\n\n"
            "你可以先让我列出所有成员。\n"
            "- Employees: #/employees"
        )
        return _persist_kernel_command_response(
            context,
            handler_name="assign_skill_to_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    profile_path, profile = found
    current_skills = [str(item) for item in profile.get("skills", [])]
    profile["skills"] = _dedupe([*current_skills, skill.id])
    profile["updated_at"] = _now()
    _write_yaml(profile_path, profile)
    employee = _employee_summary(profile)

    result = {
        "status": "completed",
        "detail": f"Assigned skill {skill.id} to employee {employee.id}",
        "skill": skill.model_dump(),
        "employee": employee.model_dump(),
        "saved_path": str(profile_path.relative_to(_workspace_root())),
        "deep_links": {
            "skill": f"#/assets/capabilities/skills/{skill.id}",
            "employee": f"#/employees/{employee.id}",
            "skills": "#/assets/capabilities/skills",
            "employees": "#/employees",
        },
        "plan": _plan_trace_data(plan),
    }
    reply = (
        f"已把 Skill {skill.title} 分配给 {employee.display_name}。\n\n"
        f"- Skill: {skill.id}\n"
        f"- Employee: {employee.display_name} ({employee.id})\n"
        f"- Employee skills: {', '.join(employee.skills) if employee.skills else 'none'}\n"
        f"- Profile: {result['saved_path']}\n"
        f"- 查看 Skill：#/assets/capabilities/skills/{skill.id}\n"
        f"- 查看 Employee：#/employees/{employee.id}"
    )
    return _persist_kernel_command_response(
        context,
        handler_name="assign_skill_to_employee",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_delete_skill_tool(context: ChatRunContext, plan: ChatKernelCommandPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    skill_lookup = (
        _tool_str_arg(plan, "skill_id", "id")
        or _tool_str_arg(plan, "skill_name", "title", "name")
        or _extract_existing_skill_id(message)
        or _extract_skill_target(message)
    )
    if not skill_lookup:
        result = {
            "status": "blocked",
            "reason": "missing_skill",
            "detail": "Skill was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_command_reply(
            "delete_skill",
            "没有识别到要删除哪个 Skill。",
            "Clara，请删除 Skill nightly-regression-log-triage。",
        )
        return _persist_kernel_command_response(
            context,
            handler_name="delete_skill",
            reply=reply,
            result=result,
            completed=False,
        )

    skill = _find_skill(skill_lookup)
    if not skill:
        result = {
            "status": "blocked",
            "reason": "skill_not_found",
            "detail": f"Skill not found: {skill_lookup}",
            "deep_links": {"skills": "#/assets/capabilities/skills"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到 Skill {skill_lookup}，所以没有删除任何文件。\n\n"
            "你可以先让我列出所有 Skills。\n"
            "- Skills: #/assets/capabilities/skills"
        )
        return _persist_kernel_command_response(
            context,
            handler_name="delete_skill",
            reply=reply,
            result=result,
            completed=False,
        )
    if skill.source != "local":
        result = {
            "status": "blocked",
            "reason": "builtin_skill_read_only",
            "detail": f"Built-in validation Skill cannot be deleted: {skill.id}",
            "skill": skill.model_dump(),
            "deep_links": {"skills": "#/assets/capabilities/skills"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"不能删除内建验证 Skill {skill.title}。\n\n"
            f"- Skill: {skill.id}\n"
            f"- Source: {skill.source}\n"
            "- 这些 Phase 5 验证 Skill 是只读基线；如需定制，可以创建同名本地 SKILL.md 覆盖它。\n"
            "- Skills: #/assets/capabilities/skills"
        )
        return _persist_kernel_command_response(
            context,
            handler_name="delete_skill",
            reply=reply,
            result=result,
            completed=False,
        )

    skill_dir = _skill_dir(skill.id)
    relative_skill_dir = str(skill_dir.relative_to(_workspace_root()))
    unassigned_employees: list[str] = []
    employees_dir = _employees_dir()
    if employees_dir.exists():
        for profile_path in sorted(employees_dir.glob("*.yaml")):
            profile = _read_yaml(profile_path)
            current_skills = [str(item) for item in profile.get("skills", [])]
            next_skills = [item for item in current_skills if item != skill.id]
            if len(next_skills) == len(current_skills):
                continue
            profile["skills"] = next_skills
            profile["updated_at"] = _now()
            _write_yaml(profile_path, profile)
            unassigned_employees.append(str(profile.get("id") or profile_path.stem))

    try:
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot delete skill: {skill.id}") from exc

    result = {
        "status": "completed",
        "detail": f"Deleted skill: {skill.id}",
        "skill": skill.model_dump(),
        "deleted_path": relative_skill_dir,
        "unassigned_employees": unassigned_employees,
        "retained_evidence": ["conversations", "traces"],
        "deep_links": {"skills": "#/assets/capabilities/skills", "employees": "#/employees"},
        "plan": _plan_trace_data(plan),
    }
    unassigned_text = ", ".join(unassigned_employees) if unassigned_employees else "none"
    reply = (
        f"已删除 Skill {skill.title}。\n\n"
        f"- ID: {skill.id}\n"
        f"- Deleted: {relative_skill_dir}\n"
        f"- 已从成员移除：{unassigned_text}\n"
        "- 历史 conversation 和 trace 已保留，用于审计。\n"
        "- Skills: #/assets/capabilities/skills"
    )
    return _persist_kernel_command_response(
        context,
        handler_name="delete_skill",
        reply=reply,
        result=result,
        completed=True,
    )


def _select_employee(
    profiles: list[dict[str, Any]],
    *,
    requested_employee_id: str | None,
    message: str,
) -> dict[str, Any]:
    by_id = {str(profile.get("id", "")).lower(): profile for profile in profiles}
    by_name = {
        str(profile.get("display_name", "")).lower(): profile
        for profile in profiles
        if profile.get("display_name")
    }

    mention = re.search(r"@([A-Za-z][\w-]*)", message)
    if mention:
        key = mention.group(1).lower()
        if key in by_id:
            return by_id[key]
        if key in by_name:
            return by_name[key]

    trimmed = message.strip().lower()
    for key, profile in {**by_id, **by_name}.items():
        if trimmed.startswith(f"{key},") or trimmed.startswith(f"{key}:") or trimmed.startswith(f"{key}，"):
            return profile

    if requested_employee_id:
        key = requested_employee_id.lower()
        if key in by_id:
            return by_id[key]
        raise HTTPException(status_code=404, detail=f"Employee not found: {requested_employee_id}")

    return by_id.get("clara") or profiles[0]


def _normalize_ticket_key(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    if _LOCAL_TICKET_ID_RE.fullmatch(candidate):
        return candidate.lower()
    return candidate.upper()


def _extract_ticket_keys(message: str, explicit: str | None) -> list[str]:
    keys: list[str] = []
    if explicit:
        keys.append(_normalize_ticket_key(explicit))
    keys.extend(_normalize_ticket_key(match) for match in _TICKET_KEY_RE.findall(message))
    return sorted(set(filter(None, keys)))


def _ensure_run_dirs() -> dict[str, Path]:
    return _store_ensure_run_dirs(_workspace_dir())


def _threads_dir() -> Path:
    return _store_threads_dir(_workspace_dir())


def _thread_index_path() -> Path:
    return _store_thread_index_path(_workspace_dir())


def _conversation_path(thread_id: str) -> Path:
    return _store_conversation_path(
        _workspace_dir(),
        thread_id,
        require_safe_id=lambda value: _require_safe_id(value, field="thread_id"),
    )


def _load_conversation_messages(thread_id: str, *, limit: int | None = None) -> list[ConversationMessage]:
    return _store_load_conversation_messages(
        _workspace_dir(),
        thread_id,
        message_model=ConversationMessage,
        require_safe_id=lambda value: _require_safe_id(value, field="thread_id"),
        limit=limit,
    )


def _load_thread_index() -> dict[str, Any]:
    return _store_load_thread_index(_workspace_dir())


def _write_thread_index(index: dict[str, Any]) -> None:
    _store_write_thread_index(_workspace_dir(), index, updated_at=_now())


def _thread_index_saved_path() -> str:
    return _store_thread_index_saved_path(_workspace_dir(), _workspace_root())


def _conversation_saved_path(thread_id: str) -> str:
    return _store_conversation_saved_path(
        _workspace_dir(),
        _workspace_root(),
        thread_id,
        require_safe_id=lambda value: _require_safe_id(value, field="thread_id"),
    )


def _thread_title_from_message(content: str) -> str:
    return _store_thread_title_from_message(content)


def _default_thread_title(employee: ChatEmployeeSummary, thread_id: str) -> str:
    if thread_id == _employee_default_thread_id(employee.id):
        return f"{employee.display_name} default"
    return f"{employee.display_name} thread"


def _employee_by_id(employee_id: str) -> ChatEmployeeSummary | None:
    lookup = employee_id.strip().lower()
    for profile in _load_employees():
        employee = _employee_summary(profile)
        if employee.id.lower() == lookup:
            return employee
    return None


def _require_employee_summary(employee_id: str) -> ChatEmployeeSummary:
    employee_id = _require_safe_id(employee_id, field="employee_id")
    employee = _employee_by_id(employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail=f"Employee not found: {employee_id}")
    return employee


def _infer_thread_employee_id(thread_id: str, employees: list[ChatEmployeeSummary]) -> str | None:
    for employee in sorted(employees, key=lambda item: len(item.id), reverse=True):
        safe_employee = _safe_thread_component(employee.id)
        if thread_id == _employee_default_thread_id(employee.id) or thread_id.startswith(f"employee-{safe_employee}-"):
            return employee.id
    return None


def _thread_summary_from_record(thread_id: str, record: dict[str, Any]) -> ChatThreadSummary:
    return ChatThreadSummary(
        id=thread_id,
        employee_id=str(record.get("employee_id") or ""),
        title=str(record.get("title") or "New thread"),
        created_at=str(record.get("created_at") or _now()),
        updated_at=str(record.get("updated_at") or record.get("last_message_at") or _now()),
        last_message_at=str(record["last_message_at"]) if record.get("last_message_at") else None,
        message_count=int(record.get("message_count") or 0),
        archived=bool(record.get("archived", False)),
        saved_path=_conversation_saved_path(thread_id),
    )


def _conversation_metadata(thread_id: str, employees: list[ChatEmployeeSummary]) -> dict[str, Any]:
    messages = _load_conversation_messages(thread_id)
    first_user = next((message for message in messages if message.role == "user" and message.content.strip()), None)
    first_assistant = next((message for message in messages if message.employee_id), None)
    created_at = messages[0].timestamp if messages else _now()
    updated_at = messages[-1].timestamp if messages else created_at
    employee_id = first_assistant.employee_id if first_assistant and first_assistant.employee_id else None
    employee_id = employee_id or _infer_thread_employee_id(thread_id, employees)
    return {
        "employee_id": employee_id,
        "title": _thread_title_from_message(first_user.content) if first_user else None,
        "created_at": created_at,
        "updated_at": updated_at,
        "last_message_at": updated_at if messages else None,
        "message_count": len(messages),
    }


def _hydrate_thread_index() -> dict[str, Any]:
    index = _load_thread_index()
    threads = index["threads"]
    active_by_employee = index["active_by_employee"]
    employees = sorted((_employee_summary(profile) for profile in _load_employees()), key=_employee_sort_key)
    employee_by_id = {employee.id: employee for employee in employees}
    changed = False
    now = _now()

    for employee in employees:
        default_thread_id = _employee_default_thread_id(employee.id)
        if default_thread_id not in threads:
            threads[default_thread_id] = {
                "id": default_thread_id,
                "employee_id": employee.id,
                "title": _default_thread_title(employee, default_thread_id),
                "created_at": now,
                "updated_at": now,
                "last_message_at": None,
                "message_count": 0,
                "archived": False,
            }
            changed = True

    conversations_dir = _workspace_dir() / "conversations"
    if conversations_dir.exists():
        for path in sorted(conversations_dir.glob("*.jsonl")):
            thread_id = path.stem
            if not _SAFE_ID_RE.fullmatch(thread_id):
                continue
            metadata = _conversation_metadata(thread_id, employees)
            employee_id = metadata["employee_id"]
            if not employee_id:
                continue
            existing = threads.get(thread_id) or {}
            record = {
                "id": thread_id,
                "employee_id": str(existing.get("employee_id") or employee_id),
                "title": str(existing.get("title") or metadata.get("title") or "New thread"),
                "created_at": str(existing.get("created_at") or metadata["created_at"]),
                "updated_at": str(metadata["updated_at"] or existing.get("updated_at") or now),
                "last_message_at": metadata.get("last_message_at") or existing.get("last_message_at"),
                "message_count": int(metadata.get("message_count") or existing.get("message_count") or 0),
                "archived": bool(existing.get("archived", False)),
            }
            if threads.get(thread_id) != record:
                threads[thread_id] = record
                changed = True

    for employee in employees:
        employee_threads = [
            _thread_summary_from_record(thread_id, record)
            for thread_id, record in threads.items()
            if record.get("employee_id") == employee.id and not bool(record.get("archived", False))
        ]
        if not employee_threads:
            continue
        active_thread_id = active_by_employee.get(employee.id)
        if active_thread_id not in {thread.id for thread in employee_threads}:
            latest = max(employee_threads, key=lambda thread: (thread.last_message_at or thread.updated_at, thread.id))
            active_by_employee[employee.id] = latest.id
            changed = True

    for employee_id, active_thread_id in list(active_by_employee.items()):
        record = threads.get(active_thread_id)
        if employee_id not in employee_by_id or not record or record.get("employee_id") != employee_id:
            active_by_employee.pop(employee_id, None)
            changed = True

    if changed:
        _write_thread_index(index)
    return index


def _upsert_thread_metadata(
    *,
    employee: ChatEmployeeSummary,
    thread_id: str,
    title: str | None = None,
    set_active: bool = False,
) -> ChatThreadSummary:
    thread_id = _require_safe_id(thread_id, field="thread_id")
    index = _hydrate_thread_index()
    threads = index["threads"]
    record = dict(threads.get(thread_id) or {})
    now = _now()
    record.setdefault("id", thread_id)
    record["employee_id"] = str(record.get("employee_id") or employee.id)
    record.setdefault("created_at", now)
    record["updated_at"] = now
    record.setdefault("last_message_at", None)
    record.setdefault("message_count", 0)
    record.setdefault("archived", False)

    next_title = (title or "").strip()
    if next_title:
        record["title"] = _thread_title_from_message(next_title)
    else:
        record.setdefault("title", _default_thread_title(employee, thread_id))

    threads[thread_id] = record
    if set_active:
        index["active_by_employee"][employee.id] = thread_id
    _write_thread_index(index)
    return _thread_summary_from_record(thread_id, record)


def _record_chat_thread_turn(context: ChatRunContext, *, last_message_at: str) -> ChatThreadSummary:
    index = _hydrate_thread_index()
    threads = index["threads"]
    record = dict(threads.get(context.thread_id) or {})
    now = _now()
    existing_title = str(record.get("title") or "").strip()
    title = existing_title
    if not title or title == _default_thread_title(context.employee, context.thread_id):
        title = _thread_title_from_message(context.request.message)

    messages = _load_conversation_messages(context.thread_id)
    created_at = str(record.get("created_at") or (messages[0].timestamp if messages else now))
    record.update({
        "id": context.thread_id,
        "employee_id": context.employee.id,
        "title": title,
        "created_at": created_at,
        "updated_at": last_message_at,
        "last_message_at": last_message_at,
        "message_count": len(messages),
        "archived": False,
    })
    threads[context.thread_id] = record
    index["active_by_employee"][context.employee.id] = context.thread_id
    _write_thread_index(index)
    return _thread_summary_from_record(context.thread_id, record)


def _thread_summary(thread_id: str) -> ChatThreadSummary | None:
    thread_id = _require_safe_id(thread_id, field="thread_id")
    index = _hydrate_thread_index()
    record = index["threads"].get(thread_id)
    return _thread_summary_from_record(thread_id, record) if isinstance(record, dict) else None


def _list_employee_threads(employee_id: str) -> ChatThreadListResponse:
    employee = _require_employee_summary(employee_id)
    index = _hydrate_thread_index()
    threads = [
        _thread_summary_from_record(thread_id, record)
        for thread_id, record in index["threads"].items()
        if record.get("employee_id") == employee.id and not bool(record.get("archived", False))
    ]
    threads.sort(key=lambda thread: (thread.last_message_at or thread.updated_at, thread.id), reverse=True)
    active_thread_id = index["active_by_employee"].get(employee.id) or _employee_default_thread_id(employee.id)
    if active_thread_id not in {thread.id for thread in threads} and threads:
        active_thread_id = threads[0].id
    return ChatThreadListResponse(employee_id=employee.id, active_thread_id=active_thread_id, threads=threads)


def _activate_thread_metadata(thread_id: str, employee_id: str | None = None) -> ChatThreadSummary:
    thread_id = _require_safe_id(thread_id, field="thread_id")
    summary = _thread_summary(thread_id)
    if summary is None:
        if not employee_id:
            raise HTTPException(status_code=404, detail=f"Thread not found: {thread_id}")
        employee = _require_employee_summary(employee_id)
        return _upsert_thread_metadata(employee=employee, thread_id=thread_id, set_active=True)

    employee = _require_employee_summary(employee_id or summary.employee_id)
    if summary.employee_id != employee.id:
        raise HTTPException(status_code=400, detail="Thread does not belong to the requested employee")
    return _upsert_thread_metadata(employee=employee, thread_id=thread_id, title=summary.title, set_active=True)


def _archive_employee_thread_metadata(employee_id: str) -> list[str]:
    index = _hydrate_thread_index()
    removed: list[str] = []
    now = _now()
    for thread_id, record in index["threads"].items():
        if record.get("employee_id") != employee_id:
            continue
        record["archived"] = True
        record["updated_at"] = now
        removed.append(thread_id)
    index["active_by_employee"].pop(employee_id, None)
    if removed:
        _write_thread_index(index)
    return removed


def _skill_titles(skill_ids: list[str]) -> list[str]:
    titles: list[str] = []
    for skill_id in skill_ids:
        skill_path = _workspace_dir() / "skills" / skill_id / "SKILL.md"
        if not skill_path.exists():
            titles.append(skill_id)
            continue
        title = skill_id
        try:
            for line in skill_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    title = line.removeprefix("# ").strip() or skill_id
                    break
        except OSError:
            title = skill_id
        titles.append(title)
    return titles


def _read_skill_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read skill: {path.parent.name}") from exc


def _skill_title_and_description(skill_id: str, text: str) -> tuple[str, str]:
    title = skill_id
    description = ""
    lines = text.splitlines()
    body_start = 0
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                body_start = index + 1
                break
            if line.lower().startswith("name:") and title == skill_id:
                title = _clean_extracted_value(line.split(":", 1)[1])
            if line.lower().startswith("description:") and not description:
                description = _clean_extracted_value(line.split(":", 1)[1])

    for line in lines[body_start:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            title = stripped.removeprefix("# ").strip() or title
            continue
        if stripped.startswith(">") and not description:
            description = stripped.lstrip(">").strip()
            continue
        if not description and not stripped.startswith("#"):
            description = stripped[:240]
        if title and description:
            break
    return title, description


def _assigned_employees_for_skill(skill_id: str) -> list[str]:
    assigned: list[str] = []
    for profile in _load_employees():
        employee = _employee_summary(profile)
        if skill_id in employee.skills:
            assigned.append(employee.id)
    return sorted(assigned)


def _skill_summary(skill_path: Path) -> ChatSkillSummary:
    skill_id = skill_path.parent.name
    text = _read_skill_text(skill_path)
    title, description = _skill_title_and_description(skill_id, text)
    resources = [
        str(path.relative_to(skill_path.parent))
        for path in sorted(skill_path.parent.rglob("*"))
        if path.is_file() and path.name != "SKILL.md"
    ]
    return ChatSkillSummary(
        id=skill_id,
        title=title,
        description=description,
        content=text,
        assigned_employees=_assigned_employees_for_skill(skill_id),
        resources=resources,
        saved_path=str(skill_path.relative_to(_workspace_root())),
    )


def _seed_skill_summary(skill: ValidationSkillDefinition) -> ChatSkillSummary:
    return ChatSkillSummary(
        id=skill.id,
        title=skill.title,
        description=skill.description,
        content=skill.content,
        assigned_employees=_assigned_employees_for_skill(skill.id),
        resources=[],
        saved_path=skill.source_ref,
        source="builtin",
    )


def _load_skills() -> list[ChatSkillSummary]:
    skills_dir = _skills_dir()
    local_skills = [] if not skills_dir.exists() else [
        _skill_summary(path)
        for path in sorted(skills_dir.glob("*/SKILL.md"))
    ]
    local_ids = {skill.id for skill in local_skills}
    seeded_skills = [
        _seed_skill_summary(skill)
        for skill in VALIDATION_SKILL_DEFINITIONS
        if skill.id not in local_ids
    ]
    return [*local_skills, *seeded_skills]


def _find_skill(skill_id_or_name: str) -> ChatSkillSummary | None:
    lookup = skill_id_or_name.strip().lower()
    if not lookup:
        return None
    for skill in _load_skills():
        if lookup in {skill.id.lower(), skill.title.lower()}:
            return skill
    slug = _slugify_skill_id(skill_id_or_name)
    path = _skill_file_path(slug)
    return _skill_summary(path) if path.exists() else None


def _chat_kernel_command_intercept_enabled(context: ChatRunContext) -> bool:
    return _chat_kernel_command_intercept_enabled_data(
        mode=os.environ.get("AITEAMOS_CHAT_KERNEL_COMMANDS", "fallback"),
        selected_ai_engine=context.selected_ai_engine,
        is_remote_kernel_action=_is_remote_kernel_action_request(context.request.message),
    )


def _employee_skill_context(employee: ChatEmployeeSummary) -> str:
    if not employee.skills:
        return "- none"
    skills_by_id = {skill.id: skill for skill in _load_skills()}
    lines: list[str] = []
    for skill_id in employee.skills:
        skill = skills_by_id.get(skill_id)
        if skill is None:
            lines.append(f"- {skill_id}: assigned in profile, but no local SKILL.md was found.")
            continue
        description = f" - {skill.description}" if skill.description else ""
        resources = f"; resources={', '.join(skill.resources[:5])}" if skill.resources else ""
        excerpt = _trim_context_text(skill.content, limit=900)
        lines.append(
            f"- {skill.title} ({skill.id}){description}; path={skill.saved_path}{resources}\n"
            f"  Skill excerpt: {excerpt}"
        )
    return "\n".join(lines)


def _employee_capability_context(employee_profile: dict[str, Any]) -> str:
    raw_permissions = [
        str(permission).strip()
        for permission in employee_profile.get("permissions", [])
        if str(permission).strip()
    ]
    expanded_permissions = sorted(expand_employee_permissions(raw_permissions))
    allowed: list[str] = []
    blocked: list[str] = []
    for command_id, spec in _KERNEL_COMMAND_SPECS.items():
        command = KernelCommand(id=command_id, capability=spec.capability, operation=spec.operation)
        decision = evaluate_kernel_policy(command, spec=spec, actor_permissions=raw_permissions)
        risk = f"; risk={spec.risk}" if spec.risk != "low" else ""
        label = f"{command_id} ({spec.description}{risk})"
        if decision.status == "allowed":
            allowed.append(label)
        else:
            missing = ", ".join(decision.missing_permissions) if decision.missing_permissions else "unknown"
            blocked.append(f"{command_id} (missing={missing})")

    return (
        f"Raw profile permissions: {', '.join(raw_permissions) if raw_permissions else 'none'}\n"
        f"Expanded Kernel permissions: {', '.join(expanded_permissions) if expanded_permissions else 'none'}\n"
        "Allowed Kernel capabilities and commands:\n"
        f"{_format_context_list(allowed)}\n"
        "Blocked Kernel commands:\n"
        f"{_format_context_list(blocked)}"
    )


def _employee_agent_context_bundle(
    *,
    employee_profile: dict[str, Any],
    employee: ChatEmployeeSummary,
    ticket_keys: list[str],
    memory_snippets: list[str],
) -> str:
    memory_scopes = employee_profile.get("memory_scopes", [])
    ticket_text = ", ".join(ticket_keys) if ticket_keys else "none"
    memory_text = _format_context_list(memory_snippets)
    memory_scope_text = ", ".join(str(item) for item in memory_scopes) if memory_scopes else "none"
    skill_context = _employee_skill_context(employee)
    capability_context = _employee_capability_context(employee_profile)
    return _build_employee_agent_context_bundle(
        memory_scope_text=memory_scope_text,
        ticket_text=ticket_text,
        skill_context=skill_context,
        memory_text=memory_text,
        capability_context=capability_context,
    )


def _ai_engine_context_gate(
    *,
    employee_profile: dict[str, Any],
    employee: ChatEmployeeSummary,
    user_message: str,
    ticket_keys: list[str],
    skills: list[str],
    memory_snippets: list[str],
) -> str:
    responsibilities = employee_profile.get("responsibilities", [])
    handoff_rules = employee_profile.get("handoff_rules", [])
    personality = str(employee_profile.get("personality", ""))
    skill_text = ", ".join(skills) if skills else "none"
    responsibilities_text = _format_context_list(responsibilities)
    handoff_text = _format_context_list(handoff_rules)
    agent_bundle = _employee_agent_context_bundle(
        employee_profile=employee_profile,
        employee=employee,
        ticket_keys=ticket_keys,
        memory_snippets=memory_snippets,
    )

    return _build_ai_engine_context_gate(
        employee_id=employee.id,
        display_name=employee.display_name,
        role=employee.role,
        summary=employee.summary,
        personality=personality,
        responsibilities_text=responsibilities_text,
        skill_text=skill_text,
        agent_bundle=agent_bundle,
        handoff_text=handoff_text,
        user_message=user_message,
    )


def _chat_completion_history(messages: list[ConversationMessage]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in messages:
        if message.role not in {"user", "assistant"}:
            continue
        content = message.content.strip()
        if not content:
            continue
        history.append({"role": message.role, "content": content})
    return history


async def _call_openai_agent(
    *,
    ai_engine_id: str,
    employee_profile: dict[str, Any],
    employee: ChatEmployeeSummary,
    message: str,
    ticket_keys: list[str],
    skills: list[str],
    memory_snippets: list[str],
    engine_state: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    runtime = _ai_engine_runtime()
    api_key = runtime.secrets.get("openai_api_key", "")
    if not runtime.openai_enabled(ai_engine_id) or not api_key:
        raise RuntimeError("OpenAI AI Engine is not enabled")
    model = runtime.openai_model()
    reasoning_effort = runtime.openai_reasoning_effort()

    request_body: dict[str, Any] = {
        "model": model,
        "instructions": _ai_engine_context_gate(
            employee_profile=employee_profile,
            employee=employee,
            user_message=message,
            ticket_keys=ticket_keys,
            skills=skills,
            memory_snippets=memory_snippets,
        ),
        "input": [{"role": "user", "content": message}],
        "store": True,
        "max_output_tokens": runtime.openai_max_output_tokens(),
        "reasoning": {"effort": reasoning_effort},
    }
    service_tier = runtime.openai_service_tier()
    if service_tier:
        request_body["service_tier"] = service_tier
    previous_response_id = engine_state.get("openai_previous_response_id")
    if isinstance(previous_response_id, str) and previous_response_id:
        request_body["previous_response_id"] = previous_response_id

    payload = await _call_openai_responses(
        async_client_factory=httpx.AsyncClient,
        base_url=runtime.openai_base_url(),
        api_key=api_key,
        request_body=request_body,
    )
    reply = _extract_openai_text(payload)
    if not reply:
        raise HTTPException(status_code=502, detail="OpenAI AI Engine returned no text output")

    response_id = payload.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise HTTPException(status_code=502, detail="OpenAI AI Engine returned no response id")

    next_state = {
        **engine_state,
        "ai_engine": "openai_responses",
        "engine_thread_id": engine_state.get("engine_thread_id")
        or f"openai-{employee.id}-{uuid4().hex[:8]}",
        "openai_previous_response_id": response_id,
        "model": payload.get("model") or model,
        "last_response_id": response_id,
        "updated_at": _now(),
    }
    metadata = {
        "ai_engine": "openai_responses",
        "model": next_state["model"],
        "reasoning_effort": reasoning_effort,
        "speed": runtime.openai_speed(),
        "service_tier": service_tier or payload.get("service_tier"),
        "response_id": response_id,
        "previous_response_id": previous_response_id,
        "usage": payload.get("usage"),
    }
    return reply, next_state, metadata


async def _call_deepseek_agent(
    *,
    ai_engine_id: str,
    employee_profile: dict[str, Any],
    employee: ChatEmployeeSummary,
    message: str,
    ticket_keys: list[str],
    skills: list[str],
    memory_snippets: list[str],
    recent_messages: list[ConversationMessage],
    engine_state: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    runtime = _ai_engine_runtime()
    api_key = runtime.secrets.get("deepseek_api_key", "")
    if not runtime.deepseek_enabled(ai_engine_id) or not api_key:
        raise RuntimeError("DeepSeek AI Engine is not enabled")
    model = runtime.deepseek_model()
    thinking = runtime.deepseek_thinking_type()

    request_body: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": _ai_engine_context_gate(
                    employee_profile=employee_profile,
                    employee=employee,
                    user_message=message,
                    ticket_keys=ticket_keys,
                    skills=skills,
                    memory_snippets=memory_snippets,
                ),
            },
            *_chat_completion_history(recent_messages),
            {"role": "user", "content": message},
        ],
        "stream": False,
        "max_tokens": runtime.deepseek_max_tokens(),
        "thinking": {"type": thinking},
    }

    payload = await _call_deepseek_chat_completion(
        async_client_factory=httpx.AsyncClient,
        base_url=runtime.deepseek_base_url(),
        api_key=api_key,
        request_body=request_body,
    )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HTTPException(status_code=502, detail="DeepSeek AI Engine returned no choices")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    finish_reason = choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None
    message_payload = choice.get("message") if isinstance(choice, dict) else None
    reply = message_payload.get("content") if isinstance(message_payload, dict) else None
    if not isinstance(reply, str) or not reply.strip():
        raise HTTPException(status_code=502, detail="DeepSeek AI Engine returned no text output")

    response_id = payload.get("id")
    if not isinstance(response_id, str) or not response_id:
        response_id = f"deepseek-{uuid4().hex[:12]}"

    next_state = {
        **engine_state,
        "ai_engine": "deepseek_chat_completions",
        "engine_thread_id": engine_state.get("engine_thread_id")
        or f"deepseek-{employee.id}-{uuid4().hex[:8]}",
        "assumed_agent_session": True,
        "deepseek_last_response_id": response_id,
        "model": payload.get("model") or model,
        "updated_at": _now(),
    }
    metadata = {
        "ai_engine": "deepseek_chat_completions",
        "model": next_state["model"],
        "response_id": response_id,
        "assumed_agent_session": True,
        "usage": payload.get("usage"),
        "finish_reason": finish_reason,
        "thinking": thinking,
        "context_window": runtime.deepseek_context_window(),
        "max_tokens": runtime.deepseek_max_tokens(),
    }
    return reply.strip(), next_state, metadata


async def _stream_deepseek_agent(
    context: ChatRunContext,
) -> AsyncIterator[tuple[str, str | dict[str, Any]]]:
    runtime = _ai_engine_runtime()
    api_key = runtime.secrets.get("deepseek_api_key", "")
    if not runtime.deepseek_enabled(context.selected_ai_engine) or not api_key:
        raise RuntimeError("DeepSeek AI Engine is not enabled")
    model = runtime.deepseek_model()
    thinking = runtime.deepseek_thinking_type()

    request_body: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": _ai_engine_context_gate(
                    employee_profile=context.selected_profile,
                    employee=context.employee,
                    user_message=context.request.message,
                    ticket_keys=context.ticket_keys,
                    skills=context.skills,
                    memory_snippets=context.memories,
                ),
            },
            *_chat_completion_history(context.recent_messages),
            {"role": "user", "content": context.request.message},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": runtime.deepseek_max_tokens(),
        "thinking": {"type": thinking},
    }

    response_id = f"deepseek-{uuid4().hex[:12]}"
    usage: Any = None
    finish_reason: str | None = None
    reply_parts: list[str] = []

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            f"{runtime.deepseek_base_url()}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        ) as response:
            if response.status_code >= 400:
                error_text = await response.aread()
                raise HTTPException(
                    status_code=502,
                    detail=f"DeepSeek AI Engine failed: {response.status_code} {error_text.decode('utf-8')[:500]}",
                )

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if isinstance(payload.get("id"), str):
                    response_id = payload["id"]
                if isinstance(payload.get("model"), str):
                    model = payload["model"]
                if payload.get("usage"):
                    usage = payload["usage"]

                choices = payload.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0] if isinstance(choices[0], dict) else {}
                reason = choice.get("finish_reason")
                if isinstance(reason, str):
                    finish_reason = reason
                delta = choice.get("delta") if isinstance(choice, dict) else None
                text = delta.get("content") if isinstance(delta, dict) else None
                if isinstance(text, str) and text:
                    reply_parts.append(text)
                    yield "delta", text

    reply = "".join(reply_parts).strip()
    if not reply:
        raise HTTPException(status_code=502, detail="DeepSeek AI Engine returned no text output")

    engine_state = {
        **context.engine_state,
        "ai_engine": "deepseek_chat_completions",
        "engine_thread_id": context.engine_state.get("engine_thread_id")
        or f"deepseek-{context.employee.id}-{uuid4().hex[:8]}",
        "assumed_agent_session": True,
        "deepseek_last_response_id": response_id,
        "model": model,
        "updated_at": _now(),
    }
    metadata = {
        "ai_engine": "deepseek_chat_completions",
        "model": model,
        "response_id": response_id,
        "assumed_agent_session": True,
        "usage": usage,
        "finish_reason": finish_reason,
        "thinking": thinking,
        "context_window": runtime.deepseek_context_window(),
        "max_tokens": runtime.deepseek_max_tokens(),
        "native_stream": True,
    }
    final_response = _persist_chat_response(
        context,
        reply=reply,
        engine_state=engine_state,
        engine_thread_id=str(engine_state["engine_thread_id"]),
        extra_trace_events=[
            ChatTraceEvent(
                event="ai_engine.deepseek.stream_completed",
                detail="Generated streaming response through DeepSeek Chat Completions API.",
                data=metadata,
            )
        ],
    )
    yield "final", final_response.model_dump()


def _ai_engine_event_metadata(trace_events: list[ChatTraceEvent]) -> dict[str, Any]:
    return _ai_engine_event_metadata_data(trace_events)


def _selected_ai_engine_model(engine: str) -> str | None:
    config = _ai_engine_config()
    if engine == "deepseek":
        return str(config["deepseek_model"])
    if engine == "openai":
        return str(config["openai_model"])
    return None


def _build_run_metadata(
    context: ChatRunContext,
    *,
    final_engine_thread_id: str,
    trace_events: list[ChatTraceEvent],
    trace_path: Path,
) -> dict[str, Any]:
    selected_ai_engine = context.selected_ai_engine
    return _build_run_metadata_data(
        run_id=context.run_id,
        thread_id=context.thread_id,
        employee_id=context.employee.id,
        employee_display_name=context.employee.display_name,
        employee_role=context.employee.role,
        employee_default_ai_engine=context.employee.default_ai_engine,
        ticket_keys=context.ticket_keys,
        memory_refs=context.memory_refs,
        selected_ai_engine=selected_ai_engine,
        selected_model=_selected_ai_engine_model(selected_ai_engine),
        engine_state=context.engine_state,
        final_engine_thread_id=final_engine_thread_id,
        trace_events=trace_events,
        trace_relative_path=str(trace_path.relative_to(_workspace_root())),
        created_at=_now(),
    )


def _build_reply(
    *,
    employee: ChatEmployeeSummary,
    message: str,
    ticket_keys: list[str],
    engine_thread_id: str,
    skills: list[str],
    memory_snippets: list[str],
) -> str:
    return _build_stub_reply(
        employee_display_name=employee.display_name,
        employee_role=employee.role,
        employee_ai_engine_mode=employee.ai_engine_mode,
        employee_default_ai_engine=employee.default_ai_engine,
        message_prefers_chinese=_message_prefers_chinese(message),
        ticket_keys=ticket_keys,
        engine_thread_id=engine_thread_id,
        skills=skills,
        memory_snippets=memory_snippets,
    )


def _recalled_memory_ref(result: Any) -> dict[str, Any]:
    provenance = result.provenance if isinstance(result.provenance, dict) else {}
    memory_id = str(provenance.get("asset_id") or result.id)
    ref: dict[str, Any] = {
        "memory_id": memory_id,
        "source": result.source,
        "source_kind": result.source_kind,
        "source_ref": result.source_ref,
        "scope": {"kind": result.scope_kind, "ref": result.scope_ref},
        "memory_type": result.memory_type,
        "employee_ids": list(result.employee_ids),
        "tags": list(result.tags),
    }
    if provenance:
        ref["provenance"] = dict(provenance)
    if result.graphiti_episode_id:
        ref["graphiti_episode_id"] = result.graphiti_episode_id
    return ref


def _memory_snippet_from_result(result: Any) -> str:
    return (
        f"[memory:{result.id}] {result.content} "
        f"(scope={result.scope_kind}:{result.scope_ref}; source={result.source_kind}:{result.source_ref})"
    )


def _merge_recalled_memory_result(context: ChatRunContext, result: Any) -> bool:
    ref = _recalled_memory_ref(result)
    for existing_ref in context.memory_refs:
        if existing_ref.get("memory_id") != ref.get("memory_id"):
            continue
        if ref.get("graphiti_episode_id") and not existing_ref.get("graphiti_episode_id"):
            existing_ref["graphiti_episode_id"] = ref["graphiti_episode_id"]
        if result.source == "graphiti":
            existing_ref["graphiti_recalled"] = True
            existing_ref["graphiti_result_id"] = result.id
        if ref.get("provenance") and not existing_ref.get("provenance"):
            existing_ref["provenance"] = ref["provenance"]
        return False
    key = json.dumps(ref, ensure_ascii=False, sort_keys=True, default=str)
    existing = {
        json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        for item in context.memory_refs
    }
    if key in existing:
        return False
    snippet = _memory_snippet_from_result(result)
    if snippet not in context.memories:
        context.memories.append(snippet)
    context.memory_refs.append(ref)
    return True


def _update_context_loaded_memory_counts(context: ChatRunContext) -> None:
    memory_count = len([item for item in context.memories if item.startswith("[memory:")])
    for event in context.trace_events:
        if event.event != "context.loaded":
            continue
        event.data["memory_count"] = memory_count
        event.data["memory_and_knowledge_count"] = len(context.memories)
        event.data["recalled_memory_refs"] = context.memory_refs
        return


async def _enrich_chat_context_with_graphiti_recall(context: ChatRunContext) -> None:
    response = await search_memory(
        query=context.request.message,
        employee_id=context.employee.id,
        ticket_key=context.ticket_keys[0] if context.ticket_keys else None,
        limit=5,
        include_graphiti=True,
    )
    graphiti_results = [result for result in response.results if result.source == "graphiti"]
    added = 0
    for result in graphiti_results:
        if _merge_recalled_memory_result(context, result):
            added += 1
    if not graphiti_results:
        return

    _update_context_loaded_memory_counts(context)
    trace_path = context.run_dirs["traces"] / f"{context.run_id}.jsonl"
    context.trace_events.append(
        ChatTraceEvent(
            event="memory.recall.completed",
            detail="Recalled approved durable Memory through Graphiti for this Chat run.",
            data={
                "query": context.request.message,
                "employee_id": context.employee.id,
                "ticket_keys": context.ticket_keys,
                "scopes": [
                    {"kind": ref.get("scope", {}).get("kind"), "ref": ref.get("scope", {}).get("ref")}
                    for ref in context.memory_refs
                    if isinstance(ref.get("scope"), dict)
                ],
                "source_trace": str(trace_path.relative_to(_workspace_root())),
                "graphiti_result_count": len(graphiti_results),
                "added_result_count": added,
                "recalled_memory_refs": context.memory_refs,
                "graphiti_recalled_memory_refs": [_recalled_memory_ref(result) for result in graphiti_results],
                "backend": response.backend.model_dump(mode="json"),
            },
        )
    )


def _latest_ticket_report_refs(trace_events: list[ChatTraceEvent]) -> dict[str, str]:
    for event in reversed(trace_events):
        ticket_payload = event.data.get("ticket") if isinstance(event.data.get("ticket"), dict) else None
        if ticket_payload is None:
            continue
        reports = ticket_payload.get("reports")
        if not isinstance(reports, list) or not reports:
            continue
        report = reports[-1] if isinstance(reports[-1], dict) else {}
        evidence = report.get("evidence")
        evidence_id = ""
        if isinstance(evidence, list) and evidence:
            evidence_id = str(evidence[0])
        return {
            "source_report_id": str(report.get("id") or ""),
            "evidence_id": evidence_id,
        }
    return {"source_report_id": "", "evidence_id": ""}


def _latest_chat_action_plan(trace_events: list[ChatTraceEvent]) -> dict[str, Any]:
    for event in reversed(trace_events):
        if event.event == "chat.action_plan.completed":
            return dict(event.data)
        plan = event.data.get("plan")
        if isinstance(plan, dict):
            action_plan = plan.get("chat_action_plan")
            if isinstance(action_plan, dict):
                return dict(action_plan)
    return {}


def _memory_candidate_run_ref(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "asset_id": candidate.id,
        "asset_type": f"memory:{candidate.memory_type}",
        "asset_status": candidate.status,
        "source_kind": candidate.source_kind,
        "source_ref": candidate.source_ref,
        "scope": {"kind": candidate.scope_kind, "ref": candidate.scope_ref},
        "confidence": candidate.confidence,
        "provenance": dict(candidate.provenance),
    }


def _learning_summary_from_candidate(candidate: Any) -> dict[str, Any]:
    provenance = candidate.provenance if isinstance(candidate.provenance, dict) else {}
    hints = provenance.get("future_recall_query_hints")
    return {
        "learned_facts": [candidate.content],
        "avoided_pitfalls": [],
        "reusable_decisions": [],
        "suggested_skill_doc_updates": [],
        "future_recall_query_hints": hints if isinstance(hints, list) else [],
        "candidate_id": candidate.id,
        "source_ticket_id": provenance.get("source_ticket_id", ""),
    }


def _learning_summary_from_run(
    context: ChatRunContext,
    *,
    memory_usage_refs: list[dict[str, Any]],
    memory_candidate: Any | None = None,
) -> dict[str, Any]:
    usage_by_memory_id = {
        str(ref.get("memory_id") or ref.get("asset_id")): ref
        for ref in memory_usage_refs
        if ref.get("memory_id") or ref.get("asset_id")
    }
    recalled_assets: list[dict[str, Any]] = []
    seen_memory_ids: set[str] = set()
    for ref in context.memory_refs:
        memory_id = str(ref.get("memory_id") or "")
        if not memory_id or memory_id in seen_memory_ids:
            continue
        seen_memory_ids.add(memory_id)
        usage_ref = usage_by_memory_id.get(memory_id, {})
        recalled_assets.append(
            {
                "memory_id": memory_id,
                "asset_id": memory_id,
                "source": ref.get("source", ""),
                "scope": ref.get("scope", {}),
                "graphiti_recalled": bool(ref.get("graphiti_recalled") or usage_ref.get("graphiti_recalled")),
                "graphiti_episode_id": ref.get("graphiti_episode_id") or usage_ref.get("graphiti_episode_id") or "",
                "usage_id": usage_ref.get("usage_id", ""),
                "usefulness_status": usage_ref.get("usefulness_status", "unreviewed") if usage_ref else "",
            }
        )

    candidate_summary = _learning_summary_from_candidate(memory_candidate) if memory_candidate is not None else {}
    if not recalled_assets and not candidate_summary:
        return {}

    future_hints = candidate_summary.get("future_recall_query_hints")
    if not isinstance(future_hints, list):
        future_hints = []
    future_hints = sorted({str(item) for item in [*future_hints, *context.ticket_keys] if str(item).strip()})
    next_round_guidance: list[str] = []
    if recalled_assets:
        next_round_guidance.append("Review whether each recalled approved Memory was useful before the next similar Ticket.")
        next_round_guidance.append("Prefer approved Memories already marked useful for future Ticket context.")
    if memory_candidate is not None:
        next_round_guidance.append("Review the proposed Memory candidate and approve it only if its provenance is sufficient.")
    source_ticket_id = (
        str(candidate_summary.get("source_ticket_id") or "")
        or (context.ticket_keys[0] if context.ticket_keys else "")
    )
    candidate_refs = [_memory_candidate_run_ref(memory_candidate)] if memory_candidate is not None else []
    if recalled_assets and memory_candidate is not None:
        clara_summary = (
            f"本轮 AITeamOS 复用了 {len(recalled_assets)} 条 approved Memory，并提出 1 条新的 Memory candidate；"
            "下一轮应复查 recall usefulness，并优先使用已证明有用的经验。"
        )
    elif recalled_assets:
        clara_summary = (
            f"本轮 AITeamOS 复用了 {len(recalled_assets)} 条 approved Memory；"
            "下一轮应让 Clara/PV 标记这些 recall 是否 useful。"
        )
    else:
        clara_summary = "本轮 AITeamOS 提出 1 条 Memory candidate；审核通过后可在类似 Ticket 中召回。"

    return {
        "learned_facts": candidate_summary.get("learned_facts", []),
        "avoided_pitfalls": candidate_summary.get("avoided_pitfalls", []),
        "reusable_decisions": candidate_summary.get("reusable_decisions", []),
        "suggested_skill_doc_updates": candidate_summary.get("suggested_skill_doc_updates", []),
        "future_recall_query_hints": future_hints,
        "candidate_id": candidate_summary.get("candidate_id", ""),
        "memory_candidate_refs": candidate_refs,
        "source_ticket_id": source_ticket_id,
        "recalled_assets": recalled_assets,
        "used_approved_asset_count": len(recalled_assets),
        "new_candidate_count": 1 if memory_candidate is not None else 0,
        "memory_usage_refs": memory_usage_refs,
        "next_round_guidance": next_round_guidance,
        "clara_summary": clara_summary,
    }


def _prepare_chat_run(request: ChatMessageRequest) -> ChatRunContext:
    profiles = _load_employees()
    selected = _select_employee(
        profiles,
        requested_employee_id=request.target_employee_id,
        message=request.message,
    )
    employee = _employee_summary(selected)
    selected_ai_engine = _ai_engine_runtime().selected_engine_for_employee(employee.default_ai_engine)

    thread_id = request.thread_id or _employee_default_thread_id(employee.id)
    thread_id = _require_safe_id(thread_id, field="thread_id")
    run_id = f"run-{uuid4().hex[:12]}"
    ticket_keys = _extract_ticket_keys(request.message, request.ticket_key)
    run_dirs = _ensure_run_dirs()
    recent_messages = _load_conversation_messages(thread_id, limit=12)
    engine_state = _engine_thread_state(_workspace_dir(), employee.id, thread_id)
    engine_thread_id = str(engine_state.get("engine_thread_id") or _engine_thread_id(_workspace_dir(), employee.id, thread_id))
    skills = _skill_titles(employee.skills)
    recalled_memory_records = recall_memory_records(
        employee_id=employee.id,
        query=request.message,
        ticket_keys=ticket_keys,
    )
    recalled_memories = [_memory_snippet_from_result(result) for result in recalled_memory_records]
    memory_refs = [_recalled_memory_ref(result) for result in recalled_memory_records]
    memories = list(recalled_memories)
    recalled_knowledge: list[str] = []
    for snippet in knowledge_snippets(request.message, limit=3):
        if snippet.startswith("[memory:"):
            continue
        if snippet not in memories:
            memories.append(snippet)
            recalled_knowledge.append(snippet)

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
                "skills": skills,
                "memory_count": len(recalled_memories),
                "knowledge_count": len(recalled_knowledge),
                "memory_and_knowledge_count": len(memories),
                "recalled_memory_refs": memory_refs,
                "recent_message_count": len(recent_messages),
                "command_intercept_policy": os.environ.get("AITEAMOS_CHAT_KERNEL_COMMANDS", "fallback"),
            },
        ),
        ChatTraceEvent(
            event="engine_thread.resolved",
            detail="Resolved stable external AI Engine thread mapping.",
            data={
                "ai_engine": engine_state.get("ai_engine", "file_stub"),
                "engine_thread_id": engine_thread_id,
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
        engine_state=engine_state,
        engine_thread_id=engine_thread_id,
        skills=skills,
        memories=memories,
        memory_refs=memory_refs,
        recent_messages=recent_messages,
        trace_events=trace_events,
    )


def _persist_chat_response(
    context: ChatRunContext,
    *,
    reply: str,
    engine_state: dict[str, Any] | None = None,
    engine_thread_id: str | None = None,
    extra_trace_events: list[ChatTraceEvent] | None = None,
) -> ChatMessageResponse:
    if engine_state is not None:
        _save_engine_thread_state(_workspace_dir(), context.employee.id, context.thread_id, engine_state)
    final_engine_thread_id = engine_thread_id or context.engine_thread_id

    trace_events = [
        *context.trace_events,
        *(extra_trace_events or []),
        ChatTraceEvent(event="response.created", detail="Assistant response was created."),
    ]

    conversation_path = context.run_dirs["conversations"] / f"{context.thread_id}.jsonl"
    trace_path = context.run_dirs["traces"] / f"{context.run_id}.jsonl"
    memory_usage_refs: list[dict[str, Any]] = []
    try:
        memory_usage_refs = record_memory_recall_usage(
            memory_refs=context.memory_refs,
            run_id=context.run_id,
            employee_id=context.employee.id,
            ticket_keys=context.ticket_keys,
            query=context.request.message,
            trace_path=str(trace_path.relative_to(_workspace_root())),
        )
        if memory_usage_refs:
            trace_events.append(
                ChatTraceEvent(
                    event="memory.recall.usage_recorded",
                    detail="Recorded learning-effectiveness usage refs for recalled approved Memory assets.",
                    data={
                        "usage_refs": memory_usage_refs,
                        "usage_count": len(memory_usage_refs),
                        "ticket_keys": context.ticket_keys,
                        "employee_id": context.employee.id,
                    },
                )
            )
    except Exception as exc:
        trace_events.append(
            ChatTraceEvent(
                event="memory.recall.usage_failed",
                detail="Memory recall usage recording failed; chat response was still persisted.",
                data={"error": str(exc)[:300]},
            )
        )
    run_metadata = _build_run_metadata(
        context,
        final_engine_thread_id=final_engine_thread_id,
        trace_events=trace_events,
        trace_path=trace_path,
    )
    if memory_usage_refs:
        run_metadata["memory_usage_refs"] = memory_usage_refs
        run_metadata["learning_effectiveness"] = {
            "recalled_asset_count": len(memory_usage_refs),
            "usefulness_status": "unreviewed",
            "usage_refs": memory_usage_refs,
            "source": "memory_recall_usage",
        }
        run_metadata["learning_summary"] = _learning_summary_from_run(
            context,
            memory_usage_refs=memory_usage_refs,
        )
    trace_events.append(
        ChatTraceEvent(
            event="run.metadata.recorded",
            detail="Captured AI Engine, ticket, and tool metadata for this run.",
            data=run_metadata,
        )
    )

    user_timestamp = _now()
    assistant_timestamp = _now()
    _append_jsonl(conversation_path, {
        "timestamp": user_timestamp,
        "role": "user",
        "content": context.request.message,
        "employee_id": None,
        "run_id": context.run_id,
        "metadata": {
            "aiteamos": {
                "message_kind": "user_request",
                "run_id": context.run_id,
                "thread_id": context.thread_id,
                "target_employee_id": context.employee.id,
                "ticket_keys": context.ticket_keys,
                "ai_engine": {
                    "selected_ai_engine": context.selected_ai_engine,
                    "employee_default_ai_engine": context.employee.default_ai_engine,
                },
            }
        },
    })
    _append_jsonl(conversation_path, {
        "timestamp": assistant_timestamp,
        "role": "assistant",
        "content": reply,
        "employee_id": context.employee.id,
        "run_id": context.run_id,
        "metadata": {
            "aiteamos": {
                "message_kind": "assistant_response",
                **run_metadata,
            }
        },
    })
    thread_summary = _record_chat_thread_turn(context, last_message_at=assistant_timestamp)

    memory_candidate = None
    try:
        ticket_report_refs = _latest_ticket_report_refs(trace_events)
        memory_candidate = propose_memory_from_chat_turn(
            run_id=context.run_id,
            thread_id=context.thread_id,
            employee_id=context.employee.id,
            employee_display_name=context.employee.display_name,
            user_message=context.request.message,
            assistant_reply=reply,
            ticket_keys=context.ticket_keys,
            trace_path=str(trace_path.relative_to(_workspace_root())),
            provider_refs=run_metadata.get("provider_refs") if isinstance(run_metadata.get("provider_refs"), list) else [],
            graphiti_episode_refs=run_metadata.get("graphiti_episode_refs") if isinstance(run_metadata.get("graphiti_episode_refs"), list) else [],
            source_report_id=ticket_report_refs["source_report_id"],
            evidence_id=ticket_report_refs["evidence_id"],
            recalled_memory_refs=context.memory_refs,
            action_plan=_latest_chat_action_plan(trace_events),
        )
        if memory_candidate is not None:
            run_metadata["memory_candidate_refs"] = [_memory_candidate_run_ref(memory_candidate)]
            run_metadata["learning_summary"] = _learning_summary_from_run(
                context,
                memory_usage_refs=memory_usage_refs,
                memory_candidate=memory_candidate,
            )
            for event in trace_events:
                if event.event == "run.metadata.recorded":
                    event.data = run_metadata
                    break
            trace_events.append(
                ChatTraceEvent(
                    event="memory.candidate.proposed",
                    detail="Proposed a ticket-aware memory candidate from this Chat run.",
                    data={
                        "candidate_id": memory_candidate.id,
                        "scope": f"{memory_candidate.scope_kind}:{memory_candidate.scope_ref}",
                        "confidence": memory_candidate.confidence,
                        "source_kind": memory_candidate.source_kind,
                        "source_ref": memory_candidate.source_ref,
                        "provenance": memory_candidate.provenance,
                    },
                )
            )
    except Exception as exc:
        trace_events.append(
            ChatTraceEvent(
                event="memory.candidate.failed",
                detail="Memory candidate extraction failed; chat response was still persisted.",
                data={"error": str(exc)[:300]},
            )
        )

    if run_metadata.get("learning_summary"):
        trace_events.append(
            ChatTraceEvent(
                event="learning.summary.recorded",
                detail="Recorded Clara learning summary for recalled assets and proposed candidates.",
                data=run_metadata["learning_summary"],
            )
        )

    for event in trace_events:
        _append_jsonl(trace_path, {
            "timestamp": _now(),
            "run_id": context.run_id,
            **event.model_dump(),
        })

    trace_events.append(ChatTraceEvent(event="trace.persisted", detail="Conversation and trace were saved."))

    return ChatMessageResponse(
        thread_id=context.thread_id,
        run_id=context.run_id,
        target_employee=context.employee,
        engine_thread_id=final_engine_thread_id,
        ticket_keys=context.ticket_keys,
        reply=reply,
        trace_events=trace_events,
        run_metadata=run_metadata,
        saved_paths={
            "conversation": str(conversation_path.relative_to(_workspace_root())),
            "trace": str(trace_path.relative_to(_workspace_root())),
            "threads": _thread_index_saved_path(),
            "thread": thread_summary.saved_path,
            "engine_threads": str((_workspace_dir() / "engine_threads.json").relative_to(_workspace_root())),
            **(
                {"memory_candidate": f".aiteamos/memory/candidates.json#{memory_candidate.id}"}
                if memory_candidate is not None
                else {}
            ),
        },
    )


def _stub_reply(context: ChatRunContext) -> str:
    return _build_reply(
        employee=context.employee,
        message=context.request.message,
        ticket_keys=context.ticket_keys,
        engine_thread_id=context.engine_thread_id,
        skills=context.skills,
        memory_snippets=context.memories,
    )


def _kernel_command_from_plan(context: ChatRunContext, plan: ChatKernelCommandPlan) -> KernelCommand | None:
    return _kernel_command_from_plan_data(plan, ticket_keys=context.ticket_keys)


def _persist_kernel_policy_blocked(
    context: ChatRunContext,
    *,
    command: KernelCommand,
    policy: Any,
) -> ChatMessageResponse:
    result = _kernel_policy_blocked_result(command, policy)
    return _persist_chat_response(
        context,
        reply=_kernel_policy_blocked_reply(command, policy),
        extra_trace_events=[
            ChatTraceEvent(
                event="command.called",
                detail=f"Resolved {command.id} through Kernel command executor.",
                data={
                    "requested_by": context.employee.id,
                    "command": result["command"],
                    "kernel_policy": result["kernel_policy"],
                },
            ),
            ChatTraceEvent(
                event="command.blocked",
                detail=result["detail"],
                data=result,
            ),
        ],
    )


def _complete_list_skills_command(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None = None,
) -> ChatMessageResponse:
    result = _list_skills_tool_result()
    result["plan"] = _plan_trace_data(plan)
    return _persist_kernel_command_response(
        context,
        handler_name="list_skills",
        reply=_build_list_skills_reply(result),
        result=result,
        completed=True,
    )


def _complete_list_employees_command(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None = None,
) -> ChatMessageResponse:
    result = _list_employees_tool_result()
    result["plan"] = _plan_trace_data(plan)
    return _persist_kernel_command_response(
        context,
        handler_name="list_employees",
        reply=_build_list_employees_reply(result),
        result=result,
        completed=True,
    )


def _permissions_target_profile(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None,
) -> dict[str, Any]:
    target = _tool_str_arg(plan, "target_employee_id", "employee_id", "id", "target_employee_name", "employee_name", "name")
    if target:
        found = _find_employee_profile(target)
        if found is not None:
            return _normalize_employee_profile(found[1], found[0])

    message = context.request.message.lower()
    for profile in _load_employees():
        employee = _employee_summary(profile)
        if re.search(rf"\b{re.escape(employee.id.lower())}\b", message) or employee.display_name.lower() in message:
            return profile
    return context.selected_profile


def _complete_inspect_permissions_command(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None = None,
) -> ChatMessageResponse:
    profile = _permissions_target_profile(context, plan)
    employee = _employee_summary(profile)
    raw_permissions = [str(permission) for permission in profile.get("permissions", []) if str(permission).strip()]
    expanded_permissions = sorted(expand_employee_permissions(raw_permissions))
    command_rows = _command_access_rows(raw_permissions)
    result = {
        "status": "completed",
        "detail": f"Inspected Kernel permissions for employee: {employee.id}",
        "employee": employee.model_dump(),
        "raw_permissions": raw_permissions,
        "expanded_permissions": expanded_permissions,
        "commands": command_rows,
        "plan": _plan_trace_data(plan),
    }
    return _persist_kernel_command_response(
        context,
        handler_name="inspect_permissions",
        reply=_build_permissions_reply(
            employee_display_name=employee.display_name,
            employee_id=employee.id,
            employee_role=employee.role,
            raw_permissions=raw_permissions,
            expanded_permissions=expanded_permissions,
            commands=command_rows,
            prefers_chinese=_message_prefers_chinese(context.request.message),
        ),
        result=result,
        completed=True,
    )


def _terminal_cwd_from_plan(context: ChatRunContext, plan: ChatKernelCommandPlan | None) -> tuple[Path | None, str | None]:
    raw_cwd = _tool_str_arg(plan, "cwd", "workdir")
    return _terminal_cwd_from_raw(raw_cwd, _workspace_root())


def _terminal_command_line_from_plan(context: ChatRunContext, plan: ChatKernelCommandPlan | None) -> str | None:
    return _tool_str_arg(plan, "command", "cmd", "command_line") or _extract_terminal_command_line(context.request.message)


def _terminal_ticket_id_from_context(context: ChatRunContext, plan: ChatKernelCommandPlan | None) -> str | None:
    return _extract_ticket_id(context.request.message, plan) or (context.request.ticket_key.strip() if context.request.ticket_key else None)


def _terminal_blocked_response(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None,
    *,
    reason: str,
    command_line: str | None,
) -> ChatMessageResponse:
    result = {
        "status": "blocked",
        "detail": reason,
        "command_line": command_line or "",
        "plan": _plan_trace_data(plan),
    }
    reply = _build_blocked_command_reply(
        "terminal.run",
        reason,
        "Clara，请为 rd-0001 执行命令 `pytest tests/test_file_chat_routes.py -q`。",
    )
    return _persist_kernel_command_response(
        context,
        handler_name="terminal_run",
        reply=reply,
        result=result,
        completed=False,
    )


def _record_terminal_evidence_report(
    *,
    context: ChatRunContext,
    ticket_id: str,
    command_line: str,
    cwd: Path,
    exit_code: int | None,
    timed_out: bool,
    output: str,
) -> dict[str, Any]:
    item = add_ticket_report(
        ticket_id,
        TicketReportRequest(
            reporter_employee_id=context.employee.id,
            reporter_role=context.employee.role,
            content=_terminal_report_content(
                command_line=command_line,
                cwd=cwd,
                workspace=_workspace_root(),
                exit_code=exit_code,
                timed_out=timed_out,
                output=output,
            ),
            evidence=[_terminal_evidence_ref(context.run_id)],
            report_type="terminal_evidence",
            source_run_id=context.run_id,
        ),
    )
    report = item.reports[-1] if item.reports else None
    return {
        "ticket_id": item.id,
        "ticket_status": item.status,
        "report_id": report.id if report is not None else "",
        "evidence_ref": _terminal_evidence_ref(context.run_id),
        "ticket": item.model_dump(mode="json"),
    }


async def _complete_terminal_run_command(
    context: ChatRunContext,
    plan: ChatKernelCommandPlan | None = None,
) -> ChatMessageResponse:
    command_line = _terminal_command_line_from_plan(context, plan)
    if not command_line:
        return _terminal_blocked_response(context, plan, reason="Missing terminal command.", command_line=None)
    ticket_id = _terminal_ticket_id_from_context(context, plan)
    if not ticket_id:
        return _terminal_blocked_response(
            context,
            plan,
            reason="terminal.run requires a Ticket binding before execution.",
            command_line=command_line,
        )
    try:
        if get_ticket(ticket_id) is None:
            return _terminal_blocked_response(context, plan, reason=f"Ticket not found: {ticket_id}", command_line=command_line)
    except ValueError as exc:
        return _terminal_blocked_response(context, plan, reason=str(exc), command_line=command_line)
    argv, argv_error = _terminal_argv_from_command(command_line)
    if argv_error or argv is None:
        return _terminal_blocked_response(context, plan, reason=argv_error or "Invalid terminal command.", command_line=command_line)
    cwd, cwd_error = _terminal_cwd_from_plan(context, plan)
    if cwd_error or cwd is None:
        return _terminal_blocked_response(context, plan, reason=cwd_error or "Invalid cwd.", command_line=command_line)
    path_error = _validate_terminal_workspace_args(argv, cwd, _workspace_root())
    if path_error:
        return _terminal_blocked_response(context, plan, reason=path_error, command_line=command_line)

    exit_code, output, timed_out = await _run_terminal_command_collect(argv=argv, cwd=cwd)
    report_ref: dict[str, Any] | None = None
    report_error = ""
    try:
        report_ref = _record_terminal_evidence_report(
            context=context,
            ticket_id=ticket_id,
            command_line=command_line,
            cwd=cwd,
            exit_code=exit_code,
            timed_out=timed_out,
            output=output,
        )
    except (KeyError, ValueError) as exc:
        report_error = str(exc)
    result = {
        "status": "blocked" if timed_out or report_error else ("completed" if exit_code == 0 else "failed"),
        "detail": (
            f"Terminal command ran but Ticket evidence write failed: {report_error}"
            if report_error
            else ("Terminal command completed." if exit_code == 0 and not timed_out else "Terminal command did not complete successfully.")
        ),
        "command_line": command_line,
        "argv": argv,
        "cwd": str(cwd.relative_to(_workspace_root())),
        "ticket_id": ticket_id,
        "ticket_evidence": report_ref or {},
        "exit_code": exit_code,
        "timed_out": timed_out,
        "output_preview": output[-8000:],
        "plan": _plan_trace_data(plan),
    }
    reply = _terminal_reply(
        command_line=command_line,
        cwd=cwd,
        workspace=_workspace_root(),
        exit_code=exit_code,
        output=output,
        timed_out=timed_out,
    )
    if report_ref:
        reply += (
            "\n\nTicket evidence:\n"
            f"- Ticket: {report_ref['ticket_id']}\n"
            f"- Report: {report_ref['report_id']}\n"
            f"- Evidence: {report_ref['evidence_ref']}"
        )
    elif report_error:
        reply += f"\n\nTicket evidence write failed: {report_error}"
    return _persist_kernel_command_response(
        context,
        handler_name="terminal_run",
        reply=reply,
        result=result,
        completed=exit_code == 0 and not timed_out and not report_error,
    )


KernelCommandHandler = Callable[[ChatRunContext, ChatKernelCommandPlan | None], ChatMessageResponse]


_KERNEL_COMMAND_HANDLERS: dict[str, KernelCommandHandler] = {
    "employees.manage:list": _complete_list_employees_command,
    "employees.manage:create": _complete_create_employee_tool,
    "employees.manage:update": _complete_edit_employee_profile_tool,
    "employees.manage:delete": _complete_delete_employee_tool,
    "assets.manage:list_skills": _complete_list_skills_command,
    "assets.manage:create_skill": _complete_create_skill_tool,
    "assets.manage:assign_skill": _complete_assign_skill_to_employee_tool,
    "assets.manage:delete_skill": _complete_delete_skill_tool,
    "knowledge.search:search": _complete_search_knowledge_tool,
    "tickets.manage:create": _complete_create_ticket_tool,
    "tickets.manage:list": _complete_list_tickets_tool,
    "tickets.manage:self_bootstrap_summary": _complete_self_bootstrap_summary_tool,
    "tickets.manage:report": _complete_record_ticket_report_tool,
    "tickets.manage:request_validation": _complete_request_ticket_validation_tool,
    "tickets.manage:request_human_review": _complete_request_human_review_tool,
    "repositories.list:list": _complete_list_code_repositories_tool,
    "repositories.inspect:inspect": _complete_inspect_code_repository_tool,
    "kernel.permissions:inspect": _complete_inspect_permissions_command,
}


async def _execute_kernel_command_plan(
    context: ChatRunContext,
    *,
    plan: ChatKernelCommandPlan,
    command: KernelCommand,
    policy: Any,
) -> ChatMessageResponse:
    if policy.status != "allowed":
        return _persist_kernel_policy_blocked(context, command=command, policy=policy)
    if command.id == "terminal.run:run":
        return await _complete_terminal_run_command(context, plan)
    handler = _KERNEL_COMMAND_HANDLERS.get(command.id)
    if handler is None:
        return _persist_kernel_policy_blocked(
            context,
            command=command,
            policy=policy.model_copy(update={"status": "blocked", "reason": "missing_command_handler"}),
        )
    return handler(context, plan)


async def _maybe_execute_kernel_command(context: ChatRunContext) -> ChatMessageResponse | None:
    plan = await _plan_kernel_command_intent(context)
    command = _kernel_command_from_plan(context, plan)
    if command is None:
        return None
    spec = _KERNEL_COMMAND_SPECS[command.id]
    policy = evaluate_kernel_policy(command, spec=spec, actor_permissions=_actor_permissions(context))
    return await _execute_kernel_command_plan(context, plan=plan, command=command, policy=policy)


async def _stream_terminal_run_command(
    context: ChatRunContext,
    *,
    plan: ChatKernelCommandPlan,
) -> AsyncIterator[tuple[str, str | ChatMessageResponse | dict[str, Any]]]:
    command_line = _terminal_command_line_from_plan(context, plan)
    if not command_line:
        yield "final", _terminal_blocked_response(context, plan, reason="Missing terminal command.", command_line=None)
        return
    ticket_id = _terminal_ticket_id_from_context(context, plan)
    if not ticket_id:
        yield "final", _terminal_blocked_response(
            context,
            plan,
            reason="terminal.run requires a Ticket binding before execution.",
            command_line=command_line,
        )
        return
    try:
        if get_ticket(ticket_id) is None:
            yield "final", _terminal_blocked_response(context, plan, reason=f"Ticket not found: {ticket_id}", command_line=command_line)
            return
    except ValueError as exc:
        yield "final", _terminal_blocked_response(context, plan, reason=str(exc), command_line=command_line)
        return
    argv, argv_error = _terminal_argv_from_command(command_line)
    if argv_error or argv is None:
        yield "final", _terminal_blocked_response(context, plan, reason=argv_error or "Invalid terminal command.", command_line=command_line)
        return
    cwd, cwd_error = _terminal_cwd_from_plan(context, plan)
    if cwd_error or cwd is None:
        yield "final", _terminal_blocked_response(context, plan, reason=cwd_error or "Invalid cwd.", command_line=command_line)
        return
    path_error = _validate_terminal_workspace_args(argv, cwd, _workspace_root())
    if path_error:
        yield "final", _terminal_blocked_response(context, plan, reason=path_error, command_line=command_line)
        return

    yield "delta", f"$ {command_line}\n"
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output_parts: list[str] = []
    timed_out = False
    try:
        assert process.stdout is not None
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=120.0)
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            output_parts.append(text)
            if sum(len(part) for part in output_parts) <= 20000:
                yield "delta", text
        await asyncio.wait_for(process.wait(), timeout=5.0)
    except TimeoutError:
        timed_out = True
        process.kill()
        await process.wait()
        yield "delta", "\n[terminal.run timed out]\n"

    output = "".join(output_parts)
    exit_code = None if timed_out else process.returncode
    yield "delta", f"\n[terminal.run exit_code={exit_code if exit_code is not None else '-'}]\n"
    report_ref: dict[str, Any] | None = None
    report_error = ""
    try:
        report_ref = _record_terminal_evidence_report(
            context=context,
            ticket_id=ticket_id,
            command_line=command_line,
            cwd=cwd,
            exit_code=exit_code,
            timed_out=timed_out,
            output=output,
        )
    except (KeyError, ValueError) as exc:
        report_error = str(exc)
    result = {
        "status": "blocked" if timed_out or report_error else ("completed" if exit_code == 0 else "failed"),
        "detail": (
            f"Terminal command ran but Ticket evidence write failed: {report_error}"
            if report_error
            else ("Terminal command completed." if exit_code == 0 and not timed_out else "Terminal command did not complete successfully.")
        ),
        "command_line": command_line,
        "argv": argv,
        "cwd": str(cwd.relative_to(_workspace_root())),
        "ticket_id": ticket_id,
        "ticket_evidence": report_ref or {},
        "exit_code": exit_code,
        "timed_out": timed_out,
        "output_preview": output[-8000:],
        "streamed": True,
        "plan": _plan_trace_data(plan),
    }
    reply = _terminal_reply(
        command_line=command_line,
        cwd=cwd,
        workspace=_workspace_root(),
        exit_code=exit_code,
        output=output,
        timed_out=timed_out,
    )
    if report_ref:
        reply += (
            "\n\nTicket evidence:\n"
            f"- Ticket: {report_ref['ticket_id']}\n"
            f"- Report: {report_ref['report_id']}\n"
            f"- Evidence: {report_ref['evidence_ref']}"
        )
    elif report_error:
        reply += f"\n\nTicket evidence write failed: {report_error}"
    final_response = _persist_kernel_command_response(
        context,
        handler_name="terminal_run",
        reply=reply,
        result=result,
        completed=exit_code == 0 and not timed_out and not report_error,
    )
    yield "final", final_response


@router.get("/employees", response_model=list[ChatEmployeeSummary])
async def list_chat_employees() -> list[ChatEmployeeSummary]:
    return [_employee_summary(profile) for profile in _load_employees()]


@router.put("/employees/{employee_id}/ai-engine", response_model=ChatEmployeeSummary)
async def update_chat_employee_ai_engine(
    employee_id: str,
    request: ChatEmployeeAiEngineUpdateRequest,
) -> ChatEmployeeSummary:
    safe_employee_id = _require_safe_id(employee_id, field="employee_id")
    found = _find_employee_profile(safe_employee_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    profile_path, profile = found
    default_ai_engine = _require_employee_default_ai_engine(request.default_ai_engine)
    ai_engine = profile.get("ai_engine") if isinstance(profile.get("ai_engine"), dict) else {}
    ai_engine = dict(ai_engine)
    ai_engine["default_engine"] = default_ai_engine
    profile["ai_engine"] = ai_engine
    profile["updated_at"] = _now()
    normalized = _normalize_employee_profile(profile, profile_path)
    _write_yaml(profile_path, normalized)
    return _employee_summary(normalized)


@router.get("/skills", response_model=list[ChatSkillSummary])
async def list_chat_skills() -> list[ChatSkillSummary]:
    return sorted(_load_skills(), key=lambda skill: skill.id)


@router.get("/ai-engines", response_model=ChatAiEngineSettings)
async def get_chat_ai_engines() -> ChatAiEngineSettings:
    return _ai_engine_settings_response()


@router.put("/ai-engines", response_model=ChatAiEngineSettings)
async def update_chat_ai_engines(request: ChatAiEngineSettingsRequest) -> ChatAiEngineSettings:
    current = _ai_engine_config()
    engine_configs = dict(current.get("engine_configs") or {})
    engine_configs["deepseek"] = {
        **dict(engine_configs.get("deepseek") or {}),
        "model": request.deepseek_model.strip() or "deepseek-v4-flash",
        "thinking": _normalize_thinking(request.deepseek_thinking),
    }
    engine_configs["openai"] = {
        **dict(engine_configs.get("openai") or {}),
        "model": request.openai_model.strip() or "gpt-5.5",
    }
    ai_engine_config: dict[str, Any] = {
        "active_engine": _normalize_ai_engine(request.active_engine),
        "fallback_on_error": request.fallback_on_error,
        "engine_configs": engine_configs,
    }
    _write_json_file(_ai_engine_settings_path(), _ai_engine_file_payload(ai_engine_config))

    return _ai_engine_settings_response()


@router.put("/ai-engines/{engine_id}", response_model=ChatAiEngineSettings)
async def update_chat_ai_engine(
    engine_id: str,
    request: ChatAiEngineUpdateRequest,
) -> ChatAiEngineSettings:
    engine = _require_ai_engine(engine_id)
    current = _ai_engine_config()
    next_config = dict(current)
    engine_configs = dict(current.get("engine_configs") or {})
    engine_config = dict(engine_configs.get(engine) or {})

    if request.activate:
        next_config["active_engine"] = engine

    if request.model is not None:
        engine_config["model"] = request.model.strip() or str(AI_ENGINE_CATALOG[engine].get("default_model") or "")
    if request.thinking is not None:
        if engine == "deepseek":
            engine_config["thinking"] = _normalize_thinking(request.thinking)
        elif engine == "openai":
            engine_config["thinking"] = _normalize_openai_reasoning_effort(request.thinking)
    if request.speed is not None and engine == "openai":
        engine_config["speed"] = _normalize_openai_speed(request.speed)

    has_token_config = bool(AI_ENGINE_CATALOG[engine].get("default_context_window") or AI_ENGINE_CATALOG[engine].get("default_max_tokens"))
    if request.context_window is not None and has_token_config:
        engine_config["context_window"] = _normalize_int_setting(
            request.context_window,
            default=int(AI_ENGINE_CATALOG[engine].get("default_context_window") or 1_000_000),
            min_value=1024,
            max_value=int(AI_ENGINE_CATALOG[engine].get("default_context_window") or 1_000_000),
        )
    if request.max_tokens is not None and has_token_config:
        context_window = int(engine_config.get("context_window") or AI_ENGINE_CATALOG[engine].get("default_context_window") or 1_000_000)
        engine_config["max_tokens"] = min(
            _normalize_int_setting(
                request.max_tokens,
                default=int(AI_ENGINE_CATALOG[engine].get("default_max_tokens") or 4096),
                min_value=64,
                max_value=int(AI_ENGINE_CATALOG[engine].get("max_output_tokens") or AI_ENGINE_CATALOG[engine].get("default_max_tokens") or 4096),
            ),
            context_window,
        )
    if request.base_url is not None:
        engine_config["base_url"] = request.base_url.strip() or str(AI_ENGINE_CATALOG[engine].get("default_base_url") or "")
    if request.api_key_env is not None:
        engine_config["api_key_env"] = request.api_key_env.strip() or str(AI_ENGINE_CATALOG[engine].get("default_api_key_env") or "")
    if request.enabled is not None:
        engine_config["enabled"] = bool(request.enabled)

    if has_token_config:
        context_window = _normalize_int_setting(
            engine_config.get("context_window"),
            default=int(AI_ENGINE_CATALOG[engine].get("default_context_window") or 1_000_000),
            min_value=1024,
            max_value=int(AI_ENGINE_CATALOG[engine].get("default_context_window") or 1_000_000),
        )
        engine_config["context_window"] = context_window
        engine_config["max_tokens"] = min(
            _normalize_int_setting(
                engine_config.get("max_tokens"),
                default=int(AI_ENGINE_CATALOG[engine].get("default_max_tokens") or 4096),
                min_value=64,
                max_value=int(AI_ENGINE_CATALOG[engine].get("max_output_tokens") or AI_ENGINE_CATALOG[engine].get("default_max_tokens") or 4096),
            ),
            context_window,
        )

    engine_configs[engine] = engine_config
    next_config["engine_configs"] = engine_configs
    if engine == "deepseek":
        next_config["deepseek_model"] = str(engine_config.get("model") or "deepseek-v4-flash")
        next_config["deepseek_thinking"] = _normalize_thinking(str(engine_config.get("thinking") or "enabled"))
    elif engine == "openai":
        next_config["openai_model"] = str(engine_config.get("model") or "gpt-5.5")

    _write_json_file(_ai_engine_settings_path(), _ai_engine_file_payload(next_config))

    return _ai_engine_settings_response()


@router.get("/threads", response_model=ChatThreadListResponse)
async def list_chat_threads(employee_id: str) -> ChatThreadListResponse:
    return _list_employee_threads(employee_id)


@router.post("/threads", response_model=ChatThreadSummary)
async def create_chat_thread(request: ChatThreadCreateRequest) -> ChatThreadSummary:
    employee = _require_employee_summary(request.employee_id)
    thread_id = _require_safe_id(
        f"employee-{_safe_thread_component(employee.id)}-{uuid4().hex[:12]}",
        field="thread_id",
    )
    return _upsert_thread_metadata(
        employee=employee,
        thread_id=thread_id,
        title=request.title or f"New chat with {employee.display_name}",
        set_active=True,
    )


@router.post("/threads/{thread_id}/activate", response_model=ChatThreadSummary)
async def activate_chat_thread(thread_id: str, request: ChatThreadActivateRequest) -> ChatThreadSummary:
    return _activate_thread_metadata(thread_id, request.employee_id)


@router.delete("/threads/{thread_id}")
async def delete_chat_thread(thread_id: str) -> dict[str, Any]:
    thread_id = _require_safe_id(thread_id, field="thread_id")
    summary = _thread_summary(thread_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Thread not found: {thread_id}")

    employee_id = summary.employee_id
    index = _hydrate_thread_index()
    removed = False
    if thread_id in index["threads"]:
        del index["threads"][thread_id]
        removed = True
    # Clear active mapping if this was the active thread
    if index["active_by_employee"].get(employee_id) == thread_id:
        index["active_by_employee"].pop(employee_id, None)
    if removed:
        _write_thread_index(index)

    # Delete conversation file
    conv_path = _conversation_path(thread_id)
    try:
        conv_path.unlink(missing_ok=True)
    except OSError:
        pass

    _delete_thread_engine_state_mappings(_workspace_dir(), employee_id, thread_id)

    return {
        "status": "deleted",
        "thread_id": thread_id,
        "employee_id": employee_id,
    }


@router.get("/threads/{thread_id}", response_model=ConversationResponse)
async def get_chat_thread(thread_id: str) -> ConversationResponse:
    thread_id = _require_safe_id(thread_id, field="thread_id")
    return ConversationResponse(
        thread_id=thread_id,
        messages=_load_conversation_messages(thread_id),
        thread=_thread_summary(thread_id),
    )


async def _run_aiteamos_chat_graph_node(
    state: AiteamosChatGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    text = _latest_human_message_text(list(state.get("messages", [])))
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
    response = await send_chat_message(
        ChatMessageRequest(
            message=text,
            target_employee_id=state.get("target_employee_id"),
            thread_id=thread_id,
            ticket_key=state.get("ticket_key"),
        )
    )
    payload = response.model_dump(mode="json")
    return {
        "messages": [
            AIMessage(
                content=response.reply,
                id=f"{response.run_id}-assistant",
                response_metadata={"aiteamos": payload},
            )
        ],
        "aiteamos_chat_response": payload,
    }


_agui_chat_agent: LangGraphAgent | None = None
_agui_chat_agent_workspace: Path | None = None
_agui_checkpoint_connection: sqlite3.Connection | None = None
_agui_checkpoint_status: dict[str, Any] = {"mode": "uninitialized"}


def _langgraph_checkpoint_path() -> Path:
    return _workspace_dir() / "langgraph" / "checkpoints.sqlite"


def _build_langgraph_checkpointer() -> Any:
    global _agui_checkpoint_connection, _agui_checkpoint_status
    if SqliteSaver is None:
        _agui_checkpoint_status = {
            "mode": "memory_fallback",
            "detail": "langgraph-checkpoint-sqlite is not installed",
        }
        return InMemorySaver()

    path = _langgraph_checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if _agui_checkpoint_connection is not None:
        _agui_checkpoint_connection.close()
    _agui_checkpoint_connection = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(_agui_checkpoint_connection)
    saver.setup()
    _agui_checkpoint_status = {
        "mode": "sqlite",
        "path": str(path.relative_to(_workspace_root())),
    }
    return saver


def _build_agui_chat_agent() -> LangGraphAgent:
    builder = StateGraph(AiteamosChatGraphState)
    builder.add_node("aiteamos_chat", _run_aiteamos_chat_graph_node)
    builder.add_edge(START, "aiteamos_chat")
    builder.add_edge("aiteamos_chat", END)
    graph = builder.compile(checkpointer=_build_langgraph_checkpointer())
    return LangGraphAgent(
        name="AITeamOS Clara",
        description="AG-UI/LangGraph bridge for file-backed AITeamOS Chat.",
        graph=graph,
    )


def _get_agui_chat_agent() -> LangGraphAgent:
    global _agui_chat_agent, _agui_chat_agent_workspace
    workspace = _workspace_root()
    if _agui_chat_agent is None or _agui_chat_agent_workspace != workspace:
        _agui_chat_agent = _build_agui_chat_agent()
        _agui_chat_agent_workspace = workspace
    return _agui_chat_agent


def _enrich_agui_input(input_data: RunAgentInput, request: Request) -> RunAgentInput:
    state = input_data.state if isinstance(input_data.state, dict) else {}
    next_state: dict[str, Any] = dict(state)
    forwarded_props = input_data.forwarded_props if isinstance(input_data.forwarded_props, dict) else {}

    target_employee_id = (
        request.query_params.get("target_employee_id")
        or request.headers.get("X-AITeamOS-Target-Employee-Id")
        or forwarded_props.get("target_employee_id")
    )
    ticket_key = (
        request.query_params.get("ticket_key")
        or request.headers.get("X-AITeamOS-Ticket-Key")
        or forwarded_props.get("ticket_key")
    )

    if target_employee_id:
        next_state["target_employee_id"] = str(target_employee_id)
    if ticket_key:
        next_state["ticket_key"] = str(ticket_key)

    return input_data.model_copy(update={"state": next_state})


@router.post("/agent")
async def stream_agui_chat_agent(input_data: RunAgentInput, request: Request) -> StreamingResponse:
    encoder = EventEncoder(accept=request.headers.get("accept"))
    enriched_input = _enrich_agui_input(input_data, request)

    async def event_generator() -> AsyncIterator[str | bytes]:
        async for event in _stream_agui_chat_events(enriched_input):
            yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())


@router.get("/agent/health")
async def agui_chat_agent_health() -> dict[str, Any]:
    agent = _get_agui_chat_agent()
    return {
        "status": "ok",
        "agent": {"name": agent.name},
        "checkpoint": _agui_checkpoint_status,
    }


@router.post("/messages", response_model=ChatMessageResponse)
async def send_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    context = _prepare_chat_run(request)
    await _enrich_chat_context_with_graphiti_recall(context)
    if _chat_kernel_command_intercept_enabled(context):
        kernel_command_response = await _maybe_execute_kernel_command(context)
        if kernel_command_response is not None:
            return kernel_command_response
    else:
        context.trace_events.append(
            ChatTraceEvent(
                event="command.intercept.skipped",
                detail="Remote AI Engine is available; bundled context was sent to the AI Engine instead of local command interception.",
                data={"selected_ai_engine": context.selected_ai_engine},
            )
        )

    ai_engine_id = context.selected_ai_engine
    if ai_engine_id == "stub":
        return _persist_chat_response(
            context,
            reply=_stub_reply(context),
            extra_trace_events=[ChatTraceEvent(event="ai_engine.stub.completed", detail="Generated explicit file-backed response.")],
        )

    try:
        if ai_engine_id == "deepseek":
            reply, engine_state, ai_engine_metadata = await _call_deepseek_agent(
                ai_engine_id=ai_engine_id,
                employee_profile=context.selected_profile,
                employee=context.employee,
                message=context.request.message,
                ticket_keys=context.ticket_keys,
                skills=context.skills,
                memory_snippets=context.memories,
                recent_messages=context.recent_messages,
                engine_state=context.engine_state,
            )
            completed_event = ChatTraceEvent(
                event="ai_engine.deepseek.completed",
                detail="Generated response through DeepSeek Chat Completions API.",
                data=ai_engine_metadata,
            )
        elif ai_engine_id == "openai":
            reply, engine_state, ai_engine_metadata = await _call_openai_agent(
                ai_engine_id=ai_engine_id,
                employee_profile=context.selected_profile,
                employee=context.employee,
                message=context.request.message,
                ticket_keys=context.ticket_keys,
                skills=context.skills,
                memory_snippets=context.memories,
                engine_state=context.engine_state,
            )
            completed_event = ChatTraceEvent(
                event="ai_engine.openai.completed",
                detail="Generated response through OpenAI Responses API.",
                data=ai_engine_metadata,
            )
        else:
            raise RuntimeError("No remote AI Engine configured")

        return _persist_chat_response(
            context,
            reply=reply,
            engine_state=engine_state,
            engine_thread_id=str(engine_state["engine_thread_id"]),
            extra_trace_events=[completed_event],
        )
    except RuntimeError as exc:
        return _persist_chat_response(
            context,
            reply=_build_ai_engine_configuration_reply(
                user_message=context.request.message,
                ai_engine_id=ai_engine_id,
                error=exc,
            ),
            extra_trace_events=[
                ChatTraceEvent(
                    event="ai_engine.remote.configuration_blocked",
                    detail="Remote AI Engine blocked the chat turn; no file-backed answer was generated.",
                    data={
                        "ai_engine": f"{ai_engine_id}_configuration_blocked",
                        "selected_ai_engine": ai_engine_id,
                        "reason": _safe_ai_engine_error_summary(exc),
                    },
                ),
            ],
        )
    except HTTPException as exc:
        return _persist_chat_response(
            context,
            reply=_build_ai_engine_configuration_reply(
                user_message=context.request.message,
                ai_engine_id=ai_engine_id,
                error=exc,
            ),
            extra_trace_events=[
                ChatTraceEvent(
                    event="ai_engine.remote.configuration_blocked",
                    detail="Remote AI Engine blocked the chat turn; no file-backed answer was generated.",
                    data={
                        "ai_engine": f"{ai_engine_id}_configuration_blocked",
                        "selected_ai_engine": ai_engine_id,
                        "status_code": exc.status_code,
                        "reason": _safe_ai_engine_error_summary(exc),
                    },
                ),
            ],
        )


async def _persist_agui_chat_checkpoint(
    input_data: RunAgentInput,
    *,
    final_response: ChatMessageResponse | None,
    assistant_message_id: str,
    assistant_text: str,
) -> dict[str, Any]:
    if final_response is None:
        return {"status": "skipped", "reason": "no_final_response"}

    user_payload = _latest_agui_user_message_payload(list(input_data.messages or []))
    user_text = _message_content_to_text(user_payload.get("content")) if user_payload else ""
    if not user_text:
        return {"status": "skipped", "reason": "no_user_message"}

    state = _agui_state(input_data)
    values: AiteamosChatGraphState = {
        "messages": [
            HumanMessage(
                content=user_text,
                id=str(user_payload.get("id") or f"{input_data.run_id}-user"),
            ),
            AIMessage(
                content=assistant_text,
                id=assistant_message_id,
                response_metadata={"aiteamos": final_response.model_dump(mode="json")},
            ),
        ],
        "target_employee_id": final_response.target_employee.id,
        "ticket_key": str(state.get("ticket_key")) if state.get("ticket_key") else None,
        "aiteamos_chat_response": final_response.model_dump(mode="json"),
    }
    config: RunnableConfig = {"configurable": {"thread_id": input_data.thread_id}}

    try:
        graph = _get_agui_chat_agent().graph
        next_config = graph.update_state(config, values, as_node="aiteamos_chat")
        snapshot = graph.get_state(next_config)
    except Exception as exc:  # Keep chat usable if checkpoint persistence fails.
        return {
            "status": "error",
            "detail": str(exc),
            "backend": _agui_checkpoint_status,
        }

    return {
        "status": "persisted",
        "thread_id": input_data.thread_id,
        "checkpoint_id": _checkpoint_id_from_config(next_config),
        "next": list(snapshot.next),
        "backend": _agui_checkpoint_status,
    }


def _agui_state(input_data: RunAgentInput) -> dict[str, Any]:
    return dict(input_data.state) if isinstance(input_data.state, dict) else {}


async def _stream_chat_turn(
    request: ChatMessageRequest,
) -> AsyncIterator[tuple[str, str | ChatMessageResponse | dict[str, Any]]]:
    context = _prepare_chat_run(request)
    await _enrich_chat_context_with_graphiti_recall(context)
    command_intercept_enabled = _chat_kernel_command_intercept_enabled(context)
    if command_intercept_enabled and _COMMAND_PLANNING_SIGNAL_RE.search(request.message):
        plan = await _plan_kernel_command_intent(context)
        command = _kernel_command_from_plan(context, plan)
        if command is not None:
            spec = _KERNEL_COMMAND_SPECS[command.id]
            policy = evaluate_kernel_policy(command, spec=spec, actor_permissions=_actor_permissions(context))
            if command.id == "terminal.run:run" and policy.status == "allowed":
                async for event, payload in _stream_terminal_run_command(context, plan=plan):
                    yield event, payload
                return
            response = await _execute_kernel_command_plan(context, plan=plan, command=command, policy=policy)
            yield "final", response
            return
        if context.selected_ai_engine == "deepseek" and _ai_engine_secrets()["deepseek_api_key"]:
            async for event, payload in _stream_deepseek_agent(context):
                yield event, payload
            return
    elif not command_intercept_enabled:
        context.trace_events.append(
            ChatTraceEvent(
                event="command.intercept.skipped",
                detail="Remote AI Engine is available; bundled context was streamed to the AI Engine instead of local command interception.",
                data={"selected_ai_engine": context.selected_ai_engine},
            )
        )

    if context.selected_ai_engine == "deepseek" and _ai_engine_secrets()["deepseek_api_key"]:
        async for event, payload in _stream_deepseek_agent(context):
            yield event, payload
        return

    yield "final", await send_chat_message(request)


async def _stream_agui_chat_events(input_data: RunAgentInput) -> AsyncIterator[Any]:
    thread_id = input_data.thread_id
    run_id = input_data.run_id
    yield RunStartedEvent(thread_id=thread_id, run_id=run_id, input=input_data)

    user_text = _latest_agui_user_message_text(list(input_data.messages or []))
    assistant_message_id = f"{run_id}-assistant"
    yield TextMessageStartEvent(message_id=assistant_message_id)

    accumulated = ""
    final_response: ChatMessageResponse | None = None
    try:
        if not user_text:
            accumulated = "I did not receive a user message to process."
            yield TextMessageContentEvent(message_id=assistant_message_id, delta=accumulated)
        else:
            state = _agui_state(input_data)
            request = ChatMessageRequest(
                message=user_text,
                target_employee_id=state.get("target_employee_id"),
                thread_id=thread_id,
                ticket_key=state.get("ticket_key"),
            )
            async for event, payload in _stream_chat_turn(request):
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
                for chunk in _reply_chunks(final_response.reply):
                    accumulated += chunk
                    yield TextMessageContentEvent(message_id=assistant_message_id, delta=chunk)
                    await asyncio.sleep(0)

        yield TextMessageEndEvent(message_id=assistant_message_id)
        snapshot = _agui_state(input_data)
        if final_response is not None:
            snapshot["aiteamos_chat_response"] = final_response.model_dump(mode="json")
            snapshot["langgraph_checkpoint"] = await _persist_agui_chat_checkpoint(
                input_data,
                final_response=final_response,
                assistant_message_id=assistant_message_id,
                assistant_text=accumulated,
            )
        yield StateSnapshotEvent(snapshot=snapshot)

        messages = [_agui_message_payload(message) for message in input_data.messages or []]
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


@router.post("/messages/stream")
async def stream_chat_message(request: ChatMessageRequest) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        try:
            context = _prepare_chat_run(request)
            await _enrich_chat_context_with_graphiti_recall(context)
            command_intercept_enabled = _chat_kernel_command_intercept_enabled(context)
            if command_intercept_enabled and _COMMAND_PLANNING_SIGNAL_RE.search(request.message):
                plan = await _plan_kernel_command_intent(context)
                command = _kernel_command_from_plan(context, plan)
                if command is not None:
                    spec = _KERNEL_COMMAND_SPECS[command.id]
                    policy = evaluate_kernel_policy(command, spec=spec, actor_permissions=_actor_permissions(context))
                    yield _sse_payload(
                        "start",
                        {
                            "thread_id": context.thread_id,
                            "run_id": context.run_id,
                            "target_employee": context.employee.model_dump(),
                            "engine_thread_id": context.engine_thread_id,
                            "ticket_keys": context.ticket_keys,
                        },
                    )
                    if command.id == "terminal.run:run" and policy.status == "allowed":
                        async for event, payload in _stream_terminal_run_command(context, plan=plan):
                            if event == "delta":
                                yield _sse_payload("delta", {"text": payload})
                            elif event == "final":
                                final_payload = payload.model_dump() if isinstance(payload, ChatMessageResponse) else payload
                                yield _sse_payload("final", final_payload)
                        return
                    response = await _execute_kernel_command_plan(context, plan=plan, command=command, policy=policy)
                    for chunk in _reply_chunks(response.reply):
                        yield _sse_payload("delta", {"text": chunk})
                        await asyncio.sleep(0)
                    yield _sse_payload("final", response.model_dump())
                    return

                if command is None:
                    if context.selected_ai_engine == "deepseek" and _ai_engine_secrets()["deepseek_api_key"]:
                        yield _sse_payload(
                            "start",
                            {
                                "thread_id": context.thread_id,
                                "run_id": context.run_id,
                                "target_employee": context.employee.model_dump(),
                                "engine_thread_id": context.engine_thread_id,
                                "ticket_keys": context.ticket_keys,
                            },
                        )
                        async for event, payload in _stream_deepseek_agent(context):
                            if event == "delta":
                                yield _sse_payload("delta", {"text": payload})
                            elif event == "final":
                                yield _sse_payload("final", payload)
                        return
            elif not command_intercept_enabled:
                context.trace_events.append(
                    ChatTraceEvent(
                        event="command.intercept.skipped",
                        detail="Remote AI Engine is available; bundled context was streamed to the AI Engine instead of local command interception.",
                        data={"selected_ai_engine": context.selected_ai_engine},
                    )
                )

            if context.selected_ai_engine == "deepseek" and _ai_engine_secrets()["deepseek_api_key"]:
                yield _sse_payload(
                    "start",
                    {
                        "thread_id": context.thread_id,
                        "run_id": context.run_id,
                        "target_employee": context.employee.model_dump(),
                        "engine_thread_id": context.engine_thread_id,
                        "ticket_keys": context.ticket_keys,
                    },
                )
                async for event, payload in _stream_deepseek_agent(context):
                    if event == "delta":
                        yield _sse_payload("delta", {"text": payload})
                    elif event == "final":
                        yield _sse_payload("final", payload)
                return

            response = await send_chat_message(request)
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
            for chunk in _reply_chunks(response.reply):
                yield _sse_payload("delta", {"text": chunk})
                await asyncio.sleep(0)
            yield _sse_payload("final", response.model_dump())
        except HTTPException as exc:
            yield _sse_payload("error", {"status_code": exc.status_code, "detail": exc.detail})
        except Exception as exc:
            yield _sse_payload("error", {"status_code": 500, "detail": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")
