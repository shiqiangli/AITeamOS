from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any

from aiteamos_schema import RetrospectiveSuggestionRecord

from .loader import WorkspaceIndex, manifest_to_record


OPEN_MESSAGE_STATUSES = {"open", "acknowledged"}
OPEN_HANDOFF_STATUSES = {"requested", "accepted"}


def collaboration_overview(
    index: WorkspaceIndex,
    *,
    member: str | None = None,
    project: str | None = None,
    task: str | None = None,
    message_type: str | None = None,
) -> dict[str, Any]:
    if member and member not in index.members:
        raise KeyError(f"unknown member {member}")
    selected_project = project or index.project.object_id
    if selected_project != index.project.object_id:
        raise KeyError(f"unknown project {selected_project}")
    if task and task not in index.tasks:
        raise KeyError(f"unknown task {task}")

    messages = [
        message
        for message in index.member_messages.values()
        if _message_matches(message, member=member, project=selected_project, task=task, message_type=message_type)
    ]
    handoffs = [
        handoff
        for handoff in index.handoffs.values()
        if _handoff_matches(handoff, member=member, project=selected_project, task=task)
    ]
    retrospectives = [
        retrospective
        for retrospective in index.team_retrospectives.values()
        if _retrospective_matches(index, retrospective, member=member, project=selected_project, task=task)
    ]

    return {
        "summary": {
            "messages": len(messages),
            "openMessages": sum(1 for message in messages if message.spec.status in OPEN_MESSAGE_STATUSES),
            "resolvedMessages": sum(1 for message in messages if message.spec.status == "resolved"),
            "askForHelp": sum(1 for message in messages if message.spec.messageType == "ask-for-help"),
            "reviewRequests": sum(1 for message in messages if message.spec.messageType == "review-request"),
            "knowledgeShares": sum(1 for message in messages if message.spec.messageType == "knowledge-share"),
            "handoffs": len(handoffs),
            "openHandoffs": sum(1 for handoff in handoffs if handoff.spec.status in OPEN_HANDOFF_STATUSES),
            "retrospectives": len(retrospectives),
            "proposedRetrospectives": sum(1 for retrospective in retrospectives if retrospective.spec.status == "proposed"),
        },
        "messages": [manifest_to_record(message) for message in sorted(messages, key=lambda item: item.object_id)],
        "handoffs": [manifest_to_record(handoff) for handoff in sorted(handoffs, key=lambda item: item.object_id)],
        "retrospectives": [manifest_to_record(retrospective) for retrospective in sorted(retrospectives, key=lambda item: item.object_id)],
        "byMember": _member_projection(index, messages, handoffs, retrospectives),
        "byProject": _project_projection(index, messages, handoffs, retrospectives),
        "filters": {
            "member": member,
            "project": selected_project,
            "task": task,
            "messageType": message_type,
        },
    }


def retrospective_suggestions(
    index: WorkspaceIndex,
    *,
    member: str | None = None,
    project: str | None = None,
    task: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    if member and member not in index.members:
        raise KeyError(f"unknown member {member}")
    selected_project = project or index.project.object_id
    if selected_project != index.project.object_id:
        raise KeyError(f"unknown project {selected_project}")
    if task and task not in index.tasks:
        raise KeyError(f"unknown task {task}")

    task_ids = _retrospective_task_ids(index, member=member, project=selected_project, task=task)
    candidates = [
        candidate
        for task_id in sorted(task_ids)
        if (candidate := _build_retrospective_candidate(index, task_id, member=member, project=selected_project)) is not None
    ]
    candidates = sorted(candidates, key=lambda item: (-float(item["score"]), item["id"]))[:limit]
    payload = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "filters": {"member": member, "project": selected_project, "task": task, "limit": limit},
        "summary": {
            "candidateCount": len(candidates),
            "sourceRuns": sum(len(candidate["sourceRuns"]) for candidate in candidates),
            "sourceTasks": sum(len(candidate["sourceTasks"]) for candidate in candidates),
            "sourceMessages": sum(len(candidate["sourceMessages"]) for candidate in candidates),
            "sourceHandoffs": sum(len(candidate["sourceHandoffs"]) for candidate in candidates),
        },
        "candidates": candidates,
    }
    return RetrospectiveSuggestionRecord.model_validate(payload).model_dump(mode="json")


