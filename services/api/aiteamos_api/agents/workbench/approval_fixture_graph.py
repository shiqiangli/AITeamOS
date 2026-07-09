"""Deterministic approval fixture graph for Agent Server smoke tests.

The fixture graph is intentionally separate from the production Workbench graph
so production graph assembly stays focused on runtime orchestration.
"""

import os
from pathlib import Path
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from aiteamos_api.agents.workbench.state import (
    AITeamOSWorkbenchState,
    approval_ref as _approval_ref,
    configurable as _configurable,
    latest_human_text as _latest_human_text,
    record as _record,
    records as _records,
    text as _text,
)


def fixture_employee() -> dict[str, Any]:
    return {
        "id": "clara",
        "display_name": "Clara",
        "role": "AI Team OS Manager",
        "summary": "Coordinator",
        "default_thread_id": "employee-clara-default",
    }


def fixture_response(
    *,
    approval_requests: list[dict[str, Any]],
    reply: str,
    run_id: str,
    status: str,
    ticket_id: str = "rd-approval-fixture",
) -> dict[str, Any]:
    return {
        "thread_id": "employee-clara-approval-fixture",
        "run_id": run_id,
        "target_employee": fixture_employee(),
        "engine_thread_id": "engine-thread-approval-fixture",
        "ticket_keys": [ticket_id],
        "reply": reply,
        "trace_events": [],
        "run_metadata": {
            "run_id": run_id,
            "thread_id": "employee-clara-approval-fixture",
            "employee": fixture_employee(),
            "ticket_keys": [ticket_id],
            "execution": {
                "request_id": run_id,
                "executor_id": "langgraph",
                "status": status,
                "action": "implement_ticket",
                "ticket_binding": {"mode": "existing", "ticket_id": ticket_id, "required": True},
                "capability_grants": ["tickets:read", "repo:read", *([] if approval_requests else ["repo:write"])],
                "trace": {
                    "trace_ref": f".aiteamos/traces/{run_id}.jsonl",
                    "executor_session_ref": f"lg-{run_id}",
                    "checkpoint_ref": f"langgraph:{run_id}",
                },
                "result": {
                    "output_ticket_id": ticket_id,
                    "artifact_count": 0 if approval_requests else 1,
                    "artifact_refs": [] if approval_requests else [{"kind": "runtime_mutation", "ref": "artifact-approved-fixture"}],
                    "tool_event_count": 1,
                    "memory_candidate_count": 0 if approval_requests else 1,
                    "evidence_count": 0 if approval_requests else 1,
                    "evidence_refs": [] if approval_requests else [{"kind": "runtime_report", "ref": "evidence-approved-fixture"}],
                    "ticket_report_count": 0 if approval_requests else 1,
                    "ticket_report_refs": [] if approval_requests else [{"kind": "approval_resumed", "ref": "report-approved-fixture"}],
                    "error_count": 0,
                    "errors": [],
                },
                "governance": {
                    "approval_refs": [] if approval_requests else ["approval-fixture-1"],
                    "approved_capabilities": [] if approval_requests else ["repo:write"],
                },
            },
            "approval": {
                "require_approval_for": ["repo:write"],
                "on_missing_approval": "return_needs_approval",
                "approval_refs": [] if approval_requests else ["approval-fixture-1"],
                "approved_capabilities": [] if approval_requests else ["repo:write"],
                "approval_requests": approval_requests,
            },
            "scoped_context": {
                "relevant_asset_count": 1,
                "recalled_memory_count": 1,
                "setup_blocker_count": 0,
                "setup_blockers": [],
                "universal_context": {
                    "version": "universal_context.v1",
                    "employee_id": "clara",
                    "ticket_id": ticket_id,
                    "related_ticket_count": 1,
                    "relevant_asset_count": 1,
                    "recalled_memory_count": 1,
                    "setup_blocker_count": 0,
                    "ticket_backend_status": "fixture",
                    "provenance_summary": [
                        {
                            "kind": "memory",
                            "source_kind": "memory",
                            "source_ref": "mem-approval-fixture",
                            "scope_kind": "ticket",
                            "scope_ref": ticket_id,
                        }
                    ],
                },
            },
            "recalled_memory_refs": [
                {
                    "memory_id": "mem-approval-fixture",
                    "graphiti_recalled": True,
                    "source_ticket_id": f"{ticket_id}-seed",
                }
            ],
            "trace": {"path": f".aiteamos/traces/{run_id}.jsonl"},
        },
        "saved_paths": {"trace": f".aiteamos/traces/{run_id}.jsonl"},
    }


