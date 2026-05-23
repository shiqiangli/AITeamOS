from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aiteamos_schema import MemberMessage, Task, TaskPlan, timestamp_task_id

from .audit import decision_audit_record, latest_decision_audit
from .io import read_yaml, write_yaml
from .launch_plan import build_run_launch_plan
from .loader import WorkspaceIndex, load_workspace, manifest_to_record
from .mutations import create_permission_request, create_run, record_member_message, resolve_member_message
from .permissions import explain_effective_permissions
from .run_plan import build_run_execution_plan
from .task_queue import task_execution_queue
from .worker_authorization import evaluate_worker_authorization
from .worker_readiness import evaluate_model_execution_readiness, evaluate_worker_readiness


def connector_operations_overview(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    lifecycle: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    if connector is not None and connector not in index.connectors:
        has_delivery = any(delivery.spec.connector == connector for delivery in index.automation_provider_deliveries.values())
        has_health = any(check.spec.connector == connector for check in index.connector_health_checks.values())
        if not has_delivery and not has_health:
            raise KeyError(f"unknown connector {connector}")
    if assignment is not None:
        selected_assignment = index.assignments.get(assignment)
        if selected_assignment is None:
            raise KeyError(f"unknown assignment {assignment}")
        if project is not None and project != selected_assignment.spec.project:
            raise ValueError(f"assignment {assignment} belongs to project {selected_assignment.spec.project}, not {project}")
        if member is not None and member != selected_assignment.spec.member:
            raise ValueError(f"assignment {assignment} belongs to member {selected_assignment.spec.member}, not {member}")
        project = selected_assignment.spec.project
        member = selected_assignment.spec.member
    if project is not None and project != index.project.object_id:
        raise KeyError(f"unknown project {project}")
    if member is not None and member not in index.members:
        raise KeyError(f"unknown member {member}")
    if lifecycle is not None and lifecycle not in {"active", "archived"}:
        raise ValueError("lifecycle must be active or archived")

    connectors = [
        item
        for item in index.connectors.values()
        if _connector_matches_scope(item, connector=connector, project=project, member=member)
    ]
    health_checks = [
        item
        for item in index.connector_health_checks.values()
        if _health_check_matches_scope(index, item, connector=connector, project=project, member=member)
        and (lifecycle is None or item.spec.lifecycle == lifecycle)
    ]
    provider_deliveries = [
        item
        for item in index.automation_provider_deliveries.values()
        if _provider_delivery_matches_scope(index, item, connector=connector, project=project, member=member)
        and (lifecycle is None or item.spec.lifecycle == lifecycle)
    ]

    by_connector: dict[str, dict[str, Any]] = {}
    for item in connectors:
        by_connector[item.object_id] = _connector_row(
            item.object_id,
            provider=item.spec.provider,
            connector_type=item.spec.connectorType,
            projects=item.spec.projects,
            owner_member=item.spec.ownerMember,
        )
    for check in health_checks:
        row = by_connector.setdefault(
            check.spec.connector,
            _connector_row(
                check.spec.connector,
                provider=check.spec.provider,
                connector_type=check.spec.connectorType,
                projects=[check.spec.project] if check.spec.project else [],
                owner_member=_connector_owner(index, check.spec.connector),
            ),
        )
        spec = row["spec"]
        spec["healthChecks"] += 1
        spec[f"{check.spec.lifecycle}HealthChecks"] += 1
        spec[f"{check.spec.status}HealthChecks"] = int(spec.get(f"{check.spec.status}HealthChecks", 0)) + 1
        spec["warnings"] += len(check.spec.warnings)
        spec["blockers"] += len(check.spec.blockers)
        latest = spec.get("latestHealthCheck")
        if not latest or _sort_timestamp(check.spec.checkedAt, check.metadata.createdAt) >= str(latest.get("sortKey", "")):
            spec["latestHealthCheck"] = {
                "id": check.object_id,
                "status": check.spec.status,
                "readiness": check.spec.readiness,
                "checkedAt": check.spec.checkedAt,
                "lifecycle": check.spec.lifecycle,
                "sortKey": _sort_timestamp(check.spec.checkedAt, check.metadata.createdAt),
            }
    for delivery in provider_deliveries:
        connector_id = delivery.spec.connector or "unbound-provider-deliveries"
        linked_automation = index.automations.get(delivery.spec.automation)
        row = by_connector.setdefault(
            connector_id,
            _connector_row(
                connector_id,
                provider=delivery.spec.provider,
                connector_type="other",
                projects=[delivery.spec.project] if delivery.spec.project else [],
                owner_member=_connector_owner(index, delivery.spec.connector),
            ),
        )
        spec = row["spec"]
        if linked_automation is not None:
            _append_unique(spec, "automationOwnerMembers", linked_automation.spec.ownerMember)
            _append_unique(spec, "automationServiceMembers", linked_automation.spec.serviceMember)
        spec["providerDeliveries"] += 1
        spec[f"{delivery.spec.lifecycle}ProviderDeliveries"] += 1
        spec[f"{delivery.spec.admissionStatus}ProviderDeliveries"] = int(spec.get(f"{delivery.spec.admissionStatus}ProviderDeliveries", 0)) + 1
        spec[f"{delivery.spec.replayStatus}ReplayDeliveries"] = int(spec.get(f"{delivery.spec.replayStatus}ReplayDeliveries", 0)) + 1
        spec["warnings"] += len(delivery.spec.warnings)
        spec["blockers"] += len(delivery.spec.blockers)
        latest = spec.get("latestProviderDelivery")
        if not latest or _sort_timestamp(delivery.spec.lastSeenAt, delivery.spec.receivedAt, delivery.metadata.createdAt) >= str(latest.get("sortKey", "")):
            spec["latestProviderDelivery"] = {
                "id": delivery.object_id,
                "admissionStatus": delivery.spec.admissionStatus,
                "replayStatus": delivery.spec.replayStatus,
                "lastSeenAt": delivery.spec.lastSeenAt,
                "lifecycle": delivery.spec.lifecycle,
                "sortKey": _sort_timestamp(delivery.spec.lastSeenAt, delivery.spec.receivedAt, delivery.metadata.createdAt),
            }

    for row in by_connector.values():
        _strip_internal_sort_keys(row["spec"].get("latestHealthCheck"))
        _strip_internal_sort_keys(row["spec"].get("latestProviderDelivery"))

    health_records = [_with_latest_audit(item) for item in sorted(health_checks, key=lambda value: value.object_id)]
    delivery_records = [_with_latest_audit(item) for item in sorted(provider_deliveries, key=lambda value: value.object_id)]
    by_connector_records = sorted(by_connector.values(), key=lambda value: value["id"])
    return {
        "filters": {
            "connector": connector,
            "project": project,
            "member": member,
            "assignment": assignment,
            "lifecycle": lifecycle,
        },
        "summary": _summary(len(by_connector_records), health_checks, provider_deliveries),
        "byConnector": by_connector_records,
        "healthChecks": health_records,
        "providerDeliveries": delivery_records,
    }


def connector_failure_reminder_candidates(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    lifecycle: str | None = "active",
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    filters = _normalize_scope(index, connector=connector, project=project, member=member, assignment=assignment, lifecycle=lifecycle)
    candidates: list[dict[str, Any]] = []
    for check in sorted(index.connector_health_checks.values(), key=lambda value: value.object_id):
        if not _health_check_matches_scope(index, check, connector=filters["connector"], project=filters["project"], member=filters["member"]):
            continue
        if filters["lifecycle"] is not None and check.spec.lifecycle != filters["lifecycle"]:
            continue
        if not _health_check_needs_reminder(check):
            continue
        candidates.append(_health_check_reminder_candidate(index, check))
    for delivery in sorted(index.automation_provider_deliveries.values(), key=lambda value: value.object_id):
        if not _provider_delivery_matches_scope(index, delivery, connector=filters["connector"], project=filters["project"], member=filters["member"]):
            continue
        if filters["lifecycle"] is not None and delivery.spec.lifecycle != filters["lifecycle"]:
            continue
        if not _provider_delivery_needs_reminder(delivery):
            continue
        candidates.append(_provider_delivery_reminder_candidate(index, delivery))

    for candidate in candidates:
        existing = _existing_open_reminder(index, str(candidate["spec"]["dedupeKey"]))
        candidate["spec"]["existingMessage"] = existing
        candidate["spec"]["routable"] = bool(candidate["spec"]["toMembers"]) and existing is None

    return {
        "filters": filters,
        "summary": _reminder_summary(candidates),
        "candidates": candidates,
    }


def route_connector_failure_reminders(
    workspace_path: str | Path,
    *,
    actor_member: str,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    lifecycle: str | None = "active",
    dry_run: bool = True,
    max_messages: int | None = None,
    throttle_minutes: int | None = None,
    audit_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "service"}:
        raise ValueError("connector failure reminders require a human or service actor member")
    candidate_set = connector_failure_reminder_candidates(
        index,
        connector=connector,
        project=project,
        member=member,
        assignment=assignment,
        lifecycle=lifecycle,
    )
    created: list[dict[str, Any]] = []
    created_by_connector: dict[str, str] = {}
    skipped: list[dict[str, Any]] = []
    for candidate in candidate_set["candidates"]:
        spec = candidate["spec"]
        if spec["existingMessage"]:
            skipped.append({"candidate": candidate["id"], "reason": "existing-open-message", "message": spec["existingMessage"]})
            continue
        if not spec["toMembers"]:
            skipped.append({"candidate": candidate["id"], "reason": "no-routable-member"})
            continue
        if dry_run:
            skipped.append({"candidate": candidate["id"], "reason": "dry-run"})
            continue
        if max_messages is not None and len(created) >= max_messages:
            skipped.append({"candidate": candidate["id"], "reason": "max-messages-per-run"})
            continue
        connector_id = str(spec.get("connector") or "")
        throttled_by = created_by_connector.get(connector_id) if throttle_minutes and throttle_minutes > 0 else None
        throttled_by = throttled_by or _recent_connector_reminder(index, spec.get("connector"), throttle_minutes)
        if throttled_by:
            skipped.append({"candidate": candidate["id"], "reason": "throttled", "message": throttled_by})
            continue
        message = record_member_message(
            workspace_path,
            from_member=actor_member,
            to_members=list(spec["toMembers"]),
            message_type="message",
            body=str(spec["body"]),
            project=spec.get("project") or index.project.object_id,
            attachments=list(spec["attachments"]),
            priority=str(spec["priority"]),
            audit={
                "source": "connector-failure-reminder",
                "connectorReminderDedupeKey": spec["dedupeKey"],
                "connector": spec["connector"],
                "evidenceKind": spec["evidenceKind"],
                "evidenceId": spec["evidenceId"],
                "severity": spec["severity"],
                **(audit_context or {}),
            },
            source="connector-failure-reminder",
        )
        created.append(manifest_to_record(message))
        if connector_id:
            created_by_connector[connector_id] = message.object_id
    return {
        "dryRun": dry_run,
        "filters": candidate_set["filters"],
        "summary": {
            **candidate_set["summary"],
            "createdMessages": len(created),
            "skipped": len(skipped),
            "throttled": sum(1 for item in skipped if item["reason"] == "throttled"),
            "maxMessagesSkipped": sum(1 for item in skipped if item["reason"] == "max-messages-per-run"),
        },
        "createdMessages": created,
        "skipped": skipped,
        "candidates": candidate_set["candidates"],
    }


def connector_failure_escalation_candidates(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    lifecycle: str | None = "active",
    min_evidence: int = 2,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    min_evidence = max(1, int(min_evidence))
    reminder_set = connector_failure_reminder_candidates(
        index,
        connector=connector,
        project=project,
        member=member,
        assignment=assignment,
        lifecycle=lifecycle,
    )
    grouped: dict[str, dict[str, Any]] = {}
    for reminder in reminder_set["candidates"]:
        spec = reminder["spec"]
        connector_id = str(spec.get("connector") or "unbound-provider-deliveries")
        project_id = str(spec.get("project") or _connector_project(index, spec.get("connector")) or index.project.object_id)
        group_key = f"{project_id}:{connector_id}"
        group = grouped.setdefault(
            group_key,
            _escalation_candidate(
                candidate_id=f"connector-escalation:{project_id}:{connector_id}",
                connector=connector_id,
                project=project_id,
                min_evidence=min_evidence,
            ),
        )
        group_spec = group["spec"]
        group_spec["evidenceCount"] += 1
        group_spec["severity"] = _max_severity(str(group_spec["severity"]), str(spec["severity"]))
        group_spec["priority"] = "urgent" if group_spec["severity"] == "blocked" else "high"
        _append_unique(group_spec, "toMembers", from_value_list=spec.get("toMembers"))
        _append_unique(group_spec, "evidenceIds", spec.get("evidenceId"))
        _append_unique(group_spec, "evidenceKinds", spec.get("evidenceKind"))
        _append_unique(group_spec, "attachments", spec.get("evidenceId"))
        _append_unique(group_spec, "reminderCandidates", reminder["id"])
        if spec.get("existingMessage"):
            _append_unique(group_spec, "existingReminderMessages", spec.get("existingMessage"))
        if spec.get("reason"):
            _append_unique(group_spec, "reasons", spec.get("reason"))

    candidates = sorted(grouped.values(), key=lambda value: value["id"])
    for candidate in candidates:
        spec = candidate["spec"]
        existing = _existing_open_escalation(index, str(spec["dedupeKey"]))
        resolution = _resolved_escalation_explanation(index, str(spec["dedupeKey"]), spec["evidenceIds"])
        if resolution is not None:
            spec.update(resolution)
        resolved = spec["latestResolvedReviewRequest"] if spec["resolutionCoversCurrentEvidence"] else None
        spec["existingReviewRequest"] = existing
        spec["resolvedReviewRequest"] = resolved
        spec["suppressedByResolution"] = resolved is not None
        spec["body"] = _escalation_body(spec)
        spec["routable"] = bool(spec["toMembers"]) and existing is None and resolved is None and int(spec["evidenceCount"]) >= min_evidence
        if existing:
            spec["notRoutableReason"] = "existing-open-review-request"
        elif resolved:
            spec["notRoutableReason"] = "resolved-evidence-reviewed"
        elif not spec["toMembers"]:
            spec["notRoutableReason"] = "no-routable-member"
        elif int(spec["evidenceCount"]) < min_evidence:
            spec["notRoutableReason"] = "below-evidence-threshold"
        else:
            spec["notRoutableReason"] = None

    return {
        "filters": {**reminder_set["filters"], "minEvidence": min_evidence},
        "summary": _escalation_summary(candidates),
        "candidates": candidates,
    }


def connector_remediation_suggestions(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    lifecycle: str | None = "active",
    min_evidence: int = 2,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    escalation_set = connector_failure_escalation_candidates(
        index,
        connector=connector,
        project=project,
        member=member,
        assignment=assignment,
        lifecycle=lifecycle,
        min_evidence=min_evidence,
    )
    suggestions = [
        suggestion
        for candidate in escalation_set["candidates"]
        if (suggestion := _remediation_suggestion(index, candidate)) is not None
    ]
    return {
        "filters": escalation_set["filters"],
        "summary": {
            "candidates": escalation_set["summary"]["candidates"],
            "suggestions": len(suggestions),
            "readyForTaskPlan": sum(1 for item in suggestions if item["spec"]["readyForTaskPlan"]),
            "blocked": sum(1 for item in suggestions if item["spec"]["blockers"]),
            "fromOpenReviewRequests": sum(1 for item in suggestions if item["spec"].get("sourceReviewRequest")),
            "fromUnreviewedEvidence": sum(1 for item in suggestions if item["spec"].get("unreviewedEvidenceIds")),
        },
        "suggestions": suggestions,
    }


def connector_remediation_task_plan_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    filters = _normalize_scope(index, connector=None, project=project, member=member, assignment=assignment, lifecycle=None)
    if connector is not None and not _connector_remediation_connector_known(index, connector):
        raise KeyError(f"unknown connector {connector}")
    if status is not None and status not in {"draft", "accepted", "rejected", "superseded"}:
        raise ValueError("status must be draft, accepted, rejected, or superseded")

    rows: list[dict[str, Any]] = []
    for plan in sorted(index.task_plans.values(), key=lambda item: item.object_id):
        record = _connector_remediation_task_plan_record(index, plan)
        if record is None:
            continue
        if not _connector_remediation_task_plan_matches(
            record,
            connector=connector,
            project=filters["project"],
            member=filters["member"],
            assignment=filters["assignment"],
            status=status,
        ):
            continue
        rows.append(record)

    return {
        "filters": {
            "connector": connector,
            "project": filters["project"],
            "member": filters["member"],
            "assignment": filters["assignment"],
            "status": status,
        },
        "summary": _connector_remediation_task_plan_summary(rows),
        "taskPlans": rows,
    }


def connector_remediation_materialized_task_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    status: str | None = None,
    task_plan: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    filters = _normalize_scope(index, connector=None, project=project, member=member, assignment=assignment, lifecycle=None)
    if connector is not None and not _connector_remediation_connector_known(index, connector):
        raise KeyError(f"unknown connector {connector}")
    if task_plan is not None and task_plan not in index.task_plans:
        has_materialized_task = any(_task_connector_remediation(task).get("taskPlan") == task_plan for task in index.tasks.values())
        if not has_materialized_task:
            raise KeyError(f"unknown task plan {task_plan}")

    queue = task_execution_queue(index)
    queue_by_task = {
        str(item.get("id")): item
        for item in queue.get("items", [])
        if isinstance(item, dict) and item.get("id")
    }
    rows: list[dict[str, Any]] = []
    for task in sorted(index.tasks.values(), key=lambda item: item.object_id):
        record = _connector_remediation_materialized_task_record(index, task, queue_by_task.get(task.object_id))
        if record is None:
            continue
        if not _connector_remediation_materialized_task_matches(
            record,
            connector=connector,
            project=filters["project"],
            member=filters["member"],
            assignment=filters["assignment"],
            status=status,
            task_plan=task_plan,
        ):
            continue
        rows.append(record)

    return {
        "filters": {
            "connector": connector,
            "project": filters["project"],
            "member": filters["member"],
            "assignment": filters["assignment"],
            "status": status,
            "taskPlan": task_plan,
        },
        "summary": _connector_remediation_materialized_task_summary(rows),
        "tasks": rows,
    }


def connector_remediation_run_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    status: str | None = None,
    task_plan: str | None = None,
    task: str | None = None,
) -> dict[str, Any]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    filters = _normalize_scope(index, connector=None, project=project, member=member, assignment=assignment, lifecycle=None)
    if connector is not None and not _connector_remediation_connector_known(index, connector):
        raise KeyError(f"unknown connector {connector}")
    if task_plan is not None and task_plan not in index.task_plans:
        has_run = any(_run_connector_remediation(run).get("taskPlan") == task_plan for run in index.runs.values())
        if not has_run:
            raise KeyError(f"unknown task plan {task_plan}")
    if task is not None and task not in index.tasks:
        has_run = any(_run_connector_remediation(run).get("sourceTask") == task for run in index.runs.values())
        if not has_run:
            raise KeyError(f"unknown task {task}")

    rows: list[dict[str, Any]] = []
    for run in sorted(index.runs.values(), key=lambda item: item.object_id):
        record = _connector_remediation_run_record(index, run)
        if record is None:
            continue
        if not _connector_remediation_run_matches(
            record,
            connector=connector,
            project=filters["project"],
            member=filters["member"],
            assignment=filters["assignment"],
            status=status,
            task_plan=task_plan,
            task=task,
        ):
            continue
        rows.append(record)

    return {
        "filters": {
            "connector": connector,
            "project": filters["project"],
            "member": filters["member"],
            "assignment": filters["assignment"],
            "status": status,
            "taskPlan": task_plan,
            "task": task,
        },
        "summary": _connector_remediation_run_summary(rows),
        "runs": rows,
    }


def request_connector_remediation_run_permission(
    workspace_path: str | Path,
    run_id: str,
    *,
    actor_member: str,
    action_canonical: str | None = None,
    action_index: int | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "service"}:
        raise ValueError("connector remediation permission requests require a human or governed service actor member")
    run = index.runs.get(run_id)
    if run is None:
        raise KeyError(f"unknown run {run_id}")
    run_record = _connector_remediation_run_record(index, run)
    if run_record is None:
        raise ValueError(f"run {run_id} is not a connector remediation run")
    denied_actions = [
        item
        for item in _row_spec(run_record).get("deniedPermissionActions", [])
        if isinstance(item, dict)
    ]
    if not denied_actions:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "run": run_record,
            "blockers": ["run has no denied permission actions"],
            "warnings": [],
        }

    selected_decision = _select_denied_permission_action(
        denied_actions,
        action_canonical=action_canonical,
        action_index=action_index,
    )
    action = selected_decision.get("action") if isinstance(selected_decision.get("action"), dict) else {}
    if not action:
        raise ValueError("selected permission decision has no action")
    current_decision = explain_effective_permissions(
        index,
        member=run.spec.member,
        project=run.spec.project,
        assignment=run.spec.assignment,
        action=action,
        non_interactive=True,
    )
    canonical = _permission_action_canonical(current_decision.get("normalizedAction") or action)
    existing = _pending_connector_remediation_permission_request(
        index,
        run_id=run.object_id,
        member=run.spec.member,
        action_canonical=canonical,
    )
    if existing is not None:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "run": run_record,
            "action": current_decision.get("normalizedAction") or action,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "existingRequest": existing,
            "blockers": [f"pending PermissionRequest {existing['id']} already covers {canonical}"],
            "warnings": [],
        }
    existing_state = _connector_remediation_permission_state(
        index,
        run_id=run.object_id,
        member=run.spec.member,
        project=run.spec.project,
        assignment=run.spec.assignment,
        denied_permission_actions=[selected_decision],
    )
    if existing_state["activeGrants"]:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "run": run_record,
            "action": current_decision.get("normalizedAction") or action,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "activePermissionGrants": existing_state["activeGrants"],
            "permissionApprovalOutcome": "approved-but-still-blocked",
            "blockers": [
                f"active PermissionGrant already covers {canonical}, but effective deny-first policy still blocks this remediation action"
            ],
            "warnings": [],
        }

    request_preview = {
        "member": run.spec.member,
        "project": run.spec.project,
        "assignment": run.spec.assignment,
        "task": run.spec.task,
        "run": run.object_id,
        "requesterMember": actor_member,
        "action": current_decision.get("normalizedAction") or action,
        "reason": reason or f"Connector remediation run {run.object_id} needs approval for {canonical}.",
        "expiresAt": expires_at,
        "source": "connector-remediation-run-permission-request",
    }
    if dry_run:
        return {
            "dryRun": True,
            "written": False,
            "canRequest": True,
            "run": run_record,
            "requestPreview": request_preview,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "blockers": [],
            "warnings": [],
        }

    request = create_permission_request(
        workspace_path,
        member=run.spec.member,
        action=current_decision.get("normalizedAction") or action,
        project=run.spec.project,
        assignment=run.spec.assignment,
        task=run.spec.task,
        run=run.object_id,
        requester_member=actor_member,
        reason=reason or f"Connector remediation run {run.object_id} needs approval for {canonical}.",
        expires_at=expires_at,
        current_decision=current_decision,
        source="connector-remediation-run-permission-request",
    )
    refreshed_index = load_workspace(workspace_path)
    refreshed_run_record = _connector_remediation_run_record(refreshed_index, refreshed_index.runs[run_id]) or run_record
    return {
        "dryRun": False,
        "written": True,
        "canRequest": True,
        "run": refreshed_run_record,
        "permissionRequest": manifest_to_record(request),
        "selectedPermissionDecision": selected_decision,
        "currentDecision": current_decision,
        "blockers": [],
        "warnings": [],
    }


def launch_connector_remediation_task_run(
    workspace_path: str | Path,
    task_id: str,
    *,
    actor_member: str,
    member: str | None = None,
    assignment: str | None = None,
    model_profile: str | None = None,
    mode: str | None = None,
    branch_base: str | None = None,
    reviewed_evidence_ids: list[str] | None = None,
    reviewed_review_requests: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "service"}:
        raise ValueError("connector remediation Task run launch requires a human or governed service actor member")
    task = index.tasks.get(task_id)
    if task is None:
        raise KeyError(f"unknown task {task_id}")
    remediation = _task_connector_remediation(task)
    if not remediation:
        raise ValueError(f"task {task_id} is not a materialized connector remediation task")
    task_plan_id = str(remediation["taskPlan"])
    source_plan = index.task_plans.get(task_plan_id)
    if source_plan is None:
        raise KeyError(f"unknown task plan {task_plan_id}")
    source_plan_spec = source_plan.model_dump(mode="json", exclude_none=True).get("spec", {})
    source_plan_spec = source_plan_spec if isinstance(source_plan_spec, dict) else {}
    source_plan_remediation = source_plan_spec.get("connectorRemediation") if isinstance(source_plan_spec.get("connectorRemediation"), dict) else {}
    if source_plan_spec.get("status") != "accepted":
        raise ValueError(f"source task plan {task_plan_id} is not accepted")

    required_evidence = _string_list(remediation.get("actionableEvidenceIds"))
    reviewed_evidence = set(_string_list(reviewed_evidence_ids))
    missing_evidence = sorted(set(required_evidence) - reviewed_evidence)
    required_reviews = [
        str(value)
        for value in [remediation.get("sourceReviewRequest"), remediation.get("latestResolvedReviewRequest")]
        if value
    ]
    reviewed_reviews = set(_string_list(reviewed_review_requests))
    missing_reviews = sorted(set(required_reviews) - reviewed_reviews)

    queue = task_execution_queue(index)
    queue_item = next(
        (item for item in queue.get("items", []) if isinstance(item, dict) and item.get("id") == task_id),
        None,
    )
    launch_plan = build_run_launch_plan(
        index,
        task_id,
        member=member,
        assignment=assignment,
        model_profile=model_profile,
        mode=mode,
        branch_base=branch_base,
    )
    launch_blockers = list(launch_plan.get("blockers") or [])
    queue_status = queue_item.get("queueStatus") if queue_item else None
    if queue_status != "ready-to-run":
        launch_blockers.append(f"Task queue status is {queue_status or 'unknown'}, not ready-to-run.")
    if missing_evidence:
        launch_blockers.append("Missing reviewed evidence ids: " + ", ".join(missing_evidence))
    if missing_reviews:
        launch_blockers.append("Missing reviewed review-request ids: " + ", ".join(missing_reviews))

    project_id = task.spec.project
    permission_decision = explain_effective_permissions(
        index,
        member=actor_member,
        project=project_id,
        action={"tool": "Edit", "path": "/.aiteamos/runs/RUN-*.yaml", "operation": "create"},
        non_interactive=actor_kind == "service",
    )
    if permission_decision["decision"] == "deny" or permission_decision.get("blockers"):
        launch_blockers.append(
            "Run creation is denied by effective permissions: "
            f"{permission_decision.get('reason')}; blockers={permission_decision.get('blockers')}"
        )

    task_record = _connector_remediation_materialized_task_record(index, task, queue_item)
    if dry_run:
        return {
            "dryRun": True,
            "canLaunch": not launch_blockers,
            "written": False,
            "task": task_record,
            "run": None,
            "launchPlan": launch_plan,
            "permissionDecision": permission_decision,
            "evidenceReview": {
                "requiredEvidenceIds": required_evidence,
                "reviewedEvidenceIds": sorted(reviewed_evidence),
                "missingEvidenceIds": missing_evidence,
                "requiredReviewRequests": required_reviews,
                "reviewedReviewRequests": sorted(reviewed_reviews),
                "missingReviewRequests": missing_reviews,
            },
            "blockers": launch_blockers,
        }
    if launch_blockers:
        raise ValueError("connector remediation Task run launch is blocked: " + "; ".join(launch_blockers))

    now = datetime.now().astimezone()
    decided_at = now.isoformat(timespec="milliseconds")
    selected_member = str(launch_plan["selectedMember"])
    selected_assignment = launch_plan.get("selectedAssignment")
    selected_model_profile = launch_plan.get("selectedModelProfile")
    selected_mode = str(launch_plan.get("selectedMode") or "assisted")
    task_payload = task.model_dump(mode="json", exclude_none=True)
    task_spec = task_payload.get("spec") if isinstance(task_payload.get("spec"), dict) else {}
    task_spec = task_spec if isinstance(task_spec, dict) else {}
    connector_lineage = {
        "source": "connector-remediation-task-run-launch",
        "connector": remediation.get("connector"),
        "taskPlan": task_plan_id,
        "sourceTask": task_id,
        "sourceTaskPlan": task_plan_id,
        "sourceTaskPlanSubtask": task_spec.get("sourceTaskPlanSubtask"),
        "sourceSuggestion": remediation.get("sourceSuggestion"),
        "sourceCandidate": remediation.get("sourceCandidate"),
        "sourceReviewRequest": remediation.get("sourceReviewRequest"),
        "latestResolvedReviewRequest": remediation.get("latestResolvedReviewRequest"),
        "actionableEvidenceIds": required_evidence,
        "reviewedEvidenceIds": sorted(reviewed_evidence),
        "reviewedReviewRequests": sorted(reviewed_reviews),
        "acceptedByMember": source_plan_remediation.get("acceptedByMember"),
        "acceptedByMemberKind": source_plan_remediation.get("acceptedByMemberKind"),
        "launchedByMember": actor_member,
        "launchedByMemberKind": actor_kind,
        "launchedAt": decided_at,
    }
    decision_audit = decision_audit_record(
        index,
        decision_kind="human_approval" if actor_kind == "human" else "service_policy_decision",
        decision="run-created",
        actor_member=actor_member,
        authority="approve" if actor_kind == "human" else "submit",
        reason="Connector remediation Task was launched into a normal Run after evidence review and launch readiness checks.",
        source="connector-remediation-task-run-launch",
        decided_at=decided_at,
        policy_refs=_string_list(permission_decision.get("selectedPolicyIds")),
        evidence=[
            {"kind": "Task", "id": task_id},
            {"kind": "TaskPlan", "id": task_plan_id},
            *[{"kind": _evidence_record(index, evidence_id)["kind"], "id": evidence_id} for evidence_id in required_evidence],
            *[{"kind": "MemberMessage", "id": review_id} for review_id in required_reviews],
        ],
        requires_human_review=False,
        risk_assessment=permission_decision.get("riskAssessment"),
        metadata={
            "permissionDecision": permission_decision.get("decision"),
            "queueStatus": queue_status,
            "selectedMember": selected_member,
            "selectedAssignment": selected_assignment,
            "selectedMode": selected_mode,
            "selectedModelProfile": selected_model_profile,
        },
    )
    run = create_run(
        workspace_path,
        task_id=task_id,
        member=selected_member,
        assignment=str(selected_assignment) if selected_assignment else None,
        model_profile=str(selected_model_profile) if selected_model_profile else None,
        mode=selected_mode,
        branch_base=str(launch_plan.get("branchBase") or branch_base) if launch_plan.get("branchBase") or branch_base else None,
        extra_spec={
            "createdByMember": actor_member,
            "createdByMemberKind": actor_kind,
            "sourceTaskPlan": task_plan_id,
            "sourceTaskPlanSubtask": task_spec.get("sourceTaskPlanSubtask"),
            "connectorRemediation": connector_lineage,
            "decisionAudit": [decision_audit],
        },
    )
    refreshed = load_workspace(workspace_path)
    refreshed_queue = task_execution_queue(refreshed)
    refreshed_queue_by_task = {
        str(item.get("id")): item
        for item in refreshed_queue.get("items", [])
        if isinstance(item, dict) and item.get("id")
    }
    return {
        "dryRun": False,
        "canLaunch": True,
        "written": True,
        "task": _connector_remediation_materialized_task_record(
            refreshed,
            refreshed.tasks[task_id],
            refreshed_queue_by_task.get(task_id),
        ),
        "run": manifest_to_record(refreshed.runs[run.object_id]),
        "launchPlan": launch_plan,
        "permissionDecision": permission_decision,
        "evidenceReview": {
            "requiredEvidenceIds": required_evidence,
            "reviewedEvidenceIds": sorted(reviewed_evidence),
            "missingEvidenceIds": [],
            "requiredReviewRequests": required_reviews,
            "reviewedReviewRequests": sorted(reviewed_reviews),
            "missingReviewRequests": [],
        },
        "blockers": [],
    }


