from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import shutil
import tempfile
import unittest

from aiteamos_workspace import (
    approve_permission_request,
    create_permission_request,
    escalate_overdue_approval_workflows,
    load_workspace,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class ApprovalWorkflowSlaEscalationTest(unittest.TestCase):
    def test_high_risk_permission_request_escalates_to_manager_after_sla(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            request = create_permission_request(
                workspace,
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                action={"tool": "ExportWorkspace", "redaction": "include"},
                requester_member="manager",
                reason="Exercise SLA escalation for a high-risk approval workflow.",
                current_decision={
                    "decision": "ask",
                    "reason": "high-risk export requires quorum review",
                    "selectedPolicyIds": ["digital-default"],
                    "matchedRules": [],
                    "matchedGrants": [],
                    "blockers": [],
                    "warnings": [],
                    "riskAssessment": {
                        "riskLevel": "high",
                        "recommendedDecision": "ask",
                        "requiresHumanReview": True,
                        "summary": "Unredacted export needs quorum review.",
                    },
                },
                source="approval-workflow-sla-escalation-test",
            )
            created_index = load_workspace(workspace)
            workflow = created_index.approval_workflows[request.spec.approvalWorkflow or ""]
            stage = workflow.spec.stages[0]

            self.assertEqual(workflow.spec.currentStage, "risk-quorum")
            self.assertEqual(stage.kind, "quorum")
            self.assertEqual(stage.quorum, 2)
            self.assertIsNotNone(stage.escalation)
            self.assertEqual(stage.escalation.targetMember, "manager")

            created_at = datetime.fromisoformat(workflow.spec.createdAt or workflow.metadata.createdAt or "")
            future = (created_at + timedelta(days=2)).isoformat(timespec="milliseconds")
            escalations = escalate_overdue_approval_workflows(
                workspace,
                now=future,
                actor_member="memory-service",
            )
            escalated_index = load_workspace(workspace)
            escalated_workflow = escalated_index.approval_workflows[workflow.object_id]
            escalated_stage = escalated_workflow.spec.stages[0]
            review_messages = [
                message
                for message in escalated_index.member_messages.values()
                if message.spec.audit.get("approvalWorkflow") == workflow.object_id
            ]

            self.assertEqual(len(escalations), 1)
            self.assertTrue(escalations[0]["createdMessage"])
            self.assertEqual(escalated_workflow.spec.status, "escalated")
            self.assertEqual(escalated_stage.status, "escalated")
            self.assertEqual(escalated_workflow.spec.audit["slaEscalation"]["targetMember"], "manager")
            self.assertEqual(len(review_messages), 1)
            self.assertEqual(review_messages[0].spec.messageType, "review-request")
            self.assertEqual(review_messages[0].spec.fromMember, "memory-service")
            self.assertEqual(review_messages[0].spec.toMembers, ["manager"])
            self.assertEqual(
                review_messages[0].spec.audit["approvalWorkflowEscalationDedupeKey"],
                f"approval-workflow:{workflow.object_id}:risk-quorum:sla",
            )
            self.assertEqual(escalated_workflow.spec.decisionAudit[-1].decisionKind, "system_check")
            self.assertEqual(escalated_workflow.spec.decisionAudit[-1].decision, "escalated")

            duplicate = escalate_overdue_approval_workflows(
                workspace,
                now=future,
                actor_member="memory-service",
            )
            duplicate_index = load_workspace(workspace)
            duplicate_messages = [
                message
                for message in duplicate_index.member_messages.values()
                if message.spec.audit.get("approvalWorkflow") == workflow.object_id
            ]

            self.assertEqual(duplicate, [])
            self.assertEqual(len(duplicate_messages), 1)

            approved = approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member="frontend-human",
                reason="PermissionRequest approval remains callable after SLA escalation.",
            )
            approved_index = load_workspace(workspace)
            approved_workflow = approved_index.approval_workflows[workflow.object_id]

            self.assertEqual(approved["request"].spec.status, "approved")
            self.assertEqual(approved_workflow.spec.status, "approved")
            self.assertEqual(approved_workflow.spec.stages[0].status, "satisfied")


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace
