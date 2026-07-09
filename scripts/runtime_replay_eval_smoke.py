#!/usr/bin/env python3
"""Emit deterministic Runtime Replay coverage evidence through existing services."""

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
SMOKE_SCHEMA = "aiteamos.runtime_replay_eval_smoke.v1"
if str(SERVICES_API_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICES_API_DIR))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Runtime Replay coverage smoke evidence.")
    parser.add_argument("--workspace-dir", default=os.environ.get("AITEAMOS_WORKSPACE_DIR", str(ROOT_DIR)))
    parser.add_argument("--output", default="", help="Optional path to write the JSON result.")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_dir).expanduser().resolve()
    try:
        payload = run_smoke(workspace_root=workspace_root)
    except Exception as exc:
        payload = {
            "schema": SMOKE_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "blocked",
            "workspace_dir": str(workspace_root),
            "error": str(exc),
        }
    _write_output(payload, args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


def run_smoke(*, workspace_root: Path) -> dict[str, Any]:
    from aiteamos_api.read.chat_action_plan import ChatActionPlan
    from aiteamos_api.read.execution_contract import ExecutionRequest, ExecutionResult, TicketBinding
    from aiteamos_api.read.execution_replay_service import ExecutionReplayService
    from aiteamos_api.read.execution_result_ingestion_service import ExecutionResultIngestionService
    from aiteamos_api.read.execution_session_store import load_execution_sessions
    from aiteamos_api.read.ticket_service import (
        TicketBackendSettingsUpdateRequest,
        TicketCreateRequest,
        create_ticket,
        update_ticket_backend_settings,
    )

    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    update_ticket_backend_settings(
        TicketBackendSettingsUpdateRequest(mode="local_file", local_file_path=".aiteamos/tickets/index.json")
    )
    trace_ref = ".aiteamos/traces/runtime-replay-smoke.jsonl"
    trace_path = workspace_root / trace_ref
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(
        json.dumps(
            {
                "event": "trace.step",
                "current_graph_node": "final_response",
                "authorization": "Bearer secret",
                "data": {
                    "token": "secret-token",
                    "visible": "yes",
                    "checkpoint_ref": "claude_code:runtime-replay-smoke",
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    ticket = create_ticket(
        TicketCreateRequest(
            title="Runtime Replay coverage smoke",
            description="Verify Ticket/Employee/Asset/Memory/Evidence/Trace replay coverage without a new observability layer.",
            ticket_type="rd",
            assigned_employee_id="alex",
            assigned_role="AI RD / Implementer",
            actor_employee_id="clara",
            actor_role="AI Team OS Manager",
            source_run_id="seed-runtime-replay-smoke",
        )
    )
    request_id = f"runtime-replay-smoke-{ticket.id}"
    request = ExecutionRequest(
        request_id=request_id,
        workspace_id=str(workspace_root),
        employee_id="alex",
        ticket_id=ticket.id,
        ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
        action_plan=ChatActionPlan(action="append_report", arguments={"content": "Runtime replay smoke"}),
        task_context={
            "universal_context": {
                "provenance_summary": [
                    {
                        "kind": "ticket",
                        "source_kind": "ticket_service",
                        "source_ref": ticket.id,
                        "scope_kind": "ticket",
                        "scope_ref": ticket.id,
                    }
                ]
            }
        },
        trace_context={
            "run_id": "run-runtime-replay-smoke",
            "thread_id": "thread-runtime-replay-smoke",
            "trace_ref": trace_ref,
        },
    )
    now = datetime.now(timezone.utc).isoformat()
    result = ExecutionResult(
        request_id=request.request_id,
        executor_id="claude_code",
        status="completed",
        report="Runtime Replay smoke completed with traceable evidence.",
        output_ticket_id=ticket.id,
        executor_session_ref="claude_code-runtime-replay-smoke",
        checkpoint_ref="claude_code:runtime-replay-smoke",
        trace_ref=trace_ref,
        artifacts=[
            {"kind": "runtime_session_artifact", "ref": "artifact://runtime-replay-smoke", "api_key": "secret"},
            {"kind": "asset_link", "ref": "asset-runtime-replay-smoke"},
            {
                "kind": "employee_handoff_request",
                "ticket_id": ticket.id,
                "from_employee_id": "alex",
                "from_role": "AI RD / Implementer",
                "to_employee_id": "victor",
                "to_role": "AI Runtime Owner",
                "content": "Runtime replay handoff policy requires Victor scoped memory and critical-risk ownership.",
                "lane": "rd",
                "confidence": 0.94,
                "policy": {
                    "policy_aware": True,
                    "required_memory_scopes": ["employee:victor"],
                    "matched_memory_scopes": ["employee:victor"],
                    "available_memory_scopes": ["aiteamos", "employee:victor"],
                    "memory_scope_match": "matched",
                    "risk_level": "critical",
                    "max_risk_level": "critical",
                    "risk_allowed": True,
                },
                "provenance": {
                    "source_kind": "langgraph_handoff_decision",
                    "source_ref": request_id,
                    "scope_kind": "ticket",
                    "scope_ref": ticket.id,
                },
            },
        ],
        evidence=[{"kind": "test_evidence", "ref": "pytest::runtime-replay-smoke::passed"}],
        tool_events=[
            {
                "event": "universal_agent.tool.completed",
                "data": {
                    "output_refs": [
                        {"kind": "ticket", "ref": ticket.id},
                        {"kind": "memory", "ref": "mem-runtime-replay-smoke"},
                        {"kind": "asset", "ref": "asset-runtime-replay-smoke"},
                    ],
                    "provenance": [{"source_kind": "aiteamos_service", "source_ref": "runtime_replay_eval_smoke"}],
                },
            }
        ],
        memory_candidates=[
            {
                "id": "mem-runtime-replay-smoke",
                "asset_id": "asset-runtime-replay-smoke",
                "content": "Runtime Replay coverage must include Ticket, Employee, trace, evidence, checkpoint, and Asset/Memory refs.",
                "memory_type": "lesson",
                "source_kind": "runtime_replay_eval_smoke",
                "scope_kind": "ticket",
                "scope_ref": ticket.id,
                "confidence": 0.86,
                "tags": ["runtime-replay", "coverage"],
            }
        ],
        learning_delta={"current_graph_node": "final_response"},
        started_at=now,
        finished_at=now,
    )
    ingested = ExecutionResultIngestionService(workspace_dir=workspace_root).ingest(request, result)
    sessions = load_execution_sessions(workspace_root)
    session_key = _session_key_for_request(sessions, request.request_id, ticket.id)
    replay = ExecutionReplayService(workspace_dir=workspace_root).session_replay(session_key)
    coverage = _record(replay.get("coverage_summary"))
    coverage_map = _record(coverage.get("coverage"))
    refs = _record(coverage.get("refs"))
    counts = _record(coverage.get("counts"))
    trace_events = _records(replay.get("trace_events"))
    artifacts = _records(_record(replay.get("execution_artifacts")).get("artifacts"))
    handoff_summary = _record(replay.get("handoff_summary"))
    handoff_refs = _records(handoff_summary.get("refs"))
    timeline_events = [str(item.get("event") or "") for item in _records(replay.get("timeline"))]
    checks = [
        _check("coverage.schema", coverage.get("schema"), "execution_replay_coverage.v1"),
        _check("coverage.required_chain_complete", coverage.get("required_chain_complete"), True),
        _check("coverage.gaps", coverage.get("gaps"), []),
        _check("coverage.ticket", coverage_map.get("ticket"), True),
        _check("coverage.employee", coverage_map.get("employee"), True),
        _check("coverage.runtime", coverage_map.get("runtime"), True),
        _check("coverage.evidence", coverage_map.get("evidence"), True),
        _check("coverage.trace", coverage_map.get("trace"), True),
        _check("coverage.state", coverage_map.get("state"), True),
        _check("coverage.checkpoint", coverage_map.get("checkpoint"), True),
        _check("coverage.asset_or_memory", coverage_map.get("asset_or_memory"), True),
        _check("coverage.handoff", coverage_map.get("handoff"), True),
        _check("coverage.handoff_policy", coverage_map.get("handoff_policy"), True),
        _check_at_least("counts.handoff_ref_count", counts.get("handoff_ref_count"), 3),
        _check_contains("refs.ticket_refs", _strings(refs.get("ticket_refs")), ticket.id),
        _check_contains("refs.employee_refs", _strings(refs.get("employee_refs")), "alex"),
        _check_contains("refs.memory_refs", _strings(refs.get("memory_refs")), "mem-runtime-replay-smoke"),
        _check_contains("refs.asset_refs", _strings(refs.get("asset_refs")), "asset-runtime-replay-smoke"),
        _check_contains("refs.evidence_refs", _strings(refs.get("evidence_refs")), "pytest::runtime-replay-smoke::passed"),
        _check("handoff.schema", handoff_summary.get("schema"), "execution_replay_handoff_policy.v1"),
        _check("handoff.status", handoff_summary.get("status"), "employee_handoff_recorded"),
        _check("handoff.source_kind", handoff_summary.get("source_kind"), "execution_artifact"),
        _check("handoff.target_employee_id", handoff_summary.get("target_employee_id"), "victor"),
        _check("handoff.required_memory_scopes", handoff_summary.get("required_memory_scopes"), ["employee:victor"]),
        _check("handoff.matched_memory_scopes", handoff_summary.get("matched_memory_scopes"), ["employee:victor"]),
        _check("handoff.memory_scope_match", handoff_summary.get("memory_scope_match"), "matched"),
        _check("handoff.risk_level", handoff_summary.get("risk_level"), "critical"),
        _check("handoff.max_risk_level", handoff_summary.get("max_risk_level"), "critical"),
        _check("handoff.risk_allowed", handoff_summary.get("risk_allowed"), True),
        _check_contains("handoff.refs", [f"{item.get('kind')}:{item.get('ref')}" for item in handoff_refs], "employee:victor"),
        _check_contains("timeline.events", timeline_events, "employee_handoff_request"),
        _check_int("counts.timeline_event_count", counts.get("timeline_event_count"), len(_records(replay.get("timeline")))),
        _check_int("counts.trace_event_count", counts.get("trace_event_count"), 1),
        _check_int("counts.state_transition_count", counts.get("state_transition_count"), len(_records(replay.get("state_transitions")))),
        _check("redaction.trace.authorization", _first_record(trace_events).get("authorization"), "[redacted]"),
        _check("redaction.trace.token", _record(_first_record(trace_events).get("data")).get("token"), "[redacted]"),
        _check("redaction.trace.visible", _record(_first_record(trace_events).get("data")).get("visible"), "yes"),
        _check("redaction.artifact.api_key", _first_record(artifacts).get("api_key"), "[redacted]"),
        _check("ingestion.status", ingested.status, "completed"),
    ]
    passed = all(check["passed"] for check in checks)
    return {
        "schema": SMOKE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "workspace_dir": str(workspace_root),
        "checks": checks,
        "summary": {
            "ticket_id": ticket.id,
            "session_key": session_key,
            "request_id": request.request_id,
            "required_chain_complete": bool(coverage.get("required_chain_complete")),
            "gaps": _strings(coverage.get("gaps")),
            "coverage": coverage_map,
            "counts": counts,
            "handoff": bool(coverage_map.get("handoff")),
            "handoff_policy": bool(coverage_map.get("handoff_policy")),
            "handoff_status": str(handoff_summary.get("status") or ""),
            "handoff_target_employee_id": str(handoff_summary.get("target_employee_id") or ""),
            "handoff_lane": str(handoff_summary.get("lane") or ""),
            "handoff_required_memory_scopes": _strings(handoff_summary.get("required_memory_scopes")),
            "handoff_matched_memory_scopes": _strings(handoff_summary.get("matched_memory_scopes")),
            "handoff_memory_scope_match": str(handoff_summary.get("memory_scope_match") or ""),
            "handoff_risk_level": str(handoff_summary.get("risk_level") or ""),
            "handoff_max_risk_level": str(handoff_summary.get("max_risk_level") or ""),
            "handoff_risk_allowed": bool(handoff_summary.get("risk_allowed")),
            "handoff_ref_count": _to_int(counts.get("handoff_ref_count")),
            "handoff_refs": handoff_refs,
            "ticket_refs": _strings(refs.get("ticket_refs")),
            "employee_refs": _strings(refs.get("employee_refs")),
            "asset_refs": _strings(refs.get("asset_refs")),
            "memory_refs": _strings(refs.get("memory_refs")),
            "evidence_refs": _strings(refs.get("evidence_refs")),
            "checkpoint_refs": _strings(refs.get("checkpoint_refs")),
            "trace_refs": _strings(refs.get("trace_refs")),
            "trace_redacted": _first_record(trace_events).get("authorization") == "[redacted]"
            and _record(_first_record(trace_events).get("data")).get("token") == "[redacted]"
            and _record(_first_record(trace_events).get("data")).get("visible") == "yes",
            "artifact_secret_redacted": _first_record(artifacts).get("api_key") == "[redacted]",
        },
    }


def _session_key_for_request(sessions: dict[str, Any], request_id: str, ticket_id: str) -> str:
    for key, session in sessions.items():
        if (
            isinstance(session, dict)
            and session.get("last_request_id") == request_id
            and session.get("ticket_id") == ticket_id
        ):
            return str(key)
    raise RuntimeError(f"Runtime Replay smoke session was not recorded for request {request_id}")


def _write_output(payload: dict[str, Any], output: str) -> None:
    if not output:
        return
    path = Path(output).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _check(name: str, actual: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "passed": actual == expected, "actual": actual, "expected": expected}


def _check_int(name: str, actual: Any, expected: int) -> dict[str, Any]:
    return _check(name, _to_int(actual), expected)


def _check_at_least(name: str, actual: Any, expected_minimum: int) -> dict[str, Any]:
    normalized = _to_int(actual)
    return {"name": name, "passed": normalized >= expected_minimum, "actual": normalized, "expected": expected_minimum}


def _check_contains(name: str, actual: list[str], expected: str) -> dict[str, Any]:
    return {"name": name, "passed": expected in actual, "actual": actual, "expected": expected}


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _first_record(items: list[dict[str, Any]]) -> dict[str, Any]:
    return items[0] if items else {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
