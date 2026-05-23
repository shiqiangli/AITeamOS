from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
from typing import Any

from aiteamos_schema import (
    Automation,
    AutomationApproval,
    AutomationProviderDelivery,
    AutomationRun,
    AutomationSchedulerLease,
    AutomationTriggerEvent,
    TaskPlan,
    timestamp_automation_approval_id,
    timestamp_automation_event_id,
    timestamp_automation_run_id,
)

from .audit import decision_audit_record, latest_decision_audit
from .approval_workflows import approval_workflow_id, write_subject_approval_workflow
from .artifact_retention import sweep_artifact_retention
from .connector_health import connector_health_admission_decision
from .connector_operations import route_connector_failure_reminders
from .git_activity import (
    git_activity_correlation_promotion_candidates,
    promote_git_activity_correlation_review,
    sweep_git_activity_retention,
)
from .io import read_yaml, write_yaml
from .loader import WorkspaceIndex, load_workspace, manifest_to_record
from .mutations import create_permission_request, create_run, create_task, record_member_message
from .permission_outcomes import denied_permission_decisions, permission_action_canonical, permission_outcome_state, select_permission_decision
from .permissions import edit_action, explain_effective_permissions


class _AutomationExecutionError(ValueError):
    def __init__(self, message: str, *, created_task: str | None = None) -> None:
        super().__init__(message)
        self.created_task = created_task


def create_automation(
    workspace_path: str | Path,
    *,
    name: str,
    target_type: str,
    target: dict[str, Any] | None = None,
    owner_member: str | None = None,
    service_member: str | None = None,
    project: str | None = None,
    triggers: list[dict[str, Any]] | None = None,
    dry_run: bool = True,
    status: str = "active",
    permission_policies: list[str] | None = None,
    approval_gates: list[str] | None = None,
) -> Automation:
    index = load_workspace(workspace_path)
    automation_id = _safe_manifest_id(name)
    if automation_id in index.automations:
        raise ValueError(f"automation {automation_id} already exists")
    project_id = project or index.project.object_id
    if project_id != index.project.object_id:
        raise KeyError(f"unknown project {project_id}")
    if owner_member and owner_member not in index.members:
        raise KeyError(f"unknown owner member {owner_member}")
    if service_member:
        member = index.members.get(service_member)
        if member is None:
            raise KeyError(f"unknown service member {service_member}")
        if member.spec.kind != "service":
            raise ValueError(f"automation service member {service_member} is {member.spec.kind}, not service")
    for policy in permission_policies or []:
        if policy not in index.permission_policies:
            raise KeyError(f"unknown permission policy {policy}")

    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "Automation",
        "metadata": {"name": automation_id},
        "spec": {
            "ownerMember": owner_member,
            "serviceMember": service_member,
            "project": project_id,
            "targetType": target_type,
            "target": target or {},
            "triggers": triggers or [{"triggerType": "manual"}],
            "dryRun": dry_run,
            "status": status,
            "permissionPolicies": permission_policies or [],
            "approvalGates": approval_gates or [],
        },
    }
    automation = Automation.model_validate(payload)
    automation_dir = index.workspace_root / "automations"
    automation_dir.mkdir(parents=True, exist_ok=True)
    write_yaml(automation_dir / f"{automation.object_id}.yaml", automation.model_dump(mode="json", exclude_none=True))
    return automation


def automation_run_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    automation_id: str | None = None,
) -> list[dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    runs = [
        run
        for run in index.automation_runs.values()
        if automation_id is None or run.spec.automation == automation_id
    ]
    records: list[dict[str, Any]] = []
    for run in sorted(runs, key=lambda item: item.object_id):
        record = manifest_to_record(run)
        latest_audit = latest_decision_audit(run.spec.decisionAudit)
        latest_risk = latest_audit.get("riskAssessment") or {}
        permission_member = _automation_permission_member(run)
        denied_decisions = denied_permission_decisions(list(run.spec.permissionDecisions))
        still_blocked = _automation_still_blocks_permission(index, run, permission_member, denied_decisions)
        permission_state = permission_outcome_state(
            index,
            member=permission_member,
            project=run.spec.project,
            automation=run.spec.automation,
            automation_run=run.object_id,
            permission_decisions=denied_decisions,
            still_blocked_when_active=still_blocked,
        )
        spec = record.setdefault("spec", {})
        if isinstance(spec, dict):
            spec.update(
                {
                    "permissionApprovalRequired": bool(denied_decisions),
                    "permissionRequests": permission_state["requests"],
                    "pendingPermissionRequests": permission_state["pendingRequests"],
                    "pendingPermissionRequestIds": [item["id"] for item in permission_state["pendingRequests"]],
                    "approvedPermissionRequestIds": [item["id"] for item in permission_state["approvedRequests"]],
                    "rejectedPermissionRequestIds": [item["id"] for item in permission_state["rejectedRequests"]],
                    "activePermissionGrantIds": [item["id"] for item in permission_state["activeGrants"]],
                    "expiredPermissionGrantIds": [item["id"] for item in permission_state["expiredGrants"]],
                    "revokedPermissionGrantIds": [item["id"] for item in permission_state["revokedGrants"]],
                    "permissionApprovalOutcome": permission_state["outcome"],
                    "permissionOutcomeExplanation": permission_state["explanation"],
                }
            )
        record["latestDecisionKind"] = latest_audit.get("decisionKind")
        record["latestDecision"] = latest_audit.get("decision")
        record["latestDecisionActorMember"] = latest_audit.get("actorMember")
        record["latestDecisionActorKind"] = latest_audit.get("actorMemberKind")
        record["latestRiskLevel"] = latest_risk.get("riskLevel")
        record["latestRiskRecommendedDecision"] = latest_risk.get("recommendedDecision")
        record["latestRiskRequiresHumanReview"] = latest_risk.get("requiresHumanReview")
        records.append(record)
    return records


def request_automation_run_permission(
    workspace_path: str | Path,
    automation_run_id: str,
    *,
    actor_member: str,
    action_canonical: str | None = None,
    action_index: int | None = None,
    reason: str | None = None,
    expires_at: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    actor = index.members.get(actor_member)
    if actor is None:
        raise KeyError(f"unknown actor member {actor_member}")
    if actor.spec.kind not in {"human", "service"}:
        raise ValueError("automation run permission requests require a human or governed service actor member")
    run = index.automation_runs.get(automation_run_id)
    if run is None:
        raise KeyError(f"unknown automation run {automation_run_id}")
    permission_member = _automation_permission_member(run)
    if not permission_member:
        raise ValueError(f"automation run {automation_run_id} has no service, owner, or requester member for permission review")
    denied_decisions = denied_permission_decisions(list(run.spec.permissionDecisions))
    if not denied_decisions:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "automationRun": manifest_to_record(run),
            "blockers": ["automation run has no denied permission actions"],
            "warnings": [],
        }
    selected_decision = select_permission_decision(
        denied_decisions,
        action_canonical=action_canonical,
        action_index=action_index,
    )
    action = selected_decision.get("action") if isinstance(selected_decision.get("action"), dict) else {}
    if not action:
        raise ValueError("selected permission decision has no action")
    current_decision = explain_effective_permissions(
        index,
        member=permission_member,
        project=run.spec.project,
        action=action,
        non_interactive=True,
    )
    canonical = permission_action_canonical(current_decision.get("normalizedAction") or action)
    if current_decision.get("decision") == "allow" and not current_decision.get("blockers"):
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "automationRun": manifest_to_record(run),
            "action": current_decision.get("normalizedAction") or action,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "permissionApprovalOutcome": "not-required",
            "blockers": [f"current effective permissions already allow {canonical}"],
            "warnings": [],
        }
    state = permission_outcome_state(
        index,
        member=permission_member,
        project=run.spec.project,
        automation=run.spec.automation,
        automation_run=run.object_id,
        permission_decisions=[selected_decision],
        still_blocked_when_active=True,
    )
    if state["pendingRequests"]:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "automationRun": manifest_to_record(run),
            "action": current_decision.get("normalizedAction") or action,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "existingRequest": state["pendingRequests"][0],
            "blockers": [f"pending PermissionRequest {state['pendingRequests'][0]['id']} already covers {canonical}"],
            "warnings": [],
        }
    if state["activeGrants"]:
        return {
            "dryRun": dry_run,
            "written": False,
            "canRequest": False,
            "automationRun": manifest_to_record(run),
            "action": current_decision.get("normalizedAction") or action,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "activePermissionGrants": state["activeGrants"],
            "permissionApprovalOutcome": "approved-but-still-blocked",
            "blockers": [f"active PermissionGrant already covers {canonical}, but effective deny-first policy still blocks this automation action"],
            "warnings": [],
        }
    request_preview = {
        "member": permission_member,
        "project": run.spec.project,
        "automation": run.spec.automation,
        "automationRun": run.object_id,
        "requesterMember": actor_member,
        "action": current_decision.get("normalizedAction") or action,
        "reason": reason or f"AutomationRun {run.object_id} needs approval for {canonical}.",
        "expiresAt": expires_at,
        "source": "automation-run-permission-request",
    }
    if dry_run:
        return {
            "dryRun": True,
            "written": False,
            "canRequest": True,
            "automationRun": manifest_to_record(run),
            "requestPreview": request_preview,
            "selectedPermissionDecision": selected_decision,
            "currentDecision": current_decision,
            "blockers": [],
            "warnings": [],
        }
    request = create_permission_request(
        workspace_path,
        member=permission_member,
        action=current_decision.get("normalizedAction") or action,
        project=run.spec.project,
        automation=run.spec.automation,
        automation_run=run.object_id,
        requester_member=actor_member,
        reason=reason or f"AutomationRun {run.object_id} needs approval for {canonical}.",
        expires_at=expires_at,
        current_decision=current_decision,
        source="automation-run-permission-request",
    )
    refreshed = load_workspace(workspace_path)
    return {
        "dryRun": False,
        "written": True,
        "canRequest": True,
        "automationRun": manifest_to_record(refreshed.automation_runs[automation_run_id]),
        "permissionRequest": manifest_to_record(request),
        "selectedPermissionDecision": selected_decision,
        "currentDecision": current_decision,
        "blockers": [],
        "warnings": [],
    }


