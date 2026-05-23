from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import (
    admit_external_automation_event,
    artifact_retention_candidates,
    approve_permission_request,
    approve_automation_run,
    automation_provider_delivery_records,
    automation_run_records,
    automation_scheduler_lease_records,
    automation_trigger_event_records,
    check_connector_health,
    cleanup_automation_provider_deliveries,
    connector_failure_reminder_candidates,
    connector_operations_overview,
    dry_run_automation,
    emit_scheduler_tick,
    execute_automation_run,
    admit_provider_git_activity_import,
    git_activity_correlation_preview,
    git_activity_correlation_promotion_candidates,
    index_workspace,
    ingest_automation_event,
    load_workspace,
    reject_automation_run,
    recover_scheduler_lease,
    retry_provider_delivery,
    request_automation_run_permission,
    scan_cron_scheduler,
    trigger_automation,
    review_git_activity_correlation,
)
from aiteamos_workspace.io import read_yaml, write_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class AutomationRunTest(unittest.TestCase):
    def test_dry_run_creates_source_of_truth_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            run = dry_run_automation(workspace, "memory-health-dry-run", actor_member="manager")

            self.assertEqual(run.kind, "AutomationRun")
            self.assertEqual(run.spec.automation, "memory-health-dry-run")
            self.assertEqual(run.spec.status, "dry-run")
            self.assertTrue(run.spec.dryRun)
            self.assertEqual(run.spec.serviceMember, "memory-service")
            self.assertEqual(run.spec.targetType, "memory_health")
            self.assertEqual(run.spec.permissionDecisions[0]["decision"], "allow")
            self.assertEqual(run.spec.permissionDecisions[0]["action"]["canonical"], "Automation(memory_health:memory-health-dry-run)")
            self.assertEqual(run.spec.permissionDecisions[0]["riskAssessment"]["riskLevel"], "low")
            self.assertEqual(run.spec.decisionAudit[0].decisionKind, "service_policy_decision")
            self.assertEqual(run.spec.decisionAudit[0].actorMember, "memory-service")
            self.assertEqual(run.spec.decisionAudit[0].actorMemberKind, "service")
            self.assertEqual(run.spec.decisionAudit[0].authority, "enforce")
            self.assertEqual(run.spec.decisionAudit[0].riskAssessment.riskLevel, "low")
            self.assertIsNone(run.spec.createdTask)
            self.assertIsNone(run.spec.createdRun)
            index = load_workspace(workspace)
            self.assertIn(run.object_id, index.automation_runs)
            self.assertTrue((workspace / "automations" / "runs" / f"{run.object_id}.yaml").exists())

    def test_trigger_dry_run_only_automation_is_blocked_without_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            run = trigger_automation(workspace, "memory-health-dry-run", actor_member="manager")

            self.assertEqual(run.spec.status, "blocked")
            self.assertTrue(run.spec.dryRun)
            self.assertIn("dry-run only", " ".join(run.spec.blockers))
            self.assertEqual(run.spec.permissionDecisions[0]["decision"], "allow")
            self.assertIsNone(run.spec.createdTask)
            self.assertIsNone(run.spec.createdRun)

    def test_automation_permission_request_projects_outcome_to_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "blocked-review",
                "review",
                {"maxCandidates": 1},
            )

            run = trigger_automation(workspace, "blocked-review", actor_member="manager")

            self.assertEqual(run.spec.status, "blocked")
            self.assertEqual(run.spec.permissionDecisions[0]["decision"], "deny")
            projected = automation_run_records(workspace, automation_id="blocked-review")[0]
            self.assertEqual(projected["spec"]["permissionApprovalOutcome"], "request-required")
            request_result = request_automation_run_permission(
                workspace,
                run.object_id,
                actor_member="frontend-human",
                dry_run=False,
            )
            permission_request = request_result["permissionRequest"]
            self.assertEqual(permission_request["spec"]["source"], "automation-run-permission-request")
            self.assertEqual(permission_request["spec"]["automation"], "blocked-review")
            self.assertEqual(permission_request["spec"]["automationRun"], run.object_id)
            pending = automation_run_records(workspace, automation_id="blocked-review")[0]
            self.assertEqual(pending["spec"]["pendingPermissionRequestIds"], [permission_request["id"]])
            approve_permission_request(workspace, permission_request["id"], reviewer_member="frontend-human")
            approved = automation_run_records(workspace, automation_id="blocked-review")[0]
            self.assertEqual(approved["spec"]["activePermissionGrantIds"], [approved["spec"]["permissionRequests"][0]["spec"]["grant"]])
            self.assertEqual(approved["spec"]["permissionApprovalOutcome"], "approved-active-grant")

    def test_api_lists_and_writes_automation_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            self.assertEqual(client.get("/automations/runs").json(), [])
            response = client.post("/automations/memory-health-dry-run/dry-run", json={"actorMember": "manager"})

            self.assertEqual(response.status_code, 200)
            created = response.json()
            self.assertEqual(created["kind"], "AutomationRun")
            self.assertEqual(created["spec"]["status"], "dry-run")
            self.assertEqual(created["spec"]["decisionAudit"][0]["decisionKind"], "service_policy_decision")
            self.assertEqual(created["spec"]["decisionAudit"][0]["riskAssessment"]["riskLevel"], "low")
            runs = client.get("/automations/memory-health-dry-run/runs").json()
            self.assertEqual([item["id"] for item in runs], [created["id"]])
            self.assertEqual(runs[0]["latestDecisionKind"], "service_policy_decision")
            self.assertEqual(runs[0]["latestRiskLevel"], "low")

    def test_executor_creates_human_reminder_from_queued_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "remind-frontend",
                "human_reminder",
                {
                    "toMembers": ["frontend-human"],
                    "body": "Review the automation queue before closeout.",
                    "priority": "normal",
                },
            )

            queued = trigger_automation(workspace, "remind-frontend", actor_member="manager")
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(queued.spec.status, "queued")
            self.assertEqual(executed.spec.status, "succeeded")
            self.assertIsNotNone(executed.spec.createdMessage)
            self.assertIsNone(executed.spec.createdRun)
            self.assertEqual(executed.spec.decisionAudit[-1].decisionKind, "system_check")
            self.assertEqual(executed.spec.decisionAudit[-1].decision, "succeeded")
            index = load_workspace(workspace)
            self.assertIn(executed.spec.createdMessage, index.member_messages)
            message = index.member_messages[executed.spec.createdMessage or ""]
            self.assertEqual(message.spec.fromMember, "memory-service")
            self.assertEqual(message.spec.toMembers, ["frontend-human"])
            self.assertEqual(message.spec.messageType, "message")
            self.assertEqual(message.spec.audit["automation"], "remind-frontend")

    def test_executor_routes_connector_failure_reminders_with_throttle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                secret_refs={"tokenEnv": "AITEAMOS_TEST_GITHUB_TOKEN"},
            )
            os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
            check = check_connector_health(workspace, "github-main", actor_member="memory-service")
            _write_automation(
                workspace,
                "route-connector-failures",
                "connector_failure_reminder",
                {
                    "connector": "github-main",
                    "maxMessagesPerRun": 1,
                    "throttleMinutes": 60,
                },
            )

            queued = trigger_automation(workspace, "route-connector-failures", actor_member="manager")
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(queued.spec.status, "queued")
            self.assertEqual(executed.spec.status, "succeeded")
            self.assertEqual(executed.spec.targetType, "connector_failure_reminder")
            self.assertIsNotNone(executed.spec.createdMessage)
            index = load_workspace(workspace)
            message = index.member_messages[executed.spec.createdMessage or ""]
            self.assertEqual(message.spec.fromMember, "memory-service")
            self.assertEqual(message.spec.toMembers, ["memory-service"])
            self.assertEqual(message.spec.attachments, [check.object_id])
            self.assertEqual(message.spec.audit["source"], "connector-failure-reminder")
            self.assertEqual(message.spec.audit["automation"], "route-connector-failures")
            self.assertEqual(message.spec.audit["automationRun"], queued.object_id)
            self.assertIn("Routed 1 connector failure reminder", " ".join(executed.spec.logs))

            second_check = check_connector_health(workspace, "github-main", actor_member="memory-service")
            self.assertNotEqual(second_check.object_id, check.object_id)
            second = trigger_automation(workspace, "route-connector-failures", actor_member="manager")
            throttled = execute_automation_run(workspace, second.object_id, actor_member="memory-service")
            self.assertEqual(throttled.spec.status, "succeeded")
            self.assertIsNone(throttled.spec.createdMessage)
            self.assertIn("skipped 2", " ".join(throttled.spec.logs))
            reminder_messages = [
                message
                for message in load_workspace(workspace).member_messages.values()
                if message.spec.audit.get("source") == "connector-failure-reminder"
                and message.spec.audit.get("automation") == "route-connector-failures"
            ]
            self.assertEqual(len(reminder_messages), 1)

    def test_executor_promotes_approved_git_correlation_under_service_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            payload = {
                "ref": "refs/heads/main",
                "after": "1234567890abcdef1234567890abcdef12345678",
                "repository": {"full_name": "example/aiteamos"},
                "sender": {"login": "octobot"},
                "head_commit": {"message": "bounded automation promotion", "timestamp": "2026-05-21T10:00:00+08:00"},
            }
            receipt = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                payload=payload,
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )["receipt"]
            receipt_path = workspace / "git_activity" / "imports" / f"{receipt.object_id}.yaml"
            receipt_payload = read_yaml(receipt_path)
            receipt_payload["spec"]["importPolicy"] = "service-policy-import"
            receipt_payload["spec"]["normalized"]["member"] = "backend-digital"
            receipt_payload["spec"]["normalized"]["assignment"] = "aiteamos-backend-runtime"
            write_yaml(receipt_path, receipt_payload)
            preview = git_activity_correlation_preview(workspace, project="aiteamos", repository="aiteamos", provider="github")
            group = _preview_group_for_receipts(preview, receipt.object_id)
            reviewed_at = datetime.now().astimezone() - timedelta(minutes=5)
            fresh_candidate_time = reviewed_at + timedelta(minutes=5)
            stale_candidate_time = reviewed_at + timedelta(hours=72)
            review = review_git_activity_correlation(
                workspace,
                correlation_key=str(group["correlationKey"]),
                receipts=[receipt.object_id],
                reviewer_member="frontend-human",
                decision="approved",
                summary="Approved service-policy correlation promotion.",
                recommended_member="backend-digital",
                recommended_assignment="aiteamos-backend-runtime",
                recommended_activity_type="commit",
                reviewed_at=reviewed_at.isoformat(timespec="milliseconds"),
            )["review"]
            _write_automation(
                workspace,
                "git-correlation-promoter",
                "git_activity_correlation_promotion",
                {
                    "reviewIds": [review.object_id],
                    "maxPromotionsPerRun": 1,
                    "maxApprovalAgeHours": 48,
                },
            )

            candidates = git_activity_correlation_promotion_candidates(
                workspace,
                automation="git-correlation-promoter",
                service_member="memory-service",
                now=fresh_candidate_time,
            )
            self.assertEqual(candidates["summary"]["eligible"], 1)
            self.assertEqual(candidates["candidates"][0]["promotionPreview"]["member"], "backend-digital")
            stale_candidates = git_activity_correlation_promotion_candidates(
                workspace,
                automation="git-correlation-promoter",
                service_member="memory-service",
                now=stale_candidate_time,
            )
            self.assertEqual(stale_candidates["summary"]["eligible"], 0)
            self.assertTrue(
                any("approval is stale" in blocker for blocker in stale_candidates["candidates"][0]["blockers"])
            )

            queued = trigger_automation(workspace, "git-correlation-promoter", actor_member="manager")
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(queued.spec.status, "queued")
            self.assertEqual(executed.spec.status, "succeeded")
            self.assertIn("Promoted 1 approved Git activity correlation review", " ".join(executed.spec.logs))
            index = load_workspace(workspace)
            updated_review = index.git_activity_correlation_reviews[review.object_id]
            self.assertEqual(len(updated_review.spec.importedActivities), 1)
            activity_id = updated_review.spec.importedActivities[0]
            self.assertIn(activity_id, index.git_activities)
            activity = index.git_activities[activity_id]
            self.assertEqual(activity.spec.member, "backend-digital")
            self.assertEqual(activity.spec.assignment, "aiteamos-backend-runtime")
            self.assertEqual(activity.spec.activityType, "commit")
            updated_receipt = index.git_activity_import_receipts[receipt.object_id]
            self.assertEqual(updated_receipt.spec.status, "imported")
            self.assertEqual(updated_receipt.spec.importedActivities, [activity_id])
            self.assertEqual(updated_receipt.spec.decisionAudit[-1].actorMember, "memory-service")
            self.assertEqual(updated_receipt.spec.decisionAudit[-1].decisionKind, "service_policy_decision")

    def test_executor_sweeps_git_activity_retention_without_deleting_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            activity_id = "GIT-20260521T090500000"
            _patch_git_activity(
                workspace,
                activity_id,
                retainedUntil="2026-05-20T12:00:00+08:00",
                exportPolicy="include",
            )
            _write_automation(
                workspace,
                "git-retention-sweeper",
                "git_activity_retention_sweep",
                {
                    "project": "aiteamos",
                    "maxCandidatesPerRun": 1,
                },
            )

            queued = trigger_automation(workspace, "git-retention-sweeper", actor_member="manager")
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(queued.spec.status, "queued")
            self.assertEqual(executed.spec.status, "succeeded")
            self.assertIn("Swept 1 expired Git activity retention candidate", " ".join(executed.spec.logs))
            index = load_workspace(workspace)
            activity = index.git_activities[activity_id]
            self.assertEqual(activity.spec.lifecycle, "archived")
            self.assertEqual(activity.spec.exportPolicy, "sanitize")
            self.assertEqual(activity.spec.decisionAudit[-1].actorMember, "memory-service")
            self.assertEqual(activity.spec.decisionAudit[-1].decisionKind, "service_policy_decision")
            receipt = index.git_activity_import_receipts["GITIMP-20260521T093000000"]
            self.assertEqual(receipt.spec.importedActivities, [activity_id])

    def test_executor_fails_git_activity_retention_without_lifecycle_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_retention_executor_policy_without_git_activity_edit(workspace)
            activity_id = "GIT-20260521T090500000"
            _patch_git_activity(
                workspace,
                activity_id,
                retainedUntil="2026-05-20T12:00:00+08:00",
                exportPolicy="include",
            )
            _write_automation(
                workspace,
                "git-retention-sweeper",
                "git_activity_retention_sweep",
                {
                    "project": "aiteamos",
                    "maxCandidatesPerRun": 1,
                },
            )

            queued = trigger_automation(workspace, "git-retention-sweeper", actor_member="manager")
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(queued.spec.status, "queued")
            self.assertEqual(executed.spec.status, "failed")
            self.assertTrue(any("GitActivity retention sweep failed" in blocker for blocker in executed.spec.blockers))
            index = load_workspace(workspace)
            activity = index.git_activities[activity_id]
            self.assertEqual(activity.spec.lifecycle, "active")
            self.assertEqual(activity.spec.exportPolicy, "include")
            receipt = index.git_activity_import_receipts["GITIMP-20260521T093000000"]
            self.assertEqual(receipt.spec.importedActivities, [activity_id])

    def test_artifact_retention_candidates_default_to_seven_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            artifact_id = _write_artifact_manifest(
                workspace,
                created_at="2026-05-01T00:00:00+08:00",
                export_policy="include",
            )

            candidates = artifact_retention_candidates(
                workspace,
                project="aiteamos",
                now="2026-05-09T00:00:00+08:00",
            )

            self.assertEqual(candidates["defaultRetentionDays"], 7)
            self.assertEqual(candidates["summary"]["expiredCandidates"], 1)
            candidate = candidates["candidates"][0]["spec"]
            self.assertEqual(candidate["artifact"], artifact_id)
            self.assertEqual(candidate["retainedUntil"], "2026-05-08T00:00:00.000+08:00")
            self.assertEqual(candidate["recommendedLifecycle"], "archived")
            self.assertEqual(candidate["recommendedExportPolicy"], "manifest_only")

    def test_executor_sweeps_artifact_retention_without_deleting_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            artifact_id = _write_artifact_manifest(
                workspace,
                created_at="2026-05-01T00:00:00+08:00",
                export_policy="include",
            )
            _write_automation(
                workspace,
                "artifact-retention-sweeper",
                "artifact_retention_sweep",
                {
                    "project": "aiteamos",
                    "maxCandidatesPerRun": 1,
                    "now": "2026-05-09T00:00:00+08:00",
                },
            )

            queued = trigger_automation(workspace, "artifact-retention-sweeper", actor_member="manager")
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(queued.spec.status, "queued")
            self.assertEqual(executed.spec.status, "succeeded")
            self.assertIn("Swept 1 expired artifact retention candidate", " ".join(executed.spec.logs))
            self.assertTrue((workspace / "artifacts" / "manifests" / f"{artifact_id}.yaml").exists())
            index = load_workspace(workspace)
            artifact = index.artifacts[artifact_id]
            self.assertEqual(artifact.spec.lifecycle, "archived")
            self.assertEqual(artifact.spec.exportPolicy, "manifest_only")
            self.assertEqual(artifact.spec.retainedUntil, "2026-05-08T00:00:00.000+08:00")
            self.assertEqual(artifact.spec.decisionAudit[-1].actorMember, "memory-service")
            self.assertEqual(artifact.spec.decisionAudit[-1].decisionKind, "service_policy_decision")

    def test_api_creates_connector_failure_reminder_automation_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                secret_refs={"tokenEnv": "AITEAMOS_TEST_GITHUB_TOKEN"},
            )
            os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
            check_connector_health(workspace, "github-main", actor_member="memory-service")
            client = TestClient(create_app(workspace))

            created = client.post(
                "/automations",
                json={
                    "name": "API Connector Reminder",
                    "targetType": "connector_failure_reminder",
                    "ownerMember": "manager",
                    "serviceMember": "memory-service",
                    "project": "aiteamos",
                    "target": {"connector": "github-main", "maxMessagesPerRun": 1, "throttleMinutes": 30},
                    "triggers": [{"triggerType": "manual"}],
                    "dryRun": False,
                    "permissionPolicies": ["service-automation-executor-test"],
                },
            )

            self.assertEqual(created.status_code, 200)
            self.assertEqual(created.json()["id"], "api-connector-reminder")
            self.assertEqual(created.json()["spec"]["targetType"], "connector_failure_reminder")
            self.assertIn("api-connector-reminder", load_workspace(workspace).automations)

            queued = client.post("/automations/api-connector-reminder/trigger", json={"actorMember": "manager"})
            self.assertEqual(queued.status_code, 200)
            self.assertEqual(queued.json()["spec"]["status"], "queued")
            executed = client.post(f"/automations/runs/{queued.json()['id']}/execute", json={"actorMember": "memory-service"})
            self.assertEqual(executed.status_code, 200)
            self.assertEqual(executed.json()["spec"]["status"], "succeeded")
            self.assertIsNotNone(executed.json()["spec"]["createdMessage"])

    def test_api_creates_git_activity_retention_automation_with_scheduler_preset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            client = TestClient(create_app(workspace))

            created = client.post(
                "/automations",
                json={
                    "name": "Daily Git Retention Sweep",
                    "targetType": "git_activity_retention_sweep",
                    "ownerMember": "manager",
                    "serviceMember": "memory-service",
                    "project": "aiteamos",
                    "target": {
                        "project": "aiteamos",
                        "maxCandidatesPerRun": 1,
                        "targetLifecycle": "archived",
                    },
                    "triggers": [{"triggerType": "cron", "config": {"preset": "daily", "cron": "0 3 * * *"}}],
                    "dryRun": False,
                    "permissionPolicies": ["service-automation-executor-test"],
                    "approvalGates": ["retention-sweep-review"],
                },
            )

            self.assertEqual(created.status_code, 200)
            self.assertEqual(created.json()["id"], "daily-git-retention-sweep")
            self.assertEqual(created.json()["spec"]["targetType"], "git_activity_retention_sweep")
            self.assertEqual(created.json()["spec"]["target"]["maxCandidatesPerRun"], 1)
            self.assertEqual(created.json()["spec"]["triggers"][0]["triggerType"], "cron")
            self.assertEqual(created.json()["spec"]["triggers"][0]["config"]["preset"], "daily")
            self.assertEqual(created.json()["spec"]["approvalGates"], ["retention-sweep-review"])
            self.assertIn("daily-git-retention-sweep", load_workspace(workspace).automations)

            dry_run = client.post(
                "/automations/daily-git-retention-sweep/dry-run",
                json={
                    "actorMember": "manager",
                    "sourceEvent": {"triggerType": "cron", "source": "dashboard-preset", "preset": "daily"},
                },
            )
            self.assertEqual(dry_run.status_code, 200)
            self.assertEqual(dry_run.json()["spec"]["status"], "dry-run")
            self.assertTrue(dry_run.json()["spec"]["dryRun"])

            scheduled = client.post(
                "/automations/daily-git-retention-sweep/scheduler/ticks",
                json={"schedulerId": "test-scheduler", "tickKey": "20260521T0300"},
            )
            self.assertEqual(scheduled.status_code, 200)
            self.assertEqual(scheduled.json()["run"]["spec"]["status"], "pending-approval")
            self.assertEqual(scheduled.json()["run"]["spec"]["triggerType"], "cron")
            self.assertEqual(scheduled.json()["run"]["spec"]["approvalGates"], ["retention-sweep-review"])

    def test_api_creates_artifact_retention_automation_with_scheduler_preset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            client = TestClient(create_app(workspace))

            created = client.post(
                "/automations",
                json={
                    "name": "Daily Artifact Retention Sweep",
                    "targetType": "artifact_retention_sweep",
                    "ownerMember": "manager",
                    "serviceMember": "memory-service",
                    "project": "aiteamos",
                    "target": {
                        "project": "aiteamos",
                        "maxCandidatesPerRun": 1,
                        "targetLifecycle": "archived",
                    },
                    "triggers": [{"triggerType": "cron", "config": {"preset": "daily", "cron": "0 4 * * *"}}],
                    "dryRun": False,
                    "permissionPolicies": ["service-automation-executor-test"],
                    "approvalGates": ["retention-sweep-review"],
                },
            )

            self.assertEqual(created.status_code, 200)
            self.assertEqual(created.json()["id"], "daily-artifact-retention-sweep")
            self.assertEqual(created.json()["spec"]["targetType"], "artifact_retention_sweep")
            self.assertEqual(created.json()["spec"]["target"]["maxCandidatesPerRun"], 1)
            self.assertEqual(created.json()["spec"]["triggers"][0]["triggerType"], "cron")
            self.assertEqual(created.json()["spec"]["approvalGates"], ["retention-sweep-review"])
            self.assertIn("daily-artifact-retention-sweep", load_workspace(workspace).automations)

    def test_executor_creates_task_plan_from_queued_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "plan-backend-task",
                "task_planning",
                {
                    "goal": "Plan a bounded backend runtime slice.",
                    "subtasks": [
                        {
                            "title": "Add executor tests",
                            "assignedMember": "backend-digital",
                            "assignment": "aiteamos-backend-runtime",
                            "acceptance": ["Tests validate executor output manifests."],
                        }
                    ],
                    "risks": ["schema/API drift"],
                    "reviewGates": ["architecture review"],
                },
            )

            queued = trigger_automation(workspace, "plan-backend-task", actor_member="manager")
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(executed.spec.status, "succeeded")
            self.assertIsNotNone(executed.spec.createdTaskPlan)
            index = load_workspace(workspace)
            plan = index.task_plans[executed.spec.createdTaskPlan or ""]
            self.assertEqual(plan.spec.goal, "Plan a bounded backend runtime slice.")
            self.assertEqual(plan.spec.createdByMember, "memory-service")
            self.assertEqual(plan.spec.subtasks[0].assignedMember, "backend-digital")

    def test_executor_creates_linked_task_and_run_without_worker_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "queue-backend-run",
                "digital_execution",
                {
                    "title": "Executor linked run smoke test",
                    "assignedMember": "backend-digital",
                    "assignment": "aiteamos-backend-runtime",
                    "acceptance": ["Run manifest is linked but worker is not executed."],
                    "mode": "managed",
                    "runStatus": "READY",
                },
            )

            queued = trigger_automation(workspace, "queue-backend-run", actor_member="manager")
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(executed.spec.status, "succeeded")
            self.assertIsNotNone(executed.spec.createdTask)
            self.assertIsNotNone(executed.spec.createdRun)
            index = load_workspace(workspace)
            task = index.tasks[executed.spec.createdTask or ""]
            linked_run = index.runs[executed.spec.createdRun or ""]
            self.assertEqual(task.spec.assignedMember, "backend-digital")
            self.assertEqual(task.spec.status, "QUEUED")
            self.assertEqual(task.spec.executionMode, "managed_llm")
            self.assertEqual(linked_run.spec.task, task.object_id)
            self.assertEqual(linked_run.spec.member, "backend-digital")
            self.assertEqual(linked_run.spec.mode, "managed_llm")
            self.assertEqual(linked_run.spec.status, "READY")

    def test_executor_blocks_linked_run_without_output_edit_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            write_yaml(
                workspace / "permissions" / "service-automation-executor-test.yaml",
                {
                    "apiVersion": "aiteamos.dev/v1alpha1",
                    "kind": "PermissionPolicy",
                    "metadata": {"name": "service-automation-executor-test"},
                    "spec": {
                        "scope": {"memberKind": "service", "member": "memory-service"},
                        "defaultMode": "deny",
                        "allow": [{"match": "Automation(digital_execution:*)"}],
                    },
                },
            )
            _write_automation(
                workspace,
                "queue-backend-run",
                "digital_execution",
                {
                    "title": "Executor linked run permission gate",
                    "assignedMember": "backend-digital",
                    "assignment": "aiteamos-backend-runtime",
                    "acceptance": ["Output writes need explicit permission."],
                },
            )

            queued = trigger_automation(workspace, "queue-backend-run", actor_member="manager")
            blocked = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")

            self.assertEqual(blocked.spec.status, "blocked")
            self.assertIsNone(blocked.spec.createdTask)
            self.assertIsNone(blocked.spec.createdRun)
            self.assertTrue(any("Automation output permission denied" in blocker for blocker in blocked.spec.blockers))
            self.assertTrue(any(decision.get("action", {}).get("path") == "/.aiteamos/tasks/**" for decision in blocked.spec.permissionDecisions))

    def test_api_creates_and_executes_hybrid_assist_automation_without_worker_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            client = TestClient(create_app(workspace))

            created = client.post(
                "/automations",
                json={
                    "name": "API Hybrid Assist",
                    "targetType": "hybrid_assist",
                    "ownerMember": "manager",
                    "serviceMember": "memory-service",
                    "project": "aiteamos",
                    "target": {
                        "title": "API hybrid assist smoke test",
                        "assignedMember": "frontend-human",
                        "assignment": "aiteamos-dashboard",
                        "acceptance": ["Run is assisted and waits for human ingest."],
                    },
                    "triggers": [{"triggerType": "manual"}],
                    "dryRun": False,
                    "permissionPolicies": ["service-automation-executor-test"],
                },
            )

            self.assertEqual(created.status_code, 200)
            self.assertEqual(created.json()["spec"]["targetType"], "hybrid_assist")
            queued = client.post("/automations/api-hybrid-assist/trigger", json={"actorMember": "manager"})
            self.assertEqual(queued.status_code, 200)
            self.assertEqual(queued.json()["spec"]["status"], "queued")
            executed = client.post(f"/automations/runs/{queued.json()['id']}/execute", json={"actorMember": "memory-service"})
            self.assertEqual(executed.status_code, 200)
            self.assertEqual(executed.json()["spec"]["status"], "succeeded")
            self.assertIsNotNone(executed.json()["spec"]["createdTask"])
            self.assertIsNotNone(executed.json()["spec"]["createdRun"])

            index = load_workspace(workspace)
            task = index.tasks[executed.json()["spec"]["createdTask"]]
            run = index.runs[executed.json()["spec"]["createdRun"]]
            self.assertEqual(task.spec.assignedMember, "frontend-human")
            self.assertEqual(task.spec.executionMode, "assisted")
            self.assertEqual(run.spec.member, "frontend-human")
            self.assertEqual(run.spec.mode, "assisted")
            self.assertEqual(run.spec.status, "READY")

    def test_api_executes_queued_automation_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "api-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "API executor smoke test."},
            )
            client = TestClient(create_app(workspace))

            queued = client.post("/automations/api-reminder/trigger", json={"actorMember": "manager"}).json()
            response = client.post(f"/automations/runs/{queued['id']}/execute", json={"actorMember": "memory-service"})

            self.assertEqual(response.status_code, 200)
            executed = response.json()
            self.assertEqual(executed["spec"]["status"], "succeeded")
            self.assertIn("createdMessage", executed["spec"])
            runs = client.get("/automations/runs").json()
            self.assertEqual(runs[0]["latestDecisionKind"], "system_check")

    def test_human_approval_queues_pending_automation_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "approved-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Approved automation smoke test."},
                approval_gates=["human-approval"],
            )

            pending = trigger_automation(workspace, "approved-reminder", actor_member="manager")

            self.assertEqual(pending.spec.status, "pending-approval")
            with self.assertRaises(ValueError):
                execute_automation_run(workspace, pending.object_id, actor_member="memory-service")

            queued = approve_automation_run(
                workspace,
                pending.object_id,
                reviewer_member="frontend-human",
                reason="Safe to create reminder.",
            )
            executed = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")
            index = load_workspace(workspace)

            self.assertEqual(queued.spec.status, "queued")
            self.assertEqual(queued.spec.approvalGates, [])
            self.assertEqual(len(queued.spec.approvals), 1)
            self.assertEqual(executed.spec.status, "succeeded")
            self.assertIn(queued.spec.approvals[0], index.automation_approvals)
            approval = index.automation_approvals[queued.spec.approvals[0]]
            self.assertEqual(approval.spec.decision, "approved")
            self.assertEqual(approval.spec.reviewerMember, "frontend-human")
            self.assertEqual(approval.spec.reviewerKind, "human")
            self.assertEqual(approval.spec.approvalGates, ["human-approval"])
            self.assertIsNotNone(approval.spec.expiresAt)
            self.assertEqual(approval.spec.decisionAudit[0].decisionKind, "human_approval")

    def test_reject_pending_automation_run_blocks_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "rejected-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Rejected automation smoke test."},
                approval_gates=["human-approval"],
            )

            pending = trigger_automation(workspace, "rejected-reminder", actor_member="manager")
            blocked = reject_automation_run(
                workspace,
                pending.object_id,
                reviewer_member="frontend-human",
                reason="Do not send this reminder.",
            )

            self.assertEqual(blocked.spec.status, "blocked")
            self.assertEqual(len(blocked.spec.approvals), 1)
            with self.assertRaises(ValueError):
                execute_automation_run(workspace, blocked.object_id, actor_member="memory-service")
            index = load_workspace(workspace)
            approval = index.automation_approvals[blocked.spec.approvals[0]]
            self.assertEqual(approval.spec.decision, "rejected")
            self.assertEqual(approval.spec.decisionAudit[0].decision, "rejected")

    def test_api_approves_pending_automation_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "api-approval-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "API approval smoke test."},
                approval_gates=["human-approval"],
            )
            client = TestClient(create_app(workspace))

            pending = client.post("/automations/api-approval-reminder/trigger", json={"actorMember": "manager"}).json()
            approve_response = client.post(
                f"/automations/runs/{pending['id']}/approve",
                json={"reviewerMember": "frontend-human", "reason": "Approved through API."},
            )

            self.assertEqual(approve_response.status_code, 200)
            queued = approve_response.json()
            self.assertEqual(queued["spec"]["status"], "queued")
            self.assertEqual(queued["spec"]["approvalGates"], [])
            self.assertEqual(len(queued["spec"]["approvals"]), 1)
            approvals = client.get("/automations/approvals").json()
            self.assertEqual(approvals[0]["spec"]["decision"], "approved")
            self.assertEqual(approvals[0]["spec"]["reviewerMember"], "frontend-human")

    def test_ingest_automation_event_writes_event_and_run_with_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "webhook-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Webhook event smoke test."},
                triggers=[{"triggerType": "webhook"}],
            )

            result = ingest_automation_event(
                workspace,
                "webhook-reminder",
                trigger_type="webhook",
                source="webhook",
                payload={"deliveryId": "delivery-1"},
                dedupe_key="delivery-1",
            )
            duplicate = ingest_automation_event(
                workspace,
                "webhook-reminder",
                trigger_type="webhook",
                source="webhook",
                payload={"deliveryId": "delivery-1"},
                dedupe_key="delivery-1",
            )
            event = result["event"]
            run = result["run"]
            index = load_workspace(workspace)

            self.assertIsNotNone(event)
            self.assertIsNotNone(run)
            self.assertEqual(event.object_id, duplicate["event"].object_id)
            self.assertEqual(run.object_id, duplicate["run"].object_id)
            self.assertEqual(len(index.automation_trigger_events), 1)
            self.assertEqual(event.spec.triggerType, "webhook")
            self.assertEqual(event.spec.source, "webhook")
            self.assertEqual(event.spec.automationRun, run.object_id)
            self.assertEqual(event.spec.decisionAudit[0].decisionKind, "system_check")
            self.assertEqual(run.spec.status, "queued")
            self.assertEqual(run.spec.sourceEvent["source"], "webhook")
            self.assertEqual(run.spec.sourceEvent["dedupeKey"], "delivery-1")
            self.assertEqual(automation_trigger_event_records(index, automation_id="webhook-reminder")[0]["id"], event.object_id)

    def test_admit_external_github_webhook_verifies_signature_and_redacts_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "github-issue-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "GitHub issue event smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {
                            "provider": "github",
                            "secretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET",
                        },
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "issue": {"number": 7, "title": "Bug"},
                "token": "secret-token",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "test-secret"
            signature = hmac.new(b"test-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()

            try:
                result = admit_external_automation_event(
                    workspace,
                    "github-issue-reminder",
                    provider="github",
                    event_type="issues",
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "delivery-42",
                        "X-Hub-Signature-256": f"sha256={signature}",
                        "Authorization": "Bearer should-not-be-stored",
                    },
                    payload=payload,
                    raw_body=raw_body,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)
            event = result["event"]
            run = result["run"]

            self.assertIsNotNone(event)
            self.assertIsNotNone(run)
            self.assertEqual(event.spec.triggerType, "issue_task_event")
            self.assertEqual(event.spec.source, "git_provider")
            self.assertEqual(event.spec.dedupeKey, "github:issues:delivery-42")
            self.assertTrue(event.spec.payload["signatureVerified"])
            self.assertEqual(event.spec.payload["payload"]["token"], "[REDACTED]")
            self.assertEqual(event.spec.payload["normalized"]["repository"], "example/aiteamos")
            self.assertEqual(event.spec.payload["normalized"]["number"], "7")
            self.assertNotIn("authorization", event.spec.payload["headers"])
            self.assertEqual(run.spec.sourceEvent["dedupeKey"], "github:issues:delivery-42")

    def test_connector_scoped_github_admission_validates_payload_policy_and_replay_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={
                    "allowedRepositories": ["example/aiteamos"],
                    "allowedInstallationIds": ["12345"],
                    "timestampHeader": "X-AITEAMOS-Timestamp",
                    "replayWindowSeconds": 300,
                },
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "github-connector-issue-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Connector-scoped GitHub issue event smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {
                            "provider": "github",
                            "connector": "github-main",
                        },
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "installation": {"id": 12345},
                "issue": {"number": 11, "title": "Connector bug", "html_url": "https://github.example/issues/11"},
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            signature = hmac.new(b"connector-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")

            try:
                result = admit_external_automation_event(
                    workspace,
                    "github-connector-issue-reminder",
                    provider="github",
                    event_type="issues",
                    connector="github-main",
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "connector-delivery-1",
                        "X-Hub-Signature-256": f"sha256={signature}",
                        "X-AITEAMOS-Timestamp": timestamp,
                    },
                    payload=payload,
                    raw_body=raw_body,
                    received_at=timestamp,
                )
                duplicate = admit_external_automation_event(
                    workspace,
                    "github-connector-issue-reminder",
                    provider="github",
                    event_type="issues",
                    connector="github-main",
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "connector-delivery-1",
                        "X-Hub-Signature-256": f"sha256={signature}",
                        "X-AITEAMOS-Timestamp": timestamp,
                    },
                    payload=payload,
                    raw_body=raw_body,
                    received_at=timestamp,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)

            event = result["event"]
            delivery = result["delivery"]
            duplicate_delivery = duplicate["delivery"]
            self.assertIsNotNone(event)
            self.assertIsNotNone(delivery)
            self.assertEqual(event.spec.payload["connector"], "github-main")
            self.assertEqual(event.spec.payload["deliveryReceipt"], delivery.object_id)
            self.assertEqual(event.spec.payload["normalized"]["repository"], "example/aiteamos")
            self.assertEqual(event.spec.payload["normalized"]["installationId"], "12345")
            self.assertEqual(event.spec.payload["normalized"]["number"], "11")
            self.assertEqual(event.spec.payload["headers"]["x-aiteamos-timestamp"], timestamp)
            self.assertEqual(delivery.spec.connector, "github-main")
            self.assertEqual(delivery.spec.admissionStatus, "accepted")
            self.assertEqual(delivery.spec.replayStatus, "accepted")
            self.assertEqual(len(delivery.spec.payloadDigest), 64)
            self.assertEqual(duplicate["event"].object_id, event.object_id)
            self.assertEqual(duplicate["run"].object_id, result["run"].object_id)
            self.assertEqual(duplicate_delivery.spec.admissionStatus, "duplicate")
            self.assertEqual(duplicate_delivery.spec.replayStatus, "duplicate")
            self.assertEqual(duplicate_delivery.spec.attemptCount, 2)
            index = load_workspace(workspace)
            self.assertEqual(len(index.automation_trigger_events), 1)
            self.assertEqual(len(index.automation_provider_deliveries), 1)
            self.assertEqual(automation_provider_delivery_records(index, automation_id="github-connector-issue-reminder")[0]["id"], delivery.object_id)

    def test_provider_delivery_cleanup_archives_old_receipts_without_deleting_replay_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={"allowedRepositories": ["example/aiteamos"], "allowedInstallationIds": ["12345"]},
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "github-retention-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Retention smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "github", "connector": "github-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "installation": {"id": 12345},
                "issue": {"number": 12, "title": "Retention"},
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            signature = hmac.new(b"connector-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            try:
                result = admit_external_automation_event(
                    workspace,
                    "github-retention-reminder",
                    provider="github",
                    event_type="issues",
                    connector="github-main",
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "connector-retention-1",
                        "X-Hub-Signature-256": f"sha256={signature}",
                    },
                    payload=payload,
                    raw_body=raw_body,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)
            delivery = result["delivery"]
            self.assertIsNotNone(delivery)
            _set_delivery_seen_at(workspace, delivery.object_id, "2020-01-01T00:00:00+00:00")

            cleanup = cleanup_automation_provider_deliveries(workspace, actor_member="memory-service", max_age_days=1)

            self.assertEqual(cleanup["archived"], [delivery.object_id])
            index = load_workspace(workspace)
            archived = index.automation_provider_deliveries[delivery.object_id]
            self.assertEqual(archived.spec.lifecycle, "archived")
            self.assertIsNotNone(archived.spec.archivedAt)
            self.assertEqual(archived.spec.decisionAudit[-1].authority, "expire")
            self.assertEqual(automation_provider_delivery_records(index)[0]["spec"]["lifecycle"], "archived")

    def test_api_runs_provider_delivery_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={"allowedRepositories": ["example/aiteamos"]},
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "github-retention-api-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Retention API smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "github", "connector": "github-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "issue": {"number": 14, "title": "Retention API"},
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            signature = hmac.new(b"connector-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            try:
                result = admit_external_automation_event(
                    workspace,
                    "github-retention-api-reminder",
                    provider="github",
                    event_type="issues",
                    connector="github-main",
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "connector-retention-api-1",
                        "X-Hub-Signature-256": f"sha256={signature}",
                    },
                    payload=payload,
                    raw_body=raw_body,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)
            delivery = result["delivery"]
            self.assertIsNotNone(delivery)
            _set_delivery_seen_at(workspace, delivery.object_id, "2020-01-01T00:00:00+00:00")
            client = TestClient(create_app(workspace))

            response = client.post(
                "/automations/provider-deliveries/cleanup",
                json={"actorMember": "memory-service", "maxAgeDays": 1},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["archived"], [delivery.object_id])
            index = load_workspace(workspace)
            self.assertEqual(index.automation_provider_deliveries[delivery.object_id].spec.lifecycle, "archived")
            overview = connector_operations_overview(index, connector="github-main")
            self.assertEqual(overview["summary"]["archivedProviderDeliveries"], 1)
            self.assertEqual(overview["byConnector"][0]["spec"]["archivedProviderDeliveries"], 1)
            member_overview = connector_operations_overview(index, member="memory-service")
            self.assertEqual(member_overview["summary"]["archivedProviderDeliveries"], 1)
            self.assertEqual(member_overview["byConnector"][0]["spec"]["ownerMember"], "memory-service")
            assignment_overview = connector_operations_overview(index, assignment="aiteamos-memory-service")
            self.assertEqual(assignment_overview["filters"]["member"], "memory-service")
            self.assertEqual(assignment_overview["summary"]["archivedProviderDeliveries"], 1)
            overview_response = client.get("/connectors/operations", params={"connector": "github-main", "lifecycle": "archived"})
            self.assertEqual(overview_response.status_code, 200)
            self.assertEqual(overview_response.json()["summary"]["providerDeliveries"], 1)
            self.assertEqual(overview_response.json()["providerDeliveries"][0]["id"], delivery.object_id)
            member_response = client.get("/connectors/operations", params={"member": "memory-service", "assignment": "aiteamos-memory-service"})
            self.assertEqual(member_response.status_code, 200)
            self.assertEqual(member_response.json()["summary"]["archivedProviderDeliveries"], 1)

    def test_connector_health_blocked_status_blocks_external_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={
                    "allowedRepositories": ["example/aiteamos"],
                    "allowedInstallationIds": ["12345"],
                },
                secret_refs={
                    "tokenEnv": "AITEAMOS_TEST_GITHUB_TOKEN",
                    "webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET",
                },
            )
            _write_automation(
                workspace,
                "github-health-blocked-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Health blocked smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "github", "connector": "github-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "installation": {"id": 12345},
                "issue": {"number": 21, "title": "Health blocked"},
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
            signature = hmac.new(b"connector-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            check_connector_health(
                workspace,
                "github-main",
                actor_member="memory-service",
                observed_repositories=["example/aiteamos"],
                observed_installation_ids=["12345"],
            )

            try:
                with self.assertRaises(ValueError) as error:
                    admit_external_automation_event(
                        workspace,
                        "github-health-blocked-reminder",
                        provider="github",
                        event_type="issues",
                        connector="github-main",
                        headers={
                            "X-GitHub-Event": "issues",
                            "X-GitHub-Delivery": "connector-health-blocked-1",
                            "X-Hub-Signature-256": f"sha256={signature}",
                        },
                        payload=payload,
                        raw_body=raw_body,
                    )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)

            self.assertIn("latest health check", str(error.exception))
            index = load_workspace(workspace)
            self.assertEqual(index.automation_trigger_events, {})
            delivery = next(iter(index.automation_provider_deliveries.values()))
            self.assertEqual(delivery.spec.admissionStatus, "blocked")
            self.assertEqual(delivery.spec.normalized["connectorHealth"]["status"], "blocked")
            self.assertIn("latest health check", delivery.spec.blockers[0])

    def test_degraded_connector_health_is_admission_warning_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={
                    "allowedRepositories": ["example/aiteamos"],
                    "allowedInstallationIds": ["12345"],
                },
                secret_refs={
                    "tokenEnv": "AITEAMOS_TEST_GITHUB_TOKEN",
                    "webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET",
                },
            )
            _write_automation(
                workspace,
                "github-health-degraded-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Health degraded smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "github", "connector": "github-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "installation": {"id": 12345},
                "issue": {"number": 22, "title": "Health degraded"},
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            os.environ["AITEAMOS_TEST_GITHUB_TOKEN"] = "token"
            signature = hmac.new(b"connector-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            try:
                health = check_connector_health(
                    workspace,
                    "github-main",
                    actor_member="memory-service",
                    observed_repositories=["example/aiteamos"],
                )
                result = admit_external_automation_event(
                    workspace,
                    "github-health-degraded-reminder",
                    provider="github",
                    event_type="issues",
                    connector="github-main",
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "connector-health-degraded-1",
                        "X-Hub-Signature-256": f"sha256={signature}",
                    },
                    payload=payload,
                    raw_body=raw_body,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)
                os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)

            self.assertEqual(health.spec.status, "degraded")
            event = result["event"]
            delivery = result["delivery"]
            self.assertIsNotNone(event)
            self.assertEqual(delivery.spec.admissionStatus, "accepted")
            self.assertEqual(delivery.spec.normalized["connectorHealth"]["status"], "degraded")
            self.assertIn("latest health check", delivery.spec.warnings[0])
            self.assertEqual(event.spec.payload["connectorHealth"]["latestHealthCheck"], health.object_id)

    def test_connector_scoped_github_admission_rejects_unallowed_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={
                    "allowedRepositories": ["example/aiteamos"],
                    "timestampHeader": "X-AITEAMOS-Timestamp",
                    "replayWindowSeconds": 300,
                },
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "github-unallowed-repo-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Unallowed repository smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "github", "connector": "github-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "evil/repo"},
                "issue": {"number": 12, "title": "Wrong repo"},
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            signature = hmac.new(b"connector-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")

            try:
                with self.assertRaises(ValueError):
                    admit_external_automation_event(
                        workspace,
                        "github-unallowed-repo-reminder",
                        provider="github",
                        event_type="issues",
                        connector="github-main",
                        headers={
                            "X-GitHub-Event": "issues",
                            "X-GitHub-Delivery": "connector-delivery-2",
                            "X-Hub-Signature-256": f"sha256={signature}",
                            "X-AITEAMOS-Timestamp": timestamp,
                        },
                        payload=payload,
                        raw_body=raw_body,
                        received_at=timestamp,
                    )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)
            index = load_workspace(workspace)
            self.assertEqual(index.automation_trigger_events, {})
            self.assertEqual(len(index.automation_provider_deliveries), 1)
            delivery = next(iter(index.automation_provider_deliveries.values()))
            self.assertEqual(delivery.spec.admissionStatus, "blocked")
            self.assertEqual(delivery.spec.replayStatus, "blocked")
            self.assertIn("does not allow repository", delivery.spec.blockers[0])

    def test_provider_delivery_retry_admits_reviewed_redelivery_without_raw_payload_retention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={"allowedRepositories": ["example/aiteamos"], "allowedInstallationIds": ["12345"]},
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "github-retry-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Retry smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "github", "connector": "github-main"},
                    }
                ],
            )
            blocked_payload = {
                "action": "opened",
                "repository": {"full_name": "evil/repo"},
                "installation": {"id": 12345},
                "issue": {"number": 15, "title": "Wrong repo"},
            }
            blocked_raw = json.dumps(blocked_payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            blocked_signature = hmac.new(b"connector-secret", blocked_raw.encode("utf-8"), hashlib.sha256).hexdigest()
            try:
                with self.assertRaises(ValueError):
                    admit_external_automation_event(
                        workspace,
                        "github-retry-reminder",
                        provider="github",
                        event_type="issues",
                        connector="github-main",
                        headers={
                            "X-GitHub-Event": "issues",
                            "X-GitHub-Delivery": "connector-delivery-retry-1",
                            "X-Hub-Signature-256": f"sha256={blocked_signature}",
                        },
                        payload=blocked_payload,
                        raw_body=blocked_raw,
                    )
                blocked_delivery = next(iter(load_workspace(workspace).automation_provider_deliveries.values()))

                retry_payload = {
                    "action": "opened",
                    "repository": {"full_name": "example/aiteamos"},
                    "installation": {"id": 12345},
                    "issue": {"number": 15, "title": "Allowed repo"},
                }
                retry_raw = json.dumps(retry_payload, sort_keys=True, separators=(",", ":"))
                retry_signature = hmac.new(b"connector-secret", retry_raw.encode("utf-8"), hashlib.sha256).hexdigest()
                result = retry_provider_delivery(
                    workspace,
                    blocked_delivery.object_id,
                    actor_member="frontend-human",
                    reason="Reviewed connector evidence and requested provider redelivery.",
                    headers={
                        "X-GitHub-Event": "issues",
                        "X-GitHub-Delivery": "connector-delivery-retry-2",
                        "X-Hub-Signature-256": f"sha256={retry_signature}",
                    },
                    payload=retry_payload,
                    raw_body=retry_raw,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)

            self.assertTrue(result["admitted"])
            source_delivery = result["delivery"]
            retry_delivery = result["retryDelivery"]
            event = result["event"]
            run = result["run"]
            self.assertIsNotNone(retry_delivery)
            self.assertIsNotNone(event)
            self.assertIsNotNone(run)
            self.assertEqual(source_delivery.object_id, blocked_delivery.object_id)
            self.assertEqual(source_delivery.spec.retryStatus, "admitted")
            self.assertEqual(source_delivery.spec.retryDelivery, retry_delivery.object_id)
            self.assertEqual(source_delivery.spec.retryAutomationTriggerEvent, event.object_id)
            self.assertEqual(source_delivery.spec.retryAutomationRun, run.object_id)
            self.assertEqual(source_delivery.spec.retryAttempts[-1]["outcome"], "admitted")
            self.assertEqual(source_delivery.spec.retryAttempts[-1]["actorMember"], "frontend-human")
            self.assertTrue(
                any(
                    item.decision == "retry-admitted"
                    and item.decisionKind == "human_approval"
                    and item.actorMember == "frontend-human"
                    for item in source_delivery.spec.decisionAudit
                )
            )
            self.assertEqual(retry_delivery.spec.admissionStatus, "accepted")
            self.assertEqual(retry_delivery.spec.audit["rawBodyStored"], False)
            self.assertEqual(event.spec.payload["normalized"]["repository"], "example/aiteamos")
            self.assertNotIn("evil/repo", json.dumps(retry_delivery.model_dump(mode="json")))

    def test_gitlab_provider_delivery_retry_uses_provider_headers_and_pr_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "gitlab-main",
                provider="gitlab",
                connector_type="git",
                projects=["aiteamos"],
                config={"allowedRepositories": ["example/aiteamos"]},
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "gitlab-retry-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "GitLab retry smoke test."},
                triggers=[
                    {
                        "triggerType": "pr_event",
                        "config": {"provider": "gitlab", "connector": "gitlab-main"},
                    }
                ],
            )
            blocked_payload = {
                "event_name": "merge_request",
                "project": {"path_with_namespace": "evil/repo"},
                "object_attributes": {
                    "iid": 21,
                    "title": "Wrong repo",
                    "action": "open",
                    "source_branch": "feature/replay",
                    "target_branch": "main",
                    "url": "https://gitlab.example/evil/repo/-/merge_requests/21",
                },
            }
            blocked_raw = json.dumps(blocked_payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            blocked_signature = hmac.new(b"connector-secret", blocked_raw.encode("utf-8"), hashlib.sha256).hexdigest()
            try:
                with self.assertRaises(ValueError):
                    admit_external_automation_event(
                        workspace,
                        "gitlab-retry-reminder",
                        provider="gitlab",
                        event_type="merge_request",
                        connector="gitlab-main",
                        headers={
                            "X-Gitlab-Event": "merge_request",
                            "X-Gitlab-Event-UUID": "gitlab-delivery-retry-1",
                            "X-AITEAMOS-Signature": f"sha256={blocked_signature}",
                        },
                        payload=blocked_payload,
                        raw_body=blocked_raw,
                    )
                blocked_delivery = next(iter(load_workspace(workspace).automation_provider_deliveries.values()))

                retry_payload = {
                    "event_name": "merge_request",
                    "project": {"path_with_namespace": "example/aiteamos"},
                    "object_attributes": {
                        "iid": 21,
                        "title": "Allowed GitLab MR",
                        "action": "open",
                        "source_branch": "feature/replay",
                        "target_branch": "main",
                        "url": "https://gitlab.example/example/aiteamos/-/merge_requests/21",
                    },
                }
                retry_raw = json.dumps(retry_payload, sort_keys=True, separators=(",", ":"))
                retry_signature = hmac.new(b"connector-secret", retry_raw.encode("utf-8"), hashlib.sha256).hexdigest()
                result = retry_provider_delivery(
                    workspace,
                    blocked_delivery.object_id,
                    actor_member="frontend-human",
                    reason="Reviewed GitLab connector evidence and requested provider redelivery.",
                    headers={
                        "X-Gitlab-Event": "merge_request",
                        "X-Gitlab-Event-UUID": "gitlab-delivery-retry-2",
                        "X-AITEAMOS-Signature": f"sha256={retry_signature}",
                    },
                    payload=retry_payload,
                    raw_body=retry_raw,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)

            self.assertTrue(result["admitted"])
            source_delivery = result["delivery"]
            retry_delivery = result["retryDelivery"]
            event = result["event"]
            self.assertIsNotNone(retry_delivery)
            self.assertIsNotNone(event)
            self.assertEqual(source_delivery.spec.retryStatus, "admitted")
            self.assertEqual(source_delivery.spec.retryAttempts[-1]["outcome"], "admitted")
            self.assertEqual(source_delivery.spec.retryAttempts[-1]["payloadDigest"], retry_delivery.spec.payloadDigest)
            self.assertEqual(retry_delivery.spec.provider, "gitlab")
            self.assertEqual(retry_delivery.spec.eventType, "merge_request")
            self.assertEqual(retry_delivery.spec.deliveryId, "gitlab-delivery-retry-2")
            self.assertEqual(retry_delivery.spec.safeHeaders["x-gitlab-event"], "merge_request")
            self.assertEqual(retry_delivery.spec.safeHeaders["x-gitlab-event-uuid"], "gitlab-delivery-retry-2")
            self.assertEqual(event.spec.triggerType, "pr_event")
            self.assertEqual(event.spec.dedupeKey, "gitlab:merge_request:gitlab-delivery-retry-2")
            self.assertEqual(event.spec.payload["normalized"]["repository"], "example/aiteamos")
            self.assertEqual(event.spec.payload["normalized"]["number"], "21")
            self.assertEqual(event.spec.payload["normalized"]["headRef"], "feature/replay")
            self.assertEqual(event.spec.payload["normalized"]["baseRef"], "main")
            self.assertNotIn("evil/repo", json.dumps(retry_delivery.model_dump(mode="json")))

    def test_forgejo_provider_delivery_retry_uses_provider_headers_and_pr_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "forgejo-main",
                provider="forgejo",
                connector_type="git",
                projects=["aiteamos"],
                config={"allowedRepositories": ["example/aiteamos"]},
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "forgejo-retry-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Forgejo retry smoke test."},
                triggers=[
                    {
                        "triggerType": "pr_event",
                        "config": {"provider": "forgejo", "connector": "forgejo-main"},
                    }
                ],
            )
            blocked_payload = {
                "action": "opened",
                "repository": {"full_name": "evil/repo"},
                "pull_request": {
                    "number": 34,
                    "title": "Wrong repo",
                    "head": {"ref": "feature/replay"},
                    "base": {"ref": "main"},
                    "html_url": "https://forgejo.example/evil/repo/pulls/34",
                },
            }
            blocked_raw = json.dumps(blocked_payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            blocked_signature = hmac.new(b"connector-secret", blocked_raw.encode("utf-8"), hashlib.sha256).hexdigest()
            try:
                with self.assertRaises(ValueError):
                    admit_external_automation_event(
                        workspace,
                        "forgejo-retry-reminder",
                        provider="forgejo",
                        event_type="pull_request",
                        connector="forgejo-main",
                        headers={
                            "X-Forgejo-Event": "pull_request",
                            "X-Forgejo-Delivery": "forgejo-delivery-retry-1",
                            "X-Forgejo-Signature": blocked_signature,
                        },
                        payload=blocked_payload,
                        raw_body=blocked_raw,
                    )
                blocked_delivery = next(iter(load_workspace(workspace).automation_provider_deliveries.values()))

                retry_payload = {
                    "action": "opened",
                    "repository": {"full_name": "example/aiteamos"},
                    "pull_request": {
                        "number": 34,
                        "title": "Allowed Forgejo PR",
                        "head": {"ref": "feature/replay"},
                        "base": {"ref": "main"},
                        "html_url": "https://forgejo.example/example/aiteamos/pulls/34",
                    },
                }
                retry_raw = json.dumps(retry_payload, sort_keys=True, separators=(",", ":"))
                retry_signature = hmac.new(b"connector-secret", retry_raw.encode("utf-8"), hashlib.sha256).hexdigest()
                result = retry_provider_delivery(
                    workspace,
                    blocked_delivery.object_id,
                    actor_member="frontend-human",
                    reason="Reviewed Forgejo connector evidence and requested provider redelivery.",
                    headers={
                        "X-Forgejo-Event": "pull_request",
                        "X-Forgejo-Delivery": "forgejo-delivery-retry-2",
                        "X-Forgejo-Signature": retry_signature,
                    },
                    payload=retry_payload,
                    raw_body=retry_raw,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)

            self.assertTrue(result["admitted"])
            source_delivery = result["delivery"]
            retry_delivery = result["retryDelivery"]
            event = result["event"]
            self.assertIsNotNone(retry_delivery)
            self.assertIsNotNone(event)
            self.assertEqual(source_delivery.spec.retryStatus, "admitted")
            self.assertEqual(source_delivery.spec.retryAttempts[-1]["outcome"], "admitted")
            self.assertEqual(source_delivery.spec.retryAttempts[-1]["payloadDigest"], retry_delivery.spec.payloadDigest)
            self.assertEqual(retry_delivery.spec.provider, "forgejo")
            self.assertEqual(retry_delivery.spec.eventType, "pull_request")
            self.assertEqual(retry_delivery.spec.deliveryId, "forgejo-delivery-retry-2")
            self.assertEqual(retry_delivery.spec.safeHeaders["x-forgejo-event"], "pull_request")
            self.assertEqual(retry_delivery.spec.safeHeaders["x-forgejo-delivery"], "forgejo-delivery-retry-2")
            self.assertEqual(event.spec.triggerType, "pr_event")
            self.assertEqual(event.spec.dedupeKey, "forgejo:pull_request:forgejo-delivery-retry-2")
            self.assertEqual(event.spec.payload["normalized"]["repository"], "example/aiteamos")
            self.assertEqual(event.spec.payload["normalized"]["number"], "34")
            self.assertEqual(event.spec.payload["normalized"]["headRef"], "feature/replay")
            self.assertEqual(event.spec.payload["normalized"]["baseRef"], "main")
            self.assertNotIn("evil/repo", json.dumps(retry_delivery.model_dump(mode="json")))

    def test_gitea_provider_admission_uses_provider_headers_and_unprefixed_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "gitea-main",
                provider="gitea",
                connector_type="issue",
                projects=["aiteamos"],
                config={"allowedRepositories": ["example/aiteamos"]},
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "gitea-issue-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Gitea admission smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "gitea", "connector": "gitea-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "issue": {
                    "number": 55,
                    "title": "Route Gitea issue event",
                    "html_url": "https://gitea.example/example/aiteamos/issues/55",
                },
            }
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            signature = hmac.new(b"connector-secret", raw.encode("utf-8"), hashlib.sha256).hexdigest()
            try:
                result = admit_external_automation_event(
                    workspace,
                    "gitea-issue-reminder",
                    provider="gitea",
                    event_type="issues",
                    connector="gitea-main",
                    headers={
                        "X-Gitea-Event": "issues",
                        "X-Gitea-Delivery": "gitea-delivery-55",
                        "X-Gitea-Signature": signature,
                    },
                    payload=payload,
                    raw_body=raw,
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)

            delivery = result["delivery"]
            event = result["event"]
            self.assertIsNotNone(delivery)
            self.assertIsNotNone(event)
            self.assertEqual(delivery.spec.provider, "gitea")
            self.assertEqual(delivery.spec.eventType, "issues")
            self.assertEqual(delivery.spec.deliveryId, "gitea-delivery-55")
            self.assertEqual(delivery.spec.safeHeaders["x-gitea-event"], "issues")
            self.assertEqual(delivery.spec.safeHeaders["x-gitea-delivery"], "gitea-delivery-55")
            self.assertEqual(event.spec.triggerType, "issue_task_event")
            self.assertEqual(event.spec.source, "git_provider")
            self.assertEqual(event.spec.payload["normalized"]["repository"], "example/aiteamos")
            self.assertEqual(event.spec.payload["normalized"]["number"], "55")
            self.assertEqual(event.spec.payload["normalized"]["title"], "Route Gitea issue event")

    def test_gitea_bad_signature_rejects_before_delivery_or_run_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "gitea-main",
                provider="gitea",
                connector_type="issue",
                projects=["aiteamos"],
                config={"allowedRepositories": ["example/aiteamos"]},
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "gitea-issue-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Gitea bad signature smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "gitea", "connector": "gitea-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "issue": {
                    "number": 56,
                    "title": "Reject forged Gitea issue event",
                    "html_url": "https://gitea.example/example/aiteamos/issues/56",
                },
            }
            raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            try:
                with self.assertRaisesRegex(ValueError, "webhook signature verification failed"):
                    admit_external_automation_event(
                        workspace,
                        "gitea-issue-reminder",
                        provider="gitea",
                        event_type="issues",
                        connector="gitea-main",
                        headers={
                            "X-Gitea-Event": "issues",
                            "X-Gitea-Delivery": "gitea-delivery-bad-signature",
                            "X-Gitea-Signature": "bad-signature",
                        },
                        payload=payload,
                        raw_body=raw,
                    )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)

            index = load_workspace(workspace)
            self.assertEqual(index.automation_provider_deliveries, {})
            self.assertEqual(index.automation_trigger_events, {})

    def test_api_requests_provider_delivery_retry_without_replaying_raw_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={"allowedRepositories": ["example/aiteamos"]},
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "github-api-retry-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "API retry smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "github", "connector": "github-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "evil/repo"},
                "issue": {"number": 16, "title": "Wrong repo"},
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            signature = hmac.new(b"connector-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            try:
                with self.assertRaises(ValueError):
                    admit_external_automation_event(
                        workspace,
                        "github-api-retry-reminder",
                        provider="github",
                        event_type="issues",
                        connector="github-main",
                        headers={
                            "X-GitHub-Event": "issues",
                            "X-GitHub-Delivery": "connector-api-retry-1",
                            "X-Hub-Signature-256": f"sha256={signature}",
                        },
                        payload=payload,
                        raw_body=raw_body,
                    )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)
            delivery = next(iter(load_workspace(workspace).automation_provider_deliveries.values()))
            client = TestClient(create_app(workspace))

            response = client.post(
                f"/automations/provider-deliveries/{delivery.object_id}/retry",
                json={
                    "actorMember": "frontend-human",
                    "reason": "Ask provider owner to redeliver after policy review.",
                },
            )

            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertTrue(body["requested"])
            self.assertFalse(body["admitted"])
            self.assertIsNone(body["event"])
            self.assertIsNone(body["retryDelivery"])
            self.assertEqual(body["delivery"]["spec"]["retryStatus"], "requested")
            self.assertEqual(body["delivery"]["spec"]["retryRequestedByMember"], "frontend-human")
            self.assertEqual(body["delivery"]["spec"]["retryAttempts"][-1]["outcome"], "requested")

    def test_connector_scoped_github_admission_rejects_stale_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-main",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={
                    "allowedRepositories": ["example/aiteamos"],
                    "timestampHeader": "X-AITEAMOS-Timestamp",
                    "replayWindowSeconds": 60,
                },
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "github-stale-delivery-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Stale delivery smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {"provider": "github", "connector": "github-main"},
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "issue": {"number": 13, "title": "Stale delivery"},
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "connector-secret"
            signature = hmac.new(b"connector-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            event_time = (datetime.now().astimezone() - timedelta(minutes=10)).isoformat(timespec="milliseconds")
            received_at = datetime.now().astimezone().isoformat(timespec="milliseconds")

            try:
                with self.assertRaises(ValueError):
                    admit_external_automation_event(
                        workspace,
                        "github-stale-delivery-reminder",
                        provider="github",
                        event_type="issues",
                        connector="github-main",
                        headers={
                            "X-GitHub-Event": "issues",
                            "X-GitHub-Delivery": "connector-delivery-3",
                            "X-Hub-Signature-256": f"sha256={signature}",
                            "X-AITEAMOS-Timestamp": event_time,
                        },
                        payload=payload,
                        raw_body=raw_body,
                        received_at=received_at,
                    )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)
            index = load_workspace(workspace)
            self.assertEqual(index.automation_trigger_events, {})
            self.assertEqual(len(index.automation_provider_deliveries), 1)
            delivery = next(iter(index.automation_provider_deliveries.values()))
            self.assertEqual(delivery.spec.admissionStatus, "blocked")
            self.assertEqual(delivery.spec.replayStatus, "stale")
            reminders = connector_failure_reminder_candidates(workspace, connector="github-main")
            self.assertEqual(reminders["summary"]["candidates"], 1)
            reminder = reminders["candidates"][0]
            self.assertEqual(reminder["spec"]["evidenceKind"], "AutomationProviderDelivery")
            self.assertEqual(reminder["spec"]["evidenceId"], delivery.object_id)
            self.assertEqual(reminder["spec"]["toMembers"], ["memory-service", "manager"])

    def test_admit_external_webhook_rejects_bad_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "bad-signature-webhook",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Bad signature smoke test."},
                triggers=[
                    {
                        "triggerType": "webhook",
                        "config": {
                            "provider": "github",
                            "secretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET",
                        },
                    }
                ],
            )
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "test-secret"

            try:
                with self.assertRaises(ValueError):
                    admit_external_automation_event(
                        workspace,
                        "bad-signature-webhook",
                        provider="github",
                        event_type="issues",
                        headers={
                            "X-GitHub-Event": "issues",
                            "X-GitHub-Delivery": "delivery-bad",
                            "X-Hub-Signature-256": "sha256=bad",
                        },
                        payload={"action": "opened"},
                    )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)
            self.assertEqual(load_workspace(workspace).automation_trigger_events, {})

    def test_scheduler_tick_writes_lease_event_and_run_with_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "cron-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Cron event smoke test."},
                triggers=[{"triggerType": "cron", "config": {"cron": "*/5 * * * *"}}],
            )

            result = emit_scheduler_tick(
                workspace,
                "cron-reminder",
                scheduler_id="scheduler-a",
                tick_key="2026-05-21T10:00Z",
                lease_seconds=120,
            )
            duplicate = emit_scheduler_tick(
                workspace,
                "cron-reminder",
                scheduler_id="scheduler-b",
                tick_key="2026-05-21T10:00Z",
                lease_seconds=120,
            )
            lease = result["lease"]
            event = result["event"]
            run = result["run"]
            index = load_workspace(workspace)

            self.assertIsNotNone(lease)
            self.assertIsNotNone(event)
            self.assertIsNotNone(run)
            self.assertTrue(result["acquired"])
            self.assertFalse(duplicate["acquired"])
            self.assertEqual(lease.object_id, duplicate["lease"].object_id)
            self.assertEqual(event.object_id, duplicate["event"].object_id)
            self.assertEqual(run.object_id, duplicate["run"].object_id)
            self.assertEqual(lease.spec.status, "emitted")
            self.assertEqual(lease.spec.automationTriggerEvent, event.object_id)
            self.assertEqual(lease.spec.automationRun, run.object_id)
            self.assertEqual(event.spec.source, "scheduler")
            self.assertEqual(event.spec.triggerType, "cron")
            self.assertEqual(run.spec.sourceEvent["dedupeKey"], "scheduler:cron-reminder:2026-05-21T10:00Z")
            self.assertEqual(len(index.automation_scheduler_leases), 1)
            self.assertEqual(automation_scheduler_lease_records(index, automation_id="cron-reminder")[0]["id"], lease.object_id)

    def test_scheduler_lease_recovery_reemits_blocked_tick_with_review_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "cron-recovery",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Cron recovery smoke test."},
                triggers=[{"triggerType": "cron", "config": {"cron": "*/5 * * * *"}}],
            )
            lease_id = _write_scheduler_lease(
                workspace,
                automation_id="cron-recovery",
                scheduler_id="scheduler-a",
                tick_key="2026-05-21T10:15Z",
                status="blocked",
                lease_expires_at="2099-01-01T00:00:00+00:00",
            )

            duplicate = emit_scheduler_tick(
                workspace,
                "cron-recovery",
                scheduler_id="scheduler-b",
                tick_key="2026-05-21T10:15Z",
                lease_seconds=120,
            )
            result = recover_scheduler_lease(
                workspace,
                lease_id,
                actor_member="frontend-human",
                lease_seconds=120,
                reason="Reviewed blocked scheduler lease and re-emitted the tick.",
            )

            self.assertFalse(duplicate["acquired"])
            self.assertTrue(result["acquired"])
            lease = result["lease"]
            event = result["event"]
            run = result["run"]
            self.assertIsNotNone(lease)
            self.assertIsNotNone(event)
            self.assertIsNotNone(run)
            self.assertEqual(lease.object_id, lease_id)
            self.assertEqual(lease.spec.status, "emitted")
            self.assertEqual(lease.spec.automationTriggerEvent, event.object_id)
            self.assertEqual(lease.spec.automationRun, run.object_id)
            self.assertEqual(event.spec.actorMember, "frontend-human")
            self.assertEqual(event.spec.payload["recoveredLease"], lease_id)
            decisions = [item.decision for item in lease.spec.decisionAudit]
            self.assertIn("recovered", decisions)
            self.assertTrue(
                any(
                    item.decision == "recovered"
                    and item.decisionKind == "human_approval"
                    and item.actorMember == "frontend-human"
                    for item in lease.spec.decisionAudit
                )
            )

    def test_api_recovers_scheduler_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "api-cron-recovery",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "API cron recovery smoke test."},
                triggers=[{"triggerType": "cron", "config": {"cron": "*/5 * * * *"}}],
            )
            lease_id = _write_scheduler_lease(
                workspace,
                automation_id="api-cron-recovery",
                scheduler_id="scheduler-api",
                tick_key="2026-05-21T10:20Z",
                status="blocked",
                lease_expires_at="2099-01-01T00:00:00+00:00",
            )
            client = TestClient(create_app(workspace))

            response = client.post(
                f"/automations/scheduler/leases/{lease_id}/recover",
                json={
                    "actorMember": "frontend-human",
                    "reason": "Recover the blocked API scheduler lease.",
                    "leaseSeconds": 90,
                },
            )

            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertTrue(body["acquired"])
            self.assertEqual(body["lease"]["id"], lease_id)
            self.assertEqual(body["lease"]["spec"]["status"], "emitted")
            self.assertEqual(body["event"]["spec"]["actorMember"], "frontend-human")
            self.assertEqual(body["event"]["spec"]["payload"]["recoveredLease"], lease_id)
            leases = client.get("/automations/scheduler/leases").json()
            self.assertEqual(leases[0]["spec"]["status"], "emitted")

    def test_api_ingests_automation_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "api-webhook-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "API webhook event smoke test."},
                triggers=[{"triggerType": "webhook"}],
            )
            client = TestClient(create_app(workspace))

            response = client.post(
                "/automations/api-webhook-reminder/events",
                json={
                    "triggerType": "webhook",
                    "source": "webhook",
                    "payload": {"deliveryId": "api-delivery-1"},
                    "dedupeKey": "api-delivery-1",
                },
            )

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["event"]["kind"], "AutomationTriggerEvent")
            self.assertEqual(body["event"]["spec"]["automationRun"], body["run"]["id"])
            self.assertEqual(body["run"]["spec"]["status"], "queued")
            events = client.get("/automations/events").json()
            self.assertEqual([item["id"] for item in events], [body["event"]["id"]])

    def test_api_admits_signed_webhook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_connector(
                workspace,
                "github-api",
                provider="github",
                connector_type="issue",
                projects=["aiteamos"],
                config={
                    "allowedRepositories": ["example/aiteamos"],
                    "timestampHeader": "X-AITEAMOS-Timestamp",
                    "replayWindowSeconds": 300,
                },
                secret_refs={"webhookSecretEnv": "AITEAMOS_TEST_WEBHOOK_SECRET"},
            )
            _write_automation(
                workspace,
                "api-github-issue-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "API GitHub issue event smoke test."},
                triggers=[
                    {
                        "triggerType": "issue_task_event",
                        "config": {
                            "provider": "github",
                            "connector": "github-api",
                        },
                    }
                ],
            )
            payload = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "issue": {"number": 9, "title": "API bug"},
                "secret": "secret-value",
            }
            raw_body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
            os.environ["AITEAMOS_TEST_WEBHOOK_SECRET"] = "api-secret"
            signature = hmac.new(b"api-secret", raw_body.encode("utf-8"), hashlib.sha256).hexdigest()
            timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
            client = TestClient(create_app(workspace))

            try:
                response = client.post(
                    "/automations/api-github-issue-reminder/admit-webhook",
                    json={
                        "provider": "github",
                        "connector": "github-api",
                        "eventType": "issues",
                        "headers": {
                            "X-GitHub-Event": "issues",
                            "X-GitHub-Delivery": "api-delivery-42",
                            "X-Hub-Signature-256": f"sha256={signature}",
                            "X-AITEAMOS-Timestamp": timestamp,
                        },
                        "payload": payload,
                        "rawBody": raw_body,
                        "receivedAt": timestamp,
                    },
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_WEBHOOK_SECRET", None)

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["event"]["spec"]["source"], "git_provider")
            self.assertEqual(body["event"]["spec"]["triggerType"], "issue_task_event")
            self.assertEqual(body["event"]["spec"]["payload"]["connector"], "github-api")
            self.assertEqual(body["delivery"]["kind"], "AutomationProviderDelivery")
            self.assertEqual(body["delivery"]["spec"]["connector"], "github-api")
            self.assertEqual(body["delivery"]["spec"]["automationTriggerEvent"], body["event"]["id"])
            self.assertEqual(body["event"]["spec"]["payload"]["normalized"]["repository"], "example/aiteamos")
            self.assertEqual(body["event"]["spec"]["payload"]["payload"]["secret"], "[REDACTED]")
            self.assertEqual(body["run"]["spec"]["status"], "queued")

    def test_api_scans_cron_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "api-cron-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "API cron event smoke test."},
                triggers=[{"triggerType": "cron", "config": {"cron": "*/5 * * * *"}}],
            )
            client = TestClient(create_app(workspace))

            response = client.post(
                "/automations/scheduler/scan",
                json={"schedulerId": "scheduler-api", "tickKey": "2026-05-21T10:05Z"},
            )

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(len(body), 1)
            self.assertEqual(body[0]["lease"]["kind"], "AutomationSchedulerLease")
            self.assertEqual(body[0]["lease"]["spec"]["status"], "emitted")
            self.assertEqual(body[0]["event"]["kind"], "AutomationTriggerEvent")
            self.assertEqual(body[0]["run"]["spec"]["status"], "queued")
            leases = client.get("/automations/scheduler/leases").json()
            self.assertEqual([item["id"] for item in leases], [body[0]["lease"]["id"]])

    def test_derived_index_persists_automation_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = _copy_workspace(temp_root)
            _write_executor_policy(workspace)
            _write_automation(
                workspace,
                "remind-frontend",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Index executor smoke test."},
            )
            queued = trigger_automation(workspace, "remind-frontend", actor_member="manager")
            run = execute_automation_run(workspace, queued.object_id, actor_member="memory-service")
            _write_automation(
                workspace,
                "indexed-approval-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Indexed approval smoke test."},
                approval_gates=["human-approval"],
            )
            pending = trigger_automation(workspace, "indexed-approval-reminder", actor_member="manager")
            approved = approve_automation_run(workspace, pending.object_id, reviewer_member="frontend-human")
            approval_id = approved.spec.approvals[0]
            _write_automation(
                workspace,
                "indexed-webhook-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Indexed event smoke test."},
                triggers=[{"triggerType": "webhook"}],
            )
            event_result = ingest_automation_event(
                workspace,
                "indexed-webhook-reminder",
                trigger_type="webhook",
                source="webhook",
                payload={"deliveryId": "indexed-delivery-1"},
                dedupe_key="indexed-delivery-1",
            )
            event_id = event_result["event"].object_id
            _write_automation(
                workspace,
                "indexed-cron-reminder",
                "human_reminder",
                {"toMembers": ["frontend-human"], "body": "Indexed cron event smoke test."},
                triggers=[{"triggerType": "cron", "config": {"cron": "*/5 * * * *"}}],
            )
            scheduler_result = scan_cron_scheduler(
                workspace,
                scheduler_id="index-scheduler",
                tick_key="2026-05-21T10:10Z",
            )
            lease_id = scheduler_result[0]["lease"].object_id
            db_path = temp_root / "aiteamos.sqlite"

            index_workspace(workspace, db_path=db_path)

            conn = sqlite3.connect(db_path)
            try:
                row = conn.execute(
                    "select automation_id, service_member_id, status, dry_run, approvals_json, created_message_id from automation_runs where id = ?",
                    (run.object_id,),
                ).fetchone()
                approval_row = conn.execute(
                    """
                    select automation_run_id, automation_id, reviewer_member_id, reviewer_member_kind, decision
                    from automation_approvals
                    where id = ?
                    """,
                    (approval_id,),
                ).fetchone()
                event_row = conn.execute(
                    """
                    select automation_id, trigger_type, source, dedupe_key, status, automation_run_id
                    from automation_trigger_events
                    where id = ?
                    """,
                    (event_id,),
                ).fetchone()
                lease_row = conn.execute(
                    """
                    select automation_id, scheduler_id, tick_key, status, automation_trigger_event_id, automation_run_id
                    from automation_scheduler_leases
                    where id = ?
                    """,
                    (lease_id,),
                ).fetchone()
                audit_row = conn.execute(
                    """
                    select resource_kind, resource_id, decision_kind, decision, actor_member_id, actor_member_kind, authority, risk_level
                    from decision_audit
                    where resource_id = ?
                    """,
                    (run.object_id,),
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("remind-frontend", "memory-service", "succeeded", 0, "[]", run.spec.createdMessage))
            self.assertEqual(approval_row, (pending.object_id, "indexed-approval-reminder", "frontend-human", "human", "approved"))
            self.assertEqual(
                event_row,
                ("indexed-webhook-reminder", "webhook", "webhook", "indexed-delivery-1", "accepted", event_result["run"].object_id),
            )
            self.assertEqual(
                lease_row,
                (
                    "indexed-cron-reminder",
                    "index-scheduler",
                    "2026-05-21T10:10Z",
                    "emitted",
                    scheduler_result[0]["event"].object_id,
                    scheduler_result[0]["run"].object_id,
                ),
            )
            self.assertEqual(
                audit_row,
                ("AutomationRun", run.object_id, "service_policy_decision", "allow", "memory-service", "service", "enforce", "low"),
            )


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _write_executor_policy(workspace: Path) -> None:
    write_yaml(
        workspace / "permissions" / "service-automation-executor-test.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "PermissionPolicy",
            "metadata": {"name": "service-automation-executor-test"},
            "spec": {
                "scope": {"memberKind": "service", "member": "memory-service"},
                "defaultMode": "deny",
                "allow": [
                    {"match": "Automation(human_reminder:*)"},
                    {"match": "Automation(connector_failure_reminder:*)"},
                    {"match": "Automation(task_planning:*)"},
                    {"match": "Automation(digital_execution:*)"},
                    {"match": "Automation(hybrid_assist:*)"},
                    {"match": "Automation(git_activity_correlation_promotion:*)"},
                    {"match": "Automation(git_activity_retention_sweep:*)"},
                    {"match": "Automation(artifact_retention_sweep:*)"},
                    {"match": "Edit(/.aiteamos/im/messages/**)"},
                    {"match": "Edit(/.aiteamos/task_plans/**)"},
                    {"match": "Edit(/.aiteamos/tasks/**)"},
                    {"match": "Edit(/.aiteamos/runs/**)"},
                    {"match": "Edit(/.aiteamos/git_activity/correlations/*)"},
                    {"match": "Edit(/.aiteamos/git_activity/imports/*)"},
                    {"match": "Edit(/.aiteamos/git_activity/GIT-*.yaml)"},
                    {"match": "Edit(/.aiteamos/artifacts/manifests/**)"},
                    {"match": "Edit(/.aiteamos/artifacts/manifests/ART-*.yaml)"},
                ],
            },
        },
    )


