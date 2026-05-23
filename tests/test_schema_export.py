from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from pydantic import ValidationError

from aiteamos_schema import (
    API_VERSION,
    Artifact,
    ArtifactStore,
    AutomationProviderDelivery,
    BudgetPolicy,
    ConnectorHealthCheck,
    CostAlertCandidateRecord,
    CostAlertOverviewRecord,
    CostAlertRouteInput,
    ContextCapsuleInventoryRecord,
    ContextManifest,
    DecisionAuditRecord,
    EvalCase,
    EvalCaseResult,
    EvalJudge,
    EvalResult,
    EvalSuite,
    EvalSuitePolicy,
    EvalSuiteRequirement,
    EvalSuiteRequirementStatus,
    GitActivity,
    GitActivityCorrelationReview,
    GitActivityImportReceipt,
    KnowledgeHealthRecord,
    KnowledgeHealthRemediationInput,
    KnowledgeHealthRemediationRecord,
    LearningExtraction,
    MemoryBinding,
    MemoryEntry,
    MemoryEntryCreateInput,
    MemoryGrant,
    MemoryEvalEvidenceRef,
    MemoryProposal,
    MemoryStore,
    MemoryStoreCreateInput,
    MemberGrowthRecordInput,
    RunCloseoutGateRecord,
    RunCloseoutInput,
    RunReviewGateRecord,
    RunProviderSourceIntegrationInput,
    RunProviderSourceIntegrationExecuteInput,
    RunProviderSourceIntegrationExecutionRecord,
    RunProviderSourceIntegrationRecord,
    RunSourceIntegrationGateRecord,
    RunSourceIntegrationInput,
    RunSourceIntegrationRemediationInput,
    RunSourceIntegrationRemediationRecord,
    ModelCostRow,
    ModelCostSummaryRecord,
    ModelProfile,
    PermissionAction,
    Assignment,
    ProductUser,
    RiskAssessment,
    RiskSignal,
    RunAssistanceBundleRecord,
    RunAssistancePackageRecord,
    TeamMember,
    TaskExecutionQueueRecord,
    WorkspaceActionBoardRecord,
    WorkspaceCatalogRecord,
    TaskPlan,
    build_aiteamos_bundle_schema,
    build_json_schema_bundle,
    build_openapi_schema,
    build_typescript_types,
    export_schema_files,
)
from tools.cli.aiteamos import main as cli_main


