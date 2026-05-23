from __future__ import annotations

from pathlib import Path
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace.knowledge_health import evaluate_knowledge_health
from aiteamos_workspace import (
    approve_permission_request,
    check_connector_health,
    connector_failure_escalation_candidates,
    cleanup_connector_health_checks,
    connector_failure_reminder_candidates,
    connector_health_records,
    connector_remediation_materialized_task_records,
    connector_remediation_run_records,
    connector_remediation_suggestions,
    connector_remediation_task_plan_records,
    index_workspace,
    launch_connector_remediation_task_run,
    load_workspace,
    request_connector_remediation_run_permission,
    reject_permission_request,
    resolve_connector_failure_escalation,
    route_connector_failure_escalations,
    route_connector_failure_reminders,
    update_run,
)
from aiteamos_workspace.indexer import default_db_path
from aiteamos_workspace.io import read_yaml, write_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class ConnectorHealthTest(unittest.TestCase):
    def test_missing_secret_blocks_connector_readiness_without_storing_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
            os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)

            check = check_connector_health(
                workspace,
                "github-health",
                actor_member="memory-service",
                observed_repositories=["example/aiteamos"],
                observed_installation_ids=["12345"],
            )

            self.assertEqual(check.kind, "ConnectorHealthCheck")
            self.assertEqual(check.spec.status, "blocked")
            self.assertEqual(check.spec.readiness, "blocked")
            self.assertEqual(check.spec.tokenStatus, "missing")
            self.assertEqual(check.spec.installationStatus, "authorized")
            self.assertIn("tokenEnv", check.spec.missingSecrets)
            self.assertFalse(check.spec.audit["secretsStored"])
            self.assertFalse(check.spec.audit["secretValuesObserved"])
            self.assertEqual(check.spec.decisionAudit[0].decisionKind, "system_check")
            self.assertEqual(check.spec.decisionAudit[0].actorMemberKind, "service")
            self.assertNotIn("github-secret", str(check.model_dump(mode="json")))

    def test_authorized_connector_health_check_is_manifest_backed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ["AITEAMOS_TEST_GITHUB_TOKEN"] = "github-token"
            os.environ["AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET"] = "github-secret"
            try:
                check = check_connector_health(
                    workspace,
                    "github-health",
                    actor_member="memory-service",
                    observed_repositories=["example/aiteamos"],
                    observed_installation_ids=["12345"],
                    provider_diagnostics={"status": "ok", "authorization": "secret-value"},
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
                os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)

            self.assertEqual(check.spec.status, "healthy")
            self.assertEqual(check.spec.readiness, "ready")
            self.assertEqual(check.spec.tokenStatus, "present")
            self.assertEqual(check.spec.installationStatus, "authorized")
            self.assertEqual(check.spec.providerDiagnostics["authorization"], "[REDACTED]")
            index = load_workspace(workspace)
            self.assertIn(check.object_id, index.connector_health_checks)
            self.assertEqual(connector_health_records(index, connector="github-health")[0]["id"], check.object_id)

    def test_hosted_provider_probe_records_scope_calibration_and_redacts_nested_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ["AITEAMOS_TEST_GITHUB_TOKEN"] = "github-token"
            os.environ["AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET"] = "github-secret"
            try:
                check = check_connector_health(
                    workspace,
                    "github-health",
                    actor_member="memory-service",
                    observed_repositories=["example/aiteamos"],
                    observed_installation_ids=["12345"],
                    provider_network_called=True,
                    required_provider_scopes=["repo", "pull_requests:write"],
                    observed_provider_scopes=["repo"],
                    provider_diagnostics={
                        "status": "ok",
                        "authStatus": "ok",
                        "apiReachable": True,
                        "rateLimitRemaining": 5,
                        "response": {
                            "headers": {"Authorization": "Bearer github-token"},
                            "body": {"api_key": "secret-nested-key", "safe": "retained"},
                        },
                    },
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
                os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)

            self.assertEqual(check.spec.status, "blocked")
            self.assertEqual(check.spec.providerProbeStatus, "failed")
            self.assertTrue(check.spec.providerNetworkCalled)
            self.assertEqual(check.spec.requiredProviderScopes, ["repo", "pull_requests:write"])
            self.assertEqual(check.spec.observedProviderScopes, ["repo"])
            self.assertEqual(check.spec.missingProviderScopes, ["pull_requests:write"])
            self.assertIn("missing required scopes", "; ".join(check.spec.blockers))
            diagnostics = check.spec.providerDiagnostics
            self.assertEqual(diagnostics["response"]["headers"]["Authorization"], "[REDACTED]")
            self.assertEqual(diagnostics["response"]["body"]["api_key"], "[REDACTED]")
            self.assertEqual(diagnostics["response"]["body"]["safe"], "retained")
            self.assertTrue(check.spec.audit["providerNetworkCalled"])
            self.assertEqual(check.spec.audit["source"], "hosted-provider-calibration")
            self.assertNotIn("github-token", str(check.model_dump(mode="json")))
            self.assertNotIn("secret-nested-key", str(check.model_dump(mode="json")))

    def test_api_accepts_hosted_provider_probe_scope_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ["AITEAMOS_TEST_GITHUB_TOKEN"] = "github-token"
            os.environ["AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET"] = "github-secret"
            client = TestClient(create_app(workspace))
            try:
                response = client.post(
                    "/connectors/github-health/health/check",
                    json={
                        "actorMember": "memory-service",
                        "observedRepositories": ["example/aiteamos"],
                        "observedInstallationIds": ["12345"],
                        "providerNetworkCalled": True,
                        "requiredProviderScopes": ["repo"],
                        "observedProviderScopes": ["repo"],
                        "providerDiagnostics": {
                            "status": "ok",
                            "authStatus": "ok",
                            "apiReachable": True,
                            "authorization": "Bearer github-token",
                        },
                    },
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
                os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)

            self.assertEqual(response.status_code, 200)
            created = response.json()
            self.assertEqual(created["spec"]["status"], "healthy")
            self.assertEqual(created["spec"]["providerProbeStatus"], "passed")
            self.assertTrue(created["spec"]["providerNetworkCalled"])
            self.assertEqual(created["spec"]["missingProviderScopes"], [])
            self.assertEqual(created["spec"]["providerDiagnostics"]["authorization"], "[REDACTED]")

    def test_api_and_derived_index_project_connector_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ["AITEAMOS_TEST_GITHUB_TOKEN"] = "github-token"
            os.environ["AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET"] = "github-secret"
            client = TestClient(create_app(workspace))
            try:
                response = client.post(
                    "/connectors/github-health/health/check",
                    json={
                        "actorMember": "memory-service",
                        "observedRepositories": ["example/aiteamos"],
                        "observedInstallationIds": ["12345"],
                    },
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
                os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)

            self.assertEqual(response.status_code, 200)
            created = response.json()
            self.assertEqual(created["kind"], "ConnectorHealthCheck")
            self.assertEqual(created["spec"]["status"], "healthy")
            listed = client.get("/connectors/github-health/health").json()
            self.assertEqual([item["id"] for item in listed], [created["id"]])

            index_workspace(workspace)
            conn = sqlite3.connect(default_db_path(workspace))
            try:
                row = conn.execute(
                    "select connector_id, status, readiness, token_status, installation_status from connector_health_checks where id = ?",
                    (created["id"],),
                ).fetchone()
            finally:
                conn.close()
            self.assertEqual(row, ("github-health", "healthy", "ready", "present", "authorized"))

    def test_connector_health_cleanup_archives_old_non_latest_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ["AITEAMOS_TEST_GITHUB_TOKEN"] = "github-token"
            os.environ["AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET"] = "github-secret"
            try:
                old_check = check_connector_health(
                    workspace,
                    "github-health",
                    actor_member="memory-service",
                    observed_repositories=["example/aiteamos"],
                    observed_installation_ids=["12345"],
                )
                _set_health_checked_at(workspace, old_check.object_id, "2020-01-01T00:00:00+00:00")
                latest_check = check_connector_health(
                    workspace,
                    "github-health",
                    actor_member="memory-service",
                    observed_repositories=["example/aiteamos"],
                    observed_installation_ids=["12345"],
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
                os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)

            result = cleanup_connector_health_checks(workspace, actor_member="memory-service", max_age_days=1)

            self.assertEqual(result["archived"], [old_check.object_id])
            index = load_workspace(workspace)
            self.assertEqual(index.connector_health_checks[old_check.object_id].spec.lifecycle, "archived")
            self.assertIsNotNone(index.connector_health_checks[old_check.object_id].spec.archivedAt)
            self.assertEqual(index.connector_health_checks[latest_check.object_id].spec.lifecycle, "active")
            self.assertEqual(index.connector_health_checks[old_check.object_id].spec.decisionAudit[-1].authority, "expire")

    def test_api_runs_connector_health_cleanup_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ["AITEAMOS_TEST_GITHUB_TOKEN"] = "github-token"
            os.environ["AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET"] = "github-secret"
            try:
                old_check = check_connector_health(
                    workspace,
                    "github-health",
                    actor_member="memory-service",
                    observed_repositories=["example/aiteamos"],
                    observed_installation_ids=["12345"],
                )
            finally:
                os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
                os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)
            _set_health_checked_at(workspace, old_check.object_id, "2020-01-01T00:00:00+00:00")
            client = TestClient(create_app(workspace))

            response = client.post(
                "/connectors/health/cleanup",
                json={"actorMember": "memory-service", "maxAgeDays": 1, "keepLatestPerConnector": False, "dryRun": True},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["archived"], [old_check.object_id])
            self.assertEqual(load_workspace(workspace).connector_health_checks[old_check.object_id].spec.lifecycle, "active")

    def test_connector_failure_reminders_are_candidate_backed_and_deduped_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
            os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)
            check = check_connector_health(
                workspace,
                "github-health",
                actor_member="memory-service",
                observed_repositories=["example/aiteamos"],
                observed_installation_ids=["12345"],
            )

            candidates = connector_failure_reminder_candidates(workspace, connector="github-health")

            self.assertEqual(candidates["summary"]["candidates"], 1)
            self.assertEqual(candidates["summary"]["blocked"], 1)
            self.assertEqual(candidates["summary"]["routable"], 1)
            candidate = candidates["candidates"][0]
            self.assertEqual(candidate["spec"]["evidenceKind"], "ConnectorHealthCheck")
            self.assertEqual(candidate["spec"]["evidenceId"], check.object_id)
            self.assertEqual(candidate["spec"]["toMembers"], ["memory-service"])

            dry_run = route_connector_failure_reminders(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=True,
            )
            self.assertEqual(dry_run["summary"]["createdMessages"], 0)
            self.assertEqual(
                len(
                    [
                        message
                        for message in load_workspace(workspace).member_messages.values()
                        if message.spec.audit.get("source") == "connector-failure-reminder"
                    ]
                ),
                0,
            )

            routed = route_connector_failure_reminders(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=False,
            )

            self.assertEqual(routed["summary"]["createdMessages"], 1)
            index = load_workspace(workspace)
            self.assertEqual(index.connector_health_checks[check.object_id].spec.status, "blocked")
            message = next(
                message
                for message in index.member_messages.values()
                if message.spec.audit.get("source") == "connector-failure-reminder"
            )
            self.assertEqual(message.spec.messageType, "message")
            self.assertEqual(message.spec.priority, "urgent")
            self.assertEqual(message.spec.attachments, [check.object_id])
            self.assertEqual(message.spec.audit["source"], "connector-failure-reminder")
            self.assertEqual(message.spec.audit["evidenceKind"], "ConnectorHealthCheck")

            repeat = route_connector_failure_reminders(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=False,
            )
            self.assertEqual(repeat["summary"]["createdMessages"], 0)
            self.assertEqual(repeat["summary"]["alreadyOpen"], 1)
            self.assertEqual(
                len(
                    [
                        message
                        for message in load_workspace(workspace).member_messages.values()
                        if message.spec.audit.get("source") == "connector-failure-reminder"
                    ]
                ),
                1,
            )

            client = TestClient(create_app(workspace))
            response = client.get("/connectors/operations/reminders", params={"connector": "github-health"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["summary"]["alreadyOpen"], 1)

            post = client.post(
                "/connectors/operations/reminders",
                json={"actorMember": "memory-service", "connector": "github-health", "dryRun": True},
            )
            self.assertEqual(post.status_code, 200)
            self.assertEqual(post.json()["summary"]["createdMessages"], 0)

    def test_repeated_connector_failures_escalate_to_deduped_review_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_connector(workspace)
            os.environ.pop("AITEAMOS_TEST_GITHUB_TOKEN", None)
            os.environ.pop("AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET", None)
            first = check_connector_health(
                workspace,
                "github-health",
                actor_member="memory-service",
                observed_repositories=["example/aiteamos"],
                observed_installation_ids=["12345"],
            )
            routed_reminder = route_connector_failure_reminders(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=False,
            )
            time.sleep(0.01)
            second = check_connector_health(
                workspace,
                "github-health",
                actor_member="memory-service",
                observed_repositories=["example/aiteamos"],
                observed_installation_ids=["12345"],
            )
            self.assertNotEqual(first.object_id, second.object_id)

            candidates = connector_failure_escalation_candidates(workspace, connector="github-health", min_evidence=2)

            self.assertEqual(candidates["summary"]["candidates"], 1)
            self.assertEqual(candidates["summary"]["routable"], 1)
            candidate = candidates["candidates"][0]
            self.assertEqual(candidate["spec"]["evidenceCount"], 2)
            self.assertEqual(candidate["spec"]["existingReminderMessages"], [routed_reminder["createdMessages"][0]["id"]])
            self.assertEqual(candidate["spec"]["toMembers"], ["memory-service"])
            health = evaluate_knowledge_health(workspace)
            self.assertTrue(
                any(issue["kind"] == "connector-failure-escalation" and issue["ref"] == candidate["id"] for issue in health["issues"])
            )

            dry_run = route_connector_failure_escalations(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=True,
                min_evidence=2,
            )
            self.assertEqual(dry_run["summary"]["createdReviewRequests"], 0)
            self.assertEqual(
                len(
                    [
                        message
                        for message in load_workspace(workspace).member_messages.values()
                        if message.spec.audit.get("source") == "connector-failure-escalation"
                    ]
                ),
                0,
            )

            routed = route_connector_failure_escalations(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=False,
                min_evidence=2,
            )

            self.assertEqual(routed["summary"]["createdReviewRequests"], 1)
            index = load_workspace(workspace)
            review_requests = [message for message in index.member_messages.values() if message.spec.messageType == "review-request"]
            self.assertEqual(len(review_requests), 1)
            review_request = review_requests[0]
            self.assertEqual(review_request.spec.priority, "urgent")
            self.assertEqual(review_request.spec.attachments, [first.object_id, second.object_id])
            self.assertEqual(review_request.spec.audit["source"], "connector-failure-escalation")
            self.assertEqual(review_request.spec.audit["reviewKind"], "connector-failure")
            self.assertEqual(review_request.spec.audit["evidenceIds"], [first.object_id, second.object_id])
            health = evaluate_knowledge_health(workspace)
            self.assertTrue(
                any(issue["kind"] == "connector-failure-review-open" and issue["ref"] == review_request.object_id for issue in health["issues"])
            )

            repeat = route_connector_failure_escalations(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=False,
                min_evidence=2,
            )
            self.assertEqual(repeat["summary"]["createdReviewRequests"], 0)
            self.assertEqual(repeat["summary"]["alreadyOpen"], 1)
            self.assertEqual(
                len(
                    [
                        message
                        for message in load_workspace(workspace).member_messages.values()
                        if message.spec.audit.get("source") in {"connector-failure-reminder", "connector-failure-escalation"}
                    ]
                ),
                2,
            )

            client = TestClient(create_app(workspace))
            response = client.get("/connectors/operations/escalations", params={"connector": "github-health", "minEvidence": 2})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["summary"]["alreadyOpen"], 1)
            open_suggestions = connector_remediation_suggestions(workspace, connector="github-health", min_evidence=2)
            self.assertEqual(open_suggestions["summary"]["suggestions"], 1)
            self.assertEqual(open_suggestions["summary"]["fromOpenReviewRequests"], 1)
            open_suggestion = open_suggestions["suggestions"][0]["spec"]
            self.assertEqual(open_suggestion["sourceReviewRequest"], review_request.object_id)
            self.assertEqual(open_suggestion["suggestedOwnerMember"], "memory-service")
            self.assertEqual(open_suggestion["suggestedAssignment"], "aiteamos-memory-service")
            self.assertTrue(open_suggestion["readyForTaskPlan"])
            self.assertEqual(open_suggestion["actionableEvidenceIds"], [first.object_id, second.object_id])
            self.assertEqual(open_suggestion["proposedTaskPlan"]["kind"], "TaskPlan")
            self.assertEqual(open_suggestion["proposedTaskPlan"]["spec"]["subtasks"][0]["assignedMember"], "memory-service")
            api_suggestions = client.get("/connectors/operations/remediation-suggestions", params={"connector": "github-health", "minEvidence": 2})
            self.assertEqual(api_suggestions.status_code, 200)
            self.assertEqual(api_suggestions.json()["summary"]["suggestions"], 1)

            service_submit = client.post(
                f"/connectors/operations/remediation-suggestions/{open_suggestions['suggestions'][0]['id']}/task-plan",
                json={
                    "actorMember": "memory-service",
                    "taskPlan": open_suggestion["proposedTaskPlan"],
                    "sourceActionableEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "minEvidence": 2,
                },
            )
            self.assertEqual(service_submit.status_code, 400)
            self.assertIn("denied by effective permissions", service_submit.text)

            plan_submit = client.post(
                f"/connectors/operations/remediation-suggestions/{open_suggestions['suggestions'][0]['id']}/task-plan",
                json={
                    "actorMember": "frontend-human",
                    "taskPlan": open_suggestion["proposedTaskPlan"],
                    "sourceActionableEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "minEvidence": 2,
                },
            )
            self.assertEqual(plan_submit.status_code, 200)
            submitted_plan = plan_submit.json()["taskPlan"]
            self.assertEqual(submitted_plan["kind"], "TaskPlan")
            self.assertTrue(submitted_plan["id"].startswith("PLAN-"))
            self.assertFalse(submitted_plan["id"].startswith("PLAN-PREVIEW"))
            self.assertEqual(submitted_plan["spec"]["createdByMember"], "frontend-human")
            self.assertEqual(submitted_plan["spec"]["connectorRemediation"]["sourceSuggestion"], open_suggestions["suggestions"][0]["id"])
            self.assertEqual(submitted_plan["spec"]["connectorRemediation"]["actionableEvidenceIds"], [first.object_id, second.object_id])
            self.assertEqual(submitted_plan["spec"]["decisionAudit"][0]["source"], "connector-remediation-submit")
            self.assertEqual(plan_submit.json()["permissionDecision"]["decision"], "ask")
            indexed_plan = load_workspace(workspace).task_plans[submitted_plan["id"]]
            self.assertEqual(indexed_plan.spec.createdByMember, "frontend-human")
            plan_projection = connector_remediation_task_plan_records(workspace, connector="github-health")
            self.assertEqual(plan_projection["summary"]["taskPlans"], 1)
            self.assertEqual(plan_projection["summary"]["draft"], 1)
            self.assertEqual(plan_projection["summary"]["submittedByHuman"], 1)
            self.assertEqual(plan_projection["summary"]["evidenceItems"], 2)
            projected_plan = plan_projection["taskPlans"][0]
            self.assertEqual(projected_plan["id"], submitted_plan["id"])
            self.assertEqual(projected_plan["spec"]["connector"], "github-health")
            self.assertEqual(projected_plan["spec"]["submittedByMember"], "frontend-human")
            self.assertEqual(projected_plan["spec"]["submittedByMemberKind"], "human")
            self.assertEqual(projected_plan["spec"]["assignedMembers"], ["memory-service"])
            self.assertEqual(projected_plan["spec"]["assignments"], ["aiteamos-memory-service"])
            self.assertEqual(projected_plan["spec"]["sourceReviewRequest"], review_request.object_id)
            member_projection = connector_remediation_task_plan_records(workspace, member="memory-service")
            self.assertEqual(member_projection["summary"]["taskPlans"], 1)
            actor_projection = connector_remediation_task_plan_records(workspace, member="frontend-human")
            self.assertEqual(actor_projection["summary"]["taskPlans"], 1)
            assignment_projection = connector_remediation_task_plan_records(workspace, assignment="aiteamos-memory-service")
            self.assertEqual(assignment_projection["summary"]["taskPlans"], 1)
            api_plan_projection = client.get("/connectors/operations/remediation-task-plans", params={"connector": "github-health"})
            self.assertEqual(api_plan_projection.status_code, 200)
            self.assertEqual(api_plan_projection.json()["summary"]["taskPlans"], 1)

            service_accept = client.post(
                f"/connectors/operations/remediation-task-plans/{submitted_plan['id']}/accept",
                json={
                    "actorMember": "memory-service",
                    "reviewedEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "reviewedReviewRequests": [review_request.object_id],
                    "dryRun": False,
                },
            )
            self.assertEqual(service_accept.status_code, 400)
            self.assertIn("denied by effective permissions", service_accept.text)
            accept_preview = client.post(
                f"/connectors/operations/remediation-task-plans/{submitted_plan['id']}/accept",
                json={
                    "actorMember": "frontend-human",
                    "reviewedEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "reviewedReviewRequests": [review_request.object_id],
                },
            )
            self.assertEqual(accept_preview.status_code, 200)
            self.assertTrue(accept_preview.json()["dryRun"])
            self.assertFalse(accept_preview.json()["written"])
            self.assertEqual(len(accept_preview.json()["plannedTasks"]), 1)
            accept_submit = client.post(
                f"/connectors/operations/remediation-task-plans/{submitted_plan['id']}/accept",
                json={
                    "actorMember": "frontend-human",
                    "reviewedEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "reviewedReviewRequests": [review_request.object_id],
                    "dryRun": False,
                },
            )
            self.assertEqual(accept_submit.status_code, 200)
            accepted_payload = accept_submit.json()
            self.assertTrue(accepted_payload["written"])
            self.assertEqual(accepted_payload["taskPlan"]["spec"]["status"], "accepted")
            self.assertEqual(accepted_payload["taskPlan"]["spec"]["acceptedByMember"], "frontend-human")
            self.assertEqual(accepted_payload["taskPlan"]["spec"]["materializedTaskCount"], 1)
            self.assertEqual(len(accepted_payload["createdTasks"]), 1)
            created_task = accepted_payload["createdTasks"][0]
            self.assertEqual(created_task["kind"], "Task")
            self.assertEqual(created_task["spec"]["assignedMember"], "memory-service")
            self.assertEqual(created_task["spec"]["assignment"], "aiteamos-memory-service")
            self.assertEqual(created_task["spec"]["sourceTaskPlan"], submitted_plan["id"])
            self.assertEqual(created_task["spec"]["connectorRemediation"]["connector"], "github-health")
            accepted_index = load_workspace(workspace)
            accepted_plan = accepted_index.task_plans[submitted_plan["id"]]
            self.assertEqual(accepted_plan.spec.status, "accepted")
            self.assertIn(created_task["id"], accepted_index.tasks)
            self.assertFalse(any(run.spec.task == created_task["id"] for run in accepted_index.runs.values()))
            accepted_projection = connector_remediation_task_plan_records(workspace, status="accepted")
            self.assertEqual(accepted_projection["summary"]["taskPlans"], 1)
            self.assertEqual(accepted_projection["summary"]["materialized"], 1)
            self.assertEqual(accepted_projection["summary"]["createdTasks"], 1)
            materialized_tasks = connector_remediation_materialized_task_records(workspace, connector="github-health")
            self.assertEqual(materialized_tasks["summary"]["tasks"], 1)
            self.assertEqual(materialized_tasks["summary"]["todo"], 1)
            self.assertEqual(materialized_tasks["summary"]["readyToRun"], 1)
            self.assertEqual(materialized_tasks["summary"]["launchReady"], 1)
            materialized_task = materialized_tasks["tasks"][0]
            self.assertEqual(materialized_task["id"], created_task["id"])
            self.assertEqual(materialized_task["spec"]["sourceTaskPlan"], submitted_plan["id"])
            self.assertEqual(materialized_task["spec"]["taskPlanStatus"], "accepted")
            self.assertEqual(materialized_task["spec"]["taskPlanAcceptedByMember"], "frontend-human")
            self.assertEqual(materialized_task["spec"]["connector"], "github-health")
            self.assertEqual(materialized_task["spec"]["queueStatus"], "ready-to-run")
            self.assertTrue(materialized_task["spec"]["launchReady"])
            self.assertEqual(materialized_task["spec"]["memberKind"], "service")
            self.assertEqual(materialized_task["spec"]["selectedAssignment"], "aiteamos-memory-service")
            api_materialized_tasks = client.get("/connectors/operations/remediation-tasks", params={"connector": "github-health"})
            self.assertEqual(api_materialized_tasks.status_code, 200)
            self.assertEqual(api_materialized_tasks.json()["summary"]["tasks"], 1)
            plan_task_projection = client.get(
                "/connectors/operations/remediation-tasks",
                params={"taskPlan": submitted_plan["id"], "member": "memory-service"},
            )
            self.assertEqual(plan_task_projection.status_code, 200)
            self.assertEqual(plan_task_projection.json()["tasks"][0]["id"], created_task["id"])
            launch_preview_missing_evidence = launch_connector_remediation_task_run(
                workspace,
                created_task["id"],
                actor_member="frontend-human",
                dry_run=True,
            )
            self.assertTrue(launch_preview_missing_evidence["dryRun"])
            self.assertFalse(launch_preview_missing_evidence["canLaunch"])
            self.assertIn(open_suggestion["actionableEvidenceIds"][0], launch_preview_missing_evidence["evidenceReview"]["missingEvidenceIds"])
            launch_preview = client.post(
                f"/connectors/operations/remediation-tasks/{created_task['id']}/run",
                json={
                    "actorMember": "frontend-human",
                    "reviewedEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "reviewedReviewRequests": [review_request.object_id],
                },
            )
            self.assertEqual(launch_preview.status_code, 200)
            self.assertTrue(launch_preview.json()["dryRun"])
            self.assertTrue(launch_preview.json()["canLaunch"])
            self.assertFalse(launch_preview.json()["written"])
            launch_submit = client.post(
                f"/connectors/operations/remediation-tasks/{created_task['id']}/run",
                json={
                    "actorMember": "frontend-human",
                    "reviewedEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "reviewedReviewRequests": [review_request.object_id],
                    "dryRun": False,
                },
            )
            self.assertEqual(launch_submit.status_code, 200)
            launched = launch_submit.json()
            self.assertTrue(launched["written"])
            self.assertEqual(launched["run"]["kind"], "Run")
            self.assertEqual(launched["run"]["spec"]["task"], created_task["id"])
            self.assertEqual(launched["run"]["spec"]["member"], "memory-service")
            self.assertEqual(launched["run"]["spec"]["assignment"], "aiteamos-memory-service")
            self.assertEqual(launched["run"]["spec"]["connectorRemediation"]["source"], "connector-remediation-task-run-launch")
            self.assertEqual(launched["run"]["spec"]["connectorRemediation"]["taskPlan"], submitted_plan["id"])
            self.assertEqual(launched["run"]["spec"]["connectorRemediation"]["reviewedEvidenceIds"], open_suggestion["actionableEvidenceIds"])
            self.assertEqual(launched["run"]["spec"]["createdByMember"], "frontend-human")
            self.assertEqual(launched["task"]["spec"]["latestRun"], launched["run"]["id"])
            self.assertEqual(launched["task"]["spec"]["queueStatus"], "active")
            remediation_runs = connector_remediation_run_records(workspace, connector="github-health")
            self.assertEqual(remediation_runs["summary"]["runs"], 1)
            self.assertEqual(remediation_runs["summary"]["serviceRuns"], 1)
            self.assertEqual(remediation_runs["summary"]["workerBlocked"], 1)
            self.assertEqual(remediation_runs["summary"]["authorizationBlocked"], 1)
            self.assertEqual(remediation_runs["summary"]["evidenceItems"], 2)
            remediation_run = remediation_runs["runs"][0]
            self.assertEqual(remediation_run["id"], launched["run"]["id"])
            self.assertEqual(remediation_run["spec"]["connector"], "github-health")
            self.assertEqual(remediation_run["spec"]["sourceTaskPlan"], submitted_plan["id"])
            self.assertEqual(remediation_run["spec"]["task"], created_task["id"])
            self.assertEqual(remediation_run["spec"]["selectedMember"], "memory-service")
            self.assertEqual(remediation_run["spec"]["selectedAssignment"], "aiteamos-memory-service")
            self.assertTrue(remediation_run["spec"]["evidenceReviewComplete"])
            self.assertEqual(remediation_run["spec"]["workerReadinessStatus"], "BLOCKED")
            self.assertEqual(remediation_run["spec"]["workerAuthorizationStatus"], "BLOCKED")
            self.assertEqual(remediation_run["spec"]["nextControlPlaneAction"], "inspect-service-run-readiness")
            api_remediation_runs = client.get(
                "/connectors/operations/remediation-runs",
                params={"connector": "github-health", "member": "memory-service"},
            )
            self.assertEqual(api_remediation_runs.status_code, 200)
            self.assertEqual(api_remediation_runs.json()["summary"]["runs"], 1)
            self.assertEqual(api_remediation_runs.json()["runs"][0]["id"], launched["run"]["id"])
            update_run(
                workspace,
                launched["run"]["id"],
                {
                    "worker": {
                        "verificationCommands": ["python3 -c 'print(1)'"],
                    }
                },
            )
            permission_blocked_runs = connector_remediation_run_records(workspace, connector="github-health")
            permission_blocked_run = permission_blocked_runs["runs"][0]
            self.assertTrue(permission_blocked_run["spec"]["permissionApprovalRequired"])
            self.assertEqual(permission_blocked_run["spec"]["nextControlPlaneAction"], "request-permission-approval")
            denied_action = permission_blocked_run["spec"]["deniedPermissionActions"][0]["action"]
            denied_canonical = denied_action["canonical"]
            permission_preview = request_connector_remediation_run_permission(
                workspace,
                launched["run"]["id"],
                actor_member="frontend-human",
                action_canonical=denied_canonical,
                dry_run=True,
            )
            self.assertTrue(permission_preview["dryRun"])
            self.assertTrue(permission_preview["canRequest"])
            self.assertFalse(permission_preview["written"])
            self.assertEqual(permission_preview["requestPreview"]["action"]["canonical"], denied_canonical)
            request_response = client.post(
                f"/connectors/operations/remediation-runs/{launched['run']['id']}/permission-request",
                json={
                    "actorMember": "frontend-human",
                    "actionCanonical": denied_canonical,
                    "dryRun": False,
                },
            )
            self.assertEqual(request_response.status_code, 200)
            permission_request = request_response.json()["permissionRequest"]
            self.assertTrue(request_response.json()["written"])
            self.assertEqual(permission_request["kind"], "PermissionRequest")
            self.assertEqual(permission_request["spec"]["source"], "connector-remediation-run-permission-request")
            self.assertEqual(permission_request["spec"]["member"], "memory-service")
            self.assertEqual(permission_request["spec"]["run"], launched["run"]["id"])
            self.assertEqual(permission_request["spec"]["requesterMember"], "frontend-human")
            self.assertEqual(permission_request["spec"]["action"]["canonical"], denied_canonical)
            self.assertEqual(permission_request["spec"]["currentDecision"]["decision"], "deny")
            permission_pending_runs = connector_remediation_run_records(workspace, connector="github-health")
            permission_pending_run = permission_pending_runs["runs"][0]
            self.assertEqual(permission_pending_run["spec"]["pendingPermissionRequestIds"], [permission_request["id"]])
            self.assertEqual(permission_pending_run["spec"]["nextControlPlaneAction"], "await-permission-approval")
            duplicate_request = client.post(
                f"/connectors/operations/remediation-runs/{launched['run']['id']}/permission-request",
                json={
                    "actorMember": "frontend-human",
                    "actionCanonical": denied_canonical,
                    "dryRun": False,
                },
            )
            self.assertEqual(duplicate_request.status_code, 200)
            self.assertFalse(duplicate_request.json()["written"])
            self.assertEqual(duplicate_request.json()["existingRequest"]["id"], permission_request["id"])
            reject_permission_request(
                workspace,
                permission_request["id"],
                reviewer_member="frontend-human",
                reason="Bash remains hard-denied for service remediation runs.",
            )
            permission_rejected_run = connector_remediation_run_records(workspace, connector="github-health")["runs"][0]
            self.assertEqual(permission_rejected_run["spec"]["pendingPermissionRequestIds"], [])
            self.assertEqual(permission_rejected_run["spec"]["rejectedPermissionRequestIds"], [permission_request["id"]])
            self.assertEqual(permission_rejected_run["spec"]["permissionApprovalOutcome"], "rejected")
            self.assertEqual(permission_rejected_run["spec"]["nextControlPlaneAction"], "review-rejected-permission-request")
            second_request_response = client.post(
                f"/connectors/operations/remediation-runs/{launched['run']['id']}/permission-request",
                json={
                    "actorMember": "frontend-human",
                    "actionCanonical": denied_canonical,
                    "dryRun": False,
                },
            )
            self.assertEqual(second_request_response.status_code, 200)
            second_permission_request = second_request_response.json()["permissionRequest"]
            approval = approve_permission_request(
                workspace,
                second_permission_request["id"],
                reviewer_member="frontend-human",
                reason="Approve narrowly to prove hard-deny policy still wins.",
            )
            permission_approved_run = connector_remediation_run_records(workspace, connector="github-health")["runs"][0]
            self.assertEqual(permission_approved_run["spec"]["approvedPermissionRequestIds"], [second_permission_request["id"]])
            self.assertEqual(permission_approved_run["spec"]["activePermissionGrantIds"], [approval["grant"].object_id])
            self.assertEqual(permission_approved_run["spec"]["permissionApprovalOutcome"], "approved-but-still-blocked")
            self.assertEqual(permission_approved_run["spec"]["nextControlPlaneAction"], "review-permission-policy-blocker")
            blocked_repeat_request = request_connector_remediation_run_permission(
                workspace,
                launched["run"]["id"],
                actor_member="frontend-human",
                action_canonical=denied_canonical,
                dry_run=True,
            )
            self.assertFalse(blocked_repeat_request["canRequest"])
            self.assertEqual(blocked_repeat_request["permissionApprovalOutcome"], "approved-but-still-blocked")
            repeat_launch = client.post(
                f"/connectors/operations/remediation-tasks/{created_task['id']}/run",
                json={
                    "actorMember": "frontend-human",
                    "reviewedEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "reviewedReviewRequests": [review_request.object_id],
                    "dryRun": False,
                },
            )
            self.assertEqual(repeat_launch.status_code, 400)
            self.assertIn("not ready-to-run", repeat_launch.json()["detail"])
            repeat_accept = client.post(
                f"/connectors/operations/remediation-task-plans/{submitted_plan['id']}/accept",
                json={
                    "actorMember": "frontend-human",
                    "reviewedEvidenceIds": open_suggestion["actionableEvidenceIds"],
                    "reviewedReviewRequests": [review_request.object_id],
                    "dryRun": False,
                },
            )
            self.assertEqual(repeat_accept.status_code, 200)
            self.assertTrue(repeat_accept.json()["alreadyMaterialized"])

            post = client.post(
                "/connectors/operations/escalations",
                json={"actorMember": "memory-service", "connector": "github-health", "dryRun": True, "minEvidence": 2},
            )
            self.assertEqual(post.status_code, 200)
            self.assertEqual(post.json()["summary"]["createdReviewRequests"], 0)

            generic_resolve = client.post(
                f"/member-messages/{review_request.object_id}/resolve",
                json={"actorMember": "memory-service", "resolution": "Reviewed connector evidence."},
            )
            self.assertEqual(generic_resolve.status_code, 400)

            with self.assertRaisesRegex(ValueError, "missing reviewed evidence"):
                resolve_connector_failure_escalation(
                    workspace,
                    review_request.object_id,
                    actor_member="memory-service",
                    resolution="Reviewed reminder but not all health checks.",
                    evidence_reviewed=[first.object_id],
                    reminder_messages_reviewed=[routed_reminder["createdMessages"][0]["id"]],
                )

            resolved = resolve_connector_failure_escalation(
                workspace,
                review_request.object_id,
                actor_member="memory-service",
                resolution="Reviewed both connector health checks and the routed reminder; connector policy follow-up is tracked outside this request.",
                evidence_reviewed=[first.object_id, second.object_id],
                reminder_messages_reviewed=[routed_reminder["createdMessages"][0]["id"]],
                follow_up_reviewed={"connectorPolicy": "no-change", "permissionRequest": None},
            )
            self.assertEqual(resolved.spec.status, "resolved")
            self.assertEqual(resolved.spec.resolvedByMember, "memory-service")
            resolution_audit = resolved.spec.audit["connectorEscalationResolution"]
            self.assertEqual(resolution_audit["evidenceReviewed"], [first.object_id, second.object_id])
            self.assertEqual(resolution_audit["reminderMessagesReviewed"], [routed_reminder["createdMessages"][0]["id"]])
            self.assertEqual(resolution_audit["followUpReviewed"]["connectorPolicy"], "no-change")
            health = evaluate_knowledge_health(workspace)
            self.assertFalse(
                any(issue["kind"] == "connector-failure-review-open" and issue["ref"] == review_request.object_id for issue in health["issues"])
            )

            suppressed_candidates = connector_failure_escalation_candidates(workspace, connector="github-health", min_evidence=2)
            self.assertEqual(suppressed_candidates["summary"]["routable"], 0)
            self.assertEqual(suppressed_candidates["summary"]["suppressedByResolution"], 1)
            self.assertEqual(suppressed_candidates["summary"]["withPriorResolution"], 1)
            self.assertEqual(suppressed_candidates["summary"]["withUnreviewedEvidence"], 0)
            suppressed_spec = suppressed_candidates["candidates"][0]["spec"]
            self.assertEqual(suppressed_spec["latestResolvedReviewRequest"], review_request.object_id)
            self.assertEqual(suppressed_spec["resolvedReviewRequest"], review_request.object_id)
            self.assertEqual(suppressed_spec["reviewedEvidenceIds"], [first.object_id, second.object_id])
            self.assertEqual(suppressed_spec["unreviewedEvidenceIds"], [])
            self.assertTrue(suppressed_spec["resolutionCoversCurrentEvidence"])
            self.assertEqual(suppressed_spec["resolutionReviewedByMember"], "memory-service")
            self.assertEqual(suppressed_spec["notRoutableReason"], "resolved-evidence-reviewed")
            suppressed_suggestions = connector_remediation_suggestions(workspace, connector="github-health", min_evidence=2)
            self.assertEqual(suppressed_suggestions["summary"]["suggestions"], 0)
            health = evaluate_knowledge_health(workspace)
            self.assertFalse(any(issue["kind"] == "connector-failure-escalation" for issue in health["issues"]))

            suppressed_route = route_connector_failure_escalations(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=False,
                min_evidence=2,
            )
            self.assertEqual(suppressed_route["summary"]["createdReviewRequests"], 0)
            self.assertEqual(suppressed_route["skipped"][0]["reason"], "resolved-evidence-reviewed")

            time.sleep(0.01)
            third = check_connector_health(
                workspace,
                "github-health",
                actor_member="memory-service",
                observed_repositories=["example/aiteamos"],
                observed_installation_ids=["12345"],
            )
            new_candidates = connector_failure_escalation_candidates(workspace, connector="github-health", min_evidence=2)
            self.assertEqual(new_candidates["summary"]["routable"], 1)
            self.assertEqual(new_candidates["summary"]["suppressedByResolution"], 0)
            self.assertEqual(new_candidates["summary"]["withPriorResolution"], 1)
            self.assertEqual(new_candidates["summary"]["withUnreviewedEvidence"], 1)
            new_spec = new_candidates["candidates"][0]["spec"]
            self.assertIn(third.object_id, new_spec["evidenceIds"])
            self.assertEqual(new_spec["latestResolvedReviewRequest"], review_request.object_id)
            self.assertIsNone(new_spec["resolvedReviewRequest"])
            self.assertEqual(new_spec["reviewedEvidenceIds"], [first.object_id, second.object_id])
            self.assertEqual(new_spec["unreviewedEvidenceIds"], [third.object_id])
            self.assertFalse(new_spec["resolutionCoversCurrentEvidence"])
            self.assertEqual(new_spec["notRoutableReason"], None)
            new_suggestions = connector_remediation_suggestions(workspace, connector="github-health", min_evidence=2)
            self.assertEqual(new_suggestions["summary"]["suggestions"], 1)
            self.assertEqual(new_suggestions["summary"]["fromUnreviewedEvidence"], 1)
            new_suggestion = new_suggestions["suggestions"][0]["spec"]
            self.assertEqual(new_suggestion["latestResolvedReviewRequest"], review_request.object_id)
            self.assertEqual(new_suggestion["reviewedEvidenceIds"], [first.object_id, second.object_id])
            self.assertEqual(new_suggestion["unreviewedEvidenceIds"], [third.object_id])
            self.assertEqual(new_suggestion["actionableEvidenceIds"], [third.object_id])
            self.assertIn("separate reviewed change", new_suggestion["proposedTaskPlan"]["spec"]["subtasks"][0]["acceptance"][-1])

            stale_submit = client.post(
                f"/connectors/operations/remediation-suggestions/{new_suggestions['suggestions'][0]['id']}/task-plan",
                json={
                    "actorMember": "frontend-human",
                    "taskPlan": new_suggestion["proposedTaskPlan"],
                    "sourceActionableEvidenceIds": [first.object_id, second.object_id],
                    "minEvidence": 2,
                },
            )
            self.assertEqual(stale_submit.status_code, 400)
            self.assertIn("evidence is stale", stale_submit.text)

            second_route = route_connector_failure_escalations(
                workspace,
                actor_member="memory-service",
                connector="github-health",
                dry_run=False,
                min_evidence=2,
            )
            self.assertEqual(second_route["summary"]["createdReviewRequests"], 1)
            second_review_request = second_route["createdReviewRequests"][0]
            api_resolve = client.post(
                f"/connectors/operations/escalations/{second_review_request['id']}/resolve",
                json={
                    "actorMember": "memory-service",
                    "resolution": "Reviewed repeated evidence through the connector escalation workflow.",
                    "evidenceReviewed": [first.object_id, second.object_id, third.object_id],
                    "reminderMessagesReviewed": [routed_reminder["createdMessages"][0]["id"]],
                    "followUpReviewed": {"connectorPolicy": "reviewed"},
                },
            )
            self.assertEqual(api_resolve.status_code, 200)
            self.assertEqual(api_resolve.json()["spec"]["status"], "resolved")
            self.assertEqual(api_resolve.json()["spec"]["audit"]["connectorEscalationResolution"]["actorMember"], "memory-service")


