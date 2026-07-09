"""Read-only Track E Employee growth evaluation."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .asset_candidate_service import AssetCandidateReviewRequest, review_asset_candidate
from .chat_action_plan import ChatActionPlan
from .employee_handoff_service import choose_employee_for_goal
from .employee_improvement_service import EmployeeImprovementApplyRequest, apply_employee_improvement_asset
from .employee_load_service import employee_current_load
from .employee_profile_service import normalize_employee_profile, read_employee_profile
from .execution_contract import ExecutionRequest, ExecutionResult, TicketBinding
from .execution_result_ingestion_service import ExecutionResultIngestionService
from .ticket_service import (
    EmployeeImprovementCandidateRequest,
    TicketBackendSettingsUpdateRequest,
    TicketCreateRequest,
    create_ticket,
    employee_analytics,
    employee_graph_projection,
    employee_work_ledger,
    propose_employee_quality_improvement_candidate,
    update_ticket_backend_settings,
)

EMPLOYEE_GROWTH_EVAL_CONTRACT_VERSION = "aiteamos_employee_growth_eval.v1"


class EmployeeGrowthEvalCheck(BaseModel):
    id: str
    status: str
    detail: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class EmployeeGrowthEvalSummary(BaseModel):
    employee_id: str = ""
    current_load_status: str = ""
    active_ticket_count: int = 0
    active_run_count: int = 0
    current_ticket_count: int = 0
    historical_ticket_count: int = 0
    report_count: int = 0
    handoff_count: int = 0
    asset_candidate_count: int = 0
    approved_asset_count: int = 0
    asset_review_count: int = 0
    runtime_run_count: int = 0
    quality_feedback_count: int = 0
    improvement_candidate_count: int = 0
    approved_improvement_count: int = 0
    applied_improvement_count: int = 0
    improvement_loop_proof_status: str = ""
    improvement_loop_candidate_id: str = ""
    improvement_loop_asset_id: str = ""
    improvement_loop_application_status: str = ""
    improvement_loop_ticket_report_id: str = ""
    improvement_loop_applied_change_count: int = 0
    improvement_loop_workspace: str = ""
    handoff_target_employee_id: str = ""
    handoff_work_history_score: int = 0
    provider_projection_status: str = ""
    graph_node_count: int = 0
    graph_edge_count: int = 0
    source_counts: dict[str, int] = Field(default_factory=dict)


class EmployeeGrowthEvalResponse(BaseModel):
    contract_version: str = EMPLOYEE_GROWTH_EVAL_CONTRACT_VERSION
    status: str
    detail: str
    summary: EmployeeGrowthEvalSummary = Field(default_factory=EmployeeGrowthEvalSummary)
    checks: list[EmployeeGrowthEvalCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


class EmployeeGrowthImprovementLoopProof(BaseModel):
    status: str = "blocked"
    detail: str = ""
    employee_id: str = "alex"
    ticket_id: str = ""
    feedback_id: str = ""
    candidate_id: str = ""
    asset_id: str = ""
    application_status: str = ""
    ticket_report_id: str = ""
    applied_change_count: int = 0
    applied_changes: dict[str, list[str]] = Field(default_factory=dict)
    workspace: str = "temporary"
    error: str = ""


def employee_growth_eval_report(
    *,
    workspace_dir: Path | None = None,
    employee_id: str = "",
) -> EmployeeGrowthEvalResponse:
    """Inspect live Employee growth evidence and prove the governed improvement loop in a temporary workspace."""

    workspace_root = _workspace_root(workspace_dir)
    os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
    profiles = _load_profiles_readonly(workspace_root)
    selected = _select_employee(profiles, employee_id=employee_id)
    if selected is None:
        return EmployeeGrowthEvalResponse(
            status="blocked",
            detail="Employee growth evaluation requires at least one Employee profile.",
            blockers=["employee_profile_missing"],
            commands=_commands(),
        )

    selected_id = str(selected.get("id") or "").strip()
    ledger = employee_work_ledger(selected_id)
    analytics = employee_analytics(selected_id)
    graph = employee_graph_projection(selected_id)
    current_load = employee_current_load(
        selected_id,
        base_load=selected.get("current_load") if isinstance(selected.get("current_load"), dict) else {},
        workspace_dir=workspace_root / ".aiteamos",
    )
    handoff = choose_employee_for_goal(
        "Fix a backend runtime bug.",
        profiles,
        current_employee_id="clara",
        required_memory_scopes=[f"employee:{selected_id}"],
        risk_level="high",
    )
    handoff_policy = handoff.get("policy") if isinstance(handoff.get("policy"), dict) else {}
    provider_projection = graph.provider_projection.get("employee_profile") if graph is not None else {}
    provider_projection = provider_projection if isinstance(provider_projection, dict) else {}
    improvement_candidates = [item for item in ledger.asset_candidates if item.asset_type == "employee_improvement"]
    approved_improvements = [item for item in ledger.approved_assets if item.asset_type == "employee_improvement"]
    applied_improvements = [
        item
        for item in approved_improvements
        if str(item.application_status or "").strip().lower() in {"applied", "already_applied"}
    ]
    improvement_loop_proof = _run_governed_improvement_loop_proof(selected_id)
    improvement_loop_passed = improvement_loop_proof.status == "passed"
    summary = EmployeeGrowthEvalSummary(
        employee_id=selected_id,
        current_load_status=str(current_load.get("status") or ""),
        active_ticket_count=_safe_int(current_load.get("active_ticket_count")),
        active_run_count=_safe_int(current_load.get("active_run_count")),
        current_ticket_count=len(ledger.current_tickets),
        historical_ticket_count=len(ledger.historical_tickets),
        report_count=len(ledger.reports),
        handoff_count=len(ledger.handoffs),
        asset_candidate_count=len(ledger.asset_candidates),
        approved_asset_count=len(ledger.approved_assets),
        asset_review_count=len(ledger.asset_reviews),
        runtime_run_count=len(ledger.runtime_runs),
        quality_feedback_count=len(ledger.quality_feedback),
        improvement_candidate_count=len(improvement_candidates),
        approved_improvement_count=len(approved_improvements),
        applied_improvement_count=len(applied_improvements),
        improvement_loop_proof_status=improvement_loop_proof.status,
        improvement_loop_candidate_id=improvement_loop_proof.candidate_id,
        improvement_loop_asset_id=improvement_loop_proof.asset_id,
        improvement_loop_application_status=improvement_loop_proof.application_status,
        improvement_loop_ticket_report_id=improvement_loop_proof.ticket_report_id,
        improvement_loop_applied_change_count=improvement_loop_proof.applied_change_count,
        improvement_loop_workspace=improvement_loop_proof.workspace,
        handoff_target_employee_id=str(handoff.get("target_employee_id") or ""),
        handoff_work_history_score=_safe_int(handoff_policy.get("work_history_score")),
        provider_projection_status=str(provider_projection.get("status") or ""),
        graph_node_count=len(graph.nodes) if graph is not None else 0,
        graph_edge_count=len(graph.edges) if graph is not None else 0,
        source_counts=dict(analytics.source_counts if analytics is not None else graph.source_counts if graph is not None else {}),
    )
    checks = [
        _check("profile", bool(selected_id), "Employee profile is loaded from the AITeamOS-owned profile store.", {"employee_id": selected_id}),
        _check(
            "current_load",
            bool(current_load.get("source") == "employee_load_service" and current_load.get("status")),
            "Current load is projected from Tickets and runtime sessions.",
            {
                "status": current_load.get("status"),
                "active_ticket_count": current_load.get("active_ticket_count"),
                "active_run_count": current_load.get("active_run_count"),
                "source": current_load.get("source"),
            },
        ),
        _check(
            "work_history",
            (len(ledger.current_tickets) + len(ledger.historical_tickets) + len(ledger.reports) + len(ledger.runtime_runs)) > 0,
            "Employee work history is backed by Ticket reports, runtime runs, and asset provenance.",
            {
                "current_ticket_count": len(ledger.current_tickets),
                "historical_ticket_count": len(ledger.historical_tickets),
                "report_count": len(ledger.reports),
                "runtime_run_count": len(ledger.runtime_runs),
            },
        ),
        _check(
            "quality_feedback",
            len(ledger.quality_feedback) > 0,
            "Quality feedback exists from Asset reviews or blocked/failed runtime results.",
            {"quality_feedback_count": len(ledger.quality_feedback)},
            warning_id="quality_feedback_missing",
        ),
        _check(
            "governed_improvement_loop",
            improvement_loop_passed,
            "A blocked runtime result can become a governed Employee improvement Asset and apply back to the Employee profile with Ticket report evidence.",
            _improvement_loop_evidence(improvement_loop_proof),
            warning_id="employee_improvement_loop_proof_missing",
        ),
        _check(
            "improvement_candidate_path",
            bool(improvement_candidates) or improvement_loop_passed,
            "Employee improvement candidates are represented as governed Asset candidates.",
            {
                "improvement_candidate_count": len(improvement_candidates),
                "improvement_loop_proof_status": improvement_loop_proof.status,
                "improvement_loop_candidate_id": improvement_loop_proof.candidate_id,
            },
            warning_id="employee_improvement_candidate_missing",
        ),
        _check(
            "approved_improvement_application",
            bool(applied_improvements) or improvement_loop_passed,
            "Approved Employee improvement Assets can be applied back to the profile with Ticket report evidence.",
            {
                "approved_improvement_count": len(approved_improvements),
                "applied_improvement_count": len(applied_improvements),
                "improvement_loop_proof_status": improvement_loop_proof.status,
                "improvement_loop_application_status": improvement_loop_proof.application_status,
                "improvement_loop_ticket_report_id": improvement_loop_proof.ticket_report_id,
            },
            warning_id="employee_improvement_application_missing",
        ),
        _check(
            "handoff_policy_work_history",
            _safe_int(handoff_policy.get("work_history_score")) > 0,
            "Handoff selection considers current load, risk boundary, memory scope, and Employee work history.",
            {
                "target_employee_id": handoff.get("target_employee_id"),
                "lane": handoff.get("lane"),
                "work_history_score": handoff_policy.get("work_history_score"),
                "load_status": handoff_policy.get("load_status"),
                "risk_allowed": handoff_policy.get("risk_allowed"),
            },
            warning_id="handoff_work_history_not_used",
        ),
        _check(
            "provider_projection",
            bool(provider_projection.get("backend_status")),
            "Employee profile projection state is visible without making Graphiti the source of truth.",
            {
                "status": provider_projection.get("status"),
                "backend_status": provider_projection.get("backend_status"),
                "asset_id": provider_projection.get("asset_id"),
            },
            warning_id="employee_provider_projection_missing",
        ),
    ]
    blockers = [check.id for check in checks if check.status == "blocked"]
    warnings = [str(check.evidence.get("warning_id") or check.id) for check in checks if check.status == "warning"]
    status = "blocked" if blockers else "warning" if warnings else "passed"
    return EmployeeGrowthEvalResponse(
        status=status,
        detail=_detail(status, selected_id, blockers, warnings),
        summary=summary,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        commands=_commands(),
    )


def _run_governed_improvement_loop_proof(employee_id: str) -> EmployeeGrowthImprovementLoopProof:
    proof_employee_id = _safe_employee_id(employee_id) or "alex"
    previous_workspace = os.environ.get("AITEAMOS_WORKSPACE_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="aiteamos-employee-growth-") as raw_tmp:
            workspace_root = Path(raw_tmp).resolve()
            os.environ["AITEAMOS_WORKSPACE_DIR"] = str(workspace_root)
            aiteamos_dir = workspace_root / ".aiteamos"
            _write_proof_employee_profiles(workspace_root, proof_employee_id)
            update_ticket_backend_settings(
                TicketBackendSettingsUpdateRequest(
                    mode="local_file",
                    local_file_path=".aiteamos/tickets/index.json",
                )
            )
            ticket = create_ticket(
                TicketCreateRequest(
                    title="Prove governed Employee improvement loop",
                    description="Track E proof that blocked runtime feedback becomes a reviewed and applied Employee improvement Asset.",
                    ticket_type="rd",
                    assigned_employee_id=proof_employee_id,
                    assigned_role="AI RD / Implementer",
                    actor_employee_id="clara",
                    actor_role="AI Team OS Manager",
                    source_thread_id="employee-growth-proof",
                    source_run_id="employee-growth-proof-run",
                )
            )
            timestamp = _now()
            request = ExecutionRequest(
                request_id="employee-growth-proof-request",
                employee_id=proof_employee_id,
                ticket_id=ticket.id,
                ticket_binding=TicketBinding(mode="existing", ticket_id=ticket.id, required=True),
                action_plan=ChatActionPlan(
                    action="implement_ticket",
                    arguments={"ticket_id": ticket.id, "message": "Exercise governed Employee improvement loop."},
                    confidence=1.0,
                    reason="Track E deterministic proof",
                    source="plan_v8_employee_growth_eval",
                ),
                task_context={
                    "ticket": ticket.model_dump(mode="json"),
                    "task_summary": ticket.description,
                },
                trace_context={
                    "thread_id": "employee-growth-proof",
                    "run_id": "employee-growth-proof-run",
                    "trace_ref": "trace:employee-growth-proof",
                },
            )
            result = ExecutionResult(
                request_id=request.request_id,
                executor_id="langgraph",
                status="blocked",
                report="Runtime proof intentionally blocked so Clara can turn feedback into a governed Employee improvement.",
                output_ticket_id=ticket.id,
                evidence=[{"kind": "ticket", "ref": ticket.id}],
                tool_events=[
                    {
                        "event": "runtime.blocked",
                        "detail": "Missing runtime triage skill in proof profile.",
                        "data": {"reason": "missing_runtime_blocker_triage"},
                    }
                ],
                usage={"latency_ms": 1200, "total_cost": 0.0},
                started_at=timestamp,
                finished_at=timestamp,
            )
            ExecutionResultIngestionService(workspace_dir=aiteamos_dir).ingest(request, result)
            feedback = _latest_runtime_feedback(proof_employee_id)
            if feedback is None:
                return EmployeeGrowthImprovementLoopProof(
                    employee_id=proof_employee_id,
                    detail="Proof did not produce runtime quality feedback from the blocked execution result.",
                    ticket_id=ticket.id,
                    error="runtime_feedback_missing",
                )

            candidate_response = propose_employee_quality_improvement_candidate(
                proof_employee_id,
                feedback.id,
                EmployeeImprovementCandidateRequest(
                    actor_employee_id="clara",
                    reason="Convert blocked runtime feedback into an approved Employee improvement.",
                    title="Add runtime blocker triage evidence loop",
                    content="Approved profile update for handling runtime blockers through Ticket-bound evidence.",
                    proposed_skill_refs=["runtime-blocker-triage"],
                    proposed_memory_scopes=[f"employee:{proof_employee_id}:runtime-blockers"],
                    proposed_capability_tags=["runtime-debugging"],
                    proposed_personality_tags=["evidence-driven"],
                ),
            )
            candidate_id = str(candidate_response.candidate.get("id") or "")
            reviewed = review_asset_candidate(
                candidate_id,
                AssetCandidateReviewRequest(
                    status="approved",
                    reviewer_employee_id="clara",
                    reason="Track E proof approves the Employee improvement through Asset review.",
                ),
                workspace_dir=workspace_root,
            )
            if reviewed.asset is None:
                return EmployeeGrowthImprovementLoopProof(
                    employee_id=proof_employee_id,
                    detail="Proof candidate was reviewed but did not produce an approved Asset.",
                    ticket_id=ticket.id,
                    feedback_id=feedback.id,
                    candidate_id=candidate_id,
                    error="asset_record_missing",
                )

            application = apply_employee_improvement_asset(
                proof_employee_id,
                reviewed.asset.id,
                EmployeeImprovementApplyRequest(
                    actor_employee_id="clara",
                    reason="Apply approved Employee improvement through governed profile boundary.",
                    application_note="Plan v8 Track E deterministic proof.",
                ),
                workspace_dir=workspace_root,
            )
            applied_change_count = sum(len(values) for values in application.applied_changes.values())
            missing_expected = _missing_expected_profile_updates(application.applied_changes, proof_employee_id)
            application_ok = application.status in {"applied", "already_applied"}
            passed = application_ok and bool(application.ticket_report_id) and not missing_expected
            return EmployeeGrowthImprovementLoopProof(
                employee_id=proof_employee_id,
                status="passed" if passed else "blocked",
                detail=(
                    "Governed Employee improvement loop produced an approved Asset, applied profile updates, and recorded Ticket report evidence."
                    if passed
                    else "Governed Employee improvement loop did not satisfy all proof assertions."
                ),
                ticket_id=ticket.id,
                feedback_id=feedback.id,
                candidate_id=candidate_id,
                asset_id=reviewed.asset.id,
                application_status=application.status,
                ticket_report_id=application.ticket_report_id,
                applied_change_count=applied_change_count,
                applied_changes=application.applied_changes,
                error=",".join(missing_expected),
            )
    except Exception as exc:
        return EmployeeGrowthImprovementLoopProof(
            employee_id=proof_employee_id,
            detail="Governed Employee improvement loop proof raised an exception.",
            error=str(exc),
        )
    finally:
        if previous_workspace is None:
            os.environ.pop("AITEAMOS_WORKSPACE_DIR", None)
        else:
            os.environ["AITEAMOS_WORKSPACE_DIR"] = previous_workspace


def _write_proof_employee_profiles(workspace_root: Path, employee_id: str) -> None:
    employees_dir = workspace_root / ".aiteamos" / "employees"
    employees_dir.mkdir(parents=True, exist_ok=True)
    target_employee_id = _safe_employee_id(employee_id) or "alex"
    target_name = target_employee_id[:1].upper() + target_employee_id[1:]
    profiles = {
        "clara": {
            "id": "clara",
            "name": "Clara",
            "role": "AI Team OS Manager",
            "status": "active",
            "skill_refs": [],
            "memory_scopes": ["team:governance"],
            "capability_tags": ["governance"],
            "personality_tags": ["evidence-driven"],
        },
        target_employee_id: {
            "id": target_employee_id,
            "name": target_name,
            "role": "AI RD / Implementer",
            "status": "active",
            "skill_refs": [],
            "memory_scopes": [],
            "capability_tags": [],
            "personality_tags": [],
            "current_load": {},
        },
    }
    for employee_id, profile in profiles.items():
        (employees_dir / f"{employee_id}.yaml").write_text(
            yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )


def _latest_runtime_feedback(employee_id: str) -> Any | None:
    ledger = employee_work_ledger(employee_id)
    return next((item for item in ledger.quality_feedback if item.kind == "runtime_result"), None)


def _missing_expected_profile_updates(applied_changes: dict[str, list[str]], employee_id: str) -> list[str]:
    target_employee_id = _safe_employee_id(employee_id) or "alex"
    expected = {
        "skill_refs": "runtime-blocker-triage",
        "memory_scopes": f"employee:{target_employee_id}:runtime-blockers",
        "capability_tags": "runtime-debugging",
        "personality_tags": "evidence-driven",
    }
    missing: list[str] = []
    for field, value in expected.items():
        observed = {str(item).strip().lower() for item in applied_changes.get(field, [])}
        if value.lower() not in observed:
            missing.append(f"{field}:{value}")
    return missing


def _safe_employee_id(value: str) -> str:
    return "".join(char for char in value.strip().lower() if char.isalnum() or char in {"_", "-"})


def _improvement_loop_evidence(proof: EmployeeGrowthImprovementLoopProof) -> dict[str, Any]:
    return {
        "status": proof.status,
        "detail": proof.detail,
        "employee_id": proof.employee_id,
        "ticket_id": proof.ticket_id,
        "feedback_id": proof.feedback_id,
        "candidate_id": proof.candidate_id,
        "asset_id": proof.asset_id,
        "application_status": proof.application_status,
        "ticket_report_id": proof.ticket_report_id,
        "applied_change_count": proof.applied_change_count,
        "workspace": proof.workspace,
        "error": proof.error,
    }


def _select_employee(profiles: list[dict[str, Any]], *, employee_id: str) -> dict[str, Any] | None:
    normalized = employee_id.strip().lower()
    if normalized:
        return next((profile for profile in profiles if str(profile.get("id") or "").strip().lower() == normalized), None)
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for profile in profiles:
        candidate_id = str(profile.get("id") or "").strip()
        if not candidate_id:
            continue
        try:
            ledger = employee_work_ledger(candidate_id)
        except Exception:
            continue
        score = (
            len(ledger.quality_feedback) * 4
            + len(ledger.runtime_runs) * 3
            + len(ledger.approved_assets) * 2
            + len(ledger.current_tickets)
            + len(ledger.reports)
        )
        if candidate_id.strip().lower() == "clara" and any(
            str(item.get("id") or "").strip().lower() != "clara"
            for item in profiles
        ):
            score -= 1000
        scored.append((score, candidate_id, profile))
    if not scored:
        return profiles[0] if profiles else None
    return sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)[0][2]


def _load_profiles_readonly(workspace_root: Path) -> list[dict[str, Any]]:
    employees_dir = workspace_root / ".aiteamos" / "employees"
    profiles: list[dict[str, Any]] = []
    for path in sorted(employees_dir.glob("*.yaml")):
        try:
            profiles.append(normalize_employee_profile(read_employee_profile(path), path, workspace_root=workspace_root))
        except Exception:
            continue
    return profiles


def _check(
    check_id: str,
    passed: bool,
    detail: str,
    evidence: dict[str, Any],
    *,
    warning_id: str = "",
) -> EmployeeGrowthEvalCheck:
    status = "passed" if passed else "warning" if warning_id else "blocked"
    return EmployeeGrowthEvalCheck(
        id=check_id,
        status=status,
        detail=detail,
        evidence={**evidence, **({"warning_id": warning_id} if warning_id and not passed else {})},
    )


def _workspace_root(workspace_dir: Path | None) -> Path:
    raw = workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).expanduser()
    root = raw.resolve()
    return root.parent if root.name == ".aiteamos" else root


def _commands() -> list[str]:
    return [
        "python scripts/employee_growth_eval_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-e-employee-growth-eval-smoke.json",
    ]


def _detail(status: str, employee_id: str, blockers: list[str], warnings: list[str]) -> str:
    if status == "passed":
        return f"Employee growth evidence is passing for {employee_id}."
    if blockers:
        return f"Employee growth evidence for {employee_id} is blocked by {len(blockers)} signal(s)."
    return f"Employee growth evidence for {employee_id} has {len(warnings)} warning signal(s)."


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _now() -> str:
    return datetime.now(UTC).isoformat()