def automation_approval_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    automation_run_id: str | None = None,
) -> list[dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    approvals = [
        approval
        for approval in index.automation_approvals.values()
        if automation_run_id is None or approval.spec.automationRun == automation_run_id
    ]
    return [manifest_to_record(approval) for approval in sorted(approvals, key=lambda item: item.object_id)]


def automation_trigger_event_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    automation_id: str | None = None,
) -> list[dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    events = [
        event
        for event in index.automation_trigger_events.values()
        if automation_id is None or event.spec.automation == automation_id
    ]
    return [manifest_to_record(event) for event in sorted(events, key=lambda item: item.object_id)]


def automation_provider_delivery_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    automation_id: str | None = None,
    connector: str | None = None,
) -> list[dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    deliveries = [
        delivery
        for delivery in index.automation_provider_deliveries.values()
        if (automation_id is None or delivery.spec.automation == automation_id)
        and (connector is None or delivery.spec.connector == connector)
    ]
    return [manifest_to_record(delivery) for delivery in sorted(deliveries, key=lambda item: item.object_id)]


def cleanup_automation_provider_deliveries(
    workspace_path: str | Path,
    *,
    actor_member: str | None = None,
    max_age_days: int = 30,
    dry_run: bool = False,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    if actor_member and actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    normalized_max_age = max(0, int(max_age_days))
    now = datetime.now().astimezone()
    cutoff = now - timedelta(days=normalized_max_age)

    archived: list[str] = []
    for delivery in sorted(index.automation_provider_deliveries.values(), key=lambda item: item.object_id):
        if delivery.spec.lifecycle == "archived":
            continue
        observed_at = _parse_manifest_timestamp(
            delivery.spec.lastSeenAt
            or delivery.spec.receivedAt
            or delivery.spec.firstSeenAt
            or delivery.metadata.createdAt
        )
        if observed_at is None or observed_at > cutoff:
            continue
        archived.append(delivery.object_id)
        if dry_run:
            continue
        retained_until = (observed_at + timedelta(days=normalized_max_age)).isoformat(timespec="milliseconds")
        data = delivery.model_dump(mode="json", exclude_none=True)
        spec = data.setdefault("spec", {})
        spec["lifecycle"] = "archived"
        spec["retainedUntil"] = retained_until
        spec["archivedAt"] = now.isoformat(timespec="milliseconds")
        spec.setdefault("warnings", [])
        if "archived by provider delivery retention cleanup" not in spec["warnings"]:
            spec["warnings"].append("archived by provider delivery retention cleanup")
        spec.setdefault("decisionAudit", []).append(
            decision_audit_record(
                index,
                decision_kind="system_check",
                decision="archived",
                actor_member=actor_member,
                authority="expire",
                reason="AutomationProviderDelivery exceeded retention window and was archived in place.",
                source="automation-provider-delivery-retention-cleanup",
                decided_at=now.isoformat(timespec="milliseconds"),
                evidence=[
                    {
                        "kind": "automation-provider-delivery",
                        "automationProviderDelivery": delivery.object_id,
                        "automation": delivery.spec.automation,
                        "connector": delivery.spec.connector,
                        "deliveryId": delivery.spec.deliveryId,
                        "lastSeenAt": delivery.spec.lastSeenAt,
                        "maxAgeDays": normalized_max_age,
                        "retainedUntil": retained_until,
                    }
                ],
            )
        )
        archived_delivery = AutomationProviderDelivery.model_validate(data)
        write_yaml(
            index.workspace_root / "automations" / "provider_deliveries" / f"{archived_delivery.object_id}.yaml",
            archived_delivery.model_dump(mode="json", exclude_none=True),
        )

    return {
        "archived": archived,
        "archivedCount": len(archived),
        "dryRun": dry_run,
        "scannedCount": len(index.automation_provider_deliveries),
        "cutoff": cutoff.isoformat(timespec="milliseconds"),
    }


def retry_provider_delivery(
    workspace_path: str | Path,
    delivery_id: str,
    *,
    actor_member: str,
    reason: str | None = None,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    raw_body: str | bytes | None = None,
    received_at: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    index = load_workspace(workspace_path)
    delivery = index.automation_provider_deliveries.get(delivery_id)
    if delivery is None:
        raise KeyError(f"unknown automation provider delivery {delivery_id}")
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    if delivery.spec.lifecycle == "archived":
        raise ValueError(f"automation provider delivery {delivery_id} is archived")
    if delivery.spec.admissionStatus == "accepted" and delivery.spec.replayStatus == "accepted" and not delivery.spec.blockers:
        raise ValueError(f"automation provider delivery {delivery_id} is already accepted")

    actor_kind = index.members[actor_member].spec.kind
    has_redelivery_payload = raw_body is not None or payload is not None
    if actor_kind == "digital" and has_redelivery_payload and not dry_run:
        delivery = _write_provider_delivery_retry(
            index,
            delivery,
            actor_member=actor_member,
            reason=reason,
            outcome="requested",
            dry_run=dry_run,
            blockers=["Digital members may recommend provider redelivery, but human/hybrid or governed service approval is required to admit it."],
        )
        return {
            "delivery": delivery,
            "retryDelivery": None,
            "event": None,
            "run": None,
            "admitted": False,
            "requested": True,
            "blockers": list(delivery.spec.blockers),
            "warnings": list(delivery.spec.warnings),
        }

    if not has_redelivery_payload:
        delivery = _write_provider_delivery_retry(
            index,
            delivery,
            actor_member=actor_member,
            reason=reason,
            outcome="requested",
            dry_run=dry_run,
        )
        return {
            "delivery": delivery,
            "retryDelivery": None,
            "event": None,
            "run": None,
            "admitted": False,
            "requested": True,
            "blockers": [],
            "warnings": [],
        }

    try:
        result = admit_external_automation_event(
            workspace_path,
            delivery.spec.automation,
            provider=delivery.spec.provider,
            event_type=delivery.spec.eventType,
            connector=delivery.spec.connector,
            headers=headers or {},
            payload=payload or {},
            raw_body=raw_body,
            actor_member=actor_member,
            received_at=received_at,
            dry_run=dry_run,
        )
    except ValueError as exc:
        refreshed = load_workspace(workspace_path)
        current_delivery = refreshed.automation_provider_deliveries.get(delivery_id, delivery)
        delivery = _write_provider_delivery_retry(
            refreshed,
            current_delivery,
            actor_member=actor_member,
            reason=reason,
            outcome="blocked",
            dry_run=dry_run,
            blockers=[str(exc)],
        )
        return {
            "delivery": delivery,
            "retryDelivery": None,
            "event": None,
            "run": None,
            "admitted": False,
            "requested": True,
            "blockers": [str(exc)],
            "warnings": list(delivery.spec.warnings),
        }

    refreshed = load_workspace(workspace_path)
    current_delivery = refreshed.automation_provider_deliveries.get(delivery_id, delivery)
    retry_delivery = result.get("delivery")
    event = result.get("event")
    run = result.get("run")
    delivery = _write_provider_delivery_retry(
        refreshed,
        current_delivery,
        actor_member=actor_member,
        reason=reason,
        outcome="admitted",
        dry_run=dry_run,
        retry_delivery=retry_delivery,
        event=event,
        run=run,
    )
    return {
        "delivery": delivery,
        "retryDelivery": retry_delivery,
        "event": event,
        "run": run,
        "admitted": bool(event),
        "requested": True,
        "blockers": [],
        "warnings": list(getattr(retry_delivery.spec, "warnings", []) if retry_delivery is not None else []),
    }


def automation_scheduler_lease_records(
    workspace_or_index: str | Path | WorkspaceIndex,
    *,
    automation_id: str | None = None,
) -> list[dict[str, Any]]:
    index = workspace_or_index if isinstance(workspace_or_index, WorkspaceIndex) else load_workspace(workspace_or_index)
    leases = [
        lease
        for lease in index.automation_scheduler_leases.values()
        if automation_id is None or lease.spec.automation == automation_id
    ]
    return [manifest_to_record(lease) for lease in sorted(leases, key=lambda item: item.object_id)]


def recover_scheduler_lease(
    workspace_path: str | Path,
    lease_id: str,
    *,
    actor_member: str,
    lease_seconds: int = 60,
    dry_run: bool = False,
    reason: str | None = None,
) -> dict[str, AutomationSchedulerLease | AutomationTriggerEvent | AutomationRun | None | bool]:
    index = load_workspace(workspace_path)
    lease = index.automation_scheduler_leases.get(lease_id)
    if lease is None:
        raise KeyError(f"unknown automation scheduler lease {lease_id}")
    if actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    if not lease.spec.schedulerId:
        raise ValueError(f"scheduler lease {lease_id} does not record schedulerId")
    if not lease.spec.tickKey:
        raise ValueError(f"scheduler lease {lease_id} does not record tickKey")
    payload = dict(lease.spec.audit.get("payload") or {}) if isinstance(lease.spec.audit, dict) else None
    return emit_scheduler_tick(
        workspace_path,
        lease.spec.automation,
        scheduler_id=lease.spec.schedulerId,
        tick_key=lease.spec.tickKey,
        due_at=lease.spec.dueAt,
        lease_seconds=lease_seconds,
        dry_run=dry_run,
        payload=payload,
        force_recover=True,
        recovery_actor_member=actor_member,
        recovery_reason=reason,
    )


def dry_run_automation(
    workspace_path: str | Path,
    automation_id: str,
    *,
    actor_member: str | None = None,
    source_event: dict[str, Any] | None = None,
) -> AutomationRun:
    return _create_automation_run(
        workspace_path,
        automation_id,
        actor_member=actor_member,
        source_event=source_event,
        force_dry_run=True,
    )


def trigger_automation(
    workspace_path: str | Path,
    automation_id: str,
    *,
    actor_member: str | None = None,
    source_event: dict[str, Any] | None = None,
) -> AutomationRun:
    return _create_automation_run(
        workspace_path,
        automation_id,
        actor_member=actor_member,
        source_event=source_event,
        force_dry_run=False,
    )


def ingest_automation_event(
    workspace_path: str | Path,
    automation_id: str,
    *,
    trigger_type: str = "manual",
    source: str = "manual",
    actor_member: str | None = None,
    payload: dict[str, Any] | None = None,
    dry_run: bool = False,
    dedupe_key: str | None = None,
) -> dict[str, AutomationTriggerEvent | AutomationRun | None]:
    index = load_workspace(workspace_path)
    if automation_id not in index.automations:
        raise KeyError(f"unknown automation {automation_id}")
    if actor_member and actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    for event in index.automation_trigger_events.values():
        if dedupe_key and event.spec.automation == automation_id and event.spec.dedupeKey == dedupe_key:
            run = index.automation_runs.get(event.spec.automationRun or "")
            return {"event": event, "run": run}

    now = datetime.now().astimezone()
    source_event = {
        "triggerType": trigger_type,
        "source": source,
        "dedupeKey": dedupe_key,
        "payload": dict(payload or {}),
    }
    if dry_run:
        run = dry_run_automation(
            workspace_path,
            automation_id,
            actor_member=actor_member,
            source_event=source_event,
        )
    else:
        run = trigger_automation(
            workspace_path,
            automation_id,
            actor_member=actor_member,
            source_event=source_event,
        )
    event_id = _next_automation_event_id(index.workspace_root, now)
    audit = decision_audit_record(
        index,
        decision_kind="system_check",
        decision="accepted",
        actor_member=actor_member,
        authority="record",
        reason="Automation trigger event ingested and linked to an AutomationRun.",
        source=f"automation-{source}-ingest",
        decided_at=now.isoformat(timespec="milliseconds"),
        evidence=[
            {
                "kind": "automation-trigger-event",
                "automation": automation_id,
                "triggerType": trigger_type,
                "automationRun": run.object_id,
                "dryRun": dry_run,
                "dedupeKey": dedupe_key,
            }
        ],
        requires_human_review=bool(run.spec.approvalGates),
    )
    event = AutomationTriggerEvent.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "AutomationTriggerEvent",
            "metadata": {
                "id": event_id,
                "createdAt": now.isoformat(timespec="milliseconds"),
            },
            "spec": {
                "automation": automation_id,
                "project": run.spec.project,
                "triggerType": trigger_type,
                "source": source,
                "actorMember": actor_member,
                "payload": dict(payload or {}),
                "dedupeKey": dedupe_key,
                "dryRun": dry_run,
                "status": "accepted",
                "automationRun": run.object_id,
                "receivedAt": now.isoformat(timespec="milliseconds"),
                "summary": f"Automation trigger event created run {run.object_id}.",
                "decisionAudit": [audit],
                "audit": {"sourceEvent": source_event},
            },
        }
    )
    write_yaml(
        index.workspace_root / "automations" / "events" / f"{event_id}.yaml",
        event.model_dump(mode="json", exclude_none=True),
    )
    return {"event": event, "run": run}


def admit_external_automation_event(
    workspace_path: str | Path,
    automation_id: str,
    *,
    provider: str = "generic",
    event_type: str | None = None,
    connector: str | None = None,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    raw_body: str | bytes | None = None,
    actor_member: str | None = None,
    received_at: str | None = None,
    dry_run: bool = False,
) -> dict[str, AutomationTriggerEvent | AutomationRun | AutomationProviderDelivery | None]:
    index = load_workspace(workspace_path)
    if automation_id not in index.automations:
        raise KeyError(f"unknown automation {automation_id}")
    if actor_member and actor_member not in index.members:
        raise KeyError(f"unknown actor member {actor_member}")
    automation = index.automations[automation_id]
    normalized_provider = provider.lower().strip() or "generic"
    normalized_headers = _normalize_headers(headers or {})
    raw = _raw_webhook_body(payload or {}, raw_body)
    selected_trigger_type = _external_trigger_type(normalized_provider, event_type)
    trigger = _select_external_trigger(automation.spec.triggers, selected_trigger_type, normalized_provider)
    if trigger is None:
        raise ValueError(f"automation {automation_id} has no matching external trigger for provider {normalized_provider}")
    trigger_config = dict(trigger.config or {})
    configured_connector = trigger_config.get("connector")
    connector_id = str(connector or configured_connector or "").strip() or None
    if connector and configured_connector and str(connector) != str(configured_connector):
        raise ValueError(f"webhook connector {connector} does not match trigger connector {configured_connector}")
    connector_manifest = _connector_for_external_admission(index, connector_id, normalized_provider, automation.spec.project)
    admission_config = _external_admission_config(connector_manifest, trigger_config)
    selected_trigger_type = trigger.triggerType
    event_name = event_type or _header(normalized_headers, admission_config.get("eventHeader") or _default_event_header(normalized_provider))
    delivery_id = (
        _header(normalized_headers, admission_config.get("deliveryHeader") or _default_delivery_header(normalized_provider))
        or str((payload or {}).get("deliveryId") or (payload or {}).get("id") or "")
        or _payload_digest(raw)
    )
    _verify_external_signature(
        normalized_provider,
        admission_config,
        normalized_headers,
        raw,
    )
    dedupe_key = f"{normalized_provider}:{event_name or selected_trigger_type}:{delivery_id}"
    payload_digest = hashlib.sha256(raw).hexdigest()
    safe_headers = _safe_external_headers(normalized_headers, normalized_provider, admission_config)
    delivery_record_id = _automation_provider_delivery_id(
        automation_id,
        normalized_provider,
        event_name or selected_trigger_type,
        delivery_id,
        connector_manifest.object_id if connector_manifest is not None else connector_id,
    )
    normalized_payload: dict[str, Any] = {}
    admission_warnings: list[str] = []
    try:
        normalized_payload = _normalize_provider_payload(normalized_provider, event_name or selected_trigger_type, payload or {})
        _validate_connector_external_event(connector_manifest, admission_config, normalized_headers, normalized_payload, received_at)
        health_decision = _connector_health_admission_decision(index, connector_manifest, admission_config)
        if health_decision:
            normalized_payload["connectorHealth"] = health_decision["record"]
            admission_warnings = list(health_decision["warnings"])
            if health_decision["blockers"]:
                raise ValueError("; ".join(health_decision["blockers"]))
    except ValueError as exc:
        _write_provider_delivery(
            index,
            delivery_record_id,
            automation_id=automation_id,
            automation_project=automation.spec.project,
            connector=connector_manifest.object_id if connector_manifest is not None else connector_id,
            provider=normalized_provider,
            event_type=event_name or selected_trigger_type,
            trigger_type=selected_trigger_type,
            delivery_id=delivery_id,
            dedupe_key=dedupe_key,
            payload_digest=payload_digest,
            received_at=received_at,
            replay_window_seconds=_replay_window_seconds(admission_config),
            replay_status=_replay_status_from_error(str(exc)),
            admission_status="blocked",
            normalized=normalized_payload,
            safe_headers=safe_headers,
            blockers=[str(exc)],
            warnings=admission_warnings,
            summary="Provider delivery blocked before AutomationTriggerEvent admission.",
            actor_member=actor_member,
        )
        raise
    existing_delivery = index.automation_provider_deliveries.get(delivery_record_id)
    if existing_delivery is not None:
        if existing_delivery.spec.payloadDigest != payload_digest:
            delivery = _write_provider_delivery(
                index,
                delivery_record_id,
                automation_id=automation_id,
                automation_project=automation.spec.project,
                connector=connector_manifest.object_id if connector_manifest is not None else connector_id,
                provider=normalized_provider,
                event_type=event_name or selected_trigger_type,
                trigger_type=selected_trigger_type,
                delivery_id=delivery_id,
                dedupe_key=dedupe_key,
                payload_digest=payload_digest,
                received_at=received_at,
                replay_window_seconds=_replay_window_seconds(admission_config),
                replay_status="blocked",
                admission_status="blocked",
                normalized=normalized_payload,
                safe_headers=safe_headers,
                warnings=admission_warnings,
                blockers=["Provider delivery id replay used a different payload digest."],
                summary="Provider delivery blocked because delivery id replay changed payload digest.",
                actor_member=actor_member,
            )
            raise ValueError(f"provider delivery {delivery.object_id} replay changed payload digest")
        if existing_delivery.spec.automationTriggerEvent:
            delivery = _write_provider_delivery(
                index,
                delivery_record_id,
                automation_id=automation_id,
                automation_project=automation.spec.project,
                connector=connector_manifest.object_id if connector_manifest is not None else connector_id,
                provider=normalized_provider,
                event_type=event_name or selected_trigger_type,
                trigger_type=selected_trigger_type,
                delivery_id=delivery_id,
                dedupe_key=dedupe_key,
                payload_digest=payload_digest,
                received_at=received_at,
                replay_window_seconds=_replay_window_seconds(admission_config),
                replay_status="duplicate",
                admission_status="duplicate",
                automation_trigger_event=existing_delivery.spec.automationTriggerEvent,
                automation_run=existing_delivery.spec.automationRun,
                normalized=normalized_payload,
                safe_headers=safe_headers,
                warnings=admission_warnings,
                summary="Provider delivery replay returned the existing AutomationTriggerEvent.",
                actor_member=actor_member,
            )
            return {
                "event": index.automation_trigger_events.get(existing_delivery.spec.automationTriggerEvent),
                "run": index.automation_runs.get(existing_delivery.spec.automationRun or ""),
                "delivery": delivery,
            }
        if existing_delivery.spec.admissionStatus == "blocked":
            _write_provider_delivery(
                index,
                delivery_record_id,
                automation_id=automation_id,
                automation_project=automation.spec.project,
                connector=connector_manifest.object_id if connector_manifest is not None else connector_id,
                provider=normalized_provider,
                event_type=event_name or selected_trigger_type,
                trigger_type=selected_trigger_type,
                delivery_id=delivery_id,
                dedupe_key=dedupe_key,
                payload_digest=payload_digest,
                received_at=received_at,
                replay_window_seconds=_replay_window_seconds(admission_config),
                replay_status="blocked",
                admission_status="blocked",
                normalized=normalized_payload,
                safe_headers=safe_headers,
                warnings=admission_warnings,
                blockers=["Provider delivery was previously blocked and requires a new delivery id."],
                summary="Provider delivery replay remained blocked.",
                actor_member=actor_member,
            )
            raise ValueError(f"provider delivery {existing_delivery.object_id} was previously blocked")
    admitted_payload = {
        "provider": normalized_provider,
        "connector": connector_manifest.object_id if connector_manifest is not None else connector_id,
        "eventType": event_name or selected_trigger_type,
        "deliveryId": delivery_id,
        "deliveryReceipt": delivery_record_id,
        "signatureVerified": True,
        "normalized": normalized_payload,
        "triggerConfig": _redact_external_payload(admission_config),
        "headers": safe_headers,
        "payload": _redact_external_payload(payload or {}),
    }
    if "connectorHealth" in normalized_payload:
        admitted_payload["connectorHealth"] = normalized_payload["connectorHealth"]
    result = ingest_automation_event(
        workspace_path,
        automation_id,
        trigger_type=selected_trigger_type,
        source="git_provider" if normalized_provider in {"github", "gitlab", "gitea", "forgejo"} else "webhook",
        actor_member=actor_member,
        payload=admitted_payload,
        dry_run=dry_run,
        dedupe_key=dedupe_key,
    )
    delivery = _write_provider_delivery(
        load_workspace(workspace_path),
        delivery_record_id,
        automation_id=automation_id,
        automation_project=automation.spec.project,
        connector=connector_manifest.object_id if connector_manifest is not None else connector_id,
        provider=normalized_provider,
        event_type=event_name or selected_trigger_type,
        trigger_type=selected_trigger_type,
        delivery_id=delivery_id,
        dedupe_key=dedupe_key,
        payload_digest=payload_digest,
        received_at=received_at,
        replay_window_seconds=_replay_window_seconds(admission_config),
        replay_status="accepted",
        admission_status="accepted",
        automation_trigger_event=result["event"].object_id if result.get("event") is not None else None,
        automation_run=result["run"].object_id if result.get("run") is not None else None,
        normalized=normalized_payload,
        safe_headers=safe_headers,
        warnings=admission_warnings,
        summary="Provider delivery admitted and linked to AutomationTriggerEvent.",
        actor_member=actor_member,
    )
    result["delivery"] = delivery
    return result


def emit_scheduler_tick(
    workspace_path: str | Path,
    automation_id: str,
    *,
    scheduler_id: str,
    tick_key: str,
    due_at: str | None = None,
    lease_seconds: int = 60,
    dry_run: bool = False,
    payload: dict[str, Any] | None = None,
    force_recover: bool = False,
    recovery_actor_member: str | None = None,
    recovery_reason: str | None = None,
) -> dict[str, AutomationSchedulerLease | AutomationTriggerEvent | AutomationRun | None | bool]:
    index = load_workspace(workspace_path)
    if automation_id not in index.automations:
        raise KeyError(f"unknown automation {automation_id}")
    if recovery_actor_member and recovery_actor_member not in index.members:
        raise KeyError(f"unknown actor member {recovery_actor_member}")
    automation = index.automations[automation_id]
    cron_triggers = [trigger for trigger in automation.spec.triggers if trigger.triggerType == "cron"]
    if not cron_triggers:
        raise ValueError(f"automation {automation_id} has no cron trigger")

    now = datetime.now().astimezone()
    lease_id = _automation_scheduler_lease_id(automation_id, tick_key)
    existing = index.automation_scheduler_leases.get(lease_id)
    if existing and existing.spec.automationTriggerEvent:
        if force_recover:
            raise ValueError(f"scheduler lease {lease_id} already emitted trigger event {existing.spec.automationTriggerEvent}")
        event = index.automation_trigger_events.get(existing.spec.automationTriggerEvent)
        run = index.automation_runs.get(existing.spec.automationRun or "")
        return {"lease": existing, "event": event, "run": run, "acquired": False}
    existing_expired = bool(existing and _lease_expired(existing.spec.leaseExpiresAt, now))
    recoverable_existing = bool(existing and (existing_expired or existing.spec.status in {"blocked", "expired", "skipped"}))
    if force_recover:
        if existing is None:
            raise KeyError(f"unknown automation scheduler lease {lease_id}")
        if not recoverable_existing:
            raise ValueError(f"scheduler lease {lease_id} is not recoverable while status is {existing.spec.status}")
    if existing and not existing_expired and not (force_recover and recoverable_existing):
        return {"lease": existing, "event": None, "run": None, "acquired": False}

    lease_expires_at = now + timedelta(seconds=max(1, min(int(lease_seconds or 60), 3600)))
    dedupe_key = f"scheduler:{automation_id}:{tick_key}"
    trigger_config = cron_triggers[0].config
    prior_audit = list(existing.spec.decisionAudit) if existing and force_recover else []
    recovery_audit: dict[str, Any] | None = None
    if existing and force_recover:
        actor_kind = index.members.get(recovery_actor_member).spec.kind if recovery_actor_member else None
        if actor_kind in {"human", "hybrid"}:
            decision_kind = "human_approval"
            authority = "approve"
        elif actor_kind == "service":
            decision_kind = "service_policy_decision"
            authority = "enforce"
        else:
            decision_kind = "system_check"
            authority = "record"
        recovery_audit = decision_audit_record(
            index,
            decision_kind=decision_kind,
            decision="recovered",
            actor_member=recovery_actor_member,
            authority=authority,
            reason=recovery_reason or "Recovered a blocked or expired scheduler lease before re-emitting the cron tick.",
            source="automation-scheduler-lease-recovery",
            decided_at=now.isoformat(timespec="milliseconds"),
            evidence=[
                {
                    "kind": "automation-scheduler-lease",
                    "automation": automation_id,
                    "schedulerId": existing.spec.schedulerId,
                    "tickKey": existing.spec.tickKey,
                    "previousStatus": existing.spec.status,
                    "previousLeaseExpiresAt": existing.spec.leaseExpiresAt,
                    "dedupeKey": dedupe_key,
                }
            ],
            requires_human_review=actor_kind not in {"human", "hybrid"},
        )
    lease_audit = decision_audit_record(
        index,
        decision_kind="system_check",
        decision="leased",
        actor_member=recovery_actor_member if force_recover else automation.spec.serviceMember or automation.spec.ownerMember,
        authority="record",
        reason="Scheduler recovered and acquired a cron tick lease before emitting an AutomationTriggerEvent."
        if force_recover
        else "Scheduler acquired a cron tick lease before emitting an AutomationTriggerEvent.",
        source="automation-scheduler-lease-recovery" if force_recover else "automation-scheduler",
        decided_at=now.isoformat(timespec="milliseconds"),
        evidence=[
            {
                "kind": "automation-scheduler-lease",
                "automation": automation_id,
                "schedulerId": scheduler_id,
                "tickKey": tick_key,
                "dedupeKey": dedupe_key,
            }
        ],
    )
    lease = AutomationSchedulerLease.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "AutomationSchedulerLease",
            "metadata": {
                "id": lease_id,
                "createdAt": existing.metadata.createdAt if existing else now.isoformat(timespec="milliseconds"),
            },
            "spec": {
                "automation": automation_id,
                "project": automation.spec.project,
                "schedulerId": scheduler_id,
                "tickKey": tick_key,
                "cron": str(trigger_config.get("cron") or trigger_config.get("schedule") or ""),
                "dueAt": due_at or now.isoformat(timespec="milliseconds"),
                "leaseAcquiredAt": now.isoformat(timespec="milliseconds"),
                "leaseExpiresAt": lease_expires_at.isoformat(timespec="milliseconds"),
                "heartbeatAt": now.isoformat(timespec="milliseconds"),
                "status": "leased",
                "dedupeKey": dedupe_key,
                "summary": "Scheduler lease recovered; trigger event emission is pending."
                if force_recover
                else "Scheduler lease acquired; trigger event emission is pending.",
                "decisionAudit": [*prior_audit, *([recovery_audit] if recovery_audit else []), lease_audit],
                "audit": {
                    "triggerConfig": trigger_config,
                    "payload": dict(payload or {}),
                    "recoveredFromStatus": existing.spec.status if existing and force_recover else None,
                },
            },
        }
    )
    _write_scheduler_lease(index.workspace_root, lease)

    try:
        event_result = ingest_automation_event(
            workspace_path,
            automation_id,
            trigger_type="cron",
            source="scheduler",
            actor_member=recovery_actor_member if force_recover else None,
            payload={
                "schedulerId": scheduler_id,
                "tickKey": tick_key,
                "dueAt": due_at or now.isoformat(timespec="milliseconds"),
                "triggerConfig": trigger_config,
                "recoveredLease": existing.object_id if existing and force_recover else None,
                **dict(payload or {}),
            },
            dry_run=dry_run,
            dedupe_key=dedupe_key,
        )
        event = event_result["event"]
        run = event_result["run"]
        data = lease.model_dump(mode="json", exclude_none=True)
        data["spec"]["status"] = "emitted"
        data["spec"]["automationTriggerEvent"] = event.object_id if event is not None else None
        data["spec"]["automationRun"] = run.object_id if run is not None else None
        data["spec"]["summary"] = (
            "Scheduler lease recovery emitted a deduplicated AutomationTriggerEvent."
            if force_recover
            else "Scheduler lease emitted a deduplicated AutomationTriggerEvent."
        )
        data["spec"]["decisionAudit"].append(
            decision_audit_record(
                load_workspace(workspace_path),
                decision_kind="system_check",
                decision="emitted",
                actor_member=recovery_actor_member if force_recover else automation.spec.serviceMember or automation.spec.ownerMember,
                authority="record",
                reason="Scheduler recovery emitted AutomationTriggerEvent for the leased cron tick."
                if force_recover
                else "Scheduler emitted AutomationTriggerEvent for the leased cron tick.",
                source="automation-scheduler-lease-recovery" if force_recover else "automation-scheduler",
                decided_at=datetime.now().astimezone().isoformat(timespec="milliseconds"),
                evidence=[
                    {
                        "kind": "automation-scheduler-lease",
                        "automation": automation_id,
                        "tickKey": tick_key,
                        "automationTriggerEvent": event.object_id if event is not None else None,
                        "automationRun": run.object_id if run is not None else None,
                    }
                ],
                requires_human_review=bool(run and run.spec.approvalGates),
            )
        )
        emitted = AutomationSchedulerLease.model_validate(data)
        _write_scheduler_lease(index.workspace_root, emitted)
        return {"lease": emitted, "event": event, "run": run, "acquired": True}
    except Exception as exc:
        data = lease.model_dump(mode="json", exclude_none=True)
        data["spec"]["status"] = "blocked"
        data["spec"].setdefault("blockers", []).append(str(exc))
        data["spec"]["summary"] = (
            "Scheduler lease recovery blocked before trigger event emission."
            if force_recover
            else "Scheduler lease blocked before trigger event emission."
        )
        blocked = AutomationSchedulerLease.model_validate(data)
        _write_scheduler_lease(index.workspace_root, blocked)
        raise


