from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from aiteamos_workspace import approve_permission_request, create_permission_request, load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]


class ApprovalWorkflowRiskRoutingTest(unittest.TestCase):
    def test_high_risk_permission_request_routes_to_quorum_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            request = create_permission_request(
                workspace,
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                action={"tool": "ExportWorkspace", "redaction": "include"},
                requester_member="manager",
                reason="Exercise high-risk approval workflow routing.",
                current_decision={
                    "decision": "ask",
                    "reason": "high-risk export requires review",
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
                source="approval-workflow-risk-routing-test",
            )
            index = load_workspace(workspace)
            workflow = index.approval_workflows[request.spec.approvalWorkflow or ""]
            stage = workflow.spec.stages[0]

            self.assertEqual(workflow.spec.currentStage, "risk-quorum")
            self.assertEqual(stage.id, "risk-quorum")
            self.assertEqual(stage.kind, "quorum")
            self.assertEqual(stage.quorum, 2)
            self.assertEqual(stage.reviewerKinds, ["human", "hybrid"])
            self.assertEqual(workflow.spec.audit["riskRouting"]["riskLevel"], "high")
            self.assertEqual(workflow.spec.audit["riskRouting"]["recommendedDecision"], "ask")

            approved = approve_permission_request(
                workspace,
                request.object_id,
                reviewer_member="frontend-human",
                reason="Approval remains callable while preserving risk routing evidence.",
            )
            approved_index = load_workspace(workspace)
            approved_workflow = approved_index.approval_workflows[request.spec.approvalWorkflow or ""]
            approved_stage = approved_workflow.spec.stages[0]

            self.assertEqual(approved["request"].spec.status, "approved")
            self.assertEqual(approved_workflow.spec.status, "approved")
            self.assertEqual(approved_stage.kind, "quorum")
            self.assertEqual(approved_stage.quorum, 2)
            self.assertEqual(approved_stage.status, "satisfied")

    def test_medium_risk_permission_request_keeps_default_any_of_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = _copy_workspace(Path(temp_dir))

            request = create_permission_request(
                workspace,
                member="backend-digital",
                assignment="aiteamos-backend-runtime",
                action={"tool": "Edit", "path": "/services/api/aiteamos_api/app.py"},
                requester_member="manager",
                reason="Exercise medium-risk default workflow routing.",
                current_decision={
                    "decision": "ask",
                    "reason": "medium-risk edit requires review",
                    "selectedPolicyIds": ["digital-default"],
                    "matchedRules": [],
                    "matchedGrants": [],
                    "blockers": [],
                    "warnings": [],
                    "riskAssessment": {
                        "riskLevel": "medium",
                        "recommendedDecision": "ask",
                        "requiresHumanReview": True,
                    },
                },
                source="approval-workflow-risk-routing-test",
            )
            workflow = load_workspace(workspace).approval_workflows[request.spec.approvalWorkflow or ""]
            stage = workflow.spec.stages[0]

            self.assertEqual(workflow.spec.currentStage, "permission-review")
            self.assertEqual(stage.kind, "any-of")
            self.assertIsNone(stage.quorum)
            self.assertNotIn("riskRouting", workflow.spec.audit)


def _copy_workspace(temp_root: Path) -> Path:
    workspace = temp_root / ".aiteamos"
    shutil.copytree(
        REPO_ROOT / ".aiteamos",
        workspace,
        ignore=shutil.ignore_patterns("__pycache__", "indexes", "artifacts/blob", "artifacts/cache", "artifacts/worktrees"),
    )
    return workspace