def accept_connector_remediation_task_plan(
    workspace_path: str | Path,
    task_plan_id: str,
    *,
    actor_member: str,
    reviewed_evidence_ids: list[str] | None = None,
    reviewed_review_requests: list[str] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "service"}:
        raise ValueError("connector remediation TaskPlan acceptance requires a human or governed service actor member")
    plan = index.task_plans.get(task_plan_id)
    if plan is None:
        raise KeyError(f"unknown task plan {task_plan_id}")
    plan_payload = plan.model_dump(mode="json", exclude_none=True)
    spec = plan_payload.get("spec") if isinstance(plan_payload.get("spec"), dict) else {}
    remediation = spec.get("connectorRemediation")
    if not isinstance(remediation, dict):
        raise ValueError(f"task plan {task_plan_id} is not a connector remediation task plan")
    status = str(spec.get("status") or "draft")
    if status in {"rejected", "superseded"}:
        raise ValueError(f"task plan {task_plan_id} cannot be accepted from status {status}")

    required_evidence = _string_list(remediation.get("actionableEvidenceIds"))
    reviewed_evidence = set(_string_list(reviewed_evidence_ids))
    missing_evidence = sorted(set(required_evidence) - reviewed_evidence)
    if missing_evidence:
        raise ValueError("connector remediation TaskPlan acceptance is missing reviewed evidence ids: " + ", ".join(missing_evidence))

    required_reviews = [
        str(value)
        for value in [remediation.get("sourceReviewRequest"), remediation.get("latestResolvedReviewRequest")]
        if value
    ]
    reviewed_reviews = set(_string_list(reviewed_review_requests))
    missing_reviews = sorted(set(required_reviews) - reviewed_reviews)
    if missing_reviews:
        raise ValueError("connector remediation TaskPlan acceptance is missing reviewed review-request ids: " + ", ".join(missing_reviews))

    existing_tasks = _string_list(remediation.get("createdTasks"))
    if existing_tasks and all(task_id in index.tasks for task_id in existing_tasks):
        return {
            "dryRun": dry_run,
            "alreadyMaterialized": True,
            "taskPlan": _connector_remediation_task_plan_record(index, plan),
            "plannedTasks": [],
            "createdTasks": [manifest_to_record(index.tasks[task_id]) for task_id in existing_tasks],
            "written": False,
        }

    project_id = str(spec.get("project") or remediation.get("project") or index.project.object_id)
    permission_decision = explain_effective_permissions(
        index,
        member=actor_member,
        project=project_id,
        action={"tool": "Edit", "path": f"/.aiteamos/task_plans/{task_plan_id}.yaml", "operation": "update"},
        non_interactive=actor_kind == "service",
    )
    if permission_decision["decision"] == "deny" or permission_decision.get("blockers"):
        raise ValueError(
            "connector remediation TaskPlan acceptance is denied by effective permissions: "
            f"{permission_decision.get('reason')}; blockers={permission_decision.get('blockers')}"
        )

    now = datetime.now().astimezone()
    planned_tasks = _connector_remediation_task_payloads(index, plan_payload, actor_member=actor_member, accepted_at=now)
    if not planned_tasks:
        raise ValueError(f"task plan {task_plan_id} has no materializable subtasks")
    task_permission_decision = explain_effective_permissions(
        index,
        member=actor_member,
        project=project_id,
        action={"tool": "Edit", "path": "/.aiteamos/tasks/TASK-*.yaml", "operation": "create"},
        non_interactive=actor_kind == "service",
    )
    if task_permission_decision["decision"] == "deny" or task_permission_decision.get("blockers"):
        raise ValueError(
            "connector remediation Task creation is denied by effective permissions: "
            f"{task_permission_decision.get('reason')}; blockers={task_permission_decision.get('blockers')}"
        )

    if dry_run:
        return {
            "dryRun": True,
            "alreadyMaterialized": False,
            "taskPlan": _connector_remediation_task_plan_record(index, plan),
            "plannedTasks": [manifest_to_record(Task.model_validate(payload)) for payload in planned_tasks],
            "createdTasks": [],
            "permissionDecision": permission_decision,
            "taskPermissionDecision": task_permission_decision,
            "evidenceReview": {
                "requiredEvidenceIds": required_evidence,
                "reviewedEvidenceIds": sorted(reviewed_evidence),
                "reviewedReviewRequests": sorted(reviewed_reviews),
            },
            "written": False,
        }

    created_tasks: list[Task] = []
    for payload in planned_tasks:
        task = Task.model_validate(payload)
        write_yaml(index.workspace_root / "tasks" / f"{task.object_id}.yaml", task.model_dump(mode="json", exclude_none=True))
        created_tasks.append(task)

    accepted_at = now.isoformat(timespec="milliseconds")
    remediation["acceptedByMember"] = actor_member
    remediation["acceptedByMemberKind"] = actor_kind
    remediation["acceptedAt"] = accepted_at
    remediation["materializedAt"] = accepted_at
    remediation["createdTasks"] = [task.object_id for task in created_tasks]
    remediation["reviewedEvidenceIds"] = sorted(reviewed_evidence)
    remediation["reviewedReviewRequests"] = sorted(reviewed_reviews)
    spec["connectorRemediation"] = remediation
    spec["status"] = "accepted"
    decision_audit = list(spec.get("decisionAudit")) if isinstance(spec.get("decisionAudit"), list) else []
    decision_audit.append(
        decision_audit_record(
            index,
            decision_kind="human_approval" if actor_kind == "human" else "service_policy_decision",
            decision="task-plan-accepted",
            actor_member=actor_member,
            authority="approve" if actor_kind == "human" else "submit",
            reason="Connector remediation TaskPlan was accepted and materialized into ordinary Tasks after evidence review.",
            source="connector-remediation-task-plan-accept",
            decided_at=accepted_at,
            policy_refs=_string_list(permission_decision.get("selectedPolicyIds")),
            evidence=[
                {"kind": "TaskPlan", "id": task_plan_id},
                *[{"kind": _evidence_record(index, evidence_id)["kind"], "id": evidence_id} for evidence_id in required_evidence],
                *[{"kind": "MemberMessage", "id": review_id} for review_id in required_reviews],
            ],
            requires_human_review=False,
            risk_assessment=permission_decision.get("riskAssessment"),
            metadata={
                "permissionDecision": permission_decision.get("decision"),
                "taskPermissionDecision": task_permission_decision.get("decision"),
                "createdTasks": [task.object_id for task in created_tasks],
            },
        )
    )
    spec["decisionAudit"] = decision_audit
    plan_payload["spec"] = spec
    accepted_plan = TaskPlan.model_validate(plan_payload)
    write_yaml(index.workspace_root / "task_plans" / f"{task_plan_id}.yaml", accepted_plan.model_dump(mode="json", exclude_none=True))
    refreshed = load_workspace(workspace_path)
    return {
        "dryRun": False,
        "alreadyMaterialized": False,
        "taskPlan": _connector_remediation_task_plan_record(refreshed, refreshed.task_plans[task_plan_id]),
        "plannedTasks": [],
        "createdTasks": [manifest_to_record(task) for task in created_tasks],
        "permissionDecision": permission_decision,
        "taskPermissionDecision": task_permission_decision,
        "evidenceReview": {
            "requiredEvidenceIds": required_evidence,
            "reviewedEvidenceIds": sorted(reviewed_evidence),
            "reviewedReviewRequests": sorted(reviewed_reviews),
        },
        "written": True,
    }


def submit_connector_remediation_task_plan(
    workspace_path: str | Path,
    suggestion_id: str,
    *,
    actor_member: str,
    task_plan: dict[str, Any],
    source_actionable_evidence_ids: list[str] | None = None,
    lifecycle: str | None = "active",
    min_evidence: int = 2,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "service"}:
        raise ValueError("connector remediation TaskPlan submit requires a human or governed service actor member")

    suggestion_set = connector_remediation_suggestions(index, lifecycle=lifecycle, min_evidence=min_evidence)
    suggestion = next((item for item in suggestion_set["suggestions"] if item["id"] == suggestion_id), None)
    if suggestion is None:
        raise KeyError(f"unknown connector remediation suggestion {suggestion_id}")
    suggestion_spec = suggestion["spec"]
    blockers = _string_list(suggestion_spec.get("blockers"))
    if blockers or not suggestion_spec.get("readyForTaskPlan"):
        raise ValueError("connector remediation suggestion is not ready for TaskPlan submit: " + "; ".join(blockers or ["not ready"]))

    current_evidence_ids = _string_list(suggestion_spec.get("actionableEvidenceIds"))
    submitted_evidence_ids = _string_list(source_actionable_evidence_ids)
    if submitted_evidence_ids and submitted_evidence_ids != current_evidence_ids:
        raise ValueError(
            "connector remediation suggestion evidence is stale; refresh the suggestion before submitting "
            f"(submitted={submitted_evidence_ids}, current={current_evidence_ids})"
        )

    if not isinstance(task_plan, dict):
        raise ValueError("taskPlan must be an object")
    now = datetime.now().astimezone()
    created_at = now.isoformat(timespec="milliseconds")
    plan_id = _next_task_plan_id(index.workspace_root, now)
    plan_path = index.workspace_root / "task_plans" / f"{plan_id}.yaml"
    project_id = str(suggestion_spec.get("project") or index.project.object_id)

    permission_decision = explain_effective_permissions(
        index,
        member=actor_member,
        project=project_id,
        action={"tool": "Edit", "path": f"/.aiteamos/task_plans/{plan_id}.yaml", "operation": "create"},
        non_interactive=actor_kind == "service",
    )
    if permission_decision["decision"] == "deny" or permission_decision.get("blockers"):
        raise ValueError(
            "connector remediation TaskPlan submit is denied by effective permissions: "
            f"{permission_decision.get('reason')}; blockers={permission_decision.get('blockers')}"
        )

    payload = deepcopy(task_plan)
    payload["apiVersion"] = "aiteamos.dev/v1alpha1"
    payload["kind"] = "TaskPlan"
    metadata = dict(payload.get("metadata") or {})
    metadata["id"] = plan_id
    metadata["createdAt"] = created_at
    payload["metadata"] = metadata

    spec = dict(payload.get("spec") or {})
    submitted_project = str(spec.get("project") or project_id)
    if submitted_project != project_id:
        raise ValueError(f"submitted TaskPlan project {submitted_project} does not match suggestion project {project_id}")
    spec["project"] = project_id
    spec["createdByMember"] = actor_member
    spec["status"] = "draft"

    subtasks = spec.get("subtasks")
    if not isinstance(subtasks, list) or not subtasks:
        raise ValueError("connector remediation TaskPlan must contain at least one subtask")
    normalized_subtasks = [_normalize_subtask(index, item, project_id) for item in subtasks]
    first_subtask = normalized_subtasks[0]
    first_subtask.setdefault("assignedMember", suggestion_spec.get("suggestedOwnerMember"))
    first_subtask.setdefault("assignment", suggestion_spec.get("suggestedAssignment"))
    _validate_subtask_refs(index, first_subtask, project_id)
    _append_unique_text(
        first_subtask,
        "acceptance",
        "Review current connector remediation evidence ids: " + ", ".join(current_evidence_ids) + ".",
    )
    for gate in ["connector evidence review", "secret handling review", "permission policy review"]:
        _append_unique_text(first_subtask, "reviewGates", gate)
    for gate in ["connector remediation reviewed submit", "human/service audit provenance"]:
        _append_unique_text(spec, "reviewGates", gate)
    spec["subtasks"] = normalized_subtasks

    remediation_audit = {
        "source": "connector-remediation-submit",
        "sourceSuggestion": suggestion_id,
        "sourceCandidate": suggestion_spec.get("sourceCandidate"),
        "sourceReviewRequest": suggestion_spec.get("sourceReviewRequest"),
        "latestResolvedReviewRequest": suggestion_spec.get("latestResolvedReviewRequest"),
        "connector": suggestion_spec.get("connector"),
        "project": project_id,
        "actionableEvidenceIds": current_evidence_ids,
        "actorMember": actor_member,
        "actorMemberKind": actor_kind,
        "submittedAt": created_at,
    }
    spec["connectorRemediation"] = remediation_audit
    existing_audit = spec.get("decisionAudit")
    decision_audit = list(existing_audit) if isinstance(existing_audit, list) else []
    decision_audit.append(
        decision_audit_record(
            index,
            decision_kind="human_approval" if actor_kind == "human" else "service_policy_decision",
            decision="task-plan-submitted",
            actor_member=actor_member,
            authority="submit",
            reason="Connector remediation suggestion was submitted as a draft TaskPlan after permission and evidence freshness checks.",
            source="connector-remediation-submit",
            decided_at=created_at,
            policy_refs=_string_list(permission_decision.get("selectedPolicyIds")),
            evidence=[
                {"kind": "ConnectorRemediationSuggestion", "suggestion": suggestion_id},
                *[{"kind": _evidence_record(index, evidence_id)["kind"], "id": evidence_id} for evidence_id in current_evidence_ids],
            ],
            requires_human_review=False,
            risk_assessment=permission_decision.get("riskAssessment"),
            metadata={
                "permissionDecision": permission_decision.get("decision"),
                "permissionReason": permission_decision.get("reason"),
            },
        )
    )
    spec["decisionAudit"] = decision_audit
    payload["spec"] = spec

    plan = TaskPlan.model_validate(payload)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(plan_path, plan.model_dump(mode="json", exclude_none=True))
    return {
        "sourceSuggestion": suggestion,
        "taskPlan": manifest_to_record(plan),
        "permissionDecision": permission_decision,
        "evidenceFreshness": {
            "submittedEvidenceIds": submitted_evidence_ids,
            "currentEvidenceIds": current_evidence_ids,
            "fresh": not submitted_evidence_ids or submitted_evidence_ids == current_evidence_ids,
        },
        "written": True,
    }