def scan_cron_scheduler(
    workspace_path: str | Path,
    *,
    scheduler_id: str,
    tick_key: str | None = None,
    due_at: str | None = None,
    lease_seconds: int = 60,
    dry_run: bool = False,
) -> list[dict[str, AutomationSchedulerLease | AutomationTriggerEvent | AutomationRun | None | bool]]:
    index = load_workspace(workspace_path)
    now = datetime.now().astimezone()
    resolved_tick = tick_key or now.strftime("%Y%m%dT%H%M")
    results = []
    for automation in sorted(index.automations.values(), key=lambda item: item.object_id):
        if automation.spec.status != "active":
            continue
        if not any(trigger.triggerType == "cron" for trigger in automation.spec.triggers):
            continue
        results.append(
            emit_scheduler_tick(
                workspace_path,
                automation.object_id,
                scheduler_id=scheduler_id,
                tick_key=resolved_tick,
                due_at=due_at or now.isoformat(timespec="milliseconds"),
                lease_seconds=lease_seconds,
                dry_run=dry_run,
            )
        )
    return results


def approve_automation_run(
    workspace_path: str | Path,
    automation_run_id: str,
    *,
    reviewer_member: str,
    reason: str | None = None,
    expires_at: str | None = None,
) -> AutomationRun:
    return _review_automation_run(
        workspace_path,
        automation_run_id,
        reviewer_member=reviewer_member,
        decision="approved",
        reason=reason,
        expires_at=expires_at,
    )