def _message_matches(message: Any, *, member: str | None, project: str | None, task: str | None, message_type: str | None) -> bool:
    if member and member not in {message.spec.fromMember, *message.spec.toMembers}:
        return False
    if project and message.spec.project not in {None, project}:
        return False
    if task and message.spec.task != task:
        return False
    if message_type and message.spec.messageType != message_type:
        return False
    return True


def _handoff_matches(handoff: Any, *, member: str | None, project: str | None, task: str | None) -> bool:
    if member and member not in {handoff.spec.fromMember, handoff.spec.toMember}:
        return False
    if project and handoff.spec.project not in {None, project}:
        return False
    if task and handoff.spec.task != task:
        return False
    return True


def _retrospective_matches(index: WorkspaceIndex, retrospective: Any, *, member: str | None, project: str | None, task: str | None) -> bool:
    if member and member not in {retrospective.spec.facilitatorMember, *retrospective.spec.participants}:
        return False
    if project and retrospective.spec.project != project:
        return False
    if task:
        run_tasks = {
            index.runs[run_id].spec.task
            for run_id in retrospective.spec.sourceRuns
            if run_id in index.runs and index.runs[run_id].spec.task
        }
        if task not in {*retrospective.spec.sourceTasks, *run_tasks}:
            return False
    return True


def _member_projection(index: WorkspaceIndex, messages: list[Any], handoffs: list[Any], retrospectives: list[Any]) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {
        member_id: {
            "id": member_id,
            "kind": "CollaborationMemberProjection",
            "spec": {
                "member": member_id,
                "memberKind": index.members[member_id].spec.kind,
                "messageCount": 0,
                "openMessageCount": 0,
                "sentCount": 0,
                "receivedCount": 0,
                "handoffCount": 0,
                "openHandoffCount": 0,
                "retrospectiveCount": 0,
            },
        }
        for member_id in index.members
    }
    for message in messages:
        participants = {message.spec.fromMember, *message.spec.toMembers}
        for member_id in participants:
            if member_id not in rows:
                continue
            spec = rows[member_id]["spec"]
            spec["messageCount"] += 1
            if message.spec.status in OPEN_MESSAGE_STATUSES:
                spec["openMessageCount"] += 1
            if message.spec.fromMember == member_id:
                spec["sentCount"] += 1
            if member_id in message.spec.toMembers:
                spec["receivedCount"] += 1
    for handoff in handoffs:
        for member_id in {handoff.spec.fromMember, handoff.spec.toMember}:
            if member_id not in rows:
                continue
            spec = rows[member_id]["spec"]
            spec["handoffCount"] += 1
            if handoff.spec.status in OPEN_HANDOFF_STATUSES:
                spec["openHandoffCount"] += 1
    for retrospective in retrospectives:
        for member_id in {retrospective.spec.facilitatorMember, *retrospective.spec.participants}:
            if member_id not in rows:
                continue
            rows[member_id]["spec"]["retrospectiveCount"] += 1
    return sorted(rows.values(), key=lambda row: row["id"])


def _project_projection(index: WorkspaceIndex, messages: list[Any], handoffs: list[Any], retrospectives: list[Any]) -> list[dict[str, Any]]:
    project_id = index.project.object_id
    return [
        {
            "id": project_id,
            "kind": "CollaborationProjectProjection",
            "spec": {
                "project": project_id,
                "messageCount": len(messages),
                "openMessageCount": sum(1 for message in messages if message.spec.status in OPEN_MESSAGE_STATUSES),
                "handoffCount": len(handoffs),
                "openHandoffCount": sum(1 for handoff in handoffs if handoff.spec.status in OPEN_HANDOFF_STATUSES),
                "retrospectiveCount": len(retrospectives),
            },
        }
    ]


