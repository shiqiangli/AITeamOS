from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .audit import decision_audit_record
from .loader import WorkspaceIndex, load_workspace
from .mutations import update_run, update_task
from .permissions import edit_action, explain_effective_permissions
from .review_gate import APPROVAL_VERDICTS, CHANGE_REQUEST_VERDICTS, evaluate_run_review_gate
from .run_events import append_run_event_record
from .worker_state import ACTIVE_WORKER_STATUSES


def evaluate_run_closeout_gate(
    workspace_or_index: str | Path | WorkspaceIndex,
    run_id: str,
    *,
    actor_member: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")

    run = index.runs[run_id]
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    permission_decisions: list[dict[str, Any]] = []

    if run.spec.status in {"DONE", "FINISHED"}:
        checks.append({"name": "run-status", "status": "pass", "message": f"Run is already {run.spec.status}."})
        return {
            "run": run_id,
            "readyForCloseout": False,
            "status": "CLOSED",
            "summary": f"Run is already {run.spec.status}.",
            "latestReview": _latest_review_id(index, run_id),
            "blockers": [],
            "warnings": warnings,
            "checks": checks,
            "permissionDecisions": permission_decisions,
        }

    if run.spec.status != "REVIEW":
        message = f"Run status must be REVIEW before closeout; current status is {run.spec.status}."
        blockers.append(message)
        checks.append({"name": "run-status", "status": "fail", "message": message})
    else:
        checks.append({"name": "run-status", "status": "pass", "message": "Run is in REVIEW."})

    review_gate = evaluate_run_review_gate(index, run_id)
    if review_gate["blockers"]:
        message = "Review gate still has blockers: " + "; ".join(review_gate["blockers"][:3])
        blockers.append(message)
        checks.append({"name": "review-gate", "status": "fail", "message": message})
    else:
        checks.append({"name": "review-gate", "status": "pass", "message": "Review gate has no blockers."})
        warnings.extend([f"Review gate warning: {warning}" for warning in review_gate["warnings"]])

    latest_review = _latest_review_id(index, run_id)
    if not latest_review:
        message = "No human review is linked to this run."
        blockers.append(message)
        checks.append({"name": "human-approval", "status": "fail", "message": message})
    else:
        review = index.reviews[latest_review]
        verdict = review.spec.verdict.strip().lower()
        if verdict in APPROVAL_VERDICTS and _review_is_human(index, review):
            checks.append({"name": "human-approval", "status": "pass", "message": f"Latest human review {latest_review} is {review.spec.verdict}."})
        elif verdict in CHANGE_REQUEST_VERDICTS:
            message = f"Latest human review {latest_review} requested changes."
            blockers.append(message)
            checks.append({"name": "human-approval", "status": "fail", "message": message})
        elif verdict in APPROVAL_VERDICTS:
            message = f"Latest approval {latest_review} is not from a human reviewer."
            blockers.append(message)
            checks.append({"name": "human-approval", "status": "fail", "message": message})
        else:
            message = f"Latest human review {latest_review} is not an approval: {review.spec.verdict}."
            blockers.append(message)
            checks.append({"name": "human-approval", "status": "fail", "message": message})

    active_sibling_runs = [
        sibling_id
        for sibling_id, sibling in index.runs.items()
        if sibling_id != run_id and sibling.spec.task == run.spec.task and sibling.spec.status in ACTIVE_WORKER_STATUSES
    ]
    if active_sibling_runs:
        message = "Task has active sibling run(s): " + ", ".join(sorted(active_sibling_runs))
        blockers.append(message)
        checks.append({"name": "task-sibling-runs", "status": "fail", "message": message})
    else:
        checks.append({"name": "task-sibling-runs", "status": "pass", "message": "No active sibling runs are attached to the task."})

    pending_proposals = [
        proposal_id
        for proposal_id in run.spec.memoryProposals
        if proposal_id in index.memory_proposals and index.memory_proposals[proposal_id].spec.status == "pending-review"
    ]
    if pending_proposals:
        warnings.append("Run has pending memory proposal(s): " + ", ".join(pending_proposals))
        checks.append({"name": "memory-proposals", "status": "warn", "message": "Pending memory proposals remain for later review."})
    else:
        checks.append({"name": "memory-proposals", "status": "pass", "message": "No pending memory proposals are linked to this run."})

    permission_checks, permission_blockers, permission_warnings, permission_decisions = _closeout_permission_checks(
        index,
        run_id,
        actor_member=actor_member,
    )
    checks.extend(permission_checks)
    blockers.extend(permission_blockers)
    warnings.extend(permission_warnings)

    ready = not blockers
    return {
        "run": run_id,
        "readyForCloseout": ready,
        "status": "READY_FOR_CLOSEOUT" if ready else "BLOCKED",
        "summary": "Run can be closed and task marked DONE." if ready else f"Run closeout has {len(blockers)} blocker(s).",
        "latestReview": latest_review,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "permissionDecisions": permission_decisions,
    }


def close_run_after_review(workspace_path: str | Path, run_id: str, *, actor: str = "human", reason: str | None = None) -> dict[str, Any]:
    gate = evaluate_run_closeout_gate(workspace_path, run_id, actor_member=actor)
    if gate["blockers"] or not gate["readyForCloseout"]:
        raise ValueError("run is not ready for closeout: " + "; ".join(gate["blockers"] or [gate["summary"]]))

    index = load_workspace(workspace_path)
    run = index.runs[run_id]
    actor_kind = index.members[actor].spec.kind if actor in index.members else None
    reason_text = reason or "manual dashboard closeout after approved review"
    audit = decision_audit_record(
        index,
        decision_kind=_closeout_decision_kind(actor_kind),
        decision="approved",
        actor_member=actor,
        authority=_closeout_authority(actor_kind),
        reason=reason_text,
        source="run-closeout",
        policy_refs=_policy_refs(gate["permissionDecisions"]),
        evidence=[
            {"kind": "run", "run": run_id},
            {"kind": "task", "task": run.spec.task},
            {"kind": "review", "review": gate["latestReview"]},
        ],
        metadata={"gateStatus": gate["status"]},
    )
    closed_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
    closeout_record = {
        "status": "closed",
        "closedAt": closed_at,
        "closedByMember": actor,
        "closedByMemberKind": actor_kind,
        "latestReview": gate["latestReview"],
        "reason": reason_text,
        "gate": {
            "status": gate["status"],
            "summary": gate["summary"],
            "warnings": gate["warnings"],
            "checks": gate["checks"],
        },
        "permissionDecisions": gate["permissionDecisions"],
        "decisionAudit": [audit],
    }
    update_run(workspace_path, run_id, {"status": "DONE", "closeout": closeout_record})
    update_task(workspace_path, run.spec.task, {"status": "DONE"})
    _append_event(
        index.workspace_root,
        run_id,
        {
            "type": "run.closed",
            "actorMember": actor,
            "actorMemberKind": actor_kind,
            "reason": reason_text,
            "latestReview": gate["latestReview"],
            "task": run.spec.task,
            "decisionAudit": audit,
        },
    )
    return load_workspace(workspace_path).runs[run_id].model_dump(mode="json")


def _latest_review_id(index: WorkspaceIndex, run_id: str) -> str | None:
    run = index.runs[run_id]
    review_ids = [_normalize_review_ref(ref) for ref in run.spec.reviews]
    review_ids = [review_id for review_id in review_ids if review_id in index.reviews]
    for review_id, review in index.reviews.items():
        if review.spec.run == run_id and review_id not in review_ids:
            review_ids.append(review_id)
    return sorted(review_ids)[-1] if review_ids else None


def _normalize_review_ref(ref: str) -> str:
    value = str(ref).strip()
    if value.endswith(".yaml"):
        return Path(value).stem
    return value


def _review_is_human(index: WorkspaceIndex, review: Any) -> bool:
    reviewer_kind = getattr(review.spec, "reviewerKind", None)
    if reviewer_kind == "human":
        return True
    reviewer_member = getattr(review.spec, "reviewerMember", None)
    return bool(reviewer_member and reviewer_member in index.members and index.members[reviewer_member].spec.kind == "human")


def _closeout_permission_checks(
    index: WorkspaceIndex,
    run_id: str,
    *,
    actor_member: str | None,
) -> tuple[list[dict[str, str]], list[str], list[str], list[dict[str, Any]]]:
    run = index.runs[run_id]
    if not actor_member:
        return (
            [
                {
                    "name": "closeout-actor",
                    "status": "warn",
                    "message": "Closeout actor was not supplied; write permission is checked when the action is submitted.",
                }
            ],
            [],
            [],
            [],
        )
    if actor_member not in index.members:
        message = f"unknown closeout actor member {actor_member}"
        return ([{"name": "closeout-actor", "status": "fail", "message": message}], [message], [], [])

    actor_kind = index.members[actor_member].spec.kind
    actor_assignment = run.spec.assignment
    assignment_record = index.assignments.get(actor_assignment) if actor_assignment else None
    if assignment_record is None or assignment_record.spec.member != actor_member:
        actor_assignment = None
    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    decisions: list[dict[str, Any]] = []
    targets = [
        ("run-manifest", f"/.aiteamos/runs/{run_id}/run.yaml"),
        ("task-manifest", f"/.aiteamos/tasks/{run.spec.task}.yaml"),
    ]
    for target_name, path in targets:
        decision = explain_effective_permissions(
            index,
            member=actor_member,
            project=run.spec.project,
            assignment=actor_assignment,
            action=edit_action(path),
            non_interactive=actor_kind in {"digital", "service"},
        )
        decisions.append({"target": target_name, "path": path, **decision})
        decision_value = decision.get("decision")
        if decision_value == "deny" or decision.get("blockers"):
            message = f"actor {actor_member} cannot close out {target_name}: {decision.get('reason')}"
            blockers.append(message)
            checks.append({"name": f"closeout-permission-{target_name}", "status": "fail", "message": message})
        elif decision_value == "ask":
            message = f"actor {actor_member} permission for {target_name} is ask; explicit closeout submission is the approval boundary."
            warnings.append(message)
            checks.append({"name": f"closeout-permission-{target_name}", "status": "warn", "message": message})
        else:
            checks.append({"name": f"closeout-permission-{target_name}", "status": "pass", "message": f"actor {actor_member} may edit {target_name}."})
    return checks, blockers, warnings, decisions


def _closeout_decision_kind(actor_kind: str | None) -> str:
    if actor_kind == "service":
        return "service_policy_decision"
    if actor_kind == "digital":
        return "digital_recommendation"
    return "human_approval"


def _closeout_authority(actor_kind: str | None) -> str:
    if actor_kind == "service":
        return "enforce"
    if actor_kind == "digital":
        return "recommend"
    return "approve"


def _policy_refs(permission_decisions: list[dict[str, Any]]) -> list[str]:
    refs: set[str] = set()
    for decision in permission_decisions:
        for policy_id in decision.get("selectedPolicyIds") or []:
            refs.add(str(policy_id))
    return sorted(refs)


def _append_event(workspace_root: Path, run_id: str, event: dict[str, Any]) -> None:
    append_run_event_record(workspace_root, run_id, event)
