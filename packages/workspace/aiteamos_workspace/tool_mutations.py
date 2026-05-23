from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re

from aiteamos_schema import Handoff, MemberMessage

from .gitops import changed_paths_from_diff, diff_worktree, validate_patch_scope
from .io import write_text, write_yaml
from .loader import load_workspace, manifest_to_record
from .memory_gate import evaluate_memory_promotion_gate
from .mutations import (
    append_run_event,
    append_run_journal,
    ask_for_help,
    create_memory_grant,
    propose_memory,
    record_member_message,
    request_review,
    share_memory,
    update_run,
    update_task,
)
from .review_gate import evaluate_run_review_gate
from .worker_authorization import validate_managed_worktree


MAX_TOOL_TEXT_CHARS = 64 * 1024
REJECTED_EVENT_PATTERNS = [
    re.compile(r"(^|\.)(?:approve|approved|approval)(\.|$)", re.IGNORECASE),
    re.compile(r"(^|\.)closed?$", re.IGNORECASE),
    re.compile(r"(^|\.)merge", re.IGNORECASE),
    re.compile(r"(^|\.)policy(\.|$)", re.IGNORECASE),
]
SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)[A-Z0-9_]*=)([^\s]+)"
)
SECRET_FIELD_RE = re.compile(
    r'(?i)(["\']?(?:api[_-]?key|token|secret|password|credential)["\']?\s*[:=]\s*["\']?)([^"\'\s,}]+)'
)
SECRET_TOKEN_RE = re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b")


def record_journal_for_tool(workspace_path: str | Path, run_id: str, actor_member: str, entry: str) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    _require_run_actor(index, run_id, actor_member)
    content = _bounded_text(_redact_text(entry), "journal entry")
    path = append_run_journal(workspace_path, run_id, title=f"MCP Journal Entry by {actor_member}", body=content)
    event = append_run_event(
        workspace_path,
        run_id,
        {
            "type": "journal.recorded",
            "actorMember": actor_member,
            "path": path,
            "source": "mcp-tool",
        },
    )
    return {"tool": "record_journal", "run": run_id, "path": path, "event": event}


def record_event_for_tool(workspace_path: str | Path, run_id: str, actor_member: str, event: dict[str, Any]) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    _require_run_actor(index, run_id, actor_member)
    sanitized = _sanitize_event(event)
    recorded = append_run_event(workspace_path, run_id, {**sanitized, "actorMember": actor_member, "source": "mcp-tool"})
    return {"tool": "record_event", "run": run_id, "event": recorded}


