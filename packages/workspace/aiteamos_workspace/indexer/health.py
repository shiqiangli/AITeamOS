from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import sqlite3

from .registry import (
    _decision_audit_payloads,
    _insert_decision_audit_records,
    _insert_manifest,
    _json,
    default_index_metadata_path,
)
from ..loader import WorkspaceIndex, manifest_to_record


def _write_index_metadata(
    workspace_root: Path,
    *,
    duration_seconds: float,
    database: dict[str, Any],
    vector: dict[str, Any],
) -> Path:
    metadata_path = default_index_metadata_path(workspace_root)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": "WorkspaceIndexMetadata",
        "derived": True,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lastRebuildDurationSeconds": duration_seconds,
        "databasePath": database.get("databasePath"),
        "vectorSourcesPath": vector.get("path") or vector.get("outputPath") or vector.get("vectorSourcesPath"),
        "counts": {
            "database": database.get("counts") or {},
            "vector": vector.get("counts") or {},
        },
    }
    metadata_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata_path


def _insert_activity_records(conn: sqlite3.Connection, index: WorkspaceIndex) -> None:
    for extraction in index.learning_extractions.values():
        record = manifest_to_record(extraction)
        conn.execute(
            """
            insert into learning_extractions(
              id, run_id, project_id, member_id, assignment_id, extracted_at, dedupe_key,
              extractor_id, extractor_version, proposal_count, proposal_kinds_json,
              manifest_path, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                extraction.object_id,
                extraction.spec.runId,
                extraction.spec.sourceContext.project,
                extraction.spec.sourceContext.member,
                extraction.spec.sourceContext.assignment,
                extraction.spec.extractedAt,
                extraction.spec.dedupeKey,
                extraction.spec.extractorId,
                extraction.spec.extractorVersion,
                len(extraction.spec.proposals),
                _json([proposal.kind for proposal in extraction.spec.proposals]),
                f"learning_extractions/{extraction.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "LearningExtraction", extraction.object_id, f"learning_extractions/{extraction.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "LearningExtraction", extraction.object_id, extraction.spec.decisionAudit)

    for result in index.eval_results.values():
        record = manifest_to_record(result)
        conn.execute(
            """
            insert into eval_results(
              id, eval_suite_id, project_id, task_id, run_id, member_id, assignment_id,
              status, pass_rate, evaluated_at, manifest_path, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.object_id,
                result.spec.evalSuite,
                result.spec.project,
                result.spec.task,
                result.spec.run,
                result.spec.member,
                result.spec.assignment,
                result.spec.status,
                result.spec.passRate,
                result.spec.evaluatedAt,
                f"eval_results/{result.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "EvalResult", result.object_id, f"eval_results/{result.object_id}.yaml", record)

    for retrospective in index.team_retrospectives.values():
        record = manifest_to_record(retrospective)
        conn.execute(
            """
            insert into team_retrospectives(
              id, project_id, facilitator_member_id, status, proposed_memory_id,
              source_task_plan_id, source_runs_json, source_tasks_json, source_messages_json, source_handoffs_json, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                retrospective.object_id,
                retrospective.spec.project,
                retrospective.spec.facilitatorMember,
                retrospective.spec.status,
                retrospective.spec.proposedMemory,
                retrospective.spec.sourceTaskPlan,
                _json(retrospective.spec.sourceRuns),
                _json(retrospective.spec.sourceTasks),
                _json(retrospective.spec.sourceMessages),
                _json(retrospective.spec.sourceHandoffs),
                _json(record),
            ),
        )
        _insert_manifest(conn, "TeamRetrospective", retrospective.object_id, f"im/retrospectives/{retrospective.object_id}.yaml", record)

    for activity in index.member_activities.values():
        record = manifest_to_record(activity)
        conn.execute(
            """
            insert into member_activity(
              id, member_id, project_id, assignment_id, task_id, run_id,
              activity_type, source_type, contribution_kind, source_id,
              occurred_at, visibility, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity.object_id,
                activity.spec.member,
                activity.spec.project,
                activity.spec.assignment,
                activity.spec.task,
                activity.spec.run,
                activity.spec.activityType,
                activity.spec.sourceType,
                activity.spec.contributionKind,
                activity.spec.sourceId,
                activity.spec.occurredAt,
                activity.spec.visibility,
                _json(record),
            ),
        )
        _insert_manifest(conn, "MemberActivity", activity.object_id, f"activity/{activity.object_id}.yaml", record)



def _insert_git_records(conn: sqlite3.Connection, index: WorkspaceIndex) -> None:
    for activity in index.git_activities.values():
        record = manifest_to_record(activity)
        conn.execute(
            """
            insert into git_activity(
              id, member_id, project_id, repository_id, assignment_id,
              activity_type, provider, external_id, occurred_at, visibility,
              lifecycle, retained_until, archived_at, redacted_at, redaction_policy,
              export_policy, refs_json, decision_audit_json, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity.object_id,
                activity.spec.member,
                activity.spec.project,
                activity.spec.repository,
                activity.spec.assignment,
                activity.spec.activityType,
                activity.spec.provider,
                activity.spec.externalId,
                activity.spec.occurredAt,
                activity.spec.visibility,
                activity.spec.lifecycle,
                activity.spec.retainedUntil,
                activity.spec.archivedAt,
                activity.spec.redactedAt,
                activity.spec.redactionPolicy,
                activity.spec.exportPolicy,
                _json(activity.spec.refs),
                _json(_decision_audit_payloads(activity.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "GitActivity", activity.object_id, f"git_activity/{activity.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "GitActivity", activity.object_id, activity.spec.decisionAudit)

    for receipt in index.git_activity_import_receipts.values():
        record = manifest_to_record(receipt)
        conn.execute(
            """
            insert into git_activity_import_receipts(
              id, project_id, repository_id, provider, connector_id, source_type,
              status, dedupe_key, payload_digest, redaction_policy, import_policy,
              payload_retained, retained_until, received_at, reviewed_by_member_id,
              imported_activities_json, refs_json, decision_audit_json, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                receipt.object_id,
                receipt.spec.project,
                receipt.spec.repository,
                receipt.spec.provider,
                receipt.spec.connector,
                receipt.spec.sourceType,
                receipt.spec.status,
                receipt.spec.dedupeKey,
                receipt.spec.payloadDigest,
                receipt.spec.redactionPolicy,
                receipt.spec.importPolicy,
                1 if receipt.spec.payloadRetained else 0,
                receipt.spec.retainedUntil,
                receipt.spec.receivedAt,
                receipt.spec.reviewedByMember,
                _json(receipt.spec.importedActivities),
                _json(receipt.spec.refs),
                _json(_decision_audit_payloads(receipt.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "GitActivityImportReceipt", receipt.object_id, f"git_activity/imports/{receipt.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "GitActivityImportReceipt", receipt.object_id, receipt.spec.decisionAudit)

    for review in index.git_activity_correlation_reviews.values():
        record = manifest_to_record(review)
        conn.execute(
            """
            insert into git_activity_correlation_reviews(
              id, project_id, repository_id, provider, connector_id, correlation_key,
              decision, reviewer_member_id, reviewer_member_kind, reviewed_at,
              receipts_json, imported_activities_json, risk_flags_json, decision_audit_json, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review.object_id,
                review.spec.project,
                review.spec.repository,
                review.spec.provider,
                review.spec.connector,
                review.spec.correlationKey,
                review.spec.decision,
                review.spec.reviewerMember,
                review.spec.reviewerMemberKind,
                review.spec.reviewedAt,
                _json(review.spec.receipts),
                _json(review.spec.importedActivities),
                _json(review.spec.riskFlags),
                _json(_decision_audit_payloads(review.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "GitActivityCorrelationReview", review.object_id, f"git_activity/correlations/{review.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "GitActivityCorrelationReview", review.object_id, review.spec.decisionAudit)


def _insert_automation_records(conn: sqlite3.Connection, index: WorkspaceIndex) -> None:
    for automation in index.automations.values():
        record = manifest_to_record(automation)
        conn.execute(
            "insert into automations(id, owner_member_id, service_member_id, project_id, target_type, status, dry_run, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                automation.object_id,
                automation.spec.ownerMember,
                automation.spec.serviceMember,
                automation.spec.project,
                automation.spec.targetType,
                automation.spec.status,
                1 if automation.spec.dryRun else 0,
                _json(record),
            ),
        )
        _insert_manifest(conn, "Automation", automation.object_id, f"automations/{automation.object_id}.yaml", record)

    for automation_run in index.automation_runs.values():
        record = manifest_to_record(automation_run)
        conn.execute(
            "insert into automation_runs(id, automation_id, project_id, owner_member_id, service_member_id, target_type, trigger_type, status, dry_run, approvals_json, created_task_id, created_run_id, created_task_plan_id, created_message_id, started_at, finished_at, decision_audit_json, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                automation_run.object_id,
                automation_run.spec.automation,
                automation_run.spec.project,
                automation_run.spec.ownerMember,
                automation_run.spec.serviceMember,
                automation_run.spec.targetType,
                automation_run.spec.triggerType,
                automation_run.spec.status,
                1 if automation_run.spec.dryRun else 0,
                _json(automation_run.spec.approvals),
                automation_run.spec.createdTask,
                automation_run.spec.createdRun,
                automation_run.spec.createdTaskPlan,
                automation_run.spec.createdMessage,
                automation_run.spec.startedAt,
                automation_run.spec.finishedAt,
                _json(_decision_audit_payloads(automation_run.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "AutomationRun", automation_run.object_id, f"automations/runs/{automation_run.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "AutomationRun", automation_run.object_id, automation_run.spec.decisionAudit)

    for event in index.automation_trigger_events.values():
        record = manifest_to_record(event)
        conn.execute(
            "insert into automation_trigger_events(id, automation_id, project_id, trigger_type, source, actor_member_id, dedupe_key, dry_run, status, automation_run_id, received_at, decision_audit_json, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.object_id,
                event.spec.automation,
                event.spec.project,
                event.spec.triggerType,
                event.spec.source,
                event.spec.actorMember,
                event.spec.dedupeKey,
                1 if event.spec.dryRun else 0,
                event.spec.status,
                event.spec.automationRun,
                event.spec.receivedAt,
                _json(_decision_audit_payloads(event.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "AutomationTriggerEvent", event.object_id, f"automations/events/{event.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "AutomationTriggerEvent", event.object_id, event.spec.decisionAudit)

    for delivery in index.automation_provider_deliveries.values():
        record = manifest_to_record(delivery)
        conn.execute(
            """
            insert into automation_provider_deliveries(
              id, automation_id, project_id, connector_id, provider, event_type, trigger_type,
              delivery_id, dedupe_key, payload_digest, replay_status, admission_status,
              lifecycle, retained_until, archived_at,
              attempt_count, automation_trigger_event_id, automation_run_id,
              first_seen_at, last_seen_at, received_at, decision_audit_json, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                delivery.object_id,
                delivery.spec.automation,
                delivery.spec.project,
                delivery.spec.connector,
                delivery.spec.provider,
                delivery.spec.eventType,
                delivery.spec.triggerType,
                delivery.spec.deliveryId,
                delivery.spec.dedupeKey,
                delivery.spec.payloadDigest,
                delivery.spec.replayStatus,
                delivery.spec.admissionStatus,
                delivery.spec.lifecycle,
                delivery.spec.retainedUntil,
                delivery.spec.archivedAt,
                delivery.spec.attemptCount,
                delivery.spec.automationTriggerEvent,
                delivery.spec.automationRun,
                delivery.spec.firstSeenAt,
                delivery.spec.lastSeenAt,
                delivery.spec.receivedAt,
                _json(_decision_audit_payloads(delivery.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "AutomationProviderDelivery", delivery.object_id, f"automations/provider_deliveries/{delivery.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "AutomationProviderDelivery", delivery.object_id, delivery.spec.decisionAudit)

    for lease in index.automation_scheduler_leases.values():
        record = manifest_to_record(lease)
        conn.execute(
            "insert into automation_scheduler_leases(id, automation_id, project_id, scheduler_id, tick_key, status, automation_trigger_event_id, automation_run_id, lease_acquired_at, lease_expires_at, heartbeat_at, dedupe_key, decision_audit_json, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                lease.object_id,
                lease.spec.automation,
                lease.spec.project,
                lease.spec.schedulerId,
                lease.spec.tickKey,
                lease.spec.status,
                lease.spec.automationTriggerEvent,
                lease.spec.automationRun,
                lease.spec.leaseAcquiredAt,
                lease.spec.leaseExpiresAt,
                lease.spec.heartbeatAt,
                lease.spec.dedupeKey,
                _json(_decision_audit_payloads(lease.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "AutomationSchedulerLease", lease.object_id, f"automations/leases/{lease.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "AutomationSchedulerLease", lease.object_id, lease.spec.decisionAudit)

    for approval in index.automation_approvals.values():
        record = manifest_to_record(approval)
        conn.execute(
            "insert into automation_approvals(id, automation_run_id, automation_id, project_id, reviewer_member_id, reviewer_member_kind, decision, approval_workflow_id, approval_gates_json, decided_at, expires_at, decision_audit_json, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                approval.object_id,
                approval.spec.automationRun,
                approval.spec.automation,
                approval.spec.project,
                approval.spec.reviewerMember,
                approval.spec.reviewerKind,
                approval.spec.decision,
                approval.spec.approvalWorkflow,
                _json(approval.spec.approvalGates),
                approval.spec.decidedAt,
                approval.spec.expiresAt,
                _json(_decision_audit_payloads(approval.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "AutomationApproval", approval.object_id, f"approval_workflows/{approval.spec.approvalWorkflow}.yaml", record)
        _insert_decision_audit_records(conn, "AutomationApproval", approval.object_id, approval.spec.decisionAudit)

    for workflow in index.approval_workflows.values():
        record = manifest_to_record(workflow)
        conn.execute(
            "insert into approval_workflows(id, project_id, subject_kind, subject_ref, status, current_stage, stages_json, decision_audit_json, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                workflow.object_id,
                workflow.spec.project,
                workflow.spec.subjectKind,
                workflow.spec.subjectRef,
                workflow.spec.status,
                workflow.spec.currentStage,
                _json([stage.model_dump(mode="json", exclude_none=True) for stage in workflow.spec.stages]),
                _json(_decision_audit_payloads(workflow.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "ApprovalWorkflow", workflow.object_id, f"approval_workflows/{workflow.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "ApprovalWorkflow", workflow.object_id, workflow.spec.decisionAudit)


def _insert_policy_connector_records(conn: sqlite3.Connection, index: WorkspaceIndex) -> None:
    for policy in index.permission_policies.values():
        record = manifest_to_record(policy)
        conn.execute(
            "insert into permissions(id, scope_json, default_mode, allow_json, ask_json, deny_json, payload_json) values (?, ?, ?, ?, ?, ?, ?)",
            (
                policy.object_id,
                _json(policy.spec.scope),
                policy.spec.defaultMode,
                _json([rule.model_dump(mode="json") for rule in policy.spec.allow]),
                _json([rule.model_dump(mode="json") for rule in policy.spec.ask]),
                _json([rule.model_dump(mode="json") for rule in policy.spec.deny]),
                _json(record),
            ),
        )
        _insert_manifest(conn, "PermissionPolicy", policy.object_id, f"permissions/{policy.object_id}.yaml", record)

    for request in index.permission_requests.values():
        record = manifest_to_record(request)
        conn.execute(
            "insert into permission_requests(id, project_id, member_id, assignment_id, status, action_json, reviewer_member_id, approval_workflow_id, grant_id, expires_at, decision_audit_json, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.object_id,
                request.spec.project,
                request.spec.member,
                request.spec.assignment,
                request.spec.status,
                _json(request.spec.action.model_dump(mode="json", exclude_none=True)),
                request.spec.reviewerMember,
                request.spec.approvalWorkflow,
                request.spec.grant,
                request.spec.expiresAt,
                _json(_decision_audit_payloads(request.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "PermissionRequest", request.object_id, f"approval_workflows/{request.spec.approvalWorkflow}.yaml", record)
        _insert_decision_audit_records(conn, "PermissionRequest", request.object_id, request.spec.decisionAudit)

    for grant in index.permission_grants.values():
        record = manifest_to_record(grant)
        scope = grant.spec.scope
        conn.execute(
            "insert into permission_grants(id, project_id, member_id, assignment_id, status, action_json, source_request_id, approved_by_member_id, expires_at, decision_audit_json, payload_json) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                grant.object_id,
                scope.get("project"),
                scope.get("member"),
                scope.get("assignment"),
                grant.spec.status,
                _json(grant.spec.action.model_dump(mode="json", exclude_none=True)),
                grant.spec.sourceRequest,
                grant.spec.approvedByMember,
                grant.spec.expiresAt,
                _json(_decision_audit_payloads(grant.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "PermissionGrant", grant.object_id, f"permission_grants/{grant.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "PermissionGrant", grant.object_id, grant.spec.decisionAudit)

    for skill in index.skills.values():
        record = manifest_to_record(skill)
        conn.execute(
            "insert into skills(id, owner_member_id, lifecycle, capabilities_json, required_permissions_json, payload_json) values (?, ?, ?, ?, ?, ?)",
            (skill.object_id, skill.spec.ownerMember, skill.spec.lifecycle, _json(skill.spec.capabilities), _json(skill.spec.requiredPermissions), _json(record)),
        )
        _insert_manifest(conn, "Skill", skill.object_id, f"skills/{skill.object_id}.yaml", record)

    for connector in index.connectors.values():
        record = manifest_to_record(connector)
        conn.execute(
            "insert into connectors(id, provider, connector_type, owner_member_id, payload_json) values (?, ?, ?, ?, ?)",
            (connector.object_id, connector.spec.provider, connector.spec.connectorType, connector.spec.ownerMember, _json(record)),
        )
        _insert_manifest(conn, "Connector", connector.object_id, f"connectors/{connector.object_id}.yaml", record)

    for check in index.connector_health_checks.values():
        record = manifest_to_record(check)
        conn.execute(
            """
            insert into connector_health_checks(
              id, connector_id, provider, connector_type, project_id, status,
              readiness, token_status, installation_status, lifecycle, retained_until, archived_at, checked_at,
              decision_audit_json, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                check.object_id,
                check.spec.connector,
                check.spec.provider,
                check.spec.connectorType,
                check.spec.project,
                check.spec.status,
                check.spec.readiness,
                check.spec.tokenStatus,
                check.spec.installationStatus,
                check.spec.lifecycle,
                check.spec.retainedUntil,
                check.spec.archivedAt,
                check.spec.checkedAt,
                _json(_decision_audit_payloads(check.spec.decisionAudit)),
                _json(record),
            ),
        )
        _insert_manifest(conn, "ConnectorHealthCheck", check.object_id, f"connectors/health/{check.object_id}.yaml", record)
        _insert_decision_audit_records(conn, "ConnectorHealthCheck", check.object_id, check.spec.decisionAudit)

    for profile in index.model_profiles.values():
        record = manifest_to_record(profile)
        conn.execute(
            """
            insert into model_profiles(
              id, provider, model, gateway, manifest_path, pricing_json,
              default_members_json, default_assignments_json, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.object_id,
                profile.spec.provider,
                profile.spec.model,
                profile.spec.gateway,
                f"model_profiles/{profile.object_id}.yaml",
                _json(profile.spec.pricing.model_dump(mode="json") if profile.spec.pricing else None),
                _json(profile.spec.defaultForMembers),
                _json(profile.spec.defaultForAssignments),
                _json(record),
            ),
        )
        _insert_manifest(conn, "ModelProfile", profile.object_id, f"model_profiles/{profile.object_id}.yaml", record)

    for policy in index.budget_policies.values():
        record = manifest_to_record(policy)
        conn.execute(
            """
            insert into budget_policies(
              id, project_id, member_id, assignment_id, task_id, limits_json,
              rate_limit_json, fallback_json, enforcement_json, manifest_path, payload_json
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                policy.object_id,
                policy.spec.scope.project,
                policy.spec.scope.member,
                policy.spec.scope.assignment,
                policy.spec.scope.task,
                _json(policy.spec.limits.model_dump(mode="json", exclude_none=True)),
                _json(policy.spec.rateLimit.model_dump(mode="json", exclude_none=True)),
                _json(policy.spec.fallback.model_dump(mode="json", exclude_none=True)),
                _json(policy.spec.enforcement.model_dump(mode="json", exclude_none=True)),
                f"budget_policies/{policy.object_id}.yaml",
                _json(record),
            ),
        )
        _insert_manifest(conn, "BudgetPolicy", policy.object_id, f"budget_policies/{policy.object_id}.yaml", record)

    _insert_project_member_views(conn, index)

def _insert_project_member_views(conn: sqlite3.Connection, index: WorkspaceIndex) -> None:
    for member_id in sorted(index.members):
        assignments = [assignment for assignment in index.assignments.values() if assignment.spec.member == member_id]
        active_tasks = [
            task
            for task in index.tasks.values()
            if task.spec.assignedMember == member_id and task.spec.status not in {"DONE", "FAILED", "ARCHIVED"}
        ]
        tasks = [task for task in index.tasks.values() if task.spec.assignedMember == member_id]
        runs = [run for run in index.runs.values() if run.spec.member == member_id]
        conn.execute(
            """
            insert into project_member_views(
              project_id, member_id, assignment_count, task_count, run_count, active_task_count, latest_activity_at
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (index.project.object_id, member_id, len(assignments), len(tasks), len(runs), len(active_tasks), None),
        )


