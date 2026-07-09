"""Bootstrap nodes for the AITeamOS Workbench graph."""

from typing import Any

from langchain_core.runnables.config import RunnableConfig

from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState, configurable, record, text


def bootstrap_request(state: AITeamOSWorkbenchState, config: RunnableConfig | None = None) -> dict[str, Any]:
    cfg = configurable(config)
    return {
        "thread_id": text(state.get("thread_id")) or text(cfg.get("thread_id")),
        "employee_id": text(state.get("employee_id")) or text(cfg.get("target_employee_id")) or text(cfg.get("employee_id")),
        "ticket_key": text(state.get("ticket_key")) or text(cfg.get("ticket_key")),
        "approval_ref": text(state.get("approval_ref")) or text(cfg.get("approval_ref")),
        "runtime_status": {
            "executor": "langgraph",
            "graph": "aiteamos_workbench",
            "current_node": "bootstrap_request",
            "status": "running",
        },
    }


def bind_or_create_ticket(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    ticket_key = text(state.get("ticket_key"))
    return {
        "ticket_binding": {
            "mode": "existing" if ticket_key else "none",
            "ticket_id": ticket_key,
            "required": bool(ticket_key),
        },
        "runtime_status": {
            **record(state.get("runtime_status")),
            "current_node": "bind_or_create_ticket",
        },
    }


def execute_read_tools(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    return {
        "runtime_status": {
            **record(state.get("runtime_status")),
            "current_node": "execute_read_tools",
        }
    }
