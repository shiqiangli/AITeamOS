from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiteamos_schema import MemberGrowthProjectionRecord

from .loader import WorkspaceIndex, load_workspace


NON_PUNITIVE_POLICY = [
    "Growth projections are read-only support signals, not rankings or promotion decisions.",
    "Failed, stalled, interrupted, or escalated work indicates review or support needs; it is not a negative score.",
    "Raw counts must be interpreted with task risk, assignment scope, review load, and collaboration context.",
    "Only reviewed TeamMember growth records can become durable member profile evidence.",
]


def member_growth_projection(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    member: str | None = None,
    project: str | None = None,
    assignment: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if member and member not in index.members:
        raise KeyError(f"unknown member {member}")
    if project and project != index.project.object_id:
        raise KeyError(f"unknown project {project}")
    if assignment and assignment not in index.assignments:
        raise KeyError(f"unknown assignment {assignment}")
    if assignment:
        assignment_record = index.assignments[assignment]
        if member and assignment_record.spec.member != member:
            raise ValueError(f"assignment {assignment} belongs to member {assignment_record.spec.member}, not {member}")
        if project and assignment_record.spec.project != project:
            raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {project}")
        member = member or assignment_record.spec.member
        project = project or assignment_record.spec.project

    items = [_member_growth_item(index, member_id, project=project, assignment=assignment) for member_id in _selected_members(index, member, project, assignment)]
    summary = {
        "members": len(items),
        "assignments": sum(len(item["assignments"]) for item in items),
        "tasks": sum(item["activityCounts"]["tasks"] for item in items),
        "activeTasks": sum(item["activityCounts"]["activeTasks"] for item in items),
        "runs": sum(item["activityCounts"]["runs"] for item in items),
        "memberActivities": sum(item["activityCounts"]["memberActivities"] for item in items),
        "gitActivities": sum(item["activityCounts"]["gitActivities"] for item in items),
        "automationRuns": sum(item["activityCounts"]["automationRuns"] for item in items),
        "supportSignals": sum(len(item["supportSignals"]) for item in items),
    }
    return MemberGrowthProjectionRecord.model_validate(
        {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "filters": {"member": member, "project": project, "assignment": assignment},
            "summary": summary,
            "nonPunitivePolicy": NON_PUNITIVE_POLICY,
            "items": items,
        }
    ).model_dump(mode="json")


def _selected_members(index: WorkspaceIndex, member: str | None, project: str | None, assignment: str | None) -> list[str]:
    if member:
        return [member]
    if assignment:
        return [index.assignments[assignment].spec.member]
    if project:
        return sorted({record.spec.member for record in index.assignments.values() if record.spec.project == project})
    return sorted(index.members)


def _member_growth_item(index: WorkspaceIndex, member_id: str, *, project: str | None, assignment: str | None) -> dict[str, Any]:
    member = index.members[member_id]
    assignments = [
        record
        for record in index.assignments.values()
        if record.spec.member == member_id and _project_assignment_matches(record.spec.project, record.object_id, project, assignment)
    ]
    tasks = [
        task
        for task in index.tasks.values()
        if task.spec.assignedMember == member_id and _project_assignment_matches(task.spec.project, task.spec.assignment, project, assignment)
    ]
    runs = [
        run
        for run in index.runs.values()
        if run.spec.member == member_id and _project_assignment_matches(run.spec.project, run.spec.assignment, project, assignment)
    ]
    reviews = [
        review
        for review in index.reviews.values()
        if (review.spec.reviewerMember == member_id or review.spec.reviewer == member_id)
        and _project_assignment_matches(review.spec.project, _review_assignment(index, review.spec.task, review.spec.run), project, assignment)
    ]
    memory_proposals = [
        proposal
        for proposal in index.memory_proposals.values()
        if proposal.spec.member == member_id and _project_assignment_matches(proposal.spec.project, proposal.spec.assignment, project, assignment)
    ]
    messages = [
        message
        for message in index.member_messages.values()
        if _message_matches_member(message, member_id) and _project_assignment_matches(message.spec.project, _task_assignment(index, message.spec.task), project, assignment)
    ]
    handoffs = [
        handoff
        for handoff in index.handoffs.values()
        if (handoff.spec.fromMember == member_id or handoff.spec.toMember == member_id)
        and _project_assignment_matches(handoff.spec.project or _task_project(index, handoff.spec.task), _task_assignment(index, handoff.spec.task), project, assignment)
    ]
    retrospectives = [
        retro
        for retro in index.team_retrospectives.values()
        if (retro.spec.facilitatorMember == member_id or member_id in retro.spec.participants) and (not project or retro.spec.project == project)
    ]
    activities = [
        activity
        for activity in index.member_activities.values()
        if activity.spec.member == member_id and _project_assignment_matches(activity.spec.project, activity.spec.assignment, project, assignment)
    ]
    git_activities = [
        activity
        for activity in index.git_activities.values()
        if activity.spec.member == member_id and _project_assignment_matches(activity.spec.project, activity.spec.assignment, project, assignment)
    ]
    automation_runs = [
        run
        for run in index.automation_runs.values()
        if (run.spec.ownerMember == member_id or run.spec.serviceMember == member_id)
        and _project_assignment_matches(run.spec.project, None, project, assignment)
    ]
    counts = {
        "assignments": len(assignments),
        "tasks": len(tasks),
        "activeTasks": sum(1 for task in tasks if task.spec.status not in {"DONE", "FAILED", "ARCHIVED"}),
        "doneTasks": sum(1 for task in tasks if task.spec.status == "DONE"),
        "runs": len(runs),
        "failedOrStalledRuns": sum(1 for run in runs if run.spec.status in {"FAILED", "STALLED", "INTERRUPTED"}),
        "reviewsAuthored": len(reviews),
        "memoryProposals": len(memory_proposals),
        "pendingMemoryProposals": sum(1 for proposal in memory_proposals if proposal.spec.status in {"proposed", "needs-review", "pending", "pending-review"}),
        "messages": len(messages),
        "openMessages": sum(1 for message in messages if message.spec.status in {"open", "acknowledged"}),
        "handoffsSent": sum(1 for handoff in handoffs if handoff.spec.fromMember == member_id),
        "handoffsReceived": sum(1 for handoff in handoffs if handoff.spec.toMember == member_id),
        "openHandoffs": sum(1 for handoff in handoffs if handoff.spec.status in {"requested", "accepted"}),
        "retrospectives": len(retrospectives),
        "memberActivities": len(activities),
        "gitActivities": len(git_activities),
        "automationRuns": len(automation_runs),
        "declaredGrowthRecords": len(member.spec.growthRecords),
        "declaredPerformanceMetrics": len(member.spec.performanceMetrics),
    }
    contribution_counts = _contribution_counts(
        tasks=tasks,
        runs=runs,
        reviews=reviews,
        memory_proposals=memory_proposals,
        messages=messages,
        handoffs=handoffs,
        retrospectives=retrospectives,
        activities=activities,
        git_activities=git_activities,
        automation_runs=automation_runs,
    )
    support_signals = _support_signals(counts)
    skill_ids = _member_skill_ids(member)
    growth_plan_actions = _growth_plan_actions(
        member_id=member_id,
        member_kind=member.spec.kind,
        counts=counts,
        tasks=tasks,
        runs=runs,
        reviews=reviews,
        memory_proposals=memory_proposals,
        messages=messages,
        handoffs=handoffs,
        activities=activities,
        git_activities=git_activities,
        skill_ids=skill_ids,
    )
    return {
        "member": member_id,
        "memberKind": member.spec.kind,
        "project": project or index.project.object_id,
        "assignments": [record.object_id for record in assignments],
        "activityCounts": counts,
        "contributionCounts": contribution_counts,
        "supportSignals": support_signals,
        "growthPlanActions": growth_plan_actions,
        "growthRecords": [record.model_dump(mode="json") for record in member.spec.growthRecords],
        "declaredPerformanceMetrics": [metric.model_dump(mode="json") for metric in member.spec.performanceMetrics],
        "evidence": _evidence(tasks, runs, reviews, memory_proposals, handoffs, messages, activities, git_activities, automation_runs),
        "warnings": [],
    }


def _contribution_counts(
    *,
    tasks: list[Any],
    runs: list[Any],
    reviews: list[Any],
    memory_proposals: list[Any],
    messages: list[Any],
    handoffs: list[Any],
    retrospectives: list[Any],
    activities: list[Any],
    git_activities: list[Any],
    automation_runs: list[Any],
) -> dict[str, int]:
    explicit = {
        "authoredWork": 0,
        "reviewWork": 0,
        "supportWork": 0,
        "automationWork": 0,
        "knowledgeWork": 0,
        "coordinationWork": 0,
        "gitWork": 0,
        "other": 0,
    }
    contribution_map = {
        "authored-work": "authoredWork",
        "review-work": "reviewWork",
        "support-work": "supportWork",
        "automation-work": "automationWork",
        "knowledge-work": "knowledgeWork",
        "coordination-work": "coordinationWork",
        "git-work": "gitWork",
        "other": "other",
    }
    for activity in activities:
        explicit[contribution_map.get(activity.spec.contributionKind, "other")] += 1
    return {
        "authoredWork": len(tasks) + len(runs) + explicit["authoredWork"],
        "reviewWork": len(reviews) + explicit["reviewWork"],
        "supportWork": sum(1 for handoff in handoffs if handoff.spec.status in {"requested", "accepted"}) + explicit["supportWork"],
        "automationWork": len(automation_runs) + explicit["automationWork"],
        "knowledgeWork": len(memory_proposals) + len(retrospectives) + explicit["knowledgeWork"],
        "coordinationWork": len(messages) + len(handoffs) + explicit["coordinationWork"],
        "gitWork": len(git_activities) + explicit["gitWork"],
        "other": explicit["other"],
    }


def _support_signals(counts: dict[str, int]) -> list[str]:
    signals: list[str] = []
    if counts["failedOrStalledRuns"]:
        signals.append("review-run-recovery-context")
    if counts["pendingMemoryProposals"]:
        signals.append("review-pending-memory-proposals")
    if counts["openMessages"] or counts["openHandoffs"]:
        signals.append("close-open-collaboration-loops")
    if counts["activeTasks"] >= 4:
        signals.append("review-work-in-progress-load")
    if not counts["declaredGrowthRecords"]:
        signals.append("consider-reviewed-growth-note-after-closeout")
    return signals


def _member_skill_ids(member: Any) -> list[str]:
    related = {
        related_skill
        for capability in member.spec.capabilities
        for related_skill in capability.relatedSkills
        if related_skill
    }
    return sorted({*member.spec.skills, *related})


def _growth_plan_actions(
    *,
    member_id: str,
    member_kind: str,
    counts: dict[str, int],
    tasks: list[Any],
    runs: list[Any],
    reviews: list[Any],
    memory_proposals: list[Any],
    messages: list[Any],
    handoffs: list[Any],
    activities: list[Any],
    git_activities: list[Any],
    skill_ids: list[str],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    assisted_runs = [run for run in runs if _run_needs_assisted_ingest(run)]
    if member_kind in {"human", "hybrid"} and assisted_runs:
        related_runs = _ids(assisted_runs)
        related_tasks = _ids(task for task in tasks if task.object_id in {run.spec.task for run in assisted_runs})
        actions.append(
            {
                "id": f"{member_id}:complete-assisted-ingest",
                "actionType": "complete-assisted-ingest",
                "label": f"Complete assisted ingest for {related_runs[0]}",
                "rationale": "Human and hybrid execution should return journal, tests, review target, and proposed memory through the explicit assisted ingest boundary.",
                "status": "ready",
                "evidence": _refs("run", related_runs) + _refs("task", related_tasks),
                "relatedTasks": related_tasks,
                "relatedRuns": related_runs,
            }
        )
    pending_proposals = [proposal for proposal in memory_proposals if proposal.spec.status in {"proposed", "needs-review", "pending", "pending-review"}]
    if pending_proposals:
        related_proposals = _ids(pending_proposals)
        actions.append(
            {
                "id": f"{member_id}:review-memory-proposals",
                "actionType": "review-memory-proposals",
                "label": "Review pending memory proposals",
                "rationale": "Learning should become durable memory only after review, approval, versioning, and binding.",
                "status": "ready",
                "evidence": _refs("memory-proposal", related_proposals),
                "relatedMemoryProposals": related_proposals,
            }
        )
    failed_runs = [run for run in runs if run.spec.status in {"FAILED", "STALLED", "INTERRUPTED"}]
    if failed_runs:
        related_runs = _ids(failed_runs)
        related_tasks = _ids(task for task in tasks if task.object_id in {run.spec.task for run in failed_runs})
        actions.append(
            {
                "id": f"{member_id}:review-run-recovery",
                "actionType": "review-run-recovery",
                "label": "Review run recovery context",
                "rationale": "Failed, stalled, or interrupted work is a support signal that needs recovery context, not a score.",
                "status": "ready",
                "evidence": _refs("run", related_runs) + _refs("task", related_tasks),
                "relatedTasks": related_tasks,
                "relatedRuns": related_runs,
            }
        )
    open_messages = [message for message in messages if message.spec.status in {"open", "acknowledged"}]
    open_handoffs = [handoff for handoff in handoffs if handoff.spec.status in {"requested", "accepted"}]
    if open_messages or open_handoffs:
        related_messages = _ids(open_messages)
        related_handoffs = _ids(open_handoffs)
        actions.append(
            {
                "id": f"{member_id}:close-collaboration-loops",
                "actionType": "close-collaboration-loops",
                "label": "Close open collaboration loops",
                "rationale": "Open asks, help requests, and handoffs should be resolved before deriving stable growth evidence.",
                "status": "suggested",
                "evidence": _refs("message", related_messages) + _refs("handoff", related_handoffs),
                "relatedMessages": related_messages,
                "relatedHandoffs": related_handoffs,
            }
        )
    if counts["activeTasks"] >= 4:
        active_tasks = _ids(task for task in tasks if task.spec.status not in {"DONE", "FAILED", "ARCHIVED"})
        actions.append(
            {
                "id": f"{member_id}:review-work-in-progress-load",
                "actionType": "review-work-in-progress-load",
                "label": "Review active work load",
                "rationale": "Many active tasks can indicate a planning or support need that should be handled before adding more work.",
                "status": "suggested",
                "evidence": _refs("task", active_tasks),
                "relatedTasks": active_tasks,
            }
        )
    if not counts["declaredGrowthRecords"] and (tasks or runs or reviews or memory_proposals or activities or git_activities):
        related_reviews = _ids(reviews)
        related_tasks = _ids(tasks)
        related_runs = _ids(runs)
        actions.append(
            {
                "id": f"{member_id}:capture-reviewed-growth-note",
                "actionType": "capture-reviewed-growth-note",
                "label": "Capture reviewed growth note",
                "rationale": "Observed work can become profile evidence only when a reviewer intentionally records a growth note.",
                "status": "suggested",
                "evidence": _refs("task", related_tasks[:3]) + _refs("run", related_runs[:3]) + _refs("review", related_reviews[:3]),
                "relatedTasks": related_tasks,
                "relatedRuns": related_runs,
                "relatedReviews": related_reviews,
            }
        )
    if skill_ids and (member_kind in {"human", "hybrid"} or counts["declaredPerformanceMetrics"] == 0):
        actions.append(
            {
                "id": f"{member_id}:review-skill-fit",
                "actionType": "review-skill-fit",
                "label": "Review skill fit and next practice",
                "rationale": "Declared skills should connect to recent work evidence and an explicit next practice item.",
                "status": "suggested",
                "evidence": _refs("skill", skill_ids) + _refs("activity", _ids(activities)[:3]) + _refs("git-activity", _ids(git_activities)[:3]),
                "relatedSkills": skill_ids,
            }
        )
    return actions[:6]


def _run_needs_assisted_ingest(run: Any) -> bool:
    if run.spec.mode != "assisted":
        return False
    ingest = run.spec.ingest if isinstance(run.spec.ingest, dict) else {}
    missing = ingest.get("missing") if isinstance(ingest.get("missing"), list) else []
    artifacts = ingest.get("artifacts") if isinstance(ingest.get("artifacts"), list) else []
    if missing:
        return True
    return run.spec.status in {"READY", "RUNNING", "STALLED", "INTERRUPTED"} and not artifacts and not run.spec.reviewTarget


def _ids(records: Any) -> list[str]:
    return sorted({str(record.object_id) for record in records})[:8]


def _refs(prefix: str, ids: list[str]) -> list[str]:
    return [f"{prefix}:{value}" for value in ids[:8]]


def _evidence(
    tasks: list[Any],
    runs: list[Any],
    reviews: list[Any],
    proposals: list[Any],
    handoffs: list[Any],
    messages: list[Any],
    activities: list[Any],
    git_activities: list[Any],
    automation_runs: list[Any],
) -> list[str]:
    ids = [
        *[f"task:{task.object_id}" for task in tasks],
        *[f"run:{run.object_id}" for run in runs],
        *[f"review:{review.object_id}" for review in reviews],
        *[f"memory-proposal:{proposal.object_id}" for proposal in proposals],
        *[f"handoff:{handoff.object_id}" for handoff in handoffs],
        *[f"message:{message.object_id}" for message in messages],
        *[f"activity:{activity.object_id}" for activity in activities],
        *[f"git-activity:{activity.object_id}" for activity in git_activities],
        *[f"automation-run:{run.object_id}" for run in automation_runs],
    ]
    return sorted(ids)[:40]


def _project_assignment_matches(record_project: str | None, record_assignment: str | None, project: str | None, assignment: str | None) -> bool:
    if project and record_project and record_project != project:
        return False
    if assignment and record_assignment != assignment:
        return False
    return True


def _review_assignment(index: WorkspaceIndex, task_id: str | None, run_id: str | None) -> str | None:
    if run_id and run_id in index.runs:
        return index.runs[run_id].spec.assignment
    return _task_assignment(index, task_id)


def _task_assignment(index: WorkspaceIndex, task_id: str | None) -> str | None:
    if task_id and task_id in index.tasks:
        return index.tasks[task_id].spec.assignment
    return None


def _task_project(index: WorkspaceIndex, task_id: str | None) -> str | None:
    if task_id and task_id in index.tasks:
        return index.tasks[task_id].spec.project
    return None


def _message_matches_member(message: Any, member_id: str) -> bool:
    return message.spec.fromMember == member_id or member_id in message.spec.toMembers