def _retrospective_task_ids(index: WorkspaceIndex, *, member: str | None, project: str, task: str | None) -> set[str]:
    if task:
        return {task}
    task_ids: set[str] = set()
    for task_id, task_record in index.tasks.items():
        if task_record.spec.project != project:
            continue
        if member and task_record.spec.assignedMember != member:
            continue
        task_ids.add(task_id)
    for run in index.runs.values():
        if run.spec.project != project:
            continue
        if member and run.spec.member != member:
            continue
        task_ids.add(run.spec.task)
    for message in index.member_messages.values():
        if message.spec.project not in {None, project} or not message.spec.task:
            continue
        if member and member not in {message.spec.fromMember, *message.spec.toMembers}:
            continue
        task_ids.add(message.spec.task)
    for handoff in index.handoffs.values():
        if handoff.spec.project not in {None, project}:
            continue
        if member and member not in {handoff.spec.fromMember, handoff.spec.toMember}:
            continue
        task_ids.add(handoff.spec.task)
    return task_ids


def _build_retrospective_candidate(index: WorkspaceIndex, task_id: str, *, member: str | None, project: str) -> dict[str, Any] | None:
    task = index.tasks.get(task_id)
    if task is None or task.spec.project != project:
        return None
    runs = [
        run
        for run in index.runs.values()
        if run.spec.task == task_id and run.spec.project == project and (not member or run.spec.member == member)
    ]
    messages = [
        message
        for message in index.member_messages.values()
        if _message_matches(message, member=member, project=project, task=task_id, message_type=None)
    ]
    handoffs = [
        handoff
        for handoff in index.handoffs.values()
        if _handoff_matches(handoff, member=member, project=project, task=task_id)
    ]
    if not any([runs, messages, handoffs]):
        return None

    source_runs = [run.object_id for run in sorted(runs, key=lambda item: item.object_id)]
    source_messages = [message.object_id for message in sorted(messages, key=lambda item: item.object_id)]
    source_handoffs = [handoff.object_id for handoff in sorted(handoffs, key=lambda item: item.object_id)]
    participants = _retrospective_participants(task, runs, messages, handoffs)
    sources = _retrospective_sources(index, task, runs, messages, handoffs)
    lessons, action_items = _retrospective_lessons_and_actions(index, runs, messages, handoffs)
    evidence = [
        f"task:{task_id}",
        *[f"run:{run_id}" for run_id in source_runs],
        *[f"message:{message_id}" for message_id in source_messages],
        *[f"handoff:{handoff_id}" for handoff_id in source_handoffs],
    ]
    source_type_count = sum(1 for values in [source_runs, source_messages, source_handoffs] if values)
    score = len(source_runs) * 2 + len(source_messages) + len(source_handoffs) * 2 + source_type_count
    confidence = min(0.95, 0.55 + 0.1 * source_type_count + 0.03 * len(evidence))
    warnings = []
    if runs and not any(index.run_journals.get(run.object_id, "").strip() for run in runs):
        warnings.append("No source run has a journal body beyond the run manifest.")
    if not source_messages and not source_handoffs:
        warnings.append("Suggestion is based on run evidence only; facilitator should confirm team learning before creating memory.")

    summary = f"Review team learning for {task.spec.title}."
    candidate_id = "RSUG-" + hashlib.sha256("|".join(evidence).encode("utf-8")).hexdigest()[:16]
    proposed = {
        "facilitatorMember": _suggest_facilitator(index),
        "participants": participants,
        "project": project,
        "sourceRuns": source_runs,
        "sourceTasks": [task_id],
        "sourceMessages": source_messages,
        "sourceHandoffs": source_handoffs,
        "summary": summary,
        "lessons": lessons,
        "actionItems": action_items,
    }
    return {
        "id": candidate_id,
        "project": project,
        "facilitatorMember": proposed["facilitatorMember"],
        "participants": participants,
        "sourceRuns": source_runs,
        "sourceTasks": [task_id],
        "sourceMessages": source_messages,
        "sourceHandoffs": source_handoffs,
        "summary": summary,
        "lessons": lessons,
        "actionItems": action_items,
        "evidence": evidence,
        "sources": sources,
        "score": float(score),
        "confidence": round(confidence, 2),
        "warnings": warnings,
        "proposedRetrospective": proposed,
    }


