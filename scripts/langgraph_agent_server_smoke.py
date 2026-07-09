#!/usr/bin/env python3
"""Run a repeatable smoke against a running LangGraph Agent Server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
SERVICES_API_DIR = ROOT_DIR / "services" / "api"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke a running LangGraph Agent Server with the AITeamOS Workbench graph.")
    parser.add_argument("--url", default=os.environ.get("AITEAMOS_LANGGRAPH_URL", "http://127.0.0.1:2024"))
    parser.add_argument("--assistant-id", default=os.environ.get("AITEAMOS_LANGGRAPH_ASSISTANT_ID", "aiteamos_workbench"))
    parser.add_argument("--message", default="List employees")
    parser.add_argument("--employee-id", default="clara")
    parser.add_argument("--thread-id", default="agent-server-smoke-clara")
    parser.add_argument("--ticket-key", default="")
    parser.add_argument("--runtime-run-id", default="", help="Optional deterministic LangGraph runtime run_id.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--expect-status", default="completed")
    parser.add_argument("--expect-current-node", default="final_response")
    parser.add_argument("--expect-context-source", default="langgraph_context_node")
    parser.add_argument("--expect-approval-ref", default="")
    parser.add_argument("--expect-approval-request-count", type=int, default=-1)
    parser.add_argument("--min-provider-blockers", type=int, default=-1)
    parser.add_argument("--max-provider-blockers", type=int, default=-1)
    parser.add_argument("--expect-provider-blocker-reason", default="")
    parser.add_argument("--min-asset-candidates", type=int, default=-1)
    parser.add_argument("--min-linked-assets", type=int, default=-1)
    parser.add_argument("--resume-approval-ref", default="")
    parser.add_argument("--review-resume-approval", action="store_true", help="Mark the resume approval as approved before sending the LangGraph resume command.")
    parser.add_argument("--review-approval-ref", default="", help="Review an approval after the initial Agent Server run without sending a resume command.")
    parser.add_argument("--review-approval-status", default="", help="Approval review status for --review-approval-ref, for example rejected, changes_requested, or evidence_requested.")
    parser.add_argument("--review-approval-reason", default="Reviewed by LangGraph Agent Server smoke.")
    parser.add_argument("--expect-review-status", default="")
    parser.add_argument("--expect-review-ticket-status", default="")
    parser.add_argument("--expect-review-ticket-report-type", default="")
    parser.add_argument("--expect-review-timeline-status", default="")
    parser.add_argument("--resume-approved-capabilities", default="repo:write")
    parser.add_argument("--expect-resume-status", default="completed")
    parser.add_argument("--expect-resume-current-node", default="final_response")
    parser.add_argument("--require-resume-ticket-report", action="store_true")
    parser.add_argument("--min-resume-asset-candidates", type=int, default=-1)
    parser.add_argument("--min-resume-linked-assets", type=int, default=-1)
    parser.add_argument("--expect-action", default="")
    parser.add_argument("--expect-handoff-target", default="")
    parser.add_argument("--expect-handoff-status", default="")
    parser.add_argument("--expect-handoff-memory-scope", default="")
    parser.add_argument("--expect-handoff-risk-level", default="")
    parser.add_argument("--expect-handoff-risk-allowed", action="store_true")
    parser.add_argument("--min-handoff-refs", type=int, default=-1)
    parser.add_argument("--expect-visible-response-version", default="")
    parser.add_argument("--expect-visible-display-state", default="")
    parser.add_argument("--expect-visible-assistant-contains", default="")
    parser.add_argument("--output", default="", help="Optional path to write the JSON result.")
    args = parser.parse_args()

    workspace_dir = Path(args.workspace_dir).expanduser().resolve()
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    try:
        payload = run_smoke(
            url=args.url,
            assistant_id=args.assistant_id,
            message=args.message,
            employee_id=args.employee_id,
            thread_id=args.thread_id,
            ticket_key=args.ticket_key,
            runtime_run_id=args.runtime_run_id,
            expect_status=args.expect_status,
            expect_current_node=args.expect_current_node,
            expect_context_source=args.expect_context_source,
            expect_approval_ref=args.expect_approval_ref,
            expect_approval_request_count=args.expect_approval_request_count,
            min_provider_blockers=args.min_provider_blockers,
            max_provider_blockers=args.max_provider_blockers,
            expect_provider_blocker_reason=args.expect_provider_blocker_reason,
            min_asset_candidates=args.min_asset_candidates,
            min_linked_assets=args.min_linked_assets,
            resume_approval_ref=args.resume_approval_ref,
            review_resume_approval=args.review_resume_approval,
            review_approval_ref=args.review_approval_ref,
            review_approval_status=args.review_approval_status,
            review_approval_reason=args.review_approval_reason,
            expect_review_status=args.expect_review_status,
            expect_review_ticket_status=args.expect_review_ticket_status,
            expect_review_ticket_report_type=args.expect_review_ticket_report_type,
            expect_review_timeline_status=args.expect_review_timeline_status,
            resume_approved_capabilities=_csv(args.resume_approved_capabilities),
            expect_resume_status=args.expect_resume_status,
            expect_resume_current_node=args.expect_resume_current_node,
            require_resume_ticket_report=args.require_resume_ticket_report,
            min_resume_asset_candidates=args.min_resume_asset_candidates,
            min_resume_linked_assets=args.min_resume_linked_assets,
            expect_action=args.expect_action,
            expect_handoff_target=args.expect_handoff_target,
            expect_handoff_status=args.expect_handoff_status,
            expect_handoff_memory_scope=args.expect_handoff_memory_scope,
            expect_handoff_risk_level=args.expect_handoff_risk_level,
            expect_handoff_risk_allowed=args.expect_handoff_risk_allowed,
            min_handoff_refs=args.min_handoff_refs,
            expect_visible_response_version=args.expect_visible_response_version,
            expect_visible_display_state=args.expect_visible_display_state,
            expect_visible_assistant_contains=args.expect_visible_assistant_contains,
            workspace_dir=workspace_dir,
        )
    except Exception as exc:
        payload = {
            "schema": "aiteamos.langgraph_agent_server_smoke.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "url": args.url,
            "assistant_id": args.assistant_id,
            "workspace_dir": str(workspace_dir),
            "error": str(exc),
        }
        _write_output(payload, args.output)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    _write_output(payload, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


def run_smoke(
    *,
    url: str,
    assistant_id: str,
    message: str,
    employee_id: str,
    thread_id: str,
    ticket_key: str,
    runtime_run_id: str,
    expect_status: str,
    expect_current_node: str,
    expect_context_source: str,
    expect_approval_ref: str,
    expect_approval_request_count: int,
    min_provider_blockers: int,
    max_provider_blockers: int,
    expect_provider_blocker_reason: str,
    min_asset_candidates: int,
    min_linked_assets: int,
    resume_approval_ref: str,
    review_resume_approval: bool,
    review_approval_ref: str,
    review_approval_status: str,
    review_approval_reason: str,
    expect_review_status: str,
    expect_review_ticket_status: str,
    expect_review_ticket_report_type: str,
    expect_review_timeline_status: str,
    resume_approved_capabilities: list[str],
    expect_resume_status: str,
    expect_resume_current_node: str,
    require_resume_ticket_report: bool,
    min_resume_asset_candidates: int,
    min_resume_linked_assets: int,
    expect_action: str,
    expect_handoff_target: str,
    expect_handoff_status: str,
    expect_handoff_memory_scope: str,
    expect_handoff_risk_level: str,
    expect_handoff_risk_allowed: bool,
    min_handoff_refs: int,
    expect_visible_response_version: str,
    expect_visible_display_state: str,
    expect_visible_assistant_contains: str,
    workspace_dir: Path,
) -> dict[str, Any]:
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url=url)
    try:
        thread = client.threads.create(metadata={"source": "aiteamos_langgraph_agent_server_smoke"})
        agent_thread_id = _thread_id(thread)
        runtime_config = {"run_id": runtime_run_id.strip()} if runtime_run_id.strip() else {}
        config = {
            "configurable": {
                "thread_id": thread_id,
                "target_employee_id": employee_id,
                "employee_id": employee_id,
                **({"ticket_key": ticket_key} if ticket_key else {}),
                **({"runtime_config": runtime_config} if runtime_config else {}),
            }
        }
        state = client.runs.wait(
            agent_thread_id,
            assistant_id,
            input={
                "messages": [{"role": "user", "content": message}],
                "employee_id": employee_id,
                **({"ticket_key": ticket_key} if ticket_key else {}),
            },
            config=config,
        )
        state_payload = _dump(state)
        resumed_state_payload: dict[str, Any] = {}
        if resume_approval_ref:
            if review_resume_approval:
                _approve_for_resume(workspace_dir=workspace_dir, approval_ref=resume_approval_ref)
            resumed_state = client.runs.wait(
                agent_thread_id,
                assistant_id,
                command={
                    "resume": {
                        "approval_ref": resume_approval_ref,
                        "approval_refs": [resume_approval_ref],
                        "approved_capabilities": resume_approved_capabilities,
                    }
                },
                config=config,
            )
            resumed_state_payload = _dump(resumed_state)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            close()

    runtime_status = _record(state_payload.get("runtime_status"))
    action_plan = _record(state_payload.get("action_plan"))
    context_bundle = _record(state_payload.get("context_bundle"))
    approval_requests = state_payload.get("approval_requests") if isinstance(state_payload.get("approval_requests"), list) else []
    provider_blockers = state_payload.get("provider_blockers") if isinstance(state_payload.get("provider_blockers"), list) else []
    asset_candidates = state_payload.get("asset_candidates") if isinstance(state_payload.get("asset_candidates"), list) else []
    linked_assets = state_payload.get("linked_assets") if isinstance(state_payload.get("linked_assets"), list) else []
    handoff_decision = _record(state_payload.get("handoff_decision"))
    handoff_policy = _record(handoff_decision.get("policy"))
    handoff_summary = _record(state_payload.get("handoff_summary"))
    ticket_handoff_refs = state_payload.get("ticket_handoff_refs") if isinstance(state_payload.get("ticket_handoff_refs"), list) else []
    visible_response = _visible_response(state_payload)
    visible_assistant = _record(visible_response.get("assistant_message"))
    approval_ref = _approval_ref(state_payload)
    review_summary: dict[str, Any] = {}
    if review_approval_status.strip():
        target_review_approval_ref = review_approval_ref.strip() or expect_approval_ref.strip() or approval_ref
        if target_review_approval_ref:
            review_summary = _review_approval_for_smoke(
                workspace_dir=workspace_dir,
                approval_ref=target_review_approval_ref,
                status=review_approval_status,
                reason=review_approval_reason,
            )
    checks = [
        _check("runtime_status.status", runtime_status.get("status"), expect_status),
        _check("runtime_status.current_node", runtime_status.get("current_node"), expect_current_node),
    ]
    if expect_context_source:
        checks.append(_check("context_bundle.source", context_bundle.get("source"), expect_context_source))
    if expect_action:
        checks.append(_check("action_plan.action", action_plan.get("action"), expect_action))
    if expect_handoff_target:
        checks.append(_check("handoff_decision.target_employee_id", handoff_decision.get("target_employee_id"), expect_handoff_target))
    if expect_handoff_status:
        checks.append(_check("handoff_summary.status", handoff_summary.get("status"), expect_handoff_status))
    if expect_handoff_memory_scope:
        checks.append(
            _check_contains(
                "handoff_decision.policy.matched_memory_scopes",
                _string_list(handoff_policy.get("matched_memory_scopes")),
                expect_handoff_memory_scope,
            )
        )
    if expect_handoff_risk_level:
        checks.append(_check("handoff_decision.policy.risk_level", handoff_policy.get("risk_level"), expect_handoff_risk_level))
    if expect_handoff_risk_allowed:
        checks.append(_check_bool("handoff_decision.policy.risk_allowed", handoff_policy.get("risk_allowed"), True))
    if min_handoff_refs >= 0:
        checks.append(_check_at_least("ticket_handoff_ref_count", len(ticket_handoff_refs), min_handoff_refs))
    if expect_visible_response_version:
        checks.append(_check("visible_response.version", visible_response.get("version"), expect_visible_response_version))
    if expect_visible_display_state:
        checks.append(_check("visible_response.display_state", visible_response.get("display_state"), expect_visible_display_state))
    if expect_visible_assistant_contains:
        checks.append(
            _check_text_contains(
                "visible_response.assistant_message.content",
                visible_assistant.get("content"),
                expect_visible_assistant_contains,
            )
        )
    if expect_approval_ref:
        checks.append(_check("approval_ref", approval_ref, expect_approval_ref))
    if expect_approval_request_count >= 0:
        checks.append(_check_int("approval_request_count", len(approval_requests), expect_approval_request_count))
    if min_provider_blockers >= 0:
        checks.append(_check_at_least("provider_blocker_count", len(provider_blockers), min_provider_blockers))
    if max_provider_blockers >= 0:
        checks.append(_check_at_most("provider_blocker_count", len(provider_blockers), max_provider_blockers))
    if expect_provider_blocker_reason:
        checks.append(_check_contains("provider_blocker.reason", _provider_blocker_reasons(provider_blockers), expect_provider_blocker_reason))
    if min_asset_candidates >= 0:
        checks.append(_check_at_least("asset_candidate_count", len(asset_candidates), min_asset_candidates))
    if min_linked_assets >= 0:
        checks.append(_check_at_least("linked_asset_count", len(linked_assets), min_linked_assets))
    if review_approval_status.strip():
        checks.append(_check_present("review.approval_ref", review_summary.get("approval_ref")))
    if expect_review_status:
        checks.append(_check("review.status", review_summary.get("approval_status"), expect_review_status))
    if expect_review_ticket_status:
        checks.append(_check("review.ticket_status", review_summary.get("ticket_status"), expect_review_ticket_status))
    if expect_review_ticket_report_type:
        checks.append(
            _check_contains(
                "review.ticket_report_types",
                _string_list(review_summary.get("ticket_report_types")),
                expect_review_ticket_report_type,
            )
        )
    if expect_review_timeline_status:
        checks.append(
            _check_contains(
                "review.timeline_statuses",
                _string_list(review_summary.get("timeline_statuses")),
                expect_review_timeline_status,
            )
        )
    resume_summary: dict[str, Any] = {}
    if resume_approval_ref:
        resume_runtime_status = _record(resumed_state_payload.get("runtime_status"))
        actual_resume_approval_ref = _approval_ref(resumed_state_payload)
        resume_ticket_report_id = str(resume_runtime_status.get("ticket_report_id") or "").strip()
        if require_resume_ticket_report and not resume_ticket_report_id:
            resume_ticket_id = _ticket_id(resumed_state_payload) or _ticket_id(state_payload) or ticket_key
            resume_ticket_report_id = _latest_ticket_report_id(workspace_dir=workspace_dir, ticket_id=resume_ticket_id)
        checks.extend(
            [
                _check("resume.runtime_status.status", resume_runtime_status.get("status"), expect_resume_status),
                _check("resume.runtime_status.current_node", resume_runtime_status.get("current_node"), expect_resume_current_node),
                _check("resume.approval_ref", actual_resume_approval_ref, resume_approval_ref),
            ]
        )
        resume_asset_candidate_count = len(resumed_state_payload.get("asset_candidates") or [])
        resume_linked_asset_count = len(resumed_state_payload.get("linked_assets") or [])
        if require_resume_ticket_report:
            checks.append(_check_present("resume.ticket_report_id", resume_ticket_report_id))
        if min_resume_asset_candidates >= 0:
            checks.append(_check_at_least("resume.asset_candidate_count", resume_asset_candidate_count, min_resume_asset_candidates))
        if min_resume_linked_assets >= 0:
            checks.append(_check_at_least("resume.linked_asset_count", resume_linked_asset_count, min_resume_linked_assets))
        resume_summary = {
            "runtime_status": resume_runtime_status,
            "approval_ref": actual_resume_approval_ref,
            "active_ticket": resumed_state_payload.get("active_ticket"),
            "ticket_report_id": resume_ticket_report_id,
            "asset_candidate_count": resume_asset_candidate_count,
            "linked_asset_count": resume_linked_asset_count,
        }
    passed = all(check["passed"] for check in checks)
    return {
        "schema": "aiteamos.langgraph_agent_server_smoke.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "url": url,
        "assistant_id": assistant_id,
        "workspace_dir": str(workspace_dir),
        "agent_thread_id": agent_thread_id,
        "business_thread_id": thread_id,
        "checks": checks,
        "summary": {
            "runtime_status": runtime_status,
            "action": action_plan.get("action"),
            "approval_ref": approval_ref,
            "runtime_run_id": runtime_run_id,
            "employee_id": state_payload.get("employee_id"),
            "active_ticket": state_payload.get("active_ticket"),
            "approval_request_count": len(approval_requests),
            "provider_blocker_count": len(provider_blockers),
            "provider_blocker_reasons": _provider_blocker_reasons(provider_blockers),
            "asset_candidate_count": len(asset_candidates),
            "linked_asset_count": len(linked_assets),
            "handoff_decision": handoff_decision,
            "handoff_summary": handoff_summary,
            "ticket_handoff_ref_count": len(ticket_handoff_refs),
            "ticket_handoff_refs": ticket_handoff_refs,
            "visible_response": {
                "version": str(visible_response.get("version") or ""),
                "display_state": str(visible_response.get("display_state") or ""),
                "assistant_message": str(visible_assistant.get("content") or "")[:240],
                "ticket_ref_count": len(visible_response.get("ticket_refs") or []),
                "asset_ref_count": len(visible_response.get("asset_refs") or []),
                "memory_ref_count": len(visible_response.get("memory_refs") or []),
                "provider_blocker_count": len(visible_response.get("provider_blockers") or []),
            },
            **({"review": review_summary} if review_summary else {}),
            **({"resume": resume_summary} if resume_summary else {}),
        },
    }


def _thread_id(thread: Any) -> str:
    payload = _dump(thread)
    return str(payload.get("thread_id") or payload.get("id") or "")


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
        return payload if isinstance(payload, dict) else {}
    to_dict = getattr(value, "dict", None)
    if callable(to_dict):
        payload = to_dict()
        return payload if isinstance(payload, dict) else {}
    return {}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _approval_ref(state_payload: dict[str, Any]) -> str:
    approval_ref = state_payload.get("approval_ref")
    if approval_ref:
        return str(approval_ref)
    approval_requests = state_payload.get("approval_requests")
    if isinstance(approval_requests, list) and approval_requests:
        first = approval_requests[0]
        if isinstance(first, dict):
            return str(first.get("approval_ref") or first.get("id") or "")
    approval_records = state_payload.get("approval_records")
    if isinstance(approval_records, list) and approval_records:
        first = approval_records[0]
        if isinstance(first, dict):
            return str(first.get("id") or "")
    return ""


def _ticket_id(state_payload: dict[str, Any]) -> str:
    active_ticket = state_payload.get("active_ticket")
    if isinstance(active_ticket, dict) and active_ticket.get("id"):
        return str(active_ticket.get("id") or "")
    ticket_binding = state_payload.get("ticket_binding")
    if isinstance(ticket_binding, dict) and ticket_binding.get("ticket_id"):
        return str(ticket_binding.get("ticket_id") or "")
    return ""


def _visible_response(state_payload: dict[str, Any]) -> dict[str, Any]:
    response = _record(state_payload.get("aiteamos_chat_response"))
    metadata = _record(response.get("run_metadata"))
    visible = _record(metadata.get("visible_response"))
    if visible:
        return visible
    messages = state_payload.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            message_record = _record(message)
            response_metadata = _record(message_record.get("response_metadata"))
            visible = _record(response_metadata.get("visible_response"))
            if visible:
                return visible
    return {}


def _latest_ticket_report_id(*, workspace_dir: Path, ticket_id: str) -> str:
    if not ticket_id.strip():
        return ""
    previous_workspace = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    try:
        from aiteamos_api.read.ticket_service import get_ticket

        ticket = get_ticket(ticket_id.strip())
    finally:
        if previous_workspace is None:
            os.environ.pop("AITEAMOS_WORKSPACE_DIR", None)
        else:
            os.environ["AITEAMOS_WORKSPACE_DIR"] = previous_workspace
    if ticket is None or not ticket.reports:
        return ""
    return str(ticket.reports[-1].id or "")


def _review_approval_for_smoke(*, workspace_dir: Path, approval_ref: str, status: str, reason: str) -> dict[str, Any]:
    previous_workspace = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_dir)
    try:
        from aiteamos_api.read.execution_approval_service import ExecutionApprovalReviewRequest, review_execution_approval
        from aiteamos_api.read.ticket_loop_service import ticket_loop_timeline
        from aiteamos_api.read.ticket_service import get_ticket

        reviewed = review_execution_approval(
            workspace_dir=workspace_dir,
            approval_id=approval_ref,
            review=ExecutionApprovalReviewRequest(
                status=status,
                reviewer_employee_id="clara",
                reason=reason.strip() or "Reviewed by LangGraph Agent Server smoke.",
            ),
        )
        ticket_status = ""
        ticket_report_types: list[str] = []
        ticket_report_ids: list[str] = []
        timeline_statuses: list[str] = []
        timeline_error = ""
        if reviewed.ticket_id:
            ticket = get_ticket(reviewed.ticket_id)
            if ticket is not None:
                ticket_status = str(getattr(ticket, "status", "") or "")
                for report in getattr(ticket, "reports", []) or []:
                    report_type = str(getattr(report, "report_type", "") or "")
                    if report_type:
                        ticket_report_types.append(report_type)
                    report_id = str(getattr(report, "id", "") or "")
                    if report_id:
                        ticket_report_ids.append(report_id)
            try:
                timeline = ticket_loop_timeline(reviewed.ticket_id, workspace_dir=workspace_dir)
                timeline_statuses = [str(item.status or "") for item in timeline.items if str(item.status or "")]
            except Exception as exc:
                timeline_error = str(exc)
        return {
            "approval_ref": reviewed.id,
            "approval_status": reviewed.status,
            "ticket_id": reviewed.ticket_id,
            "ticket_status": ticket_status,
            "ticket_report_types": ticket_report_types,
            "ticket_report_ids": ticket_report_ids,
            "timeline_statuses": timeline_statuses,
            **({"timeline_error": timeline_error} if timeline_error else {}),
        }
    finally:
        if previous_workspace is None:
            os.environ.pop("AITEAMOS_WORKSPACE_DIR", None)
        else:
            os.environ["AITEAMOS_WORKSPACE_DIR"] = previous_workspace


def _approve_for_resume(*, workspace_dir: Path, approval_ref: str) -> None:
    from aiteamos_api.read.execution_approval_service import ExecutionApprovalReviewRequest, review_execution_approval

    review_execution_approval(
        workspace_dir=workspace_dir,
        approval_id=approval_ref,
        review=ExecutionApprovalReviewRequest(
            status="approved",
            reviewer_employee_id="clara",
            reason="Approved by LangGraph Agent Server smoke before resume.",
        ),
    )


def _check(name: str, actual: Any, expected: str) -> dict[str, Any]:
    actual_text = str(actual or "")
    return {
        "name": name,
        "expected": expected,
        "actual": actual_text,
        "passed": actual_text == expected,
    }


def _check_present(name: str, actual: Any) -> dict[str, Any]:
    actual_text = str(actual or "")
    return {
        "name": name,
        "expected": "present",
        "actual": actual_text,
        "passed": bool(actual_text),
    }


def _check_bool(name: str, actual: Any, expected: bool) -> dict[str, Any]:
    return {
        "name": name,
        "expected": expected,
        "actual": bool(actual),
        "passed": bool(actual) is expected,
    }


def _check_at_least(name: str, actual: int, expected: int) -> dict[str, Any]:
    return {
        "name": name,
        "expected": f">={expected}",
        "actual": str(actual),
        "passed": actual >= expected,
    }


def _check_at_most(name: str, actual: int, expected: int) -> dict[str, Any]:
    return {
        "name": name,
        "expected": f"<={expected}",
        "actual": str(actual),
        "passed": actual <= expected,
    }


def _check_int(name: str, actual: int, expected: int) -> dict[str, Any]:
    return {
        "name": name,
        "expected": str(expected),
        "actual": str(actual),
        "passed": actual == expected,
    }


def _check_contains(name: str, actual: list[str], expected: str) -> dict[str, Any]:
    return {
        "name": name,
        "expected": expected,
        "actual": ",".join(actual),
        "passed": expected in actual,
    }


def _check_text_contains(name: str, actual: Any, expected: str) -> dict[str, Any]:
    actual_text = str(actual or "")
    return {
        "name": name,
        "expected": f"contains {expected}",
        "actual": actual_text[:240],
        "passed": expected in actual_text,
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return []


def _provider_blocker_reasons(provider_blockers: list[Any]) -> list[str]:
    reasons: list[str] = []
    for item in provider_blockers:
        if isinstance(item, dict):
            reason = str(item.get("reason") or "").strip()
            if reason:
                reasons.append(reason)
    return reasons


def _write_output(payload: dict[str, Any], output: str) -> None:
    if not output:
        return
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