def reject_automation_run(
    workspace_path: str | Path,
    automation_run_id: str,
    *,
    reviewer_member: str,
    reason: str | None = None,
) -> AutomationRun:
    return _review_automation_run(
        workspace_path,
        automation_run_id,
        reviewer_member=reviewer_member,
        decision="rejected",
        reason=reason,
        expires_at=None,
    )


def _review_automation_run(
    workspace_path: str | Path,
    automation_run_id: str,
    *,
    reviewer_member: str,
    decision: str,
    reason: str | None,
    expires_at: str | None,
) -> AutomationRun:
    index = load_workspace(workspace_path)
    if automation_run_id not in index.automation_runs:
        raise KeyError(f"unknown automation run {automation_run_id}")
    if reviewer_member not in index.members:
        raise KeyError(f"unknown reviewer member {reviewer_member}")
    reviewer = index.members[reviewer_member]
    if reviewer.spec.kind != "human":
        raise ValueError("automation approval requires a human reviewer member")
    run = index.automation_runs[automation_run_id]
    if run.spec.status != "pending-approval":
        raise ValueError(f"automation run {automation_run_id} is {run.spec.status}, not pending-approval")
    if run.spec.automation not in index.automations:
        raise KeyError(f"unknown automation {run.spec.automation}")

    now = datetime.now().astimezone()
    decided_at = now.isoformat(timespec="milliseconds")
    approval_id = _next_automation_approval_id(index.workspace_root, now)
    approval_gates = list(run.spec.approvalGates)
    approval_expires_at = expires_at
    if decision == "approved" and approval_expires_at is None:
        approval_expires_at = (now + timedelta(hours=24)).isoformat(timespec="milliseconds")
    audit = decision_audit_record(
        index,
        decision_kind="human_approval",
        decision=decision,
        actor_member=reviewer_member,
        authority="approve",
        reason=reason or f"automation run {decision}",
        source="automation-run-approval",
        decided_at=decided_at,
        evidence=[
            {
                "kind": "automation-run",
                "automationRun": automation_run_id,
                "automation": run.spec.automation,
                "approvalGates": approval_gates,
                "targetType": run.spec.targetType,
            }
        ],
        requires_human_review=False,
        metadata={"automationApproval": approval_id},
    )
    approval = AutomationApproval.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "AutomationApproval",
            "metadata": {
                "id": approval_id,
                "createdAt": decided_at,
            },
            "spec": {
                "automationRun": automation_run_id,
                "automation": run.spec.automation,
                "project": run.spec.project,
                "approvalWorkflow": approval_workflow_id("AutomationApproval", approval_id),
                "reviewerMember": reviewer_member,
                "reviewerKind": reviewer.spec.kind,
                "decision": decision,
                "approvalGates": approval_gates,
                "reason": reason,
                "decidedAt": decided_at,
                "expiresAt": approval_expires_at,
                "decisionAudit": [audit],
                "audit": {"source": "automation-run-review"},
            },
        }
    )
    workflow_decision_audit = [
        item.model_dump(mode="json", exclude_none=True)
        for item in run.spec.decisionAudit
    ] + [item.model_dump(mode="json", exclude_none=True) for item in approval.spec.decisionAudit]
    write_subject_approval_workflow(
        index,
        subject_kind="AutomationApproval",
        subject_ref=approval.object_id,
        project=approval.spec.project,
        requester_member=run.spec.requestedByMember,
        owner_member=reviewer_member,
        status=decision,
        stage_id="automation-approval",
        stage_kind="every-of",
        reviewer_members=[reviewer_member],
        approvals=[approval.object_id] if decision == "approved" else [],
        decision_audit=workflow_decision_audit,
        subject_record=approval.model_dump(mode="json", exclude_none=True),
        reason=reason,
        decided_at=decided_at,
    )

    run_path = index.workspace_root / "automations" / "runs" / f"{automation_run_id}.yaml"
    run_data = read_yaml(run_path)
    spec = run_data.setdefault("spec", {})
    spec.setdefault("decisionAudit", []).append(audit)
    spec.setdefault("approvals", []).append(approval_id)
    if decision == "approved":
        spec["status"] = "queued"
        spec["approvalGates"] = []
        spec["summary"] = "Automation trigger approved and queued for executor pickup."
    else:
        spec["status"] = "blocked"
        spec["finishedAt"] = decided_at
        spec["summary"] = "Automation trigger rejected by human reviewer."
        spec.setdefault("blockers", []).append(reason or "Automation approval rejected.")
    updated = AutomationRun.model_validate(run_data)
    write_yaml(run_path, updated.model_dump(mode="json", exclude_none=True))
    return updated


def execute_automation_run(
    workspace_path: str | Path,
    automation_run_id: str,
    *,
    actor_member: str | None = None,
) -> AutomationRun:
    index = load_workspace(workspace_path)
    if automation_run_id not in index.automation_runs:
        raise KeyError(f"unknown automation run {automation_run_id}")
    run = index.automation_runs[automation_run_id]
    if run.spec.status != "queued":
        raise ValueError(f"automation run {automation_run_id} is {run.spec.status}, not queued")
    if run.spec.dryRun:
        raise ValueError(f"automation run {automation_run_id} is dry-run only")
    if run.spec.automation not in index.automations:
        raise KeyError(f"unknown automation {run.spec.automation}")

    now = datetime.now().astimezone()
    executor_member = actor_member or run.spec.serviceMember or run.spec.ownerMember or run.spec.requestedByMember
    blockers = list(run.spec.blockers)
    warnings = list(run.spec.warnings)
    logs = list(run.spec.logs)
    permission_decisions = list(run.spec.permissionDecisions)
    decision_audit = _decision_audit_payloads(run.spec.decisionAudit)

    if not executor_member:
        blockers.append("Automation run has no actor, service member, owner member, or requester member for execution.")
    elif executor_member not in index.members:
        blockers.append(f"Executor member {executor_member} does not exist.")
    if run.spec.approvalGates:
        blockers.append("Automation run still has approval gates and cannot be executed without an approval record.")
    blockers.extend(_approval_blockers(index, run, now))

    if executor_member and executor_member in index.members:
        permission_decision = explain_effective_permissions(
            index,
            member=executor_member,
            project=run.spec.project,
            action={
                "tool": "Automation",
                "target": f"{run.spec.targetType}:{run.spec.automation}",
            },
            non_interactive=True,
        )
        permission_summary = _permission_decision_summary(permission_decision)
        permission_decisions.append(permission_summary)
        decision_audit.append(
            decision_audit_record(
                index,
                decision_kind="service_policy_decision",
                decision=str(permission_decision.get("decision") or "pending"),
                actor_member=executor_member,
                authority="enforce",
                reason=str(permission_decision.get("reason") or "automation executor permission evaluated"),
                source="automation-executor-permission-evaluator",
                policy_refs=list(permission_decision.get("selectedPolicyIds") or []),
                evidence=[
                    {
                        "kind": "permission-explain",
                        "automation": run.spec.automation,
                        "automationRun": automation_run_id,
                        "action": permission_summary.get("action"),
                        "matchedRules": permission_decision.get("matchedRules", []),
                        "matchedGrants": permission_decision.get("matchedGrants", []),
                        "blockers": permission_decision.get("blockers", []),
                        "warnings": permission_decision.get("warnings", []),
                    }
                ],
                requires_human_review=False,
                risk_assessment=permission_decision.get("riskAssessment"),
            )
        )
        if permission_decision["decision"] != "allow" or permission_decision["blockers"]:
            blockers.append(
                f"Automation executor permission denied for {executor_member}: {permission_decision['reason']}."
            )
        for output_path in _automation_output_permission_paths(run):
            output_decision = explain_effective_permissions(
                index,
                member=executor_member,
                project=run.spec.project,
                action=edit_action(output_path),
                non_interactive=True,
            )
            output_summary = _permission_decision_summary(output_decision)
            permission_decisions.append(output_summary)
            decision_audit.append(
                decision_audit_record(
                    index,
                    decision_kind="service_policy_decision",
                    decision=str(output_decision.get("decision") or "pending"),
                    actor_member=executor_member,
                    authority="enforce",
                    reason=str(output_decision.get("reason") or "automation output permission evaluated"),
                    source="automation-output-permission-evaluator",
                    policy_refs=list(output_decision.get("selectedPolicyIds") or []),
                    evidence=[
                        {
                            "kind": "permission-explain",
                            "automation": run.spec.automation,
                            "automationRun": automation_run_id,
                            "outputPath": output_path,
                            "action": output_summary.get("action"),
                            "matchedRules": output_decision.get("matchedRules", []),
                            "matchedGrants": output_decision.get("matchedGrants", []),
                            "blockers": output_decision.get("blockers", []),
                            "warnings": output_decision.get("warnings", []),
                        }
                    ],
                    requires_human_review=False,
                    risk_assessment=output_decision.get("riskAssessment"),
                )
            )
            if output_decision["decision"] != "allow" or output_decision["blockers"]:
                blockers.append(
                    f"Automation output permission denied for {executor_member} on {output_path}: {output_decision['reason']}."
                )

    if blockers:
        decision_audit.append(
            decision_audit_record(
                index,
                decision_kind="system_check",
                decision="blocked",
                actor_member=executor_member,
                authority="record",
                reason="Automation executor blocked before side effects.",
                source="automation-executor",
                evidence=[{"kind": "automation-run", "automationRun": automation_run_id}],
                requires_human_review=True,
            )
        )
        logs.append("Executor blocked before side effects.")
        return _write_automation_run_update(
            index,
            automation_run_id,
            status="blocked",
            finished_at=now.isoformat(timespec="milliseconds"),
            summary="Automation executor blocked by approval or permission gates.",
            permission_decisions=permission_decisions,
            decision_audit=decision_audit,
            blockers=blockers,
            warnings=warnings,
            logs=logs,
        )

    created_task: str | None = run.spec.createdTask
    created_run: str | None = run.spec.createdRun
    created_task_plan: str | None = run.spec.createdTaskPlan
    created_message: str | None = run.spec.createdMessage

    try:
        if run.spec.targetType == "human_reminder":
            message = _execute_human_reminder(index, run, executor_member=executor_member)
            created_message = message.object_id
            logs.append(f"Created member message {created_message}.")
        elif run.spec.targetType == "task_planning":
            plan = _execute_task_plan(index, run, executor_member=executor_member, now=now)
            created_task_plan = plan.object_id
            logs.append(f"Created task plan {created_task_plan}.")
        elif run.spec.targetType == "manager_recommendation":
            message, plan = _execute_manager_recommendation(index, run, executor_member=executor_member, now=now)
            created_message = message.object_id
            if plan is not None:
                created_task_plan = plan.object_id
                logs.append(f"Created manager recommendation task plan {created_task_plan}.")
            logs.append(f"Created manager recommendation message {created_message}.")
        elif run.spec.targetType == "connector_failure_reminder":
            result = _execute_connector_failure_reminders(index, run, executor_member=executor_member)
            messages = result.get("createdMessages") or []
            if messages:
                created_message = str(messages[0].get("id") or created_message)
            logs.append(
                "Routed "
                f"{result.get('summary', {}).get('createdMessages', 0)} connector failure reminder message(s); "
                f"skipped {result.get('summary', {}).get('skipped', 0)}."
            )
        elif run.spec.targetType == "git_activity_correlation_promotion":
            result = _execute_git_activity_correlation_promotions(index, run, executor_member=executor_member)
            logs.append(
                "Promoted "
                f"{result.get('promotedCount', 0)} approved Git activity correlation review(s); "
                f"eligible {result.get('eligibleCount', 0)}; blocked {result.get('blockedCount', 0)}."
            )
        elif run.spec.targetType == "git_activity_retention_sweep":
            result = _execute_git_activity_retention_sweep(index, run, executor_member=executor_member)
            logs.append(
                "Swept "
                f"{result.get('updatedCount', 0)} expired Git activity retention candidate(s); "
                f"considered {result.get('candidateCount', 0)}."
            )
        elif run.spec.targetType == "artifact_retention_sweep":
            result = _execute_artifact_retention_sweep(index, run, executor_member=executor_member)
            logs.append(
                "Swept "
                f"{result.get('updatedCount', 0)} expired artifact retention candidate(s); "
                f"considered {result.get('candidateCount', 0)}."
            )
        elif run.spec.targetType in {"digital_execution", "hybrid_assist"}:
            task_id, run_id = _execute_linked_run(index, run)
            created_task = task_id or created_task
            created_run = run_id
            logs.append(f"Created linked run {created_run}.")
        else:
            raise ValueError(f"automation target type {run.spec.targetType} is not executable in this control-plane slice")
    except (KeyError, ValueError) as exc:
        if isinstance(exc, _AutomationExecutionError):
            created_task = exc.created_task or created_task
        blockers.append(f"Automation executor failed: {exc}.")
        decision_audit.append(
            decision_audit_record(
                index,
                decision_kind="system_check",
                decision="failed",
                actor_member=executor_member,
                authority="record",
                reason=str(exc),
                source="automation-executor",
                evidence=[{"kind": "automation-run", "automationRun": automation_run_id}],
                requires_human_review=True,
            )
        )
        logs.append("Executor failed while creating target control-plane records.")
        return _write_automation_run_update(
            index,
            automation_run_id,
            status="failed",
            finished_at=now.isoformat(timespec="milliseconds"),
            summary="Automation executor failed before worker execution.",
            permission_decisions=permission_decisions,
            decision_audit=decision_audit,
            blockers=blockers,
            warnings=warnings,
            logs=logs,
            created_task=created_task,
        )

    decision_audit.append(
        decision_audit_record(
            index,
            decision_kind="system_check",
            decision="succeeded",
            actor_member=executor_member,
            authority="record",
            reason="Queued automation run executed by writing control-plane output records.",
            source="automation-executor",
            evidence=[
                {
                    "kind": "automation-run",
                    "automationRun": automation_run_id,
                    "createdTask": created_task,
                    "createdRun": created_run,
                    "createdTaskPlan": created_task_plan,
                    "createdMessage": created_message,
                }
            ],
            requires_human_review=False,
        )
    )
    return _write_automation_run_update(
        index,
        automation_run_id,
        status="succeeded",
        finished_at=now.isoformat(timespec="milliseconds"),
        summary="Automation executor created control-plane output records without running worker code.",
        permission_decisions=permission_decisions,
        decision_audit=decision_audit,
        blockers=blockers,
        warnings=warnings,
        logs=logs,
        created_task=created_task,
        created_run=created_run,
        created_task_plan=created_task_plan,
        created_message=created_message,
    )


