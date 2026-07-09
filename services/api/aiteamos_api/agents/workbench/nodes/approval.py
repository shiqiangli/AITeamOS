"""Approval interrupt nodes for the AITeamOS Workbench graph."""

from __future__ import annotations

from typing import Any, Literal

from langgraph.types import interrupt

from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState, approval_ref, record, records, text


def approval_status(state: AITeamOSWorkbenchState) -> str:
    runtime_status = record(state.get("runtime_status"))
    response = record(state.get("aiteamos_chat_response"))
    metadata = record(response.get("run_metadata"))
    execution = record(metadata.get("execution"))
    return (
        text(runtime_status.get("status"))
        or text(execution.get("status"))
        or text(metadata.get("status"))
    ).lower()


def should_interrupt_for_approval(state: AITeamOSWorkbenchState) -> bool:
    if text(state.get("approval_ref")):
        return False
    requests = records(state.get("approval_requests"))
    if not requests:
        return False
    return approval_status(state) in {"needs_approval", "waiting_approval", "approval_required"}


def route_after_governance(state: AITeamOSWorkbenchState) -> Literal["approval_interrupt", "dispatch_runtime_executor"]:
    return "approval_interrupt" if should_interrupt_for_approval(state) else "dispatch_runtime_executor"


def route_after_workbench_state(state: AITeamOSWorkbenchState) -> Literal["approval_interrupt", "final_response"]:
    return "approval_interrupt" if should_interrupt_for_approval(state) else "final_response"


def approval_interrupt(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    requests = records(state.get("approval_requests"))
    primary_request = requests[0] if requests else {}
    runtime_status = record(state.get("runtime_status"))
    active_ticket = record(state.get("active_ticket"))
    ticket_binding = record(state.get("ticket_binding"))
    ticket_id = (
        text(primary_request.get("ticket_id"))
        or text(active_ticket.get("id"))
        or text(active_ticket.get("ticket_id"))
        or text(ticket_binding.get("ticket_id"))
    )
    approval_request_ref = approval_ref(primary_request)
    interrupt_payload = {
        "source": "aiteamos_workbench_graph",
        "kind": text(primary_request.get("kind")) or "runtime_approval",
        "approval_ref": approval_request_ref,
        "approval_requests": requests,
        "ticket_id": ticket_id,
        "employee_id": text(state.get("employee_id")),
        "executor_id": text(primary_request.get("executor_id")) or text(runtime_status.get("executor_id")),
        "required_capability": (
            text(primary_request.get("required_capability"))
            or text(primary_request.get("capability"))
            or "approval"
        ),
        "risk_level": text(primary_request.get("risk_level")),
        "reason": text(primary_request.get("reason")),
        "checkpoint_ref": text(primary_request.get("checkpoint_ref")) or text(runtime_status.get("checkpoint_ref")),
        "executor_session_ref": (
            text(primary_request.get("executor_session_ref"))
            or text(runtime_status.get("executor_session_ref"))
        ),
        "current_graph_node": text(primary_request.get("current_graph_node")) or "governance_gate",
        "runtime_status": runtime_status,
    }
    resume_value = interrupt(interrupt_payload)
    resume_record = record(resume_value)
    resumed_ref = approval_ref(resume_record) or (text(resume_value) if isinstance(resume_value, str) else "") or approval_request_ref
    approval_refs = resume_record.get("approval_refs")
    approved_capabilities = resume_record.get("approved_capabilities")
    return {
        "approval_ref": resumed_ref,
        "approval_interrupt": interrupt_payload,
        "approval_resume": {
            "approval_ref": resumed_ref,
            "approval_refs": approval_refs if isinstance(approval_refs, list) else ([resumed_ref] if resumed_ref else []),
            "approved_capabilities": approved_capabilities if isinstance(approved_capabilities, list) else [],
            "resume_command": resume_record,
            "source": "langgraph_command_resume",
        },
        "runtime_status": {
            **runtime_status,
            "current_node": "resume_after_approval",
            "status": "resuming",
            "approval_ref": resumed_ref,
        },
    }
