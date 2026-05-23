from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest

import yaml

from aiteamos_workspace import (
    admit_local_git_activity_import,
    admit_provider_git_activity_import,
    explain_git_activity_import_policy,
    git_activity_correlation_preview,
    git_activity_retention_candidates,
    promote_git_activity_correlation_review,
    load_workspace,
    promote_git_activity_import_receipt,
    review_git_activity_correlation,
    sweep_git_activity_retention,
    update_git_activity_evidence_lifecycle,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class GitActivityImportAdmissionTest(unittest.TestCase):
    def test_local_scan_writes_needs_review_receipt_without_git_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = _copy_workspace(temp_root)
            source_repo = _init_repo(temp_root / "source")
            _git(source_repo, ["checkout", "-b", "private/customer-x"])
            (source_repo / "src.txt").write_text("private branch work\n", encoding="utf-8")
            _git(source_repo, ["add", "src.txt"])
            _git(source_repo, ["commit", "-m", "private customer change"])
            _point_workspace_repository_at(workspace, source_repo)

            result = admit_local_git_activity_import(
                workspace,
                repository="aiteamos",
                ref="private/customer-x",
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )

            receipt = result["receipt"]
            self.assertTrue(result["created"])
            self.assertEqual(receipt.kind, "GitActivityImportReceipt")
            self.assertEqual(receipt.spec.status, "needs-review")
            self.assertEqual(receipt.spec.sourceType, "local-scan")
            self.assertEqual(receipt.spec.redactionPolicy, "metadata-only")
            self.assertFalse(receipt.spec.payloadRetained)
            self.assertEqual(receipt.spec.importedActivities, [])
            self.assertTrue(receipt.spec.refs[0].startswith("redacted-ref:"))
            self.assertTrue(receipt.spec.normalized["refRedacted"])
            self.assertIn("subjectSha256", receipt.spec.normalized)
            receipt_json = json.dumps(receipt.model_dump(mode="json"), sort_keys=True)
            self.assertNotIn("customer-x", receipt_json)
            self.assertNotIn("aiteamos@example.invalid", receipt_json)
            self.assertTrue(receipt.spec.decisionAudit[0].requiresHumanReview)

            index = load_workspace(workspace)
            self.assertIn(receipt.object_id, index.git_activity_import_receipts)
            self.assertNotIn(receipt.object_id, index.git_activities)

            duplicate = admit_local_git_activity_import(
                workspace,
                repository="aiteamos",
                ref="private/customer-x",
                actor_member="frontend-human",
                received_at="2026-05-21T10:01:00+08:00",
            )
            self.assertFalse(duplicate["created"])
            self.assertEqual(duplicate["duplicateOf"], receipt.object_id)

    def test_provider_event_writes_needs_review_receipt_without_raw_payload_or_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            existing_git_activity_ids = set(load_workspace(workspace).git_activities)
            github_payload = {
                "ref": "refs/heads/private/customer-x",
                "after": "1234567890abcdef1234567890abcdef12345678",
                "repository": {"full_name": "private/customer-x"},
                "sender": {"login": "octocat"},
                "head_commit": {"message": "secret customer fix", "timestamp": "2026-05-21T10:00:00+08:00"},
            }

            result = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                source_type="webhook",
                payload=github_payload,
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )

            receipt = result["receipt"]
            self.assertTrue(result["created"])
            self.assertEqual(receipt.kind, "GitActivityImportReceipt")
            self.assertEqual(receipt.spec.provider, "github")
            self.assertEqual(receipt.spec.sourceType, "webhook")
            self.assertEqual(receipt.spec.status, "needs-review")
            self.assertEqual(receipt.spec.redactionPolicy, "metadata-only")
            self.assertFalse(receipt.spec.payloadRetained)
            self.assertEqual(receipt.spec.importedActivities, [])
            self.assertTrue(receipt.spec.refs[0].startswith("redacted-ref:"))
            self.assertTrue(receipt.spec.normalized["refRedacted"])
            self.assertEqual(receipt.spec.normalized["activityType"], "commit")
            self.assertIn("actorLoginSha256", receipt.spec.normalized)
            self.assertIn("repositoryFullNameSha256", receipt.spec.normalized)
            receipt_json = json.dumps(receipt.model_dump(mode="json"), sort_keys=True)
            self.assertNotIn("customer-x", receipt_json)
            self.assertNotIn("octocat", receipt_json)
            self.assertNotIn("secret customer fix", receipt_json)
            self.assertTrue(receipt.spec.decisionAudit[0].requiresHumanReview)

            index = load_workspace(workspace)
            self.assertIn(receipt.object_id, index.git_activity_import_receipts)
            self.assertEqual(set(index.git_activities), existing_git_activity_ids)

            duplicate = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                source_type="webhook",
                payload=github_payload,
                actor_member="frontend-human",
                received_at="2026-05-21T10:01:00+08:00",
            )
            self.assertFalse(duplicate["created"])
            self.assertEqual(duplicate["duplicateOf"], receipt.object_id)

    def test_connector_git_import_policy_maps_actor_without_creating_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_git_connector(workspace, actor_login="octobot")
            payload = {
                "ref": "refs/heads/main",
                "after": "1234567890abcdef1234567890abcdef12345678",
                "repository": {"full_name": "example/aiteamos"},
                "installation": {"id": 12345},
                "sender": {"login": "octobot"},
            }

            explanation = explain_git_activity_import_policy(
                workspace,
                provider="github",
                repository="aiteamos",
                connector="github-import",
                payload=payload,
            )
            self.assertEqual(explanation["decision"], "admit-needs-review")
            self.assertEqual(explanation["targetMember"], "backend-digital")
            self.assertEqual(explanation["targetAssignment"], "aiteamos-backend-runtime")
            self.assertEqual(explanation["blockers"], [])

            result = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                connector="github-import",
                payload=payload,
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )

            receipt = result["receipt"]
            self.assertEqual(receipt.spec.status, "needs-review")
            self.assertEqual(receipt.spec.importPolicy, "reviewed-import")
            self.assertEqual(receipt.spec.normalized["member"], "backend-digital")
            self.assertEqual(receipt.spec.normalized["assignment"], "aiteamos-backend-runtime")
            self.assertEqual(receipt.spec.normalized["installationId"], "12345")
            self.assertIn("connectors/github-import.yaml", receipt.spec.evidence)
            self.assertEqual(load_workspace(workspace).git_activity_import_receipts[receipt.object_id].spec.importedActivities, [])

    def test_connector_git_import_policy_blocks_out_of_allowlist_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_git_connector(workspace, actor_login="octobot")
            payload = {
                "ref": "refs/heads/main",
                "after": "1234567890abcdef1234567890abcdef12345678",
                "repository": {"full_name": "other/private-project"},
                "installation": {"id": 12345},
                "sender": {"login": "octobot"},
            }

            result = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                connector="github-import",
                payload=payload,
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )

            receipt = result["receipt"]
            self.assertEqual(receipt.spec.status, "blocked")
            self.assertIn("provider repository is outside connector git import allowlist", receipt.spec.blockers)
            self.assertEqual(receipt.spec.importedActivities, [])
            self.assertNotIn("private-project", json.dumps(receipt.model_dump(mode="json"), sort_keys=True))

    def test_provider_pr_events_have_read_only_correlation_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            opened = {
                "action": "opened",
                "repository": {"full_name": "example/aiteamos"},
                "sender": {"login": "octobot"},
                "pull_request": {
                    "number": 77,
                    "id": 7700,
                    "node_id": "PR_node_77",
                    "head": {"ref": "feature/correlation", "sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
                    "html_url": "https://example.invalid/aiteamos/pull/77",
                    "updated_at": "2026-05-21T10:00:00+08:00",
                },
            }
            synchronized = {
                **opened,
                "action": "synchronize",
                "pull_request": {
                    **opened["pull_request"],
                    "head": {"ref": "feature/correlation", "sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
                    "updated_at": "2026-05-21T10:05:00+08:00",
                },
            }

            first = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                payload=opened,
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )["receipt"]
            second = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                payload=synchronized,
                actor_member="frontend-human",
                received_at="2026-05-21T10:05:00+08:00",
            )["receipt"]

            preview = git_activity_correlation_preview(workspace, project="aiteamos", repository="aiteamos", provider="github")
            group = _preview_group_for_receipts(preview, first.object_id, second.object_id)
            self.assertEqual(group["project"], "aiteamos")
            self.assertEqual(group["provider"], "github")
            self.assertIn("77", group["pullRequests"])
            self.assertIn("pull-request", group["eventFamilies"])
            self.assertTrue(group["multiEventRisk"])
            self.assertTrue(group["squashMergeRisk"])
            self.assertEqual(group["importedActivities"], [])
            self.assertEqual(load_workspace(workspace).git_activity_import_receipts[first.object_id].spec.importedActivities, [])

            reviewed = review_git_activity_correlation(
                workspace,
                correlation_key=group["correlationKey"],
                receipts=[first.object_id, second.object_id],
                reviewer_member="frontend-human",
                decision="approved",
                summary="Approved reviewed PR event correlation without promoting receipts.",
            )

            review = reviewed["review"]
            self.assertTrue(reviewed["created"])
            self.assertEqual(review.kind, "GitActivityCorrelationReview")
            self.assertEqual(review.spec.decision, "approved")
            self.assertEqual(review.spec.reviewerMember, "frontend-human")
            self.assertEqual(review.spec.reviewerMemberKind, "human")
            self.assertEqual(set(review.spec.receipts), {first.object_id, second.object_id})
            self.assertIn("multi-event", review.spec.riskFlags)
            self.assertIn("squash-merge", review.spec.riskFlags)
            self.assertEqual(review.spec.importedActivities, [])
            self.assertEqual(review.spec.decisionAudit[-1].decisionKind, "human_approval")

            self.assertFalse(review.spec.decisionAudit[-1].requiresHumanReview)

            index = load_workspace(workspace)
            self.assertIn(review.object_id, index.git_activity_correlation_reviews)
            self.assertEqual(index.git_activity_import_receipts[first.object_id].spec.importedActivities, [])

            duplicate = review_git_activity_correlation(
                workspace,
                correlation_key=group["correlationKey"],
                receipts=[first.object_id, second.object_id],
                reviewer_member="frontend-human",
                decision="approved",
            )
            self.assertFalse(duplicate["created"])
            self.assertEqual(duplicate["duplicateOf"], review.object_id)

            promoted = promote_git_activity_correlation_review(
                workspace,
                review.object_id,
                reviewer_member="frontend-human",
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                activity_type="pull-request",
                summary="Promoted reviewed PR event correlation as one GitActivity.",
            )

            activity = promoted["activities"][0]
            self.assertTrue(promoted["created"])
            self.assertFalse(promoted["alreadyPromoted"])
            self.assertEqual(activity.kind, "GitActivity")
            self.assertEqual(activity.spec.member, "backend-digital")
            self.assertEqual(activity.spec.assignment, "aiteamos-backend-runtime")
            self.assertEqual(activity.spec.activityType, "pull-request")
            self.assertIn(f"git_activity/correlations/{review.object_id}.yaml", activity.spec.evidence)
            self.assertIn(f"git_activity/imports/{first.object_id}.yaml", activity.spec.evidence)
            self.assertIn(f"git_activity/imports/{second.object_id}.yaml", activity.spec.evidence)

            index = load_workspace(workspace)
            updated_review = index.git_activity_correlation_reviews[review.object_id]
            self.assertEqual(updated_review.spec.importedActivities, [activity.object_id])
            self.assertEqual(updated_review.spec.decisionAudit[-1].decision, "promote-correlation")
            for receipt_id in (first.object_id, second.object_id):
                updated_receipt = index.git_activity_import_receipts[receipt_id]
                self.assertEqual(updated_receipt.spec.status, "imported")
                self.assertEqual(updated_receipt.spec.importedActivities, [activity.object_id])
                self.assertIn(f"git_activity/correlations/{review.object_id}.yaml", updated_receipt.spec.evidence)
                self.assertEqual(updated_receipt.spec.decisionAudit[-1].decisionKind, "human_approval")

            duplicate_promotion = promote_git_activity_correlation_review(
                workspace,
                review.object_id,
                reviewer_member="frontend-human",
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
            )
            self.assertFalse(duplicate_promotion["created"])
            self.assertTrue(duplicate_promotion["alreadyPromoted"])
            self.assertEqual(duplicate_promotion["activities"][0].object_id, activity.object_id)

    def test_git_activity_evidence_lifecycle_redacts_without_deleting_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            receipt = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                source_type="webhook",
                payload={
                    "ref": "refs/heads/private/customer-x",
                    "after": "1234567890abcdef1234567890abcdef12345678",
                    "repository": {"full_name": "private/customer-x"},
                    "sender": {"login": "octobot"},
                    "head_commit": {"timestamp": "2026-05-21T10:00:00+08:00"},
                },
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )["receipt"]
            promoted = promote_git_activity_import_receipt(
                workspace,
                receipt.object_id,
                reviewer_member="frontend-human",
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                activity_type="commit",
                summary="Promoted private customer Git evidence.",
            )
            activity = promoted["activities"][0]

            lifecycle_update = update_git_activity_evidence_lifecycle(
                workspace,
                activity.object_id,
                actor_member="frontend-human",
                lifecycle="redacted",
                reason="Sensitive branch evidence should be kept only as redacted lineage.",
                redaction_policy="redacted-summary",
                export_policy="exclude",
            )

            redacted = lifecycle_update["activity"]
            self.assertEqual(redacted.spec.lifecycle, "redacted")
            self.assertEqual(redacted.spec.redactionPolicy, "redacted-summary")
            self.assertEqual(redacted.spec.exportPolicy, "exclude")
            self.assertIsNotNone(redacted.spec.redactedAt)
            self.assertTrue(redacted.spec.refs[0].startswith("redacted-ref:"))
            self.assertTrue(redacted.spec.externalId.startswith("redacted:sha256:"))
            self.assertIn(f"git_activity/imports/{receipt.object_id}.yaml", redacted.spec.evidence)
            self.assertEqual(redacted.spec.decisionAudit[-1].decision, "git-activity-evidence-redacted")
            self.assertEqual(redacted.spec.decisionAudit[-1].actorMember, "frontend-human")

            index = load_workspace(workspace)
            linked_receipt = index.git_activity_import_receipts[receipt.object_id]
            self.assertEqual(linked_receipt.spec.importedActivities, [activity.object_id])
            self.assertIn(activity.object_id, index.git_activities)
            activity_json = json.dumps(index.git_activities[activity.object_id].model_dump(mode="json"), sort_keys=True)
            self.assertNotIn("customer-x", activity_json)

    def test_git_activity_retention_sweep_uses_lifecycle_gate_without_deleting_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            receipt = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                source_type="webhook",
                payload={
                    "ref": "refs/heads/main",
                    "after": "1234567890abcdef1234567890abcdef12345678",
                    "repository": {"full_name": "example/aiteamos"},
                    "sender": {"login": "octobot"},
                    "head_commit": {"timestamp": "2026-05-20T10:00:00+08:00"},
                },
                actor_member="frontend-human",
                received_at="2026-05-20T10:00:00+08:00",
            )["receipt"]
            promoted = promote_git_activity_import_receipt(
                workspace,
                receipt.object_id,
                reviewer_member="frontend-human",
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                activity_type="commit",
                summary="Promoted Git evidence with retention policy.",
            )
            activity = promoted["activities"][0]
            _patch_git_activity(
                workspace,
                activity.object_id,
                retainedUntil="2026-05-20T12:00:00+08:00",
                exportPolicy="include",
            )

            candidates = git_activity_retention_candidates(workspace, now="2026-05-21T12:00:00+08:00")
            candidate = next(item for item in candidates["candidates"] if item["spec"]["activity"] == activity.object_id)
            self.assertEqual(candidate["spec"]["recommendedLifecycle"], "archived")
            self.assertIn("active include export policy should be reduced", candidate["spec"]["warnings"][0])

            dry_run = sweep_git_activity_retention(
                workspace,
                actor_member="frontend-human",
                now="2026-05-21T12:00:00+08:00",
                dry_run=True,
            )
            self.assertEqual(dry_run["updatedCount"], 0)
            self.assertEqual(len(dry_run["candidates"]), 1)
            self.assertEqual(load_workspace(workspace).git_activities[activity.object_id].spec.lifecycle, "active")

            result = sweep_git_activity_retention(
                workspace,
                actor_member="frontend-human",
                now="2026-05-21T12:00:00+08:00",
                dry_run=False,
            )
            self.assertEqual(result["updated"], [activity.object_id])
            self.assertEqual(result["updatedCount"], 1)
            updated = load_workspace(workspace).git_activities[activity.object_id]
            self.assertEqual(updated.spec.lifecycle, "archived")
            self.assertEqual(updated.spec.exportPolicy, "sanitize")
            self.assertIsNotNone(updated.spec.archivedAt)
            self.assertEqual(updated.spec.decisionAudit[-1].source, "git-activity-evidence-lifecycle")
            self.assertIn(receipt.object_id, load_workspace(workspace).git_activity_import_receipts)
            self.assertEqual(load_workspace(workspace).git_activity_import_receipts[receipt.object_id].spec.importedActivities, [activity.object_id])

    def test_provider_push_events_flag_ref_correlation_risk_without_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            first_payload = {
                "ref": "refs/heads/main",
                "after": "1111111111111111111111111111111111111111",
                "repository": {"full_name": "example/aiteamos"},
                "sender": {"login": "octobot"},
                "head_commit": {"timestamp": "2026-05-21T10:00:00+08:00"},
            }
            second_payload = {
                **first_payload,
                "after": "2222222222222222222222222222222222222222",
                "head_commit": {"timestamp": "2026-05-21T10:05:00+08:00"},
            }

            first = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                payload=first_payload,
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )["receipt"]
            second = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                payload=second_payload,
                actor_member="frontend-human",
                received_at="2026-05-21T10:05:00+08:00",
            )["receipt"]

            preview = git_activity_correlation_preview(workspace, project="aiteamos", repository="aiteamos", provider="github")
            group = _preview_group_for_receipts(preview, first.object_id, second.object_id)
            self.assertIn("ref:refs/heads/main", group["refs"])
            self.assertEqual(set(group["commits"]), {first.spec.normalized["commit"], second.spec.normalized["commit"]})
            self.assertTrue(group["forcePushRisk"])
            self.assertTrue(group["multiEventRisk"])
            self.assertEqual(group["importedActivities"], [])

    def test_correlation_review_requires_human_or_hybrid_for_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            first = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                payload={
                    "ref": "refs/heads/main",
                    "after": "1111111111111111111111111111111111111111",
                    "repository": {"full_name": "example/aiteamos"},
                    "sender": {"login": "octobot"},
                },
                actor_member="frontend-human",
            )["receipt"]
            second = admit_provider_git_activity_import(
                workspace,
                provider="github",
                repository="aiteamos",
                payload={
                    "ref": "refs/heads/main",
                    "after": "2222222222222222222222222222222222222222",
                    "repository": {"full_name": "example/aiteamos"},
                    "sender": {"login": "octobot"},
                },
                actor_member="frontend-human",
            )["receipt"]
            preview = git_activity_correlation_preview(workspace, project="aiteamos", repository="aiteamos", provider="github")
            group = _preview_group_for_receipts(preview, first.object_id, second.object_id)

            with self.assertRaises(ValueError):
                review_git_activity_correlation(
                    workspace,
                    correlation_key=group["correlationKey"],
                    receipts=[first.object_id, second.object_id],
                    reviewer_member="backend-digital",
                    decision="approved",
                )

    def test_human_review_promotes_receipt_to_git_activity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            workspace = _copy_workspace(temp_root)
            source_repo = _init_repo(temp_root / "source")
            (source_repo / "src.txt").write_text("reviewed git evidence\n", encoding="utf-8")
            _git(source_repo, ["add", "src.txt"])
            _git(source_repo, ["commit", "-m", "reviewed evidence"])
            _point_workspace_repository_at(workspace, source_repo)
            admitted = admit_local_git_activity_import(
                workspace,
                repository="aiteamos",
                actor_member="frontend-human",
                received_at="2026-05-21T10:00:00+08:00",
            )

            promoted = promote_git_activity_import_receipt(
                workspace,
                admitted["receipt"].object_id,
                reviewer_member="frontend-human",
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                activity_type="commit",
                summary="Promoted reviewed local Git metadata.",
            )

            activity = promoted["activities"][0]
            receipt = promoted["receipt"]
            self.assertTrue(promoted["created"])
            self.assertEqual(activity.kind, "GitActivity")
            self.assertEqual(activity.spec.member, "backend-digital")
            self.assertEqual(activity.spec.assignment, "aiteamos-backend-runtime")
            self.assertEqual(activity.spec.activityType, "commit")
            self.assertIn(f"git_activity/imports/{receipt.object_id}.yaml", activity.spec.evidence)
            self.assertEqual(receipt.spec.status, "imported")
            self.assertEqual(receipt.spec.reviewedByMember, "frontend-human")
            self.assertEqual(receipt.spec.importedActivities, [activity.object_id])
            self.assertEqual(receipt.spec.decisionAudit[-1].decisionKind, "human_approval")
            self.assertFalse(receipt.spec.decisionAudit[-1].requiresHumanReview)

            index = load_workspace(workspace)
            self.assertIn(activity.object_id, index.git_activities)
            self.assertEqual(index.git_activity_import_receipts[receipt.object_id].spec.status, "imported")

            duplicate = promote_git_activity_import_receipt(
                workspace,
                receipt.object_id,
                reviewer_member="frontend-human",
                member="backend-digital",
            )
            self.assertFalse(duplicate["created"])
            self.assertTrue(duplicate["alreadyImported"])
            self.assertEqual(duplicate["activities"][0].object_id, activity.object_id)


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _point_workspace_repository_at(workspace: Path, source_repo: Path) -> None:
    path = workspace / "repositories" / "aiteamos.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["spec"]["provider"] = "local"
    data["spec"]["localPath"] = str(source_repo)
    data["spec"]["url"] = f"file://{source_repo}"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _write_git_connector(workspace: Path, *, actor_login: str) -> None:
    connector_path = workspace / "connectors" / "github-import.yaml"
    connector_path.parent.mkdir(parents=True, exist_ok=True)
    actor_hash = hashlib.sha256(actor_login.encode("utf-8")).hexdigest()
    connector_path.write_text(
        yaml.safe_dump(
            {
                "apiVersion": "aiteamos.dev/v1alpha1",
                "kind": "Connector",
                "metadata": {"id": "github-import"},
                "spec": {
                    "provider": "github",
                    "connectorType": "git",
                    "ownerMember": "memory-service",
                    "projects": ["aiteamos"],
                    "config": {
                        "allowedRepositories": ["example/aiteamos"],
                        "allowedInstallationIds": ["12345"],
                    },
                    "gitActivityImport": {
                        "enabled": True,
                        "allowedRepositories": ["example/aiteamos"],
                        "allowedInstallationIds": ["12345"],
                        "protectedRefPatterns": ["refs/heads/release/*"],
                        "actorMappings": [
                            {
                                "actorLoginSha256": actor_hash,
                                "member": "backend-digital",
                                "assignment": "aiteamos-backend-runtime",
                                "policy": "map-to-member",
                            }
                        ],
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _patch_git_activity(workspace: Path, activity_id: str, **spec_updates: object) -> None:
    path = workspace / "git_activity" / f"{activity_id}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("spec", {}).update(spec_updates)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _preview_group_for_receipts(preview: dict[str, object], *receipt_ids: str) -> dict[str, object]:
    receipt_set = set(receipt_ids)
    for group in preview["groups"]:
        if receipt_set.issubset(set(group["receipts"])):
            return group
    raise AssertionError(f"no preview group contains receipts {sorted(receipt_set)}")


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, ["init", "-b", "main"])
    _git(path, ["config", "user.email", "aiteamos@example.invalid"])
    _git(path, ["config", "user.name", "AITEAMOS Import Test"])
    (path / "README.md").write_text("# Import Test\n", encoding="utf-8")
    _git(path, ["add", "README.md"])
    _git(path, ["commit", "-m", "initial"])
    return path


def _git(cwd: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