def _write_retention_executor_policy_without_git_activity_edit(workspace: Path) -> None:
    write_yaml(
        workspace / "permissions" / "service-automation-executor-test.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "PermissionPolicy",
            "metadata": {"name": "service-automation-executor-test"},
            "spec": {
                "scope": {"memberKind": "service", "member": "memory-service"},
                "defaultMode": "deny",
                "allow": [
                    {"match": "Automation(git_activity_retention_sweep:*)"},
                ],
            },
        },
    )


def _write_artifact_manifest(
    workspace: Path,
    *,
    created_at: str,
    export_policy: str,
    sensitivity: str = "workspace-artifact",
) -> str:
    artifact_id = "ART-20260501T000000000-TEST-LOG"
    write_yaml(
        workspace / "artifacts" / "manifests" / f"{artifact_id}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Artifact",
            "metadata": {"id": artifact_id, "createdAt": created_at},
            "spec": {
                "kind": "test_log",
                "uri": "artifacts/logs/test.log",
                "sha256": "0" * 64,
                "sizeBytes": 12,
                "retention": "default",
                "sensitivity": sensitivity,
                "exportPolicy": export_policy,
                "redaction": {},
            },
        },
    )
    return artifact_id


def _write_automation(
    workspace: Path,
    name: str,
    target_type: str,
    target: dict[str, object],
    *,
    approval_gates: list[str] | None = None,
    triggers: list[dict[str, object]] | None = None,
) -> None:
    write_yaml(
        workspace / "automations" / f"{name}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Automation",
            "metadata": {"name": name},
            "spec": {
                "ownerMember": "manager",
                "serviceMember": "memory-service",
                "project": "aiteamos",
                "targetType": target_type,
                "target": target,
                "triggers": triggers or [{"triggerType": "manual"}],
                "dryRun": False,
                "status": "active",
                "permissionPolicies": ["service-automation-executor-test"],
                "approvalGates": approval_gates or [],
            },
        },
    )