def route_connector_failure_escalations(
    workspace_path: str | Path,
    *,
    actor_member: str,
    connector: str | None = None,
    project: str | None = None,
    member: str | None = None,
    assignment: str | None = None,
    lifecycle: str | None = "active",
    dry_run: bool = True,
    min_evidence: int = 2,
    max_messages: int | None = None,
    audit_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "service"}:
        raise ValueError("connector failure escalations require a human or service actor member")
    candidate_set = connector_failure_escalation_candidates(
        index,
        connector=connector,
        project=project,
        member=member,
        assignment=assignment,
        lifecycle=lifecycle,
        min_evidence=min_evidence,
    )
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for candidate in candidate_set["candidates"]:
        spec = candidate["spec"]
        if spec["existingReviewRequest"]:
            skipped.append({"candidate": candidate["id"], "reason": "existing-open-review-request", "message": spec["existingReviewRequest"]})
            continue
        if spec.get("resolvedReviewRequest"):
            skipped.append({"candidate": candidate["id"], "reason": "resolved-evidence-reviewed", "message": spec["resolvedReviewRequest"]})
            continue
        if not spec["toMembers"]:
            skipped.append({"candidate": candidate["id"], "reason": "no-routable-member"})
            continue
        if int(spec["evidenceCount"]) < int(spec["minEvidence"]):
            skipped.append({"candidate": candidate["id"], "reason": "below-evidence-threshold"})
            continue
        if dry_run:
            skipped.append({"candidate": candidate["id"], "reason": "dry-run"})
            continue
        if max_messages is not None and len(created) >= max_messages:
            skipped.append({"candidate": candidate["id"], "reason": "max-review-requests-per-run"})
            continue
        message = record_member_message(
            workspace_path,
            from_member=actor_member,
            to_members=list(spec["toMembers"]),
            message_type="review-request",
            body=str(spec["body"]),
            project=spec.get("project") or index.project.object_id,
            attachments=list(spec["attachments"]),
            priority=str(spec["priority"]),
            audit={
                "source": "connector-failure-escalation",
                "workflow": "review-request",
                "reviewKind": "connector-failure",
                "connectorEscalationDedupeKey": spec["dedupeKey"],
                "connector": spec["connector"],
                "evidenceIds": list(spec["evidenceIds"]),
                "existingReminderMessages": list(spec["existingReminderMessages"]),
                "severity": spec["severity"],
                "minEvidence": spec["minEvidence"],
                **(audit_context or {}),
            },
            source="connector-failure-escalation",
        )
        created.append(manifest_to_record(message))
    return {
        "dryRun": dry_run,
        "filters": candidate_set["filters"],
        "summary": {
            **candidate_set["summary"],
            "createdReviewRequests": len(created),
            "skipped": len(skipped),
            "maxReviewRequestsSkipped": sum(1 for item in skipped if item["reason"] == "max-review-requests-per-run"),
        },
        "createdReviewRequests": created,
        "skipped": skipped,
        "candidates": candidate_set["candidates"],
    }


def resolve_connector_failure_escalation(
    workspace_path: str | Path,
    message_id: str,
    *,
    actor_member: str,
    resolution: str,
    evidence_reviewed: list[str] | None = None,
    reminder_messages_reviewed: list[str] | None = None,
    follow_up_reviewed: dict[str, Any] | None = None,
) -> MemberMessage:
    index = load_workspace(workspace_path)
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    actor_kind = index.members[actor_member].spec.kind
    if actor_kind not in {"human", "service"}:
        raise ValueError("connector failure escalation resolution requires a human or service actor member")
    if message_id not in index.member_messages:
        raise KeyError(f"unknown member message {message_id}")

    message = index.member_messages[message_id]
    if message.spec.messageType != "review-request" or message.spec.audit.get("source") != "connector-failure-escalation":
        raise ValueError(f"member message {message_id} is not a connector failure escalation review request")

    audit = message.spec.audit
    required_evidence = set(_string_list(audit.get("evidenceIds")))
    reviewed_evidence = set(evidence_reviewed or [])
    missing_evidence = sorted(required_evidence - reviewed_evidence)
    if missing_evidence:
        raise ValueError("connector escalation resolution is missing reviewed evidence: " + ", ".join(missing_evidence))

    for evidence_id in reviewed_evidence:
        if evidence_id not in index.connector_health_checks and evidence_id not in index.automation_provider_deliveries:
            raise KeyError(f"unknown connector escalation evidence {evidence_id}")

    required_reminders = set(_string_list(audit.get("existingReminderMessages")))
    reviewed_reminders = set(reminder_messages_reviewed or [])
    missing_reminders = sorted(required_reminders - reviewed_reminders)
    if missing_reminders:
        raise ValueError("connector escalation resolution is missing reviewed reminder messages: " + ", ".join(missing_reminders))

    for reminder_id in reviewed_reminders:
        if reminder_id not in index.member_messages:
            raise KeyError(f"unknown connector escalation reminder message {reminder_id}")

    resolved = resolve_member_message(
        workspace_path,
        message_id,
        actor_member=actor_member,
        resolution=resolution,
        status="resolved",
        allow_connector_escalation_resolution=True,
    )

    path = _member_message_manifest_path(index, message_id)
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    audit_data = spec.setdefault("audit", {})
    audit_data["connectorEscalationResolution"] = {
        "actorMember": actor_member,
        "actorMemberKind": actor_kind,
        "resolvedAt": spec.get("resolvedAt"),
        "evidenceReviewed": sorted(reviewed_evidence),
        "reminderMessagesReviewed": sorted(reviewed_reminders),
        "followUpReviewed": follow_up_reviewed or {},
    }
    resolved = MemberMessage.model_validate(data)
    write_yaml(path, resolved.model_dump(mode="json", exclude_none=True))
    return resolved


def _normalize_scope(
    index: WorkspaceIndex,
    *,
    connector: str | None,
    project: str | None,
    member: str | None,
    assignment: str | None,
    lifecycle: str | None,
) -> dict[str, str | None]:
    if connector is not None and connector not in index.connectors:
        has_delivery = any(delivery.spec.connector == connector for delivery in index.automation_provider_deliveries.values())
        has_health = any(check.spec.connector == connector for check in index.connector_health_checks.values())
        if not has_delivery and not has_health:
            raise KeyError(f"unknown connector {connector}")
    if assignment is not None:
        selected_assignment = index.assignments.get(assignment)
        if selected_assignment is None:
            raise KeyError(f"unknown assignment {assignment}")
        if project is not None and project != selected_assignment.spec.project:
            raise ValueError(f"assignment {assignment} belongs to project {selected_assignment.spec.project}, not {project}")
        if member is not None and member != selected_assignment.spec.member:
            raise ValueError(f"assignment {assignment} belongs to member {selected_assignment.spec.member}, not {member}")
        project = selected_assignment.spec.project
        member = selected_assignment.spec.member
    if project is not None and project != index.project.object_id:
        raise KeyError(f"unknown project {project}")
    if member is not None and member not in index.members:
        raise KeyError(f"unknown member {member}")
    if lifecycle is not None and lifecycle not in {"active", "archived"}:
        raise ValueError("lifecycle must be active or archived")
    return {
        "connector": connector,
        "project": project,
        "member": member,
        "assignment": assignment,
        "lifecycle": lifecycle,
    }


def _member_message_manifest_path(index: WorkspaceIndex, message_id: str) -> Path:
    direct = index.workspace_root / "im" / "messages" / f"{message_id}.yaml"
    if direct.exists():
        return direct
    matches = sorted((index.workspace_root / "im" / "messages").rglob(f"{message_id}.yaml"))
    if not matches:
        raise FileNotFoundError(f"member message manifest not found for {message_id}")
    return matches[0]


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    if value is None:
        return []
    return [str(value)]


def _connector_row(connector_id: str, *, provider: str, connector_type: str, projects: list[str], owner_member: str | None) -> dict[str, Any]:
    return {
        "id": connector_id,
        "kind": "ConnectorOperations",
        "spec": {
            "connector": connector_id,
            "provider": provider,
            "connectorType": connector_type,
            "projects": projects,
            "ownerMember": owner_member,
            "automationOwnerMembers": [],
            "automationServiceMembers": [],
            "healthChecks": 0,
            "activeHealthChecks": 0,
            "archivedHealthChecks": 0,
            "healthyHealthChecks": 0,
            "degradedHealthChecks": 0,
            "blockedHealthChecks": 0,
            "unknownHealthChecks": 0,
            "providerDeliveries": 0,
            "activeProviderDeliveries": 0,
            "archivedProviderDeliveries": 0,
            "acceptedProviderDeliveries": 0,
            "duplicateProviderDeliveries": 0,
            "blockedProviderDeliveries": 0,
            "acceptedReplayDeliveries": 0,
            "duplicateReplayDeliveries": 0,
            "staleReplayDeliveries": 0,
            "blockedReplayDeliveries": 0,
            "warnings": 0,
            "blockers": 0,
        },
    }


def _summary(connector_count: int, health_checks: list[Any], provider_deliveries: list[Any]) -> dict[str, int]:
    return {
        "connectors": connector_count,
        "healthChecks": len(health_checks),
        "activeHealthChecks": sum(1 for item in health_checks if item.spec.lifecycle == "active"),
        "archivedHealthChecks": sum(1 for item in health_checks if item.spec.lifecycle == "archived"),
        "healthyHealthChecks": sum(1 for item in health_checks if item.spec.status == "healthy"),
        "degradedHealthChecks": sum(1 for item in health_checks if item.spec.status == "degraded"),
        "blockedHealthChecks": sum(1 for item in health_checks if item.spec.status == "blocked"),
        "unknownHealthChecks": sum(1 for item in health_checks if item.spec.status == "unknown"),
        "providerDeliveries": len(provider_deliveries),
        "activeProviderDeliveries": sum(1 for item in provider_deliveries if item.spec.lifecycle == "active"),
        "archivedProviderDeliveries": sum(1 for item in provider_deliveries if item.spec.lifecycle == "archived"),
        "acceptedProviderDeliveries": sum(1 for item in provider_deliveries if item.spec.admissionStatus == "accepted"),
        "duplicateProviderDeliveries": sum(1 for item in provider_deliveries if item.spec.admissionStatus == "duplicate"),
        "blockedProviderDeliveries": sum(1 for item in provider_deliveries if item.spec.admissionStatus == "blocked"),
        "staleReplayDeliveries": sum(1 for item in provider_deliveries if item.spec.replayStatus == "stale"),
        "blockedReplayDeliveries": sum(1 for item in provider_deliveries if item.spec.replayStatus == "blocked"),
        "warnings": sum(len(item.spec.warnings) for item in [*health_checks, *provider_deliveries]),
        "blockers": sum(len(item.spec.blockers) for item in [*health_checks, *provider_deliveries]),
    }


def _reminder_summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "candidates": len(candidates),
        "blocked": sum(1 for item in candidates if item["spec"]["severity"] == "blocked"),
        "warning": sum(1 for item in candidates if item["spec"]["severity"] == "warning"),
        "routable": sum(1 for item in candidates if item["spec"]["routable"]),
        "unrouted": sum(1 for item in candidates if not item["spec"]["toMembers"]),
        "alreadyOpen": sum(1 for item in candidates if item["spec"]["existingMessage"]),
    }


def _escalation_summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "candidates": len(candidates),
        "blocked": sum(1 for item in candidates if item["spec"]["severity"] == "blocked"),
        "warning": sum(1 for item in candidates if item["spec"]["severity"] == "warning"),
        "routable": sum(1 for item in candidates if item["spec"]["routable"]),
        "alreadyOpen": sum(1 for item in candidates if item["spec"]["existingReviewRequest"]),
        "alreadyResolved": sum(1 for item in candidates if item["spec"].get("resolvedReviewRequest")),
        "withPriorResolution": sum(1 for item in candidates if item["spec"].get("latestResolvedReviewRequest")),
        "suppressedByResolution": sum(1 for item in candidates if item["spec"].get("suppressedByResolution")),
        "withUnreviewedEvidence": sum(1 for item in candidates if item["spec"].get("unreviewedEvidenceIds")),
        "belowThreshold": sum(1 for item in candidates if int(item["spec"]["evidenceCount"]) < int(item["spec"]["minEvidence"])),
        "unrouted": sum(1 for item in candidates if not item["spec"]["toMembers"]),
    }


def _with_latest_audit(manifest: Any) -> dict[str, Any]:
    record = manifest_to_record(manifest)
    latest = latest_decision_audit(manifest.spec.decisionAudit)
    record["latestDecisionKind"] = latest.get("decisionKind")
    record["latestDecision"] = latest.get("decision")
    record["latestDecisionAuthority"] = latest.get("authority")
    record["latestDecisionActorMember"] = latest.get("actorMember")
    record["latestDecisionActorKind"] = latest.get("actorMemberKind")
    return record


