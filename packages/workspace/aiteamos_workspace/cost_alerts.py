from __future__ import annotations

from pathlib import Path
from typing import Any

from aiteamos_schema import BudgetPolicy, CostAlertOverviewRecord

from .costs import summarize_model_costs
from .loader import WorkspaceIndex, load_workspace, manifest_to_record
from .mutations import record_member_message


COST_METRIC_NAME = "aiteamos_model_call_cost_usd_total"
OPEN_MESSAGE_STATUSES = {"open", "acknowledged"}


def cost_alert_candidates(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    task: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    _validate_scope(index, project=project, member=member, assignment=assignment, task=task)
    summary = summarize_model_costs(index)
    existing_messages = _existing_cost_alert_messages(index)
    candidates: list[dict[str, Any]] = []

    for row in summary["byRun"]:
        run_id = str(row.get("run") or "")
        run = index.runs.get(run_id)
        if run is None or not _run_matches_scope(run, project=project, member=member, assignment=assignment, task=task):
            continue
        policy = _select_budget_policy(index, run_id)
        if policy is None:
            continue
        candidate = _threshold_candidate(index, run_id, row, policy, existing_messages)
        if candidate is not None:
            candidates.append(candidate)

    overview = {
        "source": "workspace-event-ledger",
        "metricName": COST_METRIC_NAME,
        "summary": {
            "candidates": len(candidates),
            "routable": sum(1 for item in candidates if not item["suppressed"]),
            "suppressed": sum(1 for item in candidates if item["suppressed"]),
            "costUsd": summary["totals"]["costUsd"],
            "calls": summary["totals"]["calls"],
            "policies": len({item["policy"] for item in candidates}),
        },
        "candidates": candidates,
    }
    return CostAlertOverviewRecord.model_validate(overview).model_dump(mode="json")


def route_cost_alerts(
    workspace_path: str | Path,
    *,
    actor_member: str,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    task: str | None = None,
    max_messages: int | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "service"}:
        raise ValueError("cost alert routing requires a human or service actor member")

    overview = cost_alert_candidates(index, project=project, member=member, assignment=assignment, task=task)
    routable = [item for item in overview["candidates"] if not item["suppressed"]]
    if max_messages is not None:
        routable = routable[:max_messages]

    created_messages: list[dict[str, Any]] = []
    if not dry_run:
        for candidate in routable:
            message = record_member_message(
                workspace_path,
                from_member=actor_member,
                to_members=list(candidate["targetMembers"]),
                channel="cost-alerts" if not candidate["targetMembers"] else None,
                message_type="cost-alert",
                project=candidate["project"],
                task=candidate["task"],
                run=candidate["run"],
                priority="urgent" if candidate["thresholdKind"] == "hard" else "high",
                body=_message_body(candidate),
                attachments=[candidate["run"], candidate["policy"]],
                audit={
                    "costAlertDedupeKey": candidate["dedupeKey"],
                    "metricName": COST_METRIC_NAME,
                    "policy": candidate["policy"],
                    "thresholdName": candidate["thresholdName"],
                    "thresholdKind": candidate["thresholdKind"],
                    "limitUsd": candidate["limitUsd"],
                    "costUsd": candidate["costUsd"],
                    "usageRatio": candidate["usageRatio"],
                    "sourceRun": candidate["run"],
                    "source": "cost-alert-routing",
                },
                source="cost-alert-routing",
            )
            created_messages.append(manifest_to_record(message))

    return {
        **overview,
        "dryRun": dry_run,
        "createdMessages": created_messages,
        "skippedCandidates": max(0, len(overview["candidates"]) - len(routable)),
    }


def _validate_scope(
    index: WorkspaceIndex,
    *,
    project: str | None,
    member: str | None,
    assignment: str | None,
    task: str | None,
) -> None:
    if project is not None and project != index.project.object_id:
        raise KeyError(f"unknown project {project}")
    if member is not None and member not in index.members:
        raise KeyError(f"unknown member {member}")
    if assignment is not None and assignment not in index.assignments:
        raise KeyError(f"unknown assignment {assignment}")
    if task is not None and task not in index.tasks:
        raise KeyError(f"unknown task {task}")


def _run_matches_scope(
    run: Any,
    *,
    project: str | None,
    member: str | None,
    assignment: str | None,
    task: str | None,
) -> bool:
    if project is not None and run.spec.project != project:
        return False
    if member is not None and run.spec.member != member:
        return False
    if assignment is not None and run.spec.assignment != assignment:
        return False
    if task is not None and run.spec.task != task:
        return False
    return True


def _threshold_candidate(
    index: WorkspaceIndex,
    run_id: str,
    row: dict[str, Any],
    policy: BudgetPolicy,
    existing_messages: dict[str, str],
) -> dict[str, Any] | None:
    cost_usd = float(row.get("costUsd") or 0.0)
    limits = policy.spec.limits
    threshold_name: str | None = None
    threshold_kind: str | None = None
    limit_usd: float | None = None
    if limits.maxUsdPerRun is not None and cost_usd >= limits.maxUsdPerRun:
        threshold_name = "maxUsdPerRun"
        threshold_kind = "hard"
        limit_usd = float(limits.maxUsdPerRun)
    elif limits.softUsdPerRun is not None and cost_usd >= limits.softUsdPerRun:
        threshold_name = "softUsdPerRun"
        threshold_kind = "soft"
        limit_usd = float(limits.softUsdPerRun)
    if threshold_name is None or threshold_kind is None or limit_usd is None:
        return None

    run = index.runs[run_id]
    dedupe_key = f"cost-alert:{run_id}:{policy.object_id}:{threshold_name}"
    existing_message = existing_messages.get(dedupe_key)
    target_members = [run.spec.member] if run.spec.member in index.members else []
    return {
        "id": dedupe_key,
        "source": "workspace-event-ledger",
        "metricName": COST_METRIC_NAME,
        "project": run.spec.project,
        "task": run.spec.task,
        "run": run_id,
        "member": run.spec.member,
        "assignment": run.spec.assignment,
        "policy": policy.object_id,
        "thresholdName": threshold_name,
        "thresholdKind": threshold_kind,
        "limitUsd": limit_usd,
        "costUsd": cost_usd,
        "usageRatio": round(cost_usd / limit_usd, 4) if limit_usd else 0.0,
        "targetMembers": target_members,
        "existingMessage": existing_message,
        "suppressed": existing_message is not None,
        "status": "suppressed-by-open-message" if existing_message else "routable",
        "severity": "critical" if threshold_kind == "hard" else "warning",
        "dedupeKey": dedupe_key,
    }


def _existing_cost_alert_messages(index: WorkspaceIndex) -> dict[str, str]:
    messages: dict[str, str] = {}
    for message in sorted(index.member_messages.values(), key=lambda item: item.object_id):
        if message.spec.messageType != "cost-alert" or message.spec.status not in OPEN_MESSAGE_STATUSES:
            continue
        dedupe_key = message.spec.audit.get("costAlertDedupeKey")
        if isinstance(dedupe_key, str) and dedupe_key:
            messages.setdefault(dedupe_key, message.object_id)
    return messages


def _select_budget_policy(index: WorkspaceIndex, run_id: str) -> BudgetPolicy | None:
    run = index.runs[run_id]
    candidates: list[tuple[int, str, BudgetPolicy]] = []
    for policy in index.budget_policies.values():
        scope = policy.spec.scope
        if scope.task and scope.task != run.spec.task:
            continue
        if scope.project and scope.project != run.spec.project:
            continue
        if scope.member and scope.member != run.spec.member:
            continue
        if scope.assignment and scope.assignment != run.spec.assignment:
            continue
        score = 0
        if scope.project:
            score += 1
        if scope.member:
            score += 2
        if scope.assignment:
            score += 3
        if scope.task:
            score += 8
        candidates.append((score, policy.object_id, policy))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _message_body(candidate: dict[str, Any]) -> str:
    return (
        f"Run {candidate['run']} recorded ${candidate['costUsd']:.4f} against "
        f"BudgetPolicy {candidate['policy']} {candidate['thresholdName']}=${candidate['limitUsd']:.4f}."
    )
