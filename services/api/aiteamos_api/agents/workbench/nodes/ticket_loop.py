"""Ticket loop policy and close/continue decision node."""

import asyncio
from typing import Any

from aiteamos_api.agents.workbench.state import AITeamOSWorkbenchState, record, records, text
from aiteamos_api.read.asset_candidate_service import (
    TicketCloseoutAssetCandidateRequest,
    TicketCloseoutSettlementRequest,
    propose_ticket_closeout_asset_candidates,
    settle_ticket_closeout_assets,
)
from aiteamos_api.read.ticket_loop_service import ticket_loop_queue_worker_status, ticket_loop_timeline


async def close_or_continue_ticket_loop(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    """Expose Ticket loop policy/timeline facts without owning queue scheduling."""

    return await asyncio.to_thread(_close_or_continue_ticket_loop_sync, state)


def _close_or_continue_ticket_loop_sync(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    runtime_status = record(state.get("runtime_status"))
    provider_blockers = records(state.get("provider_blockers"))
    ticket_id = _ticket_id_from_state(state)
    if not ticket_id:
        return {
            "ticket_loop_decision": {
                "node": "close_or_continue_ticket_loop",
                "action": "not_applicable",
                "reason": "This Workbench turn is not bound to a durable Ticket.",
                "ticket_bound": False,
            },
            "runtime_status": {
                **runtime_status,
                "current_node": "close_or_continue_ticket_loop",
                "ticket_loop_action": "not_applicable",
            },
        }

    try:
        timeline = ticket_loop_timeline(ticket_id)
    except Exception as exc:
        blocker = {
            "kind": "ticket_loop",
            "reason": "ticket_loop_timeline_unavailable",
            "detail": str(exc)[:500],
            "provider": "ticket_loop_service",
            "ticket_id": ticket_id,
        }
        return {
            "provider_blockers": [*provider_blockers, blocker],
            "ticket_loop_decision": {
                "node": "close_or_continue_ticket_loop",
                "action": "inspect_blocker",
                "reason": "Ticket loop timeline could not be loaded.",
                "ticket_id": ticket_id,
                "ticket_bound": True,
            },
            "runtime_status": {
                **runtime_status,
                "current_node": "close_or_continue_ticket_loop",
                "ticket_loop_action": "inspect_blocker",
                "ticket_id": ticket_id,
            },
        }

    summary = timeline.summary.model_dump(mode="json")
    policy = record(summary.get("policy"))
    decision = _decision_from_summary(summary)
    applied = _apply_ticket_loop_decision(ticket_id, decision, policy, timeline, state)
    provider_blockers = [*provider_blockers, *records(applied.get("provider_blockers"))]
    closeout_candidates = records(applied.get("asset_candidates"))
    if applied:
        decision = {
            **decision,
            "applied_action": record(applied.get("applied_action")),
        }
        timeline = ticket_loop_timeline(ticket_id)
        summary = timeline.summary.model_dump(mode="json")
        policy = record(summary.get("policy"))
    policy_actions, policy_action_blocker = _recent_policy_actions_for_ticket(ticket_id)
    if policy_action_blocker:
        provider_blockers.append(policy_action_blocker)
    policy_handoff_refs = _handoff_refs_from_policy_actions(policy_actions)
    policy_refs = _policy_action_refs(policy_actions)
    decision = _with_policy_actions(decision, policy_actions, policy_refs)
    return {
        "ticket_loop_summary": summary,
        "ticket_loop_policy": policy,
        "ticket_loop_decision": decision,
        "ticket_loop_policy_actions": policy_actions,
        "ticket_handoff_refs": _merge_refs(records(state.get("ticket_handoff_refs")), policy_handoff_refs),
        "asset_candidates": _merge_asset_candidates(records(state.get("asset_candidates")), closeout_candidates),
        "provider_blockers": provider_blockers,
        "workbench_panels": {
            **record(state.get("workbench_panels")),
            "active_ticket": True,
            "ticket_loop": True,
            "assets": bool(closeout_candidates or records(state.get("asset_candidates"))),
            "handoff": bool(policy_handoff_refs or record(state.get("workbench_panels")).get("handoff")),
            "provenance": True,
            "provider_blockers": bool(provider_blockers),
        },
        "provenance_events": [
            *records(state.get("provenance_events")),
            {
                "kind": "ticket_loop_policy",
                "source_kind": "ticket_loop_service",
                "source_ref": ticket_id,
                "scope_kind": "ticket",
                "scope_ref": ticket_id,
                "policy_source": text(policy.get("source")),
            },
            *_policy_action_provenance(ticket_id, policy_actions),
        ],
        "runtime_status": {
            **runtime_status,
            "current_node": "close_or_continue_ticket_loop",
            "ticket_id": ticket_id,
            "ticket_loop_status": text(summary.get("status")),
            "ticket_loop_action": text(decision.get("action")),
            "ticket_loop_policy_source": text(policy.get("source")),
            "ticket_loop_applied_action": text(record(decision.get("applied_action")).get("kind")),
            "ticket_loop_policy_action_count": len(policy_actions),
            "ticket_loop_policy_action_kinds": [text(action.get("kind")) for action in policy_actions if text(action.get("kind"))],
        },
    }


def _ticket_id_from_state(state: AITeamOSWorkbenchState) -> str:
    active_ticket = record(state.get("active_ticket"))
    ticket_binding = record(state.get("ticket_binding"))
    execution_request = record(state.get("execution_request"))
    execution_result = record(state.get("execution_result"))
    for value in [
        active_ticket.get("id"),
        active_ticket.get("ticket_id"),
        ticket_binding.get("ticket_id"),
        execution_request.get("ticket_id"),
        record(execution_request.get("ticket_binding")).get("ticket_id"),
        execution_result.get("output_ticket_id"),
        *(state.get("ticket_keys") or []),
    ]:
        value_text = text(value)
        if value_text:
            return value_text
    return ""


def _decision_from_summary(summary: dict[str, Any]) -> dict[str, Any]:
    status = text(summary.get("status")).lower()
    policy = record(summary.get("policy"))
    queue = record(summary.get("queue_reliability"))
    queue_status = text(queue.get("status")).lower()
    can_resume = bool(summary.get("can_resume"))
    can_retry = bool(summary.get("can_retry"))
    can_run = bool(summary.get("can_run"))

    action = "continue"
    reason = text(summary.get("next_action")) or "Continue normal Ticket execution."
    if status in {"closed", "completed", "done", "cancelled"}:
        action = "terminal"
    elif status == "validated":
        closeout = record(policy.get("closeout"))
        if closeout.get("auto_settle_assets") and closeout.get("auto_approve_candidates"):
            action = "settle_closeout_assets"
            reason = "Validated Ticket is ready for governed closeout settlement."
        else:
            action = "propose_closeout_assets" if closeout.get("auto_propose_assets", True) else "await_manual_closeout"
            reason = "Validated Ticket is ready for governed closeout asset review."
    elif status == "waiting_validation":
        action = "request_validation"
    elif status == "waiting_approval":
        action = "wait_for_approval"
    elif can_resume:
        action = "resume_available"
    elif queue_status in {"error", "stale_running", "duplicate_queued"}:
        action = "inspect_queue"
        reason = text(queue.get("detail")) or reason
    elif queue_status in {"waiting_worker", "active"}:
        action = "await_queue_worker"
        reason = text(queue.get("detail")) or reason
    elif can_retry:
        action = "retry_available"
    elif not can_run:
        action = "blocked"
    elif record(policy.get("recurrence")).get("enabled"):
        action = "recurrence_scheduled"

    return {
        "node": "close_or_continue_ticket_loop",
        "action": action,
        "reason": reason,
        "ticket_bound": True,
        "ticket_id": text(summary.get("ticket_id")),
        "ticket_status": status,
        "can_run": can_run,
        "can_resume": can_resume,
        "can_retry": can_retry,
        "queue_status": queue_status,
        "policy_source": text(policy.get("source")),
        "policy_configured": record(policy.get("configured")),
    }


def _apply_ticket_loop_decision(
    ticket_id: str,
    decision: dict[str, Any],
    policy: dict[str, Any],
    timeline: Any,
    state: AITeamOSWorkbenchState,
) -> dict[str, Any]:
    action = text(decision.get("action"))
    if action not in {"propose_closeout_assets", "settle_closeout_assets"}:
        return {}

    closeout_policy = record(policy.get("closeout"))
    require_validation_evidence = closeout_policy.get("require_validation_evidence", True) is not False
    if require_validation_evidence and not _has_validation_evidence(timeline):
        blocker = {
            "kind": "ticket_loop",
            "reason": "closeout_validation_evidence_required",
            "detail": "Ticket closeout Asset proposal requires validation evidence before creating governed candidates.",
            "provider": "ticket_loop_service",
            "ticket_id": ticket_id,
        }
        return {
            "applied_action": {
                "kind": "closeout_asset_candidates",
                "status": "blocked",
                "detail": blocker["detail"],
                "candidate_count": 0,
            },
            "provider_blockers": [blocker],
        }

    selected_employee = record(state.get("selected_employee"))
    actor_employee_id = text(state.get("employee_id")) or text(selected_employee.get("id")) or "clara"
    actor_role = text(selected_employee.get("role")) or "AI Team OS Manager"
    if action == "settle_closeout_assets":
        response = asyncio.run(
            settle_ticket_closeout_assets(
                ticket_id,
                TicketCloseoutSettlementRequest(
                    actor_employee_id=actor_employee_id,
                    actor_role=actor_role,
                    reviewer_employee_id=actor_employee_id,
                    reason="LangGraph close_or_continue_ticket_loop settled governed closeout Assets from Ticket policy.",
                    approve_candidates=True,
                    project_graphiti=bool(closeout_policy.get("project_graphiti")),
                    project_relationships=bool(closeout_policy.get("project_relationships")),
                    asset_types=[text(item) for item in closeout_policy.get("asset_types", []) if text(item)],
                ),
            )
        )
        candidates = [candidate.model_dump(mode="json") for candidate in response.candidates]
        return {
            "asset_candidates": candidates,
            "provider_blockers": _settlement_provider_blockers(ticket_id, response.model_dump(mode="json")),
            "applied_action": {
                "kind": "closeout_settlement",
                "status": response.status,
                "detail": response.detail,
                "report_id": response.report_id,
                "candidate_count": len(candidates),
                "candidate_ids": [text(candidate.get("id")) for candidate in candidates if text(candidate.get("id"))],
                "asset_ids": response.asset_ids,
                "review_status": response.review.status if response.review is not None else "",
                "reviewed_count": response.review.reviewed_count if response.review is not None else 0,
                "projection_statuses": [
                    {"asset_id": projection.asset_id, "status": projection.status, "error": projection.error}
                    for projection in response.projections
                ],
                "saved_paths": response.saved_paths,
            },
        }

    response = propose_ticket_closeout_asset_candidates(
        ticket_id,
        TicketCloseoutAssetCandidateRequest(
            actor_employee_id=actor_employee_id,
            actor_role=actor_role,
            reason="LangGraph close_or_continue_ticket_loop proposed governed closeout Asset candidates.",
        ),
    )
    candidates = [candidate.model_dump(mode="json") for candidate in response.candidates]
    return {
        "asset_candidates": candidates,
        "applied_action": {
            "kind": "closeout_asset_candidates",
            "status": response.status,
            "detail": response.detail,
            "report_id": response.report_id,
            "candidate_count": len(candidates),
            "candidate_ids": [text(candidate.get("id")) for candidate in candidates if text(candidate.get("id"))],
            "saved_paths": response.saved_paths,
        },
    }


def _settlement_provider_blockers(ticket_id: str, settlement: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for projection in records(settlement.get("projections")):
        error = text(projection.get("error"))
        if not error:
            continue
        blockers.append(
            {
                "kind": "asset_graph_projection",
                "reason": "closeout_settlement_projection_blocked",
                "detail": error[:500],
                "provider": "graphiti",
                "ticket_id": ticket_id,
                "asset_id": text(projection.get("asset_id")),
                "status": text(projection.get("status")),
            }
        )
    if text(settlement.get("status")) == "blocked" and not blockers:
        blockers.append(
            {
                "kind": "asset_graph_projection",
                "reason": "closeout_settlement_blocked",
                "detail": text(settlement.get("detail"))[:500],
                "provider": "graphiti",
                "ticket_id": ticket_id,
            }
        )
    return blockers


def _recent_policy_actions_for_ticket(ticket_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        status = ticket_loop_queue_worker_status()
    except Exception as exc:
        return [], {
            "kind": "ticket_loop",
            "reason": "ticket_loop_policy_actions_unavailable",
            "detail": str(exc)[:500],
            "provider": "ticket_loop_service",
            "ticket_id": ticket_id,
        }
    actions = []
    for action in status.recent_policy_actions:
        payload = action.model_dump(mode="json")
        if text(payload.get("ticket_id")) == ticket_id:
            actions.append(payload)
    return actions, {}


def _with_policy_actions(
    decision: dict[str, Any],
    policy_actions: list[dict[str, Any]],
    policy_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    if not policy_actions:
        return decision
    return {
        **decision,
        "policy_actions": policy_actions,
        "policy_action_count": len(policy_actions),
        "policy_action_kinds": [text(action.get("kind")) for action in policy_actions if text(action.get("kind"))],
        "policy_action_refs": policy_refs,
    }


def _policy_action_refs(policy_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for action in policy_actions:
        action_kind = text(action.get("kind"))
        for ref in records(action.get("handoff_refs")):
            refs.append(
                {
                    "kind": "ticket_handoff",
                    "action_kind": action_kind,
                    "ticket_id": text(ref.get("ticket_id")) or text(action.get("ticket_id")),
                    "event_id": text(ref.get("event_id")),
                    "to_employee_id": text(ref.get("to_employee_id")),
                    "to_role": text(ref.get("to_role")),
                }
            )
        for queue_id in action.get("queue_ids") or []:
            queue_id_text = text(queue_id)
            if queue_id_text:
                refs.append({"kind": "ticket_loop_queue", "action_kind": action_kind, "ticket_id": text(action.get("ticket_id")), "queue_id": queue_id_text})
        for run_id in action.get("run_ids") or []:
            run_id_text = text(run_id)
            if run_id_text:
                refs.append({"kind": "ticket_loop_run", "action_kind": action_kind, "ticket_id": text(action.get("ticket_id")), "run_id": run_id_text})
        report_id = text(action.get("report_id"))
        if report_id:
            refs.append({"kind": "ticket_report", "action_kind": action_kind, "ticket_id": text(action.get("ticket_id")), "report_id": report_id})
    return refs


def _handoff_refs_from_policy_actions(policy_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for action in policy_actions:
        action_kind = text(action.get("kind"))
        for ref in records(action.get("handoff_refs")):
            refs.append(
                {
                    **ref,
                    "kind": "ticket_handoff",
                    "source": "ticket_loop_policy_action",
                    "action_kind": action_kind,
                    "ticket_id": text(ref.get("ticket_id")) or text(action.get("ticket_id")),
                    "report_id": text(action.get("report_id")),
                }
            )
    return refs


def _policy_action_provenance(ticket_id: str, policy_actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for action in policy_actions:
        action_kind = text(action.get("kind"))
        if not action_kind:
            continue
        events.append(
            {
                "kind": "ticket_loop_policy_action",
                "source_kind": "ticket_loop_queue_worker",
                "source_ref": action_kind,
                "scope_kind": "ticket",
                "scope_ref": ticket_id,
                "status": text(action.get("status")),
                "report_id": text(action.get("report_id")),
                "queue_ids": [text(value) for value in action.get("queue_ids") or [] if text(value)],
                "run_ids": [text(value) for value in action.get("run_ids") or [] if text(value)],
            }
        )
    return events


def _merge_refs(existing: list[dict[str, Any]], proposed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in [*existing, *proposed]:
        key = "|".join(
            [
                text(ref.get("kind")),
                text(ref.get("event_id")),
                text(ref.get("ticket_id")),
                text(ref.get("to_employee_id")),
                text(ref.get("report_id")),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
    return merged


def _has_validation_evidence(timeline: Any) -> bool:
    for item in getattr(timeline, "items", []) or []:
        if text(getattr(item, "kind", "")).lower() != "ticket_report":
            continue
        if text(getattr(item, "status", "")).lower() not in {"validation", "validated", "validation_passed", "pv_validation"}:
            continue
        refs = getattr(item, "refs", []) or []
        if refs:
            return True
        data = record(getattr(item, "data", {}))
        evidence = data.get("evidence")
        if isinstance(evidence, list) and any(text(value) for value in evidence):
            return True
    return False


def _merge_asset_candidates(
    existing: list[dict[str, Any]],
    proposed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in [*existing, *proposed]:
        key = text(candidate.get("id")) or text(candidate.get("candidate_id")) or text(candidate.get("source_candidate_id"))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        merged.append(candidate)
    return merged
