"""Aggregate Plan v8 release readiness from existing read-only contracts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .live_provider_dogfood_service import (
    LiveProviderDogfoodReadinessResponse,
    LiveProviderDogfoodRequest,
    LiveProviderDogfoodService,
)
from .plan_v8_artifact_service import PlanV8ArtifactSummary, plan_v8_artifact_summary
from .provider_conformance_service import ProviderConformanceResponse, provider_conformance_report
from .release_hygiene_service import ReleaseHygieneResponse, release_hygiene_report
from .schema_registry_service import SchemaRegistryResponse, schema_registry_report

PLAN_V8_READINESS_CONTRACT_VERSION = "aiteamos_plan_v8_readiness.v1"
_CHAT_VISIBLE_RESPONSE_STATES = ("completed", "blocked", "needs_approval", "handoff", "provider_blocker")
_COMPAT_VISIBLE_RESPONSE_STATES = set(_CHAT_VISIBLE_RESPONSE_STATES) | {"provider_blocked"}


class PlanV8ReadinessCheck(BaseModel):
    id: str
    scope: str
    status: str
    detail: str
    blockers: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class PlanV8ReadinessNextStep(BaseModel):
    id: str
    label: str
    detail: str = ""
    kind: str = "info"
    status: str = ""
    href: str = ""
    command: str = ""
    mutation_gate_required: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class PlanV8ReadinessSummary(BaseModel):
    check_count: int = 0
    passed_count: int = 0
    warning_count: int = 0
    blocked_count: int = 0
    failed_count: int = 0
    ready_for_release: bool = False
    contract_version: str = PLAN_V8_READINESS_CONTRACT_VERSION
    next_action: str = ""
    next_steps: list[str] = Field(default_factory=list)
    next_step_actions: list[PlanV8ReadinessNextStep] = Field(default_factory=list)


class PlanV8ReadinessResponse(BaseModel):
    contract_version: str = PLAN_V8_READINESS_CONTRACT_VERSION
    status: str
    detail: str
    summary: PlanV8ReadinessSummary = Field(default_factory=PlanV8ReadinessSummary)
    checks: list[PlanV8ReadinessCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


async def plan_v8_readiness_report(
    *,
    workspace_dir: Path | None = None,
    artifacts: PlanV8ArtifactSummary | None = None,
    release_hygiene: ReleaseHygieneResponse | None = None,
    schema_registry: SchemaRegistryResponse | None = None,
    provider_conformance: ProviderConformanceResponse | None = None,
    live_provider_dogfood: LiveProviderDogfoodReadinessResponse | None = None,
) -> PlanV8ReadinessResponse:
    """Build a release review checklist without mutating providers or runtime state."""

    root = _workspace_root(workspace_dir)
    artifacts = artifacts or plan_v8_artifact_summary(workspace_dir=root)
    release_hygiene = release_hygiene or release_hygiene_report(workspace_dir=root)
    schema_registry = schema_registry or schema_registry_report(workspace_dir=root)
    provider_conformance = provider_conformance or await provider_conformance_report()
    live_provider_dogfood = live_provider_dogfood or await LiveProviderDogfoodService(workspace_dir=root).readiness(
        LiveProviderDogfoodRequest(execute=True)
    )

    checks = [
        _chat_visible_response_check(artifacts),
        _artifact_evidence_check(artifacts),
        _live_provider_dogfood_check(live_provider_dogfood),
        _provider_boundary_check(provider_conformance),
        _schema_registry_check(schema_registry),
        _release_hygiene_check(release_hygiene),
    ]
    failed = [item for item in checks if item.status == "failed"]
    blocked = [item for item in checks if item.status == "blocked"]
    warned = [item for item in checks if item.status == "warning"]
    status = "failed" if failed else "blocked" if blocked else "warning" if warned else "passed"
    blockers = _unique([blocker for check in checks for blocker in check.blockers])
    next_step_actions = _next_step_actions(status, blockers, release_hygiene, live_provider_dogfood=live_provider_dogfood)
    summary = PlanV8ReadinessSummary(
        check_count=len(checks),
        passed_count=sum(1 for item in checks if item.status == "passed"),
        warning_count=len(warned),
        blocked_count=len(blocked),
        failed_count=len(failed),
        ready_for_release=status == "passed",
        next_action=_next_action(status, blockers, release_hygiene),
        next_steps=[step.detail or step.label for step in next_step_actions],
        next_step_actions=next_step_actions,
    )
    return PlanV8ReadinessResponse(
        status=status,
        detail=_detail(status, blockers),
        summary=summary,
        checks=checks,
        blockers=blockers,
        commands=_commands(),
        evidence_refs=_evidence_refs(artifacts),
    )


def _chat_visible_response_check(artifacts: PlanV8ArtifactSummary) -> PlanV8ReadinessCheck:
    latest = artifacts.latest_agent_server_smoke
    matrix = artifacts.latest_chat_visible_response_matrix
    summary = latest.summary if latest is not None else {}
    matrix_summary = matrix.summary if matrix is not None else {}
    blockers: list[str] = []
    if latest is None:
        blockers.append("agent_server_smoke_missing")
    if summary.get("visible_response_version") != "chat_visible_response.v1":
        blockers.append("chat_visible_response_contract_missing")
    if str(summary.get("visible_display_state") or "") not in _COMPAT_VISIBLE_RESPONSE_STATES:
        blockers.append("chat_visible_response_state_missing")
    if str(summary.get("runtime_status") or "") not in _COMPAT_VISIBLE_RESPONSE_STATES:
        blockers.append("runtime_status_mapping_missing")
    observed_states = set(_strings(matrix_summary.get("observed_states")))
    missing_states = [
        state
        for state in _CHAT_VISIBLE_RESPONSE_STATES
        if state not in observed_states and not (state == "provider_blocker" and "provider_blocked" in observed_states)
    ]
    if matrix is None:
        blockers.append("chat_visible_response_matrix_missing")
    elif matrix.status != "passed":
        blockers.append("chat_visible_response_matrix_not_passed")
    if missing_states:
        blockers.append("chat_visible_response_matrix_state_missing")
    return PlanV8ReadinessCheck(
        id="chat_visible_response",
        scope="Track A",
        status="blocked" if blockers else "passed",
        detail="Chat main-thread visible response contract from fresh Agent Server evidence plus the five-state visible-response matrix.",
        blockers=blockers,
        evidence={
            "artifact": latest.name if latest is not None else "",
            "matrix_artifact": matrix.name if matrix is not None else "",
            "visible_response_version": str(summary.get("visible_response_version") or ""),
            "visible_display_state": str(summary.get("visible_display_state") or ""),
            "runtime_status": str(summary.get("runtime_status") or ""),
            "current_node": str(summary.get("current_node") or ""),
            "matrix_required_states": list(_CHAT_VISIBLE_RESPONSE_STATES),
            "matrix_observed_states": _strings(matrix_summary.get("observed_states")),
            "matrix_passed_case_count": matrix_summary.get("passed_case_count", 0),
        },
    )


def _artifact_evidence_check(artifacts: PlanV8ArtifactSummary) -> PlanV8ReadinessCheck:
    blockers = list(artifacts.evidence_gaps)
    status = "blocked" if blockers else "warning" if artifacts.provider_blockers or artifacts.evidence_warnings else "passed"
    return PlanV8ReadinessCheck(
        id="plan_v8_artifact_evidence",
        scope="Track C/F/G",
        status=status,
        detail="Latest plan_v8 artifact summary for Agent Server, live readiness, context retrieval, and Asset provenance.",
        blockers=blockers + list(artifacts.provider_blockers),
        evidence={
            "artifact_count": artifacts.artifact_count,
            "agent_server_smoke_count": artifacts.agent_server_smoke_count,
            "chat_visible_response_matrix_count": artifacts.chat_visible_response_matrix_count,
            "live_provider_readiness_count": artifacts.live_provider_readiness_count,
            "live_provider_soak_plan_count": artifacts.live_provider_soak_plan_count,
            "live_provider_soak_evidence_count": artifacts.live_provider_soak_evidence_count,
            "plane_scope_discovery_smoke_count": artifacts.plane_scope_discovery_smoke_count,
            "plane_scope_discovery_smoke_status": (
                artifacts.latest_plane_scope_discovery_smoke.status
                if artifacts.latest_plane_scope_discovery_smoke is not None
                else ""
            ),
            "plane_scope_discovery_status": (
                artifacts.latest_plane_scope_discovery_smoke.summary.get("discovery_status")
                if artifacts.latest_plane_scope_discovery_smoke is not None
                else ""
            ),
            "plane_scope_discovery_suggestion_count": (
                artifacts.latest_plane_scope_discovery_smoke.summary.get("suggestion_count")
                if artifacts.latest_plane_scope_discovery_smoke is not None
                else 0
            ),
            "plane_scope_discovery_external_mutation": (
                artifacts.latest_plane_scope_discovery_smoke.summary.get("external_mutation")
                if artifacts.latest_plane_scope_discovery_smoke is not None
                else False
            ),
            "plane_ticket_action_smoke_count": artifacts.plane_ticket_action_smoke_count,
            "plane_ticket_action_smoke_status": (
                artifacts.latest_plane_ticket_action_smoke.status
                if artifacts.latest_plane_ticket_action_smoke is not None
                else ""
            ),
            "plane_ticket_action_smoke_provider": (
                artifacts.latest_plane_ticket_action_smoke.summary.get("provider")
                if artifacts.latest_plane_ticket_action_smoke is not None
                else ""
            ),
            "ticket_loop_worker_soak_count": artifacts.ticket_loop_worker_soak_count,
            "context_retrieval_eval_count": artifacts.context_retrieval_eval_count,
            "asset_provenance_eval_count": artifacts.asset_provenance_eval_count,
            "plan_v8_readiness_count": artifacts.plan_v8_readiness_count,
            "employee_growth_eval_count": artifacts.employee_growth_eval_count,
            "employee_growth_warning_count": len(artifacts.evidence_warnings),
            "evidence_warnings": artifacts.evidence_warnings,
            "employee_growth_improvement_loop_proof_status": (
                artifacts.latest_employee_growth_eval.summary.get("improvement_loop_proof_status")
                if artifacts.latest_employee_growth_eval is not None
                else ""
            ),
            "employee_growth_improvement_loop_application_status": (
                artifacts.latest_employee_growth_eval.summary.get("improvement_loop_application_status")
                if artifacts.latest_employee_growth_eval is not None
                else ""
            ),
            "employee_growth_improvement_loop_ticket_report_id": (
                artifacts.latest_employee_growth_eval.summary.get("improvement_loop_ticket_report_id")
                if artifacts.latest_employee_growth_eval is not None
                else ""
            ),
            "ticket_loop_worker_processed_delta": (
                artifacts.latest_ticket_loop_worker_soak.summary.get("worker_processed_delta")
                if artifacts.latest_ticket_loop_worker_soak is not None
                else 0
            ),
            "ticket_loop_worker_policy_action_delta": (
                artifacts.latest_ticket_loop_worker_soak.summary.get("worker_policy_action_delta")
                if artifacts.latest_ticket_loop_worker_soak is not None
                else 0
            ),
            "ticket_loop_worker_daemon_status": (
                artifacts.latest_ticket_loop_worker_soak.summary.get("daemon_status")
                if artifacts.latest_ticket_loop_worker_soak is not None
                else ""
            ),
            "latest_generated_at": artifacts.latest_generated_at,
        },
    )


def _live_provider_dogfood_check(readiness: LiveProviderDogfoodReadinessResponse) -> PlanV8ReadinessCheck:
    blockers = _unique([str(item.get("reason") or item.get("id") or "") for item in readiness.blockers if isinstance(item, dict)])
    return PlanV8ReadinessCheck(
        id="live_provider_dogfood",
        scope="Track C",
        status="passed" if readiness.status == "ready" else "blocked",
        detail="Readiness for the live Plane / Graphiti Ticket-loop dogfood gate.",
        blockers=blockers,
        evidence={
            "status": readiness.status,
            "profile": readiness.profile,
            "selected_executor_id": readiness.selected_executor_id,
            "mutation_gate_open": bool(readiness.mutation_gate.get("open")),
            "repo_write_ready_count": readiness.summary.get("repo_write_ready_count"),
            "ticket_backend_status": readiness.summary.get("ticket_backend_status"),
            "ticket_backend_mode": readiness.summary.get("ticket_backend_mode"),
            "ticket_backend_provider": readiness.summary.get("ticket_backend_provider"),
            "plane_ticket_backend_selected": readiness.summary.get("plane_ticket_backend_selected"),
            "plane_ticket_backend_setup_status": readiness.summary.get("plane_ticket_backend_setup_status"),
            "plane_ticket_backend_setup_required": readiness.summary.get("plane_ticket_backend_setup_required"),
            "plane_ticket_backend_configured": readiness.summary.get("plane_ticket_backend_configured"),
            "plane_ticket_workspace_configured": readiness.summary.get("plane_ticket_workspace_configured"),
            "plane_ticket_project_configured": readiness.summary.get("plane_ticket_project_configured"),
            "plane_ticket_api_key_configured": readiness.summary.get("plane_ticket_api_key_configured"),
            "plane_ticket_scope_status": readiness.summary.get("plane_ticket_scope_status"),
            "plane_ticket_scope_candidate_count": readiness.summary.get("plane_ticket_scope_candidate_count"),
            "plane_ticket_scope_missing_count": readiness.summary.get("plane_ticket_scope_missing_count"),
            "plane_ticket_scope_setup_action": readiness.summary.get("plane_ticket_scope_setup_action"),
            "ticket_backend_release_target_status": readiness.summary.get("ticket_backend_release_target_status"),
            "ticket_backend_release_target_ready": readiness.summary.get("ticket_backend_release_target_ready"),
            "ticket_backend_release_target_blockers": readiness.summary.get("ticket_backend_release_target_blockers"),
            "ticket_backend_release_target_setup_action": readiness.summary.get("ticket_backend_release_target_setup_action"),
            "memory_backend_status": readiness.summary.get("memory_backend_status"),
        },
    )


def _provider_boundary_check(conformance: ProviderConformanceResponse) -> PlanV8ReadinessCheck:
    blockers: list[str] = []
    direct_llm_providers = [
        provider.provider_id
        for provider in conformance.providers
        if "direct_llm" in provider.provider_id or provider.implementation == "direct_llm"
    ]
    if direct_llm_providers:
        blockers.extend([f"direct_llm_provider:{item}" for item in direct_llm_providers])
    blockers.extend([f"runtime_boundary:{item}" for item in conformance.summary.runtime_boundary_blockers])
    if conformance.summary.core_blocked_count:
        blockers.append("core_provider_not_production_ready")
    status = "blocked" if blockers else "passed"
    return PlanV8ReadinessCheck(
        id="provider_boundary",
        scope="Track B/C",
        status=status,
        detail="Provider conformance keeps Ticket / Employee / Asset facts AITeamOS-owned and runtime behind LangGraph/RuntimeExecutor boundaries.",
        blockers=blockers,
        evidence={
            "contract_version": conformance.contract_version,
            "provider_count": conformance.summary.provider_count,
            "production_ready_count": conformance.summary.production_ready_count,
            "core_required_count": conformance.summary.core_required_count,
            "core_blocked_count": conformance.summary.core_blocked_count,
            "direct_llm_provider_count": len(direct_llm_providers),
            "runtime_boundary_status": conformance.summary.runtime_boundary_status,
            "runtime_boundary_checks": conformance.summary.runtime_boundary_checks,
            "runtime_boundary_warnings": conformance.summary.runtime_boundary_warnings,
            "runtime_boundary_blocker_count": len(conformance.summary.runtime_boundary_blockers),
        },
    )


def _schema_registry_check(schema_registry: SchemaRegistryResponse) -> PlanV8ReadinessCheck:
    blockers: list[str] = []
    if schema_registry.status != "passed":
        blockers.append(f"schema_registry_{schema_registry.status}")
    if schema_registry.summary.migration_required_count:
        blockers.append("schema_migration_required")
    return PlanV8ReadinessCheck(
        id="schema_registry",
        scope="Track G",
        status="blocked" if blockers else "passed",
        detail="Local Ticket, Employee, Asset, and runtime ledgers are on expected schema boundaries.",
        blockers=blockers,
        evidence={
            "contract_version": schema_registry.contract_version,
            "store_count": schema_registry.summary.store_count,
            "current_count": schema_registry.summary.current_count,
            "migration_required_count": schema_registry.summary.migration_required_count,
            "covered_domains": schema_registry.summary.covered_domains,
        },
    )


def _release_hygiene_check(release_hygiene: ReleaseHygieneResponse) -> PlanV8ReadinessCheck:
    blockers: list[str] = []
    if release_hygiene.summary.unknown_count:
        blockers.append("unknown_changed_paths")
    if release_hygiene.status == "blocked":
        blockers.append("release_hygiene_blocked")
    return PlanV8ReadinessCheck(
        id="release_hygiene",
        scope="Track G",
        status="blocked" if blockers else "warning" if release_hygiene.status == "warning" else "passed",
        detail="Source files, generated artifacts, local projections, and test outputs are classified for release review.",
        blockers=blockers,
        evidence={
            "contract_version": release_hygiene.contract_version,
            "git_root": release_hygiene.git_root,
            "total_changed": release_hygiene.summary.total_changed,
            "source_count": release_hygiene.summary.source_count,
            "generated_artifact_count": release_hygiene.summary.generated_artifact_count,
            "local_projection_count": release_hygiene.summary.local_projection_count,
            "unknown_count": release_hygiene.summary.unknown_count,
        },
    )


def _workspace_root(workspace_dir: Path | None) -> Path:
    raw = workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).expanduser()
    root = raw.resolve()
    return root.parent if root.name == ".aiteamos" else root


def _commands() -> list[str]:
    return [
        "python scripts/plan_v8_readiness.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json",
        "python scripts/chat_visible_response_matrix.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-a-chat-visible-response-matrix.json",
        "python scripts/live_provider_soak_plan.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-plan.json",
        "python scripts/live_provider_soak_evidence.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-evidence.json",
        "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
        "python scripts/plane_scope_discovery_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-plane-scope-discovery-smoke.json",
        "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
        "python scripts/employee_growth_eval_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-e-employee-growth-eval-smoke.json",
        "python scripts/environment_smoke.py --workspace-dir .",
        "pytest tests/test_file_system_status_routes.py tests/test_context_retrieval_eval.py -q",
        "cd apps/dashboard && npx vitest run --environment jsdom src/__tests__/system-status-page.test.tsx src/__tests__/assets-page.test.tsx src/__tests__/tickets-page.test.tsx",
        "cd apps/dashboard && npm run build",
    ]


def _evidence_refs(artifacts: PlanV8ArtifactSummary) -> list[str]:
    refs = [
        artifacts.latest_agent_server_smoke.name if artifacts.latest_agent_server_smoke else "",
        artifacts.latest_chat_visible_response_matrix.name if artifacts.latest_chat_visible_response_matrix else "",
        artifacts.latest_live_provider_readiness.name if artifacts.latest_live_provider_readiness else "",
        artifacts.latest_live_provider_soak_plan.name if artifacts.latest_live_provider_soak_plan else "",
        artifacts.latest_live_provider_soak_evidence.name if artifacts.latest_live_provider_soak_evidence else "",
        artifacts.latest_plane_scope_discovery_smoke.name if artifacts.latest_plane_scope_discovery_smoke else "",
        artifacts.latest_plane_ticket_action_smoke.name if artifacts.latest_plane_ticket_action_smoke else "",
        artifacts.latest_ticket_loop_worker_soak.name if artifacts.latest_ticket_loop_worker_soak else "",
        artifacts.latest_context_retrieval_eval.name if artifacts.latest_context_retrieval_eval else "",
        artifacts.latest_asset_provenance_eval.name if artifacts.latest_asset_provenance_eval else "",
        artifacts.latest_plan_v8_readiness.name if artifacts.latest_plan_v8_readiness else "",
        artifacts.latest_employee_growth_eval.name if artifacts.latest_employee_growth_eval else "",
    ]
    return _unique(refs)


def _next_action(status: str, blockers: list[str], release_hygiene: ReleaseHygieneResponse) -> str:
    if "plane_ticket_backend_not_selected" in blockers:
        return "Complete the Code Repository Plane workspace/project scope, switch the Ticket backend to Plane, rerun the Plane action smoke, then reopen the live mutation gate for Plane / Graphiti dogfood."
    if "live_provider_dogfood_not_confirmed" in blockers:
        return "Open the live mutation gate explicitly, then run the live provider dogfood soak against Plane and Graphiti."
    if "unknown_changed_paths" in blockers:
        return "Classify unknown changed paths before release review."
    if release_hygiene.status == "warning":
        return "Review source diffs separately from generated artifacts and local provider projections."
    if status == "passed":
        return "Run the live soak and release review commands as the final confirmation set."
    return "Clear the listed blockers, then rerun the Plan v8 readiness command."


def _next_step_actions(
    status: str,
    blockers: list[str],
    release_hygiene: ReleaseHygieneResponse,
    *,
    live_provider_dogfood: LiveProviderDogfoodReadinessResponse | None = None,
) -> list[PlanV8ReadinessNextStep]:
    actions: list[PlanV8ReadinessNextStep] = []
    live_summary = live_provider_dogfood.summary if live_provider_dogfood is not None else {}
    mutation_gate = live_provider_dogfood.mutation_gate if live_provider_dogfood is not None else {}
    plane_scope_status = str(live_summary.get("plane_ticket_scope_status") or "")
    plane_scope_candidate_count = _int_value(live_summary.get("plane_ticket_scope_candidate_count"))
    plane_scope_missing_count = _int_value(live_summary.get("plane_ticket_scope_missing_count"))
    plane_setup_status = str(live_summary.get("plane_ticket_backend_setup_status") or "")
    ticket_backend_mode = str(live_summary.get("ticket_backend_mode") or "")
    ticket_backend_provider = str(live_summary.get("ticket_backend_provider") or "")
    plane_backend_selected = bool(live_summary.get("plane_ticket_backend_selected"))
    release_target_blockers = [
        str(item)
        for item in live_summary.get("ticket_backend_release_target_blockers", [])
        if str(item)
    ] if isinstance(live_summary.get("ticket_backend_release_target_blockers"), list) else []
    mutation_gate_open = bool(mutation_gate.get("open"))
    if "plane_ticket_backend_not_selected" in blockers or "ticket_provider_not_ready" in blockers:
        actions.extend(
            [
                PlanV8ReadinessNextStep(
                    id="complete_code_repository_plane_scope",
                    label="Code Repository scope",
                    detail="Open Settings -> Code Repositories, use Discover Plane scope to read workspace/project candidates without mutation, then complete the AITeamOS repository Plane scope.",
                    kind="settings",
                    status=plane_scope_status or "blocked",
                    href="#/settings/code-repositories",
                    evidence={
                        "scope_candidates": plane_scope_candidate_count,
                        "scope_missing": plane_scope_missing_count,
                        "setup_action": str(live_summary.get("plane_ticket_scope_setup_action") or ""),
                        "discovery_ui_action": "Discover Plane scope",
                        "discovery_endpoint": "/api/v1/tickets/backend/plane-scope/discovery",
                        "api_key_configured": bool(live_summary.get("plane_ticket_api_key_configured")),
                        "external_mutation": False,
                    },
                ),
                PlanV8ReadinessNextStep(
                    id="apply_plane_ticket_backend",
                    label="Ticket Backend Plane mode",
                    detail="Open Settings -> Ticket Backend and use Apply scope or save the form with mode=plane.",
                    kind="settings",
                    status="ready" if plane_backend_selected and plane_setup_status == "ready" else plane_setup_status or "setup_blocked",
                    href="#/settings/ticket-backend",
                    evidence={
                        "current_mode": ticket_backend_mode,
                        "release_target_status": str(live_summary.get("ticket_backend_release_target_status") or ""),
                        "release_target_ready": bool(live_summary.get("ticket_backend_release_target_ready")),
                        "release_target_setup_action": str(live_summary.get("ticket_backend_release_target_setup_action") or ""),
                        "release_target_blockers": release_target_blockers,
                        "current_provider": ticket_backend_provider,
                        "plane_selected": plane_backend_selected,
                        "workspace_configured": bool(live_summary.get("plane_ticket_workspace_configured")),
                        "project_configured": bool(live_summary.get("plane_ticket_project_configured")),
                        "api_key_configured": bool(live_summary.get("plane_ticket_api_key_configured")),
                    },
                ),
                PlanV8ReadinessNextStep(
                    id="run_live_provider_readiness_smoke",
                    label="Provider readiness smoke",
                    detail="Run python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json before any provider mutation.",
                    kind="command",
                    status="ready_to_run",
                    command="python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
                    evidence={
                        "external_mutation": False,
                        "provider_smoke_status": "read_only",
                    },
                ),
                PlanV8ReadinessNextStep(
                    id="run_plane_action_smoke",
                    label="Plane action smoke",
                    detail="Run python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json.",
                    kind="command",
                    status="blocked" if not plane_backend_selected else "ready_to_run",
                    command="python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
                    evidence={
                        "requires_ticket_backend_mode": "plane",
                        "current_mode": ticket_backend_mode,
                    },
                ),
            ]
        )
    if "memory_provider_not_ready" in blockers:
        actions.append(
            PlanV8ReadinessNextStep(
                id="confirm_memory_backend",
                label="Memory Backend",
                detail="Open Settings -> Memory Backend and confirm Graphiti / Neo4j setup before live provider dogfood.",
                kind="settings",
                status=str(live_summary.get("memory_backend_status") or "blocked"),
                href="#/settings/memory-backend",
            )
        )
    if "live_provider_dogfood_not_confirmed" in blockers:
        actions.extend(
            [
                PlanV8ReadinessNextStep(
                    id="keep_mutation_gate_closed",
                    label="Mutation gate",
                    detail="Keep AITEAMOS_LIVE_PROVIDER_DOGFOOD unset until Plane and Graphiti setup evidence is ready.",
                    kind="guard",
                    status="open" if mutation_gate_open else "closed",
                    command="unset AITEAMOS_LIVE_PROVIDER_DOGFOOD",
                    mutation_gate_required=True,
                    evidence={
                        "gate_open": mutation_gate_open,
                        "confirm_env_var": str(mutation_gate.get("confirm_env_var") or "AITEAMOS_LIVE_PROVIDER_DOGFOOD"),
                    },
                ),
                PlanV8ReadinessNextStep(
                    id="run_live_provider_dogfood",
                    label="Live dogfood soak",
                    detail="When ready, run AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json.",
                    kind="command",
                    status="blocked" if not mutation_gate_open else "ready_to_run",
                    command="AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
                    mutation_gate_required=True,
                    evidence={
                        "requires_gate_open": True,
                        "gate_open": mutation_gate_open,
                    },
                ),
            ]
        )
    if "unknown_changed_paths" in blockers:
        actions.append(
            PlanV8ReadinessNextStep(
                id="classify_changed_paths",
                label="Release hygiene",
                detail="Classify unknown changed paths before release review.",
                kind="review",
                status="blocked",
            )
        )
    if not actions and release_hygiene.status == "warning":
        actions.append(
            PlanV8ReadinessNextStep(
                id="review_release_hygiene",
                label="Release hygiene",
                detail="Review source diffs separately from generated artifacts and local provider projections.",
                kind="review",
                status=release_hygiene.status,
            )
        )
    if not actions and status == "passed":
        actions.extend(
            [
                PlanV8ReadinessNextStep(
                    id="rerun_plan_v8_readiness",
                    label="Plan v8 readiness",
                    detail="Run python scripts/plan_v8_readiness.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json.",
                    kind="command",
                    status="ready_to_run",
                    command="python scripts/plan_v8_readiness.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-g-plan-v8-readiness.json",
                ),
                PlanV8ReadinessNextStep(
                    id="run_final_live_soak",
                    label="Final live soak",
                    detail="Run the live soak commands listed in the Plan v8 readiness payload as the final confirmation set.",
                    kind="command",
                    status="ready_to_run",
                ),
            ]
        )
    if not actions:
        actions.append(
            PlanV8ReadinessNextStep(
                id="clear_blockers",
                label="Clear blockers",
                detail="Clear the listed blockers, then rerun the Plan v8 readiness command.",
                kind="review",
                status="blocked",
            )
        )
    deduped: list[PlanV8ReadinessNextStep] = []
    seen: set[str] = set()
    for action in actions:
        if action.id in seen:
            continue
        seen.add(action.id)
        deduped.append(action)
    return deduped


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _detail(status: str, blockers: list[str]) -> str:
    if status == "passed":
        return "Plan v8 readiness checks are passing."
    if status in {"blocked", "failed"} and blockers:
        return f"Plan v8 readiness is blocked by {len(blockers)} signal(s)."
    if blockers:
        return f"Plan v8 readiness has {len(blockers)} warning signal(s) for release review."
    return "Plan v8 readiness has warnings that need release review."


def _strings(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return _unique([str(item or "").strip() for item in items if str(item or "").strip()])


def _unique(items: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique
