from __future__ import annotations

from pathlib import Path
from typing import Any

from aiteamos_schema import WorkspaceActionBoardRecord

from .knowledge_health import evaluate_knowledge_health
from .loader import WorkspaceIndex, load_workspace
from .memory_gate import memory_proposal_review_queue
from .run_plan import build_run_execution_plan
from .task_queue import task_execution_queue


LANES = ["closeout", "review", "recovery", "execute", "ingest", "launch", "memory", "setup", "attention", "knowledge", "done"]
LANE_ORDER = {lane: index for index, lane in enumerate(LANES)}


def workspace_action_board(workspace_or_index: str | Path | WorkspaceIndex) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    items: list[dict[str, Any]] = []
    _add_task_actions(index, items)
    _add_run_actions(index, items)
    _add_memory_actions(index, items)
    _add_knowledge_actions(index, items)

    summary = {lane: 0 for lane in LANES}
    for item in items:
        summary[item["lane"]] = summary.get(item["lane"], 0) + 1
    items.sort(key=lambda item: (item["priority"], LANE_ORDER.get(item["lane"], 99), item["targetType"], item["targetId"], item["id"]))
    return WorkspaceActionBoardRecord.model_validate({"summary": summary | {"total": len(items)}, "items": items}).model_dump(mode="json")


def _add_task_actions(index: WorkspaceIndex, items: list[dict[str, Any]]) -> None:
    queue = task_execution_queue(index)
    for item in queue["items"]:
        status = item["queueStatus"]
        if status == "ready-to-run":
            _append(
                items,
                lane="launch",
                priority=50,
                target_type="task",
                target_id=item["id"],
                action="create-run",
                title=item["title"],
                reason="Task is ready for a new run.",
                task=item["id"],
                member=item.get("assignedMember"),
                assignment=item.get("assignment"),
                status=item["taskStatus"],
                blockers=item["blockers"],
                warnings=[],
            )
        elif status == "needs-member":
            _append(
                items,
                lane="setup",
                priority=35,
                target_type="task",
                target_id=item["id"],
                action="assign-member",
                title=item["title"],
                reason="Task needs a valid assigned TeamMember before execution.",
                task=item["id"],
                member=item.get("assignedMember"),
                assignment=item.get("assignment"),
                status=item["taskStatus"],
                blockers=item["blockers"],
                warnings=[],
            )
        elif status == "needs-assignment":
            _append(
                items,
                lane="setup",
                priority=36,
                target_type="task",
                target_id=item["id"],
                action="bind-assignment",
                title=item["title"],
                reason="Task needs an active assignment context before execution.",
                task=item["id"],
                member=item.get("assignedMember"),
                assignment=item.get("assignment"),
                status=item["taskStatus"],
                blockers=item["blockers"],
                warnings=[],
            )
        elif status == "needs-execution-profile":
            _append(
                items,
                lane="setup",
                priority=38,
                target_type="task",
                target_id=item["id"],
                action="create-execution-profile",
                title=item["title"],
                reason="Assigned member needs an execution or collaboration profile before execution.",
                task=item["id"],
                member=item.get("assignedMember"),
                assignment=item.get("assignment"),
                status=item["taskStatus"],
                blockers=item["blockers"],
                warnings=[],
            )
        elif status == "needs-model":
            _append(
                items,
                lane="setup",
                priority=40,
                target_type="task",
                target_id=item["id"],
                action="bind-model",
                title=item["title"],
                reason="Managed execution needs a model profile.",
                task=item["id"],
                member=item.get("assignedMember"),
                assignment=item.get("assignment"),
                status=item["taskStatus"],
                blockers=item["blockers"],
                warnings=[],
            )
        elif status == "needs-attention" and not item.get("latestRun"):
            _append(
                items,
                lane="attention",
                priority=45,
                target_type="task",
                target_id=item["id"],
                action="inspect-task",
                title=item["title"],
                reason="Task needs attention but has no latest run to inspect.",
                task=item["id"],
                member=item.get("assignedMember"),
                assignment=item.get("assignment"),
                status=item["taskStatus"],
                blockers=item["blockers"],
                warnings=[],
            )