def _create_automation_run(
    workspace_path: str | Path,
    automation_id: str,
    *,
    actor_member: str | None,
    source_event: dict[str, Any] | None,
    force_dry_run: bool,
) -> AutomationRun:
    index = load_workspace(workspace_path)
    if automation_id not in index.automations:
        raise KeyError(f"unknown automation {automation_id}")
    automation = index.automations[automation_id]
    now = datetime.now().astimezone()
    event = dict(source_event or {})
    trigger_type = _trigger_type(event)
    warnings: list[str] = []
    blockers: list[str] = []
    permission_decisions: list[dict[str, Any]] = []
    decision_audit: list[dict[str, Any]] = []

    if automation.spec.status != "active":
        blockers.append(f"Automation {automation_id} is {automation.spec.status}, not active.")
    if actor_member and actor_member not in index.members:
        blockers.append(f"Requested actor member {actor_member} does not exist.")
    if automation.spec.serviceMember:
        service = index.members.get(automation.spec.serviceMember)
        if service is None:
            blockers.append(f"Service member {automation.spec.serviceMember} does not exist.")
        elif service.spec.kind != "service":
            blockers.append(f"Automation service member {automation.spec.serviceMember} is {service.spec.kind}, not service.")
    if automation.spec.triggers and trigger_type not in {trigger.triggerType for trigger in automation.spec.triggers}:
        message = f"Trigger type {trigger_type} is not declared for automation {automation_id}."
        if force_dry_run:
            warnings.append(message)
        else:
            blockers.append(message)

    permission_member = automation.spec.serviceMember or actor_member or automation.spec.ownerMember
    if permission_member:
        try:
            permission_decision = explain_effective_permissions(
                index,
                member=permission_member,
                project=automation.spec.project,
                action={
                    "tool": "Automation",
                    "target": f"{automation.spec.targetType}:{automation_id}",
                },
                non_interactive=True,
            )
            permission_summary = _permission_decision_summary(permission_decision)
            permission_decisions.append(permission_summary)
            decision_audit.append(
                decision_audit_record(
                    index,
                    decision_kind="service_policy_decision",
                    decision=str(permission_decision.get("decision") or "pending"),
                    actor_member=permission_member,
                    authority="enforce",
                    reason=str(permission_decision.get("reason") or "automation permission evaluated"),
                    source="automation-permission-evaluator",
                    policy_refs=list(permission_decision.get("selectedPolicyIds") or []),
                    evidence=[
                        {
                            "kind": "permission-explain",
                            "automation": automation_id,
                            "action": permission_summary.get("action"),
                            "matchedRules": permission_decision.get("matchedRules", []),
                            "matchedGrants": permission_decision.get("matchedGrants", []),
                            "blockers": permission_decision.get("blockers", []),
                            "warnings": permission_decision.get("warnings", []),
                        }
                    ],
                    requires_human_review=bool(automation.spec.approvalGates),
                    risk_assessment=permission_decision.get("riskAssessment"),
                )
            )
            if permission_decision["decision"] != "allow" or permission_decision["blockers"]:
                message = (
                    f"Automation permission denied for {permission_member}: "
                    f"{permission_decision['reason']}."
                )
                if force_dry_run:
                    warnings.append(message)
                else:
                    blockers.append(message)
        except (KeyError, ValueError) as exc:
            message = f"Automation permission check failed: {exc}."
            if force_dry_run:
                warnings.append(message)
            else:
                blockers.append(message)

    if force_dry_run:
        status = "dry-run" if not blockers else "blocked"
        dry_run = True
        finished_at = now.isoformat(timespec="milliseconds")
        summary = "Automation dry-run recorded without executing project work."
    elif automation.spec.dryRun:
        status = "blocked"
        dry_run = True
        finished_at = now.isoformat(timespec="milliseconds")
        blockers.append("Automation is configured for dry-run only.")
        summary = "Automation trigger blocked because this automation is dry-run only."
    elif blockers:
        status = "blocked"
        dry_run = False
        finished_at = now.isoformat(timespec="milliseconds")
        summary = "Automation trigger blocked by control-plane validation."
    elif automation.spec.approvalGates:
        status = "pending-approval"
        dry_run = False
        finished_at = None
        summary = "Automation trigger recorded and waiting for approval gates."
    else:
        status = "queued"
        dry_run = False
        finished_at = None
        summary = "Automation trigger recorded for later executor pickup."

    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "AutomationRun",
        "metadata": {
            "id": _next_automation_run_id(index.workspace_root, now),
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "automation": automation_id,
            "project": automation.spec.project,
            "ownerMember": automation.spec.ownerMember,
            "serviceMember": automation.spec.serviceMember,
            "targetType": automation.spec.targetType,
            "target": automation.spec.target,
            "triggerType": trigger_type,
            "sourceEvent": event,
            "dryRun": dry_run,
            "status": status,
            "requestedByMember": actor_member,
            "approvalGates": automation.spec.approvalGates,
            "permissionPolicies": automation.spec.permissionPolicies,
            "permissionDecisions": permission_decisions,
            "decisionAudit": decision_audit,
            "startedAt": now.isoformat(timespec="milliseconds"),
            "finishedAt": finished_at,
            "summary": summary,
            "blockers": blockers,
            "warnings": warnings,
            "logs": [],
            "artifacts": [],
        },
    }
    run = AutomationRun.model_validate(payload)
    write_yaml(index.workspace_root / "automations" / "runs" / f"{run.object_id}.yaml", run.model_dump(mode="json", exclude_none=True))
    return run


def _permission_decision_summary(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "member": decision.get("member"),
        "memberKind": decision.get("memberKind"),
        "project": decision.get("project"),
        "assignment": decision.get("assignment"),
        "action": decision.get("normalizedAction"),
        "decision": decision.get("decision"),
        "reason": decision.get("reason"),
        "selectedPolicyIds": decision.get("selectedPolicyIds", []),
        "matchedRules": decision.get("matchedRules", []),
        "blockers": decision.get("blockers", []),
        "warnings": decision.get("warnings", []),
        "riskAssessment": decision.get("riskAssessment"),
    }


def _automation_permission_member(run: AutomationRun) -> str | None:
    return run.spec.serviceMember or run.spec.ownerMember or run.spec.requestedByMember


def _automation_still_blocks_permission(
    index: WorkspaceIndex,
    run: AutomationRun,
    permission_member: str | None,
    denied_decisions: list[dict[str, Any]],
) -> bool:
    if not permission_member:
        return bool(denied_decisions)
    for decision in denied_decisions:
        action = decision.get("action") if isinstance(decision.get("action"), dict) else {}
        if not action:
            return True
        try:
            current = explain_effective_permissions(
                index,
                member=permission_member,
                project=run.spec.project,
                action=action,
                non_interactive=True,
            )
        except (KeyError, ValueError):
            return True
        if current.get("decision") != "allow" or current.get("blockers"):
            return True
    return False


def _automation_output_permission_paths(run: AutomationRun) -> list[str]:
    if run.spec.targetType in {"human_reminder", "connector_failure_reminder"}:
        return ["/.aiteamos/im/messages/**"]
    if run.spec.targetType == "task_planning":
        return ["/.aiteamos/task_plans/**"]
    if run.spec.targetType == "manager_recommendation":
        return ["/.aiteamos/im/messages/**", "/.aiteamos/task_plans/**"]
    if run.spec.targetType in {"digital_execution", "hybrid_assist"}:
        return ["/.aiteamos/tasks/**", "/.aiteamos/runs/**"]
    if run.spec.targetType == "artifact_retention_sweep":
        return ["/.aiteamos/artifacts/manifests/**"]
    return []


def _execute_human_reminder(index: WorkspaceIndex, run: AutomationRun, *, executor_member: str) -> Any:
    target = run.spec.target
    to_members = _target_list(target, "toMembers", "to_members", "members", "recipients")
    if not to_members:
        if run.spec.requestedByMember:
            to_members = [run.spec.requestedByMember]
        elif run.spec.ownerMember:
            to_members = [run.spec.ownerMember]
    if not to_members:
        raise ValueError("human_reminder target requires toMembers, requestedByMember, or ownerMember")
    body = str(
        target.get("body")
        or target.get("message")
        or target.get("summary")
        or f"Automation {run.spec.automation} created a reminder."
    )
    return record_member_message(
        index.workspace_root,
        from_member=executor_member,
        to_members=to_members,
        message_type=_member_message_type(target),
        body=body,
        project=run.spec.project,
        task=target.get("task") or target.get("taskId"),
        run=target.get("run") or target.get("runId"),
        attachments=_target_list(target, "attachments"),
        priority=str(target.get("priority") or "normal"),
        requested_response_by=target.get("requestedResponseBy") or target.get("requested_response_by"),
        audit={"source": "automation-executor", "automation": run.spec.automation, "automationRun": run.object_id},
    )


def _execute_manager_recommendation(
    index: WorkspaceIndex,
    run: AutomationRun,
    *,
    executor_member: str,
    now: datetime,
) -> tuple[Any, TaskPlan | None]:
    target = run.spec.target
    project = str(target.get("project") or run.spec.project or index.project.object_id)
    if project != index.project.object_id:
        raise KeyError(f"unknown project {project}")
    manager_member = str(target.get("managerMember") or target.get("manager_member") or run.spec.ownerMember or "aiteamos-manager")
    if manager_member not in index.members:
        raise KeyError(f"unknown manager member {manager_member}")
    if index.members[manager_member].spec.kind != "digital":
        raise ValueError(f"manager recommendation requires a digital manager member, but {manager_member} is {index.members[manager_member].spec.kind}")
    to_members = _target_list(target, "toMembers", "to_members", "reviewers", "recipients")
    if not to_members:
        to_members = [run.spec.requestedByMember or "architect"]
    for member_id in to_members:
        if member_id not in index.members:
            raise KeyError(f"unknown recommendation recipient {member_id}")

    plan: TaskPlan | None = None
    subtasks = target.get("subtasks")
    create_plan = bool(subtasks) or bool(target.get("createTaskPlan") or target.get("create_task_plan"))
    if create_plan:
        plan = _manager_recommendation_task_plan(index, run, manager_member=manager_member, now=now)

    title = str(target.get("title") or target.get("goal") or "Manager plan recommendation")
    body = str(
        target.get("body")
        or target.get("message")
        or f"{manager_member} recommends a plan for {title}. Review the attached TaskPlan before creating any Task."
    )
    attachments = _target_list(target, "attachments")
    if plan is not None:
        attachments = [*attachments, plan.object_id]
    message = record_member_message(
        index.workspace_root,
        from_member=manager_member,
        to_members=to_members,
        message_type="plan-recommendation",
        body=body,
        project=project,
        attachments=attachments,
        priority=str(target.get("priority") or "normal"),
        audit={
            "source": "manager-recommendation",
            "automation": run.spec.automation,
            "automationRun": run.object_id,
            "executorMember": executor_member,
            "createdTaskPlan": plan.object_id if plan is not None else None,
        },
    )
    return message, plan


def _manager_recommendation_task_plan(
    index: WorkspaceIndex,
    run: AutomationRun,
    *,
    manager_member: str,
    now: datetime,
) -> TaskPlan:
    target = run.spec.target
    project = str(target.get("project") or run.spec.project or index.project.object_id)
    subtasks = target.get("subtasks")
    if not isinstance(subtasks, list):
        subtasks = []
    normalized_subtasks: list[dict[str, Any]] = []
    for item in subtasks:
        if isinstance(item, str):
            normalized_subtasks.append({"title": item})
        elif isinstance(item, dict) and item.get("title"):
            normalized_subtasks.append(dict(item))
    plan_id = _next_task_plan_id(index.workspace_root, now)
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "TaskPlan",
        "metadata": {
            "id": plan_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "goal": str(target.get("goal") or target.get("title") or run.spec.automation),
            "project": project,
            "sourceTask": target.get("sourceTask") or target.get("task") or target.get("taskId"),
            "createdByMember": manager_member,
            "status": str(target.get("status") or "draft"),
            "subtasks": normalized_subtasks,
            "risks": _target_list(target, "risks"),
            "reviewGates": _target_list(target, "reviewGates", "review_gates"),
        },
    }
    plan = TaskPlan.model_validate(payload)
    write_yaml(index.workspace_root / "task_plans" / f"{plan.object_id}.yaml", plan.model_dump(mode="json", exclude_none=True))
    return plan


