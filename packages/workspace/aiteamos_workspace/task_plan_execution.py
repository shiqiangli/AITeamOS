from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .loader import WorkspaceIndex, load_workspace, manifest_to_record


COMPLETED_TASK_STATUSES = {"DONE", "COMPLETED", "CLOSED", "MERGED", "SUCCEEDED", "SUCCESS"}
DELETED_TASK_STATUSES = {"DELETED", "REMOVED", "CANCELLED", "CANCELED", "DROPPED"}
COMPLETED_RUN_STATUSES = {"DONE", "COMPLETED", "CLOSED", "SUCCEEDED", "SUCCESS", "PASSED"}


def task_plan_execution_view_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    task_plan: str | None = None,
) -> dict[str, Any]:
    index = _as_index(workspace_or_index)
    if task_plan is not None and task_plan not in index.task_plans:
        raise KeyError(f"unknown task plan {task_plan}")
    plan_ids = [task_plan] if task_plan is not None else sorted(index.task_plans)
    views = [_task_plan_execution_view(index, plan_id) for plan_id in plan_ids]
    drift_counts = Counter()
    for view in views:
        drift_counts.update(view["spec"]["summary"]["driftCounts"])
    return {
        "kind": "TaskPlanExecutionViewList",
        "summary": {
            "taskPlans": len(views),
            "subtasks": sum(view["spec"]["summary"]["subtasks"] for view in views),
            "linkedTasks": sum(view["spec"]["summary"]["linkedTasks"] for view in views),
            "linkedRuns": sum(view["spec"]["summary"]["linkedRuns"] for view in views),
            "linkedReviews": sum(view["spec"]["summary"]["linkedReviews"] for view in views),
            "linkedMemoryProposals": sum(view["spec"]["summary"]["linkedMemoryProposals"] for view in views),
            "driftCounts": dict(sorted(drift_counts.items())),
        },
        "taskPlans": views,
    }


def task_plan_execution_view(
    workspace_or_index: str | Path | WorkspaceIndex,
    task_plan_id: str,
) -> dict[str, Any]:
    index = _as_index(workspace_or_index)
    if task_plan_id not in index.task_plans:
        raise KeyError(f"unknown task plan {task_plan_id}")
    return _task_plan_execution_view(index, task_plan_id)


def _task_plan_execution_view(index: WorkspaceIndex, task_plan_id: str) -> dict[str, Any]:
    plan = index.task_plans[task_plan_id]
    plan_record = manifest_to_record(plan)
    plan_spec = _spec(plan_record)
    plan_review_gates = _string_list(plan_spec.get("reviewGates"))
    subtask_rows = []
    all_task_ids: set[str] = set()
    all_run_ids: set[str] = set()
    all_review_ids: set[str] = set()
    all_memory_ids: set[str] = set()
    drift_counts = Counter()

    for offset, subtask in enumerate(plan_spec.get("subtasks") if isinstance(plan_spec.get("subtasks"), list) else []):
        if not isinstance(subtask, dict):
            continue
        task_records = _tasks_for_subtask(index, task_plan_id, offset, subtask)
        run_records = _runs_for_subtask(index, task_plan_id, offset, task_records)
        review_records = _reviews_for_subtask(index, task_records, run_records)
        memory_records = _memory_proposals_for_subtask(index, task_records, run_records)
        task_ids = [record["id"] for record in task_records]
        run_ids = [record["id"] for record in run_records]
        review_ids = [record["id"] for record in review_records]
        memory_ids = [record["id"] for record in memory_records]
        all_task_ids.update(task_ids)
        all_run_ids.update(run_ids)
        all_review_ids.update(review_ids)
        all_memory_ids.update(memory_ids)

        planned_acceptance = _string_list(subtask.get("acceptance"))
        actual_acceptance = _actual_acceptance(task_records, run_records, review_records)
        covered_acceptance = [item for item in planned_acceptance if item in actual_acceptance]
        actual_state = _actual_state(task_records, run_records)
        drift = "split" if len(task_records) > 1 else actual_state
        drift_counts[drift] += 1
        planned_gates = _string_list(subtask.get("reviewGates")) + plan_review_gates
        subtask_rows.append(
            {
                "index": offset,
                "title": str(subtask.get("title") or ""),
                "assignedMember": subtask.get("assignedMember"),
                "assignment": subtask.get("assignment"),
                "priority": subtask.get("priority", "normal"),
                "plannedAcceptance": planned_acceptance,
                "plannedRisks": _string_list(subtask.get("risks")),
                "plannedReviewGates": planned_gates,
                "actualState": actual_state,
                "drift": drift,
                "tasks": task_ids,
                "runs": run_ids,
                "reviews": review_ids,
                "memoryProposals": memory_ids,
                "acceptanceCoverage": {
                    "planned": len(planned_acceptance),
                    "covered": len(covered_acceptance),
                    "rate": 1.0 if not planned_acceptance else len(covered_acceptance) / len(planned_acceptance),
                    "coveredItems": covered_acceptance,
                    "missingItems": [item for item in planned_acceptance if item not in actual_acceptance],
                },
                "reviewGateCoverage": {
                    "planned": len(planned_gates),
                    "reviews": len(review_ids),
                    "verdicts": [
                        _spec(record).get("verdict")
                        for record in review_records
                        if _spec(record).get("verdict") is not None
                    ],
                },
                "evidence": [
                    *[f".aiteamos/tasks/{task_id}.yaml" for task_id in task_ids],
                    *[f".aiteamos/runs/{run_id}/run.yaml" for run_id in run_ids],
                    *[f".aiteamos/reviews/{review_id}.yaml" for review_id in review_ids],
                    *[f".aiteamos/memory/proposals/{proposal_id}.yaml" for proposal_id in memory_ids],
                ],
            }
        )

    unmatched = _unmatched_source_plan_records(index, task_plan_id, all_task_ids, all_run_ids, all_review_ids, all_memory_ids)
    return {
        "id": f"{task_plan_id}:execution",
        "kind": "TaskPlanExecutionView",
        "spec": {
            "taskPlan": task_plan_id,
            "project": plan_spec.get("project") or index.project.object_id,
            "status": plan_spec.get("status"),
            "goal": plan_spec.get("goal"),
            "sourceTask": plan_spec.get("sourceTask"),
            "createdByMember": plan_spec.get("createdByMember"),
            "subtasks": subtask_rows,
            "unmatched": unmatched,
            "summary": {
                "subtasks": len(subtask_rows),
                "linkedTasks": len(all_task_ids),
                "linkedRuns": len(all_run_ids),
                "linkedReviews": len(all_review_ids),
                "linkedMemoryProposals": len(all_memory_ids),
                "completedSubtasks": sum(1 for row in subtask_rows if row["actualState"] == "completed"),
                "completionRate": 1.0
                if not subtask_rows
                else sum(1 for row in subtask_rows if row["actualState"] == "completed") / len(subtask_rows),
                "driftCounts": dict(sorted(drift_counts.items())),
            },
        },
    }


