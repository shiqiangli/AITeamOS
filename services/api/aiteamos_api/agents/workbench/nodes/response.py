"""Workbench response projection nodes for the AITeamOS Workbench graph."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState, primary_ticket_id, record, records, text
from aiteamos_api.read.chat_models import ChatMessageResponse
from aiteamos_api.read.chat_response_metadata import build_visible_response_contract


def update_workbench_state(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    response = ChatMessageResponse.model_validate(record(state.get("aiteamos_chat_response")))
    metadata = response.run_metadata or {}
    execution = record(metadata.get("execution"))
    result = record(execution.get("result"))
    approval = record(metadata.get("approval"))
    prior_context_bundle = record(state.get("context_bundle"))
    prior_workbench_panels = record(state.get("workbench_panels"))
    prior_provider_blockers = records(state.get("provider_blockers"))
    scoped_context = record(metadata.get("scoped_context"))
    universal_context = record(scoped_context.get("universal_context"))
    ticket_id = primary_ticket_id(response)
    linked_assets = [
        *records(result.get("artifact_refs")),
        *records(result.get("evidence_refs")),
        *records(result.get("ticket_report_refs")),
    ]
    recalled_memory_refs = [
        *records(metadata.get("recalled_memory_refs")),
        *records(universal_context.get("recalled_memory_refs")),
    ]
    provider_blockers = [
        *prior_provider_blockers,
        *records(scoped_context.get("setup_blockers")),
        *records(universal_context.get("setup_blockers")),
    ]
    provenance_events = [
        *records(response.model_dump(mode="json").get("trace_events")),
        *records(universal_context.get("provenance_summary")),
    ]
    return {
        "active_ticket": (
            {"id": ticket_id, "source": "aiteamos_chat_response", "ticket_keys": response.ticket_keys}
            if ticket_id
            else None
        ),
        "ticket_binding": record(execution.get("ticket_binding")) or record(state.get("ticket_binding")),
        "capability_scope": {
            "grants": execution.get("capability_grants") if isinstance(execution.get("capability_grants"), list) else [],
            "approval_required": approval.get("require_approval_for") if isinstance(approval.get("require_approval_for"), list) else [],
        },
        "context_bundle": {
            **prior_context_bundle,
            "scoped_context": scoped_context,
            "universal_context": universal_context,
        },
        "linked_assets": linked_assets,
        "recalled_memory_refs": recalled_memory_refs,
        "approval_requests": records(approval.get("approval_requests")),
        "handoff_decision": record(state.get("handoff_decision")),
        "handoff_summary": record(state.get("handoff_summary")),
        "ticket_handoff_refs": records(state.get("ticket_handoff_refs")),
        "provider_blockers": provider_blockers,
        "provenance_events": provenance_events,
        "workbench_panels": {
            **prior_workbench_panels,
            "active_ticket": bool(ticket_id),
            "employee": True,
            "assets": bool(prior_workbench_panels.get("assets") or linked_assets or recalled_memory_refs),
            "approval": bool(records(approval.get("approval_requests"))),
            "provenance": True,
            "provider_blockers": bool(provider_blockers),
        },
        "runtime_status": {
            **record(state.get("runtime_status")),
            "current_node": "update_workbench_state",
            "status": text(execution.get("status")) or "completed",
        },
    }


def final_response(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    response_payload = record(state.get("aiteamos_chat_response"))
    response = ChatMessageResponse.model_validate(response_payload) if response_payload else None
    response_text = (
        text(state.get("final_response"))
        or (response.reply if response is not None else "")
        or "AITeamOS Workbench completed this turn."
    )
    runtime_status = record(state.get("runtime_status"))
    run_metadata = record(response_payload.get("run_metadata"))
    visible_response = build_visible_response_contract(
        reply=response_text,
        run_metadata=run_metadata,
        ticket_keys=response.ticket_keys if response is not None else list(state.get("ticket_keys") or []),
        provider_blockers=records(state.get("provider_blockers")),
        approval_requests=records(state.get("approval_requests")),
        approval_records=records(state.get("approval_records")),
        handoff_summary=record(state.get("handoff_summary")),
        handoff_decision=record(state.get("handoff_decision")),
        ticket_handoff_refs=records(state.get("ticket_handoff_refs")),
        asset_candidates=records(state.get("asset_candidates")),
        runtime_status=runtime_status,
    )
    next_response_payload = {
        **response_payload,
        "run_metadata": {
            **run_metadata,
            "visible_response": visible_response,
        },
    } if response_payload else {}
    message_kwargs: dict[str, Any] = {}
    if response is not None and response.run_id:
        message_kwargs["id"] = f"{response.run_id}-assistant"
    message_kwargs["response_metadata"] = {
        "aiteamos": next_response_payload,
        "visible_response": visible_response,
    }
    return {
        "messages": [AIMessage(content=response_text, **message_kwargs)],
        "aiteamos_chat_response": next_response_payload or state.get("aiteamos_chat_response", {}),
        "runtime_status": {
            **runtime_status,
            "current_node": "final_response",
            "status": text(runtime_status.get("status")) or visible_response["runtime_status"]["status"],
            "display_state": visible_response["display_state"],
            "blocked_reason": visible_response["blocked_reason"],
            "retry_cause": visible_response["retry_cause"],
        },
    }
