/*
 * Generated from Pydantic JSON Schema emitted by packages/schema/aiteamos_schema.
 * Do not edit by hand. Run `aiteamos schema export`.
 */

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

export type ApprovalWorkflow = {
  "apiVersion"?: string;
  "kind": "ApprovalWorkflow";
  "metadata": Metadata;
  "spec": ApprovalWorkflowSpec;
  [key: string]: unknown;
};

export type ApprovalWorkflowEscalation = {
  "targetMember": string;
  "afterSlaBreach"?: boolean;
  "messageType"?: "review-request";
  "reason"?: string | null;
  [key: string]: unknown;
};

export type ApprovalWorkflowSLA = {
  "durationSeconds": number;
  "startsAt"?: "workflow-created" | "stage-entered" | "previous-stage-completed";
  "dueAt"?: string | null;
  "warningAfterSeconds"?: number | null;
  [key: string]: unknown;
};

export type ApprovalWorkflowSpec = {
  "project"?: string | null;
  "subjectKind": string;
  "subjectRef": string;
  "requesterMember"?: string | null;
  "ownerMember"?: string | null;
  "status"?: "draft" | "pending" | "approved" | "rejected" | "expired" | "cancelled" | "escalated";
  "stages": Array<ApprovalWorkflowStage>;
  "currentStage"?: string | null;
  "createdAt"?: string | null;
  "updatedAt"?: string | null;
  "completedAt"?: string | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ApprovalWorkflowStage = {
  "id": string;
  "kind": "every-of" | "any-of" | "quorum";
  "reviewerMembers"?: Array<string>;
  "reviewerKinds"?: Array<"human" | "hybrid" | "service">;
  "quorum"?: number | null;
  "sla": ApprovalWorkflowSLA;
  "escalation"?: ApprovalWorkflowEscalation | null;
  "approvals"?: Array<string>;
  "status"?: "pending" | "satisfied" | "rejected" | "expired" | "escalated";
  [key: string]: unknown;
};

export type Artifact = {
  "apiVersion"?: string;
  "kind": "Artifact";
  "metadata": Metadata;
  "spec": ArtifactSpec;
  [key: string]: unknown;
};

export type ArtifactSpec = {
  "run"?: string | null;
  "sourceRun"?: string | null;
  "kind": string;
  "uri"?: string | null;
  "path"?: string | null;
  "url"?: string | null;
  "ref"?: string | null;
  "sha256"?: string | null;
  "sizeBytes"?: number | null;
  "retention"?: string | null;
  "lifecycle"?: "active" | "archived" | "redacted";
  "retainedUntil"?: string | null;
  "archivedAt"?: string | null;
  "redactedAt"?: string | null;
  "sensitivity"?: string | null;
  "exportPolicy"?: ("include" | "sanitize" | "manifest_only" | "manifest-only" | "exclude") | null;
  "redactionPolicy"?: string | null;
  "redaction"?: Record<string, unknown>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type ArtifactStore = {
  "apiVersion"?: string;
  "kind": "ArtifactStore";
  "metadata": Metadata;
  "spec": ArtifactStoreSpec;
  [key: string]: unknown;
};

export type ArtifactStoreSecretRefs = {
  "accessKeyIdEnv"?: string | null;
  "secretAccessKeyEnv"?: string | null;
  "sessionTokenEnv"?: string | null;
  "tokenEnv"?: string | null;
};

export type ArtifactStoreSpec = {
  "project": string;
  "backend": "local" | "s3" | "minio" | "git_lfs";
  "default"?: boolean;
  "localPath"?: string | null;
  "bucket"?: string | null;
  "endpointUrl"?: string | null;
  "region"?: string | null;
  "prefix"?: string | null;
  "retentionPolicy"?: string | null;
  "secrets"?: ArtifactStoreSecretRefs;
};

export type Assignment = {
  "apiVersion"?: string;
  "kind": "Assignment";
  "metadata": Metadata;
  "spec": AssignmentSpec;
  [key: string]: unknown;
};

export type AssignmentScope = {
  "repositories"?: Array<string>;
  "read"?: Array<string>;
  "write"?: Array<string>;
  "requiresHumanReview"?: Array<string>;
  [key: string]: unknown;
};

export type AssignmentSpec = {
  "member": string;
  "project": string;
  "roleTemplate"?: string | null;
  "roleContext"?: string | null;
  "title"?: string | null;
  "status"?: "active" | "paused" | "completed" | "archived";
  "repositories"?: Array<string>;
  "modules"?: Array<string>;
  "features"?: Array<string>;
  "responsibilities"?: Array<string>;
  "scope"?: AssignmentScope;
  "permissionPolicies"?: Array<string>;
  "memoryBindings"?: Array<string>;
  "evalSuiteRequirements"?: Array<EvalSuiteRequirement>;
  "activeFrom"?: string | null;
  "activeTo"?: string | null;
  [key: string]: unknown;
};

export type Automation = {
  "apiVersion"?: string;
  "kind": "Automation";
  "metadata": Metadata;
  "spec": AutomationSpec;
  [key: string]: unknown;
};

export type AutomationApproval = {
  "apiVersion"?: string;
  "kind": "AutomationApproval";
  "metadata": Metadata;
  "spec": AutomationApprovalSpec;
  [key: string]: unknown;
};

export type AutomationApprovalSpec = {
  "automationRun": string;
  "automation": string;
  "project"?: string | null;
  "approvalWorkflow"?: string | null;
  "reviewerMember": string;
  "reviewerKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "decision": "approved" | "rejected";
  "approvalGates"?: Array<string>;
  "reason"?: string | null;
  "decidedAt"?: string | null;
  "expiresAt"?: string | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type AutomationCreateInput = {
  "name": string;
  "targetType"?: ("human_reminder" | "digital_execution" | "hybrid_assist" | "service_task" | "memory_health" | "review" | "task_planning" | "manager_recommendation" | "connector_failure_reminder" | "git_activity_correlation_promotion" | "git_activity_retention_sweep" | "artifact_retention_sweep") | null;
  "target_type"?: ("human_reminder" | "digital_execution" | "hybrid_assist" | "service_task" | "memory_health" | "review" | "task_planning" | "manager_recommendation" | "connector_failure_reminder" | "git_activity_correlation_promotion" | "git_activity_retention_sweep" | "artifact_retention_sweep") | null;
  "target"?: Record<string, unknown> | null;
  "ownerMember"?: string | null;
  "owner_member"?: string | null;
  "serviceMember"?: string | null;
  "service_member"?: string | null;
  "project"?: string | null;
  "triggers"?: Array<AutomationTriggerInput> | null;
  "dryRun"?: boolean | null;
  "dry_run"?: boolean | null;
  "status"?: "active" | "paused" | "archived";
  "permissionPolicies"?: Array<string> | null;
  "permission_policies"?: Array<string> | null;
  "approvalGates"?: Array<string> | null;
  "approval_gates"?: Array<string> | null;
};

export type AutomationProviderDelivery = {
  "apiVersion"?: string;
  "kind": "AutomationProviderDelivery";
  "metadata": Metadata;
  "spec": AutomationProviderDeliverySpec;
  [key: string]: unknown;
};

export type AutomationProviderDeliverySpec = {
  "automation": string;
  "project"?: string | null;
  "connector"?: string | null;
  "provider": string;
  "eventType"?: string | null;
  "triggerType"?: "cron" | "git_event" | "pr_event" | "issue_task_event" | "test_failure" | "memory_stale_conflict" | "manual" | "webhook";
  "deliveryId": string;
  "dedupeKey": string;
  "payloadDigest": string;
  "payloadDigestAlgorithm"?: "sha256";
  "receivedAt"?: string | null;
  "firstSeenAt"?: string | null;
  "lastSeenAt"?: string | null;
  "attemptCount"?: number;
  "replayWindowSeconds"?: number | null;
  "replayStatus"?: "accepted" | "duplicate" | "stale" | "blocked";
  "admissionStatus"?: "accepted" | "duplicate" | "blocked";
  "retryStatus"?: "not_requested" | "requested" | "admitted" | "blocked";
  "retryRequestedAt"?: string | null;
  "retryRequestedByMember"?: string | null;
  "retryDelivery"?: string | null;
  "retryAutomationTriggerEvent"?: string | null;
  "retryAutomationRun"?: string | null;
  "retryAttempts"?: Array<Record<string, unknown>>;
  "lifecycle"?: "active" | "archived";
  "retainedUntil"?: string | null;
  "archivedAt"?: string | null;
  "automationTriggerEvent"?: string | null;
  "automationRun"?: string | null;
  "normalized"?: Record<string, unknown>;
  "safeHeaders"?: Record<string, string>;
  "summary"?: string | null;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type AutomationRun = {
  "apiVersion"?: string;
  "kind": "AutomationRun";
  "metadata": Metadata;
  "spec": AutomationRunSpec;
  [key: string]: unknown;
};

export type AutomationRunActionInput = {
  "actorMember"?: string | null;
  "actor_member"?: string | null;
  "sourceEvent"?: Record<string, unknown> | null;
  "source_event"?: Record<string, unknown> | null;
};

export type AutomationRunSpec = {
  "automation": string;
  "project"?: string | null;
  "ownerMember"?: string | null;
  "serviceMember"?: string | null;
  "targetType": "human_reminder" | "digital_execution" | "hybrid_assist" | "service_task" | "memory_health" | "review" | "task_planning" | "manager_recommendation" | "connector_failure_reminder" | "git_activity_correlation_promotion" | "git_activity_retention_sweep" | "artifact_retention_sweep";
  "target"?: Record<string, unknown>;
  "triggerType"?: "cron" | "git_event" | "pr_event" | "issue_task_event" | "test_failure" | "memory_stale_conflict" | "manual" | "webhook";
  "sourceEvent"?: Record<string, unknown>;
  "dryRun"?: boolean;
  "status"?: "dry-run" | "pending-approval" | "queued" | "running" | "succeeded" | "failed" | "blocked";
  "requestedByMember"?: string | null;
  "approvalGates"?: Array<string>;
  "approvals"?: Array<string>;
  "permissionPolicies"?: Array<string>;
  "permissionDecisions"?: Array<Record<string, unknown>>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "createdTask"?: string | null;
  "createdRun"?: string | null;
  "createdTaskPlan"?: string | null;
  "createdMessage"?: string | null;
  "startedAt"?: string | null;
  "finishedAt"?: string | null;
  "summary"?: string | null;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "logs"?: Array<string>;
  "artifacts"?: Array<string>;
  [key: string]: unknown;
};

export type AutomationSchedulerLease = {
  "apiVersion"?: string;
  "kind": "AutomationSchedulerLease";
  "metadata": Metadata;
  "spec": AutomationSchedulerLeaseSpec;
  [key: string]: unknown;
};

export type AutomationSchedulerLeaseSpec = {
  "automation": string;
  "project"?: string | null;
  "triggerType"?: "cron";
  "schedulerId": string;
  "tickKey": string;
  "cron"?: string | null;
  "dueAt"?: string | null;
  "leaseAcquiredAt"?: string | null;
  "leaseExpiresAt"?: string | null;
  "heartbeatAt"?: string | null;
  "status"?: "leased" | "emitted" | "skipped" | "blocked" | "expired";
  "automationTriggerEvent"?: string | null;
  "automationRun"?: string | null;
  "dedupeKey"?: string | null;
  "summary"?: string | null;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type AutomationSpec = {
  "ownerMember"?: string | null;
  "serviceMember"?: string | null;
  "project"?: string | null;
  "targetType": "human_reminder" | "digital_execution" | "hybrid_assist" | "service_task" | "memory_health" | "review" | "task_planning" | "manager_recommendation" | "connector_failure_reminder" | "git_activity_correlation_promotion" | "git_activity_retention_sweep" | "artifact_retention_sweep";
  "target"?: Record<string, unknown>;
  "triggers"?: Array<AutomationTrigger>;
  "dryRun"?: boolean;
  "status"?: "active" | "paused" | "archived";
  "permissionPolicies"?: Array<string>;
  "approvalGates"?: Array<string>;
  [key: string]: unknown;
};

export type AutomationTrigger = {
  "triggerType": "cron" | "git_event" | "pr_event" | "issue_task_event" | "test_failure" | "memory_stale_conflict" | "manual" | "webhook";
  "config"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type AutomationTriggerEvent = {
  "apiVersion"?: string;
  "kind": "AutomationTriggerEvent";
  "metadata": Metadata;
  "spec": AutomationTriggerEventSpec;
  [key: string]: unknown;
};

export type AutomationTriggerEventSpec = {
  "automation": string;
  "project"?: string | null;
  "triggerType"?: "cron" | "git_event" | "pr_event" | "issue_task_event" | "test_failure" | "memory_stale_conflict" | "manual" | "webhook";
  "source"?: "scheduler" | "webhook" | "git_provider" | "manual" | "test" | "system";
  "actorMember"?: string | null;
  "payload"?: Record<string, unknown>;
  "dedupeKey"?: string | null;
  "dryRun"?: boolean;
  "status"?: "accepted" | "ignored" | "blocked";
  "automationRun"?: string | null;
  "receivedAt"?: string | null;
  "summary"?: string | null;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type AutomationTriggerInput = {
  "triggerType": "cron" | "git_event" | "pr_event" | "issue_task_event" | "test_failure" | "memory_stale_conflict" | "manual" | "webhook";
  "config"?: Record<string, unknown>;
};

export type BudgetPolicy = {
  "apiVersion"?: string;
  "kind": "BudgetPolicy";
  "metadata": Metadata;
  "spec": BudgetPolicySpec;
  [key: string]: unknown;
};

export type BudgetPolicyEnforcement = {
  "onSoftLimit"?: "warn" | "stop-run";
  "onHardLimit"?: "stop-run";
};

export type BudgetPolicyFallback = {
  "allowModelFallback"?: boolean;
  "maxFallbacksPerRun"?: number;
};

export type BudgetPolicyLimits = {
  "softUsdPerRun"?: number | null;
  "softUsdPerDay"?: number | null;
  "softInputTokensPerRun"?: number | null;
  "softOutputTokensPerRun"?: number | null;
  "softRetriesPerRun"?: number | null;
  "maxUsdPerRun"?: number | null;
  "maxUsdPerDay"?: number | null;
  "maxInputTokensPerRun"?: number | null;
  "maxOutputTokensPerRun"?: number | null;
  "maxRetriesPerRun"?: number | null;
};

export type BudgetPolicyRateLimit = {
  "requestsPerMinute"?: number | null;
};

export type BudgetPolicyScope = {
  "project"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "task"?: string | null;
};

export type BudgetPolicySpec = {
  "scope": BudgetPolicyScope;
  "limits": BudgetPolicyLimits;
  "rateLimit"?: BudgetPolicyRateLimit;
  "fallback"?: BudgetPolicyFallback;
  "enforcement"?: BudgetPolicyEnforcement;
};

export type Connector = {
  "apiVersion"?: string;
  "kind": "Connector";
  "metadata": Metadata;
  "spec": ConnectorSpec;
  [key: string]: unknown;
};

export type ConnectorEscalationCandidate = {
  "id": string;
  "kind": "ConnectorFailureEscalationCandidate";
  "spec": Record<string, unknown>;
};

export type ConnectorHealthCheck = {
  "apiVersion"?: string;
  "kind": "ConnectorHealthCheck";
  "metadata": Metadata;
  "spec": ConnectorHealthCheckSpec;
  [key: string]: unknown;
};

export type ConnectorHealthCheckSpec = {
  "connector": string;
  "provider": string;
  "connectorType"?: "git" | "issue" | "chat" | "calendar" | "mcp" | "artifact" | "model" | "other";
  "project"?: string | null;
  "checkedAt"?: string | null;
  "status"?: "healthy" | "degraded" | "blocked" | "unknown";
  "readiness"?: "ready" | "degraded" | "blocked" | "unknown";
  "tokenStatus"?: "present" | "missing" | "not_configured" | "not_checked";
  "installationStatus"?: "authorized" | "mismatched" | "not_configured" | "not_checked";
  "lifecycle"?: "active" | "archived";
  "retainedUntil"?: string | null;
  "archivedAt"?: string | null;
  "requiredSecrets"?: Record<string, string>;
  "missingSecrets"?: Array<string>;
  "allowedRepositories"?: Array<string>;
  "observedRepositories"?: Array<string>;
  "allowedInstallationIds"?: Array<string>;
  "observedInstallationIds"?: Array<string>;
  "providerNetworkCalled"?: boolean;
  "providerProbeStatus"?: "passed" | "failed" | "not_configured" | "not_checked";
  "requiredProviderScopes"?: Array<string>;
  "observedProviderScopes"?: Array<string>;
  "missingProviderScopes"?: Array<string>;
  "providerDiagnostics"?: Record<string, unknown>;
  "retentionPolicy"?: Record<string, unknown>;
  "summary"?: string | null;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ConnectorRemediationSuggestion = {
  "id": string;
  "kind": "ConnectorRemediationSuggestion";
  "spec": Record<string, unknown>;
};

export type ConnectorSpec = {
  "provider": string;
  "connectorType"?: "git" | "issue" | "chat" | "calendar" | "mcp" | "artifact" | "model" | "other";
  "ownerMember"?: string | null;
  "projects"?: Array<string>;
  "config"?: Record<string, unknown>;
  "secretRefs"?: Record<string, string>;
  "permissionPolicies"?: Array<string>;
  "gitActivityImport"?: GitActivityImportConnectorPolicy;
  [key: string]: unknown;
};

export type ContextCapsuleInventoryRecord = {
  "run": string;
  "task": string;
  "member": string;
  "assignment"?: string | null;
  "modelProfile"?: string | null;
  "capsulePath"?: string | null;
  "manifestPath"?: string | null;
  "generatedAt"?: string | null;
  "sourcePriority": Array<string>;
  "sourceCounts": Record<string, number>;
  "exclusionCount": number;
  "freshnessSignals": ContextManifestFreshnessSignals;
  "budget": ContextManifestBudget;
  "applicableBudgetPolicy"?: string | null;
  "capsuleSha256"?: string | null;
  "capsuleSizeBytes"?: number | null;
  "contextManifest"?: ContextManifest | null;
  "contentIncluded": boolean;
};

export type ContextManifest = {
  "apiVersion"?: string;
  "kind": "ContextManifest";
  "metadata": Metadata;
  "spec": ContextManifestSpec;
  [key: string]: unknown;
};

export type ContextManifestBudget = {
  "modelProfile"?: string | null;
  "applicablePolicy"?: string | null;
  "policies"?: Array<ContextManifestBudgetPolicy>;
};

export type ContextManifestBudgetPolicy = {
  "id": string;
  "scope": BudgetPolicyScope;
  "limits": BudgetPolicyLimits;
  "rateLimit"?: BudgetPolicyRateLimit;
  "fallback"?: BudgetPolicyFallback;
  "enforcement"?: BudgetPolicyEnforcement;
  "applies"?: boolean;
  "specificity"?: number;
};

export type ContextManifestFreshnessSignals = {
  "generatedAt"?: string | null;
  "recentRunCount"?: number;
  "approvedMemoryCount"?: number;
  "excludedMemoryCount"?: number;
};

export type ContextManifestSpec = {
  "generatedAt"?: string | null;
  "task": string;
  "member": string;
  "memberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "assignment"?: string | null;
  "project"?: string | null;
  "modelProfile"?: string | null;
  "branch"?: string | null;
  "memoryBindings"?: Array<string>;
  "memoryGrants"?: Array<string>;
  "handoffs"?: Array<string>;
  "sourcePriority"?: Array<string>;
  "sources"?: Record<string, Array<unknown>>;
  "sourceDecisions"?: Array<ContextSourceDecision>;
  "sourceCounts"?: Record<string, number>;
  "exclusions"?: Array<string>;
  "freshnessSignals"?: ContextManifestFreshnessSignals;
  "budget"?: ContextManifestBudget;
  "limits"?: Record<string, unknown>;
};

export type ContextSourceDecision = {
  "sourceType": string;
  "sourceRef"?: string | null;
  "outcome": "included" | "excluded";
  "reason": string;
  "category"?: string | null;
  "repo"?: string | null;
  "path"?: string | null;
  "dedupeKey"?: string | null;
  "budgetBucket"?: string | null;
  "rank"?: number | null;
  "score"?: number | null;
  "aclRead"?: Array<string>;
  "lifecycle"?: string | null;
  "freshness"?: string | null;
  "confidence"?: number | null;
  "sensitivity"?: string | null;
  "charsIncluded"?: number | null;
  "charsLimit"?: number | null;
  "truncated"?: boolean | null;
  "snippetPreview"?: string | null;
  "lineStart"?: number | null;
  "lineEnd"?: number | null;
};

export type CostAlertCandidateRecord = {
  "id": string;
  "source"?: "workspace-event-ledger";
  "metricName"?: "aiteamos_model_call_cost_usd_total";
  "project": string;
  "task"?: string | null;
  "run": string;
  "member"?: string | null;
  "assignment"?: string | null;
  "policy": string;
  "thresholdName": "softUsdPerRun" | "maxUsdPerRun";
  "thresholdKind": "soft" | "hard";
  "limitUsd": number;
  "costUsd": number;
  "usageRatio": number;
  "targetMembers"?: Array<string>;
  "existingMessage"?: string | null;
  "suppressed"?: boolean;
  "status"?: "routable" | "suppressed-by-open-message";
  "severity"?: "warning" | "critical";
  "dedupeKey": string;
};

export type CostAlertOverviewRecord = {
  "source"?: "workspace-event-ledger";
  "metricName"?: "aiteamos_model_call_cost_usd_total";
  "summary"?: Record<string, unknown>;
  "candidates"?: Array<CostAlertCandidateRecord>;
};

export type CostAlertRouteInput = {
  "actorMember"?: string | null;
  "actor_member"?: string | null;
  "project"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "task"?: string | null;
  "maxMessagesPerRun"?: number | null;
  "max_messages_per_run"?: number | null;
  "dryRun"?: boolean;
  "dry_run"?: boolean | null;
};

export type DecisionAuditRecord = {
  "decisionKind": "human_approval" | "digital_recommendation" | "service_policy_decision" | "system_check";
  "decision": string;
  "actorMember"?: string | null;
  "actorMemberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "authority"?: "approve" | "recommend" | "enforce" | "record" | "revoke" | "expire";
  "decidedAt"?: string | null;
  "reason"?: string | null;
  "source"?: string | null;
  "policyRefs"?: Array<string>;
  "evidence"?: Array<Record<string, unknown>>;
  "requiresHumanReview"?: boolean;
  "riskAssessment"?: RiskAssessment | null;
  "risk"?: Record<string, unknown>;
  "metadata"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type DigitalExecutionProfile = {
  "apiVersion"?: string;
  "kind": "DigitalExecutionProfile";
  "metadata": Metadata;
  "spec": DigitalExecutionProfileSpec;
  [key: string]: unknown;
};

export type DigitalExecutionProfileSpec = {
  "member": string;
  "defaultModelProfile"?: string | null;
  "allowedModelProfiles"?: Array<string>;
  "workerRuntime"?: Record<string, unknown>;
  "contextCompiler"?: Record<string, unknown>;
  "toolPolicy"?: Record<string, unknown>;
  "promptPolicy"?: Record<string, unknown>;
  "connectors"?: Array<string>;
  "budgetPolicies"?: Array<string>;
  [key: string]: unknown;
};

export type EvalCase = {
  "id"?: string | null;
  "title": string;
  "task"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "input"?: Record<string, unknown>;
  "expected"?: Record<string, unknown>;
  "goldenOutputs"?: Record<string, unknown>;
  "goldenOutputRefs"?: Array<string>;
  "tags"?: Array<string>;
  [key: string]: unknown;
};

export type EvalCaseResult = {
  "caseId"?: string | null;
  "caseTitle"?: string | null;
  "status"?: "pass" | "fail" | "skip";
  "score"?: number | null;
  "evidence"?: Array<string>;
  "message"?: string | null;
  [key: string]: unknown;
};

export type EvalJudge = {
  "kind"?: "human" | "model" | "policy";
  "member"?: string | null;
  "modelProfile"?: string | null;
  "policyRef"?: string | null;
  "rubric"?: Array<string>;
  "passCriteria"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type EvalResult = {
  "apiVersion"?: string;
  "kind": "EvalResult";
  "metadata": Metadata;
  "spec": EvalResultSpec;
  [key: string]: unknown;
};

export type EvalResultSpec = {
  "evalSuite": string;
  "project": string;
  "evaluatedAt"?: string | null;
  "task"?: string | null;
  "run"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "status"?: "pass" | "fail" | "mixed";
  "totalCases"?: number;
  "passedCases"?: number;
  "failedCases"?: number;
  "passRate"?: number;
  "caseResults"?: Array<EvalCaseResult>;
  "evidence"?: Array<string>;
  "summary"?: string | null;
  [key: string]: unknown;
};

export type EvalSuite = {
  "apiVersion"?: string;
  "kind": "EvalSuite";
  "metadata": Metadata;
  "spec": EvalSuiteSpec;
  [key: string]: unknown;
};

export type EvalSuitePolicy = {
  "autoPromoteThreshold"?: number | null;
  "minCases"?: number;
  "requireAllGoldenOutputs"?: boolean;
  [key: string]: unknown;
};

export type EvalSuiteRequirement = {
  "evalSuite": string;
  "paths"?: Array<string>;
  "minimumPassRate"?: number | null;
  "description"?: string | null;
  [key: string]: unknown;
};

export type EvalSuiteRequirementStatus = {
  "evalSuite": string;
  "paths"?: Array<string>;
  "matchedPaths"?: Array<string>;
  "threshold"?: number | null;
  "lastResultId"?: string | null;
  "passRate"?: number | null;
  "status": "pass" | "fail" | "skip";
  "message": string;
};

export type EvalSuiteSpec = {
  "project": string;
  "purpose"?: string | null;
  "members"?: Array<string>;
  "assignments"?: Array<string>;
  "tasks"?: Array<string>;
  "cases"?: Array<EvalCase>;
  "goldenOutputs"?: Record<string, unknown>;
  "judge"?: EvalJudge;
  "policy"?: EvalSuitePolicy;
  "metrics"?: Array<string>;
  [key: string]: unknown;
};

export type GateCheck = {
  "name": string;
  "status": string;
  "message": string;
};

export type GitActivity = {
  "apiVersion"?: string;
  "kind": "GitActivity";
  "metadata": Metadata;
  "spec": GitActivitySpec;
  [key: string]: unknown;
};

export type GitActivityCorrelationGroup = {
  "correlationKey": string;
  "project": string;
  "repository"?: string | null;
  "provider"?: string | null;
  "connector"?: string | null;
  "receipts"?: Array<string>;
  "importedActivities"?: Array<string>;
  "eventFamilies"?: Array<string>;
  "members"?: Array<string>;
  "assignments"?: Array<string>;
  "refs"?: Array<string>;
  "commits"?: Array<string>;
  "pullRequests"?: Array<string>;
  "externalIds"?: Array<string>;
  "signals"?: Array<GitActivityCorrelationSignal>;
  "forcePushRisk"?: boolean;
  "squashMergeRisk"?: boolean;
  "multiEventRisk"?: boolean;
  "summary": string;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
};

export type GitActivityCorrelationPreviewRecord = {
  "generatedAt": string;
  "filters"?: Record<string, unknown>;
  "groups": Array<GitActivityCorrelationGroup>;
};

export type GitActivityCorrelationReview = {
  "apiVersion"?: string;
  "kind": "GitActivityCorrelationReview";
  "metadata": Metadata;
  "spec": GitActivityCorrelationReviewSpec;
  [key: string]: unknown;
};

export type GitActivityCorrelationReviewSpec = {
  "project": string;
  "repository"?: string | null;
  "provider"?: string | null;
  "connector"?: string | null;
  "correlationKey": string;
  "receipts"?: Array<string>;
  "importedActivities"?: Array<string>;
  "decision"?: "approved" | "rejected" | "needs-changes" | "archived";
  "reviewerMember": string;
  "reviewerMemberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "reviewedAt"?: string | null;
  "eventFamilies"?: Array<string>;
  "members"?: Array<string>;
  "assignments"?: Array<string>;
  "refs"?: Array<string>;
  "commits"?: Array<string>;
  "pullRequests"?: Array<string>;
  "externalIds"?: Array<string>;
  "signals"?: Array<GitActivityCorrelationSignal>;
  "riskFlags"?: Array<"force-push" | "squash-merge" | "multi-event" | "blocked-receipt" | "imported-activity" | "manual-review-required">;
  "recommendedPromotion"?: Record<string, unknown>;
  "summary": string;
  "evidence"?: Array<string>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type GitActivityCorrelationSignal = {
  "kind": string;
  "value": string;
  "weight"?: number;
  "sourceReceipt"?: string | null;
  "evidence"?: Record<string, unknown>;
};

export type GitActivityImportConnectorPolicy = {
  "enabled"?: boolean;
  "allowedRepositories"?: Array<string>;
  "allowedInstallationIds"?: Array<string>;
  "protectedRefPatterns"?: Array<string>;
  "actorMappings"?: Array<GitProviderActorMapping>;
  "defaultMember"?: string | null;
  "defaultAssignment"?: string | null;
  "importPolicy"?: "reviewed-import" | "service-policy-import";
  "autoPromotion"?: "disabled" | "service-policy";
  "dedupeStrategy"?: Array<"payload-digest" | "external-id" | "commit-ref" | "pr-number" | "squash-merge">;
  "requireHealthyConnector"?: boolean;
  [key: string]: unknown;
};

export type GitActivityImportReceipt = {
  "apiVersion"?: string;
  "kind": "GitActivityImportReceipt";
  "metadata": Metadata;
  "spec": GitActivityImportReceiptSpec;
  [key: string]: unknown;
};

export type GitActivityImportReceiptSpec = {
  "project": string;
  "repository"?: string | null;
  "provider": string;
  "connector"?: string | null;
  "sourceType"?: "provider-sync" | "webhook" | "manual-import" | "local-scan";
  "status"?: "candidate" | "needs-review" | "imported" | "blocked" | "duplicate" | "archived";
  "dedupeKey": string;
  "payloadDigest": string;
  "payloadDigestAlgorithm"?: "sha256";
  "redactionPolicy"?: "metadata-only" | "redacted-summary" | "artifact-reference";
  "importPolicy"?: "reviewed-import" | "service-policy-import" | "manual-record";
  "payloadRetained"?: boolean;
  "rawPayloadArtifact"?: string | null;
  "retainedUntil"?: string | null;
  "receivedAt"?: string | null;
  "reviewedByMember"?: string | null;
  "reviewedAt"?: string | null;
  "serviceMember"?: string | null;
  "importerMember"?: string | null;
  "importedActivities"?: Array<string>;
  "refs"?: Array<string>;
  "normalized"?: Record<string, unknown>;
  "summary"?: string | null;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "evidence"?: Array<string>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type GitActivitySpec = {
  "member": string;
  "project": string;
  "repository"?: string | null;
  "assignment"?: string | null;
  "activityType": "commit" | "branch" | "pull-request" | "review-comment" | "merge" | "tag" | "other";
  "provider"?: string | null;
  "externalId"?: string | null;
  "url"?: string | null;
  "occurredAt"?: string | null;
  "summary": string;
  "refs"?: Array<string>;
  "evidence"?: Array<string>;
  "visibility"?: "member" | "project" | "team" | "organization";
  "lifecycle"?: "active" | "archived" | "redacted";
  "retainedUntil"?: string | null;
  "archivedAt"?: string | null;
  "redactedAt"?: string | null;
  "redactionPolicy"?: ("metadata-only" | "redacted-summary" | "artifact-reference") | null;
  "exportPolicy"?: "include" | "sanitize" | "manifest-only" | "exclude";
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type GitProviderActorMapping = {
  "actorLogin"?: string | null;
  "actorLoginSha256"?: string | null;
  "actorEmailSha256"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "policy"?: "map-to-member" | "needs-review" | "ignore";
  "reason"?: string | null;
  [key: string]: unknown;
};

export type Handoff = {
  "apiVersion"?: string;
  "kind": "Handoff";
  "metadata": Metadata;
  "spec": HandoffSpec;
  [key: string]: unknown;
};

export type HandoffSpec = {
  "fromMember": string;
  "toMember": string;
  "task": string;
  "run"?: string | null;
  "project"?: string | null;
  "sourceBranch"?: string | null;
  "targetBranch"?: string | null;
  "problem": string;
  "knownContext"?: Array<string>;
  "recommendedNextStep"?: string | null;
  "sharedMemoryPack"?: Array<string>;
  "ownership"?: "transfer" | "copy" | "consult";
  "status"?: "requested" | "accepted" | "declined" | "completed" | "cancelled";
  "lifecycle"?: "active" | "archived" | "redacted";
  "archivedAt"?: string | null;
  "redactedAt"?: string | null;
  "redactionPolicy"?: string | null;
  "exportPolicy"?: "include" | "sanitize" | "manifest-only" | "exclude";
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type HumanCollaborationProfile = {
  "apiVersion"?: string;
  "kind": "HumanCollaborationProfile";
  "metadata": Metadata;
  "spec": HumanCollaborationProfileSpec;
  [key: string]: unknown;
};

export type HumanCollaborationProfileSpec = {
  "member": string;
  "contact"?: Record<string, unknown>;
  "ideEntrypoints"?: Array<string>;
  "reviewAuthority"?: Array<string>;
  "approvalScopes"?: Array<string>;
  "availability"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type HybridExecutionProfile = {
  "apiVersion"?: string;
  "kind": "HybridExecutionProfile";
  "metadata": Metadata;
  "spec": HybridExecutionProfileSpec;
  [key: string]: unknown;
};

export type HybridExecutionProfileSpec = {
  "member": string;
  "humanProfile"?: string | null;
  "assistedTools"?: Array<string>;
  "ingestPolicy"?: Record<string, unknown>;
  "aiAssistancePolicy"?: Record<string, unknown>;
  "reviewExpectations"?: Array<string>;
  [key: string]: unknown;
};

export type KnowledgeHealthIssue = {
  "severity": string;
  "kind": string;
  "ref": string;
  "message": string;
  "action": string;
};

export type KnowledgeHealthRecord = {
  "generatedAt": string;
  "summary": KnowledgeHealthSummary;
  "issues": Array<KnowledgeHealthIssue>;
};

export type KnowledgeHealthRemediationInput = {
  "issueKind": string;
  "ref": string;
  "action": "verify-entry" | "mark-entry-stale" | "archive-binding" | "revoke-grant";
  "actorMember": string;
  "reason": string;
  "dryRun"?: boolean;
};

export type KnowledgeHealthRemediationRecord = {
  "generatedAt": string;
  "issueKind": string;
  "ref": string;
  "action": "verify-entry" | "mark-entry-stale" | "archive-binding" | "revoke-grant";
  "actorMember": string;
  "dryRun": boolean;
  "applied": boolean;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "issue"?: KnowledgeHealthIssue | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "result"?: Record<string, unknown>;
};

export type KnowledgeHealthSummary = {
  "memoryEntries"?: number;
  "approvedMemory": number;
  "pendingProposals": number;
  "activeBindings"?: number;
  "activeGrants"?: number;
  "staleMemory"?: number;
  "conflictedMemory"?: number;
  "sensitiveMemory"?: number;
  "orphanedBindings"?: number;
  "orphanedGrants"?: number;
  "expiredGrants"?: number;
  "issues": number;
  "warnings": number;
  "errors": number;
};

export type LearningExtraction = {
  "apiVersion"?: string;
  "kind": "LearningExtraction";
  "metadata": Metadata;
  "spec": LearningExtractionSpec;
  [key: string]: unknown;
};

export type LearningExtractionProposal = {
  "kind": "memory" | "skill" | "growth" | "retrospective";
  "targetKind"?: string | null;
  "targetManifest": Record<string, unknown>;
  "summary"?: string | null;
  "confidence"?: number | null;
  "evidence"?: Array<string>;
  "dedupeKey"?: string | null;
  "reviewGuidance"?: string | null;
  "warnings"?: Array<string>;
  [key: string]: unknown;
};

export type LearningExtractionSourceContext = {
  "project"?: string | null;
  "taskId"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "runStatus"?: string | null;
  "sourceJournalPath"?: string | null;
  "sourceEventLedger"?: string | null;
  [key: string]: unknown;
};

export type LearningExtractionSpec = {
  "runId": string;
  "extractedAt": string;
  "dedupeKey": string;
  "extractorId"?: string;
  "extractorVersion"?: string;
  "sourceContext"?: LearningExtractionSourceContext;
  "proposals"?: Array<LearningExtractionProposal>;
  "warnings"?: Array<string>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type ManagerInputBundle = {
  "generatedAt": string;
  "manager": string;
  "project": string;
  "assignment"?: string | null;
  "filters": Record<string, unknown>;
  "workspaceHealth": WorkspaceHealth;
  "reviewGates": Array<RunReviewGateRecord>;
  "connectorEscalationCandidates": Array<ConnectorEscalationCandidate>;
  "connectorEscalationSummary": Record<string, number>;
  "connectorRemediationSuggestions": Array<ConnectorRemediationSuggestion>;
  "connectorRemediationSummary": Record<string, number>;
  "retrospectiveSuggestions": Array<RetrospectiveSuggestionRecord>;
  "memberGrowthSupportSignals": MemberGrowthSupportSignals;
  "managerEvaluation"?: Record<string, unknown>;
  "readOnly"?: boolean;
  "sourceRefs": Array<string>;
};

export type MemberAboutMe = {
  "coreCapabilities"?: Array<string>;
  "workStyle"?: Array<string>;
  "workMethod"?: Array<string>;
  [key: string]: unknown;
};

export type MemberActivity = {
  "apiVersion"?: string;
  "kind": "MemberActivity";
  "metadata": Metadata;
  "spec": MemberActivitySpec;
  [key: string]: unknown;
};

export type MemberActivitySpec = {
  "member": string;
  "project"?: string | null;
  "assignment"?: string | null;
  "task"?: string | null;
  "run"?: string | null;
  "activityType": string;
  "sourceType"?: "task" | "run" | "review" | "memory-proposal" | "message" | "handoff" | "retrospective" | "automation" | "git" | "manual";
  "contributionKind"?: "authored-work" | "review-work" | "support-work" | "automation-work" | "knowledge-work" | "coordination-work" | "git-work" | "other";
  "sourceId"?: string | null;
  "occurredAt"?: string | null;
  "summary": string;
  "evidence"?: Array<string>;
  "visibility"?: "member" | "project" | "team" | "organization";
  [key: string]: unknown;
};

export type MemberCapability = {
  "name": string;
  "level"?: string | null;
  "evidence"?: Array<string>;
  "relatedSkills"?: Array<string>;
  [key: string]: unknown;
};

export type MemberDeleteRequestInput = {
  "actorMember": string;
  "reason"?: string | null;
};

export type MemberDeleteRequestRecord = {
  "member": string;
  "actorMember": string;
  "requestedAt": string;
  "status": "redacted";
  "references"?: Record<string, Array<string>>;
  "redactionQueue"?: Array<MemberDeleteRequestReference>;
  "updated"?: Record<string, number>;
  "decisionAudit": DecisionAuditRecord;
};

export type MemberDeleteRequestReference = {
  "kind": "Run" | "MemberMessage" | "Handoff" | "GitActivity" | "Assignment" | "MemoryBinding";
  "id": string;
  "path": string;
  "action": "archive" | "redact";
};

export type MemberGrowthPlanAction = {
  "id": string;
  "actionType": "complete-assisted-ingest" | "review-memory-proposals" | "review-run-recovery" | "close-collaboration-loops" | "review-work-in-progress-load" | "capture-reviewed-growth-note" | "review-skill-fit";
  "label": string;
  "rationale": string;
  "status"?: "ready" | "suggested" | "blocked";
  "evidence"?: Array<string>;
  "relatedTasks"?: Array<string>;
  "relatedRuns"?: Array<string>;
  "relatedReviews"?: Array<string>;
  "relatedMemoryProposals"?: Array<string>;
  "relatedMessages"?: Array<string>;
  "relatedHandoffs"?: Array<string>;
  "relatedSkills"?: Array<string>;
};

export type MemberGrowthProjectionItem = {
  "member": string;
  "memberKind": "human" | "digital" | "hybrid" | "service";
  "project"?: string | null;
  "assignments": Array<string>;
  "activityCounts": Record<string, number>;
  "contributionCounts": Record<string, number>;
  "supportSignals": Array<string>;
  "growthPlanActions": Array<MemberGrowthPlanAction>;
  "growthRecords": Array<MemberGrowthRecord>;
  "declaredPerformanceMetrics": Array<MemberPerformanceMetric>;
  "evidence": Array<string>;
  "warnings": Array<string>;
};

export type MemberGrowthProjectionRecord = {
  "generatedAt": string;
  "filters": Record<string, unknown>;
  "summary": Record<string, number>;
  "nonPunitivePolicy": Array<string>;
  "items": Array<MemberGrowthProjectionItem>;
};

export type MemberGrowthRecord = {
  "recordedAt"?: string | null;
  "project"?: string | null;
  "summary": string;
  "evidence"?: Array<string>;
  "sourceAction"?: string | null;
  "sourceTask"?: string | null;
  "sourceRun"?: string | null;
  "sourceReview"?: string | null;
  "sourceMemoryProposal"?: string | null;
  "sourceSkill"?: string | null;
  "reviewedByMember"?: string | null;
  "reviewedAt"?: string | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type MemberGrowthRecordInput = {
  "actorMember": string;
  "summary": string;
  "project"?: string | null;
  "sourceAction"?: string | null;
  "sourceTask"?: string | null;
  "sourceRun"?: string | null;
  "sourceReview"?: string | null;
  "sourceMemoryProposal"?: string | null;
  "sourceSkill"?: string | null;
  "evidence"?: Array<string>;
  "reason"?: string | null;
};

export type MemberGrowthSupportSignals = {
  "generatedAt": string;
  "filters": Record<string, unknown>;
  "summary": Record<string, number>;
  "nonPunitivePolicy": Array<string>;
  "items": Array<MemberGrowthProjectionItem>;
};

export type MemberMessage = {
  "apiVersion"?: string;
  "kind": "MemberMessage";
  "metadata": Metadata;
  "spec": MemberMessageSpec;
  [key: string]: unknown;
};

export type MemberMessageSpec = {
  "fromMember": string;
  "toMembers"?: Array<string>;
  "channel"?: string | null;
  "messageType"?: "message" | "ask-for-help" | "review-request" | "knowledge-share" | "handoff-note" | "plan-recommendation" | "cost-alert";
  "status"?: "open" | "acknowledged" | "resolved" | "archived";
  "priority"?: "low" | "normal" | "high" | "urgent";
  "project"?: string | null;
  "task"?: string | null;
  "run"?: string | null;
  "body": string;
  "attachments"?: Array<string>;
  "requestedResponseBy"?: string | null;
  "resolvedAt"?: string | null;
  "resolvedByMember"?: string | null;
  "resolution"?: string | null;
  "audit"?: Record<string, unknown>;
  "lifecycle"?: "active" | "archived" | "redacted";
  "archivedAt"?: string | null;
  "redactedAt"?: string | null;
  "redactionPolicy"?: string | null;
  "exportPolicy"?: "include" | "sanitize" | "manifest-only" | "exclude";
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type MemberPerformanceMetric = {
  "name": string;
  "value"?: string | number | boolean | null;
  "period"?: string | null;
  "source"?: string | null;
  [key: string]: unknown;
};

export type MemberProfile = {
  "displayName"?: string | null;
  "title"?: string | null;
  "avatarUrl"?: string | null;
  "timezone"?: string | null;
  "status"?: "active" | "inactive" | "archived";
  "summary"?: string | null;
  [key: string]: unknown;
};

export type MemberProjectEngagement = {
  "project": string;
  "assignments"?: Array<string>;
  "responsibilities"?: Array<string>;
  "status"?: string;
  [key: string]: unknown;
};

export type MemberWorkMethod = {
  "methods"?: Array<string>;
  "notes"?: string | null;
  [key: string]: unknown;
};

export type MemberWorkStyle = {
  "traits"?: Array<string>;
  "notes"?: string | null;
  [key: string]: unknown;
};

export type MemoryACL = {
  "read"?: Array<string>;
  "write"?: Array<string>;
  "reference"?: Array<string>;
  "promote"?: Array<string>;
  "export"?: Array<string>;
  "share"?: Array<string>;
  [key: string]: unknown;
};

export type MemoryBinding = {
  "apiVersion"?: string;
  "kind": "MemoryBinding";
  "metadata": Metadata;
  "spec": MemoryBindingSpec;
  [key: string]: unknown;
};

export type MemoryBindingSpec = {
  "store"?: string | null;
  "entry"?: string | null;
  "collectionPath"?: string | null;
  "targetType": "member" | "project" | "assignment" | "task" | "run" | "team" | "context-capsule";
  "targetId": string;
  "access"?: Array<"read" | "write" | "reference" | "inject" | "promote" | "export" | "share">;
  "reason"?: string | null;
  "status"?: "active" | "paused" | "revoked" | "archived";
  "createdByMember"?: string | null;
  [key: string]: unknown;
};

export type MemoryEntry = {
  "apiVersion"?: string;
  "kind": "MemoryEntry";
  "metadata": Metadata;
  "spec": MemoryEntrySpec;
  [key: string]: unknown;
};

export type MemoryEntryCreateInput = {
  "title": string;
  "content": string;
  "actorMember": string;
  "store": string;
  "path"?: string | null;
  "kind"?: "semantic" | "episodic" | "procedural" | "decision" | "mistake" | "preference" | "skill" | "project-status" | "external-note";
  "scope"?: "member" | "project" | "team" | "org" | "domain" | "task" | "run";
  "source"?: string | null;
  "evidence"?: Array<string>;
  "confidence"?: number | null;
  "freshness"?: string | null;
  "sensitivity"?: "public" | "internal" | "confidential" | "secret";
  "visibility"?: "private" | "project" | "team" | "organization" | "public";
  "acl"?: MemoryACL;
  "tags"?: Array<string>;
  "relatedProjects"?: Array<string>;
  "relatedMembers"?: Array<string>;
  "relatedAssignments"?: Array<string>;
  "lifecycle"?: "candidate" | "active" | "stale" | "deprecated" | "conflicted" | "redacted" | "archived";
  "reason"?: string | null;
  "bindTargetType"?: ("member" | "project" | "assignment" | "task" | "run" | "team" | "context-capsule") | null;
  "bindTargetId"?: string | null;
  "bindAccess"?: Array<"read" | "write" | "reference" | "inject" | "promote" | "export" | "share">;
  "bindReason"?: string | null;
};

export type MemoryEntrySpec = {
  "store": string;
  "path": string;
  "title": string;
  "content": string;
  "kind": "semantic" | "episodic" | "procedural" | "decision" | "mistake" | "preference" | "skill" | "project-status" | "external-note";
  "scope": "member" | "project" | "team" | "org" | "domain" | "task" | "run";
  "source"?: string | null;
  "evidence"?: Array<string>;
  "evalEvidence"?: Array<MemoryEvalEvidenceRef>;
  "confidence"?: number | null;
  "freshness"?: string | null;
  "lastVerifiedAt"?: string | null;
  "sensitivity"?: "public" | "internal" | "confidential" | "secret";
  "visibility"?: "private" | "project" | "team" | "organization" | "public";
  "acl"?: MemoryACL;
  "tags"?: Array<string>;
  "relatedProjects"?: Array<string>;
  "relatedMembers"?: Array<string>;
  "relatedAssignments"?: Array<string>;
  "version"?: number;
  "lineage"?: MemoryLineageRef;
  "supersedes"?: Array<string>;
  "conflictsWith"?: Array<string>;
  "lifecycle"?: "candidate" | "active" | "stale" | "deprecated" | "conflicted" | "redacted" | "archived";
  "embedding"?: Record<string, unknown>;
  "createdByMember"?: string | null;
  "reviewReason"?: string | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type MemoryEvalEvidenceRef = {
  "evalSuiteId": string;
  "lastResultId": string;
  "passRate"?: number | null;
  "threshold"?: number | null;
  [key: string]: unknown;
};

export type MemoryGrant = {
  "apiVersion"?: string;
  "kind": "MemoryGrant";
  "metadata": Metadata;
  "spec": MemoryGrantSpec;
  [key: string]: unknown;
};

export type MemoryGrantSpec = {
  "granteeMember": string;
  "grantorMember"?: string | null;
  "task"?: string | null;
  "run"?: string | null;
  "stores"?: Array<string>;
  "entries"?: Array<string>;
  "access"?: Array<"read" | "reference" | "inject">;
  "reason"?: string | null;
  "expiresAt"?: string | null;
  "status"?: "active" | "expired" | "revoked";
  [key: string]: unknown;
};

export type MemoryLineageRef = {
  "sourceRun"?: string | null;
  "sourceTask"?: string | null;
  "authorMember"?: string | null;
  "reviewerMember"?: string | null;
  "evidence"?: Array<string>;
  "relatedDiffs"?: Array<string>;
  "relatedTests"?: Array<string>;
  "relatedReviews"?: Array<string>;
  [key: string]: unknown;
};

export type MemoryProposal = {
  "apiVersion"?: string;
  "kind": "MemoryProposal";
  "metadata": Metadata;
  "spec": MemoryProposalSpec;
  [key: string]: unknown;
};

export type MemoryProposalSpec = {
  "project": string;
  "member"?: string | null;
  "assignment"?: string | null;
  "store"?: string | null;
  "entryPath"?: string | null;
  "sourceRun"?: string | null;
  "sourceTask"?: string | null;
  "sourceIngestId"?: string | null;
  "sourceExtractorId"?: string | null;
  "dedupeKey"?: string | null;
  "status"?: string;
  "approvedMemory"?: string | null;
  "kind": string;
  "title": string;
  "content": string;
  "evidence"?: Array<string>;
  "confidence"?: number | null;
  "reviewGuidance"?: string | null;
  "reviewedAt"?: string | null;
  "reviewedByMember"?: string | null;
  "reviewReason"?: string | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type MemoryStore = {
  "apiVersion"?: string;
  "kind": "MemoryStore";
  "metadata": Metadata;
  "spec": MemoryStoreSpec;
  [key: string]: unknown;
};

export type MemoryStoreCreateInput = {
  "name": string;
  "actorMember": string;
  "storeType": "project" | "member" | "team" | "domain" | "organization" | "temporary" | "imported";
  "ownerProject"?: string | null;
  "ownerMember"?: string | null;
  "ownerTeam"?: string | null;
  "domain"?: string | null;
  "description"?: string | null;
  "visibility"?: "private" | "project" | "team" | "organization" | "public";
  "lifecycle"?: "active" | "stale" | "deprecated" | "redacted" | "archived";
  "acl"?: MemoryACL;
  "retention"?: Record<string, unknown>;
  "reason"?: string | null;
};

export type MemoryStoreSpec = {
  "storeType": "project" | "member" | "team" | "domain" | "organization" | "temporary" | "imported";
  "ownerProject"?: string | null;
  "ownerMember"?: string | null;
  "ownerTeam"?: string | null;
  "domain"?: string | null;
  "description"?: string | null;
  "visibility"?: "private" | "project" | "team" | "organization" | "public";
  "lifecycle"?: "active" | "stale" | "deprecated" | "redacted" | "archived";
  "acl"?: MemoryACL;
  "retention"?: Record<string, unknown>;
  "createdByMember"?: string | null;
  "reviewReason"?: string | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type MemoryVersion = {
  "apiVersion"?: string;
  "kind": "MemoryVersion";
  "metadata": Metadata;
  "spec": MemoryVersionSpec;
  [key: string]: unknown;
};

export type MemoryVersionSpec = {
  "entry": string;
  "store": string;
  "version": number;
  "operation": "create" | "update" | "delete" | "redact";
  "contentSha256"?: string | null;
  "createdAt"?: string | null;
  "createdByMember"?: string | null;
  "redacted"?: boolean;
  [key: string]: unknown;
};

export type Metadata = {
  "name"?: string | null;
  "id"?: string | null;
  "title"?: string | null;
  "createdAt"?: string | null;
  [key: string]: unknown;
};

export type ModelCostRow = {
  "attempts": number;
  "calls": number;
  "failures": number;
  "fallbacks": number;
  "inputTokens": number;
  "outputTokens": number;
  "totalTokens": number;
  "costUsd": number;
  "latencyMsAvg"?: number | null;
  "successRate"?: number | null;
  "provider"?: string | null;
  "model"?: string | null;
  "run"?: string | null;
  "task"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "profile"?: string | null;
  "lastEventTs"?: string | null;
};

export type ModelCostSummaryRecord = {
  "source": string;
  "totals": ModelCostRow;
  "byModel": Array<ModelCostRow>;
  "byRun": Array<ModelCostRow>;
};

export type ModelProfile = {
  "apiVersion"?: string;
  "kind": "ModelProfile";
  "metadata": Metadata;
  "spec": ModelProfileSpec;
  [key: string]: unknown;
};

export type ModelProfilePricing = {
  "currency"?: "USD";
  "inputUsdPer1MTokens"?: number | null;
  "outputUsdPer1MTokens"?: number | null;
  "requestUsd"?: number | null;
};

export type ModelProfileSpec = {
  "provider": string;
  "model": string;
  "displayName"?: string | null;
  "gateway"?: string;
  "secretEnv"?: string | null;
  "invocation"?: Record<string, unknown>;
  "pricing"?: ModelProfilePricing | null;
  "capabilities"?: Array<string>;
  "defaultForMembers"?: Array<string>;
  "defaultForAssignments"?: Array<string>;
  "notes"?: string | null;
  [key: string]: unknown;
};

export type PermissionAction = {
  "tool"?: string | null;
  "value"?: string | null;
  "path"?: string | null;
  "command"?: string | null;
  "url"?: string | null;
  "domain"?: string | null;
  "port"?: number | null;
  "protocol"?: string | null;
  "mcpServer"?: string | null;
  "mcpTool"?: string | null;
  "envVar"?: string | null;
  "connector"?: string | null;
  "connectorType"?: string | null;
  "connectorScope"?: string | null;
  "artifactStore"?: string | null;
  "artifactKind"?: string | null;
  "retentionPolicy"?: string | null;
  "exportPolicy"?: ("include" | "sanitize" | "manifest_only" | "exclude") | null;
  "redactionMode"?: string | null;
  "sensitivity"?: string | null;
  "operation"?: string | null;
  "target"?: string | null;
  "resource"?: string | null;
  "risk"?: ("low" | "medium" | "high" | "critical") | null;
  "metadata"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type PermissionGrant = {
  "apiVersion"?: string;
  "kind": "PermissionGrant";
  "metadata": Metadata;
  "spec": PermissionGrantSpec;
  [key: string]: unknown;
};

export type PermissionGrantSpec = {
  "scope"?: Record<string, string>;
  "action"?: PermissionAction;
  "sourceRequest"?: string | null;
  "approvedByMember"?: string | null;
  "reason"?: string | null;
  "status"?: "active" | "revoked" | "expired";
  "expiresAt"?: string | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type PermissionPolicy = {
  "apiVersion"?: string;
  "kind": "PermissionPolicy";
  "metadata": Metadata;
  "spec": PermissionPolicySpec;
  [key: string]: unknown;
};

export type PermissionPolicySpec = {
  "scope"?: Record<string, string>;
  "defaultMode"?: "allow" | "ask" | "deny";
  "allow"?: Array<PermissionRule>;
  "ask"?: Array<PermissionRule>;
  "deny"?: Array<PermissionRule>;
  "sensitivePaths"?: Array<string>;
  "inheritance"?: Record<string, unknown>;
  "expiresAt"?: string | null;
  [key: string]: unknown;
};

export type PermissionRequest = {
  "apiVersion"?: string;
  "kind": "PermissionRequest";
  "metadata": Metadata;
  "spec": PermissionRequestSpec;
  [key: string]: unknown;
};

export type PermissionRequestSpec = {
  "project"?: string | null;
  "member": string;
  "assignment"?: string | null;
  "task"?: string | null;
  "run"?: string | null;
  "automation"?: string | null;
  "automationRun"?: string | null;
  "approvalWorkflow"?: string | null;
  "requesterMember"?: string | null;
  "reviewerMember"?: string | null;
  "action"?: PermissionAction;
  "reason"?: string | null;
  "status"?: "pending" | "approved" | "rejected" | "cancelled" | "expired";
  "currentDecision"?: Record<string, unknown>;
  "decidedAt"?: string | null;
  "expiresAt"?: string | null;
  "grant"?: string | null;
  "source"?: string | null;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type PermissionRule = {
  "match": string;
  "reason"?: string | null;
  [key: string]: unknown;
};

export type ProductUser = {
  "apiVersion"?: string;
  "kind": "ProductUser";
  "metadata": Metadata;
  "spec": ProductUserSpec;
  [key: string]: unknown;
};

export type ProductUserArchiveInput = {
  "actorMember": string;
  "reason"?: string | null;
};

export type ProductUserCreateInput = {
  "name": string;
  "actorMember": string;
  "displayName"?: string | null;
  "member"?: string | null;
  "identityProvider"?: string;
  "identitySubjectHash"?: string | null;
  "status"?: "active" | "disabled" | "archived";
  "roles"?: Array<"admin" | "viewer" | "governance_reviewer" | "operator" | "auditor">;
  "sessionTokenEnv"?: string | null;
  "governanceScopes"?: Array<string>;
  "reason"?: string | null;
};

export type ProductUserManagementAudit = {
  "action": "create-product-user" | "update-product-user" | "archive-product-user";
  "actorMember": string;
  "actorMemberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "decisionKind"?: "human_approval" | "digital_recommendation" | "service_policy_decision";
  "authority"?: "approve" | "recommend" | "enforce";
  "decidedAt"?: string | null;
  "reason"?: string | null;
  "permissionDecision"?: ("allow" | "ask" | "deny") | null;
  "policyRefs"?: Array<string>;
  "targetUser"?: string | null;
  [key: string]: unknown;
};

export type ProductUserSpec = {
  "displayName"?: string | null;
  "member"?: string | null;
  "identityProvider"?: string;
  "identitySubjectHash"?: string | null;
  "status"?: "active" | "disabled" | "archived";
  "roles"?: Array<"admin" | "viewer" | "governance_reviewer" | "operator" | "auditor">;
  "sessionTokenEnv"?: string | null;
  "governanceScopes"?: Array<string>;
  "managementAudit"?: Array<ProductUserManagementAudit>;
  [key: string]: unknown;
};

export type ProductUserUpdateInput = {
  "actorMember": string;
  "displayName"?: string | null;
  "member"?: string | null;
  "identityProvider"?: string | null;
  "identitySubjectHash"?: string | null;
  "status"?: ("active" | "disabled" | "archived") | null;
  "roles"?: (Array<"admin" | "viewer" | "governance_reviewer" | "operator" | "auditor">) | null;
  "sessionTokenEnv"?: string | null;
  "governanceScopes"?: Array<string> | null;
  "reason"?: string | null;
};

export type Project = {
  "apiVersion"?: string;
  "kind": "Project";
  "metadata": Metadata;
  "spec": ProjectSpec;
  [key: string]: unknown;
};

export type ProjectSpec = {
  "description"?: string | null;
  "repositories"?: Array<string>;
  "defaultRepository"?: string | null;
  "workspaceMode"?: string | null;
  "publicDataPolicy"?: Record<string, unknown>;
  "demoProjects"?: Array<Record<string, unknown>>;
  "ruleEntrypoints"?: Array<string>;
  "defaultExecutionMode"?: string | null;
  "deliveryStrategy"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type Repository = {
  "apiVersion"?: string;
  "kind": "Repository";
  "metadata": Metadata;
  "spec": RepositorySpec;
  [key: string]: unknown;
};

export type RepositorySpec = {
  "provider": string;
  "url"?: string | null;
  "localPath"?: string | null;
  "defaultBranch"?: string | null;
  "workspaceRelation"?: string | null;
  "pathPolicy"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type RetrospectiveSuggestion = {
  "id": string;
  "project": string;
  "facilitatorMember"?: string | null;
  "participants": Array<string>;
  "sourceRuns": Array<string>;
  "sourceTasks": Array<string>;
  "sourceMessages": Array<string>;
  "sourceHandoffs": Array<string>;
  "summary": string;
  "lessons": Array<string>;
  "actionItems": Array<string>;
  "evidence": Array<string>;
  "sources": Array<RetrospectiveSuggestionSource>;
  "score": number;
  "confidence": number;
  "warnings"?: Array<string>;
  "proposedRetrospective"?: Record<string, unknown>;
};

export type RetrospectiveSuggestionRecord = {
  "generatedAt": string;
  "filters": Record<string, unknown>;
  "summary": Record<string, number>;
  "candidates": Array<RetrospectiveSuggestion>;
};

export type RetrospectiveSuggestionSource = {
  "sourceType": "run" | "task" | "message" | "handoff";
  "id": string;
  "project"?: string | null;
  "task"?: string | null;
  "run"?: string | null;
  "member"?: string | null;
  "status"?: string | null;
  "summary": string;
};

export type Review = {
  "apiVersion"?: string;
  "kind": "Review";
  "metadata": Metadata;
  "spec": ReviewSpec;
  [key: string]: unknown;
};

export type ReviewFinding = {
  "id": string;
  "severity"?: string;
  "summary": string;
  "action"?: string | null;
  [key: string]: unknown;
};

export type ReviewSpec = {
  "project": string;
  "task"?: string | null;
  "run"?: string | null;
  "reviewer": string;
  "reviewerMember"?: string | null;
  "reviewerKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "source"?: string | null;
  "verdict": string;
  "target"?: ReviewTarget | null;
  "findings"?: Array<ReviewFinding>;
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type ReviewTarget = {
  "type": "pull_request" | "branch" | "commit" | "diff_patch" | "external_review";
  "url"?: string | null;
  "ref"?: string | null;
  "description"?: string | null;
  [key: string]: unknown;
};

export type RiskAssessment = {
  "classifier"?: string;
  "classifierVersion"?: string;
  "provider"?: string | null;
  "riskLevel"?: "low" | "medium" | "high" | "critical";
  "recommendedDecision"?: "allow" | "ask" | "deny";
  "requiresHumanReview"?: boolean;
  "evaluatedAt"?: string | null;
  "summary"?: string | null;
  "action"?: Record<string, unknown>;
  "signals"?: Array<RiskSignal>;
  "metadata"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type RiskSignal = {
  "name": string;
  "severity"?: "info" | "low" | "medium" | "high" | "critical";
  "reason"?: string | null;
  "evidence"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type RoleTemplate = {
  "apiVersion"?: string;
  "kind": "RoleTemplate";
  "metadata": Metadata;
  "spec": RoleTemplateSpec;
  [key: string]: unknown;
};

export type RoleTemplateSpec = {
  "summary"?: string | null;
  "reusableAcrossProjects"?: boolean;
  "defaultResponsibilities"?: Array<string>;
  "defaultOutputs"?: Array<string>;
  [key: string]: unknown;
};

export type Run = {
  "apiVersion"?: string;
  "kind": "Run";
  "metadata": RunMetadata;
  "spec": RunSpec;
  [key: string]: unknown;
};

export type RunAssistanceBundleFile = {
  "path": string;
  "mediaType"?: string;
  "purpose": string;
  "content": string;
  "sizeBytes": number;
  "sensitive"?: boolean;
};

export type RunAssistanceBundleRecord = {
  "apiVersion"?: "aiteamos.dev/v1alpha1";
  "kind"?: "AiteamosBundle";
  "schemaVersion"?: "aiteamos-bundle.v1";
  "run": string;
  "task": string;
  "project": string;
  "member": string;
  "memberKind": "human" | "digital" | "hybrid" | "service";
  "assignment"?: string | null;
  "generatedAt": string;
  "bundleKind"?: "human_hybrid_assisted_handoff_bundle";
  "ready": boolean;
  "package": RunAssistancePackageRecord;
  "files"?: Array<RunAssistanceBundleFile>;
  "fileCount": number;
  "totalSizeBytes": number;
  "ingestInputSchema"?: "RunAssistedIngestInput";
  "secretHandling"?: "references-only-no-secret-values";
  "instructions"?: Array<string>;
  "warnings"?: Array<string>;
  "blockers"?: Array<string>;
};

export type RunAssistancePackageCommand = {
  "label": string;
  "command": string;
  "purpose": string;
};

export type RunAssistancePackageContract = {
  "requiredInputs"?: Array<string>;
  "expectedArtifacts"?: Array<string>;
  "reviewTargetTypes"?: Array<string>;
  "memoryProposalPolicy": string;
  "durableMutationBoundary": string;
};

export type RunAssistancePackageRecord = {
  "run": string;
  "task": string;
  "project": string;
  "member": string;
  "memberKind": "human" | "digital" | "hybrid" | "service";
  "assignment"?: string | null;
  "mode": string;
  "status": string;
  "readyForAssistedExecution": boolean;
  "packageKind"?: "human_assisted_execution_package";
  "generatedAt": string;
  "summary": string;
  "entrypoints"?: Array<RunAssistancePackageCommand>;
  "ideWorkspace"?: Record<string, unknown>;
  "branch"?: Record<string, unknown>;
  "allowedWrites"?: Array<string>;
  "readScope"?: Array<string>;
  "responsibilities"?: Array<string>;
  "acceptance"?: Array<string>;
  "contextSources"?: Record<string, number>;
  "selectedMemory"?: Array<string>;
  "handoffs"?: Array<string>;
  "ingestContract": RunAssistancePackageContract;
  "reviewContract"?: Record<string, unknown>;
  "warnings"?: Array<string>;
  "blockers"?: Array<string>;
};

export type RunAssistedIngestInput = {
  "journal"?: string | null;
  "diffPatch"?: string | null;
  "testLog"?: string | null;
  "reviewTarget"?: ReviewTarget | null;
  "memoryProposal"?: RunAssistedMemoryProposalInput | null;
};

export type RunAssistedMemoryProposalInput = {
  "title"?: string | null;
  "content"?: string | null;
  "kind"?: string;
  "confidence"?: number | null;
  "reviewGuidance"?: string | null;
};

export type RunBranch = {
  "name": string;
  "base"?: string;
  "status"?: string;
  [key: string]: unknown;
};

export type RunCloseoutGateRecord = {
  "run": string;
  "readyForCloseout": boolean;
  "status": string;
  "summary": string;
  "latestReview"?: string | null;
  "blockers": Array<string>;
  "warnings": Array<string>;
  "checks": Array<GateCheck>;
  "permissionDecisions"?: Array<Record<string, unknown>>;
};

export type RunCloseoutInput = {
  "actorMember"?: string | null;
  "actor_member"?: string | null;
  "reason"?: string | null;
};

export type RunEvent = {
  "seq"?: number | null;
  "ts"?: string | null;
  "type"?: string | null;
  "event"?: string | null;
  "lifecycle"?: "active" | "archived" | "redacted";
  "retainedUntil"?: string | null;
  "archivedAt"?: string | null;
  "redactedAt"?: string | null;
  "redactionPolicy"?: string | null;
  "exportPolicy"?: "include" | "sanitize" | "manifest-only" | "exclude";
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type RunMetadata = {
  "name"?: string | null;
  "id": string;
  "title"?: string | null;
  "createdAt"?: string | null;
  [key: string]: unknown;
};

export type RunProviderSourceIntegrationExecuteInput = {
  "actorMember"?: string | null;
  "actor_member"?: string | null;
  "reason"?: string | null;
  "dryRun"?: boolean;
  "dry_run"?: boolean | null;
};

export type RunProviderSourceIntegrationExecutionRecord = {
  "run": string;
  "status": string;
  "summary": string;
  "strategy": string;
  "provider"?: string | null;
  "dryRun"?: boolean;
  "reviewTarget"?: Record<string, unknown> | null;
  "providerChecks"?: Record<string, unknown> | null;
  "changedPaths"?: Array<string>;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "gate"?: Record<string, unknown>;
  "permissionDecisions"?: Array<Record<string, unknown>>;
  "decisionAudit"?: Array<Record<string, unknown>>;
  "providerResult"?: Record<string, unknown> | null;
  "error"?: string | null;
  "attemptedAt"?: string | null;
  "attemptedByMember"?: string | null;
  "attemptedByMemberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
};

export type RunProviderSourceIntegrationInput = {
  "actorMember"?: string | null;
  "actor_member"?: string | null;
  "reason"?: string | null;
};

export type RunProviderSourceIntegrationRecord = {
  "run": string;
  "status": string;
  "summary": string;
  "strategy": string;
  "provider"?: string | null;
  "reviewTarget"?: Record<string, unknown> | null;
  "providerChecks"?: Record<string, unknown> | null;
  "changedPaths"?: Array<string>;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "gate"?: Record<string, unknown>;
  "permissionDecisions"?: Array<Record<string, unknown>>;
  "decisionAudit"?: Array<Record<string, unknown>>;
  "requestedAt"?: string | null;
  "requestedByMember"?: string | null;
  "requestedByMemberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
};

export type RunReviewFindingInput = {
  "severity"?: string;
  "summary": string;
  "action"?: string | null;
};

export type RunReviewGateRecord = {
  "run": string;
  "project"?: string | null;
  "task"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "memberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "readyForHumanReview": boolean;
  "status": string;
  "summary": string;
  "blockers": Array<string>;
  "warnings": Array<string>;
  "checks": Array<GateCheck>;
  "evalSuiteRequirements"?: Array<EvalSuiteRequirementStatus>;
};

export type RunReviewInput = {
  "reviewer"?: string | null;
  "reviewerMember"?: string | null;
  "reviewer_member"?: string | null;
  "verdict"?: string;
  "summary"?: string | null;
  "findings"?: Array<RunReviewFindingInput>;
  "target"?: ReviewTarget | null;
  "source"?: string;
};

export type RunReviewTargetCheckRecord = {
  "run": string;
  "generatedAt": string;
  "source": string;
  "status": string;
  "summary": string;
  "target"?: Record<string, unknown> | null;
  "checks"?: Array<Record<string, unknown>>;
};

export type RunSourceIntegrationGateRecord = {
  "run": string;
  "readyForSourceIntegration": boolean;
  "status": string;
  "summary": string;
  "repository"?: string | null;
  "sourceBranch"?: string | null;
  "workerBranch"?: string | null;
  "changedPaths"?: Array<string>;
  "blockers": Array<string>;
  "warnings": Array<string>;
  "checks": Array<GateCheck>;
  "permissionDecisions"?: Array<Record<string, unknown>>;
};

export type RunSourceIntegrationInput = {
  "actorMember"?: string | null;
  "actor_member"?: string | null;
  "reason"?: string | null;
};

export type RunSourceIntegrationRemediationInput = {
  "actorMember"?: string | null;
  "actor_member"?: string | null;
  "reason"?: string | null;
};

export type RunSourceIntegrationRemediationRecord = {
  "run": string;
  "status": string;
  "summary": string;
  "strategy": string;
  "repository"?: string | null;
  "sourceBranch"?: string | null;
  "workerBranch"?: string | null;
  "remediationBranch"?: string | null;
  "remediationWorktree"?: string | null;
  "mergeStatus"?: string | null;
  "baseSha"?: string | null;
  "sourceSha"?: string | null;
  "workerSha"?: string | null;
  "conflictFiles"?: Array<string>;
  "conflictResolution"?: Record<string, unknown> | null;
  "changedPaths"?: Array<string>;
  "blockers"?: Array<string>;
  "warnings"?: Array<string>;
  "remediationReviewTarget"?: Record<string, unknown> | null;
  "gate"?: Record<string, unknown>;
  "permissionDecisions"?: Array<Record<string, unknown>>;
  "decisionAudit"?: Array<Record<string, unknown>>;
  "requestedAt"?: string | null;
  "requestedByMember"?: string | null;
  "requestedByMemberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
};

export type RunSpec = {
  "project": string;
  "task": string;
  "member": string;
  "assignment"?: string | null;
  "memberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "roleContext"?: string | null;
  "mode"?: string;
  "status"?: string;
  "modelProfile"?: string | null;
  "branch"?: RunBranch | null;
  "reviewTarget"?: ReviewTarget | null;
  "contextCapsule"?: string | null;
  "contextManifest"?: string | null;
  "eventLedger"?: string | null;
  "journal"?: string | null;
  "reviews"?: Array<string>;
  "outputs"?: Array<unknown>;
  "memoryProposals"?: Array<string>;
  "ingest"?: Record<string, unknown>;
  "closeout"?: Record<string, unknown>;
  "sourceIntegration"?: Record<string, unknown>;
  "lifecycle"?: "active" | "archived" | "redacted";
  "retainedUntil"?: string | null;
  "archivedAt"?: string | null;
  "redactedAt"?: string | null;
  "redactionPolicy"?: string | null;
  "exportPolicy"?: "include" | "sanitize" | "manifest-only" | "exclude";
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type ServiceAccountProfile = {
  "apiVersion"?: string;
  "kind": "ServiceAccountProfile";
  "metadata": Metadata;
  "spec": ServiceAccountProfileSpec;
  [key: string]: unknown;
};

export type ServiceAccountProfileSpec = {
  "member": string;
  "serviceKind": string;
  "owner"?: string | null;
  "triggerSources"?: Array<string>;
  "auditPolicy"?: Record<string, unknown>;
  "credentialRefs"?: Record<string, string>;
  [key: string]: unknown;
};

export type SessionLoginInput = {
  "token": string;
};

export type SessionLoginRecord = {
  "id"?: "current";
  "kind"?: "SessionLogin";
  "authenticated"?: boolean;
  "authMode"?: "product-user-token";
  "productUser": string;
  "viewerMember"?: string | null;
  "admin"?: boolean;
  "canSelectViewer"?: boolean;
  "expiresInSeconds"?: number;
  "issuedAt"?: string | null;
  "expiresAt"?: string | null;
  "sessionVersion"?: number;
  "sessionId"?: string | null;
  "csrfToken"?: string | null;
};

export type SessionProjectionRecord = {
  "id"?: "current";
  "kind"?: "SessionProjection";
  "spec": SessionProjectionSpec;
};

export type SessionProjectionSpec = {
  "authenticated"?: boolean;
  "authMode"?: "open-local" | "anonymous" | "api-token" | "viewer-token" | "product-user-token";
  "tokenBound"?: boolean;
  "admin"?: boolean;
  "productUser"?: string | null;
  "productUserStatus"?: ("active" | "disabled" | "archived") | null;
  "productUserMember"?: string | null;
  "productUserRoles"?: Array<string>;
  "canApproveGovernance"?: boolean;
  "viewerMember"?: string | null;
  "viewerMemberKind"?: ("human" | "digital" | "hybrid" | "service") | null;
  "viewerMemberStatus"?: ("active" | "inactive" | "archived") | null;
  "requestedViewerMember"?: string | null;
  "canSelectViewer"?: boolean;
  "projectionMode"?: "public-redacted" | "selected-viewer" | "token-bound-viewer" | "admin-selected-viewer";
  "governedScopes"?: Array<string>;
  "warnings"?: Array<string>;
  [key: string]: unknown;
};

export type Skill = {
  "apiVersion"?: string;
  "kind": "Skill";
  "metadata": Metadata;
  "spec": SkillSpec;
  [key: string]: unknown;
};

export type SkillArchiveInput = {
  "actorMember": string;
  "reason"?: string | null;
};

export type SkillAttachMemberInput = {
  "actorMember": string;
  "member"?: string | null;
  "growthSummary"?: string | null;
  "reason"?: string | null;
};

export type SkillCreateInput = {
  "name": string;
  "actorMember": string;
  "description"?: string | null;
  "ownerMember"?: string | null;
  "projects"?: Array<string>;
  "capabilities"?: Array<string>;
  "requiredPermissions"?: Array<string>;
  "entrypoint"?: string | null;
  "lifecycle"?: "proposed" | "active" | "deprecated" | "archived";
  "reason"?: string | null;
};

export type SkillProjectionRecord = {
  "id": string;
  "kind"?: "SkillProjection";
  "redacted"?: boolean;
  "redactionReason"?: string | null;
  "spec": SkillProjectionSpec;
};

export type SkillProjectionSpec = {
  "skill": string;
  "ownerMember"?: string | null;
  "lifecycle"?: ("proposed" | "active" | "deprecated" | "archived") | null;
  "projects"?: Array<string>;
  "projectCount"?: number;
  "members"?: Array<string>;
  "memberCount"?: number;
  "assignments"?: Array<string>;
  "assignmentCount"?: number;
  "tasks"?: Array<string>;
  "taskCount"?: number;
  "runs"?: Array<string>;
  "runCount"?: number;
  "capabilities"?: Array<string>;
  "requiredPermissions"?: Array<string>;
  "memberFitReasons"?: Array<string>;
  "fitSignal"?: string | null;
  "redacted"?: boolean;
  "redactionReason"?: string | null;
  [key: string]: unknown;
};

export type SkillSpec = {
  "description"?: string | null;
  "ownerMember"?: string | null;
  "projects"?: Array<string>;
  "capabilities"?: Array<string>;
  "requiredPermissions"?: Array<string>;
  "entrypoint"?: string | null;
  "lifecycle"?: "proposed" | "active" | "deprecated" | "archived";
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type SkillUpdateInput = {
  "actorMember": string;
  "description"?: string | null;
  "ownerMember"?: string | null;
  "projects"?: Array<string> | null;
  "capabilities"?: Array<string> | null;
  "requiredPermissions"?: Array<string> | null;
  "entrypoint"?: string | null;
  "lifecycle"?: ("proposed" | "active" | "deprecated" | "archived") | null;
  "reason"?: string | null;
};

export type Task = {
  "apiVersion"?: string;
  "kind": "Task";
  "metadata": TaskMetadata;
  "spec": TaskSpec;
  [key: string]: unknown;
};

export type TaskExecutionQueueItem = {
  "id": string;
  "queueStatus": string;
  "title": string;
  "taskStatus": string;
  "assignedMember"?: string | null;
  "assignment"?: string | null;
  "memberModelProfile"?: string | null;
  "latestRun"?: string | null;
  "latestRunStatus"?: string | null;
  "runCount": number;
  "blockers": Array<string>;
  "actions": Array<string>;
};

export type TaskExecutionQueueRecord = {
  "summary": Record<string, number>;
  "items": Array<TaskExecutionQueueItem>;
};

export type TaskMetadata = {
  "name"?: string | null;
  "id": string;
  "title"?: string | null;
  "createdAt"?: string | null;
  [key: string]: unknown;
};

export type TaskPlan = {
  "apiVersion"?: string;
  "kind": "TaskPlan";
  "metadata": Metadata;
  "spec": TaskPlanSpec;
  [key: string]: unknown;
};

export type TaskPlanSpec = {
  "goal": string;
  "project"?: string | null;
  "sourceTask"?: string | null;
  "createdByMember"?: string | null;
  "status"?: "draft" | "accepted" | "rejected" | "superseded";
  "subtasks"?: Array<TaskPlanSubtask>;
  "risks"?: Array<string>;
  "reviewGates"?: Array<string>;
  [key: string]: unknown;
};

export type TaskPlanSubtask = {
  "title": string;
  "assignedMember"?: string | null;
  "assignment"?: string | null;
  "priority"?: string;
  "acceptance"?: Array<string>;
  "risks"?: Array<string>;
  "reviewGates"?: Array<string>;
  "dependsOn"?: Array<string>;
  [key: string]: unknown;
};

export type TaskSpec = {
  "title": string;
  "project": string;
  "assignedMember"?: string | null;
  "assignment"?: string | null;
  "status"?: string;
  "priority"?: string;
  "riskClass"?: string | null;
  "executionMode"?: string | null;
  "acceptance"?: Array<string>;
  "relatedRuns"?: Array<string>;
  "relatedReviews"?: Array<string>;
  [key: string]: unknown;
};

export type Team = {
  "apiVersion"?: string;
  "kind": "Team";
  "metadata": Metadata;
  "spec": TeamSpec;
  [key: string]: unknown;
};

export type TeamMember = {
  "apiVersion"?: string;
  "kind": "TeamMember";
  "metadata": Metadata;
  "spec": TeamMemberSpec;
  [key: string]: unknown;
};

export type TeamMemberSpec = {
  "kind": "human" | "digital" | "hybrid" | "service";
  "profile"?: MemberProfile;
  "userBinding"?: TeamMemberUserBinding | null;
  "aboutMe"?: MemberAboutMe;
  "capabilities"?: Array<MemberCapability>;
  "workStyle"?: MemberWorkStyle;
  "workMethod"?: MemberWorkMethod;
  "projects"?: Array<MemberProjectEngagement>;
  "defaultAssignments"?: Array<string>;
  "skills"?: Array<string>;
  "connectors"?: Array<string>;
  "permissionPolicies"?: Array<string>;
  "memoryStores"?: Array<string>;
  "growthRecords"?: Array<MemberGrowthRecord>;
  "performanceMetrics"?: Array<MemberPerformanceMetric>;
  "lifecycle"?: "active" | "archived" | "redacted";
  "archivedAt"?: string | null;
  "redactedAt"?: string | null;
  "redactionPolicy"?: string | null;
  "exportPolicy"?: "include" | "sanitize" | "manifest-only" | "exclude";
  "decisionAudit"?: Array<DecisionAuditRecord>;
  [key: string]: unknown;
};

export type TeamMemberUserBinding = {
  "productUser": string;
  "source"?: "ProductUser";
  "identityProvider"?: string;
  "identitySubjectHash"?: string | null;
  "sessionTokenEnv"?: string | null;
  "status"?: "active" | "disabled" | "archived";
  "roles"?: Array<"admin" | "viewer" | "governance_reviewer" | "operator" | "auditor">;
  "boundAt"?: string | null;
  "boundByMember"?: string | null;
  "updatedAt"?: string | null;
  [key: string]: unknown;
};

export type TeamRetrospective = {
  "apiVersion"?: string;
  "kind": "TeamRetrospective";
  "metadata": Metadata;
  "spec": TeamRetrospectiveSpec;
  [key: string]: unknown;
};

export type TeamRetrospectiveSpec = {
  "project": string;
  "facilitatorMember": string;
  "participants"?: Array<string>;
  "sourceTaskPlan"?: string | null;
  "sourceRuns"?: Array<string>;
  "sourceTasks"?: Array<string>;
  "sourceMessages"?: Array<string>;
  "sourceHandoffs"?: Array<string>;
  "summary": string;
  "lessons"?: Array<string>;
  "actionItems"?: Array<string>;
  "proposedMemory"?: string | null;
  "status"?: "draft" | "proposed" | "reviewed" | "archived";
  "audit"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type TeamSpec = {
  "description"?: string | null;
  "members"?: Array<string>;
  "projects"?: Array<string>;
  "memoryStores"?: Array<string>;
  "permissionPolicies"?: Array<string>;
  [key: string]: unknown;
};

export type Workspace = {
  "apiVersion"?: string;
  "kind": "Workspace";
  "metadata": Metadata;
  "spec": WorkspaceSpec;
  [key: string]: unknown;
};

export type WorkspaceActionBoardRecord = {
  "summary": Record<string, number>;
  "items": Array<WorkspaceActionItem>;
};

export type WorkspaceActionItem = {
  "id": string;
  "lane": string;
  "priority": number;
  "targetType": string;
  "targetId": string;
  "task"?: string | null;
  "run"?: string | null;
  "member"?: string | null;
  "assignment"?: string | null;
  "status"?: string | null;
  "action": string;
  "title": string;
  "reason": string;
  "blockers": Array<string>;
  "warnings": Array<string>;
};

export type WorkspaceCatalogOption = {
  "id": string;
  "label": string;
  "optionType": "current" | "example";
  "workspaceRef": string;
  "workspaceName"?: string | null;
  "workspaceMode"?: string | null;
  "protocolVersion"?: string | null;
  "project"?: string | null;
  "projectTitle"?: string | null;
  "relativePath"?: string | null;
  "servedByCurrentApi"?: boolean;
  "safeForPublicDemo"?: boolean;
  "launchCommand"?: string | null;
  "validateCommand"?: string | null;
  "dashboardCommand"?: string | null;
  "counts"?: Record<string, number>;
  "healthSummary"?: Record<string, number>;
  "warnings"?: Array<string>;
};

export type WorkspaceCatalogRecord = {
  "id"?: "workspace-catalog";
  "kind"?: "WorkspaceCatalog";
  "spec": WorkspaceCatalogSpec;
};

export type WorkspaceCatalogSpec = {
  "currentWorkspace": string;
  "generatedAt": string;
  "options": Array<WorkspaceCatalogOption>;
};

export type WorkspaceHealth = {
  "schemaVersion"?: "WorkspaceHealthV2";
  "issues": Array<Record<string, unknown>>;
  "summary": Record<string, number>;
  "lastIndexDuration"?: number | null;
  "manifestLoadFailures"?: Array<Record<string, unknown>>;
  "vectorChunkCount"?: number;
  "schemaVersionMismatch"?: boolean;
  "staleWorkerLeases"?: Array<Record<string, unknown>>;
};

export type WorkspaceSpec = {
  "mode": "embedded" | "shadow";
  "protocolVersion"?: string;
  "projectRef": string;
  "storage"?: Record<string, unknown>;
  "indexing"?: Record<string, unknown>;
  "governance"?: Record<string, unknown>;
  [key: string]: unknown;
};

export type AiteamosManifest = Workspace | Project | Repository | RoleTemplate | TeamMember | ProductUser | DigitalExecutionProfile | HumanCollaborationProfile | HybridExecutionProfile | ServiceAccountProfile | Team | Assignment | MemberActivity | GitActivity | GitActivityImportReceipt | GitActivityCorrelationReview | Task | TaskPlan | Run | Review | MemoryStore | MemoryEntry | MemoryVersion | MemoryBinding | MemoryGrant | MemoryProposal | LearningExtraction | MemberMessage | Handoff | TeamRetrospective | Automation | AutomationRun | AutomationTriggerEvent | AutomationProviderDelivery | AutomationSchedulerLease | AutomationApproval | ApprovalWorkflow | PermissionPolicy | PermissionRequest | PermissionGrant | Skill | Connector | ConnectorHealthCheck | EvalSuite | EvalResult | Artifact | ArtifactStore | ModelProfile | BudgetPolicy | ContextManifest;
export type AiteamosManifestKind = "ApprovalWorkflow" | "Artifact" | "ArtifactStore" | "Assignment" | "Automation" | "AutomationApproval" | "AutomationProviderDelivery" | "AutomationRun" | "AutomationSchedulerLease" | "AutomationTriggerEvent" | "BudgetPolicy" | "Connector" | "ConnectorHealthCheck" | "ContextManifest" | "DigitalExecutionProfile" | "EvalResult" | "EvalSuite" | "GitActivity" | "GitActivityCorrelationReview" | "GitActivityImportReceipt" | "Handoff" | "HumanCollaborationProfile" | "HybridExecutionProfile" | "LearningExtraction" | "MemberActivity" | "MemberMessage" | "MemoryBinding" | "MemoryEntry" | "MemoryGrant" | "MemoryProposal" | "MemoryStore" | "MemoryVersion" | "ModelProfile" | "PermissionGrant" | "PermissionPolicy" | "PermissionRequest" | "ProductUser" | "Project" | "Repository" | "Review" | "RoleTemplate" | "Run" | "ServiceAccountProfile" | "Skill" | "Task" | "TaskPlan" | "Team" | "TeamMember" | "TeamRetrospective" | "Workspace";