def _as_index(workspace_or_index: str | Path | WorkspaceIndex) -> WorkspaceIndex:
    if isinstance(workspace_or_index, WorkspaceIndex):
        return workspace_or_index
    return load_workspace(workspace_or_index)


def _tasks_for_subtask(
    index: WorkspaceIndex,
    task_plan_id: str,
    subtask_index: int,
    subtask: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    subtask_key = _subtask_match_key(subtask)
    for task in index.tasks.values():
        record = manifest_to_record(task)
        spec = _spec(record)
        if _source_task_plan(spec) != task_plan_id:
            if not subtask_key or _subtask_match_key(spec) != subtask_key:
                continue
        elif not _matches_subtask(spec.get("sourceTaskPlanSubtask"), subtask_index) and _subtask_match_key(spec) != subtask_key:
            continue
        rows.append(record)
    return sorted(rows, key=lambda record: record["id"])


def _runs_for_subtask(
    index: WorkspaceIndex,
    task_plan_id: str,
    subtask_index: int,
    task_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    task_ids = {record["id"] for record in task_records}
    rows = []
    for run in index.runs.values():
        record = manifest_to_record(run)
        spec = _spec(record)
        source_plan = _source_task_plan(spec)
        if spec.get("task") in task_ids:
            rows.append(record)
            continue
        if source_plan == task_plan_id and _matches_subtask(spec.get("sourceTaskPlanSubtask"), subtask_index):
            rows.append(record)
    return sorted(_unique_records(rows), key=lambda record: record["id"])


def _reviews_for_subtask(
    index: WorkspaceIndex,
    task_records: list[dict[str, Any]],
    run_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    task_ids = {record["id"] for record in task_records}
    run_ids = {record["id"] for record in run_records}
    review_ids = set()
    for task in task_records:
        review_ids.update(_string_list(_spec(task).get("relatedReviews")))
    for run in run_records:
        review_ids.update(_string_list(_spec(run).get("reviews")))
    rows = []
    for review in index.reviews.values():
        record = manifest_to_record(review)
        spec = _spec(record)
        if record["id"] in review_ids or spec.get("task") in task_ids or spec.get("run") in run_ids:
            rows.append(record)
    return sorted(_unique_records(rows), key=lambda record: record["id"])


def _memory_proposals_for_subtask(
    index: WorkspaceIndex,
    task_records: list[dict[str, Any]],
    run_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    task_ids = {record["id"] for record in task_records}
    run_ids = {record["id"] for record in run_records}
    proposal_ids = set()
    for run in run_records:
        proposal_ids.update(_string_list(_spec(run).get("memoryProposals")))
    rows = []
    for proposal in index.memory_proposals.values():
        record = manifest_to_record(proposal)
        spec = _spec(record)
        if record["id"] in proposal_ids or spec.get("sourceTask") in task_ids or spec.get("sourceRun") in run_ids:
            rows.append(record)
    return sorted(_unique_records(rows), key=lambda record: record["id"])


def _unmatched_source_plan_records(
    index: WorkspaceIndex,
    task_plan_id: str,
    task_ids: set[str],
    run_ids: set[str],
    review_ids: set[str],
    memory_ids: set[str],
) -> dict[str, list[str]]:
    source_tasks = [
        task.object_id
        for task in index.tasks.values()
        if task.object_id not in task_ids and _source_task_plan(manifest_to_record(task).get("spec", {})) == task_plan_id
    ]
    source_runs = [
        run.object_id
        for run in index.runs.values()
        if run.object_id not in run_ids and _source_task_plan(manifest_to_record(run).get("spec", {})) == task_plan_id
    ]
    source_review_ids = []
    source_memory_ids = []
    source_task_set = set(source_tasks)
    source_run_set = set(source_runs)
    for review in index.reviews.values():
        spec = _spec(manifest_to_record(review))
        if review.object_id not in review_ids and (spec.get("task") in source_task_set or spec.get("run") in source_run_set):
            source_review_ids.append(review.object_id)
    for proposal in index.memory_proposals.values():
        spec = _spec(manifest_to_record(proposal))
        if proposal.object_id not in memory_ids and (spec.get("sourceTask") in source_task_set or spec.get("sourceRun") in source_run_set):
            source_memory_ids.append(proposal.object_id)
    return {
        "tasks": sorted(source_tasks),
        "runs": sorted(source_runs),
        "reviews": sorted(source_review_ids),
        "memoryProposals": sorted(source_memory_ids),
    }


def _actual_acceptance(
    task_records: list[dict[str, Any]],
    run_records: list[dict[str, Any]],
    review_records: list[dict[str, Any]],
) -> set[str]:
    values: set[str] = set()
    for record in task_records:
        values.update(_string_list(_spec(record).get("acceptance")))
    for record in run_records:
        spec = _spec(record)
        for output in spec.get("outputs", []):
            if isinstance(output, str):
                values.add(output)
            elif isinstance(output, dict):
                values.update(_string_list(output.get("acceptance")))
                values.update(_string_list(output.get("acceptanceEvidence")))
    for record in review_records:
        for finding in _spec(record).get("findings", []):
            if isinstance(finding, dict):
                values.update(_string_list(finding.get("action")))
                values.update(_string_list(finding.get("summary")))
    return values


def _actual_state(task_records: list[dict[str, Any]], run_records: list[dict[str, Any]]) -> str:
    if not task_records and not run_records:
        return "deferred"
    task_statuses = {_status(_spec(record).get("status")) for record in task_records}
    run_statuses = {_status(_spec(record).get("status")) for record in run_records}
    if task_statuses and task_statuses.issubset(DELETED_TASK_STATUSES):
        return "deleted"
    if task_records and task_statuses.issubset(COMPLETED_TASK_STATUSES):
        if not run_statuses or run_statuses.issubset(COMPLETED_RUN_STATUSES):
            return "completed"
    return "in-progress"


def _source_task_plan(spec: dict[str, Any]) -> str | None:
    remediation = spec.get("connectorRemediation") if isinstance(spec.get("connectorRemediation"), dict) else {}
    for key in ("sourceTaskPlan", "taskPlan", "taskPlanId", "createdFromTaskPlan", "acceptedTaskPlan"):
        value = spec.get(key)
        if value:
            return str(value)
    for key in ("sourceTaskPlan", "taskPlan"):
        value = remediation.get(key)
        if value:
            return str(value)
    return None


def _matches_subtask(value: Any, offset: int) -> bool:
    if value is None:
        return False
    if isinstance(value, int):
        return value == offset
    text = str(value).strip()
    return text == str(offset) or text == f"subtask-{offset}" or text == f"subtask-{offset + 1}"


def _subtask_match_key(record: dict[str, Any]) -> str:
    title = str(record.get("title") or "").strip().lower()
    assigned_member = str(record.get("assignedMember") or "").strip()
    assignment = str(record.get("assignment") or "").strip()
    if not title or not assigned_member or not assignment:
        return ""
    return f"{title}|{assigned_member}|{assignment}"


def _unique_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for record in records:
        record_id = record.get("id")
        if not record_id or record_id in seen:
            continue
        seen.add(record_id)
        result.append(record)
    return result


def _spec(record: dict[str, Any]) -> dict[str, Any]:
    spec = record.get("spec")
    return spec if isinstance(spec, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _status(value: Any) -> str:
    return str(value or "").strip().upper()
