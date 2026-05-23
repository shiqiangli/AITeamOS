from __future__ import annotations

from pathlib import Path
from typing import Any

from .loader import WorkspaceIndex, load_workspace


ACCEPTED_OUTCOMES = {"accept", "accepted", "approve", "approved", "merged", "materialized"}
REJECTED_OUTCOMES = {"reject", "rejected", "decline", "declined", "superseded", "abandoned"}


def manager_evaluation_signal(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    manager: str = "aiteamos-manager",
    project: str | None = None,
    assignment: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    selected_project = project or index.project.object_id
    if selected_project != index.project.object_id:
        raise KeyError(f"unknown project {selected_project}")
    if manager not in index.members:
        raise KeyError(f"unknown manager member {manager}")
    selected_assignment = assignment or _manager_assignment(index, manager)
    if selected_assignment and selected_assignment not in index.assignments:
        raise KeyError(f"unknown manager assignment {selected_assignment}")

    recommendation_pairs = _recommendation_pairs(
        index,
        manager=manager,
        project=selected_project,
        limit=max(1, int(limit or 5)),
    )
    evaluation_suites = _evaluation_suites(index, manager=manager, project=selected_project, assignment=selected_assignment)
    latest_status = next((suite for suite in evaluation_suites if suite.get("lastResultId")), None)
    selected_profile, profile_source = _model_profile_selection(index, manager=manager, assignment=selected_assignment)
    outcome_counts = _outcome_counts(recommendation_pairs)
    resolved = outcome_counts["accepted"] + outcome_counts["rejected"]
    acceptance_rate = round(outcome_counts["accepted"] / resolved, 4) if resolved else None

    source_refs = _source_refs(
        recommendation_pairs,
        evaluation_suites,
        manager=manager,
        assignment=selected_assignment,
        selected_profile=selected_profile,
    )
    return {
        "manager": manager,
        "project": selected_project,
        "assignment": selected_assignment,
        "readOnly": True,
        "recommendationWindow": {
            "limit": max(1, int(limit or 5)),
            "total": len(recommendation_pairs),
            "accepted": outcome_counts["accepted"],
            "rejected": outcome_counts["rejected"],
            "pending": outcome_counts["pending"],
            "acceptanceRate": acceptance_rate,
        },
        "recommendationPairs": recommendation_pairs,
        "evalSuites": evaluation_suites,
        "modelProfileSelection": {
            "modelProfile": selected_profile,
            "source": profile_source,
            "basis": "manager-eval-suite" if latest_status else profile_source,
            "evalSuite": latest_status.get("evalSuite") if latest_status else None,
            "lastResultId": latest_status.get("lastResultId") if latest_status else None,
            "passRate": latest_status.get("passRate") if latest_status else None,
            "status": latest_status.get("status") if latest_status else "missing-eval-result",
            "message": "Manager model profile selection has EvalSuite outcome evidence."
            if latest_status
            else "Manager model profile selection falls back to execution profile defaults until an EvalResult exists.",
        },
        "sourceRefs": sorted(dict.fromkeys(source_refs)),
    }


def _manager_assignment(index: WorkspaceIndex, manager: str) -> str | None:
    for assignment_id, assignment in sorted(index.assignments.items()):
        if assignment.spec.member == manager:
            return assignment_id
    return None


def _model_profile_selection(index: WorkspaceIndex, *, manager: str, assignment: str | None) -> tuple[str | None, str]:
    profile = index.digital_execution_profiles.get(manager)
    if profile and profile.spec.defaultModelProfile:
        return profile.spec.defaultModelProfile, "digital-execution-profile"
    for profile_id, model_profile in sorted(index.model_profiles.items()):
        if assignment and assignment in model_profile.spec.defaultForAssignments:
            return profile_id, "assignment-default"
        if manager in model_profile.spec.defaultForMembers:
            return profile_id, "member-default"
    return None, "unresolved"


def _recommendation_pairs(index: WorkspaceIndex, *, manager: str, project: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for message_id, message in sorted(index.member_messages.items(), reverse=True):
        if message.spec.fromMember != manager or message.spec.messageType != "plan-recommendation":
            continue
        if message.spec.project and message.spec.project != project:
            continue
        plan_refs = _attached_task_plans(index, message.spec.attachments)
        rows.append(
            {
                "message": message_id,
                "taskPlans": [plan.object_id for plan in plan_refs],
                "outcome": _message_outcome(message.spec.status, message.spec.resolution, message.spec.audit),
                "status": message.spec.status,
                "resolvedByMember": message.spec.resolvedByMember,
                "resolvedAt": message.spec.resolvedAt,
                "resolution": message.spec.resolution,
                "modelProfile": message.spec.audit.get("modelProfile"),
                "evidence": [f".aiteamos/im/messages/{message_id}.yaml", *[f".aiteamos/task_plans/{plan.object_id}.yaml" for plan in plan_refs]],
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _attached_task_plans(index: WorkspaceIndex, attachments: list[str]) -> list[Any]:
    plans: list[Any] = []
    for attachment in attachments:
        ref = str(attachment)
        if ":" in ref:
            prefix, value = ref.split(":", 1)
            if prefix.lower() in {"taskplan", "task_plan"}:
                ref = value
        if ref in index.task_plans:
            plans.append(index.task_plans[ref])
    return plans


def _message_outcome(status: str, resolution: str | None, audit: dict[str, Any]) -> str:
    for key in ("humanOutcome", "outcome", "finalOutcome"):
        outcome = str(audit.get(key) or "").strip().lower()
        if outcome in ACCEPTED_OUTCOMES:
            return "accepted"
        if outcome in REJECTED_OUTCOMES:
            return "rejected"
    resolution_text = str(resolution or "").strip().lower()
    if any(token in resolution_text for token in ACCEPTED_OUTCOMES):
        return "accepted"
    if any(token in resolution_text for token in REJECTED_OUTCOMES):
        return "rejected"
    return "pending" if status != "resolved" else "unclassified"


def _outcome_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"accepted": 0, "rejected": 0, "pending": 0}
    for row in rows:
        outcome = str(row.get("outcome") or "pending")
        if outcome in ("accepted", "rejected"):
            counts[outcome] += 1
        else:
            counts["pending"] += 1
    return counts


def _evaluation_suites(index: WorkspaceIndex, *, manager: str, project: str, assignment: str | None) -> list[dict[str, Any]]:
    suites = [
        suite
        for suite in index.eval_suites.values()
        if suite.spec.project == project
        and (manager in suite.spec.members or (assignment is not None and assignment in suite.spec.assignments))
        and "manager" in " ".join([suite.object_id, suite.spec.purpose or "", *suite.spec.metrics]).lower()
    ]
    rows: list[dict[str, Any]] = []
    for suite in sorted(suites, key=lambda item: item.object_id):
        result_id, result = _latest_eval_result(index, suite.object_id)
        rows.append(
            {
                "evalSuite": suite.object_id,
                "purpose": suite.spec.purpose,
                "metrics": suite.spec.metrics,
                "threshold": suite.spec.policy.autoPromoteThreshold,
                "lastResultId": result_id,
                "status": result.spec.status if result is not None else "missing",
                "passRate": result.spec.passRate if result is not None else None,
                "evaluatedAt": result.spec.evaluatedAt if result is not None else None,
            }
        )
    return sorted(rows, key=lambda row: str(row.get("evaluatedAt") or ""), reverse=True)


def _latest_eval_result(index: WorkspaceIndex, suite_id: str) -> tuple[str | None, Any | None]:
    candidates = [
        (result_id, result)
        for result_id, result in index.eval_results.items()
        if result.spec.evalSuite == suite_id
    ]
    if not candidates:
        return None, None
    return sorted(candidates, key=lambda item: (item[1].spec.evaluatedAt or item[1].metadata.createdAt or "", item[0]))[-1]


def _source_refs(
    recommendation_pairs: list[dict[str, Any]],
    evaluation_suites: list[dict[str, Any]],
    *,
    manager: str,
    assignment: str | None,
    selected_profile: str | None,
) -> list[str]:
    refs = [f".aiteamos/members/{manager}.yaml"]
    if assignment:
        refs.append(f".aiteamos/assignments/{assignment}.yaml")
    if selected_profile:
        refs.append(f".aiteamos/model_profiles/{selected_profile}.yaml")
    for row in recommendation_pairs:
        refs.extend(str(ref) for ref in row.get("evidence", []))
    for suite in evaluation_suites:
        suite_id = str(suite.get("evalSuite") or "")
        result_id = suite.get("lastResultId")
        if suite_id:
            refs.append(f".aiteamos/eval_suites/{suite_id}.yaml")
        if result_id:
            refs.append(f".aiteamos/eval_results/{result_id}.yaml")
    return refs