def _workspace_root() -> Path:
    configured = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _fixture_record_approval_request(approval_request: dict[str, Any], *, ticket_id: str) -> dict[str, Any]:
    from aiteamos_api.read.chat_action_plan import ChatActionPlan
    from aiteamos_api.read.execution_approval_service import record_execution_approval_requests
    from aiteamos_api.read.execution_contract import ExecutionRequest, ExecutionResult, TicketBinding

    request = ExecutionRequest(
        request_id="fixture",
        workspace_id=str(_workspace_root()),
        employee_id="clara",
        ticket_id=ticket_id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket_id, required=True),
        action_plan=ChatActionPlan(action="implement_ticket", arguments={"message": "Trigger approval fixture."}),
        capability_grants=["tickets:read", "repo:read"],
        approval_policy={"require_approval_for": ["repo:write"], "on_missing_approval": "return_needs_approval"},
        expected_outputs={"evidence": True, "artifacts": True, "memory_candidates": True},
        trace_context={
            "run_id": "fixture-needs-approval",
            "thread_id": "employee-clara-approval-fixture",
            "trace_ref": ".aiteamos/traces/fixture-needs-approval.jsonl",
        },
    )
    result = ExecutionResult(
        request_id=request.request_id,
        executor_id="fixture_runtime",
        status="needs_approval",
        report="Fixture approval requires a LangGraph native resume command.",
        output_ticket_id=ticket_id,
        trace_ref=".aiteamos/traces/fixture-needs-approval.jsonl",
        executor_session_ref="lg-fixture-needs-approval",
        checkpoint_ref="langgraph:fixture-needs-approval",
        approval_requests=[
            {
                **approval_request,
                "approval_ref": "approval-fixture-1",
                "source_state_ref": "state://aiteamos_workbench_approval_fixture/fixture-needs-approval",
                "proposed_action": {
                    "executor_id": "fixture_runtime",
                    "action": "implement_ticket",
                    "ticket_id": ticket_id,
                },
            }
        ],
        errors=[
            {
                "reason": "repo_mutation_approval_required",
                "detail": "repo:write requires approval before fixture runtime mutation.",
            }
        ],
    )
    records = record_execution_approval_requests(workspace_dir=_workspace_root(), request=request, result=result)
    return records[0].model_dump(mode="json") if records else {}


