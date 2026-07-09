"""Read-only repeated live-provider soak plan for Plan v8 Track C."""

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

LIVE_PROVIDER_SOAK_PLAN_CONTRACT_VERSION = "aiteamos_live_provider_soak_plan.v1"


class LiveProviderSoakScenario(BaseModel):
    id: str
    title: str
    expected_state: str
    status: str
    detail: str
    command: str
    required_evidence: list[str] = Field(default_factory=list)
    ui_surfaces: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class LiveProviderSoakPlanSummary(BaseModel):
    scenario_count: int = 0
    ready_scenario_count: int = 0
    blocked_scenario_count: int = 0
    expected_state_count: int = 0
    expected_states: list[str] = Field(default_factory=list)
    mutation_gate_open: bool = False
    ticket_backend_status: str = ""
    ticket_backend_mode: str = ""
    ticket_backend_provider: str = ""
    plane_ticket_backend_selected: bool = False
    plane_ticket_backend_setup_status: str = ""
    plane_ticket_backend_setup_required: list[str] = Field(default_factory=list)
    plane_ticket_scope_status: str = ""
    plane_ticket_scope_candidate_count: int = 0
    plane_ticket_scope_missing_count: int = 0
    plane_ticket_scope_setup_action: str = ""
    memory_backend_status: str = ""
    selected_executor_id: str = ""
    ready_to_execute: bool = False
    contract_version: str = LIVE_PROVIDER_SOAK_PLAN_CONTRACT_VERSION


class LiveProviderSoakPlanResponse(BaseModel):
    contract_version: str = LIVE_PROVIDER_SOAK_PLAN_CONTRACT_VERSION
    status: str
    detail: str
    summary: LiveProviderSoakPlanSummary = Field(default_factory=LiveProviderSoakPlanSummary)
    blockers: list[str] = Field(default_factory=list)
    scenarios: list[LiveProviderSoakScenario] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


async def live_provider_soak_plan_report(
    *,
    workspace_dir: Path | None = None,
    readiness: LiveProviderDogfoodReadinessResponse | None = None,
    artifacts: PlanV8ArtifactSummary | None = None,
) -> LiveProviderSoakPlanResponse:
    root = _workspace_root(workspace_dir)
    readiness = readiness or await LiveProviderDogfoodService(workspace_dir=root).readiness(LiveProviderDogfoodRequest(execute=True))
    artifacts = artifacts or plan_v8_artifact_summary(workspace_dir=root)
    blockers = _readiness_blockers(readiness)
    scenarios = _scenarios(blockers=blockers, readiness=readiness)
    blocked_scenarios = [item for item in scenarios if item.status == "blocked"]
    status = "ready" if not blocked_scenarios else "blocked"
    expected_states = _unique([item.expected_state for item in scenarios])
    mutation_gate = readiness.mutation_gate if isinstance(readiness.mutation_gate, dict) else {}
    summary = LiveProviderSoakPlanSummary(
        scenario_count=len(scenarios),
        ready_scenario_count=len(scenarios) - len(blocked_scenarios),
        blocked_scenario_count=len(blocked_scenarios),
        expected_state_count=len(expected_states),
        expected_states=expected_states,
        mutation_gate_open=bool(mutation_gate.get("open")),
        ticket_backend_status=str(readiness.summary.get("ticket_backend_status") or ""),
        ticket_backend_mode=str(readiness.summary.get("ticket_backend_mode") or ""),
        ticket_backend_provider=str(readiness.summary.get("ticket_backend_provider") or ""),
        plane_ticket_backend_selected=bool(readiness.summary.get("plane_ticket_backend_selected")),
        plane_ticket_backend_setup_status=str(readiness.summary.get("plane_ticket_backend_setup_status") or ""),
        plane_ticket_backend_setup_required=_strings(readiness.summary.get("plane_ticket_backend_setup_required")),
        plane_ticket_scope_status=str(readiness.summary.get("plane_ticket_scope_status") or ""),
        plane_ticket_scope_candidate_count=_safe_int(readiness.summary.get("plane_ticket_scope_candidate_count")),
        plane_ticket_scope_missing_count=_safe_int(readiness.summary.get("plane_ticket_scope_missing_count")),
        plane_ticket_scope_setup_action=str(readiness.summary.get("plane_ticket_scope_setup_action") or ""),
        memory_backend_status=str(readiness.summary.get("memory_backend_status") or ""),
        selected_executor_id=readiness.selected_executor_id,
        ready_to_execute=status == "ready",
    )
    return LiveProviderSoakPlanResponse(
        status=status,
        detail=_detail(status, blockers),
        summary=summary,
        blockers=blockers,
        scenarios=scenarios,
        commands=_commands(),
        evidence_refs=_evidence_refs(artifacts),
    )