class SchemaExportTest(unittest.TestCase):
    def test_json_schema_bundle_is_generated_from_manifest_models(self) -> None:
        bundle = build_json_schema_bundle()

        self.assertEqual(bundle["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(bundle["x-aiteamos-api-version"], API_VERSION)
        self.assertIn({"$ref": "#/$defs/Task"}, bundle["oneOf"])
        self.assertIn({"$ref": "#/$defs/Run"}, bundle["oneOf"])

        defs = bundle["$defs"]
        for name in [
            "Task",
            "TaskSpec",
            "TaskPlan",
            "TaskPlanSpec",
            "EvalSuite",
            "EvalCase",
            "EvalCaseResult",
            "EvalJudge",
            "EvalResult",
            "EvalResultSpec",
            "EvalSuitePolicy",
            "EvalSuiteRequirement",
            "EvalSuiteRequirementStatus",
            "EvalSuiteSpec",
            "Run",
            "RunSpec",
            "RunAssistanceBundleFile",
            "RunAssistanceBundleRecord",
            "RunAssistancePackageCommand",
            "RunAssistancePackageContract",
            "RunAssistancePackageRecord",
            "RunAssistedIngestInput",
            "ModelProfile",
            "ModelProfilePricing",
            "BudgetPolicy",
            "ContextManifest",
            "ContextManifestBudget",
            "ContextManifestFreshnessSignals",
            "ContextCapsuleInventoryRecord",
            "DecisionAuditRecord",
            "RiskAssessment",
            "RiskSignal",
            "GateCheck",
            "KnowledgeHealthIssue",
            "KnowledgeHealthRecord",
            "KnowledgeHealthRemediationInput",
            "KnowledgeHealthRemediationRecord",
            "KnowledgeHealthSummary",
            "LearningExtraction",
            "LearningExtractionSpec",
            "LearningExtractionProposal",
            "LearningExtractionSourceContext",
            "MemoryStoreCreateInput",
            "MemoryEntryCreateInput",
            "MemberGrowthRecordInput",
            "MemberGrowthPlanAction",
            "MemberGrowthProjectionItem",
            "MemberGrowthProjectionRecord",
            "MemberGrowthSupportSignals",
            "WorkspaceHealth",
            "ConnectorEscalationCandidate",
            "ConnectorRemediationSuggestion",
            "CostAlertCandidateRecord",
            "CostAlertOverviewRecord",
            "CostAlertRouteInput",
            "ManagerInputBundle",
            "GitActivity",
            "GitActivitySpec",
            "GitActivityImportReceipt",
            "GitActivityImportReceiptSpec",
            "GitActivityCorrelationReview",
            "GitActivityCorrelationReviewSpec",
            "ModelCostRow",
            "ModelCostSummaryRecord",
            "RunCloseoutGateRecord",
            "RunCloseoutInput",
            "RunProviderSourceIntegrationExecuteInput",
            "RunProviderSourceIntegrationExecutionRecord",
            "RunProviderSourceIntegrationInput",
            "RunProviderSourceIntegrationRecord",
            "RunSourceIntegrationGateRecord",
            "RunSourceIntegrationInput",
            "RunSourceIntegrationRemediationInput",
            "RunSourceIntegrationRemediationRecord",
            "RunReviewFindingInput",
            "RunReviewGateRecord",
            "RunReviewInput",
            "TaskExecutionQueueItem",
            "TaskExecutionQueueRecord",
            "WorkspaceActionBoardRecord",
            "WorkspaceActionItem",
            "WorkspaceCatalogRecord",
            "WorkspaceCatalogOption",
            "WorkspaceCatalogSpec",
            "Artifact",
            "ArtifactStore",
            "ArtifactStoreSpec",
            "AutomationProviderDelivery",
            "ConnectorHealthCheck",
            "TeamMember",
            "TeamMemberSpec",
            "ProductUser",
            "ProductUserSpec",
            "Assignment",
            "AssignmentSpec",
            "MemoryStore",
            "MemoryEntry",
            "MemoryEvalEvidenceRef",
            "MemoryStoreCreateInput",
            "MemoryEntryCreateInput",
            "MemoryBinding",
            "MemoryGrant",
            "MemoryProposal",
            "MemoryProposalSpec",
            "LearningExtraction",
            "LearningExtractionSpec",
        ]:
            self.assertIn(name, defs)
        workspace_health_fields = defs["WorkspaceHealth"]["properties"]
        for name in [
            "schemaVersion",
            "lastIndexDuration",
            "manifestLoadFailures",
            "vectorChunkCount",
            "schemaVersionMismatch",
            "staleWorkerLeases",
        ]:
            self.assertIn(name, workspace_health_fields)

    def test_member_assignment_memory_and_artifact_manifests_are_schema_backed(self) -> None:
        member = TeamMember(
            apiVersion=API_VERSION,
            kind="TeamMember",
            metadata={"name": "compiler-architect"},
            spec={
                "kind": "digital",
                "profile": {"displayName": "Compiler Architect"},
                "aboutMe": {
                    "coreCapabilities": ["compiler architecture"],
                    "workStyle": ["conservative"],
                    "workMethod": ["read-docs-first"],
                },
            },
        )
        assignment = Assignment(
            apiVersion=API_VERSION,
            kind="Assignment",
            metadata={"name": "aiteamos-backend-runtime"},
            spec={
                "member": "compiler-architect",
                "project": "aiteamos",
                "roleTemplate": "backend-engineer",
                "modules": ["services/api"],
                "responsibilities": ["Own API/runtime implementation."],
                "evalSuiteRequirements": [
                    {
                        "evalSuite": "aiteamos-eval-suite-schema-contract",
                        "paths": ["packages/workspace/**"],
                        "minimumPassRate": 0.95,
                    }
                ],
            },
        )
        store = MemoryStore(
            apiVersion=API_VERSION,
            kind="MemoryStore",
            metadata={"name": "aiteamos-project-memory"},
            spec={"storeType": "project", "ownerProject": "aiteamos", "visibility": "project"},
        )
        entry = MemoryEntry(
            apiVersion=API_VERSION,
            kind="MemoryEntry",
            metadata={"id": "MEM-1"},
            spec={
                "store": "aiteamos-project-memory",
                "path": "decisions/team-member-baseline.md",
                "title": "TeamMember baseline",
                "content": "TeamMember is the durable identity.",
                "kind": "decision",
                "scope": "project",
                "confidence": 0.95,
                "evalEvidence": [
                    {
                        "evalSuiteId": "aiteamos-eval-suite-schema-contract",
                        "lastResultId": "ERES-20260522T204421556",
                        "passRate": 1.0,
                        "threshold": 0.95,
                    }
                ],
                "relatedProjects": ["aiteamos"],
            },
        )
        binding = MemoryBinding(
            apiVersion=API_VERSION,
            kind="MemoryBinding",
            metadata={"id": "MB-1"},
            spec={"entry": "MEM-1", "targetType": "assignment", "targetId": "aiteamos-backend-runtime", "access": ["read", "reference", "inject"]},
        )
        grant = MemoryGrant(
            apiVersion=API_VERSION,
            kind="MemoryGrant",
            metadata={"id": "MG-1"},
            spec={"granteeMember": "compiler-architect", "task": "TASK-20260520T101022277", "entries": ["MEM-1"]},
        )
        proposal = MemoryProposal(
            apiVersion=API_VERSION,
            kind="MemoryProposal",
            metadata={"id": "MP-REVIEW-AUDIT"},
            spec={
                "project": "aiteamos",
                "member": "compiler-architect",
                "assignment": "aiteamos-backend-runtime",
                "status": "approved",
                "approvedMemory": "MEM-REVIEW-AUDIT",
                "kind": "procedural",
                "title": "Reviewed memory proposal",
                "content": "Memory proposal review records reviewer provenance.",
                "reviewedAt": "2026-05-22T10:00:00+08:00",
                "reviewedByMember": "compiler-architect",
                "reviewReason": "Approved after checking run evidence.",
                "decisionAudit": [
                    {
                        "decisionKind": "human_approval",
                        "decision": "approved",
                        "actorMember": "compiler-architect",
                        "actorMemberKind": "digital",
                        "authority": "approve",
                    }
                ],
            },
        )
        artifact = Artifact(
            apiVersion=API_VERSION,
            kind="Artifact",
            metadata={"id": "ART-1"},
            spec={"run": "RUN-1", "kind": "test_log", "uri": "runs/RUN-1/test.log", "sizeBytes": 10},
        )
        package = RunAssistancePackageRecord(
            run="RUN-1",
            task="TASK-20260520T101022277",
            project="aiteamos",
            member="compiler-architect",
            memberKind="hybrid",
            assignment="aiteamos-backend-runtime",
            mode="assisted",
            status="RUNNING",
            readyForAssistedExecution=True,
            generatedAt="2026-05-22T10:00:00+08:00",
            summary="Hybrid member can return assisted work through the explicit ingest boundary.",
            entrypoints=[
                {
                    "label": "Return Assisted Output",
                    "command": "POST /workspaces/current/runs/RUN-1/assisted-ingest",
                    "purpose": "Submit journal and review target.",
                }
            ],
            ingestContract={
                "requiredInputs": ["journal", "reviewTarget or diffPatch"],
                "expectedArtifacts": ["journal.md"],
                "reviewTargetTypes": ["external_review"],
                "memoryProposalPolicy": "pending review only",
                "durableMutationBoundary": "/workspaces/current/runs/RUN-1/assisted-ingest",
            },
        )
        bundle = RunAssistanceBundleRecord(
            run="RUN-1",
            task="TASK-20260520T101022277",
            project="aiteamos",
            member="compiler-architect",
            memberKind="hybrid",
            assignment="aiteamos-backend-runtime",
            generatedAt="2026-05-22T10:00:00+08:00",
            ready=True,
            package=package,
            files=[
                {
                    "path": "README.md",
                    "mediaType": "text/markdown",
                    "purpose": "Human-readable assisted handoff.",
                    "content": "# Assisted handoff",
                    "sizeBytes": 18,
                },
                {
                    "path": "assisted-ingest-template.json",
                    "mediaType": "application/json",
                    "purpose": "Durable ingest template.",
                    "content": "{}",
                    "sizeBytes": 2,
                },
            ],
            fileCount=2,
            totalSizeBytes=20,
            instructions=["Return durable output through assisted ingest."],
        )
        self.assertEqual(bundle.kind, "AiteamosBundle")
        self.assertEqual(bundle.schemaVersion, "aiteamos-bundle.v1")
        self.assertEqual(bundle.ingestInputSchema, "RunAssistedIngestInput")
        self.assertEqual(bundle.package.run, package.run)
        product_user = ProductUser(
            apiVersion=API_VERSION,
            kind="ProductUser",
            metadata={"name": "frontend-admin"},
            spec={
                "displayName": "Frontend Admin",
                "member": "compiler-architect",
                "roles": ["admin"],
                "sessionTokenEnv": "AITEAMOS_FRONTEND_ADMIN_TOKEN",
            },
        )
        git_activity = GitActivity(
            apiVersion=API_VERSION,
            kind="GitActivity",
            metadata={"id": "GIT-20260521T090500000"},
            spec={
                "member": "compiler-architect",
                "project": "aiteamos",
                "repository": "aiteamos",
                "assignment": "aiteamos-backend-runtime",
                "activityType": "pull-request",
                "provider": "github",
                "summary": "Opened a reviewed implementation PR.",
                "refs": ["refs/pull/1/head"],
            },
        )
        git_import = GitActivityImportReceipt(
            apiVersion=API_VERSION,
            kind="GitActivityImportReceipt",
            metadata={"id": "GITIMP-20260521T093000000"},
            spec={
                "project": "aiteamos",
                "repository": "aiteamos",
                "provider": "github",
                "sourceType": "provider-sync",
                "status": "imported",
                "dedupeKey": "github:pull_request:example/aiteamos:1",
                "payloadDigest": "sha256:0123456789abcdef",
                "redactionPolicy": "metadata-only",
                "importPolicy": "reviewed-import",
                "payloadRetained": False,
                "reviewedByMember": "frontend-human",
                "importedActivities": ["GIT-20260521T090500000"],
                "decisionAudit": [
                    {
                        "decisionKind": "human_approval",
                        "decision": "approve",
                        "actorMember": "frontend-human",
                        "actorMemberKind": "human",
                        "authority": "approve",
                    }
                ],
            },
        )
        git_correlation_review = GitActivityCorrelationReview(
            apiVersion=API_VERSION,
            kind="GitActivityCorrelationReview",
            metadata={"id": "GITCORR-20260521T094000000"},
            spec={
                "project": "aiteamos",
                "repository": "aiteamos",
                "provider": "github",
                "correlationKey": "pr:github:aiteamos:aiteamos:1",
                "receipts": ["GITIMP-20260521T093000000"],
                "decision": "approved",
                "reviewerMember": "frontend-human",
                "reviewerMemberKind": "human",
                "summary": "Approved import receipt correlation without promotion.",
                "riskFlags": ["manual-review-required"],
                "decisionAudit": [
                    {
                        "decisionKind": "human_approval",
                        "decision": "correlation-approved",
                        "actorMember": "frontend-human",
                        "actorMemberKind": "human",
                        "authority": "approve",
                    }
                ],
            },
        )

        self.assertEqual(member.spec.kind, "digital")
        self.assertEqual(assignment.spec.member, "compiler-architect")
        self.assertEqual(assignment.spec.evalSuiteRequirements[0].evalSuite, "aiteamos-eval-suite-schema-contract")
        self.assertEqual(assignment.spec.evalSuiteRequirements[0].paths, ["packages/workspace/**"])
        self.assertEqual(git_activity.spec.activityType, "pull-request")
        self.assertEqual(git_import.spec.redactionPolicy, "metadata-only")
        self.assertFalse(git_import.spec.payloadRetained)
        self.assertEqual(git_correlation_review.spec.decision, "approved")
        self.assertEqual(store.spec.storeType, "project")
        self.assertEqual(entry.spec.kind, "decision")
        self.assertEqual(binding.spec.targetType, "assignment")
        self.assertEqual(grant.spec.granteeMember, "compiler-architect")
        self.assertEqual(proposal.spec.reviewedByMember, "compiler-architect")
        self.assertEqual(proposal.spec.decisionAudit[0].decision, "approved")
        self.assertEqual(artifact.spec.kind, "test_log")
        self.assertTrue(package.readyForAssistedExecution)
        self.assertEqual(product_user.spec.sessionTokenEnv, "AITEAMOS_FRONTEND_ADMIN_TOKEN")

        with self.assertRaises(ValidationError):
            Artifact(
                apiVersion=API_VERSION,
                kind="Artifact",
                metadata={"id": "ART-NEGATIVE"},
                spec={"kind": "log", "uri": "runs/RUN-1/log.txt", "sizeBytes": -1},
            )

    def test_artifact_store_manifest_is_env_name_only(self) -> None:
        store = ArtifactStore(
            apiVersion=API_VERSION,
            kind="ArtifactStore",
            metadata={"name": "local-artifacts"},
            spec={
                "project": "aiteamos",
                "backend": "local",
                "default": True,
                "localPath": "artifacts/blob",
                "retentionPolicy": "reviewed-runs",
            },
        )
        remote_store = ArtifactStore(
            apiVersion=API_VERSION,
            kind="ArtifactStore",
            metadata={"name": "minio-artifacts"},
            spec={
                "project": "aiteamos",
                "backend": "minio",
                "bucket": "aiteamos-artifacts",
                "endpointUrl": "https://minio.example.invalid",
                "secrets": {"accessKeyIdEnv": "AITEAMOS_MINIO_ACCESS_KEY_ID", "secretAccessKeyEnv": "AITEAMOS_MINIO_SECRET_ACCESS_KEY"},
            },
        )

        self.assertEqual(store.spec.backend, "local")
        self.assertEqual(remote_store.spec.secrets.secretAccessKeyEnv, "AITEAMOS_MINIO_SECRET_ACCESS_KEY")

        with self.assertRaises(ValidationError):
            ArtifactStore(apiVersion=API_VERSION, kind="ArtifactStore", metadata={"name": "missing-path"}, spec={"project": "aiteamos", "backend": "local"})

        with self.assertRaises(ValidationError):
            ArtifactStore(
                apiVersion=API_VERSION,
                kind="ArtifactStore",
                metadata={"name": "secret-value"},
                spec={"project": "aiteamos", "backend": "s3", "bucket": "aiteamos-artifacts", "secrets": {"secretAccessKeyEnv": "not a value"}},
            )

    def test_permission_action_supports_env_connector_scope_and_artifact_controls(self) -> None:
        env_action = PermissionAction(tool="EnvVar", envVar="OPENAI_API_KEY", operation="use")
        connector_action = PermissionAction(tool="Connector", connector="github", connectorScope="issues", operation="read")
        artifact_action = PermissionAction(
            tool="ArtifactStore",
            artifactStore="local-artifacts",
            operation="write",
            retentionPolicy="reviewed-runs",
            exportPolicy="sanitize",
            redactionMode="sanitize",
        )

        self.assertEqual(env_action.envVar, "OPENAI_API_KEY")
        self.assertEqual(connector_action.connectorScope, "issues")
        self.assertEqual(artifact_action.redactionMode, "sanitize")

        with self.assertRaises(ValidationError):
            PermissionAction(tool="EnvVar", envVar="not a value", operation="read")

    def test_decision_audit_record_distinguishes_human_ai_and_service_decisions(self) -> None:
        human = DecisionAuditRecord(
            decisionKind="human_approval",
            decision="approved",
            actorMember="frontend-human",
            actorMemberKind="human",
            authority="approve",
            reason="Human reviewer approved a bounded permission grant.",
        )
        digital = DecisionAuditRecord(
            decisionKind="digital_recommendation",
            decision="changes_requested",
            actorMember="manager",
            actorMemberKind="digital",
            authority="recommend",
            requiresHumanReview=True,
        )
        service = DecisionAuditRecord(
            decisionKind="service_policy_decision",
            decision="deny",
            actorMember="memory-service",
            actorMemberKind="service",
            authority="enforce",
            evidence=[{"kind": "permission-explain", "blockers": ["non-interactive ask became deny"]}],
            riskAssessment=RiskAssessment(
                riskLevel="high",
                recommendedDecision="ask",
                requiresHumanReview=True,
                signals=[RiskSignal(name="non-interactive-deny", severity="medium")],
            ),
        )

        self.assertEqual(human.authority, "approve")
        self.assertTrue(digital.requiresHumanReview)
        self.assertEqual(service.evidence[0]["kind"], "permission-explain")
        self.assertEqual(service.riskAssessment.riskLevel, "high")

        with self.assertRaises(ValidationError):
            DecisionAuditRecord(decisionKind="digital_approval", decision="approved")

    def test_member_growth_record_input_is_schema_backed(self) -> None:
        payload = MemberGrowthRecordInput(
            actorMember="frontend-human",
            summary="Practice assisted ingest closeout from reviewed work evidence.",
            sourceAction="frontend-human:capture-reviewed-growth-note",
            sourceTask="TASK-HUMAN",
            sourceRun="RUN-HUMAN",
            evidence=["task:TASK-HUMAN", "run:RUN-HUMAN"],
            reason="Human reviewer captured a non-punitive growth note.",
        )

        self.assertEqual(payload.actorMember, "frontend-human")
        self.assertEqual(payload.sourceRun, "RUN-HUMAN")

        with self.assertRaises(ValidationError):
            MemberGrowthRecordInput(actorMember="frontend-human", summary="ok", hiddenScore=90)

    def test_task_plan_and_eval_suite_manifests_are_schema_backed(self) -> None:
        plan = TaskPlan(
            apiVersion=API_VERSION,
            kind="TaskPlan",
            metadata={"id": "PLAN-1"},
            spec={
                "goal": "Add model profile configuration to the dashboard.",
                "sourceTask": "TASK-20260520T101022277",
                "createdByMember": "manager",
                "subtasks": [
                    {
                        "title": "Add schema support",
                        "assignedMember": "backend-digital",
                        "assignment": "aiteamos-backend-runtime",
                        "priority": "high",
                        "acceptance": ["TaskPlan manifests validate through Pydantic."],
                        "reviewGates": ["schema review"],
                    }
                ],
            },
        )
        suite = EvalSuite(
            apiVersion=API_VERSION,
            kind="EvalSuite",
            metadata={"id": "EVAL-1"},
            spec={
                "project": "aiteamos",
                "purpose": "Exercise model/member/task behavior.",
                "members": ["backend-digital"],
                "assignments": ["aiteamos-backend-runtime"],
                "tasks": ["TASK-20260520T101022277"],
                "goldenOutputs": {
                    "dashboard-model-profiles": {
                        "expectedRoute": "/settings/model-profiles",
                        "requiredFields": ["id", "displayName", "provider", "model"],
                    }
                },
                "judge": {
                    "kind": "policy",
                    "policyRef": "digital-default",
                    "modelProfile": "openai-gpt-5.5-xhigh",
                    "rubric": ["The manifest contract remains schema-backed."],
                    "passCriteria": {"minRequiredFields": 4},
                },
                "policy": {"autoPromoteThreshold": 0.95, "minCases": 1, "requireAllGoldenOutputs": True},
                "cases": [
                    {
                        "id": "model-profile-listing",
                        "title": "List dashboard model profiles",
                        "member": "backend-digital",
                        "goldenOutputRefs": ["dashboard-model-profiles"],
                    }
                ],
                "metrics": ["acceptance"],
            },
        )
        case = EvalCase(title="Schema-backed case", goldenOutputRefs=["dashboard-model-profiles"])
        judge = EvalJudge(kind="policy", policyRef="digital-default")
        policy = EvalSuitePolicy(autoPromoteThreshold=0.95)
        requirement = EvalSuiteRequirement(
            evalSuite="EVAL-1",
            paths=["packages/workspace/**"],
            minimumPassRate=0.95,
            description="Workspace runtime changes require a green EvalSuite.",
        )

        self.assertEqual(plan.spec.subtasks[0].assignedMember, "backend-digital")
        self.assertEqual(suite.spec.cases[0].title, "List dashboard model profiles")
        self.assertEqual(suite.spec.goldenOutputs["dashboard-model-profiles"]["expectedRoute"], "/settings/model-profiles")
        self.assertEqual(suite.spec.cases[0].goldenOutputRefs, ["dashboard-model-profiles"])
        self.assertEqual(suite.spec.judge.kind, "policy")
        self.assertEqual(suite.spec.judge.policyRef, "digital-default")
        self.assertEqual(suite.spec.policy.autoPromoteThreshold, 0.95)
        self.assertEqual(case.goldenOutputRefs, ["dashboard-model-profiles"])
        self.assertEqual(judge.policyRef, "digital-default")
        self.assertEqual(policy.autoPromoteThreshold, 0.95)
        self.assertEqual(requirement.paths, ["packages/workspace/**"])

        result = EvalResult(
            apiVersion=API_VERSION,
            kind="EvalResult",
            metadata={"id": "ERES-1"},
            spec={
                "evalSuite": "EVAL-1",
                "project": "aiteamos",
                "status": "pass",
                "totalCases": 1,
                "passedCases": 1,
                "failedCases": 0,
                "passRate": 1.0,
                "caseResults": [EvalCaseResult(caseId="model-profile-listing", status="pass", score=1.0).model_dump(mode="json")],
            },
        )
        self.assertEqual(result.spec.passRate, 1.0)
        self.assertEqual(result.spec.caseResults[0].caseId, "model-profile-listing")
        self.assertEqual(MemoryEvalEvidenceRef(evalSuiteId="EVAL-1", lastResultId="ERES-1", passRate=1.0).lastResultId, "ERES-1")

        with self.assertRaises(ValidationError):
            TaskPlan(apiVersion=API_VERSION, kind="TaskPlan", metadata={"id": "PLAN-BAD"}, spec={"goal": "x", "status": "done"})

        with self.assertRaises(ValidationError):
            EvalSuite(apiVersion=API_VERSION, kind="EvalSuite", metadata={"id": "EVAL-BAD"}, spec={"purpose": "missing project"})

        with self.assertRaises(ValidationError):
            EvalSuitePolicy(autoPromoteThreshold=1.2)

        with self.assertRaises(ValidationError):
            EvalResult(apiVersion=API_VERSION, kind="EvalResult", metadata={"id": "ERES-BAD"}, spec={"evalSuite": "EVAL-1", "project": "aiteamos", "passRate": 1.2})

    def test_learning_extraction_manifest_is_schema_backed(self) -> None:
        extraction = LearningExtraction(
            apiVersion=API_VERSION,
            kind="LearningExtraction",
            metadata={"id": "LEX-1"},
            spec={
                "runId": "RUN-1",
                "extractedAt": "2026-05-22T16:31:13.141+08:00",
                "dedupeKey": "run:RUN-1:extractor:aiteamos.learning-extractor:v1",
                "proposals": [
                    {
                        "kind": "memory",
                        "targetManifest": {
                            "apiVersion": API_VERSION,
                            "kind": "MemoryProposal",
                            "metadata": {"id": "MP-DRAFT-1"},
                            "spec": {"title": "Draft memory"},
                        },
                        "confidence": 0.75,
                    }
                ],
            },
        )

        self.assertEqual(extraction.spec.proposals[0].targetKind, "MemoryProposal")

        with self.assertRaises(ValidationError):
            LearningExtraction(
                apiVersion=API_VERSION,
                kind="LearningExtraction",
                metadata={"id": "LEX-BAD"},
                spec={
                    "runId": "RUN-1",
                    "extractedAt": "2026-05-22T16:31:13.141+08:00",
                    "dedupeKey": "run:RUN-1:extractor:bad:v1",
                    "proposals": [{"kind": "skill", "targetManifest": {"kind": "MemoryProposal"}}],
                },
            )

    def test_budget_policy_schema_is_constrained(self) -> None:
        policy = BudgetPolicy(
            apiVersion=API_VERSION,
            kind="BudgetPolicy",
            metadata={"name": "default-project-budget"},
            spec={
                    "scope": {"project": "aiteamos", "member": "backend-digital", "assignment": "aiteamos-backend-runtime"},
                "limits": {
                    "softUsdPerRun": 5.0,
                    "softInputTokensPerRun": 100000,
                    "maxUsdPerRun": 10.0,
                    "maxUsdPerDay": 50.0,
                    "maxInputTokensPerRun": 200000,
                    "maxOutputTokensPerRun": 40000,
                    "maxRetriesPerRun": 2,
                },
                "rateLimit": {"requestsPerMinute": 20},
                "fallback": {"allowModelFallback": True, "maxFallbacksPerRun": 1},
                "enforcement": {"onSoftLimit": "warn", "onHardLimit": "stop-run"},
            },
        )

        self.assertEqual(policy.spec.scope.project, "aiteamos")
        self.assertEqual(policy.spec.limits.softUsdPerRun, 5.0)
        self.assertEqual(policy.spec.limits.maxRetriesPerRun, 2)
        self.assertEqual(policy.spec.rateLimit.requestsPerMinute, 20)

        with self.assertRaises(ValidationError):
            BudgetPolicy(
                apiVersion=API_VERSION,
                kind="BudgetPolicy",
                metadata={"name": "freeform-budget"},
                spec={
                    "scope": {"project": "aiteamos", "unknown": "not allowed"},
                    "limits": {"customLimit": 1},
                    "customPolicy": "not allowed",
                },
            )

        with self.assertRaises(ValidationError):
            BudgetPolicy(
                apiVersion=API_VERSION,
                kind="BudgetPolicy",
                metadata={"name": "negative-budget"},
                spec={"scope": {"project": "aiteamos"}, "limits": {"maxUsdPerRun": -1}},
            )

        with self.assertRaises(ValidationError):
            BudgetPolicy(
                apiVersion=API_VERSION,
                kind="BudgetPolicy",
                metadata={"name": "invalid-soft-hard-budget"},
                spec={"scope": {"project": "aiteamos"}, "limits": {"softUsdPerRun": 20, "maxUsdPerRun": 10}},
            )

    def test_context_manifest_schema_records_explainability_fields(self) -> None:
        manifest = ContextManifest(
            apiVersion=API_VERSION,
            kind="ContextManifest",
            metadata={"id": "RUN-1"},
            spec={
                "generatedAt": "2026-05-20T00:00:00+00:00",
                "task": "TASK-20260520T101022277",
                "member": "backend-digital",
                "memberKind": "digital",
                "assignment": "aiteamos-backend-runtime",
                "project": "aiteamos",
                "modelProfile": "openai-gpt-5.5-xhigh",
                "branch": "aiteamos/test",
                "memoryBindings": ["MB-1"],
                "memoryGrants": ["MG-1"],
                "sourcePriority": ["task", "member_identity", "assignment_contract", "model_budget"],
                "sources": {"projectDocs": [{"path": "docs/architecture.md"}], "approvedMemory": []},
                "sourceDecisions": [
                    {
                        "sourceType": "projectDoc",
                        "sourceRef": "aiteamos:docs/architecture.md",
                        "outcome": "included",
                        "reason": "project.ruleEntrypoints",
                        "dedupeKey": "projectDoc:aiteamos:docs/architecture.md",
                        "budgetBucket": "projectDocs",
                        "charsIncluded": 120,
                        "charsLimit": 2400,
                        "truncated": False,
                        "snippetPreview": "AITEAMOS Architecture",
                        "lineStart": 1,
                        "lineEnd": 2,
                    }
                ],
                "sourceCounts": {"projectDocs": 1, "approvedMemory": 0},
                "exclusions": ["relevant code capped"],
                "freshnessSignals": {"recentRunCount": 1, "approvedMemoryCount": 0, "excludedMemoryCount": 0},
                "budget": {
                    "modelProfile": "openai-gpt-5.5-xhigh",
                    "applicablePolicy": "default-budget",
                    "policies": [
                        {
                            "id": "default-budget",
                            "scope": {"project": "aiteamos"},
                            "limits": {"maxInputTokensPerRun": 800000},
                            "rateLimit": {"requestsPerMinute": 10},
                            "fallback": {"allowModelFallback": False, "maxFallbacksPerRun": 0},
                            "enforcement": {"onSoftLimit": "warn", "onHardLimit": "stop-run"},
                            "applies": True,
                            "specificity": 1,
                        }
                    ],
                },
                "limits": {"projectDocs": 8},
            },
        )

        self.assertEqual(manifest.spec.sourceCounts["projectDocs"], 1)
        self.assertEqual(manifest.spec.sourceDecisions[0].dedupeKey, "projectDoc:aiteamos:docs/architecture.md")
        self.assertEqual(manifest.spec.sourceDecisions[0].lineStart, 1)
        self.assertEqual(manifest.spec.sourceDecisions[0].lineEnd, 2)
        self.assertEqual(manifest.spec.freshnessSignals.recentRunCount, 1)
        self.assertEqual(manifest.spec.budget.applicablePolicy, "default-budget")

        with self.assertRaises(ValidationError):
            ContextManifest(
                apiVersion=API_VERSION,
                kind="ContextManifest",
                metadata={"id": "RUN-BAD"},
                spec={"task": "TASK-20260520T101022277", "member": "backend-digital", "customField": "not allowed"},
            )

    def test_api_view_records_are_schema_backed(self) -> None:
        review_gate = RunReviewGateRecord(
            run="RUN-1",
            readyForHumanReview=True,
            status="READY_FOR_HUMAN_REVIEW",
            summary="Ready.",
            blockers=[],
            warnings=[],
            checks=[{"name": "journal", "status": "pass", "message": "Run journal is present."}],
            evalSuiteRequirements=[
                {
                    "evalSuite": "aiteamos-eval-suite-schema-contract",
                    "paths": ["packages/workspace/**"],
                    "matchedPaths": ["packages/workspace/runtime.py"],
                    "threshold": 0.95,
                    "lastResultId": "ERES-1",
                    "passRate": 1.0,
                    "status": "pass",
                    "message": "EvalSuite passed.",
                }
            ],
        )
        requirement_status = EvalSuiteRequirementStatus(
            evalSuite="aiteamos-eval-suite-schema-contract",
            paths=["packages/workspace/**"],
            matchedPaths=["packages/workspace/runtime.py"],
            threshold=0.95,
            lastResultId="ERES-1",
            passRate=1.0,
            status="pass",
            message="EvalSuite passed.",
        )
        closeout_gate = RunCloseoutGateRecord(
            run="RUN-1",
            readyForCloseout=False,
            status="BLOCKED",
            summary="Needs approval.",
            latestReview=None,
            blockers=["No human review is linked to this run."],
            warnings=[],
            checks=[{"name": "human-approval", "status": "fail", "message": "No human review is linked to this run."}],
        )
        source_integration_gate = RunSourceIntegrationGateRecord(
            run="RUN-1",
            readyForSourceIntegration=True,
            status="READY_FOR_SOURCE_INTEGRATION",
            summary="Ready to integrate source.",
            repository="/tmp/example",
            sourceBranch="main",
            workerBranch="aiteamos/TASK/backend/RUN-1",
            changedPaths=["src/app.py"],
            blockers=[],
            warnings=[],
            checks=[{"name": "fast-forward", "status": "pass", "message": "Worker branch can fast-forward main."}],
        )
        capsule = ContextCapsuleInventoryRecord(
            run="RUN-1",
            task="TASK-20260520T101022277",
            member="backend-digital",
            assignment="aiteamos-backend-runtime",
            sourcePriority=["task"],
            sourceCounts={"projectDocs": 1},
            exclusionCount=0,
            freshnessSignals={"recentRunCount": 1},
            budget={"modelProfile": "local/manual", "applicablePolicy": "default-budget"},
            contentIncluded=False,
        )

        self.assertTrue(review_gate.readyForHumanReview)
        self.assertEqual(review_gate.evalSuiteRequirements[0].evalSuite, "aiteamos-eval-suite-schema-contract")
        self.assertEqual(requirement_status.status, "pass")
        self.assertFalse(closeout_gate.readyForCloseout)
        self.assertTrue(source_integration_gate.readyForSourceIntegration)
        self.assertEqual(capsule.budget.applicablePolicy, "default-budget")
        closeout_input = RunCloseoutInput(actorMember="frontend-human", reason="Approved reviewed run evidence.")
        self.assertEqual(closeout_input.actorMember, "frontend-human")
        source_integration_input = RunSourceIntegrationInput(actorMember="frontend-human", reason="Integrate reviewed branch.")
        self.assertEqual(source_integration_input.actorMember, "frontend-human")
        remediation_input = RunSourceIntegrationRemediationInput(actorMember="frontend-human", reason="Request follow-up target.")
        remediation_record = RunSourceIntegrationRemediationRecord(
            run="RUN-1",
            status="remediation-requested",
            summary="Source branch advanced before integration.",
            strategy="conflict-resolution-worktree",
            sourceBranch="main",
            workerBranch="aiteamos/test",
            remediationBranch="aiteamos/remediation/RUN-1",
            remediationWorktree="/tmp/aiteamos/.aiteamos/artifacts/worktrees/RUN-1-source-remediation",
            mergeStatus="conflicts-detected",
            conflictFiles=["src/runtime.py"],
            conflictResolution={
                "status": "conflicts-detected",
                "branch": "aiteamos/remediation/RUN-1",
                "worktree": "/tmp/aiteamos/.aiteamos/artifacts/worktrees/RUN-1-source-remediation",
            },
        )
        provider_input = RunProviderSourceIntegrationInput(actorMember="frontend-human", reason="Request provider merge queue.")
        provider_execute_input = RunProviderSourceIntegrationExecuteInput(
            actorMember="frontend-human",
            reason="Preflight provider merge queue.",
            dryRun=True,
        )
        provider_record = RunProviderSourceIntegrationRecord(
            run="RUN-1",
            status="provider-integration-requested",
            summary="Provider review target can be queued for source integration.",
            strategy="provider-review-target",
            provider="github",
            reviewTarget={"type": "pull_request", "url": "https://github.com/example/aiteamos/pull/9"},
            providerChecks={"status": "passed"},
        )
        provider_execution_record = RunProviderSourceIntegrationExecutionRecord(
            run="RUN-1",
            status="dry-run-passed",
            summary="Provider source integration preflight passed.",
            strategy="provider-review-target-execution",
            provider="github",
            dryRun=True,
            reviewTarget={"type": "pull_request", "url": "https://github.com/example/aiteamos/pull/9"},
            providerChecks={"status": "passed"},
        )
        self.assertEqual(remediation_input.actorMember, "frontend-human")
        self.assertEqual(remediation_record.strategy, "conflict-resolution-worktree")
        self.assertEqual(remediation_record.mergeStatus, "conflicts-detected")
        self.assertEqual(provider_input.actorMember, "frontend-human")
        self.assertTrue(provider_execute_input.dryRun)
        self.assertEqual(provider_record.strategy, "provider-review-target")
        self.assertEqual(provider_execution_record.status, "dry-run-passed")

        with self.assertRaises(ValidationError):
            RunReviewGateRecord(
                run="RUN-1",
                readyForHumanReview=True,
                status="READY_FOR_HUMAN_REVIEW",
                summary="Ready.",
                blockers=[],
                warnings=[],
                checks=[],
                unknown="not allowed",
            )

    def test_model_cost_summary_record_is_schema_backed(self) -> None:
        summary = ModelCostSummaryRecord(
            source="workspace-event-ledger",
            totals={
                "attempts": 1,
                "calls": 1,
                "failures": 0,
                "fallbacks": 0,
                "inputTokens": 10,
                "outputTokens": 5,
                "totalTokens": 15,
                "costUsd": 0.01,
                "latencyMsAvg": 12.5,
                "successRate": 1.0,
            },
            byModel=[
                {
                    "provider": "openai",
                    "model": "example-model",
                    "attempts": 1,
                    "calls": 1,
                    "failures": 0,
                    "fallbacks": 0,
                    "inputTokens": 10,
                    "outputTokens": 5,
                    "totalTokens": 15,
                    "costUsd": 0.01,
                    "successRate": 1.0,
                }
            ],
            byRun=[],
        )

        self.assertEqual(summary.totals.totalTokens, 15)
        self.assertEqual(summary.byModel[0].provider, "openai")

        with self.assertRaises(ValidationError):
            ModelCostRow(
                attempts=0,
                calls=0,
                failures=0,
                fallbacks=0,
                inputTokens=0,
                outputTokens=0,
                totalTokens=0,
                costUsd=-1,
            )

    def test_read_only_guidance_records_are_schema_backed(self) -> None:
        queue = TaskExecutionQueueRecord(
            summary={"total": 1, "ready-to-run": 1},
            items=[
                {
                    "id": "TASK-20260520T101022277",
                    "queueStatus": "ready-to-run",
                    "title": "Exercise guided dashboard action",
                    "taskStatus": "TODO",
                    "runCount": 0,
                    "blockers": [],
                    "actions": ["Create a run."],
                }
            ],
        )
        board = WorkspaceActionBoardRecord(
            summary={"total": 1, "launch": 1},
            items=[
                {
                    "id": "task:TASK-20260520T101022277:create-run",
                    "lane": "launch",
                    "priority": 50,
                    "targetType": "task",
                    "targetId": "TASK-20260520T101022277",
                    "task": "TASK-20260520T101022277",
                    "action": "create-run",
                    "title": "Exercise guided dashboard action",
                    "reason": "Task is ready for a new run.",
                    "blockers": [],
                    "warnings": [],
                }
            ],
        )
        catalog = WorkspaceCatalogRecord(
            spec={
                "currentWorkspace": "current",
                "generatedAt": "2026-05-21T00:00:00Z",
                "options": [
                    {
                        "id": "example:protocol-fixture",
                        "label": "Protocol Fixture",
                        "optionType": "example",
                        "workspaceRef": "examples/protocol-fixture",
                        "workspaceName": "protocol-fixture-demo",
                        "workspaceMode": "embedded",
                        "protocolVersion": API_VERSION,
                        "project": "protocol-fixture",
                        "projectTitle": "Protocol Fixture",
                        "relativePath": "examples/protocol-fixture/.aiteamos",
                        "servedByCurrentApi": False,
                        "safeForPublicDemo": True,
                        "launchCommand": "./aiteamos serve --workspace examples/protocol-fixture/.aiteamos",
                        "validateCommand": "./aiteamos workspace validate --workspace examples/protocol-fixture/.aiteamos",
                        "dashboardCommand": "cd apps/dashboard && npm run dev",
                        "counts": {"members": 4},
                        "healthSummary": {"errors": 0, "warnings": 0, "info": 0},
                    }
                ],
            }
        )

        self.assertEqual(queue.items[0].queueStatus, "ready-to-run")
        self.assertEqual(board.items[0].lane, "launch")
        self.assertEqual(catalog.spec.options[0].workspaceName, "protocol-fixture-demo")

        with self.assertRaises(ValidationError):
            TaskExecutionQueueRecord(summary={"total": 1}, items=[{"id": "TASK-1", "queueStatus": "ready-to-run"}])
        with self.assertRaises(ValidationError):
            WorkspaceCatalogRecord(
                spec={
                    "currentWorkspace": "current",
                    "generatedAt": "2026-05-21T00:00:00Z",
                    "options": [{"id": "unsafe", "label": "Unsafe", "optionType": "private"}],
                }
            )

    def test_knowledge_health_record_is_schema_backed(self) -> None:
        health = KnowledgeHealthRecord(
            generatedAt="2026-05-20T00:00:00+00:00",
            summary={"approvedMemory": 1, "pendingProposals": 2, "issues": 1, "warnings": 1, "errors": 0},
            issues=[
                {
                    "severity": "warning",
                    "kind": "memory-status",
                    "ref": "MEM-1",
                    "message": "Approved memory is marked stale.",
                    "action": "Re-verify the memory.",
                }
            ],
        )

        self.assertEqual(health.summary.approvedMemory, 1)
        self.assertEqual(health.issues[0].kind, "memory-status")
        remediation = KnowledgeHealthRemediationRecord(
            generatedAt="2026-05-20T00:01:00+00:00",
            issueKind="memory-status",
            ref="MEM-1",
            action="verify-entry",
            actorMember="frontend-human",
            dryRun=True,
            applied=False,
            issue=health.issues[0],
            decisionAudit=[
                {
                    "decisionKind": "human_approval",
                    "decision": "dry-run",
                    "actorMember": "frontend-human",
                    "authority": "record",
                }
            ],
        )
        remediation_input = KnowledgeHealthRemediationInput(
            issueKind="memory-status",
            ref="MEM-1",
            action="verify-entry",
            actorMember="frontend-human",
            reason="Verify stale memory.",
        )

        self.assertEqual(remediation.action, "verify-entry")
        self.assertTrue(remediation_input.dryRun)

        with self.assertRaises(ValidationError):
            KnowledgeHealthRecord(
                generatedAt="2026-05-20T00:00:00+00:00",
                summary={"approvedMemory": -1, "pendingProposals": 0, "issues": 0, "warnings": 0, "errors": 0},
                issues=[],
            )

    def test_model_profile_pricing_schema_is_constrained(self) -> None:
        profile = ModelProfile(
            apiVersion=API_VERSION,
            kind="ModelProfile",
            metadata={"name": "priced-profile"},
            spec={
                "provider": "openai",
                "model": "example-model",
                "pricing": {
                    "inputUsdPer1MTokens": 1.0,
                    "outputUsdPer1MTokens": 2.0,
                    "requestUsd": 0.01,
                },
            },
        )

        self.assertEqual(profile.spec.pricing.inputUsdPer1MTokens, 1.0)

        with self.assertRaises(ValidationError):
            ModelProfile(
                apiVersion=API_VERSION,
                kind="ModelProfile",
                metadata={"name": "empty-pricing"},
                spec={"provider": "openai", "model": "example-model", "pricing": {}},
            )

        with self.assertRaises(ValidationError):
            ModelProfile(
                apiVersion=API_VERSION,
                kind="ModelProfile",
                metadata={"name": "negative-pricing"},
                spec={"provider": "openai", "model": "example-model", "pricing": {"inputUsdPer1MTokens": -1}},
            )

    def test_openapi_reuses_pydantic_schema_components(self) -> None:
        openapi = build_openapi_schema()

        self.assertEqual(openapi["openapi"], "3.1.0")
        self.assertEqual(openapi["info"]["version"], API_VERSION)
        schemas = openapi["components"]["schemas"]
        self.assertIn("Task", schemas)
        self.assertIn("RunSpec", schemas)
        self.assertIn("RunAssistanceBundleFile", schemas)
        self.assertIn("RunAssistanceBundleRecord", schemas)
        self.assertIn("RunAssistancePackageRecord", schemas)
        self.assertIn("RunAssistedIngestInput", schemas)
        self.assertIn("ContextCapsuleInventoryRecord", schemas)
        self.assertIn("KnowledgeHealthRecord", schemas)
        self.assertIn("KnowledgeHealthRemediationInput", schemas)
        self.assertIn("KnowledgeHealthRemediationRecord", schemas)
        self.assertIn("LearningExtraction", schemas)
        self.assertIn("LearningExtractionProposal", schemas)
        self.assertIn("ModelCostSummaryRecord", schemas)
        self.assertIn("ManagerInputBundle", schemas)
        self.assertIn("WorkspaceHealth", schemas)
        for name in [
            "lastIndexDuration",
            "manifestLoadFailures",
            "vectorChunkCount",
            "schemaVersionMismatch",
            "staleWorkerLeases",
        ]:
            self.assertIn(name, schemas["WorkspaceHealth"]["properties"])
        self.assertIn("ConnectorEscalationCandidate", schemas)
        self.assertIn("ConnectorRemediationSuggestion", schemas)
        self.assertIn("MemberGrowthSupportSignals", schemas)
        self.assertIn("RunReviewGateRecord", schemas)
        self.assertIn("RunCloseoutGateRecord", schemas)
        self.assertIn("RunCloseoutInput", schemas)
        self.assertIn("RunProviderSourceIntegrationExecuteInput", schemas)
        self.assertIn("RunProviderSourceIntegrationExecutionRecord", schemas)
        self.assertIn("RunProviderSourceIntegrationInput", schemas)
        self.assertIn("RunProviderSourceIntegrationRecord", schemas)
        self.assertIn("RunSourceIntegrationGateRecord", schemas)
        self.assertIn("RunSourceIntegrationInput", schemas)
        self.assertIn("TaskExecutionQueueRecord", schemas)
        self.assertIn("WorkspaceActionBoardRecord", schemas)
        self.assertIn("WorkspaceCatalogRecord", schemas)
        self.assertIn("RetrospectiveSuggestionRecord", schemas)
        self.assertIn("#/components/schemas/Metadata", json.dumps(openapi, sort_keys=True))
        self.assertNotIn("#/$defs/", json.dumps(openapi, sort_keys=True))

    def test_typescript_types_are_generated_without_parallel_zod_schema(self) -> None:
        typescript = build_typescript_types()

        self.assertIn("Generated from Pydantic JSON Schema emitted by packages/schema/aiteamos_schema.", typescript)
        self.assertIn("export type TaskSpec", typescript)
        self.assertIn("export type TaskPlanSpec", typescript)
        self.assertIn("export type EvalSuiteSpec", typescript)
        self.assertIn("export type ContextManifestBudget", typescript)
        self.assertIn("export type ContextCapsuleInventoryRecord", typescript)
        self.assertIn("export type KnowledgeHealthRecord", typescript)
        self.assertIn("export type KnowledgeHealthRemediationInput", typescript)
        self.assertIn("export type KnowledgeHealthRemediationRecord", typescript)
        self.assertIn("export type LearningExtractionSpec", typescript)
        self.assertIn("export type LearningExtractionProposal", typescript)
        self.assertIn("export type ModelCostSummaryRecord", typescript)
        self.assertIn("export type ManagerInputBundle", typescript)
        self.assertIn("export type WorkspaceHealth", typescript)
        self.assertIn('"lastIndexDuration"?: number | null', typescript)
        self.assertIn('"manifestLoadFailures"?: Array<Record<string, unknown>>', typescript)
        self.assertIn('"vectorChunkCount"?: number', typescript)
        self.assertIn('"schemaVersionMismatch"?: boolean', typescript)
        self.assertIn('"staleWorkerLeases"?: Array<Record<string, unknown>>', typescript)
        self.assertIn("export type ConnectorEscalationCandidate", typescript)
        self.assertIn("export type ConnectorRemediationSuggestion", typescript)
        self.assertIn("export type MemberGrowthSupportSignals", typescript)
        self.assertIn("export type RunReviewGateRecord", typescript)
        self.assertIn("export type RunCloseoutGateRecord", typescript)
        self.assertIn("export type RunCloseoutInput", typescript)
        self.assertIn("export type RunProviderSourceIntegrationExecuteInput", typescript)
        self.assertIn("export type RunProviderSourceIntegrationExecutionRecord", typescript)
        self.assertIn("export type RunProviderSourceIntegrationInput", typescript)
        self.assertIn("export type RunProviderSourceIntegrationRecord", typescript)
        self.assertIn("export type RunSourceIntegrationGateRecord", typescript)
        self.assertIn("export type RunSourceIntegrationInput", typescript)
        self.assertIn("export type TaskExecutionQueueRecord", typescript)
        self.assertIn("export type WorkspaceActionBoardRecord", typescript)
        self.assertIn("export type WorkspaceCatalogRecord", typescript)
        self.assertIn("export type RetrospectiveSuggestionRecord", typescript)
        self.assertIn("export type SessionProjectionRecord", typescript)
        self.assertIn("export type RunSpec", typescript)
        self.assertIn("export type RunAssistanceBundleFile", typescript)
        self.assertIn("export type RunAssistanceBundleRecord", typescript)
        self.assertIn("export type RunAssistancePackageRecord", typescript)
        self.assertIn("export type RunAssistedIngestInput", typescript)
        self.assertIn("export type ModelProfileSpec", typescript)
        self.assertIn("export type AiteamosManifest", typescript)
        self.assertNotIn("zod", typescript.lower())

    def test_aiteamos_bundle_schema_is_generated_from_pydantic_contract(self) -> None:
        schema = build_aiteamos_bundle_schema()

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["$id"], "https://aiteamos.dev/schemas/aiteamos.dev/v1alpha1/aiteamos-bundle.schema.json")
        self.assertEqual(schema["x-aiteamos-api-version"], API_VERSION)
        self.assertEqual(schema["$ref"], "#/$defs/RunAssistanceBundleRecord")
        defs = schema["$defs"]
        self.assertIn("RunAssistanceBundleRecord", defs)
        self.assertIn("RunAssistedIngestInput", defs)
        properties = defs["RunAssistanceBundleRecord"]["properties"]
        self.assertEqual(properties["apiVersion"]["const"], API_VERSION)
        self.assertEqual(properties["kind"]["const"], "AiteamosBundle")
        self.assertEqual(properties["schemaVersion"]["const"], "aiteamos-bundle.v1")
        self.assertEqual(properties["ingestInputSchema"]["const"], "RunAssistedIngestInput")
        self.assertIn("durableMutationBoundary", json.dumps(schema, sort_keys=True))

    def test_export_writes_all_contract_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_schema_path = root / "schema" / "aiteamos.schema.json"
            openapi_path = root / "schema" / "openapi.json"
            typescript_path = root / "dashboard" / "aiteamos-schema.ts"
            bundle_schema_path = root / "schema" / "aiteamos-bundle.schema.json"

            written = export_schema_files(
                json_schema_path=json_schema_path,
                openapi_path=openapi_path,
                typescript_path=typescript_path,
                aiteamos_bundle_schema_path=bundle_schema_path,
            )

            self.assertEqual(written, [json_schema_path, openapi_path, typescript_path, bundle_schema_path])
            self.assertEqual(json.loads(json_schema_path.read_text(encoding="utf-8"))["x-aiteamos-api-version"], API_VERSION)
            self.assertEqual(json.loads(openapi_path.read_text(encoding="utf-8"))["info"]["version"], API_VERSION)
            self.assertEqual(json.loads(bundle_schema_path.read_text(encoding="utf-8")), build_aiteamos_bundle_schema())
            self.assertIn("export type AiteamosManifest", typescript_path.read_text(encoding="utf-8"))

    def test_cli_schema_export_writes_requested_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            json_schema_path = root / "contracts" / "aiteamos.schema.json"
            openapi_path = root / "contracts" / "openapi.json"
            typescript_path = root / "types" / "aiteamos-schema.ts"

            result = cli_main(
                [
                    "schema",
                    "export",
                    "--json-schema",
                    str(json_schema_path),
                    "--openapi",
                    str(openapi_path),
                    "--typescript",
                    str(typescript_path),
                ]
            )

            self.assertEqual(result, 0)
            self.assertTrue(json_schema_path.exists())
            self.assertTrue(openapi_path.exists())
            self.assertTrue(typescript_path.exists())


if __name__ == "__main__":
    unittest.main()
