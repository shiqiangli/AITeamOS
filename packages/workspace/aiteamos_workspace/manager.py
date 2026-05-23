from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiteamos_schema import ManagerInputBundle

from .collaboration import retrospective_suggestions
from .connector_operations import connector_failure_escalation_candidates, connector_remediation_suggestions
from .loader import WorkspaceIndex, load_workspace
from .manager_eval import manager_evaluation_signal
from .member_growth import member_growth_projection
from .health import workspace_health_v2
from .review_gate import evaluate_run_review_gate


def manager_input_bundle(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    manager: str = "aiteamos-manager",
    project: str | None = None,
    assignment: str | None = None,
    retrospective_limit: int = 5,
    connector_min_evidence: int = 2,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    selected_project, selected_assignment, assignment_member = _resolve_scope(index, project=project, assignment=assignment)
    if manager not in index.members:
        raise KeyError(f"unknown manager member {manager}")

    health = workspace_health_v2(index).model_dump(mode="json")
    review_gates = _review_gates(index, project=selected_project, assignment=selected_assignment)
    escalation_set = connector_failure_escalation_candidates(
        index,
        project=selected_project,
        assignment=selected_assignment,
        min_evidence=connector_min_evidence,
    )
    remediation_set = connector_remediation_suggestions(
        index,
        project=selected_project,
        assignment=selected_assignment,
        min_evidence=connector_min_evidence,
    )
    retrospective_records = _retrospective_records(
        index,
        project=selected_project,
        assignment_member=assignment_member,
        limit=retrospective_limit,
    )
    growth_signals = member_growth_projection(
        index,
        project=selected_project,
        assignment=selected_assignment,
    )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "manager": manager,
        "project": selected_project,
        "assignment": selected_assignment,
        "filters": {
            "manager": manager,
            "project": selected_project,
            "assignment": selected_assignment,
            "retrospectiveLimit": retrospective_limit,
            "connectorMinEvidence": connector_min_evidence,
        },
        "workspaceHealth": health,
        "reviewGates": review_gates,
        "connectorEscalationCandidates": escalation_set["candidates"],
        "connectorEscalationSummary": escalation_set["summary"],
        "connectorRemediationSuggestions": remediation_set["suggestions"],
        "connectorRemediationSummary": remediation_set["summary"],
        "retrospectiveSuggestions": retrospective_records,
        "memberGrowthSupportSignals": growth_signals,
        "managerEvaluation": manager_evaluation_signal(
            index,
            manager=manager,
            project=selected_project,
            assignment=selected_assignment,
            limit=retrospective_limit,
        ),
        "readOnly": True,
        "sourceRefs": _source_refs(
            index,
            manager=manager,
            assignment=selected_assignment,
        ),
    }
    return ManagerInputBundle.model_validate(payload).model_dump(mode="json")


def _resolve_scope(index: WorkspaceIndex, *, project: str | None, assignment: str | None) -> tuple[str, str | None, str | None]:
    selected_project = project or index.project.object_id
    if selected_project != index.project.object_id:
        raise KeyError(f"unknown project {selected_project}")
    if not assignment:
        return selected_project, None, None
    if assignment not in index.assignments:
        raise KeyError(f"unknown assignment {assignment}")
    assignment_record = index.assignments[assignment]
    if assignment_record.spec.project != selected_project:
        raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {selected_project}")
    return selected_project, assignment, assignment_record.spec.member


def _review_gates(index: WorkspaceIndex, *, project: str, assignment: str | None) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for run_id, run in sorted(index.runs.items()):
        if run.spec.project != project:
            continue
        if assignment and run.spec.assignment != assignment:
            continue
        try:
            gates.append(evaluate_run_review_gate(index, run_id))
        except (OSError, RuntimeError, ValueError) as exc:
            gates.append(
                {
                    "run": run_id,
                    "project": run.spec.project,
                    "task": run.spec.task,
                    "member": run.spec.member,
                    "assignment": run.spec.assignment,
                    "memberKind": run.spec.memberKind,
                    "readyForHumanReview": False,
                    "status": "BLOCKED",
                    "summary": "Run review gate could not be evaluated.",
                    "blockers": ["Run review gate evaluation failed."],
                    "warnings": [],
                    "checks": [{"name": "review-gate-evaluation", "status": "fail", "message": exc.__class__.__name__}],
                }
            )
    return gates


def _retrospective_records(
    index: WorkspaceIndex,
    *,
    project: str,
    assignment_member: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    records = [retrospective_suggestions(index, project=project, limit=limit)]
    if assignment_member:
        scoped = retrospective_suggestions(index, member=assignment_member, project=project, limit=limit)
        if scoped["filters"] != records[0]["filters"]:
            records.append(scoped)
    return records


def _source_refs(
    index: WorkspaceIndex,
    *,
    manager: str,
    assignment: str | None,
) -> list[str]:
    refs = [".aiteamos/workspace.yaml", ".aiteamos/project.yaml", f".aiteamos/members/{manager}.yaml"]
    if assignment:
        refs.append(f".aiteamos/assignments/{assignment}.yaml")
    return sorted(dict.fromkeys(refs))