def _connector_remediation_connector_known(index: WorkspaceIndex, connector_id: str) -> bool:
    if connector_id in index.connectors:
        return True
    if any(check.spec.connector == connector_id for check in index.connector_health_checks.values()):
        return True
    if any(delivery.spec.connector == connector_id for delivery in index.automation_provider_deliveries.values()):
        return True
    return any(
        _task_plan_connector_remediation(plan).get("connector") == connector_id
        for plan in index.task_plans.values()
        if _task_plan_connector_remediation(plan)
    ) or any(
        _task_connector_remediation(task).get("connector") == connector_id
        for task in index.tasks.values()
        if _task_connector_remediation(task)
    ) or any(
        _run_connector_remediation(run).get("connector") == connector_id
        for run in index.runs.values()
        if _run_connector_remediation(run)
    )


def _connector_remediation_task_plan_record(index: WorkspaceIndex, plan: TaskPlan) -> dict[str, Any] | None:
    payload = plan.model_dump(mode="json", exclude_none=True)
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    remediation = spec.get("connectorRemediation")
    if not isinstance(remediation, dict):
        return None

    subtasks = spec.get("subtasks") if isinstance(spec.get("subtasks"), list) else []
    assigned_members: list[str] = []
    assignments: list[str] = []
    for subtask in subtasks:
        if not isinstance(subtask, dict):
            continue
        _append_unique({"values": assigned_members}, "values", subtask.get("assignedMember"))
        _append_unique({"values": assignments}, "values", subtask.get("assignment"))

    latest = latest_decision_audit(spec.get("decisionAudit") if isinstance(spec.get("decisionAudit"), list) else [])
    actor_member = str(remediation.get("actorMember") or spec.get("createdByMember") or "")
    actor_kind = str(remediation.get("actorMemberKind") or "")
    if actor_member and not actor_kind:
        actor = index.members.get(actor_member)
        actor_kind = actor.spec.kind if actor is not None else ""
    actionable_evidence_ids = _string_list(remediation.get("actionableEvidenceIds"))
    record = manifest_to_record(plan)
    record_spec = record.setdefault("spec", {})
    if not isinstance(record_spec, dict):
        record["spec"] = record_spec = {}
    record_spec.update(
        {
            "connector": remediation.get("connector"),
            "project": spec.get("project") or remediation.get("project"),
            "submittedByMember": actor_member or None,
            "submittedByMemberKind": actor_kind or None,
            "acceptedByMember": remediation.get("acceptedByMember"),
            "acceptedByMemberKind": remediation.get("acceptedByMemberKind"),
            "acceptedAt": remediation.get("acceptedAt"),
            "materializedAt": remediation.get("materializedAt"),
            "createdTasks": _string_list(remediation.get("createdTasks")),
            "materializedTaskCount": len(_string_list(remediation.get("createdTasks"))),
            "sourceSuggestion": remediation.get("sourceSuggestion"),
            "sourceCandidate": remediation.get("sourceCandidate"),
            "sourceReviewRequest": remediation.get("sourceReviewRequest"),
            "latestResolvedReviewRequest": remediation.get("latestResolvedReviewRequest"),
            "actionableEvidenceIds": actionable_evidence_ids,
            "evidenceCount": len(actionable_evidence_ids),
            "assignedMembers": assigned_members,
            "assignments": assignments,
            "latestDecisionKind": latest.get("decisionKind"),
            "latestDecision": latest.get("decision"),
            "latestDecisionAuthority": latest.get("authority"),
            "latestDecisionActorMember": latest.get("actorMember"),
            "latestDecisionActorKind": latest.get("actorMemberKind"),
            "latestRiskLevel": (latest.get("riskAssessment") or {}).get("riskLevel") if isinstance(latest.get("riskAssessment"), dict) else None,
            "latestRecommendedDecision": (latest.get("riskAssessment") or {}).get("recommendedDecision") if isinstance(latest.get("riskAssessment"), dict) else None,
        }
    )
    return record


def _task_plan_connector_remediation(plan: TaskPlan) -> dict[str, Any]:
    payload = plan.model_dump(mode="json", exclude_none=True)
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    remediation = spec.get("connectorRemediation")
    return dict(remediation) if isinstance(remediation, dict) else {}


def _task_connector_remediation(task: Task) -> dict[str, Any]:
    payload = task.model_dump(mode="json", exclude_none=True)
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    remediation = spec.get("connectorRemediation")
    if not isinstance(remediation, dict):
        return {}
    source_task_plan = spec.get("sourceTaskPlan") or remediation.get("taskPlan")
    if remediation.get("source") != "connector-remediation-task-plan" or not source_task_plan:
        return {}
    return {
        **remediation,
        "taskPlan": str(source_task_plan),
    }


def _run_connector_remediation(run: Any) -> dict[str, Any]:
    payload = run.model_dump(mode="json", exclude_none=True)
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    remediation = spec.get("connectorRemediation")
    if not isinstance(remediation, dict):
        return {}
    task_plan = spec.get("sourceTaskPlan") or remediation.get("taskPlan") or remediation.get("sourceTaskPlan")
    source_task = spec.get("task") or remediation.get("sourceTask")
    if remediation.get("source") != "connector-remediation-task-run-launch" or not task_plan or not source_task:
        return {}
    return {
        **remediation,
        "taskPlan": str(task_plan),
        "sourceTask": str(source_task),
    }


def _connector_remediation_materialized_task_record(
    index: WorkspaceIndex,
    task: Task,
    queue_item: dict[str, Any] | None,
) -> dict[str, Any] | None:
    remediation = _task_connector_remediation(task)
    if not remediation:
        return None
    payload = task.model_dump(mode="json", exclude_none=True)
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    task_plan_id = str(remediation["taskPlan"])
    source_plan = index.task_plans.get(task_plan_id)
    source_plan_spec = source_plan.model_dump(mode="json", exclude_none=True).get("spec", {}) if source_plan is not None else {}
    source_plan_spec = source_plan_spec if isinstance(source_plan_spec, dict) else {}
    source_plan_remediation = source_plan_spec.get("connectorRemediation") if isinstance(source_plan_spec.get("connectorRemediation"), dict) else {}
    launch_plan = build_run_launch_plan(index, task.object_id)
    accepted_by_member = source_plan_remediation.get("acceptedByMember")
    accepted_by_kind = source_plan_remediation.get("acceptedByMemberKind")
    created_by_member = spec.get("createdByMember")
    created_by_kind = _member_kind(index, created_by_member)
    actionable_evidence_ids = _string_list(remediation.get("actionableEvidenceIds"))
    record = manifest_to_record(task)
    record_spec = record.setdefault("spec", {})
    if not isinstance(record_spec, dict):
        record["spec"] = record_spec = {}
    record_spec.update(
        {
            "connector": remediation.get("connector"),
            "sourceTaskPlan": task_plan_id,
            "sourceTaskPlanSubtask": spec.get("sourceTaskPlanSubtask"),
            "taskPlanStatus": source_plan_spec.get("status") if source_plan_spec else None,
            "taskPlanAcceptedByMember": accepted_by_member,
            "taskPlanAcceptedByMemberKind": accepted_by_kind,
            "taskPlanMaterializedAt": source_plan_remediation.get("materializedAt"),
            "createdByMember": created_by_member,
            "createdByMemberKind": created_by_kind,
            "sourceSuggestion": remediation.get("sourceSuggestion"),
            "sourceCandidate": remediation.get("sourceCandidate"),
            "sourceReviewRequest": remediation.get("sourceReviewRequest"),
            "latestResolvedReviewRequest": remediation.get("latestResolvedReviewRequest"),
            "actionableEvidenceIds": actionable_evidence_ids,
            "evidenceCount": len(actionable_evidence_ids),
            "queueStatus": queue_item.get("queueStatus") if queue_item else None,
            "queueBlockers": queue_item.get("blockers", []) if queue_item else [],
            "queueActions": queue_item.get("actions", []) if queue_item else [],
            "runCount": queue_item.get("runCount", 0) if queue_item else 0,
            "latestRun": queue_item.get("latestRun") if queue_item else None,
            "latestRunStatus": queue_item.get("latestRunStatus") if queue_item else None,
            "launchReady": bool(launch_plan.get("canCreateRun")),
            "launchSummary": launch_plan.get("summary"),
            "launchBlockers": launch_plan.get("blockers", []),
            "launchWarnings": launch_plan.get("warnings", []),
            "launchActions": launch_plan.get("actions", []),
            "selectedMember": launch_plan.get("selectedMember"),
            "selectedAssignment": launch_plan.get("selectedAssignment"),
            "memberKind": launch_plan.get("memberKind"),
            "selectedMode": launch_plan.get("selectedMode"),
            "selectedModelProfile": launch_plan.get("selectedModelProfile"),
            "branchPreview": launch_plan.get("branchPreview"),
        }
    )
    return record


def _connector_remediation_run_record(index: WorkspaceIndex, run: Any) -> dict[str, Any] | None:
    remediation = _run_connector_remediation(run)
    if not remediation:
        return None
    payload = run.model_dump(mode="json", exclude_none=True)
    spec = payload.get("spec") if isinstance(payload.get("spec"), dict) else {}
    task_id = str(remediation["sourceTask"])
    task = index.tasks.get(task_id)
    task_payload = task.model_dump(mode="json", exclude_none=True) if task is not None else {}
    task_spec = task_payload.get("spec") if isinstance(task_payload.get("spec"), dict) else {}
    task_spec = task_spec if isinstance(task_spec, dict) else {}
    task_plan_id = str(remediation["taskPlan"])
    source_plan = index.task_plans.get(task_plan_id)
    source_plan_spec = source_plan.model_dump(mode="json", exclude_none=True).get("spec", {}) if source_plan is not None else {}
    source_plan_spec = source_plan_spec if isinstance(source_plan_spec, dict) else {}
    source_plan_remediation = source_plan_spec.get("connectorRemediation") if isinstance(source_plan_spec.get("connectorRemediation"), dict) else {}
    execution_plan = build_run_execution_plan(index, run.object_id)
    model_readiness = evaluate_model_execution_readiness(index, run.object_id)
    worker_readiness = evaluate_worker_readiness(index, run.object_id)
    worker_authorization = evaluate_worker_authorization(index, run.object_id)
    permission_decisions = [
        decision
        for decision in worker_authorization.get("permissionDecisions", [])
        if isinstance(decision, dict)
    ]
    denied_permission_actions = [
        decision
        for decision in permission_decisions
        if decision.get("decision") != "allow" or decision.get("blockers")
    ]
    permission_approval_required = bool(denied_permission_actions)
    permission_state = _connector_remediation_permission_state(
        index,
        run_id=run.object_id,
        member=spec.get("member"),
        project=spec.get("project"),
        assignment=spec.get("assignment"),
        denied_permission_actions=denied_permission_actions,
    )
    pending_permission_requests = permission_state["pendingRequests"]
    accepted_by_member = remediation.get("acceptedByMember") or source_plan_remediation.get("acceptedByMember")
    accepted_by_kind = remediation.get("acceptedByMemberKind") or source_plan_remediation.get("acceptedByMemberKind")
    reviewed_evidence_ids = _string_list(remediation.get("reviewedEvidenceIds"))
    actionable_evidence_ids = _string_list(remediation.get("actionableEvidenceIds"))
    record = manifest_to_record(run)
    record_spec = record.setdefault("spec", {})
    if not isinstance(record_spec, dict):
        record["spec"] = record_spec = {}
    record_spec.update(
        {
            "connector": remediation.get("connector"),
            "sourceTaskPlan": task_plan_id,
            "sourceTaskPlanSubtask": remediation.get("sourceTaskPlanSubtask") if remediation.get("sourceTaskPlanSubtask") is not None else spec.get("sourceTaskPlanSubtask"),
            "task": task_id,
            "taskStatus": task_spec.get("status"),
            "taskPlanStatus": source_plan_spec.get("status") if source_plan_spec else None,
            "taskPlanAcceptedByMember": accepted_by_member,
            "taskPlanAcceptedByMemberKind": accepted_by_kind,
            "sourceSuggestion": remediation.get("sourceSuggestion"),
            "sourceCandidate": remediation.get("sourceCandidate"),
            "sourceReviewRequest": remediation.get("sourceReviewRequest"),
            "latestResolvedReviewRequest": remediation.get("latestResolvedReviewRequest"),
            "actionableEvidenceIds": actionable_evidence_ids,
            "reviewedEvidenceIds": reviewed_evidence_ids,
            "reviewedReviewRequests": _string_list(remediation.get("reviewedReviewRequests")),
            "evidenceReviewComplete": set(actionable_evidence_ids).issubset(set(reviewed_evidence_ids)),
            "evidenceCount": len(actionable_evidence_ids),
            "launchedByMember": remediation.get("launchedByMember") or spec.get("createdByMember"),
            "launchedByMemberKind": remediation.get("launchedByMemberKind") or spec.get("createdByMemberKind"),
            "launchedAt": remediation.get("launchedAt"),
            "selectedMember": spec.get("member"),
            "selectedAssignment": spec.get("assignment"),
            "selectedModelProfile": spec.get("modelProfile"),
            "memberKind": spec.get("memberKind") or _member_kind(index, spec.get("member")),
            "mode": spec.get("mode"),
            "status": spec.get("status"),
            "executionSummary": execution_plan.get("summary"),
            "executionRecommendedActions": execution_plan.get("recommendedActions", []),
            "executionActions": execution_plan.get("actions", {}),
            "modelReadinessStatus": model_readiness.get("status"),
            "modelReady": model_readiness.get("ready"),
            "modelReadinessBlockers": model_readiness.get("blockers", []),
            "modelReadinessWarnings": model_readiness.get("warnings", []),
            "workerReadinessStatus": worker_readiness.get("status"),
            "workerReady": worker_readiness.get("ready"),
            "workerReadinessBlockers": worker_readiness.get("blockers", []),
            "workerReadinessWarnings": worker_readiness.get("warnings", []),
            "workerAuthorizationStatus": worker_authorization.get("status"),
            "workerAuthorized": worker_authorization.get("ready"),
            "workerAuthorizationBlockers": worker_authorization.get("blockers", []),
            "workerAuthorizationWarnings": worker_authorization.get("warnings", []),
            "permissionApprovalRequired": permission_approval_required,
            "permissionApprovalRoute": "Permissions > Pending Requests" if permission_approval_required else None,
            "deniedPermissionActions": denied_permission_actions,
            "permissionRequests": permission_state["requests"],
            "pendingPermissionRequests": pending_permission_requests,
            "pendingPermissionRequestIds": [item["id"] for item in pending_permission_requests],
            "approvedPermissionRequests": permission_state["approvedRequests"],
            "approvedPermissionRequestIds": [item["id"] for item in permission_state["approvedRequests"]],
            "rejectedPermissionRequests": permission_state["rejectedRequests"],
            "rejectedPermissionRequestIds": [item["id"] for item in permission_state["rejectedRequests"]],
            "permissionGrants": permission_state["grants"],
            "activePermissionGrants": permission_state["activeGrants"],
            "activePermissionGrantIds": [item["id"] for item in permission_state["activeGrants"]],
            "expiredPermissionGrantIds": [item["id"] for item in permission_state["expiredGrants"]],
            "revokedPermissionGrantIds": [item["id"] for item in permission_state["revokedGrants"]],
            "permissionApprovalOutcome": permission_state["outcome"],
            "permissionOutcomeExplanation": permission_state["explanation"],
            "nextControlPlaneAction": _connector_remediation_run_next_action(
                record_spec,
                execution_plan=execution_plan,
                model_readiness=model_readiness,
                worker_readiness=worker_readiness,
                worker_authorization=worker_authorization,
                permission_approval_required=permission_approval_required,
                permission_state=permission_state,
            ),
        }
    )
    return record


