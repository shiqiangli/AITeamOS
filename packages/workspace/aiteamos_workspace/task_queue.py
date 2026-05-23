from __future__ import annotations

from pathlib import Path
from typing import Any

from aiteamos_schema import TaskExecutionQueueRecord

from .loader import WorkspaceIndex, load_workspace


ACTIVE_RUN_STATUSES = {"READY", "QUEUED", "CONTEXT_BUILDING", "RUNNING", "TESTING", "RECOVERING"}
ATTENTION_RUN_STATUSES = {"FAILED", "INTERRUPTED", "INGEST_INCOMPLETE", "CHANGES_REQUESTED"}
MANAGED_RUN_MODES = {"managed_llm"}
QUEUE_STATUSES = [
    "ready-to-run",
    "needs-member",
    "needs-assignment",
    "needs-execution-profile",
    "needs-model",
    "active",
    "stalled",
    "review-ready",
    "needs-attention",
    "done",
]


def task_execution_queue(workspace_or_index: str | Path | WorkspaceIndex) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    counts = {status: 0 for status in QUEUE_STATUSES}
    items = []
    runs_by_task = _runs_by_task(index)
    for task_id in sorted(index.tasks):
        task = index.tasks[task_id]
        task_runs = runs_by_task.get(task_id, [])
        queue_status, blockers, actions = _task_queue_status(index, task_id, task_runs)
        counts[queue_status] += 1
        latest_run = _latest_run(task_runs)
        assignment_id = task.spec.assignment or _single_active_assignment(index, task.spec.assignedMember, task.spec.project)
        items.append(
            {
                "id": task_id,
                "queueStatus": queue_status,
                "title": task.spec.title,
                "taskStatus": task.spec.status,
                "assignedMember": task.spec.assignedMember,
                "assignment": assignment_id,
                "memberModelProfile": _default_model_profile(index, task.spec.assignedMember, assignment_id),
                "latestRun": latest_run.object_id if latest_run else None,
                "latestRunStatus": latest_run.spec.status if latest_run else None,
                "runCount": len(task_runs),
                "blockers": blockers,
                "actions": actions,
            }
        )
    order = {status: position for position, status in enumerate(QUEUE_STATUSES)}
    items.sort(key=lambda item: (order[item["queueStatus"]], item["assignedMember"] or "", item["assignment"] or "", item["id"]))
    return TaskExecutionQueueRecord.model_validate({"summary": counts | {"total": len(items)}, "items": items}).model_dump(mode="json")


def _runs_by_task(index: WorkspaceIndex) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for run in index.runs.values():
        grouped.setdefault(run.spec.task, []).append(run)
    for runs in grouped.values():
        runs.sort(key=lambda run: run.object_id)
    return grouped


def _latest_run(runs: list[Any]) -> Any | None:
    return runs[-1] if runs else None


def _task_queue_status(index: WorkspaceIndex, task_id: str, runs: list[Any]) -> tuple[str, list[str], list[str]]:
    task = index.tasks[task_id]
    blockers: list[str] = []
    actions: list[str] = []
    latest_run = _latest_run(runs)
    latest_status = latest_run.spec.status if latest_run else None
    if task.spec.status == "DONE" or latest_status == "DONE":
        return "done", blockers, ["No execution action required."]
    if latest_status in ACTIVE_RUN_STATUSES:
        return "active", blockers, ["Open the latest run and inspect worker events."]
    if latest_status == "STALLED" or task.spec.status == "STALLED":
        return "stalled", ["A run is stalled."], ["Inspect recovery and build a retry plan from Run Detail."]
    if latest_status == "REVIEW" or task.spec.status == "REVIEW":
        return "review-ready", blockers, ["Open the review target and record human review."]
    if latest_status in ATTENTION_RUN_STATUSES or task.spec.status in ATTENTION_RUN_STATUSES:
        return "needs-attention", ["Latest run or task requires human attention."], ["Open Run Detail and resolve failed or incomplete execution."]

    member_id = task.spec.assignedMember
    if not member_id or member_id not in index.members:
        return "needs-member", ["Task has no valid assigned TeamMember."], ["Assign a human, digital, hybrid, or service member before creating a run."]
    member = index.members[member_id]
    assignment_id = task.spec.assignment or _single_active_assignment(index, member_id, task.spec.project)
    if not assignment_id or assignment_id not in index.assignments:
        return "needs-assignment", ["Task has no active assignment context."], ["Bind the member to a project/module/feature assignment before creating a run."]
    assignment = index.assignments[assignment_id]
    if assignment.spec.member != member_id or assignment.spec.project != task.spec.project:
        return "needs-assignment", ["Task assignment does not match the assigned member/project."], ["Choose an assignment owned by the selected member in this project."]

    profile = _execution_profile(index, member_id, member.spec.kind)
    if member.spec.kind in {"digital", "hybrid", "service"} and profile is None:
        return "needs-execution-profile", [f"Member {member_id} has no {member.spec.kind} execution profile."], ["Create an execution/collaboration profile for this member."]

    mode = task.spec.executionMode or _default_execution_mode(profile) or index.project.spec.defaultExecutionMode or "assisted"
    needs_model = mode in MANAGED_RUN_MODES
    model_profile = _default_model_profile(index, member_id, assignment_id)
    if needs_model and not model_profile:
        return "needs-model", ["Managed execution requires a model profile."], ["Choose a model profile or set a member/assignment default."]
    return "ready-to-run", blockers, ["Create a run, inspect its context capsule, then start managed or assisted execution."]


def _single_active_assignment(index: WorkspaceIndex, member_id: str | None, project: str) -> str | None:
    if not member_id:
        return None
    matches = [
        assignment.object_id
        for assignment in index.assignments.values()
        if assignment.spec.member == member_id and assignment.spec.project == project and assignment.spec.status == "active"
    ]
    return sorted(matches)[0] if len(matches) == 1 else None


def _execution_profile(index: WorkspaceIndex, member_id: str, member_kind: str) -> Any | None:
    stores = {
        "digital": index.digital_execution_profiles,
        "human": index.human_collaboration_profiles,
        "hybrid": index.hybrid_execution_profiles,
        "service": index.service_account_profiles,
    }
    return stores.get(member_kind, {}).get(member_id)


def _default_execution_mode(profile: Any | None) -> str | None:
    if profile is None:
        return None
    runtime = getattr(profile.spec, "workerRuntime", None)
    if isinstance(runtime, dict):
        return runtime.get("defaultMode")
    ingest_policy = getattr(profile.spec, "ingestPolicy", None)
    if isinstance(ingest_policy, dict):
        return ingest_policy.get("defaultMode")
    return None


def _default_model_profile(index: WorkspaceIndex, member_id: str | None, assignment_id: str | None) -> str | None:
    if not member_id or member_id not in index.members:
        return None
    member = index.members[member_id]
    profile = _execution_profile(index, member_id, member.spec.kind)
    if profile is not None and getattr(profile.spec, "defaultModelProfile", None):
        return profile.spec.defaultModelProfile
    for profile_id, model in sorted(index.model_profiles.items()):
        if assignment_id and assignment_id in model.spec.defaultForAssignments:
            return profile_id
        if member_id in model.spec.defaultForMembers:
            return profile_id
    return None