def _write_scheduler_lease(
    workspace: Path,
    *,
    automation_id: str,
    scheduler_id: str,
    tick_key: str,
    status: str,
    lease_expires_at: str,
) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{automation_id}-{tick_key}").strip("-")
    lease_id = f"ASLEASE-{safe[:180]}"
    write_yaml(
        workspace / "automations" / "leases" / f"{lease_id}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "AutomationSchedulerLease",
            "metadata": {"id": lease_id, "createdAt": "2026-05-21T10:00:00+00:00"},
            "spec": {
                "automation": automation_id,
                "project": "aiteamos",
                "schedulerId": scheduler_id,
                "tickKey": tick_key,
                "cron": "*/5 * * * *",
                "dueAt": "2026-05-21T10:00:00+00:00",
                "leaseAcquiredAt": "2026-05-21T10:00:00+00:00",
                "leaseExpiresAt": lease_expires_at,
                "heartbeatAt": "2026-05-21T10:00:00+00:00",
                "status": status,
                "dedupeKey": f"scheduler:{automation_id}:{tick_key}",
                "summary": f"Scheduler lease fixture is {status}.",
                "blockers": ["fixture scheduler lease blocker"] if status == "blocked" else [],
                "decisionAudit": [
                    {
                        "decisionKind": "system_check",
                        "decision": status,
                        "actorMember": "memory-service",
                        "actorMemberKind": "service",
                        "authority": "record",
                        "decidedAt": "2026-05-21T10:00:00+00:00",
                        "reason": "Fixture scheduler lease state.",
                        "source": "test-fixture",
                    }
                ],
                "audit": {"payload": {"fixture": "blocked-scheduler-lease"}},
            },
        },
    )
    return lease_id