def _copy_workspace(temp_root: Path) -> Path:
    source = REPO_ROOT / ".aiteamos"
    target = temp_root / ".aiteamos"
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("indexes"))
    return target


def _write_connector(workspace: Path) -> None:
    write_yaml(
        workspace / "connectors" / "github-health.yaml",
        {
            "apiVersion": "aiteamos.dev/v1alpha1",
            "kind": "Connector",
            "metadata": {"name": "github-health"},
            "spec": {
                "provider": "github",
                "connectorType": "git",
                "ownerMember": "memory-service",
                "projects": ["aiteamos"],
                "config": {
                    "allowedRepositories": ["example/aiteamos"],
                    "allowedInstallationIds": ["12345"],
                    "deliveryRetentionDays": 30,
                },
                "secretRefs": {
                    "tokenEnv": "AITEAMOS_TEST_GITHUB_TOKEN",
                    "webhookSecretEnv": "AITEAMOS_TEST_GITHUB_WEBHOOK_SECRET",
                },
                "permissionPolicies": ["service-memory-default"],
            },
        },
    )


def _set_health_checked_at(workspace: Path, check_id: str, checked_at: str) -> None:
    path = workspace / "connectors" / "health" / f"{check_id}.yaml"
    data = read_yaml(path)
    data.setdefault("metadata", {})["createdAt"] = checked_at
    data.setdefault("spec", {})["checkedAt"] = checked_at
    write_yaml(path, data)


if __name__ == "__main__":
    unittest.main()
