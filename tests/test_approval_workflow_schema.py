from __future__ import annotations

from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from pydantic import ValidationError
import yaml

from aiteamos_schema import ApprovalWorkflow, build_json_schema_bundle, build_openapi_schema, build_typescript_types
from aiteamos_workspace.indexer import index_workspace
from aiteamos_workspace.loader import load_workspace


REPO_ROOT = Path(__file__).resolve().parents[1]


class ApprovalWorkflowSchemaTest(unittest.TestCase):
    def test_approval_workflow_models_stage_sla_and_escalation(self) -> None:
        workflow = ApprovalWorkflow.model_validate(_approval_workflow_payload("AWF-schema-contract"))

        self.assertEqual(workflow.kind, "ApprovalWorkflow")
        self.assertEqual(workflow.spec.currentStage, "risk-quorum")
        self.assertEqual(workflow.spec.stages[0].kind, "quorum")
        self.assertEqual(workflow.spec.stages[0].quorum, 2)
        self.assertEqual(workflow.spec.stages[0].sla.durationSeconds, 1800)
        self.assertEqual(workflow.spec.stages[0].escalation.targetMember, "aiteamos-manager")

    def test_quorum_stage_requires_valid_quorum(self) -> None:
        payload = _approval_workflow_payload("AWF-invalid-quorum")
        payload["spec"]["stages"][0].pop("quorum")
        with self.assertRaisesRegex(ValidationError, "quorum approval stages require quorum"):
            ApprovalWorkflow.model_validate(payload)

        payload = _approval_workflow_payload("AWF-invalid-quorum-size")
        payload["spec"]["stages"][0]["quorum"] = 3
        with self.assertRaisesRegex(ValidationError, "cannot require more approvals"):
            ApprovalWorkflow.model_validate(payload)

        payload = _approval_workflow_payload("AWF-invalid-non-quorum")
        payload["spec"]["stages"][0]["kind"] = "every-of"
        with self.assertRaisesRegex(ValidationError, "only quorum approval stages may set quorum"):
            ApprovalWorkflow.model_validate(payload)

    def test_schema_exports_include_approval_workflow_contracts(self) -> None:
        bundle = build_json_schema_bundle()
        openapi = build_openapi_schema()
        typescript = build_typescript_types()

        for schema_name in (
            "ApprovalWorkflow",
            "ApprovalWorkflowSpec",
            "ApprovalWorkflowStage",
            "ApprovalWorkflowSLA",
            "ApprovalWorkflowEscalation",
        ):
            self.assertIn(schema_name, bundle["$defs"])
            self.assertIn(schema_name, openapi["components"]["schemas"])
            self.assertIn(f"export type {schema_name}", typescript)

    def test_workspace_loader_and_indexer_accept_approval_workflows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / ".aiteamos"
            shutil.copytree(REPO_ROOT / ".aiteamos", workspace, ignore=shutil.ignore_patterns("__pycache__", "indexes"))
            workflow_path = workspace / "approval_workflows" / "AWF-loader-contract.yaml"
            workflow_path.parent.mkdir(parents=True, exist_ok=True)
            workflow_path.write_text(
                yaml.safe_dump(_approval_workflow_payload("AWF-loader-contract"), sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )

            index = load_workspace(workspace)
            self.assertIn("AWF-loader-contract", index.approval_workflows)
            self.assertIn("PREQ-schema-contract", index.permission_requests)
            self.assertEqual(index.health, [])
            self.assertEqual(index.to_summary()["counts"]["approvalWorkflows"], 1)

            db_path = Path(temp_dir) / "derived.sqlite"
            index_workspace(workspace, db_path=db_path)
            with closing(sqlite3.connect(db_path)) as conn:
                row = conn.execute("select subject_kind, status from approval_workflows where id = ?", ("AWF-loader-contract",)).fetchone()
            self.assertEqual(row, ("PermissionRequest", "pending"))


def _approval_workflow_payload(workflow_id: str) -> dict[str, object]:
    return {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "ApprovalWorkflow",
        "metadata": {"id": workflow_id, "title": "Approval workflow schema contract"},
        "spec": {
            "project": "aiteamos",
            "subjectKind": "PermissionRequest",
            "subjectRef": "PREQ-schema-contract",
            "requesterMember": "backend-digital",
            "ownerMember": "frontend-human",
            "status": "pending",
            "currentStage": "risk-quorum",
            "stages": [
                {
                    "id": "risk-quorum",
                    "kind": "quorum",
                    "reviewerMembers": ["frontend-human", "architect"],
                    "quorum": 2,
                    "sla": {
                        "durationSeconds": 1800,
                        "startsAt": "stage-entered",
                        "warningAfterSeconds": 900,
                    },
                    "escalation": {
                        "targetMember": "aiteamos-manager",
                        "afterSlaBreach": True,
                        "reason": "Escalate stale high-risk approval workflow.",
                    },
                }
            ],
            "decisionAudit": [
                {
                    "source": "approval-workflow-schema-test",
                    "decisionKind": "system_check",
                    "actorMember": "aiteamos-manager",
                    "actorMemberKind": "human",
                    "authority": "record",
                    "decision": "schema-created",
                    "decidedAt": "2026-05-23T06:44:41+08:00",
                    "reason": "Exercise DG-11.1 ApprovalWorkflow contract.",
                }
            ],
            "audit": {
                "subjectRecord": _permission_request_payload("PREQ-schema-contract", workflow_id),
            },
        },
    }


def _permission_request_payload(request_id: str, workflow_id: str) -> dict[str, object]:
    return {
        "apiVersion": "aiteamos.dev/v1alpha1",
        "kind": "PermissionRequest",
        "metadata": {"id": request_id, "title": "Permission request workflow schema contract"},
        "spec": {
            "project": "aiteamos",
            "member": "backend-digital",
            "approvalWorkflow": workflow_id,
            "requesterMember": "backend-digital",
            "action": {"tool": "Read", "path": "/README.md"},
            "reason": "Exercise ApprovalWorkflow loader link validation.",
            "status": "pending",
            "currentDecision": {"decision": "ask"},
            "source": "approval-workflow-schema-test",
        },
    }


if __name__ == "__main__":
    unittest.main()
