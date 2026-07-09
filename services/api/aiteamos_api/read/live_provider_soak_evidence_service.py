"""Read-only repeated live-provider soak evidence for Plan v8 Track C."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .live_provider_soak_plan_service import LiveProviderSoakPlanResponse, live_provider_soak_plan_report


LIVE_PROVIDER_SOAK_EVIDENCE_CONTRACT_VERSION = "aiteamos_live_provider_soak_evidence.v1"


class LiveProviderSoakEvidenceScenario(BaseModel):
    id: str
    title: str
    expected_state: str
    status: str
    detail: str
    command: str = ""
    execution_kind: str = ""
    operator_action: str = ""
    artifact_name: str
    artifact_path: str = ""
    artifact_schema: str = ""
    artifact_status: str = ""
    generated_at: str = ""
    required_evidence: list[str] = Field(default_factory=list)
    observed_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    ui_surfaces: list[str] = Field(default_factory=list)


class LiveProviderSoakEvidenceSummary(BaseModel):
    scenario_count: int = 0
    passed_scenario_count: int = 0
    blocked_scenario_count: int = 0
    failed_scenario_count: int = 0
    missing_scenario_count: int = 0
    warning_scenario_count: int = 0
    latest_generated_at: str = ""
    mutation_gate_open: bool = False
    ready_to_execute: bool = False
    ready_for_release: bool = False
    live_write_scenario_count: int = 0
    remaining_live_write_scenario_count: int = 0
    passed_non_mutating_scenario_count: int = 0
    operator_action_required: bool = False
    operator_action: str = ""
    mutation_gate_env_var: str = "AITEAMOS_LIVE_PROVIDER_DOGFOOD"
    live_write_targets: list[str] = Field(default_factory=list)
    contract_version: str = LIVE_PROVIDER_SOAK_EVIDENCE_CONTRACT_VERSION


class LiveProviderSoakEvidenceResponse(BaseModel):
    contract_version: str = LIVE_PROVIDER_SOAK_EVIDENCE_CONTRACT_VERSION
    status: str
    detail: str
    summary: LiveProviderSoakEvidenceSummary = Field(default_factory=LiveProviderSoakEvidenceSummary)
    blockers: list[str] = Field(default_factory=list)
    scenarios: list[LiveProviderSoakEvidenceScenario] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


SCENARIO_ARTIFACTS = {
    "core_loop_completed_closeout_asset": "track-c-live-soak-completed.json",
    "natural_handoff": "track-c-live-soak-handoff.json",
    "approval_and_asset_governance": "track-c-live-soak-approval-assets.json",
    "provider_blocker_visibility": "track-c-live-provider-readiness-smoke.json",
    "plane_ticket_action_preflight": "track-c-plane-ticket-action-smoke.json",
    "retry_resume_closeout": "track-c-ticket-loop-worker-soak.json",
}


async def live_provider_soak_evidence_report(
    *,
    workspace_dir: Path | None = None,
    plan: LiveProviderSoakPlanResponse | None = None,
) -> LiveProviderSoakEvidenceResponse:
    root = _workspace_root(workspace_dir)
    plan = plan or await live_provider_soak_plan_report(workspace_dir=root)
    artifact_dir = root / ".aiteamos" / "artifacts" / "plan_v8"
    scenarios = [
        _scenario_evidence(
            artifact_dir=artifact_dir,
            scenario_id=scenario.id,
            title=scenario.title,
            expected_state=scenario.expected_state,
            command=scenario.command,
            required_evidence=scenario.required_evidence,
            plan_blockers=scenario.blockers or plan.blockers,
            ui_surfaces=scenario.ui_surfaces,
        )
        for scenario in plan.scenarios
    ]
    status = _overall_status(scenarios, plan.blockers)
    latest_generated_at = _latest_generated_at(scenarios)
    blockers = _unique(
        [blocker for scenario in scenarios if scenario.status != "passed" for blocker in scenario.blockers]
        + list(plan.blockers)
    )
    live_write_scenarios = [item for item in scenarios if item.execution_kind == "live_provider_write"]
    remaining_live_write_scenarios = [item for item in live_write_scenarios if item.status != "passed"]
    summary = LiveProviderSoakEvidenceSummary(
        scenario_count=len(scenarios),
        passed_scenario_count=sum(1 for item in scenarios if item.status == "passed"),
        blocked_scenario_count=sum(1 for item in scenarios if item.status == "blocked"),
        failed_scenario_count=sum(1 for item in scenarios if item.status == "failed"),
        missing_scenario_count=sum(1 for item in scenarios if item.status == "missing"),
        warning_scenario_count=sum(1 for item in scenarios if item.status == "warning"),
        latest_generated_at=latest_generated_at,
        mutation_gate_open=plan.summary.mutation_gate_open,
        ready_to_execute=plan.summary.ready_to_execute,
        ready_for_release=status == "passed",
        live_write_scenario_count=len(live_write_scenarios),
        remaining_live_write_scenario_count=len(remaining_live_write_scenarios),
        passed_non_mutating_scenario_count=sum(
            1 for item in scenarios if item.execution_kind != "live_provider_write" and item.status == "passed"
        ),
        operator_action_required=bool(remaining_live_write_scenarios) and not plan.summary.mutation_gate_open,
        operator_action=_summary_operator_action(
            remaining_live_write_scenarios=remaining_live_write_scenarios,
            mutation_gate_open=plan.summary.mutation_gate_open,
        ),
        live_write_targets=[
            "Plane Ticket reports / comments",
            "LangGraph Agent Server thread / run state",
            "Runtime approval records",
            "Asset reviews and approved records",
            "Graphiti projection / recall",
        ],
    )
    return LiveProviderSoakEvidenceResponse(
        status=status,
        detail=_detail(status=status, blockers=blockers, summary=summary),
        summary=summary,
        blockers=blockers,
        scenarios=scenarios,
        commands=_commands(),
        evidence_refs=[item.artifact_name for item in scenarios if item.artifact_path],
    )


def _scenario_evidence(
    *,
    artifact_dir: Path,
    scenario_id: str,
    title: str,
    expected_state: str,
    command: str,
    required_evidence: list[str],
    plan_blockers: list[str],
    ui_surfaces: list[str],
) -> LiveProviderSoakEvidenceScenario:
    artifact_name = SCENARIO_ARTIFACTS.get(scenario_id, f"{scenario_id}.json")
    artifact_path = artifact_dir / artifact_name
    execution_kind = _execution_kind(command)
    if not artifact_path.exists():
        gate_blockers = _unique(plan_blockers)
        status = "blocked" if gate_blockers else "missing"
        return LiveProviderSoakEvidenceScenario(
            id=scenario_id,
            title=title,
            expected_state=expected_state,
            status=status,
            detail=(
                "Execution evidence is waiting on the live mutation gate."
                if gate_blockers
                else "Expected live soak artifact is missing."
            ),
            command=command,
            execution_kind=execution_kind,
            operator_action=_operator_action(status=status, execution_kind=execution_kind),
            artifact_name=artifact_name,
            required_evidence=required_evidence,
            missing_evidence=required_evidence,
            blockers=gate_blockers,
            ui_surfaces=ui_surfaces,
        )

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return LiveProviderSoakEvidenceScenario(
            id=scenario_id,
            title=title,
            expected_state=expected_state,
            status="failed",
            detail=f"Soak artifact could not be parsed: {exc}",
            command=command,
            execution_kind=execution_kind,
            operator_action=_operator_action(status="failed", execution_kind=execution_kind),
            artifact_name=artifact_name,
            artifact_path=str(artifact_path),
            required_evidence=required_evidence,
            missing_evidence=required_evidence,
            blockers=["live_soak_artifact_unreadable"],
            ui_surfaces=ui_surfaces,
        )

    observed = [item for item in required_evidence if _has_evidence(payload, item)]
    missing = [item for item in required_evidence if item not in observed]
    artifact_status = _artifact_status(payload)
    blockers = _artifact_blockers(payload)
    status = _scenario_status(expected_state=expected_state, artifact_status=artifact_status, missing=missing, blockers=blockers)
    return LiveProviderSoakEvidenceScenario(
        id=scenario_id,
        title=title,
        expected_state=expected_state,
        status=status,
        detail=_scenario_detail(status=status, artifact_status=artifact_status, missing=missing, blockers=blockers),
        command=command,
        execution_kind=execution_kind,
        operator_action=_operator_action(status=status, execution_kind=execution_kind),
        artifact_name=artifact_name,
        artifact_path=str(artifact_path),
        artifact_schema=str(payload.get("schema") or ""),
        artifact_status=artifact_status,
        generated_at=_generated_at(artifact_path, payload),
        required_evidence=required_evidence,
        observed_evidence=observed,
        missing_evidence=missing,
        blockers=blockers,
        ui_surfaces=ui_surfaces,
    )


def _has_evidence(payload: dict[str, Any], evidence_id: str) -> bool:
    result = _record(payload.get("result"))
    summary = _record(payload.get("summary")) or _record(result.get("summary"))
    agent_server = _record(payload.get("agent_server"))
    runtime = _record(result.get("runtime_dogfood"))
    workbench = _record(result.get("workbench"))
    recall = _record(result.get("recall"))
    artifact_evidence = _record(result.get("evidence")) or _record(payload.get("evidence"))
    provider_prerequisites = _record(result.get("provider_prerequisites"))
    checks = _records(payload.get("checks"))
    policy_actions = _records(summary.get("policy_actions"))
    after_reliability = _record(summary.get("after_reliability"))
    daemon = _record(payload.get("daemon"))
    mapping = {
        "fresh_agent_server": lambda: bool(agent_server.get("url")) and str(agent_server.get("status") or "") in {"ready", "passed"},
        "ticket_report": lambda: bool(summary.get("ticket_id") or _record(result.get("ticket")).get("id")),
        "memory_candidate_ids": lambda: bool(_strings(summary.get("memory_candidate_ids")) or _strings(_record(runtime.get("learning_delta")).get("memory_candidate_ids"))),
        "asset_record_ids": lambda: bool(_strings(summary.get("asset_record_ids"))),
        "graphiti_projection_statuses": lambda: bool(_strings(summary.get("graphiti_projection_statuses")) or _records(result.get("graphiti_projections"))),
        "graphiti_recall_count": lambda: _safe_int(summary.get("graphiti_recall_count")) > 0 or bool(_records(recall.get("results"))),
        "handoff_summary": lambda: bool(_record(workbench.get("handoff_summary"))),
        "ticket_handoff_refs": lambda: bool(_records(workbench.get("ticket_handoff_refs"))),
        "natural_handoff": lambda: bool(_record(workbench.get("handoff_decision")) or _record(workbench.get("handoff_summary"))),
        "handoff_target_employee_id": lambda: bool(_record(workbench.get("handoff_decision")).get("target_employee_id") or _record(workbench.get("handoff_summary")).get("to_employee_id")),
        "approval_id": lambda: bool(summary.get("approval_id") or _record(runtime.get("approval")).get("id")),
        "approved_run": lambda: bool(_record(runtime.get("approved_run")) or summary.get("approved_run_status")),
        "summary_report": lambda: bool(_record(runtime.get("summary_report")) or summary.get("summary_report_id")),
        "asset_reviews": lambda: bool(_records(result.get("asset_reviews"))),
        "approved_memory": lambda: any(_record(item.get("approved_memory")) for item in _records(result.get("asset_reviews"))),
        "blocker_reasons": lambda: bool(_strings(summary.get("blocker_reasons")) or [item for item in _records(result.get("blockers")) if item.get("reason")]),
        "blocker_scopes": lambda: bool(_strings(summary.get("blocker_scopes")) or [item for item in _records(result.get("blockers")) if item.get("scope")]),
        "ticket_backend_status": lambda: bool(summary.get("ticket_backend_status") or _record(provider_prerequisites.get("ticket_backend")).get("status")),
        "memory_backend_status": lambda: bool(summary.get("memory_backend_status") or _record(provider_prerequisites.get("memory_backend")).get("status")),
        "provider_smoke_status": lambda: bool(summary.get("provider_smoke_status") or _record(provider_prerequisites.get("provider_smoke")).get("status")),
        "plane_action_smoke_guard": lambda: bool(
            artifact_evidence.get("confirm_env_var")
            or summary.get("mutation_gate_open") is True
            or any(
                str(item.get("reason") or "") == "plane_action_smoke_not_confirmed"
                for item in _records(result.get("blockers"))
            )
        ),
        "confirm_env_var": lambda: bool(artifact_evidence.get("confirm_env_var")),
        "retry_cause": lambda: bool(
            summary.get("retry_cause")
            or "blocked" in _strings(summary.get("processed_statuses"))
            or str(after_reliability.get("status") or "") == "error"
            or _check_passed(checks, "tick.processed_statuses")
            or [item for item in _records(result.get("blockers")) if "retry" in str(item).lower()]
        ),
        "execution_session": lambda: bool(summary.get("execution_session_id") or _record(result.get("execution_session")).get("session_key")),
        "validation_or_closeout": lambda: bool(summary.get("validation_id") or summary.get("closeout_id") or summary.get("closeout_status")),
        "runtime_replay_ref": lambda: bool(summary.get("runtime_replay_ref") or summary.get("execution_session_id")),
        "queue_reliability": lambda: bool(after_reliability.get("status") or _check_passed(checks, "after.queue_reliability")),
        "failure_retrospective_candidate": lambda: bool(
            _strings(summary.get("asset_candidate_ids"))
            or [action for action in policy_actions if action.get("kind") == "failure_retrospective_candidate"]
            or _check_passed(checks, "asset_candidate.id")
        ),
        "daemon_resume_settlement": lambda: _daemon_settled(summary=summary, daemon=daemon, checks=checks),
    }
    checker = mapping.get(evidence_id)
    return bool(checker()) if checker is not None else False


def _artifact_status(payload: dict[str, Any]) -> str:
    result = _record(payload.get("result"))
    summary = _record(payload.get("summary")) or _record(result.get("summary"))
    value = str(result.get("status") or summary.get("status") or payload.get("status") or "").strip()
    if value == "completed":
        return "passed"
    return value or "unknown"


def _artifact_blockers(payload: dict[str, Any]) -> list[str]:
    result = _record(payload.get("result"))
    summary = _record(payload.get("summary")) or _record(result.get("summary"))
    blockers = _strings(summary.get("blocker_reasons"))
    blockers.extend(
        str(item.get("reason") or item.get("id") or "").strip()
        for item in _records(result.get("blockers"))
        if str(item.get("reason") or item.get("id") or "").strip()
    )
    return _unique(blockers)


def _scenario_status(*, expected_state: str, artifact_status: str, missing: list[str], blockers: list[str]) -> str:
    if artifact_status in {"failed", "error"}:
        return "failed"
    if missing:
        return "warning"
    if expected_state == "blocked" and artifact_status == "blocked" and blockers:
        return "passed"
    if expected_state == "retry" and artifact_status in {"retry", "blocked"}:
        return "passed"
    if expected_state == "approval" and artifact_status in {"approval", "needs_approval", "passed"}:
        return "passed"
    if expected_state == "handoff" and artifact_status in {"handoff", "passed"}:
        return "passed"
    if expected_state == "preflight" and artifact_status in {"dry_run", "passed"}:
        return "passed"
    if expected_state == "completed" and artifact_status == "passed":
        return "passed"
    if artifact_status == "blocked":
        return "blocked"
    if artifact_status == "passed":
        return "passed"
    return "missing"


def _overall_status(scenarios: list[LiveProviderSoakEvidenceScenario], plan_blockers: list[str]) -> str:
    if any(item.status == "failed" for item in scenarios):
        return "failed"
    if any(item.status == "blocked" for item in scenarios):
        return "blocked"
    if any(item.status == "missing" for item in scenarios):
        return "missing"
    if any(item.status == "warning" for item in scenarios):
        return "warning"
    if scenarios and all(item.status == "passed" for item in scenarios) and not plan_blockers:
        return "passed"
    return "blocked" if plan_blockers else "missing"


def _scenario_detail(*, status: str, artifact_status: str, missing: list[str], blockers: list[str]) -> str:
    if status == "passed":
        if artifact_status == "blocked":
            return "Soak artifact satisfies the expected governed blocker evidence for this scenario."
        if artifact_status == "dry_run":
            return "Soak artifact proves the provider action path is present and mutation-gated."
        return "Soak artifact satisfies the required evidence for this scenario."
    if status == "warning":
        return f"Soak artifact exists, but {len(missing)} required evidence item(s) are missing."
    if status == "blocked":
        return f"Soak artifact reports blocked status ({', '.join(blockers) or artifact_status})."
    if status == "failed":
        return f"Soak artifact reports failed status ({artifact_status})."
    return "Soak artifact status is not sufficient for release evidence."


def _detail(*, status: str, blockers: list[str], summary: LiveProviderSoakEvidenceSummary) -> str:
    if status == "passed":
        return "All repeated live-provider soak scenarios have passing evidence."
    if blockers:
        return f"Repeated live-provider soak evidence is blocked by {len(blockers)} readiness signal(s)."
    if summary.missing_scenario_count:
        return f"Repeated live-provider soak evidence is missing {summary.missing_scenario_count} scenario artifact(s)."
    return "Repeated live-provider soak evidence is incomplete."


def _execution_kind(command: str) -> str:
    if "live_provider_dogfood.py" in command:
        return "live_provider_write"
    if "ticket_loop_queue_worker_smoke.py" in command:
        return "local_queue_worker"
    if "live_provider_readiness_smoke.py" in command:
        return "read_only_provider_blocker_smoke"
    if "plane_ticket_action_smoke.py" in command:
        return "gated_provider_action_smoke"
    return "read_only"


def _operator_action(*, status: str, execution_kind: str) -> str:
    if status == "passed":
        return "covered"
    if execution_kind == "live_provider_write":
        return "open_live_mutation_gate_and_run_command"
    if status == "failed":
        return "inspect_artifact_failure"
    return "refresh_non_mutating_evidence"


def _summary_operator_action(
    *,
    remaining_live_write_scenarios: list[LiveProviderSoakEvidenceScenario],
    mutation_gate_open: bool,
) -> str:
    if not remaining_live_write_scenarios:
        return "All live-write soak scenarios have evidence."
    if mutation_gate_open:
        return f"Run {len(remaining_live_write_scenarios)} remaining live provider soak command(s)."
    return (
        "Explicitly set AITEAMOS_LIVE_PROVIDER_DOGFOOD=1, then run the remaining "
        f"{len(remaining_live_write_scenarios)} live provider soak command(s)."
    )


def _commands() -> list[str]:
    return [
        "python scripts/live_provider_soak_evidence.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-evidence.json",
        "python scripts/live_provider_soak_plan.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-live-provider-soak-plan.json",
        "python scripts/plane_ticket_action_smoke.py --workspace-dir . --source-run-id plan-v8-plane-action-smoke --output .aiteamos/artifacts/plan_v8/track-c-plane-ticket-action-smoke.json",
        "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-completed.json",
        "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --require-natural-handoff --expected-handoff-target alex --output .aiteamos/artifacts/plan_v8/track-c-live-soak-handoff.json",
        "AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/live_provider_dogfood.py --execute --start-agent-server --profile core-loop --output .aiteamos/artifacts/plan_v8/track-c-live-soak-approval-assets.json",
        "python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir . --output .aiteamos/artifacts/plan_v8/track-c-ticket-loop-worker-soak.json",
    ]


def _latest_generated_at(scenarios: list[LiveProviderSoakEvidenceScenario]) -> str:
    values = sorted([item.generated_at for item in scenarios if item.generated_at], reverse=True)
    return values[0] if values else ""


def _generated_at(path: Path, payload: dict[str, Any]) -> str:
    value = str(payload.get("generated_at") or "").strip()
    if value:
        return value
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _workspace_root(workspace_dir: Path | None) -> Path:
    raw = workspace_dir or Path(os.environ.get("AITEAMOS_WORKSPACE_DIR", ".")).expanduser()
    root = raw.resolve()
    return root.parent if root.name == ".aiteamos" else root


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _unique([str(item or "").strip() for item in value if str(item or "").strip()])


def _check_passed(checks: list[dict[str, Any]], name: str) -> bool:
    return any(item.get("name") == name and item.get("passed") is True for item in checks)


def _daemon_settled(*, summary: dict[str, Any], daemon: dict[str, Any], checks: list[dict[str, Any]]) -> bool:
    daemon_summary = _record(summary.get("daemon")) or _record(daemon.get("summary"))
    status = str(summary.get("daemon_status") or daemon.get("status") or "").strip()
    if status == "passed" and _all_completed(daemon_summary.get("queue_statuses")) and _all_completed(daemon_summary.get("run_statuses")):
        return True
    return (
        _check_passed(checks, "daemon.queue_statuses")
        and _check_passed(checks, "daemon.run_statuses")
        and _check_passed(checks, "daemon.saved_path")
    )


def _all_completed(value: Any) -> bool:
    statuses = _strings(value)
    return bool(statuses) and all(item == "completed" for item in statuses)


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
