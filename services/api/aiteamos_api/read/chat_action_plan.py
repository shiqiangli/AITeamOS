"""Chat action and Kernel command plan normalization helpers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .capability_service import local_kernel_command_ids
from .chat_kernel_catalog import CHAT_ACTION_TO_COMMAND_ID, COMMAND_ID_TO_CHAT_ACTION


class ChatKernelCommandPlan(BaseModel):
    command: str = "none"
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    source: str = "heuristic"


class ChatActionPlan(BaseModel):
    action: str = "answer_only"
    arguments: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    source: str = "heuristic"


def _bounded_confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def normalize_chat_action_plan(payload: dict[str, Any], *, source: str) -> ChatActionPlan:
    raw_action = str(
        payload.get("action")
        or payload.get("chat_action")
        or payload.get("intent")
        or payload.get("type")
        or payload.get("command")
        or "answer_only"
    ).strip().lower()
    action_aliases = {
        "none": "answer_only",
        "answer": "answer_only",
        "answer-only": "answer_only",
        "respond": "answer_only",
        "list_employees": "list_employees",
        "employees.manage:list": "list_employees",
        "create_employee": "create_employee",
        "create_ai_employee": "create_employee",
        "add_employee": "create_employee",
        "new_employee": "create_employee",
        "employees.manage:create": "create_employee",
        "edit_employee": "edit_employee_profile",
        "edit_employee_profile": "edit_employee_profile",
        "update_employee": "edit_employee_profile",
        "update_employee_profile": "edit_employee_profile",
        "employees.manage:update": "edit_employee_profile",
        "delete_employee": "delete_employee",
        "remove_employee": "delete_employee",
        "delete_ai_employee": "delete_employee",
        "employees.manage:delete": "delete_employee",
        "list_skills": "list_skills",
        "assets.manage:list_skills": "list_skills",
        "create_skill": "create_skill",
        "new_skill": "create_skill",
        "assets.manage:create_skill": "create_skill",
        "assign_skill": "assign_skill_to_employee",
        "assign_skill_to_employee": "assign_skill_to_employee",
        "attach_skill": "assign_skill_to_employee",
        "assets.manage:assign_skill": "assign_skill_to_employee",
        "delete_skill": "delete_skill",
        "remove_skill": "delete_skill",
        "assets.manage:delete_skill": "delete_skill",
        "inspect_permissions": "inspect_permissions",
        "permissions_inspect": "inspect_permissions",
        "kernel.permissions:inspect": "inspect_permissions",
        "create": "create_ticket",
        "create_ticket": "create_ticket",
        "open_ticket": "create_ticket",
        "tickets.manage:create": "create_ticket",
        "implement_ticket": "implement_ticket",
        "implementation": "implement_ticket",
        "repo_mutation": "implement_ticket",
        "repo_write": "implement_ticket",
        "repository_write": "implement_ticket",
        "code_edit": "implement_ticket",
        "code_change": "implement_ticket",
        "apply_patch": "implement_ticket",
        "runtime.external:repo_mutation": "implement_ticket",
        "report": "append_report",
        "append_report": "append_report",
        "record_ticket_report": "append_report",
        "add_ticket_report": "append_report",
        "tickets.manage:report": "append_report",
        "record_validation": "record_validation",
        "validation": "record_validation",
        "validation_passed": "record_validation",
        "record_failure": "record_failure",
        "record_validation_failure": "record_failure",
        "validation_failed": "record_failure",
        "validation_rejected": "record_failure",
        "validation_request": "request_validation",
        "request_validation": "request_validation",
        "request_ticket_validation": "request_validation",
        "ask_validation": "request_validation",
        "ask_pv": "request_validation",
        "tickets.manage:request_validation": "request_validation",
        "human_review": "request_human_review",
        "request_human_review": "request_human_review",
        "request_human": "request_human_review",
        "ask_human_review": "request_human_review",
        "human_review_request": "request_human_review",
        "tickets.manage:request_human_review": "request_human_review",
        "self_bootstrap": "self_bootstrap_summary",
        "self_bootstrap_close": "self_bootstrap_close",
        "self_bootstrap_complete": "self_bootstrap_close",
        "self_bootstrap_closure": "self_bootstrap_close",
        "self_bootstrap_start": "self_bootstrap_start",
        "start_self_bootstrap": "self_bootstrap_start",
        "bootstrap_start": "self_bootstrap_start",
        "tickets.manage:self_bootstrap_close": "self_bootstrap_close",
        "tickets.manage:self_bootstrap_start": "self_bootstrap_start",
        "self_bootstrap_summary": "self_bootstrap_summary",
        "bootstrap_summary": "self_bootstrap_summary",
        "learning_summary": "self_bootstrap_summary",
        "tickets.manage:self_bootstrap_summary": "self_bootstrap_summary",
        "terminal_run": "terminal_run",
        "run_terminal": "terminal_run",
        "run_command": "terminal_run",
        "terminal.run:run": "terminal_run",
    }
    action = action_aliases.get(raw_action, raw_action)
    if action not in CHAT_ACTION_TO_COMMAND_ID:
        action = "answer_only"

    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    return ChatActionPlan(
        action=action,
        arguments=arguments,
        confidence=_bounded_confidence(payload.get("confidence", 0)),
        reason=str(payload.get("reason") or ""),
        source=source,
    )


def chat_action_plan_from_kernel_plan(plan: ChatKernelCommandPlan) -> ChatActionPlan:
    payload = plan.model_dump()
    payload["action"] = COMMAND_ID_TO_CHAT_ACTION.get(plan.command, "answer_only")
    return normalize_chat_action_plan(payload, source=plan.source)


def kernel_plan_from_chat_action_plan(plan: ChatActionPlan) -> ChatKernelCommandPlan:
    arguments = dict(plan.arguments)
    if plan.action == "record_validation":
        arguments.setdefault("report_type", "validation")
    elif plan.action == "record_failure":
        arguments.setdefault("report_type", "validation_failed")
    return ChatKernelCommandPlan(
        command=CHAT_ACTION_TO_COMMAND_ID.get(plan.action, "none"),
        arguments=arguments,
        confidence=plan.confidence,
        reason=plan.reason,
        source=plan.source,
    )


def normalize_kernel_command_plan(payload: dict[str, Any], *, source: str) -> ChatKernelCommandPlan:
    raw_command = str(payload.get("command") or "none").strip().lower()
    command_aliases = {
        "list_employee": "employees.manage:list",
        "list_employees": "employees.manage:list",
        "list_ai_employees": "employees.manage:list",
        "create_employee": "employees.manage:create",
        "create_ai_employee": "employees.manage:create",
        "add_employee": "employees.manage:create",
        "new_employee": "employees.manage:create",
        "edit_employee_profile": "employees.manage:update",
        "edit_employee": "employees.manage:update",
        "update_employee": "employees.manage:update",
        "update_employee_profile": "employees.manage:update",
        "delete_employee": "employees.manage:delete",
        "remove_employee": "employees.manage:delete",
        "delete_ai_employee": "employees.manage:delete",
        "delete_user": "employees.manage:delete",
        "list_skill": "assets.manage:list_skills",
        "list_skills": "assets.manage:list_skills",
        "show_skills": "assets.manage:list_skills",
        "create_skill": "assets.manage:create_skill",
        "create_agent_skill": "assets.manage:create_skill",
        "new_skill": "assets.manage:create_skill",
        "add_skill": "assets.manage:create_skill",
        "assign_skill_to_employee": "assets.manage:assign_skill",
        "assign_skill": "assets.manage:assign_skill",
        "attach_skill": "assets.manage:assign_skill",
        "add_skill_to_employee": "assets.manage:assign_skill",
        "delete_skill": "assets.manage:delete_skill",
        "remove_skill": "assets.manage:delete_skill",
        "drop_skill": "assets.manage:delete_skill",
        "search_knowledge": "knowledge.search:search",
        "query_knowledge": "knowledge.search:search",
        "read_docs": "knowledge.search:search",
        "search_docs": "knowledge.search:search",
        "create_ticket": "tickets.manage:create",
        "open_ticket": "tickets.manage:create",
        "list_tickets": "tickets.manage:list",
        "record_ticket_report": "tickets.manage:report",
        "add_ticket_report": "tickets.manage:report",
        "complete_ticket": "tickets.manage:report",
        "record_validation": "tickets.manage:report",
        "validation_passed": "tickets.manage:report",
        "record_failure": "tickets.manage:report",
        "validation_failed": "tickets.manage:report",
        "validation_rejected": "tickets.manage:report",
        "request_validation": "tickets.manage:request_validation",
        "validation_request": "tickets.manage:request_validation",
        "request_ticket_validation": "tickets.manage:request_validation",
        "ask_validation": "tickets.manage:request_validation",
        "ask_pv": "tickets.manage:request_validation",
        "human_review": "tickets.manage:request_human_review",
        "request_human_review": "tickets.manage:request_human_review",
        "request_human": "tickets.manage:request_human_review",
        "ask_human_review": "tickets.manage:request_human_review",
        "human_review_request": "tickets.manage:request_human_review",
        "self_bootstrap": "tickets.manage:self_bootstrap_summary",
        "self_bootstrap_close": "tickets.manage:self_bootstrap_close",
        "self_bootstrap_complete": "tickets.manage:self_bootstrap_close",
        "self_bootstrap_closure": "tickets.manage:self_bootstrap_close",
        "self_bootstrap_start": "tickets.manage:self_bootstrap_start",
        "start_self_bootstrap": "tickets.manage:self_bootstrap_start",
        "bootstrap_start": "tickets.manage:self_bootstrap_start",
        "tickets.manage:self_bootstrap_close": "tickets.manage:self_bootstrap_close",
        "tickets.manage:self_bootstrap_start": "tickets.manage:self_bootstrap_start",
        "self_bootstrap_summary": "tickets.manage:self_bootstrap_summary",
        "bootstrap_summary": "tickets.manage:self_bootstrap_summary",
        "learning_summary": "tickets.manage:self_bootstrap_summary",
        "tickets.manage:self_bootstrap_summary": "tickets.manage:self_bootstrap_summary",
        "list_code_repositories": "repositories.list:list",
        "list_repositories": "repositories.list:list",
        "list_repos": "repositories.list:list",
        "list_code_repos": "repositories.list:list",
        "show_repositories": "repositories.list:list",
        "show_code_repositories": "repositories.list:list",
        "inspect_code_repository": "repositories.inspect:inspect",
        "inspect_repository": "repositories.inspect:inspect",
        "inspect_repo": "repositories.inspect:inspect",
        "search_repository": "repositories.inspect:inspect",
        "search_repo": "repositories.inspect:inspect",
        "read_repository": "repositories.inspect:inspect",
        "read_repo": "repositories.inspect:inspect",
        "read_file": "repositories.inspect:inspect",
        "search_code": "repositories.inspect:inspect",
        "terminal_run": "terminal.run:run",
        "run_terminal": "terminal.run:run",
        "run_command": "terminal.run:run",
        "terminal.run:run": "terminal.run:run",
        "inspect_permissions": "kernel.permissions:inspect",
        "list_permissions": "kernel.permissions:inspect",
        "describe_permissions": "kernel.permissions:inspect",
        "permissions_inspect": "kernel.permissions:inspect",
    }
    command = command_aliases.get(raw_command, raw_command)
    if command not in {"none", *local_kernel_command_ids()}:
        command = "none"

    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    return ChatKernelCommandPlan(
        command=command,
        arguments=arguments,
        confidence=_bounded_confidence(payload.get("confidence", 0)),
        reason=str(payload.get("reason") or ""),
        source=source,
    )


def plan_trace_data(plan: ChatKernelCommandPlan | None) -> dict[str, Any]:
    if plan is None:
        return {"source": "unknown", "chat_action_plan": ChatActionPlan().model_dump()}
    data = plan.model_dump()
    if plan.command in COMMAND_ID_TO_CHAT_ACTION:
        data["chat_action_plan"] = chat_action_plan_from_kernel_plan(plan).model_dump()
    return data