def propose_memory_for_tool(
    workspace_path: str | Path,
    run_id: str,
    actor_member: str,
    *,
    content: str,
    title: str | None = None,
    kind: str = "procedural",
    confidence: float | None = None,
    evidence: list[str] | None = None,
    review_guidance: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    run = _require_run_actor(index, run_id, actor_member)
    proposal = propose_memory(
        workspace_path,
        project=run.spec.project,
        member=run.spec.member,
        assignment=run.spec.assignment,
        source_run=run_id,
        source_task=run.spec.task,
        title=title or f"MCP memory proposal from {run_id}",
        content=_bounded_text(_redact_text(content), "memory proposal"),
        kind=kind,
        confidence=confidence,
        evidence=evidence or [f"runs/{run_id}/{run.spec.journal or 'journal.md'}"],
        review_guidance=review_guidance or "Recorded through an MCP tool; human review is required before approval.",
    )
    event = append_run_event(
        workspace_path,
        run_id,
        {
            "type": "memory.proposed",
            "actorMember": actor_member,
            "proposal": proposal.object_id,
            "source": "mcp-tool",
        },
    )
    gate = evaluate_memory_promotion_gate(workspace_path, proposal.object_id)
    return {
        "tool": "propose_memory",
        "run": run_id,
        "proposal": manifest_to_record(proposal),
        "event": event,
        "promotionGate": gate,
    }


def record_member_message_for_tool(
    workspace_path: str | Path,
    from_member: str,
    body: str,
    *,
    to_members: list[str] | None = None,
    channel: str | None = None,
    message_type: str = "message",
    project: str | None = None,
    task: str | None = None,
    run_id: str | None = None,
    attachments: list[str] | None = None,
    priority: str = "normal",
    requested_response_by: str | None = None,
) -> dict[str, Any]:
    message = record_member_message(
        workspace_path,
        from_member=from_member,
        to_members=to_members,
        channel=channel,
        message_type=message_type,
        project=project,
        task=task,
        run=run_id,
        body=_bounded_text(_redact_text(body), "member message"),
        attachments=attachments,
        priority=priority,
        requested_response_by=requested_response_by,
        source="mcp-tool",
    )
    return {"tool": "record_member_message", "message": manifest_to_record(message)}


def record_handoff_for_tool(
    workspace_path: str | Path,
    task_id: str,
    from_member: str,
    to_member: str,
    problem: str,
    *,
    run_id: str | None = None,
    known_context: list[str] | None = None,
    recommended_next_step: str | None = None,
    shared_memory_pack: list[str] | None = None,
    ownership: str = "transfer",
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if task_id not in index.tasks:
        raise KeyError(f"unknown task {task_id}")
    _require_member(index, from_member, "from_member")
    _require_member(index, to_member, "to_member")

    task = index.tasks[task_id]
    if task.spec.assignedMember and task.spec.assignedMember != from_member:
        raise ValueError(f"task {task_id} is assigned to {task.spec.assignedMember}, not {from_member}")
    selected_run_id = run_id or _latest_run_for_task_member(index, task_id, from_member)
    if not selected_run_id:
        raise ValueError("handoff requires a run_id or an existing source run for the task/from_member")
    run = index.runs[selected_run_id]
    if run.spec.task != task_id:
        raise ValueError(f"run {selected_run_id} does not belong to task {task_id}")
    if run.spec.member != from_member:
        raise ValueError(f"run {selected_run_id} belongs to member {run.spec.member}, not {from_member}")

    handoff_id = _timestamped_id("HANDOFF")
    target_assignment = _single_active_assignment(index, to_member, task.spec.project)
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "Handoff",
        "metadata": {"id": handoff_id, "createdAt": _now()},
        "spec": {
            "fromMember": from_member,
            "toMember": to_member,
            "task": task_id,
            "run": selected_run_id,
            "project": task.spec.project,
            "sourceBranch": run.spec.branch.name if run.spec.branch else None,
            "targetBranch": None,
            "problem": _bounded_text(_redact_text(problem), "handoff problem"),
            "knownContext": known_context or [],
            "recommendedNextStep": _redact_text(recommended_next_step or "") or None,
            "sharedMemoryPack": shared_memory_pack or [],
            "ownership": ownership,
            "status": "requested",
        },
    }
    handoff = Handoff.model_validate(payload)
    write_yaml(index.workspace_root / "im" / "handoffs" / f"{handoff_id}.yaml", handoff.model_dump(mode="json", exclude_none=True))

    event = append_run_event(
        workspace_path,
        selected_run_id,
        {
            "type": "handoff.recorded",
            "actorMember": from_member,
            "handoff": handoff_id,
            "fromMember": from_member,
            "toMember": to_member,
            "taskId": task_id,
            "runId": selected_run_id,
            "ownership": ownership,
            "sharedMemoryPack": shared_memory_pack or [],
            "source": "mcp-tool",
        },
    )
    updated_task = None
    if ownership == "transfer":
        update = {"assignedMember": to_member}
        if target_assignment:
            update["assignment"] = target_assignment
        updated_task = update_task(workspace_path, task_id, update)

    return {
        "tool": "handoff",
        "task": task_id,
        "run": selected_run_id,
        "handoff": manifest_to_record(handoff),
        "event": event,
        "ownershipTransferred": ownership == "transfer",
        "updatedTask": manifest_to_record(updated_task) if updated_task else None,
    }


def grant_memory_for_tool(
    workspace_path: str | Path,
    grantee_member: str,
    *,
    grantor_member: str | None = None,
    task: str | None = None,
    run_id: str | None = None,
    stores: list[str] | None = None,
    entries: list[str] | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    grant = create_memory_grant(
        workspace_path,
        grantee_member=grantee_member,
        grantor_member=grantor_member,
        task=task,
        run=run_id,
        stores=stores,
        entries=entries,
        reason=_bounded_text(_redact_text(reason or ""), "memory grant reason") or None,
        expires_at=expires_at,
    )
    return {"tool": "grant_memory", "grant": manifest_to_record(grant)}


def share_memory_for_tool(
    workspace_path: str | Path,
    from_member: str,
    to_member: str,
    *,
    stores: list[str] | None = None,
    entries: list[str] | None = None,
    task: str | None = None,
    run_id: str | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
) -> dict[str, Any]:
    result = share_memory(
        workspace_path,
        from_member=from_member,
        to_member=to_member,
        stores=stores,
        entries=entries,
        task=task,
        run=run_id,
        reason=_bounded_text(_redact_text(reason or ""), "memory share reason") or None,
        expires_at=expires_at,
    )
    return {
        "tool": "share_memory",
        "grant": manifest_to_record(result["grant"]),
        "message": manifest_to_record(result["message"]),
    }


def ask_member_for_tool(
    workspace_path: str | Path,
    from_member: str,
    to_member: str,
    question: str,
    *,
    project: str | None = None,
    task: str | None = None,
    run_id: str | None = None,
    priority: str = "normal",
    requested_response_by: str | None = None,
    attachments: list[str] | None = None,
) -> dict[str, Any]:
    message = ask_for_help(
        workspace_path,
        from_member=from_member,
        to_members=[to_member],
        question=_bounded_text(_redact_text(question), "member question"),
        project=project,
        task=task,
        run=run_id,
        priority=priority,
        requested_response_by=requested_response_by,
        attachments=attachments,
        source="mcp-tool",
    )
    return {"tool": "ask_member", "message": manifest_to_record(message)}


def request_review_for_tool(
    workspace_path: str | Path,
    from_member: str,
    to_member: str,
    body: str,
    *,
    review_kind: str = "code",
    project: str | None = None,
    task: str | None = None,
    run_id: str | None = None,
    priority: str = "normal",
    requested_response_by: str | None = None,
    attachments: list[str] | None = None,
) -> dict[str, Any]:
    message = request_review(
        workspace_path,
        from_member=from_member,
        to_members=[to_member],
        body=_bounded_text(_redact_text(body), "review request"),
        review_kind=review_kind,
        project=project,
        task=task,
        run=run_id,
        priority=priority,
        requested_response_by=requested_response_by,
        attachments=attachments,
        source="mcp-tool",
    )
    return {"tool": "request_review", "message": manifest_to_record(message)}


def create_patch_for_tool(
    workspace_path: str | Path,
    run_id: str,
    actor_member: str,
    *,
    diff_patch: str | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    run = _require_run_actor(index, run_id, actor_member)
    diff_text = diff_patch if diff_patch is not None else _diff_from_recorded_worktree(index, run_id)
    diff_text = _bounded_text(diff_text.strip(), "diff patch")
    if not diff_text:
        raise ValueError("diff patch is empty")
    changed_paths = changed_paths_from_diff(diff_text)
    if not changed_paths:
        raise ValueError("diff patch has no changed paths")
    if _contains_secret_material(diff_text):
        raise ValueError("diff patch appears to contain secret material")
    violations = validate_patch_scope(index, run_id, diff_text)
    if violations:
        raise ValueError("patch scope violations: " + "; ".join(violations))

    relative_path = f"runs/{run_id}/diff.patch"
    write_text(index.workspace_root / relative_path, diff_text.rstrip() + "\n")
    outputs = _with_output(run.spec.outputs, {"type": "diff_patch", "path": relative_path, "source": "mcp-tool"})
    review_target = {
        "type": "diff_patch",
        "ref": relative_path,
        "description": "Diff patch recorded through an MCP tool for human review.",
    }
    update_run(workspace_path, run_id, {"status": "REVIEW", "outputs": outputs, "reviewTarget": review_target})
    event = append_run_event(
        workspace_path,
        run_id,
        {
            "type": "patch.created",
            "actorMember": actor_member,
            "path": relative_path,
            "changedPaths": changed_paths,
            "source": "mcp-tool",
        },
    )
    gate = evaluate_run_review_gate(workspace_path, run_id)
    return {"tool": "create_patch", "run": run_id, "path": relative_path, "event": event, "reviewGate": gate}


def _require_run_actor(index: Any, run_id: str, actor_member: str) -> Any:
    if not actor_member:
        raise ValueError("actor_member is required")
    _require_member(index, actor_member, "actor_member")
    if run_id not in index.runs:
        raise KeyError(f"unknown run {run_id}")
    run = index.runs[run_id]
    if run.spec.member != actor_member:
        raise ValueError(f"actor_member {actor_member} cannot mutate run {run_id} owned by member {run.spec.member}")
    return run


def _require_member(index: Any, member_id: str, label: str) -> None:
    if member_id not in index.members:
        raise KeyError(f"unknown {label} {member_id}")


def _sanitize_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    forbidden = {"seq", "ts", "run", "runId"}
    present = sorted(key for key in forbidden if key in event)
    if present:
        raise ValueError("event may not supply workspace-owned fields: " + ", ".join(present))
    event_type = str(event.get("type") or "").strip()
    if not event_type:
        raise ValueError("event.type is required")
    if any(pattern.search(event_type) for pattern in REJECTED_EVENT_PATTERNS):
        raise ValueError(f"event type {event_type} is not allowed through MCP record_event")
    return _sanitize_json(event)


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, str):
        return _bounded_text(_redact_text(value), "event string")
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value[:100]]
    if isinstance(value, dict):
        return {str(key): _sanitize_json(item) for key, item in value.items()}
    return value


def _bounded_text(text: str, label: str) -> str:
    if len(text) > MAX_TOOL_TEXT_CHARS:
        raise ValueError(f"{label} exceeds {MAX_TOOL_TEXT_CHARS} characters")
    return text


def _redact_text(text: str) -> str:
    redacted = SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", text)
    redacted = SECRET_FIELD_RE.sub(r"\1[REDACTED]", redacted)
    redacted = SECRET_TOKEN_RE.sub("sk-[REDACTED]", redacted)
    return redacted


def _contains_secret_material(diff_text: str) -> bool:
    added_lines = "\n".join(line[1:] for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    return _redact_text(added_lines) != added_lines


def _latest_run_for_task_member(index: Any, task_id: str, member: str) -> str | None:
    candidates = [run_id for run_id, run in index.runs.items() if run.spec.task == task_id and run.spec.member == member]
    return sorted(candidates)[-1] if candidates else None


def _single_active_assignment(index: Any, member_id: str, project: str) -> str | None:
    matches = [
        assignment.object_id
        for assignment in index.assignments.values()
        if assignment.spec.member == member_id and assignment.spec.project == project and assignment.spec.status == "active"
    ]
    return sorted(matches)[0] if len(matches) == 1 else None


def _diff_from_recorded_worktree(index: Any, run_id: str) -> str:
    run = index.runs[run_id]
    run_data = run.model_dump(mode="json").get("spec", {})
    worker = run_data.get("worker") if isinstance(run_data.get("worker"), dict) else {}
    worktree_value = run_data.get("worktree") or worker.get("worktree")
    violations = validate_managed_worktree(index, run_id, worktree_value)
    if violations:
        raise ValueError("unsafe recorded worktree: " + "; ".join(violations))
    if not worktree_value:
        raise ValueError("run has no recorded worktree and no diff_patch was supplied")
    return diff_worktree(Path(worktree_value).expanduser().resolve())


def _with_output(outputs: list[Any], output: dict[str, Any]) -> list[Any]:
    next_outputs = list(outputs)
    if output not in next_outputs:
        next_outputs.append(output)
    return next_outputs


def _timestamped_id(prefix: str) -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f")[:-3]
    return f"{prefix}-{stamp}"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