def _execute_connector_failure_reminders(index: WorkspaceIndex, run: AutomationRun, *, executor_member: str) -> dict[str, Any]:
    target = run.spec.target
    max_messages = _optional_int(target, "maxMessagesPerRun", "max_messages_per_run")
    if max_messages is None:
        max_messages = 1
    throttle_minutes = _optional_int(target, "throttleMinutes", "throttle_minutes")
    if throttle_minutes is None:
        throttle_minutes = 60
    return route_connector_failure_reminders(
        index.workspace_root,
        actor_member=executor_member,
        connector=_optional_string(target, "connector"),
        project=_optional_string(target, "project") or run.spec.project,
        member=_optional_string(target, "member"),
        assignment=_optional_string(target, "assignment"),
        lifecycle=_optional_string(target, "lifecycle") or "active",
        dry_run=False,
        max_messages=max_messages,
        throttle_minutes=throttle_minutes,
        audit_context={"automation": run.spec.automation, "automationRun": run.object_id},
    )


def _execute_git_activity_correlation_promotions(index: WorkspaceIndex, run: AutomationRun, *, executor_member: str) -> dict[str, Any]:
    candidates = git_activity_correlation_promotion_candidates(
        index,
        project=run.spec.project,
        automation=run.spec.automation,
        service_member=executor_member,
        include_blocked=True,
    )
    policy = candidates.get("policy") if isinstance(candidates.get("policy"), dict) else {}
    max_promotions = max(1, int(policy.get("maxPromotionsPerRun") or 1))
    eligible_candidates = [
        candidate
        for candidate in candidates.get("candidates", [])
        if isinstance(candidate, dict) and candidate.get("eligible")
    ][:max_promotions]
    promoted: list[dict[str, Any]] = []
    for candidate in eligible_candidates:
        preview = candidate.get("promotionPreview") if isinstance(candidate.get("promotionPreview"), dict) else {}
        review_id = str(candidate.get("review") or "")
        if not review_id:
            continue
        result = promote_git_activity_correlation_review(
            index.workspace_root,
            review_id,
            reviewer_member=executor_member,
            member=_optional_string(preview, "member"),
            assignment=_optional_string(preview, "assignment"),
            activity_type=_optional_string(preview, "activityType"),
            visibility=_optional_string(preview, "visibility") or "project",
            summary=f"Automation {run.spec.automation} promoted approved Git import correlation {review_id}.",
        )
        promoted.append(
            {
                "review": review_id,
                "created": bool(result.get("created")),
                "alreadyPromoted": bool(result.get("alreadyPromoted")),
                "activities": [activity.object_id for activity in result.get("activities", [])],
            }
        )
    summary = candidates.get("summary") if isinstance(candidates.get("summary"), dict) else {}
    return {
        "promoted": promoted,
        "promotedCount": len(promoted),
        "eligibleCount": int(summary.get("eligible") or 0),
        "blockedCount": int(summary.get("blocked") or 0),
        "candidates": candidates,
    }


def _execute_git_activity_retention_sweep(index: WorkspaceIndex, run: AutomationRun, *, executor_member: str) -> dict[str, Any]:
    target = run.spec.target
    max_candidates = _optional_int(target, "maxCandidatesPerRun", "max_candidates_per_run")
    if max_candidates is None:
        max_candidates = 1
    result = sweep_git_activity_retention(
        index.workspace_root,
        actor_member=executor_member,
        target_lifecycle=_optional_string(target, "targetLifecycle", "target_lifecycle"),
        project=_optional_string(target, "project") or run.spec.project,
        member=_optional_string(target, "member"),
        assignment=_optional_string(target, "assignment"),
        dry_run=False,
        limit=max_candidates,
    )
    errors = result.get("errors", [])
    if isinstance(errors, list) and errors:
        details = "; ".join(
            f"{item.get('activity', 'unknown')}: {item.get('error', 'unknown error')}"
            for item in errors
            if isinstance(item, dict)
        )
        raise ValueError(f"GitActivity retention sweep failed for {len(errors)} candidate(s): {details}")
    return {
        "updated": result.get("updated", []),
        "updatedCount": int(result.get("updatedCount") or 0),
        "candidateCount": len(result.get("candidates", [])),
        "candidateSummary": result.get("candidateSummary", {}),
        "errors": result.get("errors", []),
    }


def _execute_artifact_retention_sweep(index: WorkspaceIndex, run: AutomationRun, *, executor_member: str) -> dict[str, Any]:
    target = run.spec.target
    max_candidates = _optional_int(target, "maxCandidatesPerRun", "max_candidates_per_run")
    if max_candidates is None:
        max_candidates = 1
    result = sweep_artifact_retention(
        index.workspace_root,
        actor_member=executor_member,
        target_lifecycle=_optional_string(target, "targetLifecycle", "target_lifecycle"),
        project=_optional_string(target, "project") or run.spec.project,
        run=_optional_string(target, "run", "sourceRun", "source_run"),
        kind=_optional_string(target, "kind", "artifactKind", "artifact_kind"),
        now=_optional_string(target, "now", "evaluatedAt", "evaluated_at"),
        dry_run=False,
        limit=max_candidates,
    )
    errors = result.get("errors", [])
    if isinstance(errors, list) and errors:
        details = "; ".join(
            f"{item.get('artifact', 'unknown')}: {item.get('error', 'unknown error')}"
            for item in errors
            if isinstance(item, dict)
        )
        raise ValueError(f"Artifact retention sweep failed for {len(errors)} candidate(s): {details}")
    return {
        "updated": result.get("updated", []),
        "updatedCount": int(result.get("updatedCount") or 0),
        "candidateCount": len(result.get("candidates", [])),
        "candidateSummary": result.get("candidateSummary", {}),
        "errors": result.get("errors", []),
    }


def _execute_task_plan(index: WorkspaceIndex, run: AutomationRun, *, executor_member: str, now: datetime) -> TaskPlan:
    target = run.spec.target
    project = str(target.get("project") or run.spec.project or index.project.object_id)
    if project != index.project.object_id:
        raise KeyError(f"unknown project {project}")
    subtasks = target.get("subtasks")
    if not isinstance(subtasks, list):
        subtasks = []
    normalized_subtasks: list[dict[str, Any]] = []
    for item in subtasks:
        if isinstance(item, str):
            normalized_subtasks.append({"title": item})
        elif isinstance(item, dict) and item.get("title"):
            normalized_subtasks.append(dict(item))
    plan_id = _next_task_plan_id(index.workspace_root, now)
    payload = {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "TaskPlan",
        "metadata": {
            "id": plan_id,
            "createdAt": now.isoformat(timespec="milliseconds"),
        },
        "spec": {
            "goal": str(target.get("goal") or target.get("title") or run.spec.automation),
            "project": project,
            "sourceTask": target.get("sourceTask") or target.get("task") or target.get("taskId"),
            "createdByMember": executor_member,
            "status": str(target.get("status") or "draft"),
            "subtasks": normalized_subtasks,
            "risks": _target_list(target, "risks"),
            "reviewGates": _target_list(target, "reviewGates", "review_gates"),
        },
    }
    plan = TaskPlan.model_validate(payload)
    write_yaml(index.workspace_root / "task_plans" / f"{plan.object_id}.yaml", plan.model_dump(mode="json", exclude_none=True))
    return plan


def _execute_linked_run(index: WorkspaceIndex, run: AutomationRun) -> tuple[str | None, str]:
    target = run.spec.target
    project = str(target.get("project") or run.spec.project or index.project.object_id)
    if project != index.project.object_id:
        raise KeyError(f"unknown project {project}")
    task_id = target.get("task") or target.get("taskId")
    created_task: str | None = None
    member = target.get("assignedMember") or target.get("member") or run.spec.ownerMember or run.spec.requestedByMember
    assignment = target.get("assignment")
    if not member:
        raise ValueError(f"{run.spec.targetType} automation requires target.assignedMember, target.member, ownerMember, or requestedByMember")
    member_id = str(member)
    if member_id not in index.members:
        raise KeyError(f"unknown member {member_id}")
    member_kind = index.members[member_id].spec.kind
    requested_mode = str(target.get("mode") or target.get("runMode") or ("managed_llm" if run.spec.targetType == "digital_execution" else "assisted"))
    if requested_mode == "managed":
        requested_mode = "managed_llm"
    if run.spec.targetType == "digital_execution":
        if member_kind != "digital":
            raise ValueError(f"digital_execution automation requires a digital member, but {member_id} is {member_kind}")
        if requested_mode != "managed_llm":
            raise ValueError(f"digital_execution automation requires managed_llm run mode, not {requested_mode}")
    if run.spec.targetType == "hybrid_assist":
        if member_kind not in {"human", "hybrid"}:
            raise ValueError(f"hybrid_assist automation requires a human or hybrid member, but {member_id} is {member_kind}")
        if requested_mode not in {"assisted", "manual"}:
            raise ValueError(f"hybrid_assist automation requires assisted or manual run mode, not {requested_mode}")
    task_execution_mode = str(target.get("executionMode") or requested_mode)
    if not task_id:
        task = create_task(
            index.workspace_root,
            title=str(target.get("title") or target.get("taskTitle") or run.spec.automation),
            project=project,
            assigned_member=member_id,
            assignment=assignment,
            priority=str(target.get("priority") or "normal"),
            status=str(target.get("taskStatus") or "QUEUED"),
            risk_class=target.get("riskClass") or target.get("risk_class"),
            execution_mode=task_execution_mode,
            acceptance=_target_list(target, "acceptance"),
            markdown=target.get("markdown"),
        )
        task_id = task.object_id
        created_task = task.object_id
    try:
        linked_run = create_run(
            index.workspace_root,
            task_id=str(task_id),
            member=member_id,
            assignment=assignment,
            model_profile=target.get("modelProfile") or target.get("model_profile"),
            mode=requested_mode,
            status=str(target.get("runStatus") or "READY"),
            branch_base=target.get("branchBase") or target.get("branch_base"),
        )
    except (KeyError, ValueError) as exc:
        raise _AutomationExecutionError(str(exc), created_task=created_task) from exc
    return created_task, linked_run.object_id


def _write_automation_run_update(
    index: WorkspaceIndex,
    automation_run_id: str,
    *,
    status: str,
    finished_at: str,
    summary: str,
    permission_decisions: list[dict[str, Any]],
    decision_audit: list[dict[str, Any]],
    blockers: list[str],
    warnings: list[str],
    logs: list[str],
    created_task: str | None = None,
    created_run: str | None = None,
    created_task_plan: str | None = None,
    created_message: str | None = None,
) -> AutomationRun:
    path = index.workspace_root / "automations" / "runs" / f"{automation_run_id}.yaml"
    data = read_yaml(path)
    spec = data.setdefault("spec", {})
    spec["status"] = status
    spec["finishedAt"] = finished_at
    spec["summary"] = summary
    spec["permissionDecisions"] = permission_decisions
    spec["decisionAudit"] = decision_audit
    spec["blockers"] = blockers
    spec["warnings"] = warnings
    spec["logs"] = logs
    if created_task:
        spec["createdTask"] = created_task
    if created_run:
        spec["createdRun"] = created_run
    if created_task_plan:
        spec["createdTaskPlan"] = created_task_plan
    if created_message:
        spec["createdMessage"] = created_message
    updated = AutomationRun.model_validate(data)
    write_yaml(path, updated.model_dump(mode="json", exclude_none=True))
    return updated