def _connector_remediation_task_payloads(
    index: WorkspaceIndex,
    plan_payload: dict[str, Any],
    *,
    actor_member: str,
    accepted_at: datetime,
) -> list[dict[str, Any]]:
    spec = plan_payload.get("spec") if isinstance(plan_payload.get("spec"), dict) else {}
    remediation = spec.get("connectorRemediation") if isinstance(spec.get("connectorRemediation"), dict) else {}
    project_id = str(spec.get("project") or remediation.get("project") or index.project.object_id)
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    subtasks = spec.get("subtasks") if isinstance(spec.get("subtasks"), list) else []
    payloads: list[dict[str, Any]] = []
    for offset, subtask in enumerate(subtasks):
        if not isinstance(subtask, dict) or not subtask.get("title"):
            continue
        task_id = _next_task_id(index.workspace_root, accepted_at + timedelta(milliseconds=offset))
        assigned_member = subtask.get("assignedMember")
        assignment = subtask.get("assignment")
        if assigned_member and str(assigned_member) not in index.members:
            raise KeyError(f"unknown assigned member {assigned_member}")
        if assignment:
            assignment_record = index.assignments.get(str(assignment))
            if assignment_record is None:
                raise KeyError(f"unknown assignment {assignment}")
            if assignment_record.spec.project != project_id:
                raise ValueError(f"assignment {assignment} belongs to project {assignment_record.spec.project}, not {project_id}")
            if assigned_member and assignment_record.spec.member != str(assigned_member):
                raise ValueError(f"assignment {assignment} belongs to member {assignment_record.spec.member}, not {assigned_member}")
            assigned_member = assigned_member or assignment_record.spec.member
        payloads.append(
            {
                "apiVersion": "aiteamos.dev/v1alpha1",
                "kind": "Task",
                "metadata": {
                    "id": task_id,
                    "createdAt": accepted_at.isoformat(timespec="milliseconds"),
                },
                "spec": {
                    "title": str(subtask["title"]),
                    "project": project_id,
                    "assignedMember": assigned_member,
                    "assignment": assignment,
                    "status": "TODO",
                    "priority": str(subtask.get("priority") or "normal"),
                    "riskClass": "connector-remediation",
                    "executionMode": "assisted",
                    "acceptance": _string_list(subtask.get("acceptance")),
                    "relatedRuns": [],
                    "relatedReviews": [],
                    "reviewGates": _string_list(subtask.get("reviewGates")) + _string_list(spec.get("reviewGates")),
                    "risks": _string_list(subtask.get("risks")) + _string_list(spec.get("risks")),
                    "sourceTaskPlan": plan_payload.get("id") or (plan_payload.get("metadata") or {}).get("id"),
                    "sourceTaskPlanSubtask": offset,
                    "createdByMember": actor_member,
                    "connectorRemediation": {
                        "source": "connector-remediation-task-plan",
                        "taskPlan": plan_payload.get("id") or (plan_payload.get("metadata") or {}).get("id"),
                        "connector": remediation.get("connector"),
                        "sourceSuggestion": remediation.get("sourceSuggestion"),
                        "sourceCandidate": remediation.get("sourceCandidate"),
                        "sourceReviewRequest": remediation.get("sourceReviewRequest"),
                        "latestResolvedReviewRequest": remediation.get("latestResolvedReviewRequest"),
                        "actionableEvidenceIds": _string_list(remediation.get("actionableEvidenceIds")),
                    },
                },
            }
        )
    return payloads


def _connector_remediation_task_plan_matches(
    record: dict[str, Any],
    *,
    connector: str | None,
    project: str | None,
    member: str | None,
    assignment: str | None,
    status: str | None,
) -> bool:
    spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
    if connector is not None and spec.get("connector") != connector:
        return False
    if project is not None and spec.get("project") != project:
        return False
    if status is not None and spec.get("status") != status:
        return False
    if assignment is not None and assignment not in _string_list(spec.get("assignments")):
        return False
    if member is not None:
        member_refs = {
            spec.get("createdByMember"),
            spec.get("submittedByMember"),
            spec.get("latestDecisionActorMember"),
        }
        member_refs.update(_string_list(spec.get("assignedMembers")))
        if member not in member_refs:
            return False
    return True


def _connector_remediation_materialized_task_matches(
    record: dict[str, Any],
    *,
    connector: str | None,
    project: str | None,
    member: str | None,
    assignment: str | None,
    status: str | None,
    task_plan: str | None,
) -> bool:
    spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
    if connector is not None and spec.get("connector") != connector:
        return False
    if project is not None and spec.get("project") != project:
        return False
    if status is not None and spec.get("status") != status:
        return False
    if task_plan is not None and spec.get("sourceTaskPlan") != task_plan:
        return False
    if assignment is not None and spec.get("assignment") != assignment and spec.get("selectedAssignment") != assignment:
        return False
    if member is not None:
        member_refs = {
            spec.get("assignedMember"),
            spec.get("selectedMember"),
            spec.get("createdByMember"),
            spec.get("taskPlanAcceptedByMember"),
        }
        if member not in member_refs:
            return False
    return True


def _connector_remediation_run_matches(
    record: dict[str, Any],
    *,
    connector: str | None,
    project: str | None,
    member: str | None,
    assignment: str | None,
    status: str | None,
    task_plan: str | None,
    task: str | None,
) -> bool:
    spec = record.get("spec") if isinstance(record.get("spec"), dict) else {}
    if connector is not None and spec.get("connector") != connector:
        return False
    if project is not None and spec.get("project") != project:
        return False
    if status is not None and spec.get("status") != status:
        return False
    if task_plan is not None and spec.get("sourceTaskPlan") != task_plan:
        return False
    if task is not None and spec.get("task") != task:
        return False
    if assignment is not None and spec.get("assignment") != assignment and spec.get("selectedAssignment") != assignment:
        return False
    if member is not None:
        member_refs = {
            spec.get("member"),
            spec.get("selectedMember"),
            spec.get("createdByMember"),
            spec.get("launchedByMember"),
            spec.get("taskPlanAcceptedByMember"),
        }
        if member not in member_refs:
            return False
    return True


def _connector_remediation_task_plan_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "taskPlans": len(rows),
        "draft": sum(1 for row in rows if _row_spec(row).get("status") == "draft"),
        "accepted": sum(1 for row in rows if _row_spec(row).get("status") == "accepted"),
        "rejected": sum(1 for row in rows if _row_spec(row).get("status") == "rejected"),
        "superseded": sum(1 for row in rows if _row_spec(row).get("status") == "superseded"),
        "submittedByHuman": sum(1 for row in rows if _row_spec(row).get("submittedByMemberKind") == "human"),
        "submittedByDigital": sum(1 for row in rows if _row_spec(row).get("submittedByMemberKind") == "digital"),
        "submittedByHybrid": sum(1 for row in rows if _row_spec(row).get("submittedByMemberKind") == "hybrid"),
        "submittedByService": sum(1 for row in rows if _row_spec(row).get("submittedByMemberKind") == "service"),
        "withDecisionAudit": sum(1 for row in rows if _row_spec(row).get("latestDecision")),
        "withOpenReviewSource": sum(1 for row in rows if _row_spec(row).get("sourceReviewRequest")),
        "withPriorResolution": sum(1 for row in rows if _row_spec(row).get("latestResolvedReviewRequest")),
        "materialized": sum(1 for row in rows if _row_spec(row).get("createdTasks")),
        "createdTasks": sum(len(_string_list(_row_spec(row).get("createdTasks"))) for row in rows),
        "evidenceItems": sum(int(_row_spec(row).get("evidenceCount") or 0) for row in rows),
    }


def _connector_remediation_materialized_task_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "tasks": len(rows),
        "todo": sum(1 for row in rows if _row_spec(row).get("status") == "TODO"),
        "queued": sum(1 for row in rows if _row_spec(row).get("status") == "QUEUED"),
        "running": sum(1 for row in rows if _row_spec(row).get("status") == "RUNNING"),
        "review": sum(1 for row in rows if _row_spec(row).get("status") == "REVIEW"),
        "done": sum(1 for row in rows if _row_spec(row).get("status") == "DONE"),
        "failed": sum(1 for row in rows if _row_spec(row).get("status") == "FAILED"),
        "launchReady": sum(1 for row in rows if _row_spec(row).get("launchReady") is True),
        "launchBlocked": sum(1 for row in rows if _row_spec(row).get("launchReady") is not True),
        "readyToRun": sum(1 for row in rows if _row_spec(row).get("queueStatus") == "ready-to-run"),
        "needsMember": sum(1 for row in rows if _row_spec(row).get("queueStatus") == "needs-member"),
        "needsAssignment": sum(1 for row in rows if _row_spec(row).get("queueStatus") == "needs-assignment"),
        "needsExecutionProfile": sum(1 for row in rows if _row_spec(row).get("queueStatus") == "needs-execution-profile"),
        "needsModel": sum(1 for row in rows if _row_spec(row).get("queueStatus") == "needs-model"),
        "withRuns": sum(1 for row in rows if int(_row_spec(row).get("runCount") or 0) > 0),
        "assignedToHuman": sum(1 for row in rows if _row_spec(row).get("memberKind") == "human"),
        "assignedToDigital": sum(1 for row in rows if _row_spec(row).get("memberKind") == "digital"),
        "assignedToHybrid": sum(1 for row in rows if _row_spec(row).get("memberKind") == "hybrid"),
        "assignedToService": sum(1 for row in rows if _row_spec(row).get("memberKind") == "service"),
        "materializedByHuman": sum(1 for row in rows if _row_spec(row).get("taskPlanAcceptedByMemberKind") == "human"),
        "materializedByService": sum(1 for row in rows if _row_spec(row).get("taskPlanAcceptedByMemberKind") == "service"),
        "evidenceItems": sum(int(_row_spec(row).get("evidenceCount") or 0) for row in rows),
    }


def _connector_remediation_run_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "runs": len(rows),
        "ready": sum(1 for row in rows if _row_spec(row).get("status") == "READY"),
        "queued": sum(1 for row in rows if _row_spec(row).get("status") == "QUEUED"),
        "running": sum(1 for row in rows if _row_spec(row).get("status") == "RUNNING"),
        "testing": sum(1 for row in rows if _row_spec(row).get("status") == "TESTING"),
        "review": sum(1 for row in rows if _row_spec(row).get("status") == "REVIEW"),
        "done": sum(1 for row in rows if _row_spec(row).get("status") in {"DONE", "FINISHED"}),
        "failed": sum(1 for row in rows if _row_spec(row).get("status") == "FAILED"),
        "stalled": sum(1 for row in rows if _row_spec(row).get("status") == "STALLED"),
        "managedRuns": sum(1 for row in rows if _row_spec(row).get("mode") == "managed_llm"),
        "serviceRuns": sum(1 for row in rows if _row_spec(row).get("mode") == "service" or _row_spec(row).get("memberKind") == "service"),
        "assistedRuns": sum(1 for row in rows if _row_spec(row).get("mode") == "assisted"),
        "manualRuns": sum(1 for row in rows if _row_spec(row).get("mode") == "manual"),
        "readyForWorkerStart": sum(1 for row in rows if _row_spec(row).get("nextControlPlaneAction") == "ready-for-managed-worker-start"),
        "workerBlocked": sum(1 for row in rows if _row_spec(row).get("workerReadinessStatus") == "BLOCKED"),
        "authorizationBlocked": sum(1 for row in rows if _row_spec(row).get("workerAuthorizationStatus") == "BLOCKED"),
        "modelBlocked": sum(1 for row in rows if _row_spec(row).get("modelReadinessStatus") == "BLOCKED"),
        "permissionApprovalRequired": sum(1 for row in rows if _row_spec(row).get("permissionApprovalRequired") is True),
        "pendingPermissionRequests": sum(len(_row_spec(row).get("pendingPermissionRequests") or []) for row in rows),
        "approvedPermissionRequests": sum(len(_row_spec(row).get("approvedPermissionRequests") or []) for row in rows),
        "rejectedPermissionRequests": sum(len(_row_spec(row).get("rejectedPermissionRequests") or []) for row in rows),
        "activePermissionGrants": sum(len(_row_spec(row).get("activePermissionGrants") or []) for row in rows),
        "permissionPolicyStillBlocked": sum(1 for row in rows if _row_spec(row).get("permissionApprovalOutcome") == "approved-but-still-blocked"),
        "evidenceItems": sum(int(_row_spec(row).get("evidenceCount") or 0) for row in rows),
    }


def _connector_remediation_run_next_action(
    spec: dict[str, Any],
    *,
    execution_plan: dict[str, Any],
    model_readiness: dict[str, Any],
    worker_readiness: dict[str, Any],
    worker_authorization: dict[str, Any],
    permission_approval_required: bool,
    permission_state: dict[str, Any],
) -> str:
    status = str(spec.get("status") or "")
    mode = str(spec.get("mode") or "")
    member_kind = str(spec.get("memberKind") or "")
    if status in {"DONE", "FINISHED"}:
        return "none"
    if status == "REVIEW":
        return "review"
    if status in {"STALLED", "FAILED", "INTERRUPTED"}:
        return "inspect-recovery"
    if permission_approval_required:
        outcome = str(permission_state.get("outcome") or "request-required")
        if outcome == "pending":
            return "await-permission-approval"
        if outcome == "approved-but-still-blocked":
            return "review-permission-policy-blocker"
        if outcome == "rejected":
            return "review-rejected-permission-request"
        if outcome == "expired-or-revoked":
            return "refresh-expired-permission-grant"
        return "request-permission-approval"
    if mode == "service" or member_kind == "service":
        return "inspect-service-run-readiness"
    if mode == "managed_llm":
        if model_readiness.get("ready") and worker_readiness.get("ready") and worker_authorization.get("ready"):
            return "ready-for-managed-worker-start"
        return "resolve-worker-readiness"
    actions = execution_plan.get("actions") if isinstance(execution_plan.get("actions"), dict) else {}
    if actions.get("ingestAssisted"):
        return "assisted-ingest"
    return "inspect-run-execution-plan"


