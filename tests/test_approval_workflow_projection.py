from __future__ import annotations

from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from aiteamos_workspace import (
    approve_automation_run,
    approve_permission_request,
    create_automation,
    create_permission_request,
    index_workspace,
    load_workspace,
    reject_automation_run,
    reject_permission_request,
    trigger_automation,
)
from aiteamos_workspace.io import write_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class ApprovalWorkflowProjectionTest(unittest.TestCase):
    def test_permission_request_writes_and_updates_linked_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            request = create_permission_request(
                workspace,
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                action={"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"},
                requester_member="manager",
                reason="Need a governed API edit.",
                current_decision={
                    "decision": "ask",
                    "reason": "human approval required",
                    "selectedPolicyIds": ["digital-default"],
                    "matchedRules": [],
                    "matchedGrants": [],
                    "blockers": [],
                    "warnings": [],
                },
                source="approval-workflow-projection-test",
            )
            created_index = load_workspace(workspace)
            workflow_id = request.spec.approvalWorkflow

            self.assertIsNotNone(workflow_id)
            self.assertFalse((workspace / "permission_requests" / f"{request.object_id}.yaml").exists())
            self.assertIn(workflow_id or "", created_index.approval_workflows)
            self.assertIn(request.object_id, created_index.permission_requests)
            created_workflow = created_index.approval_workflows[workflow_id or ""]
            self.assertEqual(created_workflow.spec.subjectKind, "PermissionRequest")
            self.assertEqual(created_workflow.spec.subjectRef, request.object_id)
            self.assertEqual(created_workflow.spec.status, "pending")
            self.assertEqual(created_workflow.spec.currentStage, "permission-review")
            self.assertEqual(created_workflow.spec.stages[0].kind, "any-of")
            self.assertEqual(created_workflow.spec.stages[0].sla.durationSeconds, 86_400)

            approved = approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member="frontend-human",
                reason="Approved for one bounded projection test.",
            )
            approved_index = load_workspace(workspace)
            approved_request = approved_index.permission_requests[request.object_id]
            approved_workflow = approved_index.approval_workflows[workflow_id or ""]

            self.assertEqual(approved_request.spec.status, "approved")
            self.assertEqual(approved_request.spec.approvalWorkflow, workflow_id)
            self.assertEqual(approved_workflow.spec.status, "approved")
            self.assertIsNone(approved_workflow.spec.currentStage)
            self.assertEqual(approved_workflow.spec.stages[0].status, "satisfied")
            self.assertEqual(approved_workflow.spec.stages[0].approvals, [approved["grant"].object_id])

            rejected_request = create_permission_request(
                workspace,
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                action={"tool": "Read", "path": "/.aiteamos/project.yaml"},
                requester_member="manager",
                reason="Exercise rejection workflow.",
                source="approval-workflow-projection-test",
            )
            rejected = reject_permission_request(
                workspace,
                rejected_request.object_id,
                reviewer_member="frontend-human",
                reason="Rejected for projection coverage.",
            )
            rejected_index = load_workspace(workspace)
            rejected_workflow = rejected_index.approval_workflows[rejected.spec.approvalWorkflow or ""]
            self.assertEqual(rejected.spec.status, "rejected")
            self.assertEqual(rejected_workflow.spec.status, "rejected")
            self.assertEqual(rejected_workflow.spec.stages[0].status, "rejected")

            db_path = Path(temp_dir) / "derived.sqlite"
            index_workspace(workspace, db_path=db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                permission_row = conn.execute(
                    "select approval_workflow_id from permission_requests where id = ?",
                    (request.object_id,),
                ).fetchone()
                workflow_row = conn.execute(
                    "select subject_kind, subject_ref, status from approval_workflows where id = ?",
                    (workflow_id,),
                ).fetchone()
            self.assertEqual(permission_row, (workflow_id,))
            self.assertEqual(workflow_row, ("PermissionRequest", request.object_id, "approved"))

    def test_automation_approval_writes_linked_workflow_for_approve_and_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))
            _write_executor_policy(workspace)
            create_automation(
                workspace,
                name="workflow-approved-reminder",
                target_type="human_reminder",
                target={"toMembers": ["frontend-human"], "body": "ApprovalWorkflow projection approved path."},
                owner_member="manager",
                service_member="memory-service",
                project="aiteamos",
                dry_run=False,
                permission_policies=["service-automation-executor-test"],
                approval_gates=["human-approval"],
            )

            pending = trigger_automation(workspace, "workflow-approved-reminder", actor_member="manager")
            queued = approve_automation_run(
                workspace,
                pending.object_id,
                reviewer_member="frontend-human",
                reason="Approved workflow projection.",
            )
            approved_index = load_workspace(workspace)
            approval_id = queued.spec.approvals[0]
            approval = approved_index.automation_approvals[approval_id]
            workflow = approved_index.approval_workflows[approval.spec.approvalWorkflow or ""]

            self.assertFalse((workspace / "automations" / "approvals" / f"{approval_id}.yaml").exists())
            self.assertEqual(approval.spec.decision, "approved")
            self.assertEqual(workflow.spec.subjectKind, "AutomationApproval")
            self.assertEqual(workflow.spec.subjectRef, approval_id)
            self.assertEqual(workflow.spec.status, "approved")
            self.assertEqual(workflow.spec.stages[0].kind, "every-of")
            self.assertEqual(workflow.spec.stages[0].status, "satisfied")
            self.assertEqual(workflow.spec.stages[0].approvals, [approval_id])

            create_automation(
                workspace,
                name="workflow-rejected-reminder",
                target_type="human_reminder",
                target={"toMembers": ["frontend-human"], "body": "ApprovalWorkflow projection rejected path."},
                owner_member="manager",
                service_member="memory-service",
                project="aiteamos",
                dry_run=False,
                permission_policies=["service-automation-executor-test"],
                approval_gates=["human-approval"],
            )
            pending_rejection = trigger_automation(workspace, "workflow-rejected-reminder", actor_member="manager")
            blocked = reject_automation_run(
                workspace,
                pending_rejection.object_id,
                reviewer_member="frontend-human",
                reason="Rejected workflow projection.",
            )
            rejected_index = load_workspace(workspace)
            rejected_approval = rejected_index.automation_approvals[blocked.spec.approvals[0]]
            rejected_workflow = rejected_index.approval_workflows[rejected_approval.spec.approvalWorkflow or ""]

            self.assertEqual(rejected_approval.spec.decision, "rejected")
            self.assertEqual(rejected_workflow.spec.status, "rejected")
            self.assertEqual(rejected_workflow.spec.stages[0].status, "rejected")

            db_path = Path(temp_dir) / "derived.sqlite"
            index_workspace(workspace, db_path=db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                approval_row = conn.execute(
                    "select approval_workflow_id from automation_approvals where id = ?",
                    (approval_id,),
                ).fetchone()
                workflow_row = conn.execute(
                    "select subject_kind, subject_ref, status from approval_workflows where id = ?",
                    (approval.spec.approvalWorkflow,),
                ).fetchone()
            self.assertEqual(approval_row, (approval.spec.approvalWorkflow,))
            self.assertEqual(workflow_row, ("AutomationApproval", approval_id, "approved"))


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
                    {"match": "Edit(/.aiteamos/im/messages/**)"},
                ],
            },
        },
    )