def _patch_git_activity(workspace: Path, activity_id: str, **spec_updates: object) -> None:
    path = workspace / "git_activity" / f"{activity_id}.yaml"
    payload = read_yaml(path)
    payload.setdefault("spec", {}).update(spec_updates)
    write_yaml(path, payload)


def _write_connector(
    workspace: Path,
    name: str,
    *,
    provider: str,
    connector_type: str,
    projects: list[str] | None = None,
    config: dict[str, object] | None = None,
    secret_refs: dict[str, str] | None = None,
) -> None:
    (workspace / "connectors").mkdir(parents=True, exist_ok=True)
    write_yaml(
        workspace / "connectors" / f"{name}.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Connector",
            "metadata": {"name": name},
            "spec": {
                "provider": provider,
                "connectorType": connector_type,
                "ownerMember": "memory-service",
                "projects": projects or [],
                "config": config or {},
                "secretRefs": secret_refs or {},
                "permissionPolicies": ["service-automation-executor-test"],
            },
        },
    )


def _preview_group_for_receipts(preview: dict[str, object], *receipt_ids: str) -> dict[str, object]:
    receipt_set = set(receipt_ids)
    groups = preview.get("groups") if isinstance(preview, dict) else []
    for group in groups if isinstance(groups, list) else []:
        if isinstance(group, dict) and receipt_set.issubset(set(group.get("receipts") or [])):
            return group
    raise AssertionError(f"no preview group contains receipts {sorted(receipt_set)}")


def _set_delivery_seen_at(workspace: Path, delivery_id: str, observed_at: str) -> None:
    path = workspace / "automations" / "provider_deliveries" / f"{delivery_id}.yaml"
    data = read_yaml(path)
    data.setdefault("metadata", {})["createdAt"] = observed_at
    spec = data.setdefault("spec", {})
    spec["firstSeenAt"] = observed_at
    spec["lastSeenAt"] = observed_at
    spec["receivedAt"] = observed_at
    write_yaml(path, data)


if __name__ == "__main__":
    unittest.main()
