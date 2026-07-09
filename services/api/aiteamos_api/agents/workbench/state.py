"""Shared state and small helpers for the AITeamOS Workbench graph."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.message import add_messages

from aiteamos_api.read.chat_models import ChatMessageResponse


class AITeamOSWorkbenchState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    thread_id: str
    employee_id: str
    selected_employee: dict[str, Any]
    employee_identity: dict[str, Any]
    employee_profiles: list[dict[str, Any]]
    selected_ai_engine: str
    active_ticket: dict[str, Any] | None
    ticket_binding: dict[str, Any]
    ticket_key: str
    ticket_keys: list[str]
    approval_ref: str
    approval_interrupt: dict[str, Any]
    approval_resume: dict[str, Any]
    capability_scope: dict[str, Any]
    governance_summary: dict[str, Any]
    context_bundle: dict[str, Any]
    action_plan: dict[str, Any]
    planning_events: list[dict[str, Any]]
    recent_messages: list[dict[str, Any]]
    linked_assets: list[dict[str, Any]]
    recalled_memory_refs: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    execution_request: dict[str, Any]
    execution_result: dict[str, Any]
    execution_summary: dict[str, Any]
    ticket_evidence_refs: list[dict[str, Any]]
    ticket_report_refs: list[dict[str, Any]]
    ticket_handoff_refs: list[dict[str, Any]]
    ticket_loop_summary: dict[str, Any]
    ticket_loop_policy: dict[str, Any]
    ticket_loop_decision: dict[str, Any]
    ticket_loop_policy_actions: list[dict[str, Any]]
    approval_requests: list[dict[str, Any]]
    approval_records: list[dict[str, Any]]
    handoff_decision: dict[str, Any]
    handoff_summary: dict[str, Any]
    asset_candidates: list[dict[str, Any]]
    asset_proposal_summary: dict[str, Any]
    provenance_events: list[dict[str, Any]]
    provider_blockers: list[dict[str, Any]]
    workbench_panels: dict[str, Any]
    runtime_status: dict[str, Any]
    final_response: str
    aiteamos_chat_response: dict[str, Any]


def configurable(config: RunnableConfig | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    value = config.get("configurable")
    return value if isinstance(value, dict) else {}


def text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def latest_human_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "human":
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(text(item.get("text")))
                    elif isinstance(item, str):
                        parts.append(item)
                return "\n".join(part for part in parts if part).strip()
    return ""


def record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def approval_ref(value: dict[str, Any]) -> str:
    for key in ("approval_ref", "approval_id", "id"):
        value_text = text(value.get(key))
        if value_text:
            return value_text
    return ""


def primary_ticket_id(response: ChatMessageResponse) -> str:
    metadata = response.run_metadata or {}
    execution = record(metadata.get("execution"))
    ticket_binding = record(execution.get("ticket_binding"))
    result = record(execution.get("result"))
    universal_context = record(record(record(metadata.get("scoped_context")).get("universal_context")).get("summary"))
    for value in [
        response.ticket_keys[0] if response.ticket_keys else "",
        ticket_binding.get("ticket_id"),
        result.get("output_ticket_id"),
        universal_context.get("ticket_id"),
    ]:
        value_text = text(value)
        if value_text:
            return value_text
    return ""