def _decision_audit_payloads(records: list[Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for record in records:
        if hasattr(record, "model_dump"):
            payloads.append(record.model_dump(mode="json", exclude_none=True))
        elif isinstance(record, dict):
            payloads.append(dict(record))
    return payloads


def _target_list(target: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = target.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _optional_string(target: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = target.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _optional_int(target: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = target.get(key)
        if value is None:
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"automation target field {key} must be an integer")
        if number < 0:
            raise ValueError(f"automation target field {key} must be non-negative")
        return number
    return None


def _normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _header(headers: dict[str, str], name: str | None) -> str | None:
    if not name:
        return None
    return headers.get(str(name).lower())


def _raw_webhook_body(payload: dict[str, Any], raw_body: str | bytes | None) -> bytes:
    if raw_body is None:
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if isinstance(raw_body, bytes):
        return raw_body
    return raw_body.encode("utf-8")


def _payload_digest(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()[:32]


def _automation_provider_delivery_id(
    automation_id: str,
    provider: str,
    event_type: str,
    delivery_id: str,
    connector: str | None,
) -> str:
    digest = hashlib.sha256(
        f"{automation_id}:{connector or ''}:{provider}:{event_type}:{delivery_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"ADELIVERY-{digest}"


def _write_provider_delivery(
    index: WorkspaceIndex,
    delivery_record_id: str,
    *,
    automation_id: str,
    automation_project: str | None,
    connector: str | None,
    provider: str,
    event_type: str,
    trigger_type: str,
    delivery_id: str,
    dedupe_key: str,
    payload_digest: str,
    received_at: str | None,
    replay_window_seconds: int | None,
    replay_status: str,
    admission_status: str,
    normalized: dict[str, Any],
    safe_headers: dict[str, str],
    actor_member: str | None,
    summary: str,
    automation_trigger_event: str | None = None,
    automation_run: str | None = None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
) -> AutomationProviderDelivery:
    now = datetime.now().astimezone()
    existing = index.automation_provider_deliveries.get(delivery_record_id)
    first_seen_at = existing.spec.firstSeenAt if existing else now.isoformat(timespec="milliseconds")
    prior_audit = list(existing.spec.decisionAudit) if existing else []
    attempt_count = (existing.spec.attemptCount if existing else 0) + 1
    linked_event = automation_trigger_event if automation_trigger_event is not None else (existing.spec.automationTriggerEvent if existing else None)
    linked_run = automation_run if automation_run is not None else (existing.spec.automationRun if existing else None)
    retry_status = existing.spec.retryStatus if existing else "not_requested"
    retry_requested_at = existing.spec.retryRequestedAt if existing else None
    retry_requested_by_member = existing.spec.retryRequestedByMember if existing else None
    retry_delivery = existing.spec.retryDelivery if existing else None
    retry_event = existing.spec.retryAutomationTriggerEvent if existing else None
    retry_run = existing.spec.retryAutomationRun if existing else None
    retry_attempts = list(existing.spec.retryAttempts) if existing else []
    audit = decision_audit_record(
        index,
        decision_kind="system_check",
        decision=admission_status,
        actor_member=actor_member,
        authority="record",
        reason=summary,
        source="automation-provider-delivery-admission",
        decided_at=now.isoformat(timespec="milliseconds"),
        evidence=[
            {
                "kind": "automation-provider-delivery",
                "automation": automation_id,
                "connector": connector,
                "provider": provider,
                "eventType": event_type,
                "deliveryId": delivery_id,
                "dedupeKey": dedupe_key,
                "payloadDigestAlgorithm": "sha256",
                "payloadDigest": payload_digest,
                "attemptCount": attempt_count,
                "replayStatus": replay_status,
                "admissionStatus": admission_status,
                "automationTriggerEvent": linked_event,
                "automationRun": linked_run,
            }
        ],
    )
    delivery = AutomationProviderDelivery.model_validate(
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "AutomationProviderDelivery",
            "metadata": {
                "id": delivery_record_id,
                "createdAt": first_seen_at,
            },
            "spec": {
                "automation": automation_id,
                "project": automation_project,
                "connector": connector,
                "provider": provider,
                "eventType": event_type,
                "triggerType": trigger_type,
                "deliveryId": delivery_id,
                "dedupeKey": dedupe_key,
                "payloadDigest": payload_digest,
                "payloadDigestAlgorithm": "sha256",
                "receivedAt": received_at or now.isoformat(timespec="milliseconds"),
                "firstSeenAt": first_seen_at,
                "lastSeenAt": now.isoformat(timespec="milliseconds"),
                "attemptCount": attempt_count,
                "replayWindowSeconds": replay_window_seconds,
                "replayStatus": replay_status,
                "admissionStatus": admission_status,
                "retryStatus": retry_status,
                "retryRequestedAt": retry_requested_at,
                "retryRequestedByMember": retry_requested_by_member,
                "retryDelivery": retry_delivery,
                "retryAutomationTriggerEvent": retry_event,
                "retryAutomationRun": retry_run,
                "retryAttempts": retry_attempts,
                "automationTriggerEvent": linked_event,
                "automationRun": linked_run,
                "normalized": normalized,
                "safeHeaders": safe_headers,
                "summary": summary,
                "blockers": blockers or [],
                "warnings": warnings or [],
                "decisionAudit": [*prior_audit, audit],
                "audit": {
                    "rawBodyStored": False,
                    "signatureStored": False,
                    "authorizationStored": False,
                },
            },
        }
    )
    write_yaml(
        index.workspace_root / "automations" / "provider_deliveries" / f"{delivery.object_id}.yaml",
        delivery.model_dump(mode="json", exclude_none=True),
    )
    return delivery


def _write_provider_delivery_retry(
    index: WorkspaceIndex,
    delivery: AutomationProviderDelivery,
    *,
    actor_member: str,
    reason: str | None,
    outcome: str,
    dry_run: bool,
    retry_delivery: AutomationProviderDelivery | None = None,
    event: AutomationTriggerEvent | None = None,
    run: AutomationRun | None = None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
) -> AutomationProviderDelivery:
    now = datetime.now().astimezone()
    actor_kind = index.members.get(actor_member).spec.kind if actor_member in index.members else None
    if actor_kind in {"human", "hybrid"}:
        decision_kind = "human_approval"
        authority = "approve"
    elif actor_kind == "service":
        decision_kind = "service_policy_decision"
        authority = "enforce"
    elif actor_kind == "digital":
        decision_kind = "digital_recommendation"
        authority = "recommend"
    else:
        decision_kind = "system_check"
        authority = "record"

    retry_status = "admitted" if outcome == "admitted" else ("blocked" if outcome == "blocked" else "requested")
    attempt = {
        "attemptedAt": now.isoformat(timespec="milliseconds"),
        "actorMember": actor_member,
        "actorMemberKind": actor_kind,
        "outcome": outcome,
        "dryRun": dry_run,
        "reason": reason,
        "retryDelivery": retry_delivery.object_id if retry_delivery is not None else None,
        "retryAutomationTriggerEvent": event.object_id if event is not None else None,
        "retryAutomationRun": run.object_id if run is not None else None,
        "payloadDigest": retry_delivery.spec.payloadDigest if retry_delivery is not None else None,
        "blockers": blockers or [],
        "warnings": warnings or [],
    }
    attempt = {key: value for key, value in attempt.items() if value not in (None, [], {})}
    data = delivery.model_dump(mode="json", exclude_none=True)
    spec = data.setdefault("spec", {})
    existing_attempts = list(spec.get("retryAttempts") or [])
    existing_blockers = list(spec.get("blockers") or [])
    existing_warnings = list(spec.get("warnings") or [])
    spec["retryStatus"] = retry_status
    spec["retryRequestedAt"] = now.isoformat(timespec="milliseconds")
    spec["retryRequestedByMember"] = actor_member
    spec["retryDelivery"] = retry_delivery.object_id if retry_delivery is not None else spec.get("retryDelivery")
    spec["retryAutomationTriggerEvent"] = event.object_id if event is not None else spec.get("retryAutomationTriggerEvent")
    spec["retryAutomationRun"] = run.object_id if run is not None else spec.get("retryAutomationRun")
    spec["retryAttempts"] = [*existing_attempts, attempt]
    spec["blockers"] = existing_blockers
    for blocker in blockers or []:
        if blocker not in spec["blockers"]:
            spec["blockers"].append(blocker)
    spec["warnings"] = existing_warnings
    for warning in warnings or []:
        if warning not in spec["warnings"]:
            spec["warnings"].append(warning)
    if outcome == "admitted":
        spec["summary"] = "Provider delivery retry admitted a new redelivery through the normal webhook admission path."
    elif outcome == "blocked":
        spec["summary"] = "Provider delivery retry was reviewed but the redelivery admission remained blocked."
    else:
        spec["summary"] = "Provider delivery retry was reviewed and requested; raw provider payload must be supplied through a new redelivery."

    spec.setdefault("decisionAudit", []).append(
        decision_audit_record(
            index,
            decision_kind=decision_kind,
            decision="retry-requested" if outcome == "requested" else f"retry-{outcome}",
            actor_member=actor_member,
            authority=authority,
            reason=reason or "Reviewed provider delivery retry request.",
            source="automation-provider-delivery-retry",
            decided_at=now.isoformat(timespec="milliseconds"),
            evidence=[
                {
                    "kind": "automation-provider-delivery",
                    "automationProviderDelivery": delivery.object_id,
                    "automation": delivery.spec.automation,
                    "connector": delivery.spec.connector,
                    "provider": delivery.spec.provider,
                    "eventType": delivery.spec.eventType,
                    "deliveryId": delivery.spec.deliveryId,
                    "dedupeKey": delivery.spec.dedupeKey,
                    "previousReplayStatus": delivery.spec.replayStatus,
                    "previousAdmissionStatus": delivery.spec.admissionStatus,
                    "retryDelivery": retry_delivery.object_id if retry_delivery is not None else None,
                    "retryAutomationTriggerEvent": event.object_id if event is not None else None,
                    "retryAutomationRun": run.object_id if run is not None else None,
                    "outcome": outcome,
                    "dryRun": dry_run,
                }
            ],
            requires_human_review=actor_kind == "digital",
        )
    )
    updated = AutomationProviderDelivery.model_validate(data)
    write_yaml(
        index.workspace_root / "automations" / "provider_deliveries" / f"{updated.object_id}.yaml",
        updated.model_dump(mode="json", exclude_none=True),
    )
    return updated


def _replay_window_seconds(config: dict[str, Any]) -> int | None:
    value = config.get("replayWindowSeconds") or config.get("timestampToleranceSeconds")
    if value is None:
        return 300 if config.get("timestampHeader") or config.get("requireTimestamp") else None
    return int(value)


def _replay_status_from_error(message: str) -> str:
    return "stale" if "replay window" in message.lower() or "timestamp" in message.lower() else "blocked"


def _external_trigger_type(provider: str, event_type: str | None) -> str:
    event = _external_event_key(event_type)
    if provider in {"github", "gitlab", "gitea", "forgejo"}:
        if event in {"issues", "issue", "issue_hook", "issue_comment", "note_hook"}:
            return "issue_task_event"
        if event in {"pull_request", "merge_request", "merge_request_hook", "pull_request_review", "pull_request_review_comment"}:
            return "pr_event"
        if event in {"push", "push_hook", "create", "delete", "tag_push", "tag_push_hook"}:
            return "git_event"
    return "webhook"


def _select_external_trigger(triggers: list[Any], trigger_type: str, provider: str) -> Any | None:
    external_types = {trigger_type, "webhook", "git_event", "pr_event", "issue_task_event"}
    candidates = [trigger for trigger in triggers if trigger.triggerType in external_types]
    provider_matches = [
        trigger
        for trigger in candidates
        if str((trigger.config or {}).get("provider") or "generic").lower() == provider
    ]
    exact_provider_matches = [trigger for trigger in provider_matches if trigger.triggerType == trigger_type]
    if exact_provider_matches:
        return exact_provider_matches[0]
    if provider_matches:
        return provider_matches[0]
    exact_matches = [trigger for trigger in candidates if trigger.triggerType == trigger_type]
    if exact_matches:
        return exact_matches[0]
    return candidates[0] if candidates else None


def _connector_for_external_admission(
    index: WorkspaceIndex,
    connector_id: str | None,
    provider: str,
    project: str | None,
) -> Any | None:
    if not connector_id:
        return None
    connector = index.connectors.get(connector_id)
    if connector is None:
        raise KeyError(f"unknown connector {connector_id}")
    if str(connector.spec.provider).lower() != provider:
        raise ValueError(f"connector {connector_id} provider {connector.spec.provider} does not match webhook provider {provider}")
    if connector.spec.connectorType not in {"git", "issue", "other"}:
        raise ValueError(f"connector {connector_id} type {connector.spec.connectorType} cannot admit git/webhook events")
    if project and connector.spec.projects and project not in connector.spec.projects:
        raise ValueError(f"connector {connector_id} is not bound to project {project}")
    return connector


def _external_admission_config(connector: Any | None, trigger_config: dict[str, Any]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if connector is not None:
        config.update(connector.spec.config or {})
        config["connector"] = connector.object_id
        secret_refs = connector.spec.secretRefs or {}
        for source_key, target_key in [
            ("webhookSecretEnv", "secretEnv"),
            ("secretEnv", "secretEnv"),
            ("webhookSecret", "secretEnv"),
        ]:
            if target_key not in config and source_key in secret_refs:
                config[target_key] = secret_refs[source_key]
    config.update(trigger_config)
    return config


def _default_event_header(provider: str) -> str:
    if provider == "github":
        return "x-github-event"
    if provider == "gitlab":
        return "x-gitlab-event"
    if provider == "gitea":
        return "x-gitea-event"
    if provider == "forgejo":
        return "x-forgejo-event"
    return "x-aiteamos-event"


def _default_delivery_header(provider: str) -> str:
    if provider == "github":
        return "x-github-delivery"
    if provider == "gitlab":
        return "x-gitlab-event-uuid"
    if provider == "gitea":
        return "x-gitea-delivery"
    if provider == "forgejo":
        return "x-forgejo-delivery"
    return "x-aiteamos-delivery"


def _normalize_provider_payload(provider: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if provider == "github":
        return _normalize_github_payload(event_type, payload)
    if provider == "gitlab":
        return _normalize_gitlab_payload(event_type, payload)
    if provider in {"gitea", "forgejo"}:
        return _normalize_gitea_like_payload(provider, event_type, payload)
    return {
        "provider": provider,
        "eventType": event_type,
        "repository": _string_or_none(payload.get("repository") or payload.get("repo")),
        "action": _string_or_none(payload.get("action")),
    }


def _normalize_github_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    repository = _nested_string(payload, "repository", "full_name")
    if not repository:
        raise ValueError("GitHub webhook payload is missing repository.full_name")
    normalized: dict[str, Any] = {
        "provider": "github",
        "eventType": event_type,
        "repository": repository,
        "action": _string_or_none(payload.get("action")),
        "installationId": _nested_string(payload, "installation", "id"),
    }
    event = _external_event_key(event_type)
    if event in {"issues", "issue", "issue_comment"}:
        issue = payload.get("issue")
        if not isinstance(issue, dict) or not issue.get("number") or not issue.get("title"):
            raise ValueError("GitHub issue webhook payload is missing issue.number or issue.title")
        normalized.update(
            {
                "number": _string_or_none(issue.get("number")),
                "title": _string_or_none(issue.get("title")),
                "url": _string_or_none(issue.get("html_url") or issue.get("url")),
            }
        )
    elif event in {"pull_request", "pull_request_review", "pull_request_review_comment"}:
        pull_request = payload.get("pull_request")
        if not isinstance(pull_request, dict) or not pull_request.get("number") or not pull_request.get("title"):
            raise ValueError("GitHub pull request webhook payload is missing pull_request.number or pull_request.title")
        normalized.update(
            {
                "number": _string_or_none(pull_request.get("number")),
                "title": _string_or_none(pull_request.get("title")),
                "url": _string_or_none(pull_request.get("html_url") or pull_request.get("url")),
                "headRef": _nested_string(pull_request, "head", "ref"),
                "baseRef": _nested_string(pull_request, "base", "ref"),
            }
        )
    elif event in {"push", "create", "delete"}:
        ref = _string_or_none(payload.get("ref"))
        if not ref:
            raise ValueError("GitHub git webhook payload is missing ref")
        normalized.update(
            {
                "ref": ref,
                "after": _string_or_none(payload.get("after")),
            }
        )
    return {key: value for key, value in normalized.items() if value is not None}


def _normalize_gitlab_payload(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = payload.get("project")
    repository = None
    if isinstance(project, dict):
        repository = _string_or_none(project.get("path_with_namespace") or project.get("path"))
    repository = repository or _nested_string(payload, "repository", "name")
    if not repository:
        raise ValueError("GitLab webhook payload is missing project.path_with_namespace")
    object_attributes = payload.get("object_attributes")
    normalized: dict[str, Any] = {
        "provider": "gitlab",
        "eventType": event_type,
        "repository": repository,
        "action": _nested_string(payload, "object_attributes", "action") or _string_or_none(payload.get("event_name")),
    }
    event = _external_event_key(event_type)
    if event in {"issue", "issue_hook", "issues"}:
        if not isinstance(object_attributes, dict) or not object_attributes.get("iid") or not object_attributes.get("title"):
            raise ValueError("GitLab issue webhook payload is missing object_attributes.iid or object_attributes.title")
        normalized.update(
            {
                "number": _string_or_none(object_attributes.get("iid")),
                "title": _string_or_none(object_attributes.get("title")),
                "url": _string_or_none(object_attributes.get("url")),
            }
        )
    elif event in {"merge_request", "merge_request_hook", "pull_request"}:
        if not isinstance(object_attributes, dict) or not object_attributes.get("iid") or not object_attributes.get("title"):
            raise ValueError("GitLab merge request webhook payload is missing object_attributes.iid or object_attributes.title")
        normalized.update(
            {
                "number": _string_or_none(object_attributes.get("iid")),
                "title": _string_or_none(object_attributes.get("title")),
                "url": _string_or_none(object_attributes.get("url")),
                "headRef": _string_or_none(object_attributes.get("source_branch")),
                "baseRef": _string_or_none(object_attributes.get("target_branch")),
            }
        )
    elif event in {"push", "push_hook", "tag_push", "tag_push_hook"}:
        ref = _string_or_none(payload.get("ref"))
        if not ref:
            raise ValueError("GitLab git webhook payload is missing ref")
        normalized["ref"] = ref
    return {key: value for key, value in normalized.items() if value is not None}


def _normalize_gitea_like_payload(provider: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    repository = _repository_full_name(payload.get("repository") or payload.get("repo"))
    if not repository:
        raise ValueError(f"{provider.capitalize()} webhook payload is missing repository.full_name")
    normalized: dict[str, Any] = {
        "provider": provider,
        "eventType": event_type,
        "repository": repository,
        "action": _string_or_none(payload.get("action")),
    }
    event = _external_event_key(event_type)
    if event in {"issues", "issue", "issue_comment"}:
        issue = payload.get("issue")
        if not isinstance(issue, dict):
            raise ValueError(f"{provider.capitalize()} issue webhook payload is missing issue")
        number = _string_or_none(issue.get("number") or issue.get("index") or issue.get("id"))
        title = _string_or_none(issue.get("title"))
        if not number or not title:
            raise ValueError(f"{provider.capitalize()} issue webhook payload is missing issue.number or issue.title")
        normalized.update(
            {
                "number": number,
                "title": title,
                "url": _string_or_none(issue.get("html_url") or issue.get("url")),
            }
        )
    elif event in {"pull_request", "pull_request_review", "pull_request_review_comment"}:
        pull_request = payload.get("pull_request")
        if not isinstance(pull_request, dict):
            raise ValueError(f"{provider.capitalize()} pull request webhook payload is missing pull_request")
        number = _string_or_none(pull_request.get("number") or pull_request.get("index") or pull_request.get("id"))
        title = _string_or_none(pull_request.get("title"))
        if not number or not title:
            raise ValueError(f"{provider.capitalize()} pull request webhook payload is missing pull_request.number or pull_request.title")
        normalized.update(
            {
                "number": number,
                "title": title,
                "url": _string_or_none(pull_request.get("html_url") or pull_request.get("url")),
                "headRef": _nested_string(pull_request, "head", "ref") or _string_or_none(pull_request.get("head_branch")),
                "baseRef": _nested_string(pull_request, "base", "ref") or _string_or_none(pull_request.get("base_branch")),
            }
        )
    elif event in {"push", "create", "delete", "tag_push"}:
        ref = _string_or_none(payload.get("ref"))
        if not ref:
            raise ValueError(f"{provider.capitalize()} git webhook payload is missing ref")
        normalized.update(
            {
                "ref": ref,
                "after": _string_or_none(payload.get("after")),
            }
        )
    return {key: value for key, value in normalized.items() if value is not None}


def _external_event_key(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _validate_connector_external_event(
    connector: Any | None,
    config: dict[str, Any],
    headers: dict[str, str],
    normalized_payload: dict[str, Any],
    received_at: str | None,
) -> None:
    if connector is None:
        return
    repository = normalized_payload.get("repository")
    allowed_repositories = _string_set(
        config.get("allowedRepositories")
        or config.get("repositoryAllowlist")
        or config.get("repositories")
    )
    if allowed_repositories and repository not in allowed_repositories:
        raise ValueError(f"connector {connector.object_id} does not allow repository {repository}")

    installation_id = normalized_payload.get("installationId")
    allowed_installation_ids = _string_set(config.get("allowedInstallationIds") or config.get("installationIds"))
    if allowed_installation_ids and installation_id not in allowed_installation_ids:
        raise ValueError(f"connector {connector.object_id} does not allow installation {installation_id}")

    _validate_external_replay_window(config, headers, received_at)


def _connector_health_admission_decision(
    index: WorkspaceIndex,
    connector: Any | None,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    if connector is None:
        return None
    return connector_health_admission_decision(index, connector.object_id, config=config)


def _validate_external_replay_window(
    config: dict[str, Any],
    headers: dict[str, str],
    received_at: str | None,
) -> None:
    timestamp_header = config.get("timestampHeader")
    require_timestamp = bool(config.get("requireTimestamp") or timestamp_header)
    if not require_timestamp:
        return
    header_name = str(timestamp_header or "x-aiteamos-timestamp")
    header_value = _header(headers, header_name)
    if not header_value:
        raise ValueError(f"missing webhook timestamp header {header_name}")
    event_time = _parse_external_timestamp(header_value)
    reference_time = _parse_external_timestamp(received_at) if received_at else datetime.now().astimezone()
    replay_window = int(config.get("replayWindowSeconds") or config.get("timestampToleranceSeconds") or 300)
    if abs((reference_time - event_time).total_seconds()) > replay_window:
        raise ValueError(f"webhook timestamp is outside replay window of {replay_window} seconds")


def _parse_external_timestamp(value: str) -> datetime:
    raw = str(value).strip()
    try:
        if raw.isdigit():
            parsed = datetime.fromtimestamp(int(raw)).astimezone()
        else:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid webhook timestamp {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _nested_string(value: dict[str, Any], *keys: str) -> str | None:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _string_or_none(current)


def _repository_full_name(value: Any) -> str | None:
    if isinstance(value, str):
        return _string_or_none(value)
    if not isinstance(value, dict):
        return None
    direct = _string_or_none(
        value.get("full_name")
        or value.get("fullName")
        or value.get("path_with_namespace")
        or value.get("path")
    )
    if direct:
        return direct
    owner = value.get("owner")
    owner_name = _string_or_none(owner.get("login") or owner.get("name") or owner.get("username")) if isinstance(owner, dict) else None
    name = _string_or_none(value.get("name"))
    if owner_name and name:
        return f"{owner_name}/{name}"
    return name


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return {str(value).strip()} if str(value).strip() else set()


def _safe_manifest_id(value: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower()).strip("-")
    if not candidate:
        raise ValueError("automation name must produce a non-empty manifest id")
    return candidate


def _verify_external_signature(
    provider: str,
    trigger_config: dict[str, Any],
    headers: dict[str, str],
    raw_body: bytes,
) -> None:
    secret_env = trigger_config.get("secretEnv") or trigger_config.get("webhookSecretEnv")
    if not secret_env:
        raise ValueError("external webhook admission requires trigger config secretEnv")
    secret = os.environ.get(str(secret_env))
    if not secret:
        raise ValueError(f"missing webhook secret environment variable {secret_env}")
    signature_header = str(trigger_config.get("signatureHeader") or _default_signature_header(provider))
    signature = _header(headers, signature_header)
    if not signature:
        raise ValueError(f"missing webhook signature header {signature_header}")
    algorithm = str(trigger_config.get("signatureAlgorithm") or "hmac-sha256")
    if algorithm != "hmac-sha256":
        raise ValueError(f"unsupported webhook signature algorithm {algorithm}")
    prefix = str(trigger_config.get("signaturePrefix") if "signaturePrefix" in trigger_config else _default_signature_prefix(provider))
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    expected_header = f"{prefix}{expected}"
    if not hmac.compare_digest(signature, expected_header):
        raise ValueError("webhook signature verification failed")


def _default_signature_header(provider: str) -> str:
    if provider == "github":
        return "x-hub-signature-256"
    if provider == "gitea":
        return "x-gitea-signature"
    if provider == "forgejo":
        return "x-forgejo-signature"
    return "x-aiteamos-signature"


def _default_signature_prefix(provider: str) -> str:
    if provider == "github":
        return "sha256="
    if provider in {"gitea", "forgejo"}:
        return ""
    return "sha256="


def _safe_external_headers(headers: dict[str, str], provider: str, trigger_config: dict[str, Any]) -> dict[str, str]:
    safe_names = {
        _default_event_header(provider).lower(),
        _default_delivery_header(provider).lower(),
        str(trigger_config.get("eventHeader") or "").lower(),
        str(trigger_config.get("deliveryHeader") or "").lower(),
        str(trigger_config.get("timestampHeader") or "").lower(),
    }
    return {
        key: value
        for key, value in headers.items()
        if key in safe_names and key
    }


def _redact_external_payload(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if _sensitive_payload_key(str(key)):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _redact_external_payload(item)
        return result
    if isinstance(value, list):
        return [_redact_external_payload(item) for item in value]
    return value


def _sensitive_payload_key(key: str) -> bool:
    normalized = key.lower()
    return any(
        marker in normalized
        for marker in ["authorization", "signature", "token", "secret", "password", "api_key", "apikey", "private_key"]
    )


def _member_message_type(target: dict[str, Any]) -> str:
    value = str(target.get("messageType") or target.get("message_type") or "message")
    if value in {"message", "ask-for-help", "review-request", "knowledge-share", "handoff-note", "plan-recommendation"}:
        return value
    return "message"


def _next_task_plan_id(workspace_root: Path, now: datetime) -> str:
    candidate = f"PLAN-{now.strftime('%Y%m%dT%H%M%S')}{now.microsecond // 1000:03d}"
    target = workspace_root / "task_plans" / f"{candidate}.yaml"
    if not target.exists():
        return candidate
    for suffix in range(1, 1000):
        alternate = f"{candidate}-{suffix:03d}"
        if not (workspace_root / "task_plans" / f"{alternate}.yaml").exists():
            return alternate
    raise RuntimeError("could not allocate unique task plan id")


def _approval_blockers(index: WorkspaceIndex, run: AutomationRun, now: datetime) -> list[str]:
    blockers: list[str] = []
    for approval_id in run.spec.approvals:
        approval = index.automation_approvals.get(approval_id)
        if approval is None:
            blockers.append(f"Automation approval {approval_id} is missing.")
            continue
        if approval.spec.automationRun != run.object_id:
            blockers.append(f"Automation approval {approval_id} belongs to {approval.spec.automationRun}, not {run.object_id}.")
        if approval.spec.decision != "approved":
            blockers.append(f"Automation approval {approval_id} is {approval.spec.decision}, not approved.")
        if approval.spec.expiresAt and _is_expired(approval.spec.expiresAt, now):
            blockers.append(f"Automation approval {approval_id} expired at {approval.spec.expiresAt}.")
    return blockers


def _parse_manifest_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def _is_expired(value: str, now: datetime) -> bool:
    try:
        expires_at = datetime.fromisoformat(value)
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.astimezone()
    return expires_at <= now


def _lease_expired(value: str | None, now: datetime) -> bool:
    if not value:
        return True
    return _is_expired(value, now)


def _trigger_type(source_event: dict[str, Any]) -> str:
    value = source_event.get("triggerType") or source_event.get("trigger_type") or "manual"
    return str(value)


def _automation_scheduler_lease_id(automation_id: str, tick_key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{automation_id}-{tick_key}").strip("-")
    return f"ASLEASE-{safe[:180]}"


def _write_scheduler_lease(workspace_root: Path, lease: AutomationSchedulerLease) -> None:
    write_yaml(
        workspace_root / "automations" / "leases" / f"{lease.object_id}.yaml",
        lease.model_dump(mode="json", exclude_none=True),
    )


def _next_automation_approval_id(workspace_root: Path, now: datetime) -> str:
    candidate = timestamp_automation_approval_id(now)
    target = workspace_root / "automations" / "approvals" / f"{candidate}.yaml"
    if not target.exists():
        return candidate
    for suffix in range(1, 1000):
        alternate = f"{candidate}-{suffix:03d}"
        if not (workspace_root / "automations" / "approvals" / f"{alternate}.yaml").exists():
            return alternate
    raise RuntimeError("could not allocate unique automation approval id")


def _next_automation_event_id(workspace_root: Path, now: datetime) -> str:
    candidate = timestamp_automation_event_id(now)
    target = workspace_root / "automations" / "events" / f"{candidate}.yaml"
    if not target.exists():
        return candidate
    for suffix in range(1, 1000):
        alternate = f"{candidate}-{suffix:03d}"
        if not (workspace_root / "automations" / "events" / f"{alternate}.yaml").exists():
            return alternate
    raise RuntimeError("could not allocate unique automation event id")


def _next_automation_run_id(workspace_root: Path, now: datetime) -> str:
    candidate = timestamp_automation_run_id(now)
    target = workspace_root / "automations" / "runs" / f"{candidate}.yaml"
    if not target.exists():
        return candidate
    for suffix in range(1, 1000):
        alternate = f"{candidate}-{suffix:03d}"
        if not (workspace_root / "automations" / "runs" / f"{alternate}.yaml").exists():
            return alternate
    raise RuntimeError("could not allocate unique automation run id")
