from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from tests.inline_testclient import TestClient

from aiteamos_api import create_app
from aiteamos_workspace import (
    approve_permission_request,
    create_permission_request,
    explain_effective_permissions,
    expire_permission_grants,
    load_workspace,
    permission_governance_overview,
    revoke_permission_grant,
    reject_permission_request,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MEMBER = "backend-digital"
BACKEND_ASSIGNMENT = "aiteamos-backend-runtime"
HUMAN_REVIEWER = "frontend-human"
FUTURE_EXPIRY = "2099-01-01T00:00:00+00:00"
PAST_EXPIRY = "2000-01-01T00:00:00+00:00"


class PermissionRequestTest(unittest.TestCase):
    def test_human_approval_creates_expiring_grant_for_ask_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            action = {"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"}
            index = load_workspace(workspace)

            before = explain_effective_permissions(
                index,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=action,
                non_interactive=True,
            )
            self.assertEqual(before["decision"], "deny")
            self.assertIn("non-interactive", before["reason"])

            request = create_permission_request(
                workspace,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=action,
                requester_member=BACKEND_MEMBER,
                reason="Need to patch the API handler.",
                current_decision=before,
            )
            result = approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member=HUMAN_REVIEWER,
                reason="Approved for one bounded backend edit.",
                expires_at=FUTURE_EXPIRY,
            )
            grant = result["grant"]

            updated = load_workspace(workspace)
            self.assertIn(request.object_id, updated.permission_requests)
            self.assertIn(grant.object_id, updated.permission_grants)
            approved_request = updated.permission_requests[request.object_id]
            self.assertEqual(approved_request.spec.status, "approved")
            self.assertEqual(approved_request.spec.grant, grant.object_id)
            self.assertEqual(approved_request.spec.decisionAudit[0].decisionKind, "service_policy_decision")
            self.assertEqual(approved_request.spec.decisionAudit[0].riskAssessment.riskLevel, "medium")
            self.assertEqual(approved_request.spec.decisionAudit[-1].decisionKind, "human_approval")
            self.assertEqual(approved_request.spec.decisionAudit[-1].actorMember, HUMAN_REVIEWER)
            self.assertEqual(approved_request.spec.decisionAudit[-1].actorMemberKind, "human")
            self.assertEqual(updated.permission_grants[grant.object_id].spec.decisionAudit[0].decisionKind, "human_approval")
            self.assertEqual(updated.permission_grants[grant.object_id].spec.decisionAudit[0].decision, "allowed")
            self.assertEqual(updated.permission_grants[grant.object_id].spec.decisionAudit[0].riskAssessment.riskLevel, "medium")

            after = explain_effective_permissions(
                updated,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=action,
                non_interactive=True,
            )
            self.assertEqual(after["decision"], "allow")
            self.assertEqual(after["reason"], "active permission grant matched")
            self.assertEqual(after["matchedGrants"][0]["grant"], grant.object_id)

    def test_explicit_deny_still_wins_over_approved_grant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            action = {"tool": "Edit", "path": "/.git/config"}
            request = create_permission_request(
                workspace,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=action,
                requester_member=BACKEND_MEMBER,
                reason="Attempt to test deny precedence.",
            )
            approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member=HUMAN_REVIEWER,
                expires_at=FUTURE_EXPIRY,
            )

            after = explain_effective_permissions(
                load_workspace(workspace),
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=action,
                non_interactive=True,
            )
            self.assertEqual(after["decision"], "deny")
            self.assertEqual(after["matchedRules"][0]["decision"], "deny")
            self.assertEqual(after["matchedRules"][0]["rule"], "Edit(/.git/**)")

    def test_api_create_and_approve_permission_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))
            action = {"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"}

            create_response = client.post(
                "/permission-requests",
                json={
                    "member": BACKEND_MEMBER,
                    "assignment": BACKEND_ASSIGNMENT,
                    "action": action,
                    "requesterMember": BACKEND_MEMBER,
                    "reason": "Need dashboard-approved API edit.",
                },
            )
            self.assertEqual(create_response.status_code, 200)
            request = create_response.json()
            self.assertEqual(request["spec"]["status"], "pending")
            self.assertEqual(request["spec"]["currentDecision"]["decision"], "deny")

            approve_response = client.post(
                f"/permission-requests/{request['id']}/approve",
                json={
                    "reviewerMember": HUMAN_REVIEWER,
                    "expiresAt": FUTURE_EXPIRY,
                    "reason": "Approved through API.",
                },
            )
            self.assertEqual(approve_response.status_code, 200)
            grant_id = approve_response.json()["grant"]["id"]

            grants_response = client.get("/permission-grants")
            self.assertEqual(grants_response.status_code, 200)
            self.assertIn(grant_id, {item["id"] for item in grants_response.json()})

            explain_response = client.get(
                "/permissions/effective",
                params={
                    "member": BACKEND_MEMBER,
                    "assignment": BACKEND_ASSIGNMENT,
                    "tool": "Edit",
                    "path": "/services/api/aiteamos_api/app.py",
                    "nonInteractive": True,
                },
            )
            self.assertEqual(explain_response.status_code, 200)
            self.assertEqual(explain_response.json()["decision"], "allow")
            self.assertEqual(explain_response.json()["matchedGrants"][0]["grant"], grant_id)

    def test_revoke_grant_removes_permission_allow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            action = {"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"}
            request = create_permission_request(
                workspace,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=action,
                requester_member=BACKEND_MEMBER,
            )
            grant = approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member=HUMAN_REVIEWER,
                expires_at=FUTURE_EXPIRY,
            )["grant"]

            self.assertEqual(
                explain_effective_permissions(
                    load_workspace(workspace),
                    member=BACKEND_MEMBER,
                    assignment=BACKEND_ASSIGNMENT,
                    action=action,
                    non_interactive=True,
                )["decision"],
                "allow",
            )

            revoked = revoke_permission_grant(
                workspace,
                grant.object_id,
                actor_member=HUMAN_REVIEWER,
                reason="No longer needed.",
            )
            self.assertEqual(revoked.spec.status, "revoked")
            after = explain_effective_permissions(
                load_workspace(workspace),
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action=action,
                non_interactive=True,
            )
            self.assertEqual(after["decision"], "deny")
            self.assertEqual(after["matchedGrants"], [])

    def test_expire_grants_persists_status_and_overview_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            request = create_permission_request(
                workspace,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action={"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"},
                requester_member=BACKEND_MEMBER,
            )
            grant = approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member=HUMAN_REVIEWER,
                expires_at=PAST_EXPIRY,
            )["grant"]

            result = expire_permission_grants(workspace)
            self.assertEqual(result["expired"], [grant.object_id])
            index = load_workspace(workspace)
            self.assertEqual(index.permission_grants[grant.object_id].spec.status, "expired")

            overview = permission_governance_overview(index)
            self.assertEqual(overview["summary"]["expiredGrants"], 1)
            self.assertEqual(overview["expiredGrants"][0]["id"], grant.object_id)
            member_row = next(row for row in overview["byMember"] if row["member"] == BACKEND_MEMBER)
            self.assertGreaterEqual(member_row["requestCount"], 1)
            self.assertGreaterEqual(member_row["grantCount"], 1)

    def test_api_revoke_and_expire_permission_grants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))
            request = create_permission_request(
                workspace,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action={"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"},
                requester_member=BACKEND_MEMBER,
            )
            grant = approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member=HUMAN_REVIEWER,
                expires_at=FUTURE_EXPIRY,
            )["grant"]

            overview_response = client.get("/permissions/overview")
            self.assertEqual(overview_response.status_code, 200)
            self.assertGreaterEqual(overview_response.json()["summary"]["activeGrants"], 1)

            revoke_response = client.post(
                f"/permission-grants/{grant.object_id}/revoke",
                json={"actorMember": HUMAN_REVIEWER, "reason": "API revocation test."},
            )
            self.assertEqual(revoke_response.status_code, 200)
            self.assertEqual(revoke_response.json()["spec"]["status"], "revoked")

            expire_response = client.post("/permission-grants/expire")
            self.assertEqual(expire_response.status_code, 200)
            self.assertIn("expiredCount", expire_response.json())

    def test_api_permission_projections_redact_sensitive_details_without_authorized_viewer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))
            request = create_permission_request(
                workspace,
                member="architect",
                assignment="aiteamos-architecture",
                action={"tool": "EnvVar", "envVar": "CUSTOMER_X_TOKEN", "operation": "read"},
                requester_member="architect",
                reason="Need to inspect a customer token during incident response.",
                name="PREQ-sensitive-projection",
            )
            approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member=HUMAN_REVIEWER,
                expires_at=FUTURE_EXPIRY,
            )

            policies_response = client.get("/permissions")
            self.assertEqual(policies_response.status_code, 200)
            self.assertIn('"redacted":true', policies_response.text.replace(" ", ""))
            self.assertNotIn("OPENAI_API_KEY", policies_response.text)
            self.assertNotIn(".env", policies_response.text)

            viewer_policies_response = client.get("/permissions", params={"viewerMember": "architect"})
            self.assertEqual(viewer_policies_response.status_code, 200)
            self.assertIn("OPENAI_API_KEY", viewer_policies_response.text)

            request_response = client.get("/permission-requests")
            self.assertEqual(request_response.status_code, 200)
            self.assertIn(request.object_id, request_response.text)
            self.assertIn('"redacted":true', request_response.text.replace(" ", ""))
            self.assertNotIn("CUSTOMER_X_TOKEN", request_response.text)
            self.assertNotIn("incident response", request_response.text)

            grant_response = client.get("/permission-grants", params={"viewerMember": "memory-service"})
            self.assertEqual(grant_response.status_code, 200)
            self.assertIn('"redacted":true', grant_response.text.replace(" ", ""))
            self.assertNotIn("CUSTOMER_X_TOKEN", grant_response.text)

            overview_response = client.get("/permissions/overview")
            self.assertEqual(overview_response.status_code, 200)
            self.assertIn(request.object_id, overview_response.text)
            self.assertIn('"redacted":true', overview_response.text.replace(" ", ""))
            self.assertNotIn("CUSTOMER_X_TOKEN", overview_response.text)

            architect_response = client.get("/permission-requests", params={"viewerMember": "architect"})
            self.assertEqual(architect_response.status_code, 200)
            self.assertIn("CUSTOMER_X_TOKEN", architect_response.text)
            self.assertIn("incident response", architect_response.text)

    def test_api_reject_permission_request_does_not_create_grant(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            client = TestClient(create_app(workspace))
            create_response = client.post(
                "/permission-requests",
                json={
                    "member": BACKEND_MEMBER,
                    "assignment": BACKEND_ASSIGNMENT,
                    "action": {"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"},
                    "requesterMember": BACKEND_MEMBER,
                    "reason": "Rejected permission request test.",
                    "name": "PREQ-reject-test",
                },
            )
            self.assertEqual(create_response.status_code, 200)
            request_id = create_response.json()["id"]

            reject_response = client.post(
                f"/permission-requests/{request_id}/reject",
                json={"reviewerMember": HUMAN_REVIEWER, "reason": "Keep backend edits blocked."},
            )
            self.assertEqual(reject_response.status_code, 200)
            self.assertEqual(reject_response.json()["spec"]["status"], "rejected")
            self.assertEqual(reject_response.json()["spec"]["decisionAudit"][-1]["decisionKind"], "human_approval")
            self.assertEqual(reject_response.json()["spec"]["decisionAudit"][-1]["decision"], "rejected")

            grants_response = client.get("/permission-grants")
            self.assertEqual(grants_response.status_code, 200)
            self.assertFalse(any(item["spec"].get("sourceRequest") == request_id for item in grants_response.json()))

    def test_permissions_overview_supports_member_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_scoped_architect_policy(workspace)
            client = TestClient(create_app(workspace))
            request = create_permission_request(
                workspace,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action={"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"},
                requester_member=BACKEND_MEMBER,
                name="PREQ-scoped-overview",
            )
            approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member=HUMAN_REVIEWER,
                expires_at=FUTURE_EXPIRY,
            )

            backend_response = client.get("/permissions/overview", params={"member": BACKEND_MEMBER})
            self.assertEqual(backend_response.status_code, 200)
            backend_overview = backend_response.json()
            self.assertEqual(backend_overview["scope"]["member"], BACKEND_MEMBER)
            self.assertIn(request.object_id, {item["id"] for item in backend_overview["requests"]})
            backend_policy_ids = {item["id"] for item in backend_overview["policies"]}
            self.assertIn("digital-default", backend_policy_ids)
            self.assertNotIn("architect-private-policy", backend_policy_ids)
            self.assertEqual(backend_overview["byMember"], [{"id": BACKEND_MEMBER, "kind": "PermissionProjection", "member": BACKEND_MEMBER, "requestCount": 1, "grantCount": 1}])

            backend_detail_response = client.get(f"/members/{BACKEND_MEMBER}/permissions")
            self.assertEqual(backend_detail_response.status_code, 200)
            backend_detail = backend_detail_response.json()
            self.assertEqual(backend_detail["scope"]["member"], BACKEND_MEMBER)
            self.assertIn(request.object_id, {item["id"] for item in backend_detail["requests"]})
            self.assertNotIn("architect-private-policy", {item["id"] for item in backend_detail["policies"]})

            project_response = client.get("/permissions/overview", params={"project": "aiteamos"})
            self.assertEqual(project_response.status_code, 200)
            self.assertIn(request.object_id, {item["id"] for item in project_response.json()["requests"]})

            project_detail_response = client.get("/projects/aiteamos/permissions")
            self.assertEqual(project_detail_response.status_code, 200)
            project_detail = project_detail_response.json()
            self.assertEqual(project_detail["scope"]["project"], "aiteamos")
            self.assertIn(request.object_id, {item["id"] for item in project_detail["requests"]})

            assignment_response = client.get("/permissions/overview", params={"assignment": BACKEND_ASSIGNMENT})
            self.assertEqual(assignment_response.status_code, 200)
            self.assertEqual(assignment_response.json()["scope"]["assignment"], BACKEND_ASSIGNMENT)
            self.assertIn(request.object_id, {item["id"] for item in assignment_response.json()["requests"]})

            assignment_detail_response = client.get(f"/assignments/{BACKEND_ASSIGNMENT}/permissions")
            self.assertEqual(assignment_detail_response.status_code, 200)
            assignment_detail = assignment_detail_response.json()
            self.assertEqual(assignment_detail["scope"]["assignment"], BACKEND_ASSIGNMENT)
            self.assertIn(request.object_id, {item["id"] for item in assignment_detail["requests"]})
            self.assertNotIn("architect-private-policy", {item["id"] for item in assignment_detail["policies"]})

            human_response = client.get("/permissions/overview", params={"member": HUMAN_REVIEWER})
            self.assertEqual(human_response.status_code, 200)
            human_overview = human_response.json()
            self.assertEqual(human_overview["scope"]["member"], HUMAN_REVIEWER)
            self.assertNotIn(request.object_id, {item["id"] for item in human_overview["requests"]})
            self.assertNotIn("architect-private-policy", {item["id"] for item in human_overview["policies"]})
            self.assertEqual(human_overview["summary"]["requests"], 0)

            architect_response = client.get("/members/architect/permissions")
            self.assertEqual(architect_response.status_code, 200)
            self.assertIn("architect-private-policy", {item["id"] for item in architect_response.json()["policies"]})
            self.assertNotIn("CUSTOMER_SCOPED_TOKEN", architect_response.text)

            authorized_architect_response = client.get("/members/architect/permissions", params={"viewerMember": "architect"})
            self.assertEqual(authorized_architect_response.status_code, 200)
            self.assertIn("architect-private-policy", {item["id"] for item in authorized_architect_response.json()["policies"]})
            self.assertIn("CUSTOMER_SCOPED_TOKEN", authorized_architect_response.text)

            architect_assignment_response = client.get("/assignments/aiteamos-architecture/permissions", params={"viewerMember": "architect"})
            self.assertEqual(architect_assignment_response.status_code, 200)
            self.assertEqual(architect_assignment_response.json()["scope"]["assignment"], "aiteamos-architecture")
            self.assertIn("architect-private-policy", {item["id"] for item in architect_assignment_response.json()["policies"]})
            self.assertIn("CUSTOMER_SCOPED_TOKEN", architect_assignment_response.text)

    def test_non_human_member_cannot_formally_decide_permission_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            request = create_permission_request(
                workspace,
                member=BACKEND_MEMBER,
                assignment=BACKEND_ASSIGNMENT,
                action={"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"},
                requester_member=BACKEND_MEMBER,
            )

            with self.assertRaises(ValueError):
                approve_permission_request(
                    workspace,
                    request.object_id,
                    reviewer_member=BACKEND_MEMBER,
                    expires_at=FUTURE_EXPIRY,
                )

            with self.assertRaises(ValueError):
                reject_permission_request(
                    workspace,
                    request.object_id,
                    reviewer_member=BACKEND_MEMBER,
                    reason="Digital reviewers can recommend but not formally decide permission requests.",
                )


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace


def _write_scoped_architect_policy(workspace: Path) -> None:
    (workspace / "permissions" / "architect-private-policy.yaml").write_text(
        """apiVersion: aiteamos.dev/v1alpha1
kind: PermissionPolicy
metadata:
  name: architect-private-policy
spec:
  scope:
    member: architect
  defaultMode: ask
  allow:
  - match: EnvVar(CUSTOMER_SCOPED_TOKEN:use)
  deny:
  - match: EnvVar(CUSTOMER_SCOPED_TOKEN:read)
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