def _row_spec(row: dict[str, Any]) -> dict[str, Any]:
    spec = row.get("spec")
    return spec if isinstance(spec, dict) else {}


def _member_kind(index: WorkspaceIndex, member_id: Any) -> str | None:
    if not member_id:
        return None
    member = index.members.get(str(member_id))
    return member.spec.kind if member is not None else None


def _select_denied_permission_action(
    denied_permission_actions: list[dict[str, Any]],
    *,
    action_canonical: str | None,
    action_index: int | None,
) -> dict[str, Any]:
    if action_index is not None:
        if action_index < 0 or action_index >= len(denied_permission_actions):
            raise ValueError(f"actionIndex {action_index} is outside denied permission actions")
        return denied_permission_actions[action_index]
    if action_canonical:
        for decision in denied_permission_actions:
            if _permission_decision_action_canonical(decision) == action_canonical:
                return decision
        raise ValueError(f"denied permission action {action_canonical} was not found on the run")
    return denied_permission_actions[0]


def _pending_connector_remediation_permission_requests(
    index: WorkspaceIndex,
    *,
    run_id: str,
    member: Any,
    denied_permission_actions: list[dict[str, Any]],
    project: Any = None,
    assignment: Any = None,
) -> list[dict[str, Any]]:
    return _connector_remediation_permission_state(
        index,
        run_id=run_id,
        member=member,
        project=project,
        assignment=assignment,
        denied_permission_actions=denied_permission_actions,
    )["pendingRequests"]


def _connector_remediation_permission_state(
    index: WorkspaceIndex,
    *,
    run_id: str,
    member: Any,
    denied_permission_actions: list[dict[str, Any]],
    project: Any = None,
    assignment: Any = None,
) -> dict[str, Any]:
    action_canonicals = {
        canonical
        for canonical in (_permission_decision_action_canonical(decision) for decision in denied_permission_actions)
        if canonical
    }
    member_id = str(member) if member else None
    requests = _connector_remediation_permission_requests(
        index,
        run_id=run_id,
        member=member_id,
        action_canonicals=action_canonicals,
    )
    grants = _connector_remediation_permission_grants(
        index,
        run_id=run_id,
        member=member_id,
        project=str(project) if project else None,
        assignment=str(assignment) if assignment else None,
        action_canonicals=action_canonicals,
        requests=requests,
    )
    pending_requests = [item for item in requests if item.get("status") == "pending"]
    approved_requests = [item for item in requests if item.get("status") == "approved"]
    rejected_requests = [item for item in requests if item.get("status") == "rejected"]
    active_grants = [item for item in grants if item.get("effectiveStatus") == "active"]
    expired_grants = [item for item in grants if item.get("effectiveStatus") == "expired"]
    revoked_grants = [item for item in grants if item.get("effectiveStatus") == "revoked"]
    outcome, explanation = _connector_remediation_permission_outcome(
        action_canonicals=action_canonicals,
        pending_requests=pending_requests,
        approved_requests=approved_requests,
        rejected_requests=rejected_requests,
        active_grants=active_grants,
        expired_grants=expired_grants,
        revoked_grants=revoked_grants,
    )
    return {
        "actionCanonicals": sorted(action_canonicals),
        "requests": requests,
        "pendingRequests": pending_requests,
        "approvedRequests": approved_requests,
        "rejectedRequests": rejected_requests,
        "grants": grants,
        "activeGrants": active_grants,
        "expiredGrants": expired_grants,
        "revokedGrants": revoked_grants,
        "outcome": outcome,
        "explanation": explanation,
    }


def _connector_remediation_permission_requests(
    index: WorkspaceIndex,
    *,
    run_id: str,
    member: str | None,
    action_canonicals: set[str],
) -> list[dict[str, Any]]:
    if not member or not action_canonicals:
        return []
    rows: list[dict[str, Any]] = []
    for request in sorted(index.permission_requests.values(), key=lambda item: item.object_id):
        if request.spec.run != run_id or request.spec.member != member:
            continue
        request_action = request.spec.action.model_dump(mode="json", exclude_none=True)
        action_canonical = _permission_action_canonical(request_action)
        if action_canonical not in action_canonicals:
            continue
        row = manifest_to_record(request)
        row["actionCanonical"] = action_canonical
        row["status"] = request.spec.status
        row["grant"] = request.spec.grant
        row["decidedAt"] = request.spec.decidedAt
        row["reviewerMember"] = request.spec.reviewerMember
        rows.append(row)
    return rows


def _connector_remediation_permission_grants(
    index: WorkspaceIndex,
    *,
    run_id: str,
    member: str | None,
    project: str | None,
    assignment: str | None,
    action_canonicals: set[str],
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not action_canonicals:
        return []
    request_ids = {str(item["id"]) for item in requests if item.get("id")}
    rows: list[dict[str, Any]] = []
    for grant in sorted(index.permission_grants.values(), key=lambda item: item.object_id):
        grant_action = grant.spec.action.model_dump(mode="json", exclude_none=True)
        action_canonical = _permission_action_canonical(grant_action)
        if action_canonical not in action_canonicals:
            continue
        source_request = grant.spec.sourceRequest
        if source_request not in request_ids and not _connector_remediation_grant_scope_matches(grant.spec.scope, member=member, project=project, assignment=assignment):
            continue
        row = manifest_to_record(grant)
        row["actionCanonical"] = action_canonical
        row["sourceRequest"] = source_request
        row["effectiveStatus"] = _connector_remediation_permission_grant_effective_status(grant)
        rows.append(row)
    return rows


def _connector_remediation_grant_scope_matches(scope: dict[str, str], *, member: str | None, project: str | None, assignment: str | None) -> bool:
    if scope.get("project") and scope["project"] != project:
        return False
    if scope.get("member") and scope["member"] != member:
        return False
    if scope.get("assignment") and scope["assignment"] != assignment:
        return False
    return True


def _connector_remediation_permission_grant_effective_status(grant: Any) -> str:
    if grant.spec.status != "active":
        return grant.spec.status
    if not grant.spec.expiresAt:
        return "active"
    try:
        expires_at = datetime.fromisoformat(grant.spec.expiresAt)
    except ValueError:
        return "expired"
    now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
    return "active" if expires_at > now else "expired"


def _connector_remediation_permission_outcome(
    *,
    action_canonicals: set[str],
    pending_requests: list[dict[str, Any]],
    approved_requests: list[dict[str, Any]],
    rejected_requests: list[dict[str, Any]],
    active_grants: list[dict[str, Any]],
    expired_grants: list[dict[str, Any]],
    revoked_grants: list[dict[str, Any]],
) -> tuple[str, str]:
    if not action_canonicals:
        return "not-required", "No denied permission action is attached to this remediation run."
    if pending_requests:
        return "pending", "A PermissionRequest is pending in the normal Permissions review queue."
    if active_grants:
        return (
            "approved-but-still-blocked",
            "An active PermissionGrant exists, but the effective evaluator still blocks this action; review deny-first policy or action scope.",
        )
    if rejected_requests:
        return "rejected", "The latest matching remediation PermissionRequest was rejected by a human reviewer."
    if expired_grants or revoked_grants:
        return "expired-or-revoked", "A matching PermissionGrant exists but is expired or revoked."
    if approved_requests:
        return "approved-without-active-grant", "A matching PermissionRequest was approved, but no active grant is available."
    return "request-required", "No matching PermissionRequest or active PermissionGrant exists for the denied action."


def _pending_connector_remediation_permission_request(
    index: WorkspaceIndex,
    *,
    run_id: str,
    member: str | None,
    action_canonical: str | None,
) -> dict[str, Any] | None:
    if not member or not action_canonical:
        return None
    for request in sorted(index.permission_requests.values(), key=lambda item: item.object_id):
        if request.spec.status != "pending":
            continue
        if request.spec.run != run_id or request.spec.member != member:
            continue
        request_action = request.spec.action.model_dump(mode="json", exclude_none=True)
        if _permission_action_canonical(request_action) == action_canonical:
            return manifest_to_record(request)
    return None


def _permission_decision_action_canonical(decision: dict[str, Any]) -> str | None:
    action = decision.get("action") if isinstance(decision.get("action"), dict) else {}
    return _permission_action_canonical(action)


def _permission_action_canonical(action: dict[str, Any] | Any) -> str | None:
    data = action if isinstance(action, dict) else {}
    canonical = data.get("canonical")
    if canonical:
        return str(canonical)
    tool = str(data.get("tool") or data.get("name") or data.get("type") or "").strip()
    value = str(
        data.get("value")
        or data.get("path")
        or data.get("command")
        or data.get("url")
        or data.get("domain")
        or data.get("operation")
        or ""
    ).strip()
    if tool and value:
        return f"{tool}({value})"
    return tool or None




def _health_check_needs_reminder(check: Any) -> bool:
    return (
        check.spec.status != "healthy"
        or check.spec.readiness != "ready"
        or bool(check.spec.blockers)
        or bool(check.spec.warnings)
    )


def _provider_delivery_needs_reminder(delivery: Any) -> bool:
    return (
        delivery.spec.admissionStatus == "blocked"
        or delivery.spec.replayStatus in {"blocked", "stale"}
        or bool(delivery.spec.blockers)
        or bool(delivery.spec.warnings)
    )


def _health_check_reminder_candidate(index: WorkspaceIndex, check: Any) -> dict[str, Any]:
    severity = "blocked" if check.spec.status == "blocked" or check.spec.readiness == "blocked" or check.spec.blockers else "warning"
    recipients = _existing_members(index, [_connector_owner(index, check.spec.connector)])
    reason = _first_signal([*check.spec.blockers, *check.spec.warnings], check.spec.summary or f"Connector {check.spec.connector} health is {check.spec.status}.")
    dedupe_key = f"connector-health:{check.object_id}"
    return _reminder_candidate(
        candidate_id=dedupe_key,
        connector=check.spec.connector,
        project=check.spec.project or _connector_project(index, check.spec.connector),
        to_members=recipients,
        severity=severity,
        evidence_kind="ConnectorHealthCheck",
        evidence_id=check.object_id,
        status=check.spec.status,
        reason=reason,
        body=(
            f"Connector {check.spec.connector} needs attention. "
            f"Health status: {check.spec.status}; readiness: {check.spec.readiness}. {reason}"
        ),
        attachments=[check.object_id],
    )


def _provider_delivery_reminder_candidate(index: WorkspaceIndex, delivery: Any) -> dict[str, Any]:
    linked_automation = index.automations.get(delivery.spec.automation)
    severity = "blocked" if delivery.spec.admissionStatus == "blocked" or delivery.spec.replayStatus in {"blocked", "stale"} or delivery.spec.blockers else "warning"
    recipients = _existing_members(
        index,
        [
            _connector_owner(index, delivery.spec.connector),
            linked_automation.spec.ownerMember if linked_automation is not None else None,
            linked_automation.spec.serviceMember if linked_automation is not None else None,
        ],
    )
    reason = _first_signal([*delivery.spec.blockers, *delivery.spec.warnings], delivery.spec.summary or f"Provider delivery {delivery.object_id} is {delivery.spec.admissionStatus}.")
    dedupe_key = f"provider-delivery:{delivery.object_id}"
    return _reminder_candidate(
        candidate_id=dedupe_key,
        connector=delivery.spec.connector,
        project=delivery.spec.project,
        to_members=recipients,
        severity=severity,
        evidence_kind="AutomationProviderDelivery",
        evidence_id=delivery.object_id,
        status=delivery.spec.admissionStatus,
        reason=reason,
        body=(
            f"Provider delivery {delivery.spec.deliveryId} for connector {delivery.spec.connector or 'unbound'} needs attention. "
            f"Admission: {delivery.spec.admissionStatus}; replay: {delivery.spec.replayStatus}. {reason}"
        ),
        attachments=[delivery.object_id],
    )


def _reminder_candidate(
    *,
    candidate_id: str,
    connector: str | None,
    project: str | None,
    to_members: list[str],
    severity: str,
    evidence_kind: str,
    evidence_id: str,
    status: str,
    reason: str,
    body: str,
    attachments: list[str],
) -> dict[str, Any]:
    return {
        "id": candidate_id,
        "kind": "ConnectorFailureReminderCandidate",
        "spec": {
            "connector": connector,
            "project": project,
            "toMembers": to_members,
            "severity": severity,
            "priority": "urgent" if severity == "blocked" else "high",
            "evidenceKind": evidence_kind,
            "evidenceId": evidence_id,
            "status": status,
            "reason": reason,
            "body": body,
            "attachments": attachments,
            "dedupeKey": candidate_id,
            "existingMessage": None,
            "routable": bool(to_members),
        },
    }


def _escalation_candidate(
    *,
    candidate_id: str,
    connector: str,
    project: str,
    min_evidence: int,
) -> dict[str, Any]:
    return {
        "id": candidate_id,
        "kind": "ConnectorFailureEscalationCandidate",
        "spec": {
            "connector": connector,
            "project": project,
            "toMembers": [],
            "severity": "warning",
            "priority": "high",
            "evidenceCount": 0,
            "minEvidence": min_evidence,
            "evidenceIds": [],
            "evidenceKinds": [],
            "attachments": [],
            "reminderCandidates": [],
            "existingReminderMessages": [],
            "existingReviewRequest": None,
            "latestResolvedReviewRequest": None,
            "resolvedReviewRequest": None,
            "suppressedByResolution": False,
            "reviewedEvidenceIds": [],
            "unreviewedEvidenceIds": [],
            "reviewedReminderMessages": [],
            "resolutionReviewedAt": None,
            "resolutionReviewedByMember": None,
            "resolutionReviewerKind": None,
            "resolutionFollowUpReviewed": {},
            "resolutionCoversCurrentEvidence": False,
            "suppressionExplanation": None,
            "reasons": [],
            "body": "",
            "dedupeKey": candidate_id,
            "routable": False,
            "notRoutableReason": None,
        },
    }


def _escalation_body(spec: dict[str, Any]) -> str:
    reasons = "; ".join(str(item) for item in spec.get("reasons", [])[:3])
    reminder_note = ""
    if spec.get("existingReminderMessages"):
        reminder_note = f" Existing reminder messages: {', '.join(str(item) for item in spec['existingReminderMessages'])}."
    resolution_note = ""
    if spec.get("latestResolvedReviewRequest"):
        if spec.get("unreviewedEvidenceIds"):
            resolution_note = (
                f" Prior resolved review request {spec['latestResolvedReviewRequest']} covered "
                f"{len(spec.get('reviewedEvidenceIds', []))} current evidence item(s); "
                f"{len(spec.get('unreviewedEvidenceIds', []))} evidence item(s) still need review."
            )
        else:
            resolution_note = f" Prior resolved review request {spec['latestResolvedReviewRequest']} covered the current evidence set."
    return (
        f"Connector {spec.get('connector')} has repeated failure evidence and needs review. "
        f"Evidence count: {spec.get('evidenceCount')}; severity: {spec.get('severity')}. "
        f"{reasons or 'Review connector health and provider delivery evidence.'}{reminder_note} {resolution_note}".strip()
    )


def _remediation_suggestion(index: WorkspaceIndex, candidate: dict[str, Any]) -> dict[str, Any] | None:
    spec = candidate["spec"]
    if spec.get("suppressedByResolution"):
        return None
    if int(spec.get("evidenceCount") or 0) < int(spec.get("minEvidence") or 1):
        return None
    evidence_ids = _string_list(spec.get("evidenceIds"))
    actionable_evidence = _string_list(spec.get("unreviewedEvidenceIds")) or evidence_ids
    if not actionable_evidence:
        return None
    connector_id = str(spec.get("connector") or "unbound-provider-deliveries")
    project_id = str(spec.get("project") or index.project.object_id)
    owner_member = _connector_owner(index, connector_id)
    assigned_member = owner_member or next(iter(_string_list(spec.get("toMembers"))), None)
    suggested_assignment = _suggest_assignment(index, assigned_member, project_id)
    blockers: list[str] = []
    warnings: list[str] = []
    if not assigned_member:
        blockers.append("No connector owner or routable member is available for the remediation task plan.")
    if spec.get("existingReviewRequest"):
        warnings.append(f"Open connector failure review request {spec['existingReviewRequest']} should remain the review authority.")
    if spec.get("latestResolvedReviewRequest") and spec.get("unreviewedEvidenceIds"):
        warnings.append(f"Prior resolved review request {spec['latestResolvedReviewRequest']} did not cover the newly unreviewed evidence.")
    title = f"Diagnose {connector_id} connector failure evidence"
    evidence_refs = ", ".join(actionable_evidence)
    acceptance = [
        f"Review connector evidence ids: {evidence_refs}.",
        "Classify the failure as secret/configuration/provider-delivery/transient before proposing any fix.",
        "Document whether permission, connector policy, or automation policy follow-up is required.",
        "Do not mutate connector, permission, automation, review, or memory policy without a separate reviewed change.",
    ]
    proposed_plan = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "TaskPlan",
        "metadata": {"id": f"PLAN-PREVIEW-{_safe_id(candidate['id'])}"},
        "spec": {
            "goal": f"Plan remediation for {connector_id} connector failures in project {project_id}.",
            "project": project_id,
            "createdByMember": _suggest_manager_member(index),
            "status": "draft",
            "subtasks": [
                {
                    "title": title,
                    "assignedMember": assigned_member,
                    "assignment": suggested_assignment,
                    "priority": str(spec.get("priority") or "high"),
                    "acceptance": acceptance,
                    "risks": ["secret leakage", "connector policy drift", "permission escalation without review"],
                    "reviewGates": ["connector evidence review", "secret handling review", "permission policy review"],
                }
            ],
            "risks": ["secret leakage", "connector/provider drift", "review bypass"],
            "reviewGates": ["connector failure review request remains authoritative", "human/service approval before policy mutation"],
        },
    }
    return {
        "id": f"connector-remediation:{project_id}:{connector_id}",
        "kind": "ConnectorRemediationSuggestion",
        "spec": {
            "connector": connector_id,
            "project": project_id,
            "sourceCandidate": candidate["id"],
            "sourceReviewRequest": spec.get("existingReviewRequest"),
            "latestResolvedReviewRequest": spec.get("latestResolvedReviewRequest"),
            "evidenceIds": evidence_ids,
            "reviewedEvidenceIds": _string_list(spec.get("reviewedEvidenceIds")),
            "unreviewedEvidenceIds": _string_list(spec.get("unreviewedEvidenceIds")),
            "actionableEvidenceIds": actionable_evidence,
            "severity": spec.get("severity"),
            "priority": spec.get("priority"),
            "suggestedOwnerMember": assigned_member,
            "suggestedAssignment": suggested_assignment,
            "readyForTaskPlan": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "evidence": [_evidence_record(index, evidence_id) for evidence_id in actionable_evidence],
            "proposedTaskPlan": proposed_plan,
        },
    }


