"""Plan v8 artifact evidence summary helpers."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_CHAT_VISIBLE_RESPONSE_STATES = ("completed", "blocked", "needs_approval", "handoff", "provider_blocker")
_COMPAT_VISIBLE_RESPONSE_STATES = set(_CHAT_VISIBLE_RESPONSE_STATES) | {"provider_blocked"}


class PlanV8ArtifactRecord(BaseModel):
    name: str
    path: str
    kind: str
    status: str
    generated_at: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)


class PlanV8ArtifactSummary(BaseModel):
    artifact_dir: str
    status: str
    artifact_count: int = 0
    agent_server_smoke_count: int = 0
    chat_visible_response_matrix_count: int = 0
    live_provider_readiness_count: int = 0
    live_provider_soak_plan_count: int = 0
    live_provider_soak_evidence_count: int = 0
    plane_scope_discovery_smoke_count: int = 0
    plane_ticket_action_smoke_count: int = 0
    ticket_loop_worker_soak_count: int = 0
    context_retrieval_eval_count: int = 0
    asset_provenance_eval_count: int = 0
    plan_v8_readiness_count: int = 0
    employee_growth_eval_count: int = 0
    latest_generated_at: str = ""
    latest_agent_server_smoke: PlanV8ArtifactRecord | None = None
    latest_chat_visible_response_matrix: PlanV8ArtifactRecord | None = None
    latest_live_provider_readiness: PlanV8ArtifactRecord | None = None
    latest_live_provider_soak_plan: PlanV8ArtifactRecord | None = None
    latest_live_provider_soak_evidence: PlanV8ArtifactRecord | None = None
    latest_plane_scope_discovery_smoke: PlanV8ArtifactRecord | None = None
    latest_plane_ticket_action_smoke: PlanV8ArtifactRecord | None = None
    latest_ticket_loop_worker_soak: PlanV8ArtifactRecord | None = None
    latest_context_retrieval_eval: PlanV8ArtifactRecord | None = None
    latest_asset_provenance_eval: PlanV8ArtifactRecord | None = None
    latest_plan_v8_readiness: PlanV8ArtifactRecord | None = None
    latest_employee_growth_eval: PlanV8ArtifactRecord | None = None
    evidence_gaps: list[str] = Field(default_factory=list)
    evidence_warnings: list[str] = Field(default_factory=list)
    provider_blockers: list[str] = Field(default_factory=list)
    records: list[PlanV8ArtifactRecord] = Field(default_factory=list)


def plan_v8_artifact_summary(*, workspace_dir: Path | None = None, limit: int = 8) -> PlanV8ArtifactSummary:
    artifact_dir = _artifact_dir(workspace_dir)
    records = _load_records(artifact_dir)
    agent_records = [item for item in records if item.kind == "agent_server_smoke"]
    matrix_records = [item for item in records if item.kind == "chat_visible_response_matrix"]
    readiness_records = [item for item in records if item.kind == "live_provider_readiness"]
    soak_plan_records = [item for item in records if item.kind == "live_provider_soak_plan"]
    soak_evidence_records = [item for item in records if item.kind == "live_provider_soak_evidence"]
    plane_scope_discovery_records = [item for item in records if item.kind == "plane_scope_discovery_smoke"]
    plane_action_records = [item for item in records if item.kind == "plane_ticket_action_smoke"]
    ticket_loop_worker_records = [item for item in records if item.kind == "ticket_loop_worker_soak"]
    context_records = [item for item in records if item.kind == "context_retrieval_eval"]
    provenance_records = [item for item in records if item.kind == "asset_provenance_eval"]
    plan_v8_readiness_records = [item for item in records if item.kind == "plan_v8_readiness"]
    employee_growth_records = [item for item in records if item.kind == "employee_growth_eval"]
    latest_agent = agent_records[0] if agent_records else None
    latest_matrix = matrix_records[0] if matrix_records else None
    latest_readiness = readiness_records[0] if readiness_records else None
    latest_soak_plan = soak_plan_records[0] if soak_plan_records else None
    latest_soak_evidence = soak_evidence_records[0] if soak_evidence_records else None
    latest_plane_scope_discovery = plane_scope_discovery_records[0] if plane_scope_discovery_records else None
    latest_plane_action = plane_action_records[0] if plane_action_records else None
    latest_ticket_loop_worker = ticket_loop_worker_records[0] if ticket_loop_worker_records else None
    latest_context = context_records[0] if context_records else None
    latest_provenance = provenance_records[0] if provenance_records else None
    latest_plan_v8_readiness = plan_v8_readiness_records[0] if plan_v8_readiness_records else None
    latest_employee_growth = employee_growth_records[0] if employee_growth_records else None
    evidence_gaps: list[str] = []
    evidence_warnings: list[str] = []
    provider_blockers: list[str] = []

    if latest_agent is None:
        evidence_gaps.append("agent_server_smoke_missing")
    else:
        if latest_agent.status != "passed":
            evidence_gaps.append("agent_server_smoke_not_passed")
        if latest_agent.summary.get("visible_response_version") != "chat_visible_response.v1":
            evidence_gaps.append("chat_visible_response_contract_missing")
        if latest_agent.summary.get("visible_display_state") not in _COMPAT_VISIBLE_RESPONSE_STATES:
            evidence_gaps.append("chat_visible_response_state_missing")

    if latest_matrix is None:
        evidence_gaps.append("chat_visible_response_matrix_missing")
    else:
        matrix_summary = latest_matrix.summary
        observed_states = set(_strings(matrix_summary.get("observed_states")))
        missing_states = [
            state
            for state in _CHAT_VISIBLE_RESPONSE_STATES
            if state not in observed_states and not (state == "provider_blocker" and "provider_blocked" in observed_states)
        ]
        if latest_matrix.status != "passed":
            evidence_gaps.append("chat_visible_response_matrix_not_passed")
        if missing_states or _safe_int(matrix_summary.get("passed_case_count")) < len(_CHAT_VISIBLE_RESPONSE_STATES):
            evidence_gaps.append("chat_visible_response_matrix_state_missing")

    if latest_readiness is None:
        evidence_gaps.append("live_provider_readiness_missing")
    else:
        readiness_status = str(latest_readiness.summary.get("readiness_status") or latest_readiness.status or "")
        if readiness_status != "ready":
            provider_blockers.extend(_strings(latest_readiness.summary.get("blocker_reasons")))
            if not provider_blockers:
                provider_blockers.append("live_provider_not_ready")

    if latest_soak_evidence is None:
        evidence_gaps.append("live_provider_soak_evidence_missing")
    else:
        soak_status = str(latest_soak_evidence.status or "")
        if soak_status != "passed":
            provider_blockers.extend(_strings(latest_soak_evidence.summary.get("blockers")))
            if not provider_blockers:
                provider_blockers.append("live_provider_soak_evidence_incomplete")

    if latest_plane_scope_discovery is not None:
        discovery_status = str(latest_plane_scope_discovery.summary.get("discovery_status") or "")
        if discovery_status == "failed":
            evidence_warnings.append("plane_scope_discovery_failed")
        elif discovery_status == "blocked":
            evidence_warnings.append("plane_scope_discovery_blocked")

    if latest_plane_action is not None:
        plane_action_status = str(latest_plane_action.status or "")
        if plane_action_status in {"blocked", "failed", "error"}:
            provider_blockers.extend(_strings(latest_plane_action.summary.get("blocker_reasons")))
            if not provider_blockers:
                provider_blockers.append("plane_ticket_action_smoke_not_passed")
        elif plane_action_status not in {"passed", "dry_run"}:
            evidence_warnings.append(f"plane_ticket_action_smoke_{plane_action_status or 'unknown'}")

    if latest_ticket_loop_worker is None:
        evidence_gaps.append("ticket_loop_worker_soak_missing")
    else:
        worker_summary = latest_ticket_loop_worker.summary
        if latest_ticket_loop_worker.status != "passed":
            evidence_gaps.append("ticket_loop_worker_soak_not_passed")
        if _safe_int(worker_summary.get("worker_processed_delta")) < 1:
            evidence_gaps.append("ticket_loop_worker_processed_delta_missing")
        if _safe_int(worker_summary.get("worker_policy_action_delta")) < 1:
            evidence_gaps.append("ticket_loop_worker_policy_action_missing")
        if _safe_int(worker_summary.get("asset_candidate_count")) < 1:
            evidence_gaps.append("ticket_loop_worker_retrospective_asset_missing")
        if str(worker_summary.get("daemon_status") or "") != "passed":
            evidence_gaps.append("ticket_loop_worker_daemon_not_passed")

    if latest_context is None:
        evidence_gaps.append("context_retrieval_eval_missing")
    else:
        context_summary = latest_context.summary
        if latest_context.status != "passed":
            evidence_gaps.append("context_retrieval_eval_not_passed")
        if _safe_int(context_summary.get("graphiti_result_count")) < 1:
            evidence_gaps.append("context_retrieval_active_recall_missing")
        if _safe_int(context_summary.get("graphiti_excluded_result_count")) < 1:
            evidence_gaps.append("context_retrieval_exclusion_missing")
        if context_summary.get("wrong_ticket_filtered") is not True:
            evidence_gaps.append("context_retrieval_wrong_ticket_filter_missing")
        if _safe_float(context_summary.get("work_history_eval_recall")) < 1:
            evidence_gaps.append("context_retrieval_work_history_recall_gap")

    if latest_provenance is None:
        evidence_gaps.append("asset_provenance_eval_missing")
    else:
        provenance_summary = latest_provenance.summary
        if latest_provenance.status != "passed":
            evidence_gaps.append("asset_provenance_eval_not_passed")
        if _safe_int(provenance_summary.get("relationship_ingested_count")) < 1:
            evidence_gaps.append("asset_relationship_projection_missing")
        if _safe_int(provenance_summary.get("relationship_search_result_count")) < 1:
            evidence_gaps.append("asset_relationship_recall_missing")
        if provenance_summary.get("stale_active_filtered") is not True:
            evidence_gaps.append("stale_asset_exclusion_missing")

    if latest_employee_growth is None:
        evidence_gaps.append("employee_growth_eval_missing")
    else:
        growth_summary = latest_employee_growth.summary
        if latest_employee_growth.status in {"blocked", "failed"}:
            evidence_gaps.append("employee_growth_eval_not_passed")
        elif latest_employee_growth.status == "warning":
            evidence_warnings.extend(_strings(growth_summary.get("warnings")))
            if not evidence_warnings:
                evidence_warnings.append("employee_growth_eval_warning")
        if _safe_int(growth_summary.get("quality_feedback_count")) < 1:
            evidence_warnings.append("employee_quality_feedback_missing")
        if _safe_int(growth_summary.get("handoff_work_history_score")) < 1:
            evidence_warnings.append("employee_handoff_work_history_gap")

    status = "ready"
    if evidence_gaps:
        status = "blocked"
    elif provider_blockers or evidence_warnings:
        status = "warning"
    latest_generated_at = records[0].generated_at if records else ""
    return PlanV8ArtifactSummary(
        artifact_dir=str(artifact_dir),
        status=status,
        artifact_count=len(records),
        agent_server_smoke_count=len(agent_records),
        chat_visible_response_matrix_count=len(matrix_records),
        live_provider_readiness_count=len(readiness_records),
        live_provider_soak_plan_count=len(soak_plan_records),
        live_provider_soak_evidence_count=len(soak_evidence_records),
        plane_scope_discovery_smoke_count=len(plane_scope_discovery_records),
        plane_ticket_action_smoke_count=len(plane_action_records),
        ticket_loop_worker_soak_count=len(ticket_loop_worker_records),
        context_retrieval_eval_count=len(context_records),
        asset_provenance_eval_count=len(provenance_records),
        plan_v8_readiness_count=len(plan_v8_readiness_records),
        employee_growth_eval_count=len(employee_growth_records),
        latest_generated_at=latest_generated_at,
        latest_agent_server_smoke=latest_agent,
        latest_chat_visible_response_matrix=latest_matrix,
        latest_live_provider_readiness=latest_readiness,
        latest_live_provider_soak_plan=latest_soak_plan,
        latest_live_provider_soak_evidence=latest_soak_evidence,
        latest_plane_scope_discovery_smoke=latest_plane_scope_discovery,
        latest_plane_ticket_action_smoke=latest_plane_action,
        latest_ticket_loop_worker_soak=latest_ticket_loop_worker,
        latest_context_retrieval_eval=latest_context,
        latest_asset_provenance_eval=latest_provenance,
        latest_plan_v8_readiness=latest_plan_v8_readiness,
        latest_employee_growth_eval=latest_employee_growth,
        evidence_gaps=evidence_gaps,
        evidence_warnings=_unique(evidence_warnings),
        provider_blockers=_unique(provider_blockers),
        records=records[: max(0, limit)],
    )


def _artifact_dir(workspace_dir: Path | None) -> Path:
    root = (workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).expanduser()).resolve()
    if root.name == ".aiteamos":
        return root / "artifacts" / "plan_v8"
    return root / ".aiteamos" / "artifacts" / "plan_v8"


def _load_records(artifact_dir: Path) -> list[PlanV8ArtifactRecord]:
    if not artifact_dir.exists():
        return []
    records: list[PlanV8ArtifactRecord] = []
    for path in artifact_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        records.append(_record_from_payload(path, payload))
    return sorted(records, key=lambda item: (item.generated_at, item.name), reverse=True)


def _record_from_payload(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    schema = str(payload.get("schema") or "")
    if schema == "aiteamos.langgraph_agent_server_ci_smoke.v1":
        return _agent_server_record(path, payload)
    if schema == "aiteamos.chat_visible_response_matrix.cli.v1":
        return _chat_visible_response_matrix_record(path, payload)
    if schema in {"aiteamos.live_provider_readiness_smoke.v1", "aiteamos.live_provider_dogfood.readiness.cli.v1"}:
        return _live_provider_readiness_record(path, payload)
    if schema == "aiteamos.live_provider_soak_plan.cli.v1":
        return _live_provider_soak_plan_record(path, payload)
    if schema == "aiteamos.live_provider_soak_evidence.cli.v1":
        return _live_provider_soak_evidence_record(path, payload)
    if schema == "aiteamos.plane_scope_discovery_smoke.v1":
        return _plane_scope_discovery_smoke_record(path, payload)
    if schema == "aiteamos.plane_ticket_action_smoke.v1":
        return _plane_ticket_action_smoke_record(path, payload)
    if schema == "aiteamos.ticket_loop_queue_worker_smoke.v2":
        return _ticket_loop_worker_soak_record(path, payload)
    if schema == "aiteamos.context_retrieval_eval_smoke.v1":
        return _context_retrieval_record(path, payload)
    if schema == "aiteamos.asset_provenance_eval_smoke.v1":
        return _asset_provenance_record(path, payload)
    if schema == "aiteamos.plan_v8_readiness.cli.v1":
        return _plan_v8_readiness_record(path, payload)
    if schema == "aiteamos.employee_growth_eval_smoke.v1":
        return _employee_growth_eval_record(path, payload)
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="artifact",
        status=str(payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={},
    )


def _agent_server_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    smoke = _record(payload.get("smoke"))
    smoke_summary = _record(smoke.get("summary"))
    runtime_status = _record(smoke_summary.get("runtime_status"))
    visible_response = _record(smoke_summary.get("visible_response"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="agent_server_smoke",
        status=str(payload.get("status") or smoke.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "assistant_id": str(payload.get("assistant_id") or smoke.get("assistant_id") or ""),
            "url": str(payload.get("url") or smoke.get("url") or ""),
            "runtime_status": str(runtime_status.get("status") or ""),
            "current_node": str(runtime_status.get("current_node") or ""),
            "visible_response_version": str(visible_response.get("version") or ""),
            "visible_display_state": str(visible_response.get("display_state") or ""),
            "provider_blocker_count": _safe_int(smoke_summary.get("provider_blocker_count")),
            "provider_blocker_reasons": _strings(smoke_summary.get("provider_blocker_reasons")),
        },
    )


def _chat_visible_response_matrix_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    result = _record(payload.get("result"))
    summary = _record(result.get("summary"))
    cases = _records(result.get("cases"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="chat_visible_response_matrix",
        status=str(result.get("status") or payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "case_count": _safe_int(summary.get("case_count") if "case_count" in summary else len(cases)),
            "passed_case_count": _safe_int(summary.get("passed_case_count")),
            "failed_case_count": _safe_int(summary.get("failed_case_count")),
            "required_states": _strings(summary.get("required_states")),
            "observed_states": _strings(summary.get("observed_states")),
            "missing_states": _strings(summary.get("missing_states")),
            "assistant_reply_visible_count": _safe_int(summary.get("assistant_reply_visible_count")),
            "runtime_status_visible_count": _safe_int(summary.get("runtime_status_visible_count")),
            "blocked_reason_visible_count": _safe_int(summary.get("blocked_reason_visible_count")),
            "retry_cause_visible_count": _safe_int(summary.get("retry_cause_visible_count")),
            "approval_request_visible_count": _safe_int(summary.get("approval_request_visible_count")),
            "handoff_visible_count": _safe_int(summary.get("handoff_visible_count")),
            "provider_blocker_visible_count": _safe_int(summary.get("provider_blocker_visible_count")),
            "blockers": _strings(result.get("blockers")),
        },
    )


def _live_provider_readiness_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    result = _record(payload.get("result"))
    summary = _record(payload.get("summary"))
    if not summary:
        summary = _record(result.get("summary"))
    blockers = _records(result.get("blockers"))
    mutation_gate = _record(result.get("mutation_gate"))
    readiness_status = str(summary.get("readiness_status") or result.get("status") or "")
    blocker_reasons = _strings(summary.get("blocker_reasons")) or _strings([item.get("reason") for item in blockers])
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="live_provider_readiness",
        status="passed" if str(payload.get("status") or "") == "passed" else readiness_status or "unknown",
        generated_at=_generated_at(path, payload),
        summary={
            "readiness_status": readiness_status,
            "profile": str(summary.get("profile") or result.get("profile") or ""),
            "selected_executor_id": str(summary.get("selected_executor_id") or result.get("selected_executor_id") or ""),
            "repo_write_ready_count": _safe_int(summary.get("repo_write_ready_count")),
            "repo_write_candidate_count": _safe_int(summary.get("repo_write_candidate_count")),
            "ticket_backend_status": str(summary.get("ticket_backend_status") or ""),
            "ticket_backend_mode": str(summary.get("ticket_backend_mode") or ""),
            "ticket_backend_provider": str(summary.get("ticket_backend_provider") or ""),
            "ticket_backend_release_target_status": str(summary.get("ticket_backend_release_target_status") or ""),
            "ticket_backend_release_target_ready": bool(summary.get("ticket_backend_release_target_ready")),
            "ticket_backend_release_target_blockers": _strings(summary.get("ticket_backend_release_target_blockers")),
            "ticket_backend_release_target_setup_action": str(summary.get("ticket_backend_release_target_setup_action") or ""),
            "plane_ticket_backend_selected": bool(summary.get("plane_ticket_backend_selected")),
            "plane_ticket_backend_setup_status": str(summary.get("plane_ticket_backend_setup_status") or ""),
            "plane_ticket_backend_setup_required": _strings(summary.get("plane_ticket_backend_setup_required")),
            "plane_ticket_backend_configured": bool(summary.get("plane_ticket_backend_configured")),
            "plane_ticket_workspace_configured": bool(summary.get("plane_ticket_workspace_configured")),
            "plane_ticket_project_configured": bool(summary.get("plane_ticket_project_configured")),
            "plane_ticket_api_key_configured": bool(summary.get("plane_ticket_api_key_configured")),
            "plane_ticket_scope_status": str(summary.get("plane_ticket_scope_status") or ""),
            "plane_ticket_scope_candidate_count": _safe_int(summary.get("plane_ticket_scope_candidate_count")),
            "plane_ticket_scope_missing_count": _safe_int(summary.get("plane_ticket_scope_missing_count")),
            "plane_ticket_scope_setup_action": str(summary.get("plane_ticket_scope_setup_action") or ""),
            "memory_backend_status": str(summary.get("memory_backend_status") or ""),
            "provider_smoke_status": str(summary.get("provider_smoke_status") or ""),
            "mutation_gate_open": bool(summary.get("mutation_gate_open") or mutation_gate.get("open")),
            "blocker_count": _safe_int(summary.get("blocker_count") if "blocker_count" in summary else len(blockers)),
            "blocker_reasons": blocker_reasons,
            "blocker_scopes": _strings(summary.get("blocker_scopes")) or _strings([item.get("scope") for item in blockers]),
        },
    )


def _live_provider_soak_plan_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    result = _record(payload.get("result"))
    summary = _record(result.get("summary"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="live_provider_soak_plan",
        status=str(result.get("status") or payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "ready_to_execute": bool(summary.get("ready_to_execute")),
            "scenario_count": _safe_int(summary.get("scenario_count")),
            "blocked_scenario_count": _safe_int(summary.get("blocked_scenario_count")),
            "expected_states": _strings(summary.get("expected_states")),
            "mutation_gate_open": bool(summary.get("mutation_gate_open")),
            "ticket_backend_status": str(summary.get("ticket_backend_status") or ""),
            "ticket_backend_mode": str(summary.get("ticket_backend_mode") or ""),
            "ticket_backend_provider": str(summary.get("ticket_backend_provider") or ""),
            "plane_ticket_backend_selected": bool(summary.get("plane_ticket_backend_selected")),
            "plane_ticket_backend_setup_status": str(summary.get("plane_ticket_backend_setup_status") or ""),
            "plane_ticket_backend_setup_required": _strings(summary.get("plane_ticket_backend_setup_required")),
            "plane_ticket_scope_status": str(summary.get("plane_ticket_scope_status") or ""),
            "plane_ticket_scope_candidate_count": _safe_int(summary.get("plane_ticket_scope_candidate_count")),
            "plane_ticket_scope_missing_count": _safe_int(summary.get("plane_ticket_scope_missing_count")),
            "plane_ticket_scope_setup_action": str(summary.get("plane_ticket_scope_setup_action") or ""),
            "memory_backend_status": str(summary.get("memory_backend_status") or ""),
            "selected_executor_id": str(summary.get("selected_executor_id") or ""),
            "blockers": _strings(result.get("blockers")),
        },
    )


def _live_provider_soak_evidence_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    result = _record(payload.get("result"))
    summary = _record(result.get("summary"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="live_provider_soak_evidence",
        status=str(result.get("status") or payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "ready_for_release": bool(summary.get("ready_for_release")),
            "scenario_count": _safe_int(summary.get("scenario_count")),
            "passed_scenario_count": _safe_int(summary.get("passed_scenario_count")),
            "blocked_scenario_count": _safe_int(summary.get("blocked_scenario_count")),
            "failed_scenario_count": _safe_int(summary.get("failed_scenario_count")),
            "missing_scenario_count": _safe_int(summary.get("missing_scenario_count")),
            "warning_scenario_count": _safe_int(summary.get("warning_scenario_count")),
            "mutation_gate_open": bool(summary.get("mutation_gate_open")),
            "live_write_scenario_count": _safe_int(summary.get("live_write_scenario_count")),
            "remaining_live_write_scenario_count": _safe_int(summary.get("remaining_live_write_scenario_count")),
            "passed_non_mutating_scenario_count": _safe_int(summary.get("passed_non_mutating_scenario_count")),
            "operator_action_required": bool(summary.get("operator_action_required")),
            "latest_generated_at": str(summary.get("latest_generated_at") or ""),
            "blockers": _strings(result.get("blockers")),
        },
    )


def _plane_scope_discovery_smoke_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    result = _record(payload.get("result"))
    summary = _record(payload.get("summary")) or _record(result.get("summary"))
    evidence = _record(result.get("evidence"))
    suggestions = _records(result.get("suggestions"))
    first_suggestion = suggestions[0] if suggestions else {}
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="plane_scope_discovery_smoke",
        status=str(payload.get("status") or result.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "discovery_status": str(summary.get("discovery_status") or result.get("status") or ""),
            "detail": str(summary.get("detail") or result.get("detail") or ""),
            "api_key_env": str(summary.get("api_key_env") or result.get("api_key_env") or ""),
            "api_key_configured": bool(summary.get("api_key_configured")),
            "external_calls": bool(summary.get("external_calls") if "external_calls" in summary else result.get("external_calls")),
            "external_mutation": bool(summary.get("external_mutation")),
            "workspace_count": _safe_int(summary.get("workspace_count") if "workspace_count" in summary else evidence.get("workspace_count")),
            "project_count": _safe_int(summary.get("project_count") if "project_count" in summary else evidence.get("project_count")),
            "suggestion_count": _safe_int(summary.get("suggestion_count") if "suggestion_count" in summary else len(suggestions)),
            "first_workspace_slug": str(summary.get("first_workspace_slug") or first_suggestion.get("plane_workspace_slug") or ""),
            "first_project_id": str(summary.get("first_project_id") or first_suggestion.get("plane_project_id") or ""),
            "first_workspace_name": str(summary.get("first_workspace_name") or first_suggestion.get("workspace_name") or ""),
            "first_project_name": str(summary.get("first_project_name") or first_suggestion.get("project_name") or ""),
            "checks": _strings(summary.get("checks")) or _strings(result.get("checks")),
            "setup_required": _strings(summary.get("setup_required")) or _strings(result.get("setup_required")),
        },
    )


def _plane_ticket_action_smoke_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    result = _record(payload.get("result"))
    summary = _record(payload.get("summary")) or _record(result.get("summary"))
    evidence = _record(result.get("evidence")) or _record(payload.get("evidence"))
    ticket_backend = _record(evidence.get("ticket_backend_status"))
    blockers = _records(result.get("blockers"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="plane_ticket_action_smoke",
        status=str(result.get("status") or payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "provider": str(result.get("provider") or ""),
            "ticket_backend_status": str(summary.get("ticket_backend_status") or ticket_backend.get("status") or ""),
            "mutation_gate_open": bool(summary.get("mutation_gate_open")),
            "confirm_env_var": str(evidence.get("confirm_env_var") or ""),
            "confirm_env_configured": bool(evidence.get("confirm_env_configured")),
            "ticket_id": str(summary.get("ticket_id") or evidence.get("ticket_id") or ""),
            "ticket_source": str(summary.get("ticket_source") or ""),
            "provider_record_id": str(summary.get("provider_record_id") or ""),
            "handoff_recorded": bool(summary.get("handoff_recorded")),
            "handoff_report_recorded": bool(summary.get("handoff_report_recorded")),
            "report_id": str(summary.get("report_id") or ""),
            "blocker_stage": str(summary.get("blocker_stage") or ""),
            "blocker_reasons": _strings([item.get("reason") for item in blockers]),
            "warnings": _strings(result.get("warnings")),
            "checks": _strings(result.get("checks")),
            "external_calls": bool(result.get("external_calls")),
            "mutating": bool(result.get("mutating")),
        },
    )


def _ticket_loop_worker_soak_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    summary = _record(payload.get("summary"))
    after_reliability = _record(summary.get("after_reliability"))
    worker_status = _record(summary.get("worker_status"))
    daemon = _record(summary.get("daemon"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="ticket_loop_worker_soak",
        status=str(payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "ticket_id": str(summary.get("ticket_id") or ""),
            "processed_statuses": _strings(summary.get("processed_statuses")),
            "queue_ids": _strings(summary.get("queue_ids")),
            "asset_candidate_ids": _strings(summary.get("asset_candidate_ids")),
            "asset_candidate_count": len(_strings(summary.get("asset_candidate_ids"))),
            "timeline_statuses": _strings(summary.get("timeline_statuses")),
            "after_reliability_status": str(after_reliability.get("status") or ""),
            "after_reliability_detail": str(after_reliability.get("detail") or ""),
            "worker_status": str(worker_status.get("status") or summary.get("worker_status") or ""),
            "worker_processed_delta": _safe_int(summary.get("worker_processed_delta")),
            "worker_policy_action_delta": _safe_int(summary.get("worker_policy_action_delta")),
            "failed_delta": _safe_int(summary.get("failed_delta")),
            "daemon_status": str(summary.get("daemon_status") or ""),
            "daemon_processed_delta": _safe_int(daemon.get("processed_delta")),
            "daemon_tick_delta": _safe_int(daemon.get("tick_delta")),
            "daemon_run_statuses": _strings(daemon.get("run_statuses")),
            "daemon_queue_statuses": _strings(daemon.get("queue_statuses")),
        },
    )


def _context_retrieval_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    summary = _record(payload.get("summary"))
    work_history = _record(summary.get("work_history"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="context_retrieval_eval",
        status=str(payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "query": str(summary.get("query") or ""),
            "ticket_id": str(summary.get("ticket_id") or ""),
            "graphiti_result_count": _safe_int(summary.get("graphiti_result_count")),
            "graphiti_excluded_result_count": _safe_int(summary.get("graphiti_excluded_result_count")),
            "active_asset_ids": _strings(summary.get("active_asset_ids")),
            "recalled_memory_ids": _strings(summary.get("recalled_memory_ids")),
            "stale_hint_asset_ids": _strings(summary.get("stale_hint_asset_ids")),
            "excluded_asset_ids": _strings(summary.get("excluded_asset_ids")),
            "wrong_ticket_filtered": bool(summary.get("wrong_ticket_filtered")),
            "work_history_eval_recall": _safe_float(work_history.get("eval_recall")),
            "work_history_eval_precision_like": _safe_float(work_history.get("eval_precision_like")),
            "work_history_missing_ref_count": len(_records(work_history.get("missing_refs"))),
            "work_history_matched_ref_count": len(_records(work_history.get("matched_refs"))),
            "provider_blocker_count": _safe_int(summary.get("provider_blocker_count")),
        },
    )


def _asset_provenance_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    summary = _record(payload.get("summary"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="asset_provenance_eval",
        status=str(payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "source_asset_id": str(summary.get("source_asset_id") or ""),
            "target_asset_id": str(summary.get("target_asset_id") or ""),
            "relationship_id": str(summary.get("relationship_id") or ""),
            "relationship_projection_status": str(summary.get("relationship_projection_status") or ""),
            "relationship_ingested_count": _safe_int(summary.get("relationship_ingested_count")),
            "relationship_repeated_status": str(summary.get("relationship_repeated_status") or ""),
            "relationship_skipped_count": _safe_int(summary.get("relationship_skipped_count")),
            "asset_record_graphiti_relationship_count": _safe_int(summary.get("asset_record_graphiti_relationship_count")),
            "relationship_search_result_count": _safe_int(summary.get("relationship_search_result_count")),
            "stale_memory_id": str(summary.get("stale_memory_id") or ""),
            "stale_review_status": str(summary.get("stale_review_status") or ""),
            "stale_before_result_count": _safe_int(summary.get("stale_before_result_count")),
            "stale_after_active_count": _safe_int(summary.get("stale_after_active_count")),
            "stale_after_excluded_count": _safe_int(summary.get("stale_after_excluded_count")),
            "stale_active_filtered": bool(summary.get("stale_active_filtered")),
        },
    )


def _plan_v8_readiness_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    result = _record(payload.get("result"))
    summary = _record(result.get("summary"))
    checks = _records(result.get("checks"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="plan_v8_readiness",
        status=str(result.get("status") or payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "ready_for_release": bool(summary.get("ready_for_release")),
            "check_count": _safe_int(summary.get("check_count") if "check_count" in summary else len(checks)),
            "passed_count": _safe_int(summary.get("passed_count")),
            "warning_count": _safe_int(summary.get("warning_count")),
            "blocked_count": _safe_int(summary.get("blocked_count")),
            "failed_count": _safe_int(summary.get("failed_count")),
            "next_action": str(summary.get("next_action") or ""),
            "next_steps": _strings(summary.get("next_steps")),
            "next_step_actions": _records(summary.get("next_step_actions")),
            "blockers": _strings(result.get("blockers")),
            "evidence_refs": _strings(result.get("evidence_refs")),
        },
    )


def _employee_growth_eval_record(path: Path, payload: dict[str, Any]) -> PlanV8ArtifactRecord:
    result = _record(payload.get("result"))
    summary = _record(result.get("summary")) or _record(payload.get("summary"))
    return PlanV8ArtifactRecord(
        name=path.name,
        path=str(path),
        kind="employee_growth_eval",
        status=str(result.get("status") or payload.get("status") or "unknown"),
        generated_at=_generated_at(path, payload),
        summary={
            "employee_id": str(summary.get("employee_id") or ""),
            "current_load_status": str(summary.get("current_load_status") or ""),
            "active_ticket_count": _safe_int(summary.get("active_ticket_count")),
            "active_run_count": _safe_int(summary.get("active_run_count")),
            "current_ticket_count": _safe_int(summary.get("current_ticket_count")),
            "historical_ticket_count": _safe_int(summary.get("historical_ticket_count")),
            "report_count": _safe_int(summary.get("report_count")),
            "handoff_count": _safe_int(summary.get("handoff_count")),
            "asset_candidate_count": _safe_int(summary.get("asset_candidate_count")),
            "approved_asset_count": _safe_int(summary.get("approved_asset_count")),
            "asset_review_count": _safe_int(summary.get("asset_review_count")),
            "runtime_run_count": _safe_int(summary.get("runtime_run_count")),
            "quality_feedback_count": _safe_int(summary.get("quality_feedback_count")),
            "improvement_candidate_count": _safe_int(summary.get("improvement_candidate_count")),
            "approved_improvement_count": _safe_int(summary.get("approved_improvement_count")),
            "applied_improvement_count": _safe_int(summary.get("applied_improvement_count")),
            "improvement_loop_proof_status": str(summary.get("improvement_loop_proof_status") or ""),
            "improvement_loop_candidate_id": str(summary.get("improvement_loop_candidate_id") or ""),
            "improvement_loop_asset_id": str(summary.get("improvement_loop_asset_id") or ""),
            "improvement_loop_application_status": str(summary.get("improvement_loop_application_status") or ""),
            "improvement_loop_ticket_report_id": str(summary.get("improvement_loop_ticket_report_id") or ""),
            "improvement_loop_applied_change_count": _safe_int(summary.get("improvement_loop_applied_change_count")),
            "improvement_loop_workspace": str(summary.get("improvement_loop_workspace") or ""),
            "handoff_target_employee_id": str(summary.get("handoff_target_employee_id") or ""),
            "handoff_work_history_score": _safe_int(summary.get("handoff_work_history_score")),
            "provider_projection_status": str(summary.get("provider_projection_status") or ""),
            "graph_node_count": _safe_int(summary.get("graph_node_count")),
            "graph_edge_count": _safe_int(summary.get("graph_edge_count")),
            "warnings": _strings(result.get("warnings")),
            "blockers": _strings(result.get("blockers")),
        },
    )


def _generated_at(path: Path, payload: dict[str, Any]) -> str:
    value = str(payload.get("generated_at") or _record(payload.get("smoke")).get("generated_at") or "")
    if value:
        return value
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique([str(item or "").strip() for item in value if str(item or "").strip()])


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
