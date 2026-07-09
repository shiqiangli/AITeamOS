"""Employee handoff node for the AITeamOS Workbench graph."""

import asyncio
from typing import Any

from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState, latest_human_text, record, records, text
from aiteamos_api.read.employee_handoff_service import choose_employee_for_goal


async def maybe_handoff_employee(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    """Expose durable handoff outputs and policy-aware handoff decisions."""

    return await asyncio.to_thread(_maybe_handoff_employee_sync, state)


def _maybe_handoff_employee_sync(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    execution_request = record(state.get("execution_request"))
    execution_result = record(state.get("execution_result"))
    runtime_status = record(state.get("runtime_status"))
    handoff_artifact = _handoff_artifact(execution_result)
    if handoff_artifact:
        target_employee = _employee_summary(
            _profile_by_id(records(state.get("employee_profiles")), text(handoff_artifact.get("to_employee_id"))),
            fallback_id=text(handoff_artifact.get("to_employee_id")),
            fallback_role=text(handoff_artifact.get("to_role")),
        )
        handoff_refs = _handoff_refs(execution_result)
        decision = _decision_from_artifact(handoff_artifact)
        return {
            "handoff_decision": decision,
            "handoff_summary": {
                "node": "maybe_handoff_employee",
                "status": "durable_handoff_recorded" if handoff_refs else "handoff_artifact_proposed",
                "ticket_id": text(handoff_artifact.get("ticket_id")),
                "from_employee_id": text(handoff_artifact.get("from_employee_id")),
                "to_employee_id": text(handoff_artifact.get("to_employee_id")),
                "to_role": text(handoff_artifact.get("to_role")),
                "lane": text(handoff_artifact.get("lane")),
                "confidence": handoff_artifact.get("confidence"),
                "handoff_ref_count": len(handoff_refs),
            },
            "ticket_handoff_refs": handoff_refs,
            "selected_employee": target_employee,
            "employee_identity": {
                "summary": target_employee,
                "handoff": handoff_artifact,
                "source": "employee_handoff_artifact",
            },
            "provenance_events": [
                *records(state.get("provenance_events")),
                *_handoff_provenance(handoff_artifact),
            ],
            "workbench_panels": {
                **record(state.get("workbench_panels")),
                "employee": True,
                "handoff": True,
                "active_ticket": True,
                "provenance": True,
            },
            "runtime_status": {
                **runtime_status,
                "current_node": "maybe_handoff_employee",
                "handoff_status": "durable_handoff_recorded" if handoff_refs else "handoff_artifact_proposed",
                "handoff_to_employee_id": text(handoff_artifact.get("to_employee_id")),
            },
        }

    decision = _preview_decision(state, execution_request)
    return {
        "handoff_decision": decision,
        "handoff_summary": {
            "node": "maybe_handoff_employee",
            "status": "handoff_preview" if decision.get("should_handoff") else "not_applicable",
            "ticket_id": text(execution_request.get("ticket_id")),
            "from_employee_id": text(execution_request.get("employee_id")),
            "to_employee_id": text(decision.get("target_employee_id")),
            "to_role": text(decision.get("target_role")),
            "lane": text(decision.get("lane")),
            "confidence": decision.get("confidence"),
            "durable_write": False,
        },
        "runtime_status": {
            **runtime_status,
            "current_node": "maybe_handoff_employee",
            "handoff_status": "handoff_preview" if decision.get("should_handoff") else "not_applicable",
        },
    }


def _handoff_artifact(result: dict[str, Any]) -> dict[str, Any]:
    learning_delta = record(result.get("learning_delta"))
    learned = record(learning_delta.get("employee_handoff"))
    if learned:
        return learned
    return next(
        (
            item
            for item in records(result.get("artifacts"))
            if item.get("kind") == "employee_handoff_request"
        ),
        {},
    )


def _handoff_refs(result: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for event in records(result.get("tool_events")):
        data = record(event.get("data"))
        command = record(data.get("command"))
        if command.get("id") != "tickets.manage:handoff":
            continue
        ticket = record(data.get("ticket"))
        handoff = record(data.get("handoff"))
        refs.append(
            {
                "kind": "ticket_handoff",
                "ticket_id": text(ticket.get("id")) or text(handoff.get("ticket_id")),
                "report_id": text(data.get("report_id")),
                "to_employee_id": text(handoff.get("to_employee_id")),
                "to_role": text(handoff.get("to_role")),
                "command_id": "tickets.manage:handoff",
            }
        )
    return refs


def _decision_from_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "should_handoff": True,
        "target_employee_id": text(artifact.get("to_employee_id")),
        "target_role": text(artifact.get("to_role")),
        "lane": text(artifact.get("lane")),
        "reason": text(artifact.get("content")),
        "confidence": artifact.get("confidence"),
        "policy": record(artifact.get("policy")),
        "source": "execution_result_artifact",
    }


def _preview_decision(state: AITeamOSWorkbenchState, execution_request: dict[str, Any]) -> dict[str, Any]:
    action = text(record(execution_request.get("action_plan")).get("action"))
    current_employee_id = text(execution_request.get("employee_id")) or text(state.get("employee_id"))
    ticket_id = text(execution_request.get("ticket_id")) or text(record(execution_request.get("ticket_binding")).get("ticket_id"))
    if action not in {"answer_only", "append_report", "request_validation"} or current_employee_id != "clara" or not ticket_id:
        return {"should_handoff": False, "reason": "Handoff policy did not apply to this graph turn.", "source": "handoff_node"}
    task_context = record(execution_request.get("task_context"))
    required_memory_scopes = (
        [text(item) for item in task_context.get("required_memory_scopes", []) if text(item)]
        if isinstance(task_context.get("required_memory_scopes"), list)
        else None
    )
    decision = choose_employee_for_goal(
        text(task_context.get("task_summary")) or latest_human_text(list(state.get("messages") or [])),
        records(task_context.get("employee_profiles")) or records(state.get("employee_profiles")),
        current_employee_id=current_employee_id,
        required_memory_scopes=required_memory_scopes,
        risk_level=text(task_context.get("risk_level") or task_context.get("risk")),
    )
    return {**decision, "source": "employee_handoff_service"}


def _profile_by_id(profiles: list[dict[str, Any]], employee_id: str) -> dict[str, Any]:
    normalized = employee_id.lower()
    return next((profile for profile in profiles if text(profile.get("id")).lower() == normalized), {})


def _employee_summary(profile: dict[str, Any], *, fallback_id: str, fallback_role: str) -> dict[str, Any]:
    employee_id = text(profile.get("id")) or fallback_id
    return {
        "id": employee_id,
        "display_name": text(profile.get("display_name")) or employee_id,
        "role": text(profile.get("role")) or fallback_role,
        "summary": text(profile.get("summary")),
        "skills": [str(item) for item in profile.get("skills", [])] if isinstance(profile.get("skills"), list) else [],
        "capability_tags": [str(item) for item in profile.get("capability_tags", [])] if isinstance(profile.get("capability_tags"), list) else [],
        "current_load": record(profile.get("current_load")),
        "handoff_policy": record(profile.get("handoff_policy")),
    }


def _handoff_provenance(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    provenance = record(artifact.get("provenance"))
    if provenance:
        return [{**provenance, "kind": "employee_handoff"}]
    ticket_id = text(artifact.get("ticket_id"))
    if not ticket_id:
        return []
    return [
        {
            "kind": "employee_handoff",
            "source_kind": "execution_result_artifact",
            "source_ref": text(artifact.get("from_employee_id")),
            "scope_kind": "ticket",
            "scope_ref": ticket_id,
        }
    ]
