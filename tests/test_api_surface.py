from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.inline_testclient import TestClient
import yaml

from aiteamos_api import create_app
from aiteamos_api.auth import API_TOKEN_ENV, MCP_READ_TOKEN_ENV, MCP_WRITE_TOKEN_ENV, VIEWER_TOKEN_MAP_ENV
from aiteamos_workspace import append_run_event, create_run, create_task, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"
AUTH_ENV_OFF = {
    API_TOKEN_ENV: "",
    MCP_READ_TOKEN_ENV: "",
    MCP_WRITE_TOKEN_ENV: "",
    VIEWER_TOKEN_MAP_ENV: "",
}


class CanonicalApiSurfaceTest(unittest.TestCase):
    def test_workspace_index_and_project_employee_projection_are_v2_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            index_response = client.post("/index")
            summary_response = client.get("/summary")
            project_members = client.get("/projects/aiteamos/members")
            contributors = client.get("/projects/aiteamos/contributors")
            employee_projects = client.get(f"/members/{BACKEND_MEMBER}/projects")
            growth = client.get("/member-growth")
            member_growth = client.get(f"/members/{BACKEND_MEMBER}/growth")
            project_growth = client.get("/projects/aiteamos/member-growth")
            eval_suites = client.get("/eval-suites")
            eval_results = client.get("/eval-results")
            member_activity = client.get("/member-activity", params={"member": BACKEND_MEMBER})
            member_git_activity = client.get(f"/members/{BACKEND_MEMBER}/git-activity")
            project_activity = client.get("/projects/aiteamos/activity")
            project_git_activity = client.get("/projects/aiteamos/git-activity")
            git_activity_imports = client.get("/git-activity/imports")
            project_git_activity_imports = client.get("/projects/aiteamos/git-activity/imports")
            local_scan = client.post("/git-activity/imports/admit-local-scan", json={"repository": "aiteamos", "actorMember": "frontend-human"})
            local_scan_id = local_scan.json()["receipt"]["id"] if local_scan.status_code == 200 else ""
            provider_admission = client.post(
                "/git-activity/imports/admit-provider-event",
                json={
                    "provider": "github",
                    "repository": "aiteamos",
                    "sourceType": "webhook",
                    "actorMember": "frontend-human",
                    "payload": {
                        "ref": "refs/heads/private/customer-x",
                        "after": "1234567890abcdef1234567890abcdef12345678",
                        "repository": {"full_name": "private/customer-x"},
                        "sender": {"login": "octocat"},
                    },
                },
            )
            provider_policy = client.post(
                "/git-activity/imports/policy/explain",
                json={
                    "provider": "github",
                    "repository": "aiteamos",
                    "payload": {
                        "ref": "refs/heads/main",
                        "after": "1234567890abcdef1234567890abcdef12345678",
                        "repository": {"full_name": "example/aiteamos"},
                        "sender": {"login": "octocat"},
                    },
                },
            )
            git_correlation_preview = client.get("/git-activity/imports/correlation-preview", params={"project": "aiteamos"})
            correlation_key = ""
            if git_correlation_preview.status_code == 200:
                group = next((item for item in git_correlation_preview.json()["groups"] if local_scan_id in item["receipts"]), None)
                correlation_key = group["correlationKey"] if group else ""
            correlation_review = client.post(
                "/git-activity/imports/correlations/review",
                json={
                    "correlationKey": correlation_key,
                    "receipts": [local_scan_id],
                    "reviewerMember": "frontend-human",
                    "decision": "approved",
                    "summary": "Approved reviewed local import correlation without promotion.",
                },
            )
            git_correlation_reviews = client.get("/git-activity/imports/correlations", params={"project": "aiteamos"})
            git_correlation_promotion_candidates = client.get(
                "/git-activity/imports/correlations/promotion-candidates",
                params={"project": "aiteamos"},
            )
            promoted_scan = client.post(
                f"/git-activity/imports/{local_scan_id}/promote",
                json={
                    "reviewerMember": "frontend-human",
                    "member": BACKEND_MEMBER,
                    "assignment": BACKEND_ASSIGNMENT,
                    "activityType": "commit",
                    "summary": "Promoted reviewed local Git import evidence.",
                },
            )
            promoted_activity_id = promoted_scan.json()["activities"][0]["id"] if promoted_scan.status_code == 200 else ""
            if promoted_activity_id:
                _patch_git_activity(
                    workspace,
                    promoted_activity_id,
                    retainedUntil="2026-05-20T12:00:00+08:00",
                    exportPolicy="include",
                )
            git_activity_retention_candidates = client.get(
                "/git-activity/retention-candidates",
                params={"project": "aiteamos", "now": "2026-05-21T12:00:00+08:00"},
            )
            git_activity_retention_sweep = client.post(
                "/git-activity/retention-sweep",
                json={
                    "actorMember": "frontend-human",
                    "project": "aiteamos",
                    "now": "2026-05-21T12:00:00+08:00",
                    "dryRun": True,
                },
            )
            git_activity_lifecycle = client.post(
                f"/git-activity/{promoted_activity_id}/lifecycle",
                json={
                    "actorMember": "frontend-human",
                    "lifecycle": "archived",
                    "reason": "Archive imported Git activity evidence after projection checks.",
                    "exportPolicy": "sanitize",
                },
            )
            correlation_promotion = client.post(
                f"/git-activity/imports/correlations/{correlation_review.json().get('review', {}).get('id', '')}/promote",
                json={
                    "reviewerMember": "frontend-human",
                    "member": BACKEND_MEMBER,
                    "assignment": BACKEND_ASSIGNMENT,
                    "activityType": "commit",
                    "summary": "Consume approved local import correlation review.",
                },
            )

            self.assertEqual(index_response.status_code, 200)
            self.assertTrue(index_response.json()["derived"])
            self.assertTrue((workspace / "indexes" / "aiteamos.sqlite").exists())
            self.assertEqual(summary_response.status_code, 200)
            self.assertGreaterEqual(summary_response.json()["counts"]["members"], 4)
            self.assertEqual(project_members.status_code, 200)
            member_kinds = {item["id"]: item["spec"]["kind"] for item in project_members.json()}
            self.assertEqual(member_kinds[BACKEND_MEMBER], "digital")
            self.assertEqual(member_kinds["frontend-human"], "human")
            self.assertEqual(member_kinds["memory-service"], "service")

            self.assertEqual(contributors.status_code, 200)
            backend_row = next(item for item in contributors.json() if item["member"] == BACKEND_MEMBER)
            self.assertEqual(backend_row["memberKind"], "digital")
            self.assertIn(BACKEND_ASSIGNMENT, backend_row["assignments"])
            self.assertNotIn("role", backend_row)
            self.assertEqual(employee_projects.status_code, 200)
            self.assertEqual(employee_projects.json()[0]["id"], "aiteamos")
            self.assertEqual(growth.status_code, 200)
            growth_payload = growth.json()
            backend_growth = next(item for item in growth_payload["items"] if item["member"] == BACKEND_MEMBER)
            self.assertEqual(backend_growth["memberKind"], "digital")
            self.assertGreaterEqual(backend_growth["activityCounts"]["tasks"], 1)
            self.assertGreaterEqual(backend_growth["activityCounts"]["memberActivities"], 1)
            self.assertGreaterEqual(backend_growth["activityCounts"]["gitActivities"], 1)
            self.assertGreaterEqual(backend_growth["contributionCounts"]["authoredWork"], 1)
            self.assertGreaterEqual(backend_growth["contributionCounts"]["gitWork"], 1)
            self.assertIn("review-pending-memory-proposals", backend_growth["supportSignals"])
            self.assertIn("Growth projections are read-only support signals", growth_payload["nonPunitivePolicy"][0])
            self.assertNotIn("score", backend_growth)
            self.assertEqual(member_growth.status_code, 200)
            self.assertEqual([item["member"] for item in member_growth.json()["items"]], [BACKEND_MEMBER])
            self.assertEqual(project_growth.status_code, 200)
            self.assertIn(BACKEND_MEMBER, {item["member"] for item in project_growth.json()["items"]})
            self.assertEqual(eval_suites.status_code, 200)
            eval_suite_ids = {item["id"] for item in eval_suites.json()}
            self.assertIn("aiteamos-eval-suite-api-surface", eval_suite_ids)
            self.assertEqual(eval_results.status_code, 200)
            eval_result_ids = {item["id"] for item in eval_results.json()}
            self.assertIn("ERES-20260522T204421556", eval_result_ids)
            self.assertIn("ERES-20260522T215837092", eval_result_ids)
            self.assertEqual(member_activity.status_code, 200)
            self.assertIn("ACT-20260521T090000000", {item["id"] for item in member_activity.json()})
            self.assertEqual(member_git_activity.status_code, 200)
            self.assertIn("GIT-20260521T090500000", {item["id"] for item in member_git_activity.json()})
            self.assertEqual(project_activity.status_code, 200)
            self.assertGreaterEqual(len(project_activity.json()), 3)
            self.assertEqual(project_git_activity.status_code, 200)
            self.assertIn("GIT-20260521T090500000", {item["id"] for item in project_git_activity.json()})
            self.assertEqual(git_activity_imports.status_code, 200)
            import_payload = next(item for item in git_activity_imports.json() if item["id"] == "GITIMP-20260521T093000000")
            self.assertEqual(import_payload["spec"]["redactionPolicy"], "metadata-only")
            self.assertFalse(import_payload["spec"]["payloadRetained"])
            self.assertEqual(import_payload["spec"]["reviewedByMember"], "frontend-human")
            self.assertEqual(project_git_activity_imports.status_code, 200)
            self.assertIn("GITIMP-20260521T093000000", {item["id"] for item in project_git_activity_imports.json()})
            self.assertEqual(local_scan.status_code, 200)
            self.assertTrue(local_scan.json()["created"])
            self.assertEqual(local_scan.json()["receipt"]["spec"]["status"], "needs-review")
            self.assertEqual(local_scan.json()["receipt"]["spec"]["importedActivities"], [])
            self.assertEqual(provider_admission.status_code, 200)
            provider_receipt = provider_admission.json()["receipt"]
            self.assertEqual(provider_receipt["spec"]["provider"], "github")
            self.assertEqual(provider_receipt["spec"]["sourceType"], "webhook")
            self.assertEqual(provider_receipt["spec"]["status"], "needs-review")
            self.assertEqual(provider_receipt["spec"]["importedActivities"], [])
            self.assertTrue(provider_receipt["spec"]["normalized"]["refRedacted"])
            self.assertNotIn("customer-x", str(provider_receipt))
            self.assertEqual(provider_policy.status_code, 200)
            self.assertEqual(provider_policy.json()["decision"], "admit-needs-review")
            self.assertFalse(provider_policy.json()["canAutoPromote"])
            self.assertEqual(git_correlation_preview.status_code, 200)
            self.assertIn("groups", git_correlation_preview.json())
            self.assertTrue(
                any(local_scan_id in group["receipts"] for group in git_correlation_preview.json()["groups"])
            )
            self.assertEqual(correlation_review.status_code, 200)
            self.assertTrue(correlation_review.json()["created"])
            self.assertEqual(correlation_review.json()["review"]["kind"], "GitActivityCorrelationReview")
            self.assertEqual(correlation_review.json()["review"]["spec"]["decision"], "approved")
            self.assertEqual(correlation_review.json()["review"]["spec"]["receipts"], [local_scan_id])
            self.assertEqual(git_correlation_reviews.status_code, 200)
            self.assertIn(correlation_review.json()["review"]["id"], {item["id"] for item in git_correlation_reviews.json()})
            self.assertEqual(git_correlation_promotion_candidates.status_code, 200)
            blocked_candidate = next(
                item
                for item in git_correlation_promotion_candidates.json()["candidates"]
                if item["review"] == correlation_review.json()["review"]["id"]
            )
            self.assertFalse(blocked_candidate["eligible"])
            self.assertTrue(any("not service-policy-import" in blocker for blocker in blocked_candidate["blockers"]))
            self.assertEqual(promoted_scan.status_code, 200)
            self.assertTrue(promoted_scan.json()["created"])
            self.assertEqual(promoted_scan.json()["receipt"]["spec"]["status"], "imported")
            self.assertEqual(promoted_scan.json()["receipt"]["spec"]["reviewedByMember"], "frontend-human")
            self.assertEqual(promoted_scan.json()["activities"][0]["spec"]["member"], BACKEND_MEMBER)
            self.assertEqual(git_activity_retention_candidates.status_code, 200)
            self.assertIn(promoted_activity_id, {item["spec"]["activity"] for item in git_activity_retention_candidates.json()["candidates"]})
            self.assertEqual(git_activity_retention_sweep.status_code, 200)
            self.assertTrue(git_activity_retention_sweep.json()["dryRun"])
            self.assertEqual(git_activity_retention_sweep.json()["updatedCount"], 0)
            self.assertIn(promoted_activity_id, {item["spec"]["activity"] for item in git_activity_retention_sweep.json()["candidates"]})
            self.assertEqual(git_activity_lifecycle.status_code, 200)
            self.assertTrue(git_activity_lifecycle.json()["updated"])
            self.assertEqual(git_activity_lifecycle.json()["activity"]["spec"]["lifecycle"], "archived")
            self.assertEqual(git_activity_lifecycle.json()["activity"]["spec"]["exportPolicy"], "sanitize")
            self.assertIn("archivedAt", git_activity_lifecycle.json()["activity"]["spec"])
            self.assertEqual(
                load_workspace(workspace).git_activity_import_receipts[local_scan_id].spec.importedActivities,
                [promoted_activity_id],
            )
            self.assertEqual(correlation_promotion.status_code, 200)
            self.assertFalse(correlation_promotion.json()["created"])
            self.assertTrue(correlation_promotion.json()["alreadyPromoted"])
            self.assertEqual(
                correlation_promotion.json()["activities"][0]["id"],
                promoted_scan.json()["activities"][0]["id"],
            )
            self.assertEqual(
                correlation_promotion.json()["review"]["spec"]["importedActivities"],
                [promoted_scan.json()["activities"][0]["id"]],
            )

    def test_task_run_and_context_surfaces_use_member_assignment_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            client = TestClient(create_app(workspace))

            task_payload = client.get(f"/tasks/{run.spec.task}").json()
            launch_plan = client.get(f"/tasks/{run.spec.task}/launch-plan").json()
            run_payload = client.get(f"/runs/{run.object_id}").json()
            context_manifest = client.get(f"/runs/{run.object_id}/context-manifest").json()
            context_preview = client.get(f"/runs/{run.object_id}/context-preview").json()

            self.assertEqual(task_payload["spec"]["assignedMember"], BACKEND_MEMBER)
            self.assertEqual(task_payload["spec"]["assignment"], BACKEND_ASSIGNMENT)
            self.assertNotIn("assignedRole", task_payload["spec"])
            self.assertEqual(launch_plan["selectedMember"], BACKEND_MEMBER)
            self.assertEqual(launch_plan["selectedAssignment"], BACKEND_ASSIGNMENT)
            self.assertEqual(launch_plan["memberKind"], "digital")
            self.assertEqual(run_payload["spec"]["member"], BACKEND_MEMBER)
            self.assertEqual(run_payload["spec"]["assignment"], BACKEND_ASSIGNMENT)
            self.assertEqual(run_payload["spec"]["memberKind"], "digital")
            self.assertEqual(context_manifest["spec"]["member"], BACKEND_MEMBER)
            self.assertEqual(context_manifest["spec"]["assignment"], BACKEND_ASSIGNMENT)
            self.assertIn("Member Identity", context_preview["capsule"])

    def test_memory_permissions_and_automation_control_plane_are_first_class(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))

            member_memory = client.get(f"/members/{BACKEND_MEMBER}/memory", params={"query": "identity"})
            project_memory = client.get("/projects/aiteamos/memory", params={"member": BACKEND_MEMBER, "query": "identity"})
            permissions = client.get("/permissions/effective", params={"member": BACKEND_MEMBER, "assignment": BACKEND_ASSIGNMENT})
            dry_run = client.post("/automations/memory-health-dry-run/dry-run", json={"actorMember": "manager"})
            all_runs = client.get("/automations/runs")
            scoped_runs = client.get("/automations/memory-health-dry-run/runs")
            blocked_trigger = client.post("/automations/memory-health-dry-run/trigger", json={"actorMember": "manager"})

            self.assertEqual(member_memory.status_code, 200)
            member_matches = member_memory.json()["matches"]
            self.assertTrue(member_matches)
            self.assertTrue(
                any("bind-aiteamos-project-memory-to-backend-runtime" in match.get("bindings", []) for match in member_matches)
            )
            self.assertEqual(project_memory.status_code, 200)
            self.assertTrue(project_memory.json()["matches"])
            self.assertEqual(permissions.status_code, 200)
            self.assertEqual(permissions.json()["decisionOrder"], ["deny", "ask", "allow"])

            self.assertEqual(dry_run.status_code, 200)
            dry_payload = dry_run.json()
            self.assertEqual(dry_payload["kind"], "AutomationRun")
            self.assertEqual(dry_payload["spec"]["automation"], "memory-health-dry-run")
            self.assertEqual(dry_payload["spec"]["status"], "dry-run")
            self.assertTrue(dry_payload["spec"]["dryRun"])
            self.assertEqual(all_runs.status_code, 200)
            self.assertIn(dry_payload["id"], {item["id"] for item in all_runs.json()})
            self.assertEqual(scoped_runs.status_code, 200)
            self.assertIn(dry_payload["id"], {item["id"] for item in scoped_runs.json()})

            self.assertEqual(blocked_trigger.status_code, 200)
            self.assertEqual(blocked_trigger.json()["spec"]["status"], "blocked")
            self.assertIn("dry-run only", blocked_trigger.json()["spec"]["summary"])

    def test_model_costs_summarize_member_run_event_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            append_run_event(workspace, run.object_id, {"type": "model.call.started", "provider": "openai", "model": "example-model"})
            append_run_event(
                workspace,
                run.object_id,
                {
                    "type": "model.call.completed",
                    "provider": "openai",
                    "model": "example-model",
                    "usage": {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
                    "cost_usd": 0.05,
                    "latency_ms": 25,
                },
            )
            client = TestClient(create_app(workspace))

            response = client.get("/models/costs")

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["source"], "workspace-event-ledger")
            self.assertEqual(payload["totals"]["calls"], 1)
            self.assertEqual(payload["totals"]["totalTokens"], 18)
            self.assertEqual(payload["totals"]["costUsd"], 0.05)
            self.assertEqual(payload["byRun"][0]["run"], run.object_id)
            self.assertEqual(payload["byRun"][0]["member"], BACKEND_MEMBER)
            self.assertEqual(payload["byRun"][0]["assignment"], BACKEND_ASSIGNMENT)

    def test_run_and_run_events_carry_lifecycle_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, AUTH_ENV_OFF):
            workspace = _copy_workspace(Path(temp_dir))
            run = _create_backend_run(workspace)
            recorded_event = append_run_event(
                workspace,
                run.object_id,
                {
                    "type": "verification.completed",
                    "tool": "unittest",
                    "decisionAudit": {
                        "decisionKind": "system_check",
                        "decision": "passed",
                        "authority": "record",
                        "reason": "Run event lifecycle metadata verified.",
                        "source": "test",
                    },
                },
            )

            index = load_workspace(workspace)
            loaded_run = index.runs[run.object_id]
            events = index.run_events[run.object_id]

            self.assertEqual(loaded_run.spec.lifecycle, "active")
            self.assertIsNotNone(loaded_run.spec.retainedUntil)
            self.assertEqual(loaded_run.spec.exportPolicy, "manifest-only")
            self.assertEqual(loaded_run.spec.decisionAudit, [])
            self.assertEqual(events[0]["type"], "run.created")
            self.assertEqual(events[0]["lifecycle"], "active")
            self.assertEqual(events[0]["retainedUntil"], loaded_run.spec.retainedUntil)
            self.assertEqual(events[0]["exportPolicy"], "manifest-only")
            self.assertEqual(recorded_event["lifecycle"], "active")
            self.assertEqual(recorded_event["retainedUntil"], loaded_run.spec.retainedUntil)
            self.assertEqual(recorded_event["exportPolicy"], "manifest-only")
            self.assertEqual(recorded_event["decisionAudit"][0]["decisionKind"], "system_check")


def _create_backend_run(workspace: Path) -> object:
    task = create_task(
        workspace,
        title="Canonical API task",
        assigned_member=BACKEND_MEMBER,
        assignment=BACKEND_ASSIGNMENT,
        execution_mode="managed_llm",
        acceptance=["api surface is exposed"],
    )
    return create_run(workspace, task_id=task.object_id, model_profile="openai-gpt-5.5-xhigh", mode="managed_llm")


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _patch_git_activity(workspace: Path, activity_id: str, **spec_updates: object) -> None:
    path = workspace / "git_activity" / f"{activity_id}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("spec", {}).update(spec_updates)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