def _scenarios(*, blockers: list[str], readiness: LiveProviderDogfoodReadinessResponse) -> list[LiveProviderSoakScenario]:
    scenario_specs = [
        {
            "id": "core_loop_completed_closeout_asset",
            "title": "Completed closeout with Asset proposal",
            "expected_state": "completed",
            "detail": "Fresh Agent Server core loop creates or advances a Ticket, writes report/evidence, promotes governed Asset evidence, projects to Graphiti, and recalls it.",
            "command": "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
            "required_evidence": [
                "fresh_agent_server",
                "ticket_report",
                "memory_candidate_ids",
                "asset_record_ids",
                "graphiti_projection_statuses",
                "graphiti_recall_count",
            ],
            "ui_surfaces": ["Chat", "Tickets", "Assets", "Runtime Replay", "System Status"],
        },
        {
            "id": "natural_handoff",
            "title": "Natural Employee handoff",
            "expected_state": "handoff",
            "detail": "Core loop records a durable Ticket-backed handoff from Clara to the worker Employee and exposes the handoff in Chat/Ticket/Employee state.",
            "command": "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --require-natural-handoff --expected-handoff-target alex --output .aiteamos/artifacts/plan_v8/track-c-live-soak-handoff.json",
            "required_evidence": [
                "handoff_summary",
                "ticket_handoff_refs",
                "natural_handoff",
                "handoff_target_employee_id",
            ],
            "ui_surfaces": ["Chat", "Tickets", "Employees", "Runtime Replay"],
        },
        {
            "id": "approval_and_asset_governance",
            "title": "Approval and Asset governance",
            "expected_state": "approval",
            "detail": "Runtime execution remains approval-bound, evidence-bound, and review-bound before durable Asset/Memory promotion.",
            "command": "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-approval-assets.json",
            "required_evidence": [
                "approval_id",
                "approved_run",
                "summary_report",
                "asset_reviews",
                "approved_memory",
            ],
            "ui_surfaces": ["Chat", "Assets", "Runtime Replay", "System Status"],
        },
        {
            "id": "provider_blocker_visibility",
            "title": "Provider blocker visibility",
            "expected_state": "blocked",
            "detail": "Provider failure must surface as a governed blocker instead of being hidden by answer-only summaries, repo-write adapters, or direct LLM fallback.",
            "command": "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
            "required_evidence": [
                "blocker_reasons",
                "blocker_scopes",
                "ticket_backend_status",
                "memory_backend_status",
                "provider_smoke_status",
            ],
            "ui_surfaces": ["Chat", "Tickets", "System Status"],
        },
        {
            "id": "plane_ticket_action_preflight",
            "title": "Plane Ticket action-smoke preflight",
            "expected_state": "preflight",
            "detail": "Gated Ticket provider action smoke verifies the Plane handoff/report write path is explicit and mutation-gated before full live dogfood.",
            "command": "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
            "required_evidence": [
                "ticket_backend_status",
                "plane_action_smoke_guard",
                "confirm_env_var",
            ],
            "ui_surfaces": ["Tickets", "System Status"],
        },
        {
            "id": "retry_resume_closeout",
            "title": "Retry, resume, and closeout settlement",
            "expected_state": "retry",
            "detail": "Deterministic queue-worker soak preserves retry causes, Ticket refs, queue reliability, failure-retrospective Asset candidates, and daemon settlement while live provider closeout remains covered by the live dogfood artifacts.",
            "command": "python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
            "required_evidence": [
                "retry_cause",
                "ticket_report",
                "queue_reliability",
                "failure_retrospective_candidate",
                "daemon_resume_settlement",
            ],
            "ui_surfaces": ["Chat", "Tickets", "Runtime Replay", "System Status"],
        },
    ]
    scenario_status = "ready" if not blockers else "blocked"
    return [
        LiveProviderSoakScenario(
            status=scenario_status,
            blockers=blockers,
            **spec,
        )
        for spec in scenario_specs
    ]


def _readiness_blockers(readiness: LiveProviderDogfoodReadinessResponse) -> list[str]:
    blockers = [
        str(item.get("reason") or item.get("id") or "").strip()
        for item in readiness.blockers
        if isinstance(item, dict)
    ]
    return _unique(blockers)


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique([str(item or "").strip() for item in value if str(item or "").strip()])


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _commands() -> list[str]:
    return [
        "python scripts/live_provider_soak_plan.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-plan.json",
        "python scripts/live_provider_readiness_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-readiness-smoke.json",
        "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
        "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
        "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --require-natural-handoff --expected-handoff-target alex --output .aiteamos/artifacts/plan_v8/track-c-live-soak-handoff.json",
        "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-approval-assets.json",
        "python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
    ]


def _evidence_refs(artifacts: PlanV8ArtifactSummary) -> list[str]:
    refs = [
        artifacts.latest_agent_server_smoke.name if artifacts.latest_agent_server_smoke else "",
        artifacts.latest_live_provider_readiness.name if artifacts.latest_live_provider_readiness else "",
        artifacts.latest_live_provider_soak_evidence.name if artifacts.latest_live_provider_soak_evidence else "",
        artifacts.latest_plane_ticket_action_smoke.name if artifacts.latest_plane_ticket_action_smoke else "",
        artifacts.latest_context_retrieval_eval.name if artifacts.latest_context_retrieval_eval else "",
        artifacts.latest_asset_provenance_eval.name if artifacts.latest_asset_provenance_eval else "",
    ]
    return _unique(refs)


def _detail(status: str, blockers: list[str]) -> str:
    if status == "ready":
        return "Live provider soak plan is ready to execute once the operator runs the explicit live commands."
    if "live_provider_dogfood_not_confirmed" in blockers:
        return "Live provider soak plan is prepared, but live writes are blocked until the mutation gate is explicitly opened."
    return f"Live provider soak plan is blocked by {len(blockers)} readiness signal(s)."


def _workspace_root(workspace_dir: Path | None) -> Path:
    raw = workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).expanduser()
    root = raw.resolve()
    return root.parent if root.name == ".aiteamos" else root


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
