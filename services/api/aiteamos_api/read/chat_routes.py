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
from typing import Annotated, Any, AsyncIterator, TypedDict
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

from .ai_engine_catalog import AI_ENGINE_CATALOG, SUPPORTED_AI_ENGINE_IDS
from .capability_service import local_chat_tool_ids, local_chat_tool_prompt, local_chat_tool_union
from .knowledge_service import knowledge_snippets, search_knowledge_sync
from .memory_service import propose_memory_from_chat_turn, recall_memory_snippets
from .repository_service import CodeRepository, get_code_repository, inspect_code_repository, list_code_repositories
from .ticket_service import (
    TicketCreateRequest,
    TicketReportRequest,
    add_ticket_report,
    create_ticket,
    get_ticket,
    list_tickets,
)

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
_LIST_EMPLOYEES_EN_RE = re.compile(
    r"\b(list|show|display|view)\b.*\b(ai\s+)?employees\b|\bemployees\b.*\b(list|show|all|available)\b"
)
_CREATE_EMPLOYEE_EN_RE = re.compile(r"\b(create|add|new|setup|set up)\b.*\b(employee|profile|user|employee)\b")
_EDIT_EMPLOYEE_EN_RE = re.compile(r"\b(edit|update|modify|change)\b.*\b(employee|profile)\b")
_DELETE_EMPLOYEE_EN_RE = re.compile(r"\b(delete|remove|drop)\b.*\b(employee|profile|user|employee)\b")
_LIST_SKILLS_EN_RE = re.compile(r"\b(list|show|display|view)\b.*\bskills?\b|\bskills?\b.*\b(list|show|all|available)\b")
_CREATE_SKILL_EN_RE = re.compile(r"\b(create|add|new|setup|set up)\b.*\bskill\b")
_ASSIGN_SKILL_EN_RE = re.compile(r"\b(assign|add|give|attach)\b.*\bskill\b.*\b(to|for)\b")
_DELETE_SKILL_EN_RE = re.compile(r"\b(delete|remove|drop)\b.*\bskill\b")
_SEARCH_KNOWLEDGE_EN_RE = re.compile(r"\b(search|find|lookup|read|query)\b.*\b(knowledge|docs?|documents?|memories|decisions)\b")
_CREATE_TICKET_EN_RE = re.compile(r"\b(create|open|plan|delegate|assign)\b.*\bticket\b")
_REPORT_TICKET_EN_RE = re.compile(r"\b(report|record|complete|finish|validate)\b.*\bticket\b")
_LIST_CODE_REPOSITORIES_EN_RE = re.compile(
    r"\b(list|show|display|view)\b.*\b(code\s+)?(repos?|repositories)\b|"
    r"\b(code\s+)?(repos?|repositories)\b.*\b(list|show|all|available)\b"
)
_INSPECT_CODE_REPOSITORY_EN_RE = re.compile(
    r"\b(inspect|search|read|check|review|analy[sz]e|look)\b.*\b(codebase|source|files?|paths?|repos?|repositories|repository)\b|"
    r"\b(codebase|source|files?|paths?|repos?|repositories|repository)\b.*\b(inspect|search|read|check|review|analy[sz]e|look)\b"
)
_FILE_PATH_RE = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:css|html|json|md|py|sh|toml|ts|tsx|txt|yaml|yml)"
)
_TOOL_PLANNING_SIGNAL_RE = re.compile(
    r"create_employee|edit_employee_profile|delete_employee|list_employees|"
    r"list_skills|create_skill|assign_skill_to_employee|delete_skill|"
    r"search_knowledge|create_ticket|record_ticket_report|list_tickets|list_code_repositories|inspect_code_repository|"
    r"创建|新增|添加|新建|补|配置|设置|编辑|修改|更新|调整|改成|改为|删除|移除|删掉|分配|关联|"
    r"列出|列表|清单|有哪些|所有|员工|成员|用户|委派|派给|交给|推进|汇报|验证|完成|"
    r"技能|知识库|文档|决策|记忆|代码仓库|代码库|仓库|工单|任务|\brepos?\b|\brepository\b|\brepositories\b|"
    r"\b(create|add|new|setup|edit|update|modify|change|delete|remove|drop|assign|list|show|employee|employee|profile|user|skills?)\b",
    re.IGNORECASE,
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
    "AI Team OS Manager": ["ticket-specification", "employee-ticket-flow-design", "technical-decision", "validation-strategy"],
    "AI Architect": ["system-architecture-design", "architecture-review", "technical-decision"],
    "AI PV": ["test-engineering", "validation-strategy"],
    "AI Release": ["resource-planning", "validation-strategy"],
    "AI QA / Harness Runner": ["test-engineering", "validation-strategy"],
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
    value: str | bool | None = None
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
    base_url: str | None = None
    api_key_env: str | None = None
    enabled: bool | None = None
    activate: bool = False


class ChatAiEngineSettings(BaseModel):
    active_engine: str = "stub"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: str = "disabled"
    openai_model: str = "gpt-5-nano"
    fallback_on_error: bool = True
    engines: dict[str, ChatAiEngineRecord] = Field(default_factory=dict)
    api_keys_configured: dict[str, bool] = Field(default_factory=dict)
    catalog_order: list[str] = Field(default_factory=list)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class ChatAiEngineSettingsRequest(BaseModel):
    active_engine: str = "stub"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: str = "disabled"
    openai_model: str = "gpt-5-nano"
    fallback_on_error: bool = True


class ChatEmployeeAiEngineUpdateRequest(BaseModel):
    default_ai_engine: str = "system"


class ChatToolPlan(BaseModel):
    tool: str = "none"
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    source: str = "heuristic"


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



def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_ai_engine(value: str | None) -> str:
    engine = (value or "stub").strip().lower()
    return engine if engine in SUPPORTED_AI_ENGINE_IDS else "stub"


def _normalize_employee_default_ai_engine(value: str | None) -> str:
    engine = (value or "system").strip().lower()
    if engine in {"", "active", "default", "global", "settings", "system_default"}:
        return "system"
    if engine in {"fallback", "file_stub", "file-stub"}:
        return "stub"
    return engine if engine in {"system", *SUPPORTED_AI_ENGINE_IDS} else "system"


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


def _normalize_thinking(value: str | None) -> str:
    thinking = (value or "disabled").strip().lower()
    return "enabled" if thinking in {"1", "true", "yes", "on", "enabled"} else "disabled"


def _normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _engine_file_config(engine_id: str, file_config: dict[str, Any]) -> dict[str, Any]:
    engines = file_config.get("engines") if isinstance(file_config.get("engines"), dict) else {}
    engine_config = engines.get(engine_id) if isinstance(engines.get(engine_id), dict) else {}
    return dict(engine_config)


def _engine_config(engine_id: str, file_config: dict[str, Any]) -> dict[str, Any]:
    catalog = AI_ENGINE_CATALOG[engine_id]
    engine_file_config = _engine_file_config(engine_id, file_config)
    model = (
        engine_file_config.get("model")
        or file_config.get(f"{engine_id}_model")
        or os.environ.get(f"AITEAMOS_{engine_id.upper().replace('-', '_')}_MODEL")
        or catalog.get("default_model")
        or ""
    )
    thinking = (
        engine_file_config.get("thinking")
        or file_config.get(f"{engine_id}_thinking")
        or os.environ.get(f"AITEAMOS_{engine_id.upper().replace('-', '_')}_THINKING")
        or catalog.get("default_thinking")
        or ""
    )
    base_url = (
        engine_file_config.get("base_url")
        or file_config.get(f"{engine_id}_base_url")
        or os.environ.get(f"AITEAMOS_{engine_id.upper().replace('-', '_')}_BASE_URL")
        or catalog.get("default_base_url")
        or ""
    )
    api_key_env = (
        engine_file_config.get("api_key_env")
        or file_config.get(f"{engine_id}_api_key_env")
        or catalog.get("default_api_key_env")
        or ""
    )
    return {
        **engine_file_config,
        "model": str(model),
        "thinking": _normalize_thinking(str(thinking)) if engine_id == "deepseek" else str(thinking),
        "base_url": str(base_url),
        "api_key_env": str(api_key_env),
        "enabled": _normalize_bool(engine_file_config.get("enabled"), True),
    }


def _ai_engine_config() -> dict[str, Any]:
    file_config = _read_json_file(_ai_engine_settings_path())
    engine_configs = {
        engine_id: _engine_config(engine_id, file_config)
        for engine_id in AI_ENGINE_CATALOG
    }
    return {
        "active_engine": _normalize_ai_engine(file_config.get("active_engine") or os.environ.get("AITEAMOS_AI_ENGINE")),
        "deepseek_model": str(engine_configs["deepseek"]["model"] or "deepseek-v4-flash"),
        "deepseek_thinking": _normalize_thinking(str(engine_configs["deepseek"]["thinking"] or "disabled")),
        "openai_model": str(engine_configs["openai"]["model"] or "gpt-5-nano"),
        "fallback_on_error": _normalize_bool(
            file_config.get(
                "fallback_on_error",
                os.environ.get("AITEAMOS_AI_ENGINE_FALLBACK_ON_ERROR", "1").lower() in {"1", "true", "yes", "on"},
            ),
            True,
        ),
        "engine_configs": engine_configs,
    }


def _ai_engine_secrets() -> dict[str, str]:
    config = _ai_engine_config()
    engine_configs = config.get("engine_configs") if isinstance(config.get("engine_configs"), dict) else {}

    def env_value(engine_id: str) -> str:
        engine_config = engine_configs.get(engine_id) if isinstance(engine_configs.get(engine_id), dict) else {}
        env_name = str(engine_config.get("api_key_env") or AI_ENGINE_CATALOG[engine_id].get("default_api_key_env") or "")
        return str(os.environ.get(env_name) or "") if env_name else ""

    return {
        "deepseek_api_key": env_value("deepseek"),
        "openai_api_key": env_value("openai"),
    }


def _secret_configured(engine_id: str, engine_config: dict[str, Any]) -> bool:
    api_key_env = str(engine_config.get("api_key_env") or "")
    if not api_key_env:
        return True
    return bool(os.environ.get(api_key_env))


def _field_value(engine_config: dict[str, Any], field_id: str) -> str | bool | None:
    if field_id == "enabled":
        return bool(engine_config.get("enabled", True))
    value = engine_config.get(field_id)
    return str(value) if value is not None else ""


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
        api_key_configured = _secret_configured(engine_id, engine_config)
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
    engine_configs = config.get("engine_configs") if isinstance(config.get("engine_configs"), dict) else {}
    if "deepseek_model" in config or "deepseek_thinking" in config or "openai_model" in config:
        engine_configs = dict(engine_configs)
        engine_configs["deepseek"] = {
            **dict(engine_configs.get("deepseek") or {}),
            "model": str(config.get("deepseek_model") or "deepseek-v4-flash"),
            "thinking": _normalize_thinking(str(config.get("deepseek_thinking") or "disabled")),
        }
        engine_configs["openai"] = {
            **dict(engine_configs.get("openai") or {}),
            "model": str(config.get("openai_model") or "gpt-5-nano"),
        }

    persisted_engines: dict[str, dict[str, Any]] = {}
    for engine_id in AI_ENGINE_CATALOG:
        if engine_id not in SUPPORTED_AI_ENGINE_IDS:
            continue
        engine_config = engine_configs.get(engine_id) if isinstance(engine_configs.get(engine_id), dict) else {}
        persisted: dict[str, Any] = {}
        for key in ("model", "thinking", "base_url", "api_key_env", "enabled", "command", "workspace", "profile"):
            value = engine_config.get(key)
            if value is not None and value != "":
                persisted[key] = value
        if persisted:
            persisted_engines[engine_id] = persisted

    return {
        "active_engine": _normalize_ai_engine(str(config.get("active_engine"))),
        "fallback_on_error": bool(config.get("fallback_on_error", True)),
        "engines": persisted_engines,
        "updated_at": _now(),
    }


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
    return value.strip().strip("\"'`“”‘’").strip()


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
    normalized = re.sub(r"\s+(and|和)\s+", ",", value, flags=re.IGNORECASE)
    normalized = normalized.replace("、", ",").replace("，", ",").replace("；", ",").replace(";", ",")
    return [_clean_extracted_value(item) for item in normalized.split(",") if _clean_extracted_value(item)]


def _stringify_tool_arg(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = _clean_extracted_value(value)
        return cleaned or None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return None


def _listify_tool_arg(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [_clean_extracted_value(str(item)) for item in value if _clean_extracted_value(str(item))]
    if isinstance(value, str):
        return _split_list_value(value)
    return None


def _tool_arg(plan: ChatToolPlan | None, *names: str) -> Any:
    if plan is None:
        return None
    for name in names:
        if name in plan.arguments:
            return plan.arguments[name]
    return None


def _tool_str_arg(plan: ChatToolPlan | None, *names: str) -> str | None:
    return _stringify_tool_arg(_tool_arg(plan, *names))


def _tool_list_arg(plan: ChatToolPlan | None, *names: str) -> list[str] | None:
    return _listify_tool_arg(_tool_arg(plan, *names))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


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


def _normalize_tool_plan(payload: dict[str, Any], *, source: str) -> ChatToolPlan:
    raw_tool = str(payload.get("tool") or "none").strip().lower()
    tool_aliases = {
        "list_employee": "list_employees",
        "list_ai_employees": "list_employees",
        "create_ai_employee": "create_employee",
        "add_employee": "create_employee",
        "new_employee": "create_employee",
        "edit_employee": "edit_employee_profile",
        "update_employee": "edit_employee_profile",
        "update_employee_profile": "edit_employee_profile",
        "remove_employee": "delete_employee",
        "delete_ai_employee": "delete_employee",
        "delete_user": "delete_employee",
        "list_skill": "list_skills",
        "show_skills": "list_skills",
        "create_agent_skill": "create_skill",
        "new_skill": "create_skill",
        "add_skill": "create_skill",
        "assign_skill": "assign_skill_to_employee",
        "attach_skill": "assign_skill_to_employee",
        "add_skill_to_employee": "assign_skill_to_employee",
        "remove_skill": "delete_skill",
        "drop_skill": "delete_skill",
        "query_knowledge": "search_knowledge",
        "read_docs": "search_knowledge",
        "search_docs": "search_knowledge",
        "open_ticket": "create_ticket",
        "add_ticket_report": "record_ticket_report",
        "complete_ticket": "record_ticket_report",
        "list_repositories": "list_code_repositories",
        "list_repos": "list_code_repositories",
        "list_code_repos": "list_code_repositories",
        "show_repositories": "list_code_repositories",
        "show_code_repositories": "list_code_repositories",
        "inspect_repository": "inspect_code_repository",
        "inspect_repo": "inspect_code_repository",
        "search_repository": "inspect_code_repository",
        "search_repo": "inspect_code_repository",
        "read_repository": "inspect_code_repository",
        "read_repo": "inspect_code_repository",
        "read_file": "inspect_code_repository",
        "search_code": "inspect_code_repository",
    }
    tool = tool_aliases.get(raw_tool, raw_tool)
    if tool not in {"none", *local_chat_tool_ids()}:
        tool = "none"

    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    confidence = payload.get("confidence", 0)
    try:
        confidence_value = max(0.0, min(float(confidence), 1.0))
    except (TypeError, ValueError):
        confidence_value = 0.0

    return ChatToolPlan(
        tool=tool,
        arguments=arguments,
        confidence=confidence_value,
        reason=str(payload.get("reason") or ""),
        source=source,
    )


def _should_use_llm_tool_planner(context: ChatRunContext) -> bool:
    if not _TOOL_PLANNING_SIGNAL_RE.search(context.request.message):
        return False
    if context.selected_ai_engine != "deepseek":
        return False
    return bool(_ai_engine_secrets()["deepseek_api_key"])


async def _call_deepseek_tool_planner(context: ChatRunContext) -> ChatToolPlan:
    employees = [_employee_summary(profile).model_dump() for profile in _load_employees()]
    skills = [skill.model_dump() for skill in _load_skills()]
    request_body: dict[str, Any] = {
        "model": _deepseek_model(),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are AITeamOS Clara's local tool planner. "
                    "Classify the user's message into exactly one local tool call. "
                    "Do not answer the user. Return only a JSON object.\n\n"
                    f"Allowed tools:\n{local_chat_tool_prompt()}\n\n"
                    "JSON schema:\n"
                    "{"
                    f"\"tool\":\"{local_chat_tool_union(include_none=True)}\","
                    "\"arguments\":{},"
                    "\"confidence\":0.0,"
                    "\"reason\":\"short reason\""
                    "}\n\n"
                    "Arguments for create_employee: display_name, employee_id, kind, role, summary, responsibility, skills. "
                    "Arguments for edit_employee_profile: target_employee_id or target_employee_name, display_name, role, "
                    "summary, skills, add_skills, ai_engine_mode. "
                    "Arguments for delete_employee: target_employee_id or target_employee_name. "
                    "Arguments for create_skill: skill_id, title, description, body. "
                    "Arguments for assign_skill_to_employee: skill_id or skill_name, target_employee_id or target_employee_name. "
                    "Arguments for delete_skill: skill_id or skill_name. "
                    "Arguments for search_knowledge: query. "
                    "Arguments for create_ticket: title, description, ticket_type, target_employee_id or target_employee_name, "
                    "assigned_role, validation_employee_id, validation_role, code_repository_ids or code_repository_name. "
                    "Arguments for record_ticket_report: ticket_id, reporter_employee_id, reporter_role, content, "
                    "report_type, evidence. "
                    "Arguments for list_code_repositories: none. "
                    "Arguments for inspect_code_repository: ticket_id, code_repository_id or code_repository_name, "
                    "query, file_path or file_paths. "
                    "Map PV, verification, regression, and harness triage roles to role='AI PV'. "
                    "Map release Tickets to role='AI Release'. Map QA or harness runner to role='AI QA / Harness Runner'. "
                    "Use kind='ai' for AI employee/employee requests and kind='human' only for human user/employee requests. "
                    "Choose a tool only when the user intends to inspect or change AITeamOS local employee profiles "
                    "or local SKILL.md assets. Choose search_knowledge when the user asks Clara to read docs, "
                    "memories, decisions, or team knowledge. Choose create_ticket when the user asks Clara "
                    "to delegate or plan a Ticket for a employee role. Choose list_code_repositories when the user asks "
                    "what code repositories, repos, GitHub/Gitea repositories, or local repository paths are configured. "
                    "Choose inspect_code_repository when an RD, PV, QA, Architect, or other non-Clara employee is asked "
                    "to inspect, search, read, review, or analyze configured repository files. "
                    "Choose record_ticket_report when a employee "
                    "or Clara records a result or validation report for an existing ticket."
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
        "thinking": {"type": _deepseek_thinking_type()},
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{_deepseek_base_url()}/chat/completions",
            headers={
                "Authorization": f"Bearer {_ai_engine_secrets()['deepseek_api_key']}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"DeepSeek tool planner failed: {response.status_code} {response.text[:300]}")

    payload = response.json()
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("DeepSeek tool planner returned no choices")
    message_payload = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message_payload.get("content") if isinstance(message_payload, dict) else None
    if not isinstance(content, str):
        raise RuntimeError("DeepSeek tool planner returned no content")
    json_payload = _extract_json_object(content)
    if json_payload is None:
        raise RuntimeError("DeepSeek tool planner returned invalid JSON")
    return _normalize_tool_plan(json_payload, source="deepseek_tool_planner")


def _heuristic_tool_plan(message: str) -> ChatToolPlan:
    if _is_record_ticket_report_request(message):
        return ChatToolPlan(
            tool="record_ticket_report",
            confidence=0.45,
            reason="Matched local ticket report fallback.",
        )
    if _is_list_code_repositories_request(message):
        return ChatToolPlan(
            tool="list_code_repositories",
            confidence=0.45,
            reason="Matched local list-code-repositories fallback.",
        )
    if _is_inspect_code_repository_request(message):
        return ChatToolPlan(
            tool="inspect_code_repository",
            confidence=0.45,
            reason="Matched local inspect-code-repository fallback.",
        )
    if _is_list_tickets_request(message):
        return ChatToolPlan(tool="list_tickets", confidence=0.45, reason="Matched local list-tickets fallback.")
    if _is_create_ticket_request(message):
        return ChatToolPlan(tool="create_ticket", confidence=0.45, reason="Matched local create-ticket fallback.")
    if _is_search_knowledge_request(message):
        return ChatToolPlan(tool="search_knowledge", confidence=0.45, reason="Matched local search-knowledge fallback.")
    if _is_create_skill_request(message):
        return ChatToolPlan(tool="create_skill", confidence=0.45, reason="Matched local create-skill fallback.")
    if _is_assign_skill_request(message):
        return ChatToolPlan(
            tool="assign_skill_to_employee",
            confidence=0.45,
            reason="Matched local assign-skill fallback.",
        )
    if _is_delete_skill_request(message):
        return ChatToolPlan(tool="delete_skill", confidence=0.45, reason="Matched local delete-skill fallback.")
    if _is_list_skills_request(message):
        return ChatToolPlan(tool="list_skills", confidence=0.45, reason="Matched local list-skills fallback.")
    if _is_create_employee_request(message):
        return ChatToolPlan(tool="create_employee", confidence=0.45, reason="Matched local create-employee fallback.")
    if _is_delete_employee_request(message):
        return ChatToolPlan(tool="delete_employee", confidence=0.45, reason="Matched local delete-employee fallback.")
    if _is_edit_employee_profile_request(message):
        return ChatToolPlan(
            tool="edit_employee_profile",
            confidence=0.45,
            reason="Matched local edit-employee fallback.",
        )
    if _is_list_employees_request(message):
        return ChatToolPlan(tool="list_employees", confidence=0.45, reason="Matched local list-employees fallback.")
    return ChatToolPlan(tool="none", confidence=0, reason="No local tool fallback matched.")


async def _plan_local_tool_intent(context: ChatRunContext) -> ChatToolPlan:
    if _should_use_llm_tool_planner(context):
        try:
            plan = await _call_deepseek_tool_planner(context)
            context.trace_events.append(
                ChatTraceEvent(
                    event="tool.intent_planner.completed",
                    detail="Planned local tool intent through DeepSeek.",
                    data=plan.model_dump(),
                )
            )
            if plan.tool != "none" and plan.confidence >= 0.5:
                return plan
        except Exception as exc:
            context.trace_events.append(
                ChatTraceEvent(
                    event="tool.intent_planner.failed",
                    detail="LLM tool planner failed; falling back to local heuristics.",
                    data={"source": "deepseek_tool_planner", "error": str(exc)[:300]},
                )
            )

    plan = _heuristic_tool_plan(context.request.message)
    if plan.tool != "none":
        context.trace_events.append(
            ChatTraceEvent(
                event="tool.intent_planner.fallback",
                detail="Planned local tool intent through local fallback heuristics.",
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
    normalized = message.strip().lower()
    if "list_employees" in normalized:
        return True
    if _LIST_EMPLOYEES_EN_RE.search(normalized):
        return True

    compact = re.sub(r"\s+", "", normalized)
    if not any(token in compact for token in ("成员", "员工", "employee", "employee")):
        return False
    return any(
        token in compact
        for token in (
            "列出",
            "列表",
            "清单",
            "有哪些",
            "所有",
            "全部",
            "团队成员",
            "成员列表",
            "成员清单",
        )
    )


def _is_create_employee_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "create_employee" in normalized:
        return True
    if _CREATE_EMPLOYEE_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    if not any(token in compact for token in ("成员", "员工", "employee", "employee", "用户", "user")):
        return False
    return any(token in compact for token in ("创建", "新增", "添加", "新建"))


def _is_edit_employee_profile_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "edit_employee_profile" in normalized:
        return True
    if _EDIT_EMPLOYEE_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    has_profile_token = any(token in compact for token in ("成员", "员工", "employee", "employee", "profile", "用户", "user"))
    has_field_token = any(token in compact for token in ("summary", "role", "skills", "skill", "技能", "ai_engine", "运行引擎", "名字", "角色", "摘要", "描述"))
    if not has_profile_token and not has_field_token:
        return False
    return any(token in compact for token in ("编辑", "修改", "更新", "调整", "改成", "改为"))


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
    normalized = message.strip().lower()
    if "list_skills" in normalized:
        return True
    if _LIST_SKILLS_EN_RE.search(normalized):
        return True

    compact = re.sub(r"\s+", "", normalized)
    if not any(token in compact for token in ("skill", "skills", "技能")):
        return False
    return any(token in compact for token in ("列出", "列表", "清单", "有哪些", "所有", "全部"))


def _is_create_skill_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "create_skill" in normalized:
        return True
    if _CREATE_SKILL_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    if not any(token in compact for token in ("skill", "skills", "技能")):
        return False
    if any(token in compact for token in ("成员", "员工", "employee", "employee", "用户", "user")):
        return False
    return any(token in compact for token in ("创建", "新增", "新建"))


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
    normalized = message.strip().lower()
    if "search_knowledge" in normalized:
        return True
    if _SEARCH_KNOWLEDGE_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    if not any(token in compact for token in ("知识库", "文档", "docs", "doc", "memory", "memories", "记忆", "decision", "决策")):
        return False
    return any(token in compact for token in ("搜索", "查找", "查询", "读取", "检索", "看看", "相关"))


def _is_create_ticket_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "create_ticket" in normalized:
        return True
    if _CREATE_TICKET_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    if any(token in compact for token in ("ticket", "工单", "本地ticket", "本地任务", "任务")) and any(
        token in compact for token in ("创建", "新增", "打开", "分解", "委派", "分配", "派给", "交给")
    ):
        return True
    return any(token in compact for token in ("委派给", "派给", "交给")) and any(
        token in compact for token in ("alex", "rd", "pv", "architect", "架构", "研发", "验证")
    )


def _is_list_tickets_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "list_tickets" in normalized:
        return True
    compact = re.sub(r"\s+", "", normalized)
    if any(token in compact for token in ("ticket", "tickets", "工单", "本地ticket", "本地任务", "任务")):
        return any(token in compact for token in ("列出", "列表", "清单", "查看", "有哪些", "所有", "list", "show"))
    return False


def _is_record_ticket_report_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "record_ticket_report" in normalized:
        return True
    if not _LOCAL_TICKET_ID_RE.search(message):
        return False
    if _REPORT_TICKET_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    return any(token in compact for token in ("汇报", "报告", "完成", "验证", "记录", "结果"))


def _is_list_code_repositories_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "list_code_repositories" in normalized:
        return True
    if _LIST_CODE_REPOSITORIES_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    has_repo_token = any(token in compact for token in ("代码仓库", "代码库", "仓库")) or bool(
        re.search(r"\b(repos?|repositories|repository)\b", normalized)
    )
    if not has_repo_token:
        return False
    return any(token in compact for token in ("列出", "列表", "清单", "查看", "有哪些", "所有", "全部", "配置", "可用"))


def _is_inspect_code_repository_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "inspect_code_repository" in normalized:
        return True
    if _INSPECT_CODE_REPOSITORY_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    has_repo_token = any(token in compact for token in ("代码仓库", "代码库", "仓库", "代码", "源码", "文件", "实现")) or bool(
        re.search(r"\b(codebase|source|files?|paths?|repos?|repositories|repository)\b", normalized)
    )
    if not has_repo_token and not _LOCAL_TICKET_ID_RE.search(message):
        return False
    return any(
        token in compact
        for token in ("检查", "读取", "搜索", "分析", "查看", "review", "inspect", "search", "read", "check", "analyze", "analyse")
    )


def _is_local_tool_request(message: str) -> bool:
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
        or _is_record_ticket_report_request(message)
        or _is_list_code_repositories_request(message)
        or _is_inspect_code_repository_request(message)
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


def _build_blocked_tool_reply(tool_name: str, reason: str, hint: str) -> str:
    return (
        f"{tool_name} 暂时没有执行。\n\n"
        f"原因：{reason}\n\n"
        f"你可以这样说：{hint}"
    )


def _persist_local_tool_response(
    context: ChatRunContext,
    *,
    tool_name: str,
    reply: str,
    result: dict[str, Any],
    completed: bool,
) -> ChatMessageResponse:
    suffix = "completed" if completed else "blocked"
    return _persist_chat_response(
        context,
        reply=reply,
        extra_trace_events=[
            ChatTraceEvent(
                event=f"tool.{tool_name}.called",
                detail=f"Resolved {tool_name} as a local file-backed tool.",
                data={"requested_by": context.employee.id, "tool": tool_name},
            ),
            ChatTraceEvent(
                event=f"tool.{tool_name}.{suffix}",
                detail=result.get("detail", f"{tool_name} {suffix}."),
                data=result,
            ),
        ],
    )


def _plan_trace_data(plan: ChatToolPlan | None) -> dict[str, Any]:
    return plan.model_dump() if plan is not None else {"source": "unknown"}


def _employee_from_plan_or_name(plan: ChatToolPlan | None, *names: str) -> ChatEmployeeSummary | None:
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


def _extract_ticket_id(message: str, plan: ChatToolPlan | None) -> str | None:
    explicit = _tool_str_arg(plan, "ticket_id", "id")
    if explicit:
        return explicit
    match = _LOCAL_TICKET_ID_RE.search(message)
    return match.group(0) if match else None


def _ticket_title(message: str, plan: ChatToolPlan | None) -> str:
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


def _code_repository_ids_from_plan_or_message(plan: ChatToolPlan | None, message: str) -> list[str]:
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


def _extract_repo_file_paths(message: str, plan: ChatToolPlan | None) -> list[str]:
    values = _tool_list_arg(plan, "file_paths", "paths") or []
    for key in ("file_path", "path"):
        value = _tool_str_arg(plan, key)
        if value:
            values.append(value)
    values.extend(match.group(0) for match in _FILE_PATH_RE.finditer(message))
    return _dedupe([value.strip().lstrip("/") for value in values if value.strip()])


def _resolve_inspection_repository(
    *,
    plan: ChatToolPlan | None,
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


def _inspection_query(context: ChatRunContext, plan: ChatToolPlan | None) -> str:
    return _tool_str_arg(plan, "query", "q", "search") or context.request.message


def _complete_search_knowledge_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
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
    return _persist_local_tool_response(
        context,
        tool_name="search_knowledge",
        reply="\n".join(lines),
        result=result,
        completed=True,
    )


def _complete_list_tickets_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
    items = list_tickets()
    lines = [f"我找到了 {len(items)} 个本地 Tickets。", ""]
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
        "detail": "Listed local Tickets.",
        "tickets": [item.model_dump(mode="json") for item in items],
        "plan": _plan_trace_data(plan),
    }
    return _persist_local_tool_response(
        context,
        tool_name="list_tickets",
        reply="\n".join(lines),
        result=result,
        completed=True,
    )


def _complete_list_code_repositories_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
    tool_result = _list_code_repositories_tool_result()
    result = {
        "status": "completed",
        "detail": "Listed configured code repositories.",
        **tool_result,
        "plan": _plan_trace_data(plan),
    }
    return _persist_local_tool_response(
        context,
        tool_name="list_code_repositories",
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


def _complete_inspect_code_repository_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
    if context.employee.id == CLARA_SYSTEM_EMPLOYEE_ID:
        return _persist_local_tool_response(
            context,
            tool_name="inspect_code_repository",
            reply=_build_blocked_tool_reply(
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
        return _persist_local_tool_response(
            context,
            tool_name="inspect_code_repository",
            reply=_build_blocked_tool_reply(
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
        return _persist_local_tool_response(
            context,
            tool_name="inspect_code_repository",
            reply=_build_blocked_tool_reply(
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
    return _persist_local_tool_response(
        context,
        tool_name="inspect_code_repository",
        reply="\n".join(lines),
        result=result,
        completed=inspection.status == "completed",
    )


def _complete_create_ticket_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
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
        return _persist_local_tool_response(
            context,
            tool_name="create_ticket",
            reply=_build_blocked_tool_reply(
                "create_ticket",
                str(exc),
                "请让 Clara 创建跨域 Ticket，或让对应 role 的 Employee 创建自己的 Ticket namespace。",
            ),
            result={"status": "blocked", "detail": str(exc), "plan": _plan_trace_data(plan)},
            completed=False,
        )

    lines = [
        "已创建本地 Ticket。",
        "",
        f"- ID: {item.id}",
        f"- Title: {item.title}",
        f"- Assigned: {item.assigned_employee_id or item.assigned_role or '-'}",
        f"- Validation: {item.validation_employee_id or item.validation_role or '-'}",
        f"- Knowledge refs: {len(item.knowledge_refs)}",
        f"- Code repositories: {', '.join(item.code_repository_ids) if item.code_repository_ids else '-'}",
        "",
        "下一步：被分派的 Employee 应基于这些 Knowledge refs、自己的 Skills/Memory 和必要的 repo 状态执行；PV 负责验证后写回报告。",
    ]
    result = {
        "status": "completed",
        "detail": "Created a local delegated Ticket.",
        "ticket": item.model_dump(mode="json"),
        "knowledge_results": [entry.model_dump(mode="json") for entry in knowledge.results],
        "plan": _plan_trace_data(plan),
    }
    return _persist_local_tool_response(
        context,
        tool_name="create_ticket",
        reply="\n".join(lines),
        result=result,
        completed=True,
    )


def _complete_record_ticket_report_tool(
    context: ChatRunContext,
    plan: ChatToolPlan | None = None,
) -> ChatMessageResponse:
    ticket_id = _extract_ticket_id(context.request.message, plan)
    if not ticket_id:
        return _persist_local_tool_response(
            context,
            tool_name="record_ticket_report",
            reply=_build_blocked_tool_reply(
                "record_ticket_report",
                "没有识别到 ticket id。",
                "请包含类似 ticket-xxx 的本地 Ticket ID。",
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
        return _persist_local_tool_response(
            context,
            tool_name="record_ticket_report",
            reply=_build_blocked_tool_reply(
                "record_ticket_report",
                f"没有找到 Ticket: {ticket_id}",
                "请先让我列出本地 Tickets，或确认 ID 是否正确。",
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
        "detail": "Recorded a local Ticket report.",
        "ticket": item.model_dump(mode="json"),
        "plan": _plan_trace_data(plan),
    }
    return _persist_local_tool_response(
        context,
        tool_name="record_ticket_report",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_create_employee_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    display_name = _tool_str_arg(plan, "display_name", "name") or _extract_employee_display_name(message)
    if not display_name:
        result = {
            "status": "blocked",
            "reason": "missing_display_name",
            "detail": "Employee display name was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_tool_reply(
            "create_employee",
            "没有识别到成员名字。",
            "Clara，请创建一个 AI PV 成员，名字叫 Victor，负责 regression 和 harness fail triage。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="create_employee",
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
        return _persist_local_tool_response(
            context,
            tool_name="create_employee",
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
    return _persist_local_tool_response(
        context,
        tool_name="create_employee",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_edit_employee_profile_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
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
        reply = _build_blocked_tool_reply(
            "edit_employee_profile",
            "没有识别到要编辑哪个成员。",
            "Clara，请把 Alex 的 summary 改成 Implementation owner for backend API Tickets。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="edit_employee_profile",
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
        return _persist_local_tool_response(
            context,
            tool_name="edit_employee_profile",
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
            return _persist_local_tool_response(
                context,
                tool_name="edit_employee_profile",
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
        reply = _build_blocked_tool_reply(
            "edit_employee_profile",
            "没有识别到可更新字段。",
            "Clara，请把 Alex 的 role 改成 AI RD / Implementer，并添加技能 test-engineering。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="edit_employee_profile",
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
    return _persist_local_tool_response(
        context,
        tool_name="edit_employee_profile",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_delete_employee_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
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
        reply = _build_blocked_tool_reply(
            "delete_employee",
            "没有识别到要删除哪个成员。",
            "Clara，请删除成员 Victor。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="delete_employee",
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
        return _persist_local_tool_response(
            context,
            tool_name="delete_employee",
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
        return _persist_local_tool_response(
            context,
            tool_name="delete_employee",
            reply=reply,
            result=result,
            completed=False,
        )

    relative_profile_path = str(profile_path.relative_to(_workspace_root()))
    try:
        profile_path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot delete employee profile: {employee.id}") from exc
    removed_engine_thread_keys = _delete_engine_thread_states(employee.id)
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
    return _persist_local_tool_response(
        context,
        tool_name="delete_employee",
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


def _complete_create_skill_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
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
        reply = _build_blocked_tool_reply(
            "create_skill",
            "没有识别到 Skill 名称。",
            "Clara，请创建一个 Skill，名字叫 nightly-regression-log-triage，用于分析 nightly regression log。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="create_skill",
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
        return _persist_local_tool_response(
            context,
            tool_name="create_skill",
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
    return _persist_local_tool_response(
        context,
        tool_name="create_skill",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_assign_skill_to_employee_tool(
    context: ChatRunContext,
    plan: ChatToolPlan | None = None,
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
        reply = _build_blocked_tool_reply(
            "assign_skill_to_employee",
            "没有识别到要分配哪个 Skill。",
            "Clara，请把 test-engineering 分配给 Alex。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="assign_skill_to_employee",
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
        reply = _build_blocked_tool_reply(
            "assign_skill_to_employee",
            "没有识别到要分配给哪个成员。",
            "Clara，请把 test-engineering 分配给 Alex。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="assign_skill_to_employee",
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
        return _persist_local_tool_response(
            context,
            tool_name="assign_skill_to_employee",
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
        return _persist_local_tool_response(
            context,
            tool_name="assign_skill_to_employee",
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
    return _persist_local_tool_response(
        context,
        tool_name="assign_skill_to_employee",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_delete_skill_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
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
        reply = _build_blocked_tool_reply(
            "delete_skill",
            "没有识别到要删除哪个 Skill。",
            "Clara，请删除 Skill nightly-regression-log-triage。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="delete_skill",
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
        return _persist_local_tool_response(
            context,
            tool_name="delete_skill",
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
    return _persist_local_tool_response(
        context,
        tool_name="delete_skill",
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


def _extract_ticket_keys(message: str, explicit: str | None) -> list[str]:
    keys: list[str] = []
    if explicit:
        keys.append(explicit.strip().upper())
    keys.extend(match.upper() for match in _TICKET_KEY_RE.findall(message))
    return sorted(set(filter(None, keys)))


def _ensure_run_dirs() -> dict[str, Path]:
    base = _workspace_dir()
    paths = {
        "conversations": base / "conversations",
        "traces": base / "traces",
        "threads": base / "threads",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _threads_dir() -> Path:
    return _workspace_dir() / "threads"


def _thread_index_path() -> Path:
    return _threads_dir() / "index.json"


def _conversation_path(thread_id: str) -> Path:
    thread_id = _require_safe_id(thread_id, field="thread_id")
    return _workspace_dir() / "conversations" / f"{thread_id}.jsonl"


def _load_conversation_messages(thread_id: str, *, limit: int | None = None) -> list[ConversationMessage]:
    path = _conversation_path(thread_id)
    messages: list[ConversationMessage] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            messages.append(ConversationMessage.model_validate_json(line))
    return messages[-limit:] if limit and limit > 0 else messages


def _load_thread_index() -> dict[str, Any]:
    path = _thread_index_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    threads = payload.get("threads") if isinstance(payload.get("threads"), dict) else {}
    active_by_employee = (
        payload.get("active_by_employee")
        if isinstance(payload.get("active_by_employee"), dict)
        else {}
    )
    return {
        "threads": {str(key): value for key, value in threads.items() if isinstance(value, dict)},
        "active_by_employee": {
            str(key): str(value)
            for key, value in active_by_employee.items()
            if isinstance(value, str)
        },
    }


def _write_thread_index(index: dict[str, Any]) -> None:
    payload = {
        "threads": index.get("threads") if isinstance(index.get("threads"), dict) else {},
        "active_by_employee": (
            index.get("active_by_employee")
            if isinstance(index.get("active_by_employee"), dict)
            else {}
        ),
        "updated_at": _now(),
    }
    _write_json_file(_thread_index_path(), payload)


def _thread_index_saved_path() -> str:
    return str(_thread_index_path().relative_to(_workspace_root()))


def _conversation_saved_path(thread_id: str) -> str:
    return str(_conversation_path(thread_id).relative_to(_workspace_root()))


def _thread_title_from_message(content: str) -> str:
    text = re.sub(r"\s+", " ", content).strip()
    if not text:
        return "New thread"
    return text[:56] + ("..." if len(text) > 56 else "")


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


def _engine_thread_id(employee_id: str, thread_id: str) -> str:
    path = _workspace_dir() / "engine_threads.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        mapping = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        mapping = {}

    key = f"{employee_id}::{thread_id}"
    if key not in mapping:
        mapping[key] = f"engine-{employee_id}-{thread_id[:8]}"
        path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return str(mapping[key])


def _load_engine_threads() -> tuple[Path, dict[str, Any]]:
    path = _workspace_dir() / "engine_threads.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mapping = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        mapping = {}
    return path, mapping if isinstance(mapping, dict) else {}


def _engine_thread_state(employee_id: str, thread_id: str) -> dict[str, Any]:
    path, mapping = _load_engine_threads()
    key = f"{employee_id}::{thread_id}"
    existing = mapping.get(key)
    if isinstance(existing, dict):
        return existing
    if isinstance(existing, str):
        return {"ai_engine": "file_stub", "engine_thread_id": existing}

    state = {
        "ai_engine": "file_stub",
        "engine_thread_id": f"engine-{employee_id}-{thread_id[:8]}",
    }
    mapping[key] = state["engine_thread_id"]
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return state


def _save_engine_thread_state(employee_id: str, thread_id: str, state: dict[str, Any]) -> None:
    path, mapping = _load_engine_threads()
    mapping[f"{employee_id}::{thread_id}"] = state
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")


def _delete_engine_thread_states(employee_id: str) -> list[str]:
    path, mapping = _load_engine_threads()
    removed_keys = [key for key in mapping if key.startswith(f"{employee_id}::")]
    if removed_keys:
        for key in removed_keys:
            mapping.pop(key, None)
        path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return removed_keys


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


def _load_skills() -> list[ChatSkillSummary]:
    skills_dir = _skills_dir()
    if not skills_dir.exists():
        return []
    return [
        _skill_summary(path)
        for path in sorted(skills_dir.glob("*/SKILL.md"))
    ]


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


def _openai_enabled(engine: str | None = None) -> bool:
    return (engine or _active_ai_engine()) == "openai"


def _active_ai_engine() -> str:
    return str(_ai_engine_config()["active_engine"])


def _selected_ai_engine_for_employee(employee: ChatEmployeeSummary) -> str:
    default_engine = _normalize_employee_default_ai_engine(employee.default_ai_engine)
    return _active_ai_engine() if default_engine == "system" else default_engine


def _openai_model() -> str:
    return str(_ai_engine_config()["openai_model"])


def _openai_base_url() -> str:
    config = _ai_engine_config()
    engine_configs = config.get("engine_configs") if isinstance(config.get("engine_configs"), dict) else {}
    openai_config = engine_configs.get("openai") if isinstance(engine_configs.get("openai"), dict) else {}
    return str(openai_config.get("base_url") or "https://api.openai.com/v1").rstrip("/")


def _openai_max_output_tokens() -> int:
    raw_value = os.environ.get("AITEAMOS_OPENAI_MAX_OUTPUT_TOKENS", "700")
    try:
        return max(64, min(int(raw_value), 4096))
    except ValueError:
        return 700


def _openai_fallback_on_error() -> bool:
    return _ai_engine_fallback_on_error()


def _deepseek_enabled(engine: str | None = None) -> bool:
    return (engine or _active_ai_engine()) == "deepseek"


def _deepseek_model() -> str:
    return str(_ai_engine_config()["deepseek_model"])


def _deepseek_base_url() -> str:
    config = _ai_engine_config()
    engine_configs = config.get("engine_configs") if isinstance(config.get("engine_configs"), dict) else {}
    deepseek_config = engine_configs.get("deepseek") if isinstance(engine_configs.get("deepseek"), dict) else {}
    return str(deepseek_config.get("base_url") or "https://api.deepseek.com").rstrip("/")


def _deepseek_max_tokens() -> int:
    raw_value = os.environ.get("AITEAMOS_DEEPSEEK_MAX_TOKENS", "700")
    try:
        return max(64, min(int(raw_value), 4096))
    except ValueError:
        return 700


def _deepseek_thinking_type() -> str:
    return str(_ai_engine_config()["deepseek_thinking"])


def _ai_engine_fallback_on_error() -> bool:
    return bool(_ai_engine_config()["fallback_on_error"])


def _ai_engine_context_gate(
    *,
    employee_profile: dict[str, Any],
    employee: ChatEmployeeSummary,
    ticket_keys: list[str],
    skills: list[str],
    memory_snippets: list[str],
) -> str:
    responsibilities = employee_profile.get("responsibilities", [])
    handoff_rules = employee_profile.get("handoff_rules", [])
    personality = str(employee_profile.get("personality", ""))
    ticket_text = ", ".join(ticket_keys) if ticket_keys else "none"
    memory_text = "\n".join(f"- {item}" for item in memory_snippets) or "- none"
    skill_text = ", ".join(skills) if skills else "none"
    responsibilities_text = "\n".join(f"- {item}" for item in responsibilities) or "- none"
    handoff_text = "\n".join(f"- {item}" for item in handoff_rules) or "- none"

    return (
        "You are an AI Employee inside AITeamOS. Answer as the addressed employee, "
        "not as a generic assistant. Be concise, truthful, and explicit about what "
        "you can and cannot do in this P0 AI Engine setup.\n\n"
        f"Employee id: {employee.id}\n"
        f"Display name: {employee.display_name}\n"
        f"Role: {employee.role}\n"
        f"Summary: {employee.summary}\n"
        f"Personality: {personality}\n"
        f"Responsibilities:\n{responsibilities_text}\n\n"
        f"Skills available through AITeamOS context gate: {skill_text}\n"
        f"Ticket keys bound to this turn: {ticket_text}\n"
        f"Local memory snippets:\n{memory_text}\n\n"
        f"Handoff rules:\n{handoff_text}\n\n"
        "AITeamOS currently gates your profile, skills, memory, Ticket context, "
        "permissions, and trace capture before sending this turn to the AI Engine. "
        "Do not claim that Ticket, Harness, repository edits, or external tools were "
        "actually invoked unless the user provided evidence in this conversation."
    )


def _extract_openai_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    for output in payload.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks).strip()


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
    api_key = _ai_engine_secrets()["openai_api_key"]
    if not _openai_enabled(ai_engine_id) or not api_key:
        raise RuntimeError("OpenAI AI Engine is not enabled")

    request_body: dict[str, Any] = {
        "model": _openai_model(),
        "instructions": _ai_engine_context_gate(
            employee_profile=employee_profile,
            employee=employee,
            ticket_keys=ticket_keys,
            skills=skills,
            memory_snippets=memory_snippets,
        ),
        "input": [{"role": "user", "content": message}],
        "store": True,
        "max_output_tokens": _openai_max_output_tokens(),
    }
    previous_response_id = engine_state.get("openai_previous_response_id")
    if isinstance(previous_response_id, str) and previous_response_id:
        request_body["previous_response_id"] = previous_response_id

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{_openai_base_url()}/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI AI Engine failed: {response.status_code} {response.text[:500]}",
        )

    payload = response.json()
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
        "model": payload.get("model") or _openai_model(),
        "last_response_id": response_id,
        "updated_at": _now(),
    }
    metadata = {
        "ai_engine": "openai_responses",
        "model": next_state["model"],
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
    api_key = _ai_engine_secrets()["deepseek_api_key"]
    if not _deepseek_enabled(ai_engine_id) or not api_key:
        raise RuntimeError("DeepSeek AI Engine is not enabled")

    request_body: dict[str, Any] = {
        "model": _deepseek_model(),
        "messages": [
            {
                "role": "system",
                "content": _ai_engine_context_gate(
                    employee_profile=employee_profile,
                    employee=employee,
                    ticket_keys=ticket_keys,
                    skills=skills,
                    memory_snippets=memory_snippets,
                ),
            },
            *_chat_completion_history(recent_messages),
            {"role": "user", "content": message},
        ],
        "stream": False,
        "max_tokens": _deepseek_max_tokens(),
        "thinking": {"type": _deepseek_thinking_type()},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{_deepseek_base_url()}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek AI Engine failed: {response.status_code} {response.text[:500]}",
        )

    payload = response.json()
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HTTPException(status_code=502, detail="DeepSeek AI Engine returned no choices")
    message_payload = choices[0].get("message") if isinstance(choices[0], dict) else None
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
        "model": payload.get("model") or _deepseek_model(),
        "updated_at": _now(),
    }
    metadata = {
        "ai_engine": "deepseek_chat_completions",
        "model": next_state["model"],
        "response_id": response_id,
        "assumed_agent_session": True,
        "usage": payload.get("usage"),
        "thinking": _deepseek_thinking_type(),
    }
    return reply.strip(), next_state, metadata


async def _stream_deepseek_agent(
    context: ChatRunContext,
) -> AsyncIterator[tuple[str, str | dict[str, Any]]]:
    api_key = _ai_engine_secrets()["deepseek_api_key"]
    if not _deepseek_enabled(context.selected_ai_engine) or not api_key:
        raise RuntimeError("DeepSeek AI Engine is not enabled")

    request_body: dict[str, Any] = {
        "model": _deepseek_model(),
        "messages": [
            {
                "role": "system",
                "content": _ai_engine_context_gate(
                    employee_profile=context.selected_profile,
                    employee=context.employee,
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
        "max_tokens": _deepseek_max_tokens(),
        "thinking": {"type": _deepseek_thinking_type()},
    }

    response_id = f"deepseek-{uuid4().hex[:12]}"
    model = _deepseek_model()
    usage: Any = None
    reply_parts: list[str] = []

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            f"{_deepseek_base_url()}/chat/completions",
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
                delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
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
        "thinking": _deepseek_thinking_type(),
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


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _tool_calls_from_trace_events(trace_events: list[ChatTraceEvent]) -> list[dict[str, Any]]:
    calls: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    terminal_phases = {"completed", "blocked", "failed"}
    for event in trace_events:
        parts = event.event.split(".")
        if len(parts) < 3 or parts[0] != "tool":
            continue
        tool_name = parts[1]
        phase = ".".join(parts[2:])
        if tool_name == "intent_planner":
            continue
        if phase not in {"called", *terminal_phases}:
            continue

        if tool_name not in calls:
            order.append(tool_name)
            calls[tool_name] = {
                "tool": tool_name,
                "status": "planned",
                "events": [],
            }
        call = calls[tool_name]
        call["events"].append(event.model_dump(mode="json"))
        if phase == "called" and call.get("status") == "planned":
            call["status"] = "called"
        if phase in terminal_phases:
            call["status"] = phase
            call["result"] = event.data
    return [calls[tool_name] for tool_name in order]


def _ai_engine_event_metadata(trace_events: list[ChatTraceEvent]) -> dict[str, Any]:
    for event in reversed(trace_events):
        if event.event.startswith("ai_engine."):
            data = dict(event.data)
            data["event"] = event.event
            data["detail"] = event.detail
            return data
    return {}


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
    tool_calls = _tool_calls_from_trace_events(trace_events)
    ai_engine_event = _ai_engine_event_metadata(trace_events)
    selected_ai_engine = context.selected_ai_engine
    if tool_calls:
        actual_ai_engine = "built_in_tool"
    elif ai_engine_event.get("event") == "ai_engine.stub.completed":
        actual_ai_engine = "stub"
    else:
        actual_ai_engine = str(ai_engine_event.get("ai_engine") or context.engine_state.get("ai_engine") or selected_ai_engine)

    return {
        "run_id": context.run_id,
        "thread_id": context.thread_id,
        "employee": {
            "id": context.employee.id,
            "display_name": context.employee.display_name,
            "role": context.employee.role,
        },
        "ticket_keys": context.ticket_keys,
        "ai_engine": {
            "selected_ai_engine": selected_ai_engine,
            "employee_default_ai_engine": context.employee.default_ai_engine,
            "actual_ai_engine": actual_ai_engine,
            "model": ai_engine_event.get("model") or _selected_ai_engine_model(selected_ai_engine),
            "engine_thread_id": final_engine_thread_id,
            "event": ai_engine_event.get("event"),
        },
        "tools": tool_calls,
        "trace": {
            "path": str(trace_path.relative_to(_workspace_root())),
            "event_count": len(trace_events),
        },
        "created_at": _now(),
    }


def _build_reply(
    *,
    employee: ChatEmployeeSummary,
    message: str,
    ticket_keys: list[str],
    engine_thread_id: str,
    skills: list[str],
    memory_snippets: list[str],
) -> str:
    ticket_text = ", ".join(ticket_keys) if ticket_keys else "not bound"
    skill_text = ", ".join(skills[:4]) if skills else "no local skills loaded"
    memory_text = f"{len(memory_snippets)} local memory snippet(s)" if memory_snippets else "no local memory snippets"

    return (
        f"{employee.display_name} received the request.\n\n"
        f"Role: {employee.role}\n"
        f"Ticket: {ticket_text}\n"
        f"AI Engine: {employee.ai_engine_mode}; default: {employee.default_ai_engine}; engine thread: {engine_thread_id}\n"
        f"Context gate: {skill_text}; {memory_text}\n\n"
        "P0 file-backed run completed: I loaded the addressed employee profile, "
        "resolved the reusable AI Engine thread mapping, captured the conversation, "
        "and wrote a local trace. External Ticket, harness, and AI Engine execution are "
        "not invoked in this first slice.\n\n"
        "Next action preview: read the Ticket context, pick the relevant skills and "
        "memory, execute through the configured external or local AI Engine, "
        "and report progress back into this thread with trace evidence."
    )


def _prepare_chat_run(request: ChatMessageRequest) -> ChatRunContext:
    profiles = _load_employees()
    selected = _select_employee(
        profiles,
        requested_employee_id=request.target_employee_id,
        message=request.message,
    )
    employee = _employee_summary(selected)
    selected_ai_engine = _selected_ai_engine_for_employee(employee)

    thread_id = request.thread_id or _employee_default_thread_id(employee.id)
    thread_id = _require_safe_id(thread_id, field="thread_id")
    run_id = f"run-{uuid4().hex[:12]}"
    ticket_keys = _extract_ticket_keys(request.message, request.ticket_key)
    run_dirs = _ensure_run_dirs()
    recent_messages = _load_conversation_messages(thread_id, limit=12)
    engine_state = _engine_thread_state(employee.id, thread_id)
    engine_thread_id = str(engine_state.get("engine_thread_id") or _engine_thread_id(employee.id, thread_id))
    skills = _skill_titles(employee.skills)
    memories = recall_memory_snippets(
        employee_id=employee.id,
        query=request.message,
        ticket_keys=ticket_keys,
    )
    for snippet in knowledge_snippets(request.message, limit=3):
        if snippet.startswith("[memory:"):
            continue
        if snippet not in memories:
            memories.append(snippet)

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
            detail="Loaded file-backed employee, skill, and approved memory context.",
            data={"skills": skills, "memory_count": len(memories), "recent_message_count": len(recent_messages)},
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
        _save_engine_thread_state(context.employee.id, context.thread_id, engine_state)
    final_engine_thread_id = engine_thread_id or context.engine_thread_id

    trace_events = [
        *context.trace_events,
        *(extra_trace_events or []),
        ChatTraceEvent(event="response.created", detail="Assistant response was created."),
    ]

    conversation_path = context.run_dirs["conversations"] / f"{context.thread_id}.jsonl"
    trace_path = context.run_dirs["traces"] / f"{context.run_id}.jsonl"
    run_metadata = _build_run_metadata(
        context,
        final_engine_thread_id=final_engine_thread_id,
        trace_events=trace_events,
        trace_path=trace_path,
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
        memory_candidate = propose_memory_from_chat_turn(
            run_id=context.run_id,
            thread_id=context.thread_id,
            employee_id=context.employee.id,
            employee_display_name=context.employee.display_name,
            user_message=context.request.message,
            assistant_reply=reply,
            ticket_keys=context.ticket_keys,
            trace_path=str(trace_path.relative_to(_workspace_root())),
        )
        if memory_candidate is not None:
            trace_events.append(
                ChatTraceEvent(
                    event="memory.candidate.proposed",
                    detail="Proposed a memory candidate from this chat turn.",
                    data={
                        "candidate_id": memory_candidate.id,
                        "scope": f"{memory_candidate.scope_kind}:{memory_candidate.scope_ref}",
                        "confidence": memory_candidate.confidence,
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


async def _maybe_complete_local_tool(context: ChatRunContext) -> ChatMessageResponse | None:
    plan = await _plan_local_tool_intent(context)
    if plan.tool == "search_knowledge":
        return _complete_search_knowledge_tool(context, plan)
    if plan.tool == "create_ticket":
        return _complete_create_ticket_tool(context, plan)
    if plan.tool == "record_ticket_report":
        return _complete_record_ticket_report_tool(context, plan)
    if plan.tool == "list_tickets":
        return _complete_list_tickets_tool(context, plan)
    if plan.tool == "list_code_repositories":
        return _complete_list_code_repositories_tool(context, plan)
    if plan.tool == "inspect_code_repository":
        return _complete_inspect_code_repository_tool(context, plan)
    if plan.tool == "create_employee":
        return _complete_create_employee_tool(context, plan)
    if plan.tool == "edit_employee_profile":
        return _complete_edit_employee_profile_tool(context, plan)
    if plan.tool == "delete_employee":
        return _complete_delete_employee_tool(context, plan)
    if plan.tool == "create_skill":
        return _complete_create_skill_tool(context, plan)
    if plan.tool == "assign_skill_to_employee":
        return _complete_assign_skill_to_employee_tool(context, plan)
    if plan.tool == "delete_skill":
        return _complete_delete_skill_tool(context, plan)
    if plan.tool == "list_skills":
        tool_result = _list_skills_tool_result()
        tool_result["plan"] = _plan_trace_data(plan)
        reply = _build_list_skills_reply(tool_result)
        return _persist_chat_response(
            context,
            reply=reply,
            extra_trace_events=[
                ChatTraceEvent(
                    event="tool.list_skills.called",
                    detail="Resolved list_skills as a local file-backed tool.",
                    data={
                        "requested_by": context.employee.id,
                        "tool": "list_skills",
                    },
                ),
                ChatTraceEvent(
                    event="tool.list_skills.completed",
                    detail="Loaded local skill profiles.",
                    data=tool_result,
                ),
            ],
        )
    if plan.tool != "list_employees":
        return None

    tool_result = _list_employees_tool_result()
    tool_result["plan"] = _plan_trace_data(plan)
    reply = _build_list_employees_reply(tool_result)
    return _persist_chat_response(
        context,
        reply=reply,
        extra_trace_events=[
            ChatTraceEvent(
                event="tool.list_employees.called",
                detail="Resolved list_employees as a local file-backed tool.",
                data={
                    "requested_by": context.employee.id,
                    "tool": "list_employees",
                },
            ),
            ChatTraceEvent(
                event="tool.list_employees.completed",
                detail="Loaded local employee profiles.",
                data=tool_result,
            ),
        ],
    )


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
        "model": request.openai_model.strip() or "gpt-5-nano",
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
    if request.thinking is not None and engine == "deepseek":
        engine_config["thinking"] = _normalize_thinking(request.thinking)
    if request.base_url is not None:
        engine_config["base_url"] = request.base_url.strip() or str(AI_ENGINE_CATALOG[engine].get("default_base_url") or "")
    if request.api_key_env is not None:
        engine_config["api_key_env"] = request.api_key_env.strip() or str(AI_ENGINE_CATALOG[engine].get("default_api_key_env") or "")
    if request.enabled is not None:
        engine_config["enabled"] = bool(request.enabled)

    engine_configs[engine] = engine_config
    next_config["engine_configs"] = engine_configs
    if engine == "deepseek":
        next_config["deepseek_model"] = str(engine_config.get("model") or "deepseek-v4-flash")
        next_config["deepseek_thinking"] = _normalize_thinking(str(engine_config.get("thinking") or "disabled"))
    elif engine == "openai":
        next_config["openai_model"] = str(engine_config.get("model") or "gpt-5-nano")

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

    # Clean up AI Engine thread mapping
    engine_thread_path = _workspace_dir() / "engine_threads.json"
    if engine_thread_path.exists():
        try:
            mapping = json.loads(engine_thread_path.read_text(encoding="utf-8"))
            keys_to_remove = [k for k, v in mapping.items() if k.endswith(f"-{thread_id[:8]}") or k == f"{employee_id}:{thread_id}"]
            for key in keys_to_remove:
                del mapping[key]
            if keys_to_remove:
                engine_thread_path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass

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


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    chunks.append(text)
        return "".join(chunks).strip()
    return str(content).strip() if content is not None else ""


def _latest_human_message_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _message_content_to_text(message.content)
    return ""


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
    local_tool_response = await _maybe_complete_local_tool(context)
    if local_tool_response is not None:
        return local_tool_response

    ai_engine_id = context.selected_ai_engine
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
    except RuntimeError:
        return _persist_chat_response(
            context,
            reply=_stub_reply(context),
            extra_trace_events=[
                ChatTraceEvent(event="ai_engine.stub.completed", detail="Generated P0 file-backed response.")
            ],
        )
    except HTTPException as exc:
        if not _ai_engine_fallback_on_error():
            raise
        return _persist_chat_response(
            context,
            reply=_stub_reply(context),
            extra_trace_events=[
                ChatTraceEvent(
                    event="ai_engine.remote.failed",
                    detail="Remote AI Engine failed; fell back to file-backed response.",
                    data={"status_code": exc.status_code, "detail": str(exc.detail)[:500]},
                ),
                ChatTraceEvent(event="ai_engine.stub.completed", detail="Generated P0 file-backed response."),
            ],
        )


def _sse_payload(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _reply_chunks(reply: str) -> list[str]:
    chunks = re.split(r"(\s+)", reply)
    merged: list[str] = []
    current = ""
    for chunk in chunks:
        if not chunk:
            continue
        current += chunk
        if len(current) >= 16 or "\n" in current:
            merged.append(current)
            current = ""
    if current:
        merged.append(current)
    return merged or [reply]


def _agui_message_payload(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        data = message.model_dump(by_alias=True, exclude_none=True)
        return data if isinstance(data, dict) else {}
    if isinstance(message, dict):
        return {key: value for key, value in message.items() if value is not None}
    return {}


def _latest_agui_user_message_payload(messages: list[Any]) -> dict[str, Any] | None:
    for message in reversed(messages):
        payload = _agui_message_payload(message)
        if payload.get("role") == "user":
            return payload
    return None


def _latest_agui_user_message_text(messages: list[Any]) -> str:
    payload = _latest_agui_user_message_payload(messages)
    if payload is None:
        return ""
    return _message_content_to_text(payload.get("content"))


def _checkpoint_id_from_config(config: RunnableConfig | dict[str, Any]) -> str | None:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    checkpoint_id = configurable.get("checkpoint_id") if isinstance(configurable, dict) else None
    return str(checkpoint_id) if checkpoint_id else None


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
    if _TOOL_PLANNING_SIGNAL_RE.search(request.message):
        context = _prepare_chat_run(request)
        response = await _maybe_complete_local_tool(context)
        if response is not None:
            yield "final", response
            return
        if context.selected_ai_engine == "deepseek" and _ai_engine_secrets()["deepseek_api_key"]:
            async for event, payload in _stream_deepseek_agent(context):
                yield event, payload
            return

    context = _prepare_chat_run(request)
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
            if _TOOL_PLANNING_SIGNAL_RE.search(request.message):
                context = _prepare_chat_run(request)
                response = await _maybe_complete_local_tool(context)
                if response is None:
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
                else:
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
                    return

            context = _prepare_chat_run(request)
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