def _retrospective_participants(task: Any, runs: list[Any], messages: list[Any], handoffs: list[Any]) -> list[str]:
    participants: set[str] = set()
    if task.spec.assignedMember:
        participants.add(task.spec.assignedMember)
    for run in runs:
        participants.add(run.spec.member)
    for message in messages:
        participants.add(message.spec.fromMember)
        participants.update(message.spec.toMembers)
    for handoff in handoffs:
        participants.add(handoff.spec.fromMember)
        participants.add(handoff.spec.toMember)
    return sorted(participants)


def _retrospective_sources(index: WorkspaceIndex, task: Any, runs: list[Any], messages: list[Any], handoffs: list[Any]) -> list[dict[str, Any]]:
    sources = [
        {
            "sourceType": "task",
            "id": task.object_id,
            "project": task.spec.project,
            "task": task.object_id,
            "member": task.spec.assignedMember,
            "status": task.spec.status,
            "summary": task.spec.title,
        }
    ]
    for run in sorted(runs, key=lambda item: item.object_id):
        journal = _brief(index.run_journals.get(run.object_id, ""), fallback=f"{run.spec.mode} run {run.spec.status}")
        sources.append(
            {
                "sourceType": "run",
                "id": run.object_id,
                "project": run.spec.project,
                "task": run.spec.task,
                "run": run.object_id,
                "member": run.spec.member,
                "status": run.spec.status,
                "summary": journal,
            }
        )
    for message in sorted(messages, key=lambda item: item.object_id):
        sources.append(
            {
                "sourceType": "message",
                "id": message.object_id,
                "project": message.spec.project or task.spec.project,
                "task": message.spec.task,
                "run": message.spec.run,
                "member": message.spec.fromMember,
                "status": message.spec.status,
                "summary": _brief(message.spec.body, fallback=message.spec.messageType),
            }
        )
    for handoff in sorted(handoffs, key=lambda item: item.object_id):
        sources.append(
            {
                "sourceType": "handoff",
                "id": handoff.object_id,
                "project": handoff.spec.project or task.spec.project,
                "task": handoff.spec.task,
                "run": handoff.spec.run,
                "member": handoff.spec.fromMember,
                "status": handoff.spec.status,
                "summary": _brief(handoff.spec.problem, fallback="handoff"),
            }
        )
    return sources


def _retrospective_lessons_and_actions(index: WorkspaceIndex, runs: list[Any], messages: list[Any], handoffs: list[Any]) -> tuple[list[str], list[str]]:
    lessons: list[str] = []
    actions: list[str] = []
    if any(message.spec.messageType == "ask-for-help" for message in messages):
        lessons.append("Help requests should be captured early and linked to the task/run they unblock.")
        actions.append("Confirm whether the requested help changed the implementation or review plan.")
    if any(message.spec.messageType == "review-request" for message in messages):
        lessons.append("Review requests should be part of handoff and closeout before context becomes stale.")
        actions.append("Include reviewer feedback in the retrospective before promoting durable memory.")
    if handoffs:
        lessons.append("Handoffs need explicit problem, known context, recommended next step, and memory pack boundaries.")
        actions.append("Check whether the handoff should create a temporary memory grant or a reviewed memory proposal.")
    if any(run.spec.status in {"FAILED", "STALLED", "RECOVERING", "INTERRUPTED"} for run in runs):
        lessons.append("Failed or stalled runs should be converted into recovery guidance before retry.")
        actions.append("Capture the verified recovery path as a pending procedural or mistake memory.")
    if runs and any(index.run_journals.get(run.object_id, "").strip() for run in runs):
        lessons.append("Run journals should be reviewed for reusable team practice before memory approval.")
    if not lessons:
        lessons.append("Collaboration and run records should be reviewed before creating team-level memory.")
        actions.append("Have the facilitator decide whether this evidence is strong enough for a retrospective.")
    return lessons, actions


def _suggest_facilitator(index: WorkspaceIndex) -> str | None:
    for preferred in ["manager", "architect"]:
        if preferred in index.members:
            return preferred
    for member_id, member in sorted(index.members.items()):
        if member.spec.kind == "human":
            return member_id
    return next(iter(sorted(index.members)), None)


def _brief(text: str, *, fallback: str, limit: int = 160) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("#").strip()
        if line:
            return line[:limit]
    return fallback[:limit]