def _fixture_prepare_needs_approval(
    state: AITeamOSWorkbenchState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    cfg = _configurable(config)
    thread_id = _text(state.get("thread_id")) or _text(cfg.get("thread_id")) or "employee-clara-approval-fixture"
    ticket_id = _text(state.get("ticket_key")) or _text(cfg.get("ticket_key")) or "rd-approval-fixture"
    if _fixture_recall_requested(state):
        return _fixture_prepare_asset_recall(thread_id=thread_id, ticket_id=ticket_id)
    approval_request = {
        "approval_ref": "approval-fixture-1",
        "kind": "repo_mutation",
        "ticket_id": ticket_id,
        "executor_id": "fixture_runtime",
        "required_capability": "repo:write",
        "risk_level": "high",
        "reason": "Fixture approval requires a LangGraph native resume command.",
        "checkpoint_ref": "langgraph:fixture-needs-approval",
        "executor_session_ref": "lg-fixture-needs-approval",
        "current_graph_node": "governance_gate",
    }
    approval_records: list[dict[str, Any]] = []
    provider_blockers: list[dict[str, Any]] = []
    try:
        approval_record = _fixture_record_approval_request(approval_request, ticket_id=ticket_id)
        if approval_record:
            approval_records.append(approval_record)
            approval_request = {
                **approval_request,
                "approval_record_ref": _text(approval_record.get("id")) or "approval-fixture-1",
                "source_state_snapshot_ref": _text(approval_record.get("source_state_snapshot_ref")),
                "status": _text(approval_record.get("status")) or "requested",
            }
    except Exception as exc:
        provider_blockers.append(
            {
                "reason": "approval_record_write_failed",
                "detail": str(exc)[:500],
                "provider": "execution_approval_service",
            }
        )
    response = fixture_response(
        approval_requests=[approval_request],
        reply="Fixture approval is required before execution.",
        run_id="fixture-needs-approval",
        status="needs_approval",
        ticket_id=ticket_id,
    )
    return {
        "aiteamos_chat_response": response,
        "thread_id": thread_id,
        "employee_id": "clara",
        "ticket_key": ticket_id,
        "selected_employee": fixture_employee(),
        "employee_identity": fixture_employee(),
        "active_ticket": {
            "id": ticket_id,
            "source": "aiteamos_workbench_approval_fixture",
            "ticket_keys": [ticket_id],
        },
        "ticket_binding": {"mode": "existing", "ticket_id": ticket_id, "required": True},
        "context_bundle": response["run_metadata"]["scoped_context"],
        "linked_assets": [],
        "recalled_memory_refs": response["run_metadata"]["recalled_memory_refs"],
        "approval_requests": [approval_request],
        "approval_records": approval_records,
        "asset_candidates": [],
        "provider_blockers": provider_blockers,
        "provenance_events": response["run_metadata"]["scoped_context"]["universal_context"]["provenance_summary"],
        "workbench_panels": {
            "active_ticket": True,
            "employee": True,
            "assets": True,
            "approval": True,
            "provenance": True,
            "provider_blockers": bool(provider_blockers),
        },
        "runtime_status": {
            "executor": "langgraph",
            "graph": "aiteamos_workbench_approval_fixture",
            "current_node": "approval_interrupt",
            "status": "needs_approval",
            "checkpoint_ref": "langgraph:fixture-needs-approval",
            "executor_session_ref": "lg-fixture-needs-approval",
        },
    }


def _fixture_recall_requested(state: AITeamOSWorkbenchState) -> bool:
    text = _latest_human_text(state.get("messages", [])).lower()
    return "recall" in text and ("asset" in text or "memory" in text)


def _fixture_safe_ref(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value.strip())
    return safe.strip("-")[:80] or "fixture"


def _fixture_asset_candidates_for_ticket(ticket_id: str) -> list[dict[str, Any]]:
    from aiteamos_api.read.asset_candidate_service import list_asset_candidates

    candidates: list[dict[str, Any]] = []
    for item in list_asset_candidates():
        payload = item.model_dump(mode="json")
        provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
        source_ticket_id = _text(provenance.get("source_ticket_id")) or _text(payload.get("scope_ref"))
        if source_ticket_id == ticket_id:
            candidates.append(payload)
    return candidates


def _fixture_recalled_asset_refs(ticket_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from aiteamos_api.read.asset_candidate_service import list_asset_records

    recalled: list[dict[str, Any]] = []
    linked_assets: list[dict[str, Any]] = []
    provider_blockers: list[dict[str, Any]] = []
    for item in list_asset_records(status="approved"):
        provenance = item.provenance if isinstance(item.provenance, dict) else {}
        source_ticket_id = _text(provenance.get("source_ticket_id")) or (item.scope_ref if item.scope_kind == "ticket" else "")
        if source_ticket_id != ticket_id:
            continue
        graphiti_status = provenance.get("graphiti_status") if isinstance(provenance.get("graphiti_status"), dict) else {}
        graphiti_episode_id = _text(graphiti_status.get("episode_id"))
        graphiti_recalled = bool(graphiti_episode_id)
        recalled.append(
            {
                "memory_id": item.id,
                "asset_id": item.id,
                "asset_type": item.asset_type,
                "title": item.title,
                "content_ref": item.content_ref,
                "source_ticket_id": source_ticket_id,
                "source_report_id": _text(provenance.get("source_report_id")),
                "graphiti_recalled": graphiti_recalled,
                "graphiti_episode_id": graphiti_episode_id,
                "source": "graphiti" if graphiti_recalled else "asset_registry",
            }
        )
        linked_assets.append(
            {
                "kind": "approved_asset",
                "ref": item.id,
                "asset_type": item.asset_type,
                "source_ticket_id": source_ticket_id,
                "graphiti_episode_id": graphiti_episode_id,
            }
        )
        if not graphiti_recalled:
            provider_blockers.append(
                {
                    "reason": "graphiti_projection_not_available",
                    "detail": f"Approved AssetRecord {item.id} has no Graphiti episode id in provenance.",
                    "provider": "graphiti",
                }
            )
    return recalled, linked_assets, provider_blockers


def _fixture_prepare_asset_recall(*, thread_id: str, ticket_id: str) -> dict[str, Any]:
    recalled_refs, linked_assets, provider_blockers = _fixture_recalled_asset_refs(ticket_id)
    asset_candidates = _fixture_asset_candidates_for_ticket(ticket_id)
    reply = (
        "Recalled approved fixture Asset from Assets registry."
        if recalled_refs
        else "No approved fixture Asset was available for recall."
    )
    response = fixture_response(
        approval_requests=[],
        reply=reply,
        run_id="fixture-asset-recall",
        status="completed",
        ticket_id=ticket_id,
    )
    metadata = _record(response["run_metadata"])
    metadata["recalled_memory_refs"] = recalled_refs
    execution = _record(metadata.get("execution"))
    result = _record(execution.get("result"))
    result["memory_candidate_count"] = len(asset_candidates)
    result["artifact_refs"] = linked_assets
    scoped_context = _record(metadata.get("scoped_context"))
    scoped_context["recalled_memory_count"] = len(recalled_refs)
    scoped_context["relevant_asset_count"] = len(linked_assets)
    scoped_context["setup_blocker_count"] = len(provider_blockers)
    scoped_context["setup_blockers"] = provider_blockers
    universal_context = _record(scoped_context.get("universal_context"))
    universal_context["recalled_memory_count"] = len(recalled_refs)
    universal_context["relevant_asset_count"] = len(linked_assets)
    universal_context["setup_blocker_count"] = len(provider_blockers)
    universal_context["provenance_summary"] = [
        {
            "kind": "asset_recall",
            "source_kind": item.get("source", "asset_registry"),
            "source_ref": item.get("asset_id", ""),
            "scope_kind": "ticket",
            "scope_ref": ticket_id,
        }
        for item in recalled_refs
    ]
    return {
        "aiteamos_chat_response": response,
        "final_response": reply,
        "thread_id": thread_id,
        "employee_id": "clara",
        "ticket_key": ticket_id,
        "selected_employee": fixture_employee(),
        "employee_identity": fixture_employee(),
        "active_ticket": {
            "id": ticket_id,
            "source": "aiteamos_workbench_approval_fixture",
            "ticket_keys": [ticket_id],
        },
        "ticket_binding": {"mode": "existing", "ticket_id": ticket_id, "required": True},
        "context_bundle": scoped_context,
        "linked_assets": linked_assets,
        "recalled_memory_refs": recalled_refs,
        "approval_requests": [],
        "approval_records": [],
        "asset_candidates": asset_candidates,
        "provider_blockers": provider_blockers,
        "provenance_events": universal_context["provenance_summary"],
        "workbench_panels": {
            "active_ticket": True,
            "employee": True,
            "assets": True,
            "approval": False,
            "provenance": True,
            "provider_blockers": bool(provider_blockers),
        },
        "runtime_status": {
            "executor": "langgraph",
            "graph": "aiteamos_workbench_approval_fixture",
            "current_node": "asset_recall",
            "status": "completed",
            "run_id": "fixture-asset-recall",
            "checkpoint_ref": "langgraph:fixture-asset-recall",
            "executor_session_ref": "lg-fixture-asset-recall",
            "recalled_asset_count": len(recalled_refs),
        },
        "messages": [AIMessage(content=reply)],
    }


def _fixture_approval_interrupt(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    requests = _records(state.get("approval_requests"))
    ticket_id = _text((requests[0] if requests else {}).get("ticket_id")) or _text(state.get("ticket_key")) or "rd-approval-fixture"
    payload = {
        "source": "aiteamos_workbench_approval_fixture",
        "kind": "repo_mutation",
        "approval_ref": "approval-fixture-1",
        "approval_requests": requests,
        "approval_records": _records(state.get("approval_records")),
        "ticket_id": ticket_id,
        "employee_id": "clara",
        "executor_id": "fixture_runtime",
        "required_capability": "repo:write",
        "risk_level": "high",
        "reason": "Fixture approval requires a LangGraph native resume command.",
        "checkpoint_ref": "langgraph:fixture-needs-approval",
        "executor_session_ref": "lg-fixture-needs-approval",
        "current_graph_node": "governance_gate",
    }
    resume_value = interrupt(payload)
    resume_record = _record(resume_value)
    approval_ref = _approval_ref(resume_record) or "approval-fixture-1"
    return {
        "approval_ref": approval_ref,
        "approval_interrupt": payload,
        "approval_resume": {
            "approval_ref": approval_ref,
            "approval_refs": [approval_ref],
            "approved_capabilities": resume_record.get("approved_capabilities") if isinstance(resume_record.get("approved_capabilities"), list) else [],
            "resume_command": resume_record,
            "source": "langgraph_command_resume",
        },
        "runtime_status": {
            **_record(state.get("runtime_status")),
            "current_node": "resume_after_approval",
            "status": "resuming",
            "approval_ref": approval_ref,
        },
    }


def _fixture_review_approval_and_record_ticket_report(response: dict[str, Any], approval_ref: str) -> dict[str, Any]:
    from aiteamos_api.read.execution_approval_service import ExecutionApprovalReviewRequest, review_execution_approval
    from aiteamos_api.read.ticket_service import TicketReportRequest, add_ticket_report, get_ticket

    run_id = _text(response.get("run_id")) or "fixture-approved-resume"
    ticket_id = _text((response.get("ticket_keys") or [""])[0]) if isinstance(response.get("ticket_keys"), list) else ""
    ticket_id = ticket_id or "rd-approval-fixture"
    reviewed: dict[str, Any] = {}
    ticket_report_id = ""
    blockers: list[dict[str, Any]] = []
    try:
        reviewed_record = review_execution_approval(
            workspace_dir=_workspace_root(),
            approval_id=approval_ref,
            review=ExecutionApprovalReviewRequest(
                status="approved",
                reviewer_employee_id="clara",
                reason="LangGraph input.respond resumed the approval fixture.",
            ),
        )
        reviewed = reviewed_record.model_dump(mode="json")
    except Exception as exc:
        blockers.append({"reason": "approval_review_record_failed", "detail": str(exc)[:500], "provider": "execution_approval_service"})

    try:
        if get_ticket(ticket_id) is None:
            raise KeyError(ticket_id)
        updated = add_ticket_report(
            ticket_id,
            TicketReportRequest(
                reporter_employee_id="clara",
                reporter_role="AI Team OS Manager",
                content=(
                    f"LangGraph approval resumed: {approval_ref}.\n\n"
                    f"Run {run_id} completed after the same interrupted graph thread resumed. "
                    "The result is now eligible to propose governed Assets."
                ),
                evidence=[
                    approval_ref,
                    "langgraph:fixture-approved-resume",
                    "lg-fixture-approved-resume",
                    ".aiteamos/traces/fixture-approved-resume.jsonl",
                ],
                report_type="approval_resumed",
                source_run_id=run_id,
            ),
        )
        ticket_report_id = updated.reports[-1].id if updated.reports else ""
    except Exception as exc:
        blockers.append({"reason": "approval_resume_ticket_report_failed", "detail": str(exc)[:500], "provider": "ticket_service"})

    return {
        "approval_record": reviewed,
        "ticket_report_id": ticket_report_id,
        "provider_blockers": blockers,
    }


def _fixture_propose_memory_asset_candidate(response: dict[str, Any], *, ticket_report_id: str = "") -> dict[str, Any]:
    from aiteamos_api.read.asset_candidate_service import upsert_asset_candidate_from_memory_candidate
    from aiteamos_api.read.memory_service import list_memory_candidates, propose_memory_from_chat_turn

    run_id = _text(response.get("run_id")) or "fixture-approved-resume"
    metadata = _record(response.get("run_metadata"))
    execution = _record(metadata.get("execution"))
    result = _record(execution.get("result"))
    ticket_keys = [_text(item) for item in response.get("ticket_keys", []) if _text(item)] if isinstance(response.get("ticket_keys"), list) else []
    ticket_suffix = _fixture_safe_ref(ticket_keys[0] if ticket_keys else "rd-approval-fixture")
    memory_run_id = f"{run_id}-{ticket_suffix}"
    trace_path = f".aiteamos/traces/{memory_run_id}.jsonl"
    candidate = propose_memory_from_chat_turn(
        run_id=memory_run_id,
        thread_id=_text(response.get("thread_id")) or "employee-clara-approval-fixture",
        employee_id="clara",
        employee_display_name="Clara",
        user_message="Trigger approval fixture.",
        assistant_reply=_text(response.get("reply")),
        ticket_keys=ticket_keys or ["rd-approval-fixture"],
        trace_path=trace_path,
        source_report_id=ticket_report_id or _text(next((item.get("ref") for item in _records(result.get("ticket_report_refs"))), "")),
        evidence_id=_text(next((item.get("ref") for item in _records(result.get("evidence_refs"))), "")),
        recalled_memory_refs=_records(metadata.get("recalled_memory_refs")),
        action_plan={"action": _text(execution.get("action")) or "implement_ticket"},
    )
    if candidate is None:
        candidate = next(
            (
                item
                for item in list_memory_candidates()
                if (
                    (
                        _text(item.provenance.get("source_run_id")) == memory_run_id
                        or item.source_ref == trace_path
                    )
                    and _text(item.provenance.get("source_ticket_id")) in set(ticket_keys or ["rd-approval-fixture"])
                )
            ),
            None,
        )
    if candidate is None:
        return {
            "kind": "memory_candidate",
            "count": 0,
            "source_run_id": memory_run_id,
            "review_required": True,
            "status": "blocked",
            "blocker": "memory_candidate_not_created",
        }
    asset_candidate = upsert_asset_candidate_from_memory_candidate(candidate)
    return {
        "kind": "memory_candidate",
        "id": asset_candidate.id,
        "candidate_id": candidate.id,
        "source_candidate_id": asset_candidate.source_candidate_id,
        "asset_id": asset_candidate.asset_id,
        "asset_type": asset_candidate.asset_type,
        "status": asset_candidate.status,
        "review_state": asset_candidate.review_state,
        "source_run_id": run_id,
        "source_ticket_id": _text(candidate.provenance.get("source_ticket_id")),
        "source_report_id": _text(candidate.provenance.get("source_report_id")),
        "evidence_id": _text(candidate.provenance.get("evidence_id")),
        "provider": asset_candidate.provider,
        "provider_ref": asset_candidate.provider_ref,
        "review_required": asset_candidate.review_state not in {"approved", "accepted", "validated"},
    }


def _fixture_complete_after_resume(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    approval_ref = _text(state.get("approval_ref")) or "approval-fixture-1"
    ticket_id = _text(state.get("ticket_key")) or _text(_record(state.get("ticket_binding")).get("ticket_id")) or "rd-approval-fixture"
    response = fixture_response(
        approval_requests=[],
        reply="Approved fixture resume completed.",
        run_id="fixture-approved-resume",
        status="completed",
        ticket_id=ticket_id,
    )
    review_result = _fixture_review_approval_and_record_ticket_report(response, approval_ref)
    ticket_report_id = _text(review_result.get("ticket_report_id"))
    if ticket_report_id:
        result = _record(_record(response["run_metadata"]).get("execution")).get("result")
        if isinstance(result, dict):
            result["ticket_report_refs"] = [{"kind": "approval_resumed", "ref": ticket_report_id}]
    asset_candidate = _fixture_propose_memory_asset_candidate(response, ticket_report_id=ticket_report_id)
    provider_blockers = _records(review_result.get("provider_blockers"))
    return {
        "aiteamos_chat_response": response,
        "final_response": response["reply"],
        "approval_requests": [],
        "approval_records": [review_result["approval_record"]] if isinstance(review_result.get("approval_record"), dict) and review_result["approval_record"] else _records(state.get("approval_records")),
        "linked_assets": [{"kind": "runtime_mutation", "ref": "artifact-approved-fixture"}],
        "asset_candidates": [asset_candidate],
        "provenance_events": [
            *_records(_record(_record(response["run_metadata"]).get("scoped_context")).get("universal_context").get("provenance_summary")),
            {"kind": "approval_resumed", "source_ref": approval_ref, "scope_ref": ticket_id},
            *([{"kind": "ticket_report", "source_ref": ticket_report_id, "scope_ref": ticket_id}] if ticket_report_id else []),
        ],
        "provider_blockers": provider_blockers,
        "runtime_status": {
            "executor": "langgraph",
            "graph": "aiteamos_workbench_approval_fixture",
            "current_node": "final_response",
            "status": "completed",
            "run_id": "fixture-approved-resume",
            "checkpoint_ref": "langgraph:fixture-approved-resume",
            "executor_session_ref": "lg-fixture-approved-resume",
            "approval_ref": approval_ref,
            "ticket_report_id": ticket_report_id,
        },
        "workbench_panels": {
            "active_ticket": True,
            "employee": True,
            "assets": True,
            "approval": True,
            "provenance": True,
            "provider_blockers": bool(provider_blockers),
        },
        "messages": [AIMessage(content=response["reply"])],
    }


def _fixture_route_after_prepare(state: AITeamOSWorkbenchState) -> Literal["approval_interrupt", "finish_recall"]:
    runtime_status = _record(state.get("runtime_status"))
    if _text(runtime_status.get("current_node")) == "asset_recall":
        return "finish_recall"
    return "approval_interrupt"


def _fixture_finish_recall(state: AITeamOSWorkbenchState) -> dict[str, Any]:
    return {}


def build_approval_fixture_graph(checkpointer: Any | None = None):
    builder = StateGraph(AITeamOSWorkbenchState)
    builder.add_node("prepare_needs_approval", _fixture_prepare_needs_approval)
    builder.add_node("approval_interrupt", _fixture_approval_interrupt)
    builder.add_node("complete_after_resume", _fixture_complete_after_resume)
    builder.add_node("finish_recall", _fixture_finish_recall)
    builder.add_edge(START, "prepare_needs_approval")
    builder.add_conditional_edges(
        "prepare_needs_approval",
        _fixture_route_after_prepare,
        {
            "approval_interrupt": "approval_interrupt",
            "finish_recall": "finish_recall",
        },
    )
    builder.add_edge("approval_interrupt", "complete_after_resume")
    builder.add_edge("complete_after_resume", END)
    builder.add_edge("finish_recall", END)
    return builder.compile(checkpointer=checkpointer) if checkpointer is not None else builder.compile()


approval_fixture_graph = build_approval_fixture_graph()
