"""
File-backed Member Chat routes.

P0 intentionally avoids database dependencies. Member profiles, conversation
history, trace events, and external provider thread mappings live under the
local .aiteamos workspace directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
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

router = APIRouter(prefix="/api/v1/chat", tags=["member-chat"])

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_LIST_MEMBERS_EN_RE = re.compile(
    r"\b(list|show|display|view)\b.*\b(ai\s+)?members\b|\bmembers\b.*\b(list|show|all|available)\b"
)
_CREATE_MEMBER_EN_RE = re.compile(r"\b(create|add|new|setup|set up)\b.*\b(member|profile|user|employee)\b")
_EDIT_MEMBER_EN_RE = re.compile(r"\b(edit|update|modify|change)\b.*\b(member|profile)\b")
_DELETE_MEMBER_EN_RE = re.compile(r"\b(delete|remove|drop)\b.*\b(member|profile|user|employee)\b")
_LIST_SKILLS_EN_RE = re.compile(r"\b(list|show|display|view)\b.*\bskills?\b|\bskills?\b.*\b(list|show|all|available)\b")
_CREATE_SKILL_EN_RE = re.compile(r"\b(create|add|new|setup|set up)\b.*\bskill\b")
_ASSIGN_SKILL_EN_RE = re.compile(r"\b(assign|add|give|attach)\b.*\bskill\b.*\b(to|for)\b")
_DELETE_SKILL_EN_RE = re.compile(r"\b(delete|remove|drop)\b.*\bskill\b")
_TOOL_PLANNING_SIGNAL_RE = re.compile(
    r"create_member|edit_member_profile|delete_member|list_members|"
    r"list_skills|create_skill|assign_skill_to_member|delete_skill|"
    r"创建|新增|添加|新建|补|配置|设置|编辑|修改|更新|调整|改成|改为|删除|移除|删掉|分配|关联|"
    r"列出|列表|清单|有哪些|所有|员工|成员|用户|"
    r"技能|"
    r"\b(create|add|new|setup|edit|update|modify|change|delete|remove|drop|assign|list|show|member|employee|profile|user|skills?)\b",
    re.IGNORECASE,
)
TEAM_LEAD_MEMBER_ID = "clara"
TEAM_LEAD_DISPLAY_NAME = "Clara"
TEAM_LEAD_ROLE = "AI Team Lead"
_CORE_MEMBER_GAPS: dict[str, tuple[str, ...]] = {
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
    ("AI Team Lead", ("clara", "team lead", "团队负责人", "协调者")),
)
_ROLE_DEFAULT_SKILLS: dict[str, list[str]] = {
    "AI Team Lead": ["task-specification", "agent-topology-design", "technical-decision", "validation-strategy"],
    "AI Architect": ["system-architecture-design", "architecture-review", "technical-decision"],
    "AI PV": ["test-engineering", "validation-strategy"],
    "AI Release": ["resource-planning", "validation-strategy"],
    "AI QA / Harness Runner": ["test-engineering", "validation-strategy"],
    "AI Memory Curator": ["technical-decision"],
    "AI RD / Implementer": ["backend-api-implementation", "frontend-api-integration", "test-engineering"],
}


class ChatMemberSummary(BaseModel):
    id: str
    display_name: str
    kind: str = "ai"
    role: str
    summary: str = ""
    skills: list[str] = Field(default_factory=list)
    runtime_mode: str = "external_or_file_stub"
    preserve_provider_thread: bool = True


class ChatSkillSummary(BaseModel):
    id: str
    title: str
    description: str = ""
    assigned_members: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    saved_path: str


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    target_member_id: str | None = None
    thread_id: str | None = None
    jira_key: str | None = None


class ChatTraceEvent(BaseModel):
    event: str
    detail: str
    data: dict[str, Any] = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    thread_id: str
    run_id: str
    target_member: ChatMemberSummary
    provider_thread_id: str
    jira_keys: list[str]
    reply: str
    trace_events: list[ChatTraceEvent]
    saved_paths: dict[str, str]


class ConversationMessage(BaseModel):
    timestamp: str
    role: str
    content: str
    member_id: str | None = None
    run_id: str | None = None


class ConversationResponse(BaseModel):
    thread_id: str
    messages: list[ConversationMessage]


class ChatRuntimeSettings(BaseModel):
    provider: str = "stub"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: str = "disabled"
    openai_model: str = "gpt-5-nano"
    fallback_on_error: bool = True
    api_keys_configured: dict[str, bool] = Field(default_factory=dict)
    saved_paths: dict[str, str] = Field(default_factory=dict)


class ChatRuntimeSettingsRequest(BaseModel):
    provider: str = "stub"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_thinking: str = "disabled"
    openai_model: str = "gpt-5-nano"
    fallback_on_error: bool = True
    deepseek_api_key: str | None = None
    openai_api_key: str | None = None


class ChatToolPlan(BaseModel):
    tool: str = "none"
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    source: str = "heuristic"


class AiteamosChatGraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    target_member_id: str | None
    jira_key: str | None
    aiteamos_chat_response: dict[str, Any]


@dataclass
class ChatRunContext:
    request: ChatMessageRequest
    selected_profile: dict[str, Any]
    member: ChatMemberSummary
    thread_id: str
    run_id: str
    jira_keys: list[str]
    runtime_dirs: dict[str, Path]
    provider_state: dict[str, Any]
    provider_thread_id: str
    skills: list[str]
    memories: list[str]
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


def _runtime_settings_path() -> Path:
    return _workspace_dir() / "runtime.json"


def _secrets_path() -> Path:
    return _workspace_dir() / "secrets.local.json"


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_provider(value: str | None) -> str:
    provider = (value or "stub").strip().lower()
    return provider if provider in {"stub", "deepseek", "openai"} else "stub"


def _normalize_thinking(value: str | None) -> str:
    thinking = (value or "disabled").strip().lower()
    return "enabled" if thinking in {"1", "true", "yes", "on", "enabled"} else "disabled"


def _runtime_config() -> dict[str, Any]:
    file_config = _read_json_file(_runtime_settings_path())
    return {
        "provider": _normalize_provider(file_config.get("provider") or os.environ.get("AITEAMOS_MODEL_PROVIDER")),
        "deepseek_model": str(
            file_config.get("deepseek_model")
            or os.environ.get("AITEAMOS_DEEPSEEK_MODEL")
            or "deepseek-v4-flash"
        ),
        "deepseek_thinking": _normalize_thinking(
            str(file_config.get("deepseek_thinking") or os.environ.get("AITEAMOS_DEEPSEEK_THINKING") or "disabled")
        ),
        "openai_model": str(file_config.get("openai_model") or os.environ.get("AITEAMOS_OPENAI_MODEL") or "gpt-5-nano"),
        "fallback_on_error": bool(
            file_config.get(
                "fallback_on_error",
                os.environ.get("AITEAMOS_RUNTIME_FALLBACK_ON_ERROR", "1").lower() in {"1", "true", "yes", "on"},
            )
        ),
    }


def _runtime_secrets() -> dict[str, str]:
    file_secrets = _read_json_file(_secrets_path())
    return {
        "deepseek_api_key": str(file_secrets.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY") or ""),
        "openai_api_key": str(file_secrets.get("openai_api_key") or os.environ.get("OPENAI_API_KEY") or ""),
    }


def _runtime_settings_response() -> ChatRuntimeSettings:
    config = _runtime_config()
    secrets = _runtime_secrets()
    return ChatRuntimeSettings(
        **config,
        api_keys_configured={
            "deepseek": bool(secrets["deepseek_api_key"]),
            "openai": bool(secrets["openai_api_key"]),
        },
        saved_paths={
            "runtime": str(_runtime_settings_path().relative_to(_workspace_root())),
            "secrets": str(_secrets_path().relative_to(_workspace_root())),
        },
    )


def _require_safe_id(value: str, *, field: str) -> str:
    if not _SAFE_ID_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


def _is_team_lead_member_id(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return normalized == TEAM_LEAD_MEMBER_ID


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read {path.name}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail=f"Invalid member profile: {path.name}")
    return data


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _normalize_member_profile(profile: dict[str, Any], path: Path) -> dict[str, Any]:
    normalized = dict(profile)
    profile_id = str(normalized.get("id") or path.stem)
    normalized["id"] = profile_id

    if _is_team_lead_member_id(profile_id):
        display_name = str(normalized.get("display_name") or "").strip()
        if not display_name:
            normalized["display_name"] = TEAM_LEAD_DISPLAY_NAME

        if not str(normalized.get("role") or "").strip():
            normalized["role"] = TEAM_LEAD_ROLE

        runtime = normalized.get("runtime") if isinstance(normalized.get("runtime"), dict) else {}
        runtime = dict(runtime)
        provider_identity = str(runtime.get("provider_identity") or "").strip()
        if not provider_identity:
            runtime["provider_identity"] = TEAM_LEAD_MEMBER_ID
        normalized["runtime"] = runtime

    return normalized


def _load_members() -> list[dict[str, Any]]:
    members_dir = _workspace_dir() / "members"
    if not members_dir.exists():
        return [_fallback_team_lead()]

    members_by_id: dict[str, dict[str, Any]] = {}
    for path in sorted(members_dir.glob("*.yaml")):
        profile = _normalize_member_profile(_read_yaml(path), path)
        profile_id = str(profile.get("id") or path.stem).lower()
        existing = members_by_id.get(profile_id)
        if existing is None or path.stem == profile.get("id"):
            members_by_id[profile_id] = profile

    return list(members_by_id.values()) or [_fallback_team_lead()]


def _fallback_team_lead() -> dict[str, Any]:
    return {
        "id": TEAM_LEAD_MEMBER_ID,
        "display_name": TEAM_LEAD_DISPLAY_NAME,
        "kind": "ai",
        "role": TEAM_LEAD_ROLE,
        "summary": "User-facing AI Team Lead for goals, constraints, routing, and final reporting.",
        "personality": "Calm, concise, explicit about blockers, and careful with handoffs.",
        "responsibilities": [
            "Understand user goals and constraints.",
            "Route work to the right AI Member or executor.",
            "Summarize progress, evidence, blockers, and next actions.",
        ],
        "skills": _default_skills_for_role(TEAM_LEAD_ROLE),
        "runtime": {
            "mode": "external_or_file_stub",
            "provider_identity": TEAM_LEAD_MEMBER_ID,
            "preserve_provider_thread": True,
        },
        "permissions": ["chat", "route_member", "read_local_assets", "write_trace"],
    }


def _member_summary(profile: dict[str, Any]) -> ChatMemberSummary:
    runtime = profile.get("runtime") if isinstance(profile.get("runtime"), dict) else {}
    return ChatMemberSummary(
        id=str(profile.get("id", "")),
        display_name=str(profile.get("display_name") or profile.get("id") or "Unknown"),
        kind=str(profile.get("kind", "ai")),
        role=str(profile.get("role", "AI Member")),
        summary=str(profile.get("summary", "")),
        skills=[str(skill) for skill in profile.get("skills", [])],
        runtime_mode=str(runtime.get("mode", "external_or_file_stub")),
        preserve_provider_thread=bool(runtime.get("preserve_provider_thread", True)),
    )


def _members_dir() -> Path:
    return _workspace_dir() / "members"


def _skills_dir() -> Path:
    return _workspace_dir() / "skills"


def _member_profile_path(member_id: str) -> Path:
    member_id = _require_safe_id(member_id, field="member_id")
    return _members_dir() / f"{member_id}.yaml"


def _skill_dir(skill_id: str) -> Path:
    skill_id = _require_safe_id(skill_id, field="skill_id")
    return _skills_dir() / skill_id


def _skill_file_path(skill_id: str) -> Path:
    return _skill_dir(skill_id) / "SKILL.md"


def _member_sort_key(member: ChatMemberSummary) -> tuple[int, str]:
    if _is_team_lead_member_id(member.id):
        return (0, member.display_name.lower())
    return (1, member.display_name.lower())


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


def _slugify_member_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", value.lower()).strip("-_")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = f"member-{uuid4().hex[:8]}"
    return _require_safe_id(slug[:80], field="member_id")


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


def _extract_member_display_name(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:名字叫|名为|叫做|叫)\s*([A-Za-z][A-Za-z0-9_. -]{0,63}|[\u4e00-\u9fff]{1,16})",
            r"(?:display_name|name)\s*[:=：]\s*([A-Za-z][A-Za-z0-9_. -]{0,63})",
            r"\b(?:named|called)\s+([A-Za-z][A-Za-z0-9_. -]{0,63})",
            r"\bcreate_member\s+([A-Za-z][A-Za-z0-9_. -]{0,63})",
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


def _extract_explicit_member_id(message: str) -> str | None:
    value = _extract_first(
        [
            r"\b(?:member_id|id)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
            r"(?:成员\s*id|成员ID)\s*[:=：]\s*([A-Za-z0-9_-]{1,80})",
        ],
        message,
    )
    return _slugify_member_id(value) if value else None


def _extract_member_kind(message: str) -> str:
    normalized = message.lower()
    if any(token in normalized for token in ("human", "user", "人类", "用户")):
        return "human"
    return "ai"


def _normalize_role_value(value: str) -> str:
    lower = f" {value.lower()} "
    for role, keywords in _ROLE_KEYWORDS:
        if any(keyword in lower for keyword in keywords):
            return role
    return value.strip() or "AI Member"


def _extract_member_role(message: str, *, require_role_marker: bool = False) -> str | None:
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


def _extract_runtime_mode(message: str) -> str | None:
    return _extract_first(
        [
            r"(?:runtime|运行模式)\s*(?:是|为|改成|改为|更新为|设置为|to|=|:|：)\s*([A-Za-z0-9_.:-]{1,80})",
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
        "list_member": "list_members",
        "list_ai_members": "list_members",
        "create_ai_member": "create_member",
        "add_member": "create_member",
        "new_member": "create_member",
        "edit_member": "edit_member_profile",
        "update_member": "edit_member_profile",
        "update_member_profile": "edit_member_profile",
        "remove_member": "delete_member",
        "delete_ai_member": "delete_member",
        "delete_user": "delete_member",
        "list_skill": "list_skills",
        "show_skills": "list_skills",
        "create_agent_skill": "create_skill",
        "new_skill": "create_skill",
        "add_skill": "create_skill",
        "assign_skill": "assign_skill_to_member",
        "attach_skill": "assign_skill_to_member",
        "add_skill_to_member": "assign_skill_to_member",
        "remove_skill": "delete_skill",
        "drop_skill": "delete_skill",
    }
    tool = tool_aliases.get(raw_tool, raw_tool)
    if tool not in {
        "none",
        "list_members",
        "create_member",
        "edit_member_profile",
        "delete_member",
        "list_skills",
        "create_skill",
        "assign_skill_to_member",
        "delete_skill",
    }:
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
    if _model_provider() != "deepseek":
        return False
    return bool(_runtime_secrets()["deepseek_api_key"])


async def _call_deepseek_tool_planner(context: ChatRunContext) -> ChatToolPlan:
    members = [_member_summary(profile).model_dump() for profile in _load_members()]
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
                    "Allowed tools:\n"
                    "- none\n"
                    "- list_members\n"
                    "- create_member\n"
                    "- edit_member_profile\n"
                    "- delete_member\n\n"
                    "- list_skills\n"
                    "- create_skill\n"
                    "- assign_skill_to_member\n\n"
                    "- delete_skill\n\n"
                    "JSON schema:\n"
                    "{"
                    "\"tool\":\"none|list_members|create_member|edit_member_profile|delete_member|"
                    "list_skills|create_skill|assign_skill_to_member|delete_skill\","
                    "\"arguments\":{},"
                    "\"confidence\":0.0,"
                    "\"reason\":\"short reason\""
                    "}\n\n"
                    "Arguments for create_member: display_name, member_id, kind, role, summary, responsibility, skills. "
                    "Arguments for edit_member_profile: target_member_id or target_member_name, display_name, role, "
                    "summary, skills, add_skills, runtime_mode. "
                    "Arguments for delete_member: target_member_id or target_member_name. "
                    "Arguments for create_skill: skill_id, title, description, body. "
                    "Arguments for assign_skill_to_member: skill_id or skill_name, target_member_id or target_member_name. "
                    "Arguments for delete_skill: skill_id or skill_name. "
                    "Map PV, verification, regression, and harness triage roles to role='AI PV'. "
                    "Map release work to role='AI Release'. Map QA or harness runner to role='AI QA / Harness Runner'. "
                    "Use kind='ai' for AI employee/member requests and kind='human' only for human user/member requests. "
                    "Choose a tool only when the user intends to inspect or change AITeamOS local member profiles "
                    "or local SKILL.md assets."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": context.request.message,
                        "target_member": context.member.model_dump(),
                        "existing_members": members,
                        "existing_skills": skills,
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
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {_runtime_secrets()['deepseek_api_key']}",
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
    if _is_create_skill_request(message):
        return ChatToolPlan(tool="create_skill", confidence=0.45, reason="Matched local create-skill fallback.")
    if _is_assign_skill_request(message):
        return ChatToolPlan(
            tool="assign_skill_to_member",
            confidence=0.45,
            reason="Matched local assign-skill fallback.",
        )
    if _is_delete_skill_request(message):
        return ChatToolPlan(tool="delete_skill", confidence=0.45, reason="Matched local delete-skill fallback.")
    if _is_list_skills_request(message):
        return ChatToolPlan(tool="list_skills", confidence=0.45, reason="Matched local list-skills fallback.")
    if _is_create_member_request(message):
        return ChatToolPlan(tool="create_member", confidence=0.45, reason="Matched local create-member fallback.")
    if _is_delete_member_request(message):
        return ChatToolPlan(tool="delete_member", confidence=0.45, reason="Matched local delete-member fallback.")
    if _is_edit_member_profile_request(message):
        return ChatToolPlan(
            tool="edit_member_profile",
            confidence=0.45,
            reason="Matched local edit-member fallback.",
        )
    if _is_list_members_request(message):
        return ChatToolPlan(tool="list_members", confidence=0.45, reason="Matched local list-members fallback.")
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
        return "Verification-focused AI Member for regression, harness, and failing case triage."
    if role == "AI Release":
        return "Release-focused AI Member for build, packaging, integration, and release-flow analysis."
    if role == "AI Architect":
        return "Architecture-focused AI Member for system design, tradeoff analysis, and boundary review."
    if role == "AI QA / Harness Runner":
        return "QA-focused AI Member for test execution, harness evidence, and validation reporting."
    if role == "AI Memory Curator":
        return "Memory-focused AI Member for extracting reusable project knowledge from execution traces."
    if role == "AI RD / Implementer":
        return "Implementation-focused AI Member for code changes, bug fixing, and engineering handoff reports."
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
        "AI RD / Implementer": ["Investigate bounded engineering tasks.", "Implement changes and report verification results."],
    }
    return defaults.get(role, ["Handle delegated AITeamOS member work within profile boundaries."])


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
    if role != TEAM_LEAD_ROLE:
        rules.append("Escalate cross-member coordination needs to Clara.")
    if role != "AI Architect":
        rules.append("Escalate architecture ambiguity to AI Architect.")
    if role not in {"AI PV", "AI QA / Harness Runner"}:
        rules.append("Ask AI PV or AI QA to validate regression and harness evidence.")
    return rules


def _default_skills_for_role(role: str) -> list[str]:
    return list(_ROLE_DEFAULT_SKILLS.get(role, []))


def _build_member_profile(
    *,
    member_id: str,
    display_name: str,
    kind: str,
    role: str,
    summary: str,
    skills: list[str],
    responsibility: str | None,
) -> dict[str, Any]:
    runtime_mode = "human" if kind == "human" else "external_or_file_stub"
    return {
        "id": member_id,
        "display_name": display_name,
        "kind": kind,
        "role": role,
        "summary": summary,
        "personality": "Concise, evidence-driven, and explicit about blockers.",
        "responsibilities": _default_responsibilities(role, responsibility),
        "skills": skills,
        "memory_scopes": ["global", "aiteamos"] if role == TEAM_LEAD_ROLE else ["project", f"member:{member_id}"],
        "runtime": {
            "mode": runtime_mode,
            "provider_identity": member_id,
            "preserve_provider_thread": True,
        },
        "permissions": _default_permissions(kind, role),
        "handoff_rules": _default_handoff_rules(role),
        "created_at": _now(),
        "updated_at": _now(),
    }


def _find_member_profile(member_id_or_name: str) -> tuple[Path, dict[str, Any]] | None:
    lookup = member_id_or_name.strip().lower()
    members_dir = _members_dir()
    if not members_dir.exists():
        return None
    for path in sorted(members_dir.glob("*.yaml")):
        profile = _read_yaml(path)
        profile_id = str(profile.get("id") or path.stem)
        display_name = str(profile.get("display_name") or profile_id)
        if lookup in {profile_id.lower(), display_name.lower()}:
            profile.setdefault("id", profile_id)
            return path, profile
    return None


def _extract_edit_member_target(message: str, context: ChatRunContext) -> str | None:
    explicit_id = _extract_explicit_member_id(message)
    if explicit_id:
        return explicit_id

    normalized = message.lower()
    profiles = sorted((_member_summary(profile) for profile in _load_members()), key=_member_sort_key)
    ordered_profiles = [
        *[member for member in profiles if member.id != context.member.id],
        *[member for member in profiles if member.id == context.member.id],
    ]
    for member in ordered_profiles:
        if re.search(rf"\b{re.escape(member.id.lower())}\b", normalized):
            return member.id
        if member.display_name.lower() in normalized:
            return member.id

    if context.member.id != "clara":
        return context.member.id
    return None


def _is_list_members_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "list_members" in normalized:
        return True
    if _LIST_MEMBERS_EN_RE.search(normalized):
        return True

    compact = re.sub(r"\s+", "", normalized)
    if not any(token in compact for token in ("成员", "员工", "member", "employee")):
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


def _is_create_member_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "create_member" in normalized:
        return True
    if _CREATE_MEMBER_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    if not any(token in compact for token in ("成员", "员工", "member", "employee", "用户", "user")):
        return False
    return any(token in compact for token in ("创建", "新增", "添加", "新建"))


def _is_edit_member_profile_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "edit_member_profile" in normalized:
        return True
    if _EDIT_MEMBER_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    has_profile_token = any(token in compact for token in ("成员", "员工", "member", "employee", "profile", "用户", "user"))
    has_field_token = any(token in compact for token in ("summary", "role", "skills", "skill", "技能", "runtime", "名字", "角色", "摘要", "描述"))
    if not has_profile_token and not has_field_token:
        return False
    return any(token in compact for token in ("编辑", "修改", "更新", "调整", "改成", "改为"))


def _is_delete_member_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "delete_member" in normalized:
        return True
    if _DELETE_MEMBER_EN_RE.search(normalized):
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
    if any(token in compact for token in ("成员", "员工", "member", "employee", "profile", "用户", "user")):
        return True

    for profile in _load_members():
        member = _member_summary(profile)
        if re.search(rf"\b{re.escape(member.id.lower())}\b", normalized):
            return True
        if member.display_name.lower() in normalized:
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
    if any(token in compact for token in ("成员", "员工", "member", "employee", "用户", "user")):
        return False
    return any(token in compact for token in ("创建", "新增", "新建"))


def _is_assign_skill_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "assign_skill_to_member" in normalized:
        return True
    if _ASSIGN_SKILL_EN_RE.search(normalized):
        return True
    compact = re.sub(r"\s+", "", normalized)
    has_skill_reference = any(token in compact for token in ("skill", "skills", "技能"))
    if not has_skill_reference and _extract_existing_skill_id(message) is None:
        return False
    if any(token in compact for token in ("summary", "role", "runtime", "名字", "角色", "摘要", "描述", "改成", "改为")):
        return False
    if not any(token in compact for token in ("分配", "关联", "添加", "增加", "assign", "attach")):
        return False
    if any(token in compact for token in ("成员", "member", "员工")):
        return True
    return any(
        member.id.lower() in normalized or member.display_name.lower() in normalized
        for member in (_member_summary(profile) for profile in _load_members())
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


def _is_local_tool_request(message: str) -> bool:
    return (
        _is_create_member_request(message)
        or _is_edit_member_profile_request(message)
        or _is_delete_member_request(message)
        or _is_list_members_request(message)
        or _is_list_skills_request(message)
        or _is_create_skill_request(message)
        or _is_assign_skill_request(message)
        or _is_delete_skill_request(message)
    )


def _detect_member_gaps(members: list[ChatMemberSummary]) -> list[str]:
    haystack = "\n".join(
        f"{member.id} {member.display_name} {member.role} {member.summary}".lower()
        for member in members
    )
    return [
        label
        for label, keywords in _CORE_MEMBER_GAPS.items()
        if not any(keyword.lower() in haystack for keyword in keywords)
    ]


def _list_members_tool_result() -> dict[str, Any]:
    members = sorted((_member_summary(profile) for profile in _load_members()), key=_member_sort_key)
    member_payloads = [member.model_dump() for member in members]
    return {
        "count": len(members),
        "members": member_payloads,
        "gaps": _detect_member_gaps(members),
        "deep_links": {
            "members": "#/members",
            **{f"member:{member.id}": f"#/members/{member.id}" for member in members},
        },
    }


def _build_list_members_reply(tool_result: dict[str, Any]) -> str:
    members = tool_result["members"]
    gaps = tool_result["gaps"]
    deep_links = tool_result["deep_links"]
    lines = [
        f"我找到了 {tool_result['count']} 个成员。",
        "",
        "成员列表：",
    ]

    for member in members:
        skill_count = len(member["skills"])
        summary = member["summary"] or "No summary"
        lines.append(
            f"- {member['display_name']} ({member['id']}) - {member['role']}；"
            f"{skill_count} skill(s)；runtime: {member['runtime_mode']}；{summary}"
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
        "- 如果要推进具体 Jira，可以直接点名成员，例如：Alex，请推进 Jira SV-1234 并汇报结果。",
        "- 如果要补齐团队拓扑，可以先创建 PV / Release / QA 等成员，再分配对应 Skills。",
        "",
        "查看入口：",
        f"- Members: {deep_links['members']}",
    ])
    for member in members:
        member_link = deep_links[f"member:{member['id']}"]
        lines.append(f"- {member['display_name']}: {member_link}")

    return "\n".join(lines)


def _list_skills_tool_result() -> dict[str, Any]:
    skills = sorted(_load_skills(), key=lambda skill: skill.id)
    return {
        "count": len(skills),
        "skills": [skill.model_dump() for skill in skills],
        "deep_links": {
            "skills": "#/skills",
            **{f"skill:{skill.id}": f"#/skills/{skill.id}" for skill in skills},
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
        assigned = ", ".join(skill["assigned_members"]) if skill["assigned_members"] else "unassigned"
        description = skill["description"] or "No description"
        lines.append(
            f"- {skill['title']} ({skill['id']})；assigned: {assigned}；"
            f"resources: {len(skill['resources'])}；{description}"
        )

    lines.extend([
        "",
        "建议下一步：",
        "- 如果要新增可复用能力，可以让我创建一个本地 SKILL.md。",
        "- 如果要让某个成员使用它，可以让我把 Skill 分配给对应 Member。",
        "",
        "查看入口：",
        f"- Skills: {deep_links['skills']}",
    ])
    for skill in skills:
        skill_link = deep_links[f"skill:{skill['id']}"]
        lines.append(f"- {skill['title']}: {skill_link}")

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
                data={"requested_by": context.member.id, "tool": tool_name},
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


def _complete_create_member_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    display_name = _tool_str_arg(plan, "display_name", "name") or _extract_member_display_name(message)
    if not display_name:
        result = {
            "status": "blocked",
            "reason": "missing_display_name",
            "detail": "Member display name was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_tool_reply(
            "create_member",
            "没有识别到成员名字。",
            "Clara，请创建一个 AI PV 成员，名字叫 Victor，负责 regression 和 harness fail triage。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="create_member",
            reply=reply,
            result=result,
            completed=False,
        )

    member_id = _extract_explicit_member_id(message) or _slugify_member_id(display_name)
    planned_member_id = _tool_str_arg(plan, "member_id", "id")
    if planned_member_id:
        member_id = _slugify_member_id(planned_member_id)
    existing = _find_member_profile(member_id) or _find_member_profile(display_name)
    if existing:
        existing_summary = _member_summary(existing[1])
        result = {
            "status": "blocked",
            "reason": "member_already_exists",
            "detail": f"Member already exists: {existing_summary.id}",
            "member": existing_summary.model_dump(),
            "deep_links": {
                "member": f"#/members/{existing_summary.id}",
                "members": "#/members",
            },
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有创建新成员，因为 {existing_summary.display_name} 已经存在。\n\n"
            f"- Member: {existing_summary.display_name} ({existing_summary.id})\n"
            f"- Role: {existing_summary.role}\n"
            f"- 查看：#/members/{existing_summary.id}\n\n"
            "如果你想修改它，可以说：Clara，请把 "
            f"{existing_summary.display_name} 的 summary 改成 ..."
        )
        return _persist_local_tool_response(
            context,
            tool_name="create_member",
            reply=reply,
            result=result,
            completed=False,
        )

    kind = (_tool_str_arg(plan, "kind") or _extract_member_kind(message)).lower()
    kind = "human" if kind == "human" else "ai"
    planned_role = _tool_str_arg(plan, "role")
    role = _normalize_role_value(planned_role) if planned_role else _extract_member_role(message)
    role = role or ("Human Member" if kind == "human" else "AI Member")
    responsibility = _tool_str_arg(plan, "responsibility") or _extract_summary(message)
    summary = _tool_str_arg(plan, "summary") or _default_summary(display_name, role, responsibility)
    skills = _tool_list_arg(plan, "skills") or _extract_skills_value(message) or _default_skills_for_role(role)
    profile = _build_member_profile(
        member_id=member_id,
        display_name=display_name,
        kind=kind,
        role=role,
        summary=summary,
        skills=_dedupe(skills),
        responsibility=responsibility,
    )
    profile_path = _member_profile_path(member_id)
    _write_yaml(profile_path, profile)

    member = _member_summary(profile)
    result = {
        "status": "completed",
        "detail": f"Created member profile: {member.id}",
        "member": member.model_dump(),
        "saved_path": str(profile_path.relative_to(_workspace_root())),
        "deep_links": {
            "member": f"#/members/{member.id}",
            "members": "#/members",
        },
        "plan": _plan_trace_data(plan),
    }
    reply = (
        f"已创建成员 {member.display_name}。\n\n"
        f"- ID: {member.id}\n"
        f"- Type: {member.kind}\n"
        f"- Role: {member.role}\n"
        f"- Skills: {', '.join(member.skills) if member.skills else 'none'}\n"
        f"- Profile: {result['saved_path']}\n"
        f"- 查看：#/members/{member.id}\n\n"
        "下一步可以直接点名它协作，或让我继续编辑它的 profile。"
    )
    return _persist_local_tool_response(
        context,
        tool_name="create_member",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_edit_member_profile_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    target_id = (
        _tool_str_arg(plan, "target_member_id", "member_id", "id")
        or _tool_str_arg(plan, "target_member_name", "display_name", "name")
        or _extract_edit_member_target(message, context)
    )
    if not target_id:
        result = {
            "status": "blocked",
            "reason": "missing_target_member",
            "detail": "Target member was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_tool_reply(
            "edit_member_profile",
            "没有识别到要编辑哪个成员。",
            "Clara，请把 Alex 的 summary 改成 Implementation owner for backend API work。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="edit_member_profile",
            reply=reply,
            result=result,
            completed=False,
        )

    found = _find_member_profile(target_id)
    if not found:
        result = {
            "status": "blocked",
            "reason": "member_not_found",
            "detail": f"Member not found: {target_id}",
            "deep_links": {"members": "#/members"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到成员 {target_id}，所以没有修改 profile。\n\n"
            "你可以先让我列出所有成员，或先创建这个成员。\n"
            "- Members: #/members"
        )
        return _persist_local_tool_response(
            context,
            tool_name="edit_member_profile",
            reply=reply,
            result=result,
            completed=False,
        )

    profile_path, profile = found
    updates: dict[str, Any] = {}
    new_display_name = _tool_str_arg(plan, "new_display_name", "display_name", "name") or _extract_new_display_name(message)
    planned_role = _tool_str_arg(plan, "role")
    new_role = _normalize_role_value(planned_role) if planned_role else _extract_member_role(message, require_role_marker=True)
    new_summary = _tool_str_arg(plan, "summary") or _extract_summary(message)
    replace_skills = _tool_list_arg(plan, "skills") or _extract_skills_value(message)
    add_skills = _tool_list_arg(plan, "add_skills") or _extract_add_skills_value(message)
    runtime_mode = _tool_str_arg(plan, "runtime_mode", "runtime.mode") or _extract_runtime_mode(message)

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
    if runtime_mode:
        runtime = profile.get("runtime") if isinstance(profile.get("runtime"), dict) else {}
        runtime["mode"] = runtime_mode
        profile["runtime"] = runtime
        updates["runtime.mode"] = runtime_mode

    if not updates:
        result = {
            "status": "blocked",
            "reason": "no_supported_updates",
            "detail": "No supported member profile fields were found in the request.",
            "supported_fields": ["display_name", "role", "summary", "skills", "runtime.mode"],
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_tool_reply(
            "edit_member_profile",
            "没有识别到可更新字段。",
            "Clara，请把 Alex 的 role 改成 AI RD / Implementer，并添加技能 test-engineering。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="edit_member_profile",
            reply=reply,
            result=result,
            completed=False,
        )

    profile["updated_at"] = _now()
    _write_yaml(profile_path, profile)
    member = _member_summary(profile)
    result = {
        "status": "completed",
        "detail": f"Updated member profile: {member.id}",
        "member": member.model_dump(),
        "updates": updates,
        "saved_path": str(profile_path.relative_to(_workspace_root())),
        "deep_links": {
            "member": f"#/members/{member.id}",
            "members": "#/members",
        },
        "plan": _plan_trace_data(plan),
    }
    changed = "\n".join(f"- {key}: {value}" for key, value in updates.items())
    reply = (
        f"已更新成员 {member.display_name} 的 profile。\n\n"
        f"{changed}\n\n"
        f"- Profile: {result['saved_path']}\n"
        f"- 查看：#/members/{member.id}"
    )
    return _persist_local_tool_response(
        context,
        tool_name="edit_member_profile",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_delete_member_tool(context: ChatRunContext, plan: ChatToolPlan | None = None) -> ChatMessageResponse:
    message = context.request.message
    target_id = (
        _tool_str_arg(plan, "target_member_id", "member_id", "id")
        or _tool_str_arg(plan, "target_member_name", "display_name", "name")
        or _extract_edit_member_target(message, context)
    )
    if not target_id:
        result = {
            "status": "blocked",
            "reason": "missing_target_member",
            "detail": "Target member was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_tool_reply(
            "delete_member",
            "没有识别到要删除哪个成员。",
            "Clara，请删除成员 Victor。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="delete_member",
            reply=reply,
            result=result,
            completed=False,
        )

    found = _find_member_profile(target_id)
    if not found:
        result = {
            "status": "blocked",
            "reason": "member_not_found",
            "detail": f"Member not found: {target_id}",
            "deep_links": {"members": "#/members"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到成员 {target_id}，所以没有删除任何 profile。\n\n"
            "你可以先让我列出所有成员。\n"
            "- Members: #/members"
        )
        return _persist_local_tool_response(
            context,
            tool_name="delete_member",
            reply=reply,
            result=result,
            completed=False,
        )

    profile_path, profile = found
    member = _member_summary(profile)
    if member.id == "clara":
        result = {
            "status": "blocked",
            "reason": "protected_member",
            "detail": "Clara is the default coordinator and cannot be deleted.",
            "member": member.model_dump(),
            "deep_links": {"member": "#/members/clara", "members": "#/members"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            "没有删除 Clara。\n\n"
            "原因：Clara 是默认协调者和系统兜底入口，P0 不允许删除。\n"
            "- 查看：#/members/clara"
        )
        return _persist_local_tool_response(
            context,
            tool_name="delete_member",
            reply=reply,
            result=result,
            completed=False,
        )

    relative_profile_path = str(profile_path.relative_to(_workspace_root()))
    try:
        profile_path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot delete member profile: {member.id}") from exc
    removed_provider_thread_keys = _delete_provider_thread_states(member.id)

    result = {
        "status": "completed",
        "detail": f"Deleted member profile: {member.id}",
        "member": member.model_dump(),
        "deleted_path": relative_profile_path,
        "provider_thread_keys_removed": removed_provider_thread_keys,
        "retained_evidence": ["conversations", "traces"],
        "deep_links": {"members": "#/members"},
        "plan": _plan_trace_data(plan),
    }
    reply = (
        f"已删除成员 {member.display_name}。\n\n"
        f"- ID: {member.id}\n"
        f"- Profile: {relative_profile_path}\n"
        f"- 清理 provider thread 映射：{len(removed_provider_thread_keys)} 条\n"
        "- 历史 conversation 和 trace 已保留，用于审计。\n"
        "- Members: #/members"
    )
    return _persist_local_tool_response(
        context,
        tool_name="delete_member",
        reply=reply,
        result=result,
        completed=True,
    )


def _default_skill_body(skill_id: str, title: str, description: str) -> str:
    return (
        f"# {title}\n\n"
        f"> {description or f'AITeamOS reusable skill: {skill_id}.'}\n\n"
        "## When To Use\n\n"
        "- Use this skill when the task matches the description above.\n\n"
        "## Procedure\n\n"
        "1. Clarify the goal, constraints, and expected evidence.\n"
        "2. Apply the relevant project context and tools.\n"
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
            "deep_links": {"skill": f"#/skills/{existing.id}", "skills": "#/skills"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有创建新 Skill，因为 {existing.title} 已经存在。\n\n"
            f"- Skill: {existing.title} ({existing.id})\n"
            f"- 查看：#/skills/{existing.id}\n\n"
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
        "deep_links": {"skill": f"#/skills/{skill.id}", "skills": "#/skills"},
        "plan": _plan_trace_data(plan),
    }
    reply = (
        f"已创建 Skill {skill.title}。\n\n"
        f"- ID: {skill.id}\n"
        f"- Description: {skill.description or 'none'}\n"
        f"- Profile: {result['saved_path']}\n"
        f"- 查看：#/skills/{skill.id}\n\n"
        "下一步可以把它分配给一个或多个 Members。"
    )
    return _persist_local_tool_response(
        context,
        tool_name="create_skill",
        reply=reply,
        result=result,
        completed=True,
    )


def _complete_assign_skill_to_member_tool(
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
        _tool_str_arg(plan, "target_member_id", "member_id")
        or _tool_str_arg(plan, "target_member_name", "display_name", "member_name")
        or _extract_edit_member_target(message, context)
    )
    if not skill_lookup:
        result = {
            "status": "blocked",
            "reason": "missing_skill",
            "detail": "Skill was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_tool_reply(
            "assign_skill_to_member",
            "没有识别到要分配哪个 Skill。",
            "Clara，请把 test-engineering 分配给 Alex。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="assign_skill_to_member",
            reply=reply,
            result=result,
            completed=False,
        )
    if not target_id:
        result = {
            "status": "blocked",
            "reason": "missing_target_member",
            "detail": "Target member was not found in the request.",
            "plan": _plan_trace_data(plan),
        }
        reply = _build_blocked_tool_reply(
            "assign_skill_to_member",
            "没有识别到要分配给哪个成员。",
            "Clara，请把 test-engineering 分配给 Alex。",
        )
        return _persist_local_tool_response(
            context,
            tool_name="assign_skill_to_member",
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
            "deep_links": {"skills": "#/skills"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到 Skill {skill_lookup}，所以没有分配。\n\n"
            "你可以先让我列出所有 Skills，或先创建这个 Skill。\n"
            "- Skills: #/skills"
        )
        return _persist_local_tool_response(
            context,
            tool_name="assign_skill_to_member",
            reply=reply,
            result=result,
            completed=False,
        )

    found = _find_member_profile(target_id)
    if not found:
        result = {
            "status": "blocked",
            "reason": "member_not_found",
            "detail": f"Member not found: {target_id}",
            "deep_links": {"members": "#/members"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到成员 {target_id}，所以没有分配 Skill。\n\n"
            "你可以先让我列出所有成员。\n"
            "- Members: #/members"
        )
        return _persist_local_tool_response(
            context,
            tool_name="assign_skill_to_member",
            reply=reply,
            result=result,
            completed=False,
        )

    profile_path, profile = found
    current_skills = [str(item) for item in profile.get("skills", [])]
    profile["skills"] = _dedupe([*current_skills, skill.id])
    profile["updated_at"] = _now()
    _write_yaml(profile_path, profile)
    member = _member_summary(profile)

    result = {
        "status": "completed",
        "detail": f"Assigned skill {skill.id} to member {member.id}",
        "skill": skill.model_dump(),
        "member": member.model_dump(),
        "saved_path": str(profile_path.relative_to(_workspace_root())),
        "deep_links": {
            "skill": f"#/skills/{skill.id}",
            "member": f"#/members/{member.id}",
            "skills": "#/skills",
            "members": "#/members",
        },
        "plan": _plan_trace_data(plan),
    }
    reply = (
        f"已把 Skill {skill.title} 分配给 {member.display_name}。\n\n"
        f"- Skill: {skill.id}\n"
        f"- Member: {member.display_name} ({member.id})\n"
        f"- Member skills: {', '.join(member.skills) if member.skills else 'none'}\n"
        f"- Profile: {result['saved_path']}\n"
        f"- 查看 Skill：#/skills/{skill.id}\n"
        f"- 查看 Member：#/members/{member.id}"
    )
    return _persist_local_tool_response(
        context,
        tool_name="assign_skill_to_member",
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
            "deep_links": {"skills": "#/skills"},
            "plan": _plan_trace_data(plan),
        }
        reply = (
            f"没有找到 Skill {skill_lookup}，所以没有删除任何文件。\n\n"
            "你可以先让我列出所有 Skills。\n"
            "- Skills: #/skills"
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
    unassigned_members: list[str] = []
    members_dir = _members_dir()
    if members_dir.exists():
        for profile_path in sorted(members_dir.glob("*.yaml")):
            profile = _read_yaml(profile_path)
            current_skills = [str(item) for item in profile.get("skills", [])]
            next_skills = [item for item in current_skills if item != skill.id]
            if len(next_skills) == len(current_skills):
                continue
            profile["skills"] = next_skills
            profile["updated_at"] = _now()
            _write_yaml(profile_path, profile)
            unassigned_members.append(str(profile.get("id") or profile_path.stem))

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
        "unassigned_members": unassigned_members,
        "retained_evidence": ["conversations", "traces"],
        "deep_links": {"skills": "#/skills", "members": "#/members"},
        "plan": _plan_trace_data(plan),
    }
    unassigned_text = ", ".join(unassigned_members) if unassigned_members else "none"
    reply = (
        f"已删除 Skill {skill.title}。\n\n"
        f"- ID: {skill.id}\n"
        f"- Deleted: {relative_skill_dir}\n"
        f"- 已从成员移除：{unassigned_text}\n"
        "- 历史 conversation 和 trace 已保留，用于审计。\n"
        "- Skills: #/skills"
    )
    return _persist_local_tool_response(
        context,
        tool_name="delete_skill",
        reply=reply,
        result=result,
        completed=True,
    )


def _select_member(
    profiles: list[dict[str, Any]],
    *,
    requested_member_id: str | None,
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

    if requested_member_id:
        key = requested_member_id.lower()
        if key in by_id:
            return by_id[key]
        raise HTTPException(status_code=404, detail=f"Member not found: {requested_member_id}")

    return by_id.get("clara") or profiles[0]


def _extract_jira_keys(message: str, explicit: str | None) -> list[str]:
    keys: list[str] = []
    if explicit:
        keys.append(explicit.strip().upper())
    keys.extend(match.upper() for match in _JIRA_KEY_RE.findall(message))
    return sorted(set(filter(None, keys)))


def _ensure_runtime_dirs() -> dict[str, Path]:
    base = _workspace_dir()
    paths = {
        "conversations": base / "conversations",
        "traces": base / "traces",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def _provider_thread_id(member_id: str, thread_id: str) -> str:
    path = _workspace_dir() / "provider_threads.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        mapping = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        mapping = {}

    key = f"{member_id}::{thread_id}"
    if key not in mapping:
        mapping[key] = f"provider-{member_id}-{thread_id[:8]}"
        path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return str(mapping[key])


def _load_provider_threads() -> tuple[Path, dict[str, Any]]:
    path = _workspace_dir() / "provider_threads.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mapping = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        mapping = {}
    return path, mapping if isinstance(mapping, dict) else {}


def _provider_thread_state(member_id: str, thread_id: str) -> dict[str, Any]:
    path, mapping = _load_provider_threads()
    key = f"{member_id}::{thread_id}"
    existing = mapping.get(key)
    if isinstance(existing, dict):
        return existing
    if isinstance(existing, str):
        return {"provider": "file_stub", "provider_thread_id": existing}

    state = {
        "provider": "file_stub",
        "provider_thread_id": f"provider-{member_id}-{thread_id[:8]}",
    }
    mapping[key] = state["provider_thread_id"]
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
    return state


def _save_provider_thread_state(member_id: str, thread_id: str, state: dict[str, Any]) -> None:
    path, mapping = _load_provider_threads()
    mapping[f"{member_id}::{thread_id}"] = state
    path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")


def _delete_provider_thread_states(member_id: str) -> list[str]:
    path, mapping = _load_provider_threads()
    removed_keys = [key for key in mapping if key.startswith(f"{member_id}::")]
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


def _assigned_members_for_skill(skill_id: str) -> list[str]:
    assigned: list[str] = []
    for profile in _load_members():
        member = _member_summary(profile)
        if skill_id in member.skills:
            assigned.append(member.id)
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
        assigned_members=_assigned_members_for_skill(skill_id),
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


def _memory_context(member_id: str) -> list[str]:
    memories_dir = _workspace_dir() / "memories"
    if not memories_dir.exists():
        return []

    snippets: list[str] = []
    for path in sorted(memories_dir.rglob("*.md"))[:5]:
        try:
            first_line = next(
                (line.strip("# ").strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()),
                path.stem,
            )
        except OSError:
            first_line = path.stem
        snippets.append(f"{member_id}:{path.relative_to(memories_dir)}:{first_line}")
    return snippets


def _openai_enabled() -> bool:
    return _model_provider() == "openai"


def _model_provider() -> str:
    return str(_runtime_config()["provider"])


def _openai_model() -> str:
    return str(_runtime_config()["openai_model"])


def _openai_max_output_tokens() -> int:
    raw_value = os.environ.get("AITEAMOS_OPENAI_MAX_OUTPUT_TOKENS", "700")
    try:
        return max(64, min(int(raw_value), 4096))
    except ValueError:
        return 700


def _openai_fallback_on_error() -> bool:
    return _runtime_fallback_on_error()


def _deepseek_enabled() -> bool:
    return _model_provider() == "deepseek"


def _deepseek_model() -> str:
    return str(_runtime_config()["deepseek_model"])


def _deepseek_max_tokens() -> int:
    raw_value = os.environ.get("AITEAMOS_DEEPSEEK_MAX_TOKENS", "700")
    try:
        return max(64, min(int(raw_value), 4096))
    except ValueError:
        return 700


def _deepseek_thinking_type() -> str:
    return str(_runtime_config()["deepseek_thinking"])


def _runtime_fallback_on_error() -> bool:
    return bool(_runtime_config()["fallback_on_error"])


def _runtime_context_gate(
    *,
    member_profile: dict[str, Any],
    member: ChatMemberSummary,
    jira_keys: list[str],
    skills: list[str],
    memory_snippets: list[str],
) -> str:
    responsibilities = member_profile.get("responsibilities", [])
    handoff_rules = member_profile.get("handoff_rules", [])
    personality = str(member_profile.get("personality", ""))
    jira_text = ", ".join(jira_keys) if jira_keys else "none"
    memory_text = "\n".join(f"- {item}" for item in memory_snippets) or "- none"
    skill_text = ", ".join(skills) if skills else "none"
    responsibilities_text = "\n".join(f"- {item}" for item in responsibilities) or "- none"
    handoff_text = "\n".join(f"- {item}" for item in handoff_rules) or "- none"

    return (
        "You are an AI Member inside AITeamOS. Answer as the addressed member, "
        "not as a generic assistant. Be concise, truthful, and explicit about what "
        "you can and cannot do in this P0 runtime.\n\n"
        f"Member id: {member.id}\n"
        f"Display name: {member.display_name}\n"
        f"Role: {member.role}\n"
        f"Summary: {member.summary}\n"
        f"Personality: {personality}\n"
        f"Responsibilities:\n{responsibilities_text}\n\n"
        f"Skills available through AITeamOS context gate: {skill_text}\n"
        f"Jira keys bound to this turn: {jira_text}\n"
        f"Local memory snippets:\n{memory_text}\n\n"
        f"Handoff rules:\n{handoff_text}\n\n"
        "AITeamOS currently gates your profile, skills, memory, Jira context, "
        "permissions, and trace capture before sending this turn to the provider. "
        "Do not claim that Jira, Harness, repository edits, or external tools were "
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


async def _call_openai_agent(
    *,
    member_profile: dict[str, Any],
    member: ChatMemberSummary,
    message: str,
    jira_keys: list[str],
    skills: list[str],
    memory_snippets: list[str],
    provider_state: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    api_key = _runtime_secrets()["openai_api_key"]
    if not _openai_enabled() or not api_key:
        raise RuntimeError("OpenAI runtime is not enabled")

    request_body: dict[str, Any] = {
        "model": _openai_model(),
        "instructions": _runtime_context_gate(
            member_profile=member_profile,
            member=member,
            jira_keys=jira_keys,
            skills=skills,
            memory_snippets=memory_snippets,
        ),
        "input": [{"role": "user", "content": message}],
        "store": True,
        "max_output_tokens": _openai_max_output_tokens(),
    }
    previous_response_id = provider_state.get("openai_previous_response_id")
    if isinstance(previous_response_id, str) and previous_response_id:
        request_body["previous_response_id"] = previous_response_id

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI runtime failed: {response.status_code} {response.text[:500]}",
        )

    payload = response.json()
    reply = _extract_openai_text(payload)
    if not reply:
        raise HTTPException(status_code=502, detail="OpenAI runtime returned no text output")

    response_id = payload.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise HTTPException(status_code=502, detail="OpenAI runtime returned no response id")

    next_state = {
        **provider_state,
        "provider": "openai_responses",
        "provider_thread_id": provider_state.get("provider_thread_id")
        or f"openai-{member.id}-{uuid4().hex[:8]}",
        "openai_previous_response_id": response_id,
        "model": payload.get("model") or _openai_model(),
        "last_response_id": response_id,
        "updated_at": _now(),
    }
    metadata = {
        "provider": "openai_responses",
        "model": next_state["model"],
        "response_id": response_id,
        "previous_response_id": previous_response_id,
        "usage": payload.get("usage"),
    }
    return reply, next_state, metadata


async def _call_deepseek_agent(
    *,
    member_profile: dict[str, Any],
    member: ChatMemberSummary,
    message: str,
    jira_keys: list[str],
    skills: list[str],
    memory_snippets: list[str],
    provider_state: dict[str, Any],
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    api_key = _runtime_secrets()["deepseek_api_key"]
    if not _deepseek_enabled() or not api_key:
        raise RuntimeError("DeepSeek runtime is not enabled")

    request_body: dict[str, Any] = {
        "model": _deepseek_model(),
        "messages": [
            {
                "role": "system",
                "content": _runtime_context_gate(
                    member_profile=member_profile,
                    member=member,
                    jira_keys=jira_keys,
                    skills=skills,
                    memory_snippets=memory_snippets,
                ),
            },
            {"role": "user", "content": message},
        ],
        "stream": False,
        "max_tokens": _deepseek_max_tokens(),
        "thinking": {"type": _deepseek_thinking_type()},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"DeepSeek runtime failed: {response.status_code} {response.text[:500]}",
        )

    payload = response.json()
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise HTTPException(status_code=502, detail="DeepSeek runtime returned no choices")
    message_payload = choices[0].get("message") if isinstance(choices[0], dict) else None
    reply = message_payload.get("content") if isinstance(message_payload, dict) else None
    if not isinstance(reply, str) or not reply.strip():
        raise HTTPException(status_code=502, detail="DeepSeek runtime returned no text output")

    response_id = payload.get("id")
    if not isinstance(response_id, str) or not response_id:
        response_id = f"deepseek-{uuid4().hex[:12]}"

    next_state = {
        **provider_state,
        "provider": "deepseek_chat_completions",
        "provider_thread_id": provider_state.get("provider_thread_id")
        or f"deepseek-{member.id}-{uuid4().hex[:8]}",
        "assumed_agent_session": True,
        "deepseek_last_response_id": response_id,
        "model": payload.get("model") or _deepseek_model(),
        "updated_at": _now(),
    }
    metadata = {
        "provider": "deepseek_chat_completions",
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
    api_key = _runtime_secrets()["deepseek_api_key"]
    if not _deepseek_enabled() or not api_key:
        raise RuntimeError("DeepSeek runtime is not enabled")

    request_body: dict[str, Any] = {
        "model": _deepseek_model(),
        "messages": [
            {
                "role": "system",
                "content": _runtime_context_gate(
                    member_profile=context.selected_profile,
                    member=context.member,
                    jira_keys=context.jira_keys,
                    skills=context.skills,
                    memory_snippets=context.memories,
                ),
            },
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
            "https://api.deepseek.com/chat/completions",
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
                    detail=f"DeepSeek runtime failed: {response.status_code} {error_text.decode('utf-8')[:500]}",
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
        raise HTTPException(status_code=502, detail="DeepSeek runtime returned no text output")

    provider_state = {
        **context.provider_state,
        "provider": "deepseek_chat_completions",
        "provider_thread_id": context.provider_state.get("provider_thread_id")
        or f"deepseek-{context.member.id}-{uuid4().hex[:8]}",
        "assumed_agent_session": True,
        "deepseek_last_response_id": response_id,
        "model": model,
        "updated_at": _now(),
    }
    metadata = {
        "provider": "deepseek_chat_completions",
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
        provider_state=provider_state,
        provider_thread_id=str(provider_state["provider_thread_id"]),
        extra_trace_events=[
            ChatTraceEvent(
                event="runtime.deepseek.stream_completed",
                detail="Generated streaming response through DeepSeek Chat Completions API.",
                data=metadata,
            )
        ],
    )
    yield "final", final_response.model_dump()


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _build_reply(
    *,
    member: ChatMemberSummary,
    message: str,
    jira_keys: list[str],
    provider_thread_id: str,
    skills: list[str],
    memory_snippets: list[str],
) -> str:
    jira_text = ", ".join(jira_keys) if jira_keys else "not bound"
    skill_text = ", ".join(skills[:4]) if skills else "no local skills loaded"
    memory_text = f"{len(memory_snippets)} local memory snippet(s)" if memory_snippets else "no local memory snippets"

    return (
        f"{member.display_name} received the request.\n\n"
        f"Role: {member.role}\n"
        f"Jira: {jira_text}\n"
        f"Runtime: {member.runtime_mode}; provider thread: {provider_thread_id}\n"
        f"Context gate: {skill_text}; {memory_text}\n\n"
        "P0 file-backed run completed: I loaded the addressed member profile, "
        "resolved the reusable provider thread mapping, captured the conversation, "
        "and wrote a local trace. External Jira, harness, and provider execution are "
        "not invoked in this first slice.\n\n"
        "Next action preview: read the Jira context, pick the relevant skills and "
        "memory, execute through the configured external or local agent runtime, "
        "and report progress back into this thread with trace evidence."
    )


def _prepare_chat_run(request: ChatMessageRequest) -> ChatRunContext:
    profiles = _load_members()
    selected = _select_member(
        profiles,
        requested_member_id=request.target_member_id,
        message=request.message,
    )
    member = _member_summary(selected)

    thread_id = request.thread_id or f"thread-{uuid4().hex[:12]}"
    thread_id = _require_safe_id(thread_id, field="thread_id")
    run_id = f"run-{uuid4().hex[:12]}"
    jira_keys = _extract_jira_keys(request.message, request.jira_key)
    runtime_dirs = _ensure_runtime_dirs()
    provider_state = _provider_thread_state(member.id, thread_id)
    provider_thread_id = str(provider_state.get("provider_thread_id") or _provider_thread_id(member.id, thread_id))
    skills = _skill_titles(member.skills)
    memories = _memory_context(member.id)

    trace_events = [
        ChatTraceEvent(event="message.received", detail="User message accepted."),
        ChatTraceEvent(
            event="member.selected",
            detail=f"Routed to {member.display_name}.",
            data={"member_id": member.id, "role": member.role},
        ),
        ChatTraceEvent(
            event="context.loaded",
            detail="Loaded file-backed member, skill, and memory context.",
            data={"skills": skills, "memory_count": len(memories)},
        ),
        ChatTraceEvent(
            event="provider_thread.resolved",
            detail="Resolved stable external provider thread mapping.",
            data={
                "provider": provider_state.get("provider", "file_stub"),
                "provider_thread_id": provider_thread_id,
            },
        ),
    ]
    if jira_keys:
        trace_events.append(
            ChatTraceEvent(
                event="jira.detected",
                detail="Detected Jira key(s) in the request.",
                data={"jira_keys": jira_keys},
            )
        )

    return ChatRunContext(
        request=request,
        selected_profile=selected,
        member=member,
        thread_id=thread_id,
        run_id=run_id,
        jira_keys=jira_keys,
        runtime_dirs=runtime_dirs,
        provider_state=provider_state,
        provider_thread_id=provider_thread_id,
        skills=skills,
        memories=memories,
        trace_events=trace_events,
    )


def _persist_chat_response(
    context: ChatRunContext,
    *,
    reply: str,
    provider_state: dict[str, Any] | None = None,
    provider_thread_id: str | None = None,
    extra_trace_events: list[ChatTraceEvent] | None = None,
) -> ChatMessageResponse:
    if provider_state is not None:
        _save_provider_thread_state(context.member.id, context.thread_id, provider_state)
    final_provider_thread_id = provider_thread_id or context.provider_thread_id

    trace_events = [
        *context.trace_events,
        *(extra_trace_events or []),
        ChatTraceEvent(event="response.created", detail="Assistant response was created."),
    ]

    conversation_path = context.runtime_dirs["conversations"] / f"{context.thread_id}.jsonl"
    trace_path = context.runtime_dirs["traces"] / f"{context.run_id}.jsonl"

    _append_jsonl(conversation_path, {
        "timestamp": _now(),
        "role": "user",
        "content": context.request.message,
        "member_id": None,
        "run_id": context.run_id,
    })
    _append_jsonl(conversation_path, {
        "timestamp": _now(),
        "role": "assistant",
        "content": reply,
        "member_id": context.member.id,
        "run_id": context.run_id,
    })

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
        target_member=context.member,
        provider_thread_id=final_provider_thread_id,
        jira_keys=context.jira_keys,
        reply=reply,
        trace_events=trace_events,
        saved_paths={
            "conversation": str(conversation_path.relative_to(_workspace_root())),
            "trace": str(trace_path.relative_to(_workspace_root())),
            "provider_threads": str((_workspace_dir() / "provider_threads.json").relative_to(_workspace_root())),
        },
    )


def _stub_reply(context: ChatRunContext) -> str:
    return _build_reply(
        member=context.member,
        message=context.request.message,
        jira_keys=context.jira_keys,
        provider_thread_id=context.provider_thread_id,
        skills=context.skills,
        memory_snippets=context.memories,
    )


async def _maybe_complete_local_tool(context: ChatRunContext) -> ChatMessageResponse | None:
    plan = await _plan_local_tool_intent(context)
    if plan.tool == "create_member":
        return _complete_create_member_tool(context, plan)
    if plan.tool == "edit_member_profile":
        return _complete_edit_member_profile_tool(context, plan)
    if plan.tool == "delete_member":
        return _complete_delete_member_tool(context, plan)
    if plan.tool == "create_skill":
        return _complete_create_skill_tool(context, plan)
    if plan.tool == "assign_skill_to_member":
        return _complete_assign_skill_to_member_tool(context, plan)
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
                        "requested_by": context.member.id,
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
    if plan.tool != "list_members":
        return None

    tool_result = _list_members_tool_result()
    tool_result["plan"] = _plan_trace_data(plan)
    reply = _build_list_members_reply(tool_result)
    return _persist_chat_response(
        context,
        reply=reply,
        extra_trace_events=[
            ChatTraceEvent(
                event="tool.list_members.called",
                detail="Resolved list_members as a local file-backed tool.",
                data={
                    "requested_by": context.member.id,
                    "tool": "list_members",
                },
            ),
            ChatTraceEvent(
                event="tool.list_members.completed",
                detail="Loaded local member profiles.",
                data=tool_result,
            ),
        ],
    )


@router.get("/members", response_model=list[ChatMemberSummary])
async def list_chat_members() -> list[ChatMemberSummary]:
    return [_member_summary(profile) for profile in _load_members()]


@router.get("/skills", response_model=list[ChatSkillSummary])
async def list_chat_skills() -> list[ChatSkillSummary]:
    return sorted(_load_skills(), key=lambda skill: skill.id)


@router.get("/runtime", response_model=ChatRuntimeSettings)
async def get_chat_runtime() -> ChatRuntimeSettings:
    return _runtime_settings_response()


@router.put("/runtime", response_model=ChatRuntimeSettings)
async def update_chat_runtime(request: ChatRuntimeSettingsRequest) -> ChatRuntimeSettings:
    runtime_config = {
        "provider": _normalize_provider(request.provider),
        "deepseek_model": request.deepseek_model.strip() or "deepseek-v4-flash",
        "deepseek_thinking": _normalize_thinking(request.deepseek_thinking),
        "openai_model": request.openai_model.strip() or "gpt-5-nano",
        "fallback_on_error": request.fallback_on_error,
        "updated_at": _now(),
    }
    _write_json_file(_runtime_settings_path(), runtime_config)

    secrets = _read_json_file(_secrets_path())
    if request.deepseek_api_key is not None and request.deepseek_api_key.strip():
        secrets["deepseek_api_key"] = request.deepseek_api_key.strip()
    if request.openai_api_key is not None and request.openai_api_key.strip():
        secrets["openai_api_key"] = request.openai_api_key.strip()
    if secrets:
        _write_json_file(_secrets_path(), secrets)

    return _runtime_settings_response()


@router.get("/threads/{thread_id}", response_model=ConversationResponse)
async def get_chat_thread(thread_id: str) -> ConversationResponse:
    thread_id = _require_safe_id(thread_id, field="thread_id")
    path = _workspace_dir() / "conversations" / f"{thread_id}.jsonl"
    messages: list[ConversationMessage] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            messages.append(ConversationMessage.model_validate_json(line))
    return ConversationResponse(thread_id=thread_id, messages=messages)


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
            target_member_id=state.get("target_member_id"),
            thread_id=thread_id,
            jira_key=state.get("jira_key"),
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


def _build_agui_chat_agent() -> LangGraphAgent:
    builder = StateGraph(AiteamosChatGraphState)
    builder.add_node("aiteamos_chat", _run_aiteamos_chat_graph_node)
    builder.add_edge(START, "aiteamos_chat")
    builder.add_edge("aiteamos_chat", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    return LangGraphAgent(
        name="AITeamOS Clara",
        description="AG-UI/LangGraph runtime for the file-backed AITeamOS Chat Workbench.",
        graph=graph,
    )


def _get_agui_chat_agent() -> LangGraphAgent:
    global _agui_chat_agent
    if _agui_chat_agent is None:
        _agui_chat_agent = _build_agui_chat_agent()
    return _agui_chat_agent


def _enrich_agui_input(input_data: RunAgentInput, request: Request) -> RunAgentInput:
    state = input_data.state if isinstance(input_data.state, dict) else {}
    next_state: dict[str, Any] = dict(state)
    forwarded_props = input_data.forwarded_props if isinstance(input_data.forwarded_props, dict) else {}

    target_member_id = (
        request.query_params.get("target_member_id")
        or request.headers.get("X-AITeamOS-Target-Member-Id")
        or forwarded_props.get("target_member_id")
    )
    jira_key = (
        request.query_params.get("jira_key")
        or request.headers.get("X-AITeamOS-Jira-Key")
        or forwarded_props.get("jira_key")
    )

    if target_member_id:
        next_state["target_member_id"] = str(target_member_id)
    if jira_key:
        next_state["jira_key"] = str(jira_key)

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
    return {"status": "ok", "agent": {"name": agent.name}}


@router.post("/messages", response_model=ChatMessageResponse)
async def send_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    context = _prepare_chat_run(request)
    local_tool_response = await _maybe_complete_local_tool(context)
    if local_tool_response is not None:
        return local_tool_response

    runtime_provider = _model_provider()
    try:
        if runtime_provider == "deepseek":
            reply, provider_state, runtime_metadata = await _call_deepseek_agent(
                member_profile=context.selected_profile,
                member=context.member,
                message=context.request.message,
                jira_keys=context.jira_keys,
                skills=context.skills,
                memory_snippets=context.memories,
                provider_state=context.provider_state,
            )
            completed_event = ChatTraceEvent(
                event="runtime.deepseek.completed",
                detail="Generated response through DeepSeek Chat Completions API.",
                data=runtime_metadata,
            )
        elif runtime_provider == "openai" or _openai_enabled():
            reply, provider_state, runtime_metadata = await _call_openai_agent(
                member_profile=context.selected_profile,
                member=context.member,
                message=context.request.message,
                jira_keys=context.jira_keys,
                skills=context.skills,
                memory_snippets=context.memories,
                provider_state=context.provider_state,
            )
            completed_event = ChatTraceEvent(
                event="runtime.openai.completed",
                detail="Generated response through OpenAI Responses API.",
                data=runtime_metadata,
            )
        else:
            raise RuntimeError("No remote runtime provider configured")

        return _persist_chat_response(
            context,
            reply=reply,
            provider_state=provider_state,
            provider_thread_id=str(provider_state["provider_thread_id"]),
            extra_trace_events=[completed_event],
        )
    except RuntimeError:
        return _persist_chat_response(
            context,
            reply=_stub_reply(context),
            extra_trace_events=[
                ChatTraceEvent(event="runtime.stub.completed", detail="Generated P0 file-backed response.")
            ],
        )
    except HTTPException as exc:
        if not _runtime_fallback_on_error():
            raise
        return _persist_chat_response(
            context,
            reply=_stub_reply(context),
            extra_trace_events=[
                ChatTraceEvent(
                    event="runtime.remote.failed",
                    detail="Remote runtime failed; fell back to file-backed response.",
                    data={"status_code": exc.status_code, "detail": str(exc.detail)[:500]},
                ),
                ChatTraceEvent(event="runtime.stub.completed", detail="Generated P0 file-backed response."),
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


def _latest_agui_user_message_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        payload = _agui_message_payload(message)
        if payload.get("role") == "user":
            return _message_content_to_text(payload.get("content"))
    return ""


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
        if _model_provider() == "deepseek" and _runtime_secrets()["deepseek_api_key"]:
            async for event, payload in _stream_deepseek_agent(context):
                yield event, payload
            return

    if _model_provider() == "deepseek" and _runtime_secrets()["deepseek_api_key"]:
        context = _prepare_chat_run(request)
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
                target_member_id=state.get("target_member_id"),
                thread_id=thread_id,
                jira_key=state.get("jira_key"),
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
                    if _model_provider() == "deepseek" and _runtime_secrets()["deepseek_api_key"]:
                        yield _sse_payload(
                            "start",
                            {
                                "thread_id": context.thread_id,
                                "run_id": context.run_id,
                                "target_member": context.member.model_dump(),
                                "provider_thread_id": context.provider_thread_id,
                                "jira_keys": context.jira_keys,
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
                            "target_member": response.target_member.model_dump(),
                            "provider_thread_id": response.provider_thread_id,
                            "jira_keys": response.jira_keys,
                        },
                    )
                    for chunk in _reply_chunks(response.reply):
                        yield _sse_payload("delta", {"text": chunk})
                        await asyncio.sleep(0)
                    yield _sse_payload("final", response.model_dump())
                    return

            if _model_provider() == "deepseek" and _runtime_secrets()["deepseek_api_key"]:
                context = _prepare_chat_run(request)
                yield _sse_payload(
                    "start",
                    {
                        "thread_id": context.thread_id,
                        "run_id": context.run_id,
                        "target_member": context.member.model_dump(),
                        "provider_thread_id": context.provider_thread_id,
                        "jira_keys": context.jira_keys,
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
                    "target_member": response.target_member.model_dump(),
                    "provider_thread_id": response.provider_thread_id,
                    "jira_keys": response.jira_keys,
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