def _max_severity(left: str, right: str) -> str:
    return "blocked" if "blocked" in {left, right} else "warning"


def _existing_open_reminder(index: WorkspaceIndex, dedupe_key: str) -> str | None:
    for message in index.member_messages.values():
        if message.spec.audit.get("connectorReminderDedupeKey") != dedupe_key:
            continue
        if message.spec.status in {"open", "acknowledged"}:
            return message.object_id
    return None


def _existing_open_escalation(index: WorkspaceIndex, dedupe_key: str) -> str | None:
    for message in index.member_messages.values():
        if message.spec.audit.get("connectorEscalationDedupeKey") != dedupe_key:
            continue
        if message.spec.status in {"open", "acknowledged"}:
            return message.object_id
    return None


def _resolved_escalation_explanation(index: WorkspaceIndex, dedupe_key: str, evidence_ids: list[Any]) -> dict[str, Any] | None:
    required = set(_string_list(evidence_ids))
    if not required:
        return None
    for message in sorted(index.member_messages.values(), key=lambda item: item.object_id, reverse=True):
        if message.spec.audit.get("connectorEscalationDedupeKey") != dedupe_key:
            continue
        if message.spec.status != "resolved":
            continue
        resolution = message.spec.audit.get("connectorEscalationResolution")
        if not isinstance(resolution, dict):
            continue
        reviewed = set(_string_list(resolution.get("evidenceReviewed")))
        reviewed_current = sorted(required & reviewed)
        unreviewed = sorted(required - reviewed)
        follow_up = resolution.get("followUpReviewed")
        if not isinstance(follow_up, dict):
            follow_up = {}
        covers_current = not unreviewed
        if covers_current:
            explanation = "resolved review covers the current evidence set"
        else:
            explanation = f"{len(unreviewed)} current evidence item(s) were not part of the latest resolved review"
        return {
            "latestResolvedReviewRequest": message.object_id,
            "reviewedEvidenceIds": reviewed_current,
            "unreviewedEvidenceIds": unreviewed,
            "reviewedReminderMessages": _string_list(resolution.get("reminderMessagesReviewed")),
            "resolutionReviewedAt": resolution.get("resolvedAt") or message.spec.resolvedAt,
            "resolutionReviewedByMember": resolution.get("actorMember") or message.spec.resolvedByMember,
            "resolutionReviewerKind": resolution.get("actorMemberKind"),
            "resolutionFollowUpReviewed": follow_up,
            "resolutionCoversCurrentEvidence": covers_current,
            "suppressionExplanation": explanation,
        }
    return None


def _recent_connector_reminder(index: WorkspaceIndex, connector: str | None, throttle_minutes: int | None) -> str | None:
    if not connector or not throttle_minutes or throttle_minutes <= 0:
        return None
    threshold = datetime.now().astimezone() - timedelta(minutes=throttle_minutes)
    for message in sorted(index.member_messages.values(), key=lambda item: item.object_id):
        if message.spec.audit.get("source") != "connector-failure-reminder":
            continue
        if message.spec.audit.get("connector") != connector:
            continue
        if message.spec.status == "archived":
            continue
        created_at = _parse_manifest_time(message.metadata.createdAt)
        if created_at is not None and created_at >= threshold:
            return message.object_id
    return None


def _parse_manifest_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _existing_members(index: WorkspaceIndex, values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value in index.members and value not in result:
            result.append(value)
    return result


def _connector_project(index: WorkspaceIndex, connector_id: str | None) -> str | None:
    if connector_id is None:
        return None
    connector = index.connectors.get(connector_id)
    if connector is None or not connector.spec.projects:
        return None
    return connector.spec.projects[0]


def _first_signal(signals: list[str], fallback: str) -> str:
    return next((str(signal) for signal in signals if str(signal).strip()), fallback)


def _suggest_assignment(index: WorkspaceIndex, member_id: str | None, project_id: str) -> str | None:
    if not member_id:
        return None
    for assignment in sorted(index.assignments.values(), key=lambda item: item.object_id):
        if assignment.spec.member == member_id and assignment.spec.project == project_id and assignment.spec.status == "active":
            return assignment.object_id
    return None


def _suggest_manager_member(index: WorkspaceIndex) -> str | None:
    if "manager" in index.members:
        return "manager"
    for member_id, member in sorted(index.members.items()):
        capabilities = [item.lower() for item in member.spec.aboutMe.coreCapabilities]
        title = (member.spec.profile.title or "").lower()
        if "task decomposition" in capabilities or "manager" in title or "pm" in title:
            return member_id
    return None


def _evidence_record(index: WorkspaceIndex, evidence_id: str) -> dict[str, Any]:
    health = index.connector_health_checks.get(evidence_id)
    if health is not None:
        return {
            "id": evidence_id,
            "kind": "ConnectorHealthCheck",
            "connector": health.spec.connector,
            "status": health.spec.status,
            "readiness": health.spec.readiness,
            "blockers": list(health.spec.blockers),
            "warnings": list(health.spec.warnings),
            "summary": health.spec.summary,
        }
    delivery = index.automation_provider_deliveries.get(evidence_id)
    if delivery is not None:
        return {
            "id": evidence_id,
            "kind": "AutomationProviderDelivery",
            "connector": delivery.spec.connector,
            "automation": delivery.spec.automation,
            "admissionStatus": delivery.spec.admissionStatus,
            "replayStatus": delivery.spec.replayStatus,
            "blockers": list(delivery.spec.blockers),
            "warnings": list(delivery.spec.warnings),
            "summary": delivery.spec.summary,
        }
    return {"id": evidence_id, "kind": "unknown"}


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value).strip("-")


def _next_task_plan_id(workspace_root: Path, now: datetime) -> str:
    candidate = f"PLAN-{now.strftime('%Y%m%dT%H%M%S')}{now.microsecond // 1000:03d}"
    if not (workspace_root / "task_plans" / f"{candidate}.yaml").exists():
        return candidate
    for suffix in range(1, 1000):
        alternate = f"{candidate}-{suffix:03d}"
        if not (workspace_root / "task_plans" / f"{alternate}.yaml").exists():
            return alternate
    raise RuntimeError("could not allocate unique task plan id")


def _next_task_id(workspace_root: Path, now: datetime) -> str:
    for offset in range(1000):
        candidate = timestamp_task_id(now + timedelta(milliseconds=offset))
        if not (workspace_root / "tasks" / f"{candidate}.yaml").exists():
            return candidate
    raise RuntimeError("could not allocate unique task id")


def _normalize_subtask(index: WorkspaceIndex, value: Any, project_id: str) -> dict[str, Any]:
    if isinstance(value, str) and value.strip():
        return {"title": value.strip()}
    if not isinstance(value, dict) or not value.get("title"):
        raise ValueError("each connector remediation TaskPlan subtask must be an object with a title")
    result = deepcopy(value)
    _validate_subtask_refs(index, result, project_id)
    return result


def _validate_subtask_refs(index: WorkspaceIndex, subtask: dict[str, Any], project_id: str) -> None:
    member_id = subtask.get("assignedMember")
    assignment_id = subtask.get("assignment")
    if member_id and str(member_id) not in index.members:
        raise KeyError(f"unknown assigned member {member_id}")
    if assignment_id:
        assignment = index.assignments.get(str(assignment_id))
        if assignment is None:
            raise KeyError(f"unknown assignment {assignment_id}")
        if assignment.spec.project != project_id:
            raise ValueError(f"assignment {assignment_id} belongs to project {assignment.spec.project}, not {project_id}")
        if member_id and assignment.spec.member != str(member_id):
            raise ValueError(f"assignment {assignment_id} belongs to member {assignment.spec.member}, not {member_id}")


def _append_unique_text(target: dict[str, Any], key: str, value: str) -> None:
    existing = target.get(key)
    items = list(existing) if isinstance(existing, list) else []
    if value not in [str(item) for item in items]:
        items.append(value)
    target[key] = items


def _connector_matches_scope(connector_record: Any, *, connector: str | None, project: str | None, member: str | None) -> bool:
    if connector is not None and connector_record.object_id != connector:
        return False
    if project is not None and connector_record.spec.projects and project not in connector_record.spec.projects:
        return False
    if member is not None and connector_record.spec.ownerMember != member:
        return False
    return True


def _health_check_matches_scope(index: WorkspaceIndex, check: Any, *, connector: str | None, project: str | None, member: str | None) -> bool:
    if connector is not None and check.spec.connector != connector:
        return False
    linked_connector = index.connectors.get(check.spec.connector)
    if project is not None:
        if check.spec.project and check.spec.project != project:
            return False
        if not check.spec.project and linked_connector is not None and linked_connector.spec.projects and project not in linked_connector.spec.projects:
            return False
    if member is not None and (linked_connector is None or linked_connector.spec.ownerMember != member):
        return False
    return True


def _provider_delivery_matches_scope(index: WorkspaceIndex, delivery: Any, *, connector: str | None, project: str | None, member: str | None) -> bool:
    if connector is not None and delivery.spec.connector != connector:
        return False
    if project is not None and delivery.spec.project != project:
        return False
    if member is None:
        return True
    linked_connector = index.connectors.get(delivery.spec.connector or "")
    linked_automation = index.automations.get(delivery.spec.automation)
    member_refs = {
        linked_connector.spec.ownerMember if linked_connector is not None else None,
        linked_automation.spec.ownerMember if linked_automation is not None else None,
        linked_automation.spec.serviceMember if linked_automation is not None else None,
    }
    return member in member_refs


def _connector_owner(index: WorkspaceIndex, connector_id: str | None) -> str | None:
    if connector_id is None:
        return None
    connector = index.connectors.get(connector_id)
    return connector.spec.ownerMember if connector is not None else None


def _append_unique(spec: dict[str, Any], key: str, value: Any = None, *, from_value_list: Any = None) -> None:
    values = spec.setdefault(key, [])
    for item in _as_list(value, from_value_list=from_value_list):
        if item and item not in values:
            values.append(item)


def _as_list(value: Any = None, *, from_value_list: Any = None) -> list[Any]:
    source = from_value_list if from_value_list is not None else value
    if source is None:
        return []
    if isinstance(source, list):
        return source
    return [source]


def _sort_timestamp(*values: str | None) -> str:
    return next((str(value) for value in values if value), "")


def _strip_internal_sort_keys(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("sortKey", None)