def _add_run_actions(index: WorkspaceIndex, items: list[dict[str, Any]]) -> None:
    for run_id in sorted(index.runs):
        run = index.runs[run_id]
        plan = build_run_execution_plan(index, run_id)
        actions = plan["actions"]
        base = {
            "task": run.spec.task,
            "run": run_id,
            "member": run.spec.member,
            "assignment": run.spec.assignment,
            "status": run.spec.status,
            "blockers": plan["blockers"],
            "warnings": plan["warnings"],
        }
        if actions.get("closeRun"):
            _append(
                items,
                lane="closeout",
                priority=5,
                target_type="run",
                target_id=run_id,
                action="close-run",
                title=f"Close {run_id}",
                reason="Run has approved human review and can mark the task DONE.",
                **base,
            )
        elif actions.get("inspectRecovery") or actions.get("buildRetryPlan"):
            _append(
                items,
                lane="recovery",
                priority=10,
                target_type="run",
                target_id=run_id,
                action="inspect-recovery",
                title=f"Recover {run_id}",
                reason=plan["recommendedActions"][0] if plan["recommendedActions"] else "Run needs recovery inspection.",
                **base,
            )
        elif actions.get("recordHumanReview"):
            _append(
                items,
                lane="review",
                priority=20,
                target_type="run",
                target_id=run_id,
                action="record-human-review",
                title=f"Review {run_id}",
                reason=plan["recommendedActions"][0] if plan["recommendedActions"] else "Run is waiting for human review.",
                **base,
            )
        elif actions.get("executeModel") or actions.get("startWorker"):
            _append(
                items,
                lane="execute",
                priority=25,
                target_type="run",
                target_id=run_id,
                action="start-managed-execution",
                title=f"Execute {run_id}",
                reason=plan["recommendedActions"][0] if plan["recommendedActions"] else "Managed run is ready to execute.",
                **base,
            )
        elif actions.get("ingestAssisted"):
            _append(
                items,
                lane="ingest",
                priority=30,
                target_type="run",
                target_id=run_id,
                action="ingest-assisted-output",
                title=f"Ingest {run_id}",
                reason=plan["recommendedActions"][0] if plan["recommendedActions"] else "Assisted run needs output ingest.",
                **base,
            )
        elif actions.get("rebuildContext"):
            _append(
                items,
                lane="attention",
                priority=42,
                target_type="run",
                target_id=run_id,
                action="rebuild-context",
                title=f"Rebuild context for {run_id}",
                reason="Run has no context capsule.",
                **base,
            )
        if actions.get("extractMemory"):
            _append(
                items,
                lane="memory",
                priority=55,
                target_type="run",
                target_id=run_id,
                action="extract-memory",
                title=f"Extract memory from {run_id}",
                reason="Run has journal/output evidence but no linked memory proposals.",
                **base,
            )
        if actions.get("refreshChecks"):
            _append(
                items,
                lane="review",
                priority=22,
                target_type="run",
                target_id=run_id,
                action="refresh-checks",
                title=f"Refresh checks for {run_id}",
                reason="Run has a pull request review target.",
                **base,
            )


def _add_memory_actions(index: WorkspaceIndex, items: list[dict[str, Any]]) -> None:
    queue = memory_proposal_review_queue(index)
    for item in queue["items"]:
        status = item["queueStatus"]
        if status in {"ready", "ready-with-warnings"}:
            _append(
                items,
                lane="memory",
                priority=32,
                target_type="memory-proposal",
                target_id=item["id"],
                action="approve-memory",
                title=item["title"],
                reason="Memory proposal is ready for human approval.",
                task=None,
                run=item.get("sourceRun"),
                member=item.get("member"),
                assignment=item.get("assignment"),
                status=item["proposalStatus"],
                blockers=[],
                warnings=[f"{item['warningCount']} warning(s)"] if item["warningCount"] else [],
            )
        elif status == "repairable":
            _append(
                items,
                lane="memory",
                priority=34,
                target_type="memory-proposal",
                target_id=item["id"],
                action="repair-memory",
                title=item["title"],
                reason="Memory proposal has safe repair hints before approval.",
                task=None,
                run=item.get("sourceRun"),
                member=item.get("member"),
                assignment=item.get("assignment"),
                status=item["proposalStatus"],
                blockers=[f"{item['blockerCount']} blocker(s)"],
                warnings=[],
            )


def _add_knowledge_actions(index: WorkspaceIndex, items: list[dict[str, Any]]) -> None:
    health = evaluate_knowledge_health(index)
    for position, issue in enumerate(health["issues"][:10]):
        severity = issue.get("severity") or "warning"
        priority = 18 if severity == "error" else 60
        _append(
            items,
            lane="knowledge",
            priority=priority + position,
            target_type="knowledge",
            target_id=str(issue.get("ref") or issue.get("kind") or position),
            action="inspect-knowledge-health",
            title=str(issue.get("message") or issue.get("kind") or "Knowledge health issue"),
            reason=str(issue.get("action") or "Inspect Knowledge Health."),
            task=None,
            run=None,
            member=None,
            assignment=None,
            status=severity,
            blockers=[str(issue.get("message"))] if severity == "error" else [],
            warnings=[str(issue.get("message"))] if severity != "error" else [],
        )


def _append(
    items: list[dict[str, Any]],
    *,
    lane: str,
    priority: int,
    target_type: str,
    target_id: str,
    action: str,
    title: str,
    reason: str,
    task: str | None,
    run: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    status: str | None = None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
) -> None:
    items.append(
        {
            "id": f"{target_type}:{target_id}:{action}",
            "lane": lane,
            "priority": priority,
            "targetType": target_type,
            "targetId": target_id,
            "task": task,
            "run": run,
            "member": member,
            "assignment": assignment,
            "status": status,
            "action": action,
            "title": title,
            "reason": reason,
            "blockers": blockers or [],
            "warnings": warnings or [],
        }
    )
