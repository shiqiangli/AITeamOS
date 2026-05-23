from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


API_VERSION = "aiteamos.dev/v1alpha1"
TASK_ID_RE = re.compile(r"^TASK-\d{8}T\d{9}$")
ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class AITEAMOSModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class StrictAITEAMOSModel(AITEAMOSModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Metadata(AITEAMOSModel):
    name: str | None = None
    id: str | None = None
    title: str | None = None
    createdAt: str | None = None

    @property
    def object_id(self) -> str:
        value = self.id or self.name
        if not value:
            raise ValueError("metadata requires either id or name")
        return value


class Manifest(AITEAMOSModel):
    apiVersion: str = API_VERSION
    kind: str
    metadata: Metadata
    spec: dict[str, Any] = Field(default_factory=dict)

    @field_validator("apiVersion")
    @classmethod
    def validate_api_version(cls, value: str) -> str:
        if value != API_VERSION:
            raise ValueError(f"unsupported apiVersion {value!r}; expected {API_VERSION!r}")
        return value

    @property
    def object_id(self) -> str:
        return self.metadata.object_id


class WorkspaceSpec(AITEAMOSModel):
    mode: Literal["embedded", "shadow"]
    protocolVersion: str = API_VERSION
    projectRef: str
    storage: dict[str, Any] = Field(default_factory=dict)
    indexing: dict[str, Any] = Field(default_factory=dict)
    governance: dict[str, Any] = Field(default_factory=dict)


class Workspace(Manifest):
    kind: Literal["Workspace"]
    spec: WorkspaceSpec


class ProjectSpec(AITEAMOSModel):
    description: str | None = None
    repositories: list[str] = Field(default_factory=list)
    defaultRepository: str | None = None
    workspaceMode: str | None = None
    publicDataPolicy: dict[str, Any] = Field(default_factory=dict)
    demoProjects: list[dict[str, Any]] = Field(default_factory=list)
    ruleEntrypoints: list[str] = Field(default_factory=list)
    defaultExecutionMode: str | None = None
    deliveryStrategy: dict[str, Any] = Field(default_factory=dict)


class Project(Manifest):
    kind: Literal["Project"]
    spec: ProjectSpec


class RepositorySpec(AITEAMOSModel):
    provider: str
    url: str | None = None
    localPath: str | None = None
    defaultBranch: str | None = None
    workspaceRelation: str | None = None
    pathPolicy: dict[str, Any] = Field(default_factory=dict)


class Repository(Manifest):
    kind: Literal["Repository"]
    spec: RepositorySpec


class RoleTemplateSpec(AITEAMOSModel):
    summary: str | None = None
    reusableAcrossProjects: bool = True
    defaultResponsibilities: list[str] = Field(default_factory=list)
    defaultOutputs: list[str] = Field(default_factory=list)


class RoleTemplate(Manifest):
    kind: Literal["RoleTemplate"]
    spec: RoleTemplateSpec


class MemberAboutMe(AITEAMOSModel):
    coreCapabilities: list[str] = Field(default_factory=list)
    workStyle: list[str] = Field(default_factory=list)
    workMethod: list[str] = Field(default_factory=list)


class MemberCapability(AITEAMOSModel):
    name: str
    level: str | None = None
    evidence: list[str] = Field(default_factory=list)
    relatedSkills: list[str] = Field(default_factory=list)


class MemberWorkStyle(AITEAMOSModel):
    traits: list[str] = Field(default_factory=list)
    notes: str | None = None


class MemberWorkMethod(AITEAMOSModel):
    methods: list[str] = Field(default_factory=list)
    notes: str | None = None


class MemberProjectEngagement(AITEAMOSModel):
    project: str
    assignments: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    status: str = "active"


class MemberGrowthRecord(AITEAMOSModel):
    recordedAt: str | None = None
    project: str | None = None
    summary: str
    evidence: list[str] = Field(default_factory=list)
    sourceAction: str | None = None
    sourceTask: str | None = None
    sourceRun: str | None = None
    sourceReview: str | None = None
    sourceMemoryProposal: str | None = None
    sourceSkill: str | None = None
    reviewedByMember: str | None = None
    reviewedAt: str | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class MemberGrowthRecordInput(StrictAITEAMOSModel):
    actorMember: str
    summary: str
    project: str | None = None
    sourceAction: str | None = None
    sourceTask: str | None = None
    sourceRun: str | None = None
    sourceReview: str | None = None
    sourceMemoryProposal: str | None = None
    sourceSkill: str | None = None
    evidence: list[str] = Field(default_factory=list)
    reason: str | None = None


class MemberPerformanceMetric(AITEAMOSModel):
    name: str
    value: str | int | float | bool | None = None
    period: str | None = None
    source: str | None = None


class MemberProfile(AITEAMOSModel):
    displayName: str | None = None
    title: str | None = None
    avatarUrl: str | None = None
    timezone: str | None = None
    status: Literal["active", "inactive", "archived"] = "active"
    summary: str | None = None


ProductUserRole = Literal["admin", "viewer", "governance_reviewer", "operator", "auditor"]
ProductUserStatus = Literal["active", "disabled", "archived"]


class TeamMemberUserBinding(AITEAMOSModel):
    productUser: str
    source: Literal["ProductUser"] = "ProductUser"
    identityProvider: str = "local-token"
    identitySubjectHash: str | None = None
    sessionTokenEnv: str | None = None
    status: ProductUserStatus = "active"
    roles: list[ProductUserRole] = Field(default_factory=list)
    boundAt: str | None = None
    boundByMember: str | None = None
    updatedAt: str | None = None

    @field_validator("identityProvider")
    @classmethod
    def validate_identity_provider(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identityProvider must not be empty")
        return value

    @field_validator("sessionTokenEnv")
    @classmethod
    def validate_session_token_env(cls, value: str | None) -> str | None:
        if value is not None and not ENV_NAME_RE.match(value):
            raise ValueError("sessionTokenEnv must be an environment variable name")
        return value


class TeamMemberSpec(AITEAMOSModel):
    kind: Literal["human", "digital", "hybrid", "service"]
    profile: MemberProfile = Field(default_factory=MemberProfile)
    userBinding: TeamMemberUserBinding | None = None
    aboutMe: MemberAboutMe = Field(default_factory=MemberAboutMe)
    capabilities: list[MemberCapability] = Field(default_factory=list)
    workStyle: MemberWorkStyle = Field(default_factory=MemberWorkStyle)
    workMethod: MemberWorkMethod = Field(default_factory=MemberWorkMethod)
    projects: list[MemberProjectEngagement] = Field(default_factory=list)
    defaultAssignments: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    connectors: list[str] = Field(default_factory=list)
    permissionPolicies: list[str] = Field(default_factory=list)
    memoryStores: list[str] = Field(default_factory=list)
    growthRecords: list[MemberGrowthRecord] = Field(default_factory=list)
    performanceMetrics: list[MemberPerformanceMetric] = Field(default_factory=list)
    lifecycle: Literal["active", "archived", "redacted"] = "active"
    archivedAt: str | None = None
    redactedAt: str | None = None
    redactionPolicy: str | None = None
    exportPolicy: Literal["include", "sanitize", "manifest-only", "exclude"] = "sanitize"
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class TeamMember(Manifest):
    kind: Literal["TeamMember"]
    spec: TeamMemberSpec


class ProductUserManagementAudit(AITEAMOSModel):
    action: Literal["create-product-user", "update-product-user", "archive-product-user"]
    actorMember: str
    actorMemberKind: Literal["human", "digital", "hybrid", "service"] | None = None
    decisionKind: Literal["human_approval", "digital_recommendation", "service_policy_decision"] = "human_approval"
    authority: Literal["approve", "recommend", "enforce"] = "approve"
    decidedAt: str | None = None
    reason: str | None = None
    permissionDecision: Literal["allow", "ask", "deny"] | None = None
    policyRefs: list[str] = Field(default_factory=list)
    targetUser: str | None = None


class ProductUserSpec(AITEAMOSModel):
    displayName: str | None = None
    member: str | None = None
    identityProvider: str = "local-token"
    identitySubjectHash: str | None = None
    status: ProductUserStatus = "active"
    roles: list[ProductUserRole] = Field(default_factory=lambda: ["viewer"])
    sessionTokenEnv: str | None = None
    governanceScopes: list[str] = Field(default_factory=list)
    managementAudit: list[ProductUserManagementAudit] = Field(default_factory=list)

    @field_validator("identityProvider")
    @classmethod
    def validate_identity_provider(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identityProvider must not be empty")
        return value

    @field_validator("sessionTokenEnv")
    @classmethod
    def validate_session_token_env(cls, value: str | None) -> str | None:
        if value is not None and not ENV_NAME_RE.match(value):
            raise ValueError("sessionTokenEnv must be an environment variable name")
        return value

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: list[ProductUserRole]) -> list[ProductUserRole]:
        if not value:
            raise ValueError("roles must include at least one ProductUser role")
        return value


class ProductUser(Manifest):
    kind: Literal["ProductUser"]
    spec: ProductUserSpec


class ProductUserCreateInput(StrictAITEAMOSModel):
    name: str
    actorMember: str
    displayName: str | None = None
    member: str | None = None
    identityProvider: str = "local-token"
    identitySubjectHash: str | None = None
    status: ProductUserStatus = "active"
    roles: list[ProductUserRole] = Field(default_factory=lambda: ["viewer"])
    sessionTokenEnv: str | None = None
    governanceScopes: list[str] = Field(default_factory=list)
    reason: str | None = None

    @field_validator("identityProvider")
    @classmethod
    def validate_identity_provider(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identityProvider must not be empty")
        return value

    @field_validator("sessionTokenEnv")
    @classmethod
    def validate_session_token_env(cls, value: str | None) -> str | None:
        if value is not None and not ENV_NAME_RE.match(value):
            raise ValueError("sessionTokenEnv must be an environment variable name")
        return value

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: list[ProductUserRole]) -> list[ProductUserRole]:
        if not value:
            raise ValueError("roles must include at least one ProductUser role")
        return value


class ProductUserUpdateInput(StrictAITEAMOSModel):
    actorMember: str
    displayName: str | None = None
    member: str | None = None
    identityProvider: str | None = None
    identitySubjectHash: str | None = None
    status: ProductUserStatus | None = None
    roles: list[ProductUserRole] | None = None
    sessionTokenEnv: str | None = None
    governanceScopes: list[str] | None = None
    reason: str | None = None

    @field_validator("identityProvider")
    @classmethod
    def validate_identity_provider(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("identityProvider must not be empty")
        return value

    @field_validator("sessionTokenEnv")
    @classmethod
    def validate_session_token_env(cls, value: str | None) -> str | None:
        if value is not None and not ENV_NAME_RE.match(value):
            raise ValueError("sessionTokenEnv must be an environment variable name")
        return value

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, value: list[ProductUserRole] | None) -> list[ProductUserRole] | None:
        if value is not None and not value:
            raise ValueError("roles must include at least one ProductUser role")
        return value


class ProductUserArchiveInput(StrictAITEAMOSModel):
    actorMember: str
    reason: str | None = None


class SessionProjectionSpec(AITEAMOSModel):
    authenticated: bool = False
    authMode: Literal["open-local", "anonymous", "api-token", "viewer-token", "product-user-token"] = "open-local"
    tokenBound: bool = False
    admin: bool = False
    productUser: str | None = None
    productUserStatus: Literal["active", "disabled", "archived"] | None = None
    productUserMember: str | None = None
    productUserRoles: list[str] = Field(default_factory=list)
    canApproveGovernance: bool = False
    viewerMember: str | None = None
    viewerMemberKind: Literal["human", "digital", "hybrid", "service"] | None = None
    viewerMemberStatus: Literal["active", "inactive", "archived"] | None = None
    requestedViewerMember: str | None = None
    canSelectViewer: bool = True
    projectionMode: Literal[
        "public-redacted",
        "selected-viewer",
        "token-bound-viewer",
        "admin-selected-viewer",
    ] = "public-redacted"
    governedScopes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SessionProjectionRecord(StrictAITEAMOSModel):
    id: Literal["current"] = "current"
    kind: Literal["SessionProjection"] = "SessionProjection"
    spec: SessionProjectionSpec


class SessionLoginInput(StrictAITEAMOSModel):
    token: str = Field(min_length=1)


class SessionLoginRecord(StrictAITEAMOSModel):
    id: Literal["current"] = "current"
    kind: Literal["SessionLogin"] = "SessionLogin"
    authenticated: bool = True
    authMode: Literal["product-user-token"] = "product-user-token"
    productUser: str
    viewerMember: str | None = None
    admin: bool = False
    canSelectViewer: bool = False
    expiresInSeconds: int = Field(default=28800, ge=1)
    issuedAt: str | None = None
    expiresAt: str | None = None
    sessionVersion: int = Field(default=1, ge=1)
    sessionId: str | None = None
    csrfToken: str | None = None


class DigitalExecutionProfileSpec(AITEAMOSModel):
    member: str
    defaultModelProfile: str | None = None
    allowedModelProfiles: list[str] = Field(default_factory=list)
    workerRuntime: dict[str, Any] = Field(default_factory=dict)
    contextCompiler: dict[str, Any] = Field(default_factory=dict)
    toolPolicy: dict[str, Any] = Field(default_factory=dict)
    promptPolicy: dict[str, Any] = Field(default_factory=dict)
    connectors: list[str] = Field(default_factory=list)
    budgetPolicies: list[str] = Field(default_factory=list)


class DigitalExecutionProfile(Manifest):
    kind: Literal["DigitalExecutionProfile"]
    spec: DigitalExecutionProfileSpec


class HumanCollaborationProfileSpec(AITEAMOSModel):
    member: str
    contact: dict[str, Any] = Field(default_factory=dict)
    ideEntrypoints: list[str] = Field(default_factory=list)
    reviewAuthority: list[str] = Field(default_factory=list)
    approvalScopes: list[str] = Field(default_factory=list)
    availability: dict[str, Any] = Field(default_factory=dict)


class HumanCollaborationProfile(Manifest):
    kind: Literal["HumanCollaborationProfile"]
    spec: HumanCollaborationProfileSpec


class HybridExecutionProfileSpec(AITEAMOSModel):
    member: str
    humanProfile: str | None = None
    assistedTools: list[str] = Field(default_factory=list)
    ingestPolicy: dict[str, Any] = Field(default_factory=dict)
    aiAssistancePolicy: dict[str, Any] = Field(default_factory=dict)
    reviewExpectations: list[str] = Field(default_factory=list)


class HybridExecutionProfile(Manifest):
    kind: Literal["HybridExecutionProfile"]
    spec: HybridExecutionProfileSpec


class ServiceAccountProfileSpec(AITEAMOSModel):
    member: str
    serviceKind: str
    owner: str | None = None
    triggerSources: list[str] = Field(default_factory=list)
    auditPolicy: dict[str, Any] = Field(default_factory=dict)
    credentialRefs: dict[str, str] = Field(default_factory=dict)


class ServiceAccountProfile(Manifest):
    kind: Literal["ServiceAccountProfile"]
    spec: ServiceAccountProfileSpec


class AssignmentScope(AITEAMOSModel):
    repositories: list[str] = Field(default_factory=list)
    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)
    requiresHumanReview: list[str] = Field(default_factory=list)


class EvalSuiteRequirement(AITEAMOSModel):
    evalSuite: str
    paths: list[str] = Field(default_factory=list)
    minimumPassRate: float | None = Field(default=None, ge=0, le=1)
    description: str | None = None


class AssignmentSpec(AITEAMOSModel):
    member: str
    project: str
    roleTemplate: str | None = None
    roleContext: str | None = None
    title: str | None = None
    status: Literal["active", "paused", "completed", "archived"] = "active"
    repositories: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    scope: AssignmentScope = Field(default_factory=AssignmentScope)
    permissionPolicies: list[str] = Field(default_factory=list)
    memoryBindings: list[str] = Field(default_factory=list)
    evalSuiteRequirements: list[EvalSuiteRequirement] = Field(default_factory=list)
    activeFrom: str | None = None
    activeTo: str | None = None


class Assignment(Manifest):
    kind: Literal["Assignment"]
    spec: AssignmentSpec


class MemberActivitySpec(AITEAMOSModel):
    member: str
    project: str | None = None
    assignment: str | None = None
    task: str | None = None
    run: str | None = None
    activityType: str
    sourceType: Literal[
        "task",
        "run",
        "review",
        "memory-proposal",
        "message",
        "handoff",
        "retrospective",
        "automation",
        "git",
        "manual",
    ] = "manual"
    contributionKind: Literal[
        "authored-work",
        "review-work",
        "support-work",
        "automation-work",
        "knowledge-work",
        "coordination-work",
        "git-work",
        "other",
    ] = "other"
    sourceId: str | None = None
    occurredAt: str | None = None
    summary: str
    evidence: list[str] = Field(default_factory=list)
    visibility: Literal["member", "project", "team", "organization"] = "project"


class MemberActivity(Manifest):
    kind: Literal["MemberActivity"]
    spec: MemberActivitySpec


class GitActivitySpec(AITEAMOSModel):
    member: str
    project: str
    repository: str | None = None
    assignment: str | None = None
    activityType: Literal["commit", "branch", "pull-request", "review-comment", "merge", "tag", "other"]
    provider: str | None = None
    externalId: str | None = None
    url: str | None = None
    occurredAt: str | None = None
    summary: str
    refs: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    visibility: Literal["member", "project", "team", "organization"] = "project"
    lifecycle: Literal["active", "archived", "redacted"] = "active"
    retainedUntil: str | None = None
    archivedAt: str | None = None
    redactedAt: str | None = None
    redactionPolicy: Literal["metadata-only", "redacted-summary", "artifact-reference"] | None = None
    exportPolicy: Literal["include", "sanitize", "manifest-only", "exclude"] = "sanitize"
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class GitActivity(Manifest):
    kind: Literal["GitActivity"]
    spec: GitActivitySpec


class GitActivityImportReceiptSpec(AITEAMOSModel):
    project: str
    repository: str | None = None
    provider: str
    connector: str | None = None
    sourceType: Literal["provider-sync", "webhook", "manual-import", "local-scan"] = "manual-import"
    status: Literal["candidate", "needs-review", "imported", "blocked", "duplicate", "archived"] = "candidate"
    dedupeKey: str
    payloadDigest: str
    payloadDigestAlgorithm: Literal["sha256"] = "sha256"
    redactionPolicy: Literal["metadata-only", "redacted-summary", "artifact-reference"] = "metadata-only"
    importPolicy: Literal["reviewed-import", "service-policy-import", "manual-record"] = "reviewed-import"
    payloadRetained: bool = False
    rawPayloadArtifact: str | None = None
    retainedUntil: str | None = None
    receivedAt: str | None = None
    reviewedByMember: str | None = None
    reviewedAt: str | None = None
    serviceMember: str | None = None
    importerMember: str | None = None
    importedActivities: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    normalized: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class GitActivityImportReceipt(Manifest):
    kind: Literal["GitActivityImportReceipt"]
    spec: GitActivityImportReceiptSpec


class GitActivityCorrelationSignal(StrictAITEAMOSModel):
    kind: str
    value: str
    weight: int = Field(default=1, ge=0)
    sourceReceipt: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class GitActivityCorrelationGroup(StrictAITEAMOSModel):
    correlationKey: str
    project: str
    repository: str | None = None
    provider: str | None = None
    connector: str | None = None
    receipts: list[str] = Field(default_factory=list)
    importedActivities: list[str] = Field(default_factory=list)
    eventFamilies: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)
    assignments: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    commits: list[str] = Field(default_factory=list)
    pullRequests: list[str] = Field(default_factory=list)
    externalIds: list[str] = Field(default_factory=list)
    signals: list[GitActivityCorrelationSignal] = Field(default_factory=list)
    forcePushRisk: bool = False
    squashMergeRisk: bool = False
    multiEventRisk: bool = False
    summary: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GitActivityCorrelationPreviewRecord(StrictAITEAMOSModel):
    generatedAt: str
    filters: dict[str, Any] = Field(default_factory=dict)
    groups: list[GitActivityCorrelationGroup]


class GitActivityCorrelationReviewSpec(AITEAMOSModel):
    project: str
    repository: str | None = None
    provider: str | None = None
    connector: str | None = None
    correlationKey: str
    receipts: list[str] = Field(default_factory=list)
    importedActivities: list[str] = Field(default_factory=list)
    decision: Literal["approved", "rejected", "needs-changes", "archived"] = "approved"
    reviewerMember: str
    reviewerMemberKind: Literal["human", "digital", "hybrid", "service"] | None = None
    reviewedAt: str | None = None
    eventFamilies: list[str] = Field(default_factory=list)
    members: list[str] = Field(default_factory=list)
    assignments: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)
    commits: list[str] = Field(default_factory=list)
    pullRequests: list[str] = Field(default_factory=list)
    externalIds: list[str] = Field(default_factory=list)
    signals: list[GitActivityCorrelationSignal] = Field(default_factory=list)
    riskFlags: list[Literal["force-push", "squash-merge", "multi-event", "blocked-receipt", "imported-activity", "manual-review-required"]] = Field(default_factory=list)
    recommendedPromotion: dict[str, Any] = Field(default_factory=dict)
    summary: str
    evidence: list[str] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class GitActivityCorrelationReview(Manifest):
    kind: Literal["GitActivityCorrelationReview"]
    spec: GitActivityCorrelationReviewSpec


class TaskMetadata(Metadata):
    id: str

    @field_validator("id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        if not TASK_ID_RE.match(value):
            raise ValueError("task id must match TASK-YYYYMMDDTHHMMSSmmm")
        return value


class TaskSpec(AITEAMOSModel):
    title: str
    project: str
    assignedMember: str | None = None
    assignment: str | None = None
    status: str = "TODO"
    priority: str = "normal"
    riskClass: str | None = None
    executionMode: str | None = None
    acceptance: list[str] = Field(default_factory=list)
    relatedRuns: list[str] = Field(default_factory=list)
    relatedReviews: list[str] = Field(default_factory=list)


class Task(Manifest):
    kind: Literal["Task"]
    metadata: TaskMetadata
    spec: TaskSpec


class TaskPlanSubtask(AITEAMOSModel):
    title: str
    assignedMember: str | None = None
    assignment: str | None = None
    priority: str = "normal"
    acceptance: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    reviewGates: list[str] = Field(default_factory=list)
    dependsOn: list[str] = Field(default_factory=list)


class TaskPlanSpec(AITEAMOSModel):
    goal: str
    project: str | None = None
    sourceTask: str | None = None
    createdByMember: str | None = None
    status: Literal["draft", "accepted", "rejected", "superseded"] = "draft"
    subtasks: list[TaskPlanSubtask] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    reviewGates: list[str] = Field(default_factory=list)


class TaskPlan(Manifest):
    kind: Literal["TaskPlan"]
    spec: TaskPlanSpec


class RunMetadata(Metadata):
    id: str


class RunBranch(AITEAMOSModel):
    name: str
    base: str = "develop"
    status: str = "planned"


class RunSpec(AITEAMOSModel):
    project: str
    task: str
    member: str
    assignment: str | None = None
    memberKind: Literal["human", "digital", "hybrid", "service"] | None = None
    roleContext: str | None = None
    mode: str = "assisted"
    status: str = "RUNNING"
    modelProfile: str | None = None
    branch: RunBranch | None = None
    reviewTarget: "ReviewTarget | None" = None
    contextCapsule: str | None = None
    contextManifest: str | None = None
    eventLedger: str | None = None
    journal: str | None = None
    reviews: list[str] = Field(default_factory=list)
    outputs: list[Any] = Field(default_factory=list)
    memoryProposals: list[str] = Field(default_factory=list)
    ingest: dict[str, Any] = Field(default_factory=dict)
    closeout: dict[str, Any] = Field(default_factory=dict)
    sourceIntegration: dict[str, Any] = Field(default_factory=dict)
    lifecycle: Literal["active", "archived", "redacted"] = "active"
    retainedUntil: str | None = None
    archivedAt: str | None = None
    redactedAt: str | None = None
    redactionPolicy: str | None = None
    exportPolicy: Literal["include", "sanitize", "manifest-only", "exclude"] = "manifest-only"
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class Run(Manifest):
    kind: Literal["Run"]
    metadata: RunMetadata
    spec: RunSpec


class RunEvent(AITEAMOSModel):
    seq: int | None = Field(default=None, ge=1)
    ts: str | None = None
    type: str | None = None
    event: str | None = None
    lifecycle: Literal["active", "archived", "redacted"] = "active"
    retainedUntil: str | None = None
    archivedAt: str | None = None
    redactedAt: str | None = None
    redactionPolicy: str | None = None
    exportPolicy: Literal["include", "sanitize", "manifest-only", "exclude"] = "manifest-only"
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)

    @field_validator("decisionAudit", mode="before")
    @classmethod
    def _normalize_decision_audit(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return [value]
        return value


class RiskSignal(AITEAMOSModel):
    name: str
    severity: Literal["info", "low", "medium", "high", "critical"] = "low"
    reason: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class RiskAssessment(AITEAMOSModel):
    classifier: str = "aiteamos.local.permission-risk"
    classifierVersion: str = "v1"
    provider: str | None = None
    riskLevel: Literal["low", "medium", "high", "critical"] = "low"
    recommendedDecision: Literal["allow", "ask", "deny"] = "allow"
    requiresHumanReview: bool = False
    evaluatedAt: str | None = None
    summary: str | None = None
    action: dict[str, Any] = Field(default_factory=dict)
    signals: list[RiskSignal] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionAuditRecord(AITEAMOSModel):
    decisionKind: Literal["human_approval", "digital_recommendation", "service_policy_decision", "system_check"]
    decision: str
    actorMember: str | None = None
    actorMemberKind: Literal["human", "digital", "hybrid", "service"] | None = None
    authority: Literal["approve", "recommend", "enforce", "record", "revoke", "expire"] = "record"
    decidedAt: str | None = None
    reason: str | None = None
    source: str | None = None
    policyRefs: list[str] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    requiresHumanReview: bool = False
    riskAssessment: RiskAssessment | None = None
    risk: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemberDeleteRequestInput(StrictAITEAMOSModel):
    actorMember: str
    reason: str | None = None


class MemberDeleteRequestReference(StrictAITEAMOSModel):
    kind: Literal["Run", "MemberMessage", "Handoff", "GitActivity", "Assignment", "MemoryBinding"]
    id: str
    path: str
    action: Literal["archive", "redact"]


class MemberDeleteRequestRecord(StrictAITEAMOSModel):
    member: str
    actorMember: str
    requestedAt: str
    status: Literal["redacted"]
    references: dict[str, list[str]] = Field(default_factory=dict)
    redactionQueue: list[MemberDeleteRequestReference] = Field(default_factory=list)
    updated: dict[str, int] = Field(default_factory=dict)
    decisionAudit: DecisionAuditRecord


class ReviewTarget(AITEAMOSModel):
    type: Literal["pull_request", "branch", "commit", "diff_patch", "external_review"]
    url: str | None = None
    ref: str | None = None
    description: str | None = None


class RunAssistedMemoryProposalInput(StrictAITEAMOSModel):
    title: str | None = None
    content: str | None = None
    kind: str = "procedural"
    confidence: float | None = Field(default=None, ge=0, le=1)
    reviewGuidance: str | None = None


class RunAssistedIngestInput(StrictAITEAMOSModel):
    journal: str | None = None
    diffPatch: str | None = None
    testLog: str | None = None
    reviewTarget: ReviewTarget | None = None
    memoryProposal: RunAssistedMemoryProposalInput | None = None


class RunAssistancePackageCommand(StrictAITEAMOSModel):
    label: str
    command: str
    purpose: str


class RunAssistancePackageContract(StrictAITEAMOSModel):
    requiredInputs: list[str] = Field(default_factory=list)
    expectedArtifacts: list[str] = Field(default_factory=list)
    reviewTargetTypes: list[str] = Field(default_factory=list)
    memoryProposalPolicy: str
    durableMutationBoundary: str


class RunAssistancePackageRecord(StrictAITEAMOSModel):
    run: str
    task: str
    project: str
    member: str
    memberKind: Literal["human", "digital", "hybrid", "service"]
    assignment: str | None = None
    mode: str
    status: str
    readyForAssistedExecution: bool
    packageKind: Literal["human_assisted_execution_package"] = "human_assisted_execution_package"
    generatedAt: str
    summary: str
    entrypoints: list[RunAssistancePackageCommand] = Field(default_factory=list)
    ideWorkspace: dict[str, Any] = Field(default_factory=dict)
    branch: dict[str, Any] = Field(default_factory=dict)
    allowedWrites: list[str] = Field(default_factory=list)
    readScope: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    contextSources: dict[str, int] = Field(default_factory=dict)
    selectedMemory: list[str] = Field(default_factory=list)
    handoffs: list[str] = Field(default_factory=list)
    ingestContract: RunAssistancePackageContract
    reviewContract: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class RunAssistanceBundleFile(StrictAITEAMOSModel):
    path: str
    mediaType: str = "text/markdown"
    purpose: str
    content: str
    sizeBytes: int = Field(ge=0)
    sensitive: bool = False


class RunAssistanceBundleRecord(StrictAITEAMOSModel):
    apiVersion: Literal["aiteamos.dev/v1alpha1"] = API_VERSION
    kind: Literal["AiteamosBundle"] = "AiteamosBundle"
    schemaVersion: Literal["aiteamos-bundle.v1"] = "aiteamos-bundle.v1"
    run: str
    task: str
    project: str
    member: str
    memberKind: Literal["human", "digital", "hybrid", "service"]
    assignment: str | None = None
    generatedAt: str
    bundleKind: Literal["human_hybrid_assisted_handoff_bundle"] = "human_hybrid_assisted_handoff_bundle"
    ready: bool
    package: RunAssistancePackageRecord
    files: list[RunAssistanceBundleFile] = Field(default_factory=list)
    fileCount: int = Field(ge=0)
    totalSizeBytes: int = Field(ge=0)
    ingestInputSchema: Literal["RunAssistedIngestInput"] = "RunAssistedIngestInput"
    secretHandling: Literal["references-only-no-secret-values"] = "references-only-no-secret-values"
    instructions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class RunReviewFindingInput(StrictAITEAMOSModel):
    severity: str = "medium"
    summary: str
    action: str | None = None


class RunReviewInput(StrictAITEAMOSModel):
    reviewer: str | None = None
    reviewerMember: str | None = None
    reviewer_member: str | None = None
    verdict: str = "approved"
    summary: str | None = None
    findings: list[RunReviewFindingInput] = Field(default_factory=list)
    target: ReviewTarget | None = None
    source: str = "dashboard-human-review"


class RunCloseoutInput(StrictAITEAMOSModel):
    actorMember: str | None = None
    actor_member: str | None = None
    reason: str | None = None


class RunSourceIntegrationInput(StrictAITEAMOSModel):
    actorMember: str | None = None
    actor_member: str | None = None
    reason: str | None = None


class RunSourceIntegrationRemediationInput(StrictAITEAMOSModel):
    actorMember: str | None = None
    actor_member: str | None = None
    reason: str | None = None


class RunProviderSourceIntegrationInput(StrictAITEAMOSModel):
    actorMember: str | None = None
    actor_member: str | None = None
    reason: str | None = None


class RunProviderSourceIntegrationExecuteInput(StrictAITEAMOSModel):
    actorMember: str | None = None
    actor_member: str | None = None
    reason: str | None = None
    dryRun: bool = True
    dry_run: bool | None = None


class SkillCreateInput(StrictAITEAMOSModel):
    name: str
    actorMember: str
    description: str | None = None
    ownerMember: str | None = None
    projects: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    requiredPermissions: list[str] = Field(default_factory=list)
    entrypoint: str | None = None
    lifecycle: Literal["proposed", "active", "deprecated", "archived"] = "active"
    reason: str | None = None


class SkillUpdateInput(StrictAITEAMOSModel):
    actorMember: str
    description: str | None = None
    ownerMember: str | None = None
    projects: list[str] | None = None
    capabilities: list[str] | None = None
    requiredPermissions: list[str] | None = None
    entrypoint: str | None = None
    lifecycle: Literal["proposed", "active", "deprecated", "archived"] | None = None
    reason: str | None = None


class SkillAttachMemberInput(StrictAITEAMOSModel):
    actorMember: str
    member: str | None = None
    growthSummary: str | None = None
    reason: str | None = None


class SkillArchiveInput(StrictAITEAMOSModel):
    actorMember: str
    reason: str | None = None


AutomationTargetType = Literal[
    "human_reminder",
    "digital_execution",
    "hybrid_assist",
    "service_task",
    "memory_health",
    "review",
    "task_planning",
    "manager_recommendation",
    "connector_failure_reminder",
    "git_activity_correlation_promotion",
    "git_activity_retention_sweep",
    "artifact_retention_sweep",
]

AutomationTriggerType = Literal["cron", "git_event", "pr_event", "issue_task_event", "test_failure", "memory_stale_conflict", "manual", "webhook"]


class AutomationRunActionInput(StrictAITEAMOSModel):
    actorMember: str | None = None
    actor_member: str | None = None
    sourceEvent: dict[str, Any] | None = None
    source_event: dict[str, Any] | None = None


class AutomationTriggerInput(StrictAITEAMOSModel):
    triggerType: AutomationTriggerType
    config: dict[str, Any] = Field(default_factory=dict)


class AutomationCreateInput(StrictAITEAMOSModel):
    name: str
    targetType: AutomationTargetType | None = None
    target_type: AutomationTargetType | None = None
    target: dict[str, Any] | None = None
    ownerMember: str | None = None
    owner_member: str | None = None
    serviceMember: str | None = None
    service_member: str | None = None
    project: str | None = None
    triggers: list[AutomationTriggerInput] | None = None
    dryRun: bool | None = None
    dry_run: bool | None = None
    status: Literal["active", "paused", "archived"] = "active"
    permissionPolicies: list[str] | None = None
    permission_policies: list[str] | None = None
    approvalGates: list[str] | None = None
    approval_gates: list[str] | None = None


class ReviewFinding(AITEAMOSModel):
    id: str
    severity: str = "medium"
    summary: str
    action: str | None = None


class ReviewSpec(AITEAMOSModel):
    project: str
    task: str | None = None
    run: str | None = None
    reviewer: str
    reviewerMember: str | None = None
    reviewerKind: Literal["human", "digital", "hybrid", "service"] | None = None
    source: str | None = None
    verdict: str
    target: ReviewTarget | None = None
    findings: list[ReviewFinding] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class Review(Manifest):
    kind: Literal["Review"]
    spec: ReviewSpec


class MemoryProposalSpec(AITEAMOSModel):
    project: str
    member: str | None = None
    assignment: str | None = None
    store: str | None = None
    entryPath: str | None = None
    sourceRun: str | None = None
    sourceTask: str | None = None
    sourceIngestId: str | None = None
    sourceExtractorId: str | None = None
    dedupeKey: str | None = None
    status: str = "pending-review"
    approvedMemory: str | None = None
    kind: str
    title: str
    content: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reviewGuidance: str | None = None
    reviewedAt: str | None = None
    reviewedByMember: str | None = None
    reviewReason: str | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class MemoryProposal(Manifest):
    kind: Literal["MemoryProposal"]
    spec: MemoryProposalSpec


LearningExtractionProposalKind = Literal["memory", "skill", "growth", "retrospective"]


class LearningExtractionProposal(AITEAMOSModel):
    kind: LearningExtractionProposalKind
    targetKind: str | None = None
    targetManifest: dict[str, Any]
    summary: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    dedupeKey: str | None = None
    reviewGuidance: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_target_manifest_kind(self) -> "LearningExtractionProposal":
        expected_targets = {
            "memory": "MemoryProposal",
            "skill": "SkillProposal",
            "growth": "GrowthSignal",
            "retrospective": "RetrospectiveCandidate",
        }
        expected = expected_targets[self.kind]
        manifest_kind = self.targetManifest.get("kind")
        if not manifest_kind:
            raise ValueError("learning extraction proposal targetManifest requires kind")
        if manifest_kind != expected:
            raise ValueError(f"{self.kind} learning proposals must target {expected}")
        if self.targetKind is None:
            self.targetKind = manifest_kind
        elif self.targetKind != expected:
            raise ValueError(f"{self.kind} learning proposals must use targetKind {expected}")
        return self


class LearningExtractionSourceContext(AITEAMOSModel):
    project: str | None = None
    taskId: str | None = None
    member: str | None = None
    assignment: str | None = None
    runStatus: str | None = None
    sourceJournalPath: str | None = None
    sourceEventLedger: str | None = None


class LearningExtractionSpec(AITEAMOSModel):
    runId: str
    extractedAt: str
    dedupeKey: str
    extractorId: str = "aiteamos.learning-extractor"
    extractorVersion: str = "v1"
    sourceContext: LearningExtractionSourceContext = Field(default_factory=LearningExtractionSourceContext)
    proposals: list[LearningExtractionProposal] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class LearningExtraction(Manifest):
    kind: Literal["LearningExtraction"]
    spec: LearningExtractionSpec


class MemoryACL(AITEAMOSModel):
    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)
    reference: list[str] = Field(default_factory=list)
    promote: list[str] = Field(default_factory=list)
    export: list[str] = Field(default_factory=list)
    share: list[str] = Field(default_factory=list)


class MemoryStoreSpec(AITEAMOSModel):
    storeType: Literal["project", "member", "team", "domain", "organization", "temporary", "imported"]
    ownerProject: str | None = None
    ownerMember: str | None = None
    ownerTeam: str | None = None
    domain: str | None = None
    description: str | None = None
    visibility: Literal["private", "project", "team", "organization", "public"] = "private"
    lifecycle: Literal["active", "stale", "deprecated", "redacted", "archived"] = "active"
    acl: MemoryACL = Field(default_factory=MemoryACL)
    retention: dict[str, Any] = Field(default_factory=dict)
    createdByMember: str | None = None
    reviewReason: str | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class MemoryStore(Manifest):
    kind: Literal["MemoryStore"]
    spec: MemoryStoreSpec


class MemoryLineageRef(AITEAMOSModel):
    sourceRun: str | None = None
    sourceTask: str | None = None
    authorMember: str | None = None
    reviewerMember: str | None = None
    evidence: list[str] = Field(default_factory=list)
    relatedDiffs: list[str] = Field(default_factory=list)
    relatedTests: list[str] = Field(default_factory=list)
    relatedReviews: list[str] = Field(default_factory=list)


class MemoryEvalEvidenceRef(AITEAMOSModel):
    evalSuiteId: str
    lastResultId: str
    passRate: float | None = Field(default=None, ge=0, le=1)
    threshold: float | None = Field(default=None, ge=0, le=1)


class MemoryEntrySpec(AITEAMOSModel):
    store: str
    path: str
    title: str
    content: str
    kind: Literal[
        "semantic",
        "episodic",
        "procedural",
        "decision",
        "mistake",
        "preference",
        "skill",
        "project-status",
        "external-note",
    ]
    scope: Literal["member", "project", "team", "org", "domain", "task", "run"]
    source: str | None = None
    evidence: list[str] = Field(default_factory=list)
    evalEvidence: list[MemoryEvalEvidenceRef] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    freshness: str | None = None
    lastVerifiedAt: str | None = None
    sensitivity: Literal["public", "internal", "confidential", "secret"] = "internal"
    visibility: Literal["private", "project", "team", "organization", "public"] = "private"
    acl: MemoryACL = Field(default_factory=MemoryACL)
    tags: list[str] = Field(default_factory=list)
    relatedProjects: list[str] = Field(default_factory=list)
    relatedMembers: list[str] = Field(default_factory=list)
    relatedAssignments: list[str] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    lineage: MemoryLineageRef = Field(default_factory=MemoryLineageRef)
    supersedes: list[str] = Field(default_factory=list)
    conflictsWith: list[str] = Field(default_factory=list)
    lifecycle: Literal["candidate", "active", "stale", "deprecated", "conflicted", "redacted", "archived"] = "candidate"
    embedding: dict[str, Any] = Field(default_factory=dict)
    createdByMember: str | None = None
    reviewReason: str | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class MemoryEntry(Manifest):
    kind: Literal["MemoryEntry"]
    spec: MemoryEntrySpec


class MemoryVersionSpec(AITEAMOSModel):
    entry: str
    store: str
    version: int = Field(ge=1)
    operation: Literal["create", "update", "delete", "redact"]
    contentSha256: str | None = None
    createdAt: str | None = None
    createdByMember: str | None = None
    redacted: bool = False


class MemoryVersion(Manifest):
    kind: Literal["MemoryVersion"]
    spec: MemoryVersionSpec


class MemoryBindingSpec(AITEAMOSModel):
    store: str | None = None
    entry: str | None = None
    collectionPath: str | None = None
    targetType: Literal["member", "project", "assignment", "task", "run", "team", "context-capsule"]
    targetId: str
    access: list[Literal["read", "write", "reference", "inject", "promote", "export", "share"]] = Field(default_factory=lambda: ["read", "reference"])
    reason: str | None = None
    status: Literal["active", "paused", "revoked", "archived"] = "active"
    createdByMember: str | None = None


class MemoryBinding(Manifest):
    kind: Literal["MemoryBinding"]
    spec: MemoryBindingSpec


class MemoryGrantSpec(AITEAMOSModel):
    granteeMember: str
    grantorMember: str | None = None
    task: str | None = None
    run: str | None = None
    stores: list[str] = Field(default_factory=list)
    entries: list[str] = Field(default_factory=list)
    access: list[Literal["read", "reference", "inject"]] = Field(default_factory=lambda: ["read", "reference", "inject"])
    reason: str | None = None
    expiresAt: str | None = None
    status: Literal["active", "expired", "revoked"] = "active"


class MemoryGrant(Manifest):
    kind: Literal["MemoryGrant"]
    spec: MemoryGrantSpec


class MemoryStoreCreateInput(StrictAITEAMOSModel):
    name: str
    actorMember: str
    storeType: Literal["project", "member", "team", "domain", "organization", "temporary", "imported"]
    ownerProject: str | None = None
    ownerMember: str | None = None
    ownerTeam: str | None = None
    domain: str | None = None
    description: str | None = None
    visibility: Literal["private", "project", "team", "organization", "public"] = "private"
    lifecycle: Literal["active", "stale", "deprecated", "redacted", "archived"] = "active"
    acl: MemoryACL = Field(default_factory=MemoryACL)
    retention: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class MemoryEntryCreateInput(StrictAITEAMOSModel):
    title: str
    content: str
    actorMember: str
    store: str
    path: str | None = None
    kind: Literal[
        "semantic",
        "episodic",
        "procedural",
        "decision",
        "mistake",
        "preference",
        "skill",
        "project-status",
        "external-note",
    ] = "procedural"
    scope: Literal["member", "project", "team", "org", "domain", "task", "run"] = "project"
    source: str | None = None
    evidence: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)
    freshness: str | None = None
    sensitivity: Literal["public", "internal", "confidential", "secret"] = "internal"
    visibility: Literal["private", "project", "team", "organization", "public"] = "private"
    acl: MemoryACL = Field(default_factory=MemoryACL)
    tags: list[str] = Field(default_factory=list)
    relatedProjects: list[str] = Field(default_factory=list)
    relatedMembers: list[str] = Field(default_factory=list)
    relatedAssignments: list[str] = Field(default_factory=list)
    lifecycle: Literal["candidate", "active", "stale", "deprecated", "conflicted", "redacted", "archived"] = "active"
    reason: str | None = None
    bindTargetType: Literal["member", "project", "assignment", "task", "run", "team", "context-capsule"] | None = None
    bindTargetId: str | None = None
    bindAccess: list[Literal["read", "write", "reference", "inject", "promote", "export", "share"]] = Field(
        default_factory=lambda: ["read", "reference", "inject"]
    )
    bindReason: str | None = None


class EvalCase(AITEAMOSModel):
    id: str | None = None
    title: str
    task: str | None = None
    member: str | None = None
    assignment: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)
    goldenOutputs: dict[str, Any] = Field(default_factory=dict)
    goldenOutputRefs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class EvalJudge(AITEAMOSModel):
    kind: Literal["human", "model", "policy"] = "policy"
    member: str | None = None
    modelProfile: str | None = None
    policyRef: str | None = None
    rubric: list[str] = Field(default_factory=list)
    passCriteria: dict[str, Any] = Field(default_factory=dict)


class EvalSuitePolicy(AITEAMOSModel):
    autoPromoteThreshold: float | None = Field(default=None, ge=0, le=1)
    minCases: int = Field(default=1, ge=1)
    requireAllGoldenOutputs: bool = True


class EvalSuiteSpec(AITEAMOSModel):
    project: str
    purpose: str | None = None
    members: list[str] = Field(default_factory=list)
    assignments: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)
    cases: list[EvalCase] = Field(default_factory=list)
    goldenOutputs: dict[str, Any] = Field(default_factory=dict)
    judge: EvalJudge = Field(default_factory=EvalJudge)
    policy: EvalSuitePolicy = Field(default_factory=EvalSuitePolicy)
    metrics: list[str] = Field(default_factory=list)


class EvalSuite(Manifest):
    kind: Literal["EvalSuite"]
    spec: EvalSuiteSpec


class EvalCaseResult(AITEAMOSModel):
    caseId: str | None = None
    caseTitle: str | None = None
    status: Literal["pass", "fail", "skip"] = "pass"
    score: float | None = Field(default=None, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    message: str | None = None


class EvalResultSpec(AITEAMOSModel):
    evalSuite: str
    project: str
    evaluatedAt: str | None = None
    task: str | None = None
    run: str | None = None
    member: str | None = None
    assignment: str | None = None
    status: Literal["pass", "fail", "mixed"] = "pass"
    totalCases: int = Field(default=0, ge=0)
    passedCases: int = Field(default=0, ge=0)
    failedCases: int = Field(default=0, ge=0)
    passRate: float = Field(default=0, ge=0, le=1)
    caseResults: list[EvalCaseResult] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    summary: str | None = None


class EvalResult(Manifest):
    kind: Literal["EvalResult"]
    spec: EvalResultSpec


class ArtifactSpec(AITEAMOSModel):
    run: str | None = None
    sourceRun: str | None = None
    kind: str
    uri: str | None = None
    path: str | None = None
    url: str | None = None
    ref: str | None = None
    sha256: str | None = None
    sizeBytes: int | None = Field(default=None, ge=0)
    retention: str | None = None
    lifecycle: Literal["active", "archived", "redacted"] = "active"
    retainedUntil: str | None = None
    archivedAt: str | None = None
    redactedAt: str | None = None
    sensitivity: str | None = None
    exportPolicy: Literal["include", "sanitize", "manifest_only", "manifest-only", "exclude"] | None = None
    redactionPolicy: str | None = None
    redaction: dict[str, Any] = Field(default_factory=dict)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class Artifact(Manifest):
    kind: Literal["Artifact"]
    spec: ArtifactSpec


class ArtifactStoreSecretRefs(StrictAITEAMOSModel):
    accessKeyIdEnv: str | None = None
    secretAccessKeyEnv: str | None = None
    sessionTokenEnv: str | None = None
    tokenEnv: str | None = None

    @field_validator("accessKeyIdEnv", "secretAccessKeyEnv", "sessionTokenEnv", "tokenEnv")
    @classmethod
    def validate_env_name(cls, value: str | None) -> str | None:
        if value is not None and not ENV_NAME_RE.match(value):
            raise ValueError("artifact store secret references must be environment variable names")
        return value


class ArtifactStoreSpec(StrictAITEAMOSModel):
    project: str
    backend: Literal["local", "s3", "minio", "git_lfs"]
    default: bool = False
    localPath: str | None = None
    bucket: str | None = None
    endpointUrl: str | None = None
    region: str | None = None
    prefix: str | None = None
    retentionPolicy: str | None = None
    secrets: ArtifactStoreSecretRefs = Field(default_factory=ArtifactStoreSecretRefs)

    @model_validator(mode="after")
    def require_backend_location(self) -> "ArtifactStoreSpec":
        if self.backend == "local" and not self.localPath:
            raise ValueError("local artifact stores require localPath")
        if self.backend in {"s3", "minio"} and not self.bucket:
            raise ValueError(f"{self.backend} artifact stores require bucket")
        return self


class ArtifactStore(Manifest):
    kind: Literal["ArtifactStore"]
    spec: ArtifactStoreSpec


class TeamSpec(AITEAMOSModel):
    description: str | None = None
    members: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    memoryStores: list[str] = Field(default_factory=list)
    permissionPolicies: list[str] = Field(default_factory=list)


class Team(Manifest):
    kind: Literal["Team"]
    spec: TeamSpec


class MemberMessageSpec(AITEAMOSModel):
    fromMember: str
    toMembers: list[str] = Field(default_factory=list)
    channel: str | None = None
    messageType: Literal[
        "message",
        "ask-for-help",
        "review-request",
        "knowledge-share",
        "handoff-note",
        "plan-recommendation",
        "cost-alert",
    ] = "message"
    status: Literal["open", "acknowledged", "resolved", "archived"] = "open"
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    project: str | None = None
    task: str | None = None
    run: str | None = None
    body: str
    attachments: list[str] = Field(default_factory=list)
    requestedResponseBy: str | None = None
    resolvedAt: str | None = None
    resolvedByMember: str | None = None
    resolution: str | None = None
    audit: dict[str, Any] = Field(default_factory=dict)
    lifecycle: Literal["active", "archived", "redacted"] = "active"
    archivedAt: str | None = None
    redactedAt: str | None = None
    redactionPolicy: str | None = None
    exportPolicy: Literal["include", "sanitize", "manifest-only", "exclude"] = "sanitize"
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class MemberMessage(Manifest):
    kind: Literal["MemberMessage"]
    spec: MemberMessageSpec


class HandoffSpec(AITEAMOSModel):
    fromMember: str
    toMember: str
    task: str
    run: str | None = None
    project: str | None = None
    sourceBranch: str | None = None
    targetBranch: str | None = None
    problem: str
    knownContext: list[str] = Field(default_factory=list)
    recommendedNextStep: str | None = None
    sharedMemoryPack: list[str] = Field(default_factory=list)
    ownership: Literal["transfer", "copy", "consult"] = "transfer"
    status: Literal["requested", "accepted", "declined", "completed", "cancelled"] = "requested"
    lifecycle: Literal["active", "archived", "redacted"] = "active"
    archivedAt: str | None = None
    redactedAt: str | None = None
    redactionPolicy: str | None = None
    exportPolicy: Literal["include", "sanitize", "manifest-only", "exclude"] = "sanitize"
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class Handoff(Manifest):
    kind: Literal["Handoff"]
    spec: HandoffSpec


class TeamRetrospectiveSpec(AITEAMOSModel):
    project: str
    facilitatorMember: str
    participants: list[str] = Field(default_factory=list)
    sourceTaskPlan: str | None = None
    sourceRuns: list[str] = Field(default_factory=list)
    sourceTasks: list[str] = Field(default_factory=list)
    sourceMessages: list[str] = Field(default_factory=list)
    sourceHandoffs: list[str] = Field(default_factory=list)
    summary: str
    lessons: list[str] = Field(default_factory=list)
    actionItems: list[str] = Field(default_factory=list)
    proposedMemory: str | None = None
    status: Literal["draft", "proposed", "reviewed", "archived"] = "proposed"
    audit: dict[str, Any] = Field(default_factory=dict)


class TeamRetrospective(Manifest):
    kind: Literal["TeamRetrospective"]
    spec: TeamRetrospectiveSpec


class AutomationTrigger(AITEAMOSModel):
    triggerType: Literal["cron", "git_event", "pr_event", "issue_task_event", "test_failure", "memory_stale_conflict", "manual", "webhook"]
    config: dict[str, Any] = Field(default_factory=dict)


class AutomationSpec(AITEAMOSModel):
    ownerMember: str | None = None
    serviceMember: str | None = None
    project: str | None = None
    targetType: Literal[
        "human_reminder",
        "digital_execution",
        "hybrid_assist",
        "service_task",
        "memory_health",
        "review",
        "task_planning",
        "manager_recommendation",
        "connector_failure_reminder",
        "git_activity_correlation_promotion",
        "git_activity_retention_sweep",
        "artifact_retention_sweep",
    ]
    target: dict[str, Any] = Field(default_factory=dict)
    triggers: list[AutomationTrigger] = Field(default_factory=list)
    dryRun: bool = True
    status: Literal["active", "paused", "archived"] = "active"
    permissionPolicies: list[str] = Field(default_factory=list)
    approvalGates: list[str] = Field(default_factory=list)


class Automation(Manifest):
    kind: Literal["Automation"]
    spec: AutomationSpec


class AutomationRunSpec(AITEAMOSModel):
    automation: str
    project: str | None = None
    ownerMember: str | None = None
    serviceMember: str | None = None
    targetType: Literal[
        "human_reminder",
        "digital_execution",
        "hybrid_assist",
        "service_task",
        "memory_health",
        "review",
        "task_planning",
        "manager_recommendation",
        "connector_failure_reminder",
        "git_activity_correlation_promotion",
        "git_activity_retention_sweep",
        "artifact_retention_sweep",
    ]
    target: dict[str, Any] = Field(default_factory=dict)
    triggerType: Literal["cron", "git_event", "pr_event", "issue_task_event", "test_failure", "memory_stale_conflict", "manual", "webhook"] = "manual"
    sourceEvent: dict[str, Any] = Field(default_factory=dict)
    dryRun: bool = True
    status: Literal["dry-run", "pending-approval", "queued", "running", "succeeded", "failed", "blocked"] = "dry-run"
    requestedByMember: str | None = None
    approvalGates: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)
    permissionPolicies: list[str] = Field(default_factory=list)
    permissionDecisions: list[dict[str, Any]] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    createdTask: str | None = None
    createdRun: str | None = None
    createdTaskPlan: str | None = None
    createdMessage: str | None = None
    startedAt: str | None = None
    finishedAt: str | None = None
    summary: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class AutomationRun(Manifest):
    kind: Literal["AutomationRun"]
    spec: AutomationRunSpec


class AutomationTriggerEventSpec(AITEAMOSModel):
    automation: str
    project: str | None = None
    triggerType: Literal["cron", "git_event", "pr_event", "issue_task_event", "test_failure", "memory_stale_conflict", "manual", "webhook"] = "manual"
    source: Literal["scheduler", "webhook", "git_provider", "manual", "test", "system"] = "manual"
    actorMember: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    dedupeKey: str | None = None
    dryRun: bool = False
    status: Literal["accepted", "ignored", "blocked"] = "accepted"
    automationRun: str | None = None
    receivedAt: str | None = None
    summary: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class AutomationTriggerEvent(Manifest):
    kind: Literal["AutomationTriggerEvent"]
    spec: AutomationTriggerEventSpec


class AutomationProviderDeliverySpec(AITEAMOSModel):
    automation: str
    project: str | None = None
    connector: str | None = None
    provider: str
    eventType: str | None = None
    triggerType: Literal["cron", "git_event", "pr_event", "issue_task_event", "test_failure", "memory_stale_conflict", "manual", "webhook"] = "webhook"
    deliveryId: str
    dedupeKey: str
    payloadDigest: str
    payloadDigestAlgorithm: Literal["sha256"] = "sha256"
    receivedAt: str | None = None
    firstSeenAt: str | None = None
    lastSeenAt: str | None = None
    attemptCount: int = Field(default=1, ge=0)
    replayWindowSeconds: int | None = None
    replayStatus: Literal["accepted", "duplicate", "stale", "blocked"] = "accepted"
    admissionStatus: Literal["accepted", "duplicate", "blocked"] = "accepted"
    retryStatus: Literal["not_requested", "requested", "admitted", "blocked"] = "not_requested"
    retryRequestedAt: str | None = None
    retryRequestedByMember: str | None = None
    retryDelivery: str | None = None
    retryAutomationTriggerEvent: str | None = None
    retryAutomationRun: str | None = None
    retryAttempts: list[dict[str, Any]] = Field(default_factory=list)
    lifecycle: Literal["active", "archived"] = "active"
    retainedUntil: str | None = None
    archivedAt: str | None = None
    automationTriggerEvent: str | None = None
    automationRun: str | None = None
    normalized: dict[str, Any] = Field(default_factory=dict)
    safeHeaders: dict[str, str] = Field(default_factory=dict)
    summary: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class AutomationProviderDelivery(Manifest):
    kind: Literal["AutomationProviderDelivery"]
    spec: AutomationProviderDeliverySpec


class AutomationSchedulerLeaseSpec(AITEAMOSModel):
    automation: str
    project: str | None = None
    triggerType: Literal["cron"] = "cron"
    schedulerId: str
    tickKey: str
    cron: str | None = None
    dueAt: str | None = None
    leaseAcquiredAt: str | None = None
    leaseExpiresAt: str | None = None
    heartbeatAt: str | None = None
    status: Literal["leased", "emitted", "skipped", "blocked", "expired"] = "leased"
    automationTriggerEvent: str | None = None
    automationRun: str | None = None
    dedupeKey: str | None = None
    summary: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class AutomationSchedulerLease(Manifest):
    kind: Literal["AutomationSchedulerLease"]
    spec: AutomationSchedulerLeaseSpec


class AutomationApprovalSpec(AITEAMOSModel):
    automationRun: str
    automation: str
    project: str | None = None
    approvalWorkflow: str | None = None
    reviewerMember: str
    reviewerKind: Literal["human", "digital", "hybrid", "service"] | None = None
    decision: Literal["approved", "rejected"]
    approvalGates: list[str] = Field(default_factory=list)
    reason: str | None = None
    decidedAt: str | None = None
    expiresAt: str | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class AutomationApproval(Manifest):
    kind: Literal["AutomationApproval"]
    spec: AutomationApprovalSpec


class ApprovalWorkflowSLA(AITEAMOSModel):
    durationSeconds: int = Field(..., ge=1)
    startsAt: Literal["workflow-created", "stage-entered", "previous-stage-completed"] = "stage-entered"
    dueAt: str | None = None
    warningAfterSeconds: int | None = Field(default=None, ge=1)


class ApprovalWorkflowEscalation(AITEAMOSModel):
    targetMember: str
    afterSlaBreach: bool = True
    messageType: Literal["review-request"] = "review-request"
    reason: str | None = None


class ApprovalWorkflowStage(AITEAMOSModel):
    id: str
    kind: Literal["every-of", "any-of", "quorum"]
    reviewerMembers: list[str] = Field(default_factory=list)
    reviewerKinds: list[Literal["human", "hybrid", "service"]] = Field(default_factory=lambda: ["human", "hybrid"])
    quorum: int | None = Field(default=None, ge=1)
    sla: ApprovalWorkflowSLA
    escalation: ApprovalWorkflowEscalation | None = None
    approvals: list[str] = Field(default_factory=list)
    status: Literal["pending", "satisfied", "rejected", "expired", "escalated"] = "pending"

    @model_validator(mode="after")
    def validate_quorum_shape(self) -> "ApprovalWorkflowStage":
        if self.kind == "quorum":
            if self.quorum is None:
                raise ValueError("quorum approval stages require quorum")
            if self.reviewerMembers and self.quorum > len(self.reviewerMembers):
                raise ValueError("quorum approval stages cannot require more approvals than reviewerMembers")
        elif self.quorum is not None:
            raise ValueError("only quorum approval stages may set quorum")
        return self


class ApprovalWorkflowSpec(AITEAMOSModel):
    project: str | None = None
    subjectKind: str
    subjectRef: str
    requesterMember: str | None = None
    ownerMember: str | None = None
    status: Literal["draft", "pending", "approved", "rejected", "expired", "cancelled", "escalated"] = "pending"
    stages: list[ApprovalWorkflowStage] = Field(..., min_length=1)
    currentStage: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    completedAt: str | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_current_stage(self) -> "ApprovalWorkflowSpec":
        stage_ids = [stage.id for stage in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("approval workflow stage ids must be unique")
        if self.currentStage is not None and self.currentStage not in set(stage_ids):
            raise ValueError("approval workflow currentStage must reference an existing stage")
        return self


class ApprovalWorkflow(Manifest):
    kind: Literal["ApprovalWorkflow"]
    spec: ApprovalWorkflowSpec


class PermissionRule(AITEAMOSModel):
    match: str
    reason: str | None = None


class PermissionPolicySpec(AITEAMOSModel):
    scope: dict[str, str] = Field(default_factory=dict)
    defaultMode: Literal["allow", "ask", "deny"] = "ask"
    allow: list[PermissionRule] = Field(default_factory=list)
    ask: list[PermissionRule] = Field(default_factory=list)
    deny: list[PermissionRule] = Field(default_factory=list)
    sensitivePaths: list[str] = Field(default_factory=list)
    inheritance: dict[str, Any] = Field(default_factory=dict)
    expiresAt: str | None = None


class PermissionPolicy(Manifest):
    kind: Literal["PermissionPolicy"]
    spec: PermissionPolicySpec


class PermissionAction(AITEAMOSModel):
    tool: str | None = None
    value: str | None = None
    path: str | None = None
    command: str | None = None
    url: str | None = None
    domain: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    protocol: str | None = None
    mcpServer: str | None = None
    mcpTool: str | None = None
    envVar: str | None = None
    connector: str | None = None
    connectorType: str | None = None
    connectorScope: str | None = None
    artifactStore: str | None = None
    artifactKind: str | None = None
    retentionPolicy: str | None = None
    exportPolicy: Literal["include", "sanitize", "manifest_only", "exclude"] | None = None
    redactionMode: str | None = None
    sensitivity: str | None = None
    operation: str | None = None
    target: str | None = None
    resource: str | None = None
    risk: Literal["low", "medium", "high", "critical"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("envVar")
    @classmethod
    def validate_env_name(cls, value: str | None) -> str | None:
        if value is not None and not ENV_NAME_RE.match(value):
            raise ValueError("permission environment variable references must be environment variable names")
        return value


class PermissionRequestSpec(AITEAMOSModel):
    project: str | None = None
    member: str
    assignment: str | None = None
    task: str | None = None
    run: str | None = None
    automation: str | None = None
    automationRun: str | None = None
    approvalWorkflow: str | None = None
    requesterMember: str | None = None
    reviewerMember: str | None = None
    action: PermissionAction = Field(default_factory=PermissionAction)
    reason: str | None = None
    status: Literal["pending", "approved", "rejected", "cancelled", "expired"] = "pending"
    currentDecision: dict[str, Any] = Field(default_factory=dict)
    decidedAt: str | None = None
    expiresAt: str | None = None
    grant: str | None = None
    source: str | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class PermissionRequest(Manifest):
    kind: Literal["PermissionRequest"]
    spec: PermissionRequestSpec


class PermissionGrantSpec(AITEAMOSModel):
    scope: dict[str, str] = Field(default_factory=dict)
    action: PermissionAction = Field(default_factory=PermissionAction)
    sourceRequest: str | None = None
    approvedByMember: str | None = None
    reason: str | None = None
    status: Literal["active", "revoked", "expired"] = "active"
    expiresAt: str | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class PermissionGrant(Manifest):
    kind: Literal["PermissionGrant"]
    spec: PermissionGrantSpec


class SkillSpec(AITEAMOSModel):
    description: str | None = None
    ownerMember: str | None = None
    projects: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    requiredPermissions: list[str] = Field(default_factory=list)
    entrypoint: str | None = None
    lifecycle: Literal["proposed", "active", "deprecated", "archived"] = "proposed"
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)


class Skill(Manifest):
    kind: Literal["Skill"]
    spec: SkillSpec


class SkillProjectionSpec(AITEAMOSModel):
    skill: str
    ownerMember: str | None = None
    lifecycle: Literal["proposed", "active", "deprecated", "archived"] | None = None
    projects: list[str] = Field(default_factory=list)
    projectCount: int = 0
    members: list[str] = Field(default_factory=list)
    memberCount: int = 0
    assignments: list[str] = Field(default_factory=list)
    assignmentCount: int = 0
    tasks: list[str] = Field(default_factory=list)
    taskCount: int = 0
    runs: list[str] = Field(default_factory=list)
    runCount: int = 0
    capabilities: list[str] = Field(default_factory=list)
    requiredPermissions: list[str] = Field(default_factory=list)
    memberFitReasons: list[str] = Field(default_factory=list)
    fitSignal: str | None = None
    redacted: bool = False
    redactionReason: str | None = None


class SkillProjectionRecord(StrictAITEAMOSModel):
    id: str
    kind: Literal["SkillProjection"] = "SkillProjection"
    redacted: bool = False
    redactionReason: str | None = None
    spec: SkillProjectionSpec


class GitProviderActorMapping(AITEAMOSModel):
    actorLogin: str | None = None
    actorLoginSha256: str | None = None
    actorEmailSha256: str | None = None
    member: str | None = None
    assignment: str | None = None
    policy: Literal["map-to-member", "needs-review", "ignore"] = "needs-review"
    reason: str | None = None


class GitActivityImportConnectorPolicy(AITEAMOSModel):
    enabled: bool = False
    allowedRepositories: list[str] = Field(default_factory=list)
    allowedInstallationIds: list[str] = Field(default_factory=list)
    protectedRefPatterns: list[str] = Field(default_factory=list)
    actorMappings: list[GitProviderActorMapping] = Field(default_factory=list)
    defaultMember: str | None = None
    defaultAssignment: str | None = None
    importPolicy: Literal["reviewed-import", "service-policy-import"] = "reviewed-import"
    autoPromotion: Literal["disabled", "service-policy"] = "disabled"
    dedupeStrategy: list[Literal["payload-digest", "external-id", "commit-ref", "pr-number", "squash-merge"]] = Field(
        default_factory=lambda: ["external-id", "commit-ref", "payload-digest"]
    )
    requireHealthyConnector: bool = False


class ConnectorSpec(AITEAMOSModel):
    provider: str
    connectorType: Literal["git", "issue", "chat", "calendar", "mcp", "artifact", "model", "other"] = "other"
    ownerMember: str | None = None
    projects: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    secretRefs: dict[str, str] = Field(default_factory=dict)
    permissionPolicies: list[str] = Field(default_factory=list)
    gitActivityImport: GitActivityImportConnectorPolicy = Field(default_factory=GitActivityImportConnectorPolicy)


class Connector(Manifest):
    kind: Literal["Connector"]
    spec: ConnectorSpec


class ConnectorHealthCheckSpec(AITEAMOSModel):
    connector: str
    provider: str
    connectorType: Literal["git", "issue", "chat", "calendar", "mcp", "artifact", "model", "other"] = "other"
    project: str | None = None
    checkedAt: str | None = None
    status: Literal["healthy", "degraded", "blocked", "unknown"] = "unknown"
    readiness: Literal["ready", "degraded", "blocked", "unknown"] = "unknown"
    tokenStatus: Literal["present", "missing", "not_configured", "not_checked"] = "not_checked"
    installationStatus: Literal["authorized", "mismatched", "not_configured", "not_checked"] = "not_checked"
    lifecycle: Literal["active", "archived"] = "active"
    retainedUntil: str | None = None
    archivedAt: str | None = None
    requiredSecrets: dict[str, str] = Field(default_factory=dict)
    missingSecrets: list[str] = Field(default_factory=list)
    allowedRepositories: list[str] = Field(default_factory=list)
    observedRepositories: list[str] = Field(default_factory=list)
    allowedInstallationIds: list[str] = Field(default_factory=list)
    observedInstallationIds: list[str] = Field(default_factory=list)
    providerNetworkCalled: bool = False
    providerProbeStatus: Literal["passed", "failed", "not_configured", "not_checked"] = "not_checked"
    requiredProviderScopes: list[str] = Field(default_factory=list)
    observedProviderScopes: list[str] = Field(default_factory=list)
    missingProviderScopes: list[str] = Field(default_factory=list)
    providerDiagnostics: dict[str, Any] = Field(default_factory=dict)
    retentionPolicy: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)


class ConnectorHealthCheck(Manifest):
    kind: Literal["ConnectorHealthCheck"]
    spec: ConnectorHealthCheckSpec


class ModelProfilePricing(StrictAITEAMOSModel):
    currency: Literal["USD"] = "USD"
    inputUsdPer1MTokens: float | None = Field(default=None, ge=0)
    outputUsdPer1MTokens: float | None = Field(default=None, ge=0)
    requestUsd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_pricing_signal(self) -> "ModelProfilePricing":
        if not any(
            value is not None
            for value in [
                self.inputUsdPer1MTokens,
                self.outputUsdPer1MTokens,
                self.requestUsd,
            ]
        ):
            raise ValueError("model profile pricing must set at least one price")
        return self


class ModelProfileSpec(AITEAMOSModel):
    provider: str
    model: str
    displayName: str | None = None
    gateway: str = "litellm"
    secretEnv: str | None = None
    invocation: dict[str, Any] = Field(default_factory=dict)
    pricing: ModelProfilePricing | None = None
    capabilities: list[str] = Field(default_factory=list)
    defaultForMembers: list[str] = Field(default_factory=list)
    defaultForAssignments: list[str] = Field(default_factory=list)
    notes: str | None = None


class ModelProfile(Manifest):
    kind: Literal["ModelProfile"]
    spec: ModelProfileSpec


class BudgetPolicyScope(StrictAITEAMOSModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, json_schema_extra={"minProperties": 1})

    project: str | None = None
    member: str | None = None
    assignment: str | None = None
    task: str | None = None

    @model_validator(mode="after")
    def require_scope_target(self) -> "BudgetPolicyScope":
        if not any([self.project, self.member, self.assignment, self.task]):
            raise ValueError("budget policy scope must set project, member, assignment, or task")
        return self


class BudgetPolicyLimits(StrictAITEAMOSModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, json_schema_extra={"minProperties": 1})

    softUsdPerRun: float | None = Field(default=None, ge=0)
    softUsdPerDay: float | None = Field(default=None, ge=0)
    softInputTokensPerRun: int | None = Field(default=None, ge=0)
    softOutputTokensPerRun: int | None = Field(default=None, ge=0)
    softRetriesPerRun: int | None = Field(default=None, ge=0)
    maxUsdPerRun: float | None = Field(default=None, ge=0)
    maxUsdPerDay: float | None = Field(default=None, ge=0)
    maxInputTokensPerRun: int | None = Field(default=None, ge=0)
    maxOutputTokensPerRun: int | None = Field(default=None, ge=0)
    maxRetriesPerRun: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_at_least_one_limit(self) -> "BudgetPolicyLimits":
        if not any(
            value is not None
            for value in [
                self.softUsdPerRun,
                self.softUsdPerDay,
                self.softInputTokensPerRun,
                self.softOutputTokensPerRun,
                self.softRetriesPerRun,
                self.maxUsdPerRun,
                self.maxUsdPerDay,
                self.maxInputTokensPerRun,
                self.maxOutputTokensPerRun,
                self.maxRetriesPerRun,
            ]
        ):
            raise ValueError("budget policy limits must set at least one limit")
        return self

    @model_validator(mode="after")
    def require_soft_limits_not_above_hard_limits(self) -> "BudgetPolicyLimits":
        pairs = [
            ("softUsdPerRun", self.softUsdPerRun, "maxUsdPerRun", self.maxUsdPerRun),
            ("softUsdPerDay", self.softUsdPerDay, "maxUsdPerDay", self.maxUsdPerDay),
            ("softInputTokensPerRun", self.softInputTokensPerRun, "maxInputTokensPerRun", self.maxInputTokensPerRun),
            ("softOutputTokensPerRun", self.softOutputTokensPerRun, "maxOutputTokensPerRun", self.maxOutputTokensPerRun),
            ("softRetriesPerRun", self.softRetriesPerRun, "maxRetriesPerRun", self.maxRetriesPerRun),
        ]
        for soft_name, soft_value, hard_name, hard_value in pairs:
            if soft_value is not None and hard_value is not None and soft_value > hard_value:
                raise ValueError(f"{soft_name} must be less than or equal to {hard_name}")
        return self


class BudgetPolicyRateLimit(StrictAITEAMOSModel):
    requestsPerMinute: int | None = Field(default=None, ge=1)


class BudgetPolicyFallback(StrictAITEAMOSModel):
    allowModelFallback: bool = False
    maxFallbacksPerRun: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def require_fallback_permission_for_fallback_count(self) -> "BudgetPolicyFallback":
        if self.maxFallbacksPerRun and not self.allowModelFallback:
            raise ValueError("maxFallbacksPerRun requires allowModelFallback")
        return self


class BudgetPolicyEnforcement(StrictAITEAMOSModel):
    onSoftLimit: Literal["warn", "stop-run"] = "warn"
    onHardLimit: Literal["stop-run"] = "stop-run"


class BudgetPolicySpec(StrictAITEAMOSModel):
    scope: BudgetPolicyScope
    limits: BudgetPolicyLimits
    rateLimit: BudgetPolicyRateLimit = Field(default_factory=BudgetPolicyRateLimit)
    fallback: BudgetPolicyFallback = Field(default_factory=BudgetPolicyFallback)
    enforcement: BudgetPolicyEnforcement = Field(default_factory=BudgetPolicyEnforcement)


class BudgetPolicy(Manifest):
    kind: Literal["BudgetPolicy"]
    spec: BudgetPolicySpec


class ContextManifestFreshnessSignals(StrictAITEAMOSModel):
    generatedAt: str | None = None
    recentRunCount: int = Field(default=0, ge=0)
    approvedMemoryCount: int = Field(default=0, ge=0)
    excludedMemoryCount: int = Field(default=0, ge=0)


class ContextManifestBudgetPolicy(StrictAITEAMOSModel):
    id: str
    scope: BudgetPolicyScope
    limits: BudgetPolicyLimits
    rateLimit: BudgetPolicyRateLimit = Field(default_factory=BudgetPolicyRateLimit)
    fallback: BudgetPolicyFallback = Field(default_factory=BudgetPolicyFallback)
    enforcement: BudgetPolicyEnforcement = Field(default_factory=BudgetPolicyEnforcement)
    applies: bool = False
    specificity: int = Field(default=0, ge=0)


class ContextManifestBudget(StrictAITEAMOSModel):
    modelProfile: str | None = None
    applicablePolicy: str | None = None
    policies: list[ContextManifestBudgetPolicy] = Field(default_factory=list)


class ContextSourceDecision(StrictAITEAMOSModel):
    sourceType: str
    sourceRef: str | None = None
    outcome: Literal["included", "excluded"]
    reason: str
    category: str | None = None
    repo: str | None = None
    path: str | None = None
    dedupeKey: str | None = None
    budgetBucket: str | None = None
    rank: int | None = Field(default=None, ge=0)
    score: int | None = Field(default=None, ge=0)
    aclRead: list[str] = Field(default_factory=list)
    lifecycle: str | None = None
    freshness: str | None = None
    confidence: float | None = None
    sensitivity: str | None = None
    charsIncluded: int | None = Field(default=None, ge=0)
    charsLimit: int | None = Field(default=None, ge=0)
    truncated: bool | None = None
    snippetPreview: str | None = None
    lineStart: int | None = Field(default=None, ge=1)
    lineEnd: int | None = Field(default=None, ge=1)


class ContextManifestSpec(StrictAITEAMOSModel):
    generatedAt: str | None = None
    task: str
    member: str
    memberKind: Literal["human", "digital", "hybrid", "service"] | None = None
    assignment: str | None = None
    project: str | None = None
    modelProfile: str | None = None
    branch: str | None = None
    memoryBindings: list[str] = Field(default_factory=list)
    memoryGrants: list[str] = Field(default_factory=list)
    handoffs: list[str] = Field(default_factory=list)
    sourcePriority: list[str] = Field(default_factory=list)
    sources: dict[str, list[Any]] = Field(default_factory=dict)
    sourceDecisions: list[ContextSourceDecision] = Field(default_factory=list)
    sourceCounts: dict[str, int] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)
    freshnessSignals: ContextManifestFreshnessSignals = Field(default_factory=ContextManifestFreshnessSignals)
    budget: ContextManifestBudget = Field(default_factory=ContextManifestBudget)
    limits: dict[str, Any] = Field(default_factory=dict)


class ContextManifest(Manifest):
    kind: Literal["ContextManifest"]
    spec: ContextManifestSpec


class GateCheck(StrictAITEAMOSModel):
    name: str
    status: str
    message: str


class EvalSuiteRequirementStatus(StrictAITEAMOSModel):
    evalSuite: str
    paths: list[str] = Field(default_factory=list)
    matchedPaths: list[str] = Field(default_factory=list)
    threshold: float | None = None
    lastResultId: str | None = None
    passRate: float | None = None
    status: Literal["pass", "fail", "skip"]
    message: str


class RunReviewGateRecord(StrictAITEAMOSModel):
    run: str
    project: str | None = None
    task: str | None = None
    member: str | None = None
    assignment: str | None = None
    memberKind: Literal["human", "digital", "hybrid", "service"] | None = None
    readyForHumanReview: bool
    status: str
    summary: str
    blockers: list[str]
    warnings: list[str]
    checks: list[GateCheck]
    evalSuiteRequirements: list[EvalSuiteRequirementStatus] = Field(default_factory=list)


class RunReviewTargetCheckRecord(StrictAITEAMOSModel):
    run: str
    generatedAt: str
    source: str
    status: str
    summary: str
    target: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list)


class RunCloseoutGateRecord(StrictAITEAMOSModel):
    run: str
    readyForCloseout: bool
    status: str
    summary: str
    latestReview: str | None = None
    blockers: list[str]
    warnings: list[str]
    checks: list[GateCheck]
    permissionDecisions: list[dict[str, Any]] = Field(default_factory=list)


class RunSourceIntegrationGateRecord(StrictAITEAMOSModel):
    run: str
    readyForSourceIntegration: bool
    status: str
    summary: str
    repository: str | None = None
    sourceBranch: str | None = None
    workerBranch: str | None = None
    changedPaths: list[str] = Field(default_factory=list)
    blockers: list[str]
    warnings: list[str]
    checks: list[GateCheck]
    permissionDecisions: list[dict[str, Any]] = Field(default_factory=list)


class RunSourceIntegrationRemediationRecord(StrictAITEAMOSModel):
    run: str
    status: str
    summary: str
    strategy: str
    repository: str | None = None
    sourceBranch: str | None = None
    workerBranch: str | None = None
    remediationBranch: str | None = None
    remediationWorktree: str | None = None
    mergeStatus: str | None = None
    baseSha: str | None = None
    sourceSha: str | None = None
    workerSha: str | None = None
    conflictFiles: list[str] = Field(default_factory=list)
    conflictResolution: dict[str, Any] | None = None
    changedPaths: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    remediationReviewTarget: dict[str, Any] | None = None
    gate: dict[str, Any] = Field(default_factory=dict)
    permissionDecisions: list[dict[str, Any]] = Field(default_factory=list)
    decisionAudit: list[dict[str, Any]] = Field(default_factory=list)
    requestedAt: str | None = None
    requestedByMember: str | None = None
    requestedByMemberKind: Literal["human", "digital", "hybrid", "service"] | None = None


class RunProviderSourceIntegrationRecord(StrictAITEAMOSModel):
    run: str
    status: str
    summary: str
    strategy: str
    provider: str | None = None
    reviewTarget: dict[str, Any] | None = None
    providerChecks: dict[str, Any] | None = None
    changedPaths: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    gate: dict[str, Any] = Field(default_factory=dict)
    permissionDecisions: list[dict[str, Any]] = Field(default_factory=list)
    decisionAudit: list[dict[str, Any]] = Field(default_factory=list)
    requestedAt: str | None = None
    requestedByMember: str | None = None
    requestedByMemberKind: Literal["human", "digital", "hybrid", "service"] | None = None


class RunProviderSourceIntegrationExecutionRecord(StrictAITEAMOSModel):
    run: str
    status: str
    summary: str
    strategy: str
    provider: str | None = None
    dryRun: bool = True
    reviewTarget: dict[str, Any] | None = None
    providerChecks: dict[str, Any] | None = None
    changedPaths: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    gate: dict[str, Any] = Field(default_factory=dict)
    permissionDecisions: list[dict[str, Any]] = Field(default_factory=list)
    decisionAudit: list[dict[str, Any]] = Field(default_factory=list)
    providerResult: dict[str, Any] | None = None
    error: str | None = None
    attemptedAt: str | None = None
    attemptedByMember: str | None = None
    attemptedByMemberKind: Literal["human", "digital", "hybrid", "service"] | None = None


class ContextCapsuleInventoryRecord(StrictAITEAMOSModel):
    run: str
    task: str
    member: str
    assignment: str | None = None
    modelProfile: str | None = None
    capsulePath: str | None = None
    manifestPath: str | None = None
    generatedAt: str | None = None
    sourcePriority: list[str]
    sourceCounts: dict[str, int]
    exclusionCount: int = Field(ge=0)
    freshnessSignals: ContextManifestFreshnessSignals
    budget: ContextManifestBudget
    applicableBudgetPolicy: str | None = None
    capsuleSha256: str | None = None
    capsuleSizeBytes: int | None = Field(default=None, ge=0)
    contextManifest: ContextManifest | None = None
    contentIncluded: bool


class ModelCostRow(StrictAITEAMOSModel):
    attempts: int = Field(ge=0)
    calls: int = Field(ge=0)
    failures: int = Field(ge=0)
    fallbacks: int = Field(ge=0)
    inputTokens: int = Field(ge=0)
    outputTokens: int = Field(ge=0)
    totalTokens: int = Field(ge=0)
    costUsd: float = Field(ge=0)
    latencyMsAvg: float | None = Field(default=None, ge=0)
    successRate: float | None = Field(default=None, ge=0, le=1)
    provider: str | None = None
    model: str | None = None
    run: str | None = None
    task: str | None = None
    member: str | None = None
    assignment: str | None = None
    profile: str | None = None
    lastEventTs: str | None = None


class ModelCostSummaryRecord(StrictAITEAMOSModel):
    source: str
    totals: ModelCostRow
    byModel: list[ModelCostRow]
    byRun: list[ModelCostRow]


class CostAlertCandidateRecord(StrictAITEAMOSModel):
    id: str
    source: Literal["workspace-event-ledger"] = "workspace-event-ledger"
    metricName: Literal["aiteamos_model_call_cost_usd_total"] = "aiteamos_model_call_cost_usd_total"
    project: str
    task: str | None = None
    run: str
    member: str | None = None
    assignment: str | None = None
    policy: str
    thresholdName: Literal["softUsdPerRun", "maxUsdPerRun"]
    thresholdKind: Literal["soft", "hard"]
    limitUsd: float = Field(ge=0)
    costUsd: float = Field(ge=0)
    usageRatio: float = Field(ge=0)
    targetMembers: list[str] = Field(default_factory=list)
    existingMessage: str | None = None
    suppressed: bool = False
    status: Literal["routable", "suppressed-by-open-message"] = "routable"
    severity: Literal["warning", "critical"] = "warning"
    dedupeKey: str


class CostAlertOverviewRecord(StrictAITEAMOSModel):
    source: Literal["workspace-event-ledger"] = "workspace-event-ledger"
    metricName: Literal["aiteamos_model_call_cost_usd_total"] = "aiteamos_model_call_cost_usd_total"
    summary: dict[str, Any] = Field(default_factory=dict)
    candidates: list[CostAlertCandidateRecord] = Field(default_factory=list)


class CostAlertRouteInput(StrictAITEAMOSModel):
    actorMember: str | None = None
    actor_member: str | None = None
    project: str | None = None
    member: str | None = None
    assignment: str | None = None
    task: str | None = None
    maxMessagesPerRun: int | None = Field(default=None, ge=1)
    max_messages_per_run: int | None = Field(default=None, ge=1)
    dryRun: bool = True
    dry_run: bool | None = None


class MemberGrowthPlanAction(StrictAITEAMOSModel):
    id: str
    actionType: Literal[
        "complete-assisted-ingest",
        "review-memory-proposals",
        "review-run-recovery",
        "close-collaboration-loops",
        "review-work-in-progress-load",
        "capture-reviewed-growth-note",
        "review-skill-fit",
    ]
    label: str
    rationale: str
    status: Literal["ready", "suggested", "blocked"] = "suggested"
    evidence: list[str] = Field(default_factory=list)
    relatedTasks: list[str] = Field(default_factory=list)
    relatedRuns: list[str] = Field(default_factory=list)
    relatedReviews: list[str] = Field(default_factory=list)
    relatedMemoryProposals: list[str] = Field(default_factory=list)
    relatedMessages: list[str] = Field(default_factory=list)
    relatedHandoffs: list[str] = Field(default_factory=list)
    relatedSkills: list[str] = Field(default_factory=list)


class MemberGrowthProjectionItem(StrictAITEAMOSModel):
    member: str
    memberKind: Literal["human", "digital", "hybrid", "service"]
    project: str | None = None
    assignments: list[str]
    activityCounts: dict[str, int]
    contributionCounts: dict[str, int]
    supportSignals: list[str]
    growthPlanActions: list[MemberGrowthPlanAction]
    growthRecords: list[MemberGrowthRecord]
    declaredPerformanceMetrics: list[MemberPerformanceMetric]
    evidence: list[str]
    warnings: list[str]


class MemberGrowthProjectionRecord(StrictAITEAMOSModel):
    generatedAt: str
    filters: dict[str, Any]
    summary: dict[str, int]
    nonPunitivePolicy: list[str]
    items: list[MemberGrowthProjectionItem]


class MemberGrowthSupportSignals(MemberGrowthProjectionRecord):
    pass


class TaskExecutionQueueItem(StrictAITEAMOSModel):
    id: str
    queueStatus: str
    title: str
    taskStatus: str
    assignedMember: str | None = None
    assignment: str | None = None
    memberModelProfile: str | None = None
    latestRun: str | None = None
    latestRunStatus: str | None = None
    runCount: int = Field(ge=0)
    blockers: list[str]
    actions: list[str]


class TaskExecutionQueueRecord(StrictAITEAMOSModel):
    summary: dict[str, int]
    items: list[TaskExecutionQueueItem]


class WorkspaceActionItem(StrictAITEAMOSModel):
    id: str
    lane: str
    priority: int
    targetType: str
    targetId: str
    task: str | None = None
    run: str | None = None
    member: str | None = None
    assignment: str | None = None
    status: str | None = None
    action: str
    title: str
    reason: str
    blockers: list[str]
    warnings: list[str]


class WorkspaceActionBoardRecord(StrictAITEAMOSModel):
    summary: dict[str, int]
    items: list[WorkspaceActionItem]


class WorkspaceCatalogOption(StrictAITEAMOSModel):
    id: str
    label: str
    optionType: Literal["current", "example"]
    workspaceRef: str
    workspaceName: str | None = None
    workspaceMode: str | None = None
    protocolVersion: str | None = None
    project: str | None = None
    projectTitle: str | None = None
    relativePath: str | None = None
    servedByCurrentApi: bool = False
    safeForPublicDemo: bool = False
    launchCommand: str | None = None
    validateCommand: str | None = None
    dashboardCommand: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    healthSummary: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class WorkspaceCatalogSpec(StrictAITEAMOSModel):
    currentWorkspace: str
    generatedAt: str
    options: list[WorkspaceCatalogOption]


class WorkspaceCatalogRecord(StrictAITEAMOSModel):
    id: Literal["workspace-catalog"] = "workspace-catalog"
    kind: Literal["WorkspaceCatalog"] = "WorkspaceCatalog"
    spec: WorkspaceCatalogSpec


class RetrospectiveSuggestionSource(StrictAITEAMOSModel):
    sourceType: Literal["run", "task", "message", "handoff"]
    id: str
    project: str | None = None
    task: str | None = None
    run: str | None = None
    member: str | None = None
    status: str | None = None
    summary: str


class RetrospectiveSuggestion(StrictAITEAMOSModel):
    id: str
    project: str
    facilitatorMember: str | None = None
    participants: list[str]
    sourceRuns: list[str]
    sourceTasks: list[str]
    sourceMessages: list[str]
    sourceHandoffs: list[str]
    summary: str
    lessons: list[str]
    actionItems: list[str]
    evidence: list[str]
    sources: list[RetrospectiveSuggestionSource]
    score: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    proposedRetrospective: dict[str, Any] = Field(default_factory=dict)


class RetrospectiveSuggestionRecord(StrictAITEAMOSModel):
    generatedAt: str
    filters: dict[str, Any]
    summary: dict[str, int]
    candidates: list[RetrospectiveSuggestion]


class WorkspaceHealth(StrictAITEAMOSModel):
    schemaVersion: Literal["WorkspaceHealthV2"] = "WorkspaceHealthV2"
    issues: list[dict[str, Any]]
    summary: dict[str, int]
    lastIndexDuration: float | None = None
    manifestLoadFailures: list[dict[str, Any]] = Field(default_factory=list)
    vectorChunkCount: int = Field(default=0, ge=0)
    schemaVersionMismatch: bool = False
    staleWorkerLeases: list[dict[str, Any]] = Field(default_factory=list)


class ConnectorEscalationCandidate(StrictAITEAMOSModel):
    id: str
    kind: Literal["ConnectorFailureEscalationCandidate"]
    spec: dict[str, Any]


class ConnectorRemediationSuggestion(StrictAITEAMOSModel):
    id: str
    kind: Literal["ConnectorRemediationSuggestion"]
    spec: dict[str, Any]


class ManagerInputBundle(StrictAITEAMOSModel):
    generatedAt: str
    manager: str
    project: str
    assignment: str | None = None
    filters: dict[str, Any]
    workspaceHealth: WorkspaceHealth
    reviewGates: list[RunReviewGateRecord]
    connectorEscalationCandidates: list[ConnectorEscalationCandidate]
    connectorEscalationSummary: dict[str, int]
    connectorRemediationSuggestions: list[ConnectorRemediationSuggestion]
    connectorRemediationSummary: dict[str, int]
    retrospectiveSuggestions: list[RetrospectiveSuggestionRecord]
    memberGrowthSupportSignals: MemberGrowthSupportSignals
    managerEvaluation: dict[str, Any] = Field(default_factory=dict)
    readOnly: bool = True
    sourceRefs: list[str]


class KnowledgeHealthSummary(StrictAITEAMOSModel):
    memoryEntries: int = Field(default=0, ge=0)
    approvedMemory: int = Field(ge=0)
    pendingProposals: int = Field(ge=0)
    activeBindings: int = Field(default=0, ge=0)
    activeGrants: int = Field(default=0, ge=0)
    staleMemory: int = Field(default=0, ge=0)
    conflictedMemory: int = Field(default=0, ge=0)
    sensitiveMemory: int = Field(default=0, ge=0)
    orphanedBindings: int = Field(default=0, ge=0)
    orphanedGrants: int = Field(default=0, ge=0)
    expiredGrants: int = Field(default=0, ge=0)
    issues: int = Field(ge=0)
    warnings: int = Field(ge=0)
    errors: int = Field(ge=0)


class KnowledgeHealthIssue(StrictAITEAMOSModel):
    severity: str
    kind: str
    ref: str
    message: str
    action: str


class KnowledgeHealthRecord(StrictAITEAMOSModel):
    generatedAt: str
    summary: KnowledgeHealthSummary
    issues: list[KnowledgeHealthIssue]


class KnowledgeHealthRemediationInput(StrictAITEAMOSModel):
    issueKind: str
    ref: str
    action: Literal["verify-entry", "mark-entry-stale", "archive-binding", "revoke-grant"]
    actorMember: str
    reason: str
    dryRun: bool = True


class KnowledgeHealthRemediationRecord(StrictAITEAMOSModel):
    generatedAt: str
    issueKind: str
    ref: str
    action: Literal["verify-entry", "mark-entry-stale", "archive-binding", "revoke-grant"]
    actorMember: str
    dryRun: bool
    applied: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    issue: KnowledgeHealthIssue | None = None
    decisionAudit: list[DecisionAuditRecord] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


KIND_TO_MODEL: dict[str, type[Manifest]] = {
    "Workspace": Workspace,
    "Project": Project,
    "Repository": Repository,
    "RoleTemplate": RoleTemplate,
    "TeamMember": TeamMember,
    "ProductUser": ProductUser,
    "DigitalExecutionProfile": DigitalExecutionProfile,
    "HumanCollaborationProfile": HumanCollaborationProfile,
    "HybridExecutionProfile": HybridExecutionProfile,
    "ServiceAccountProfile": ServiceAccountProfile,
    "Team": Team,
    "Assignment": Assignment,
    "MemberActivity": MemberActivity,
    "GitActivity": GitActivity,
    "GitActivityImportReceipt": GitActivityImportReceipt,
    "GitActivityCorrelationReview": GitActivityCorrelationReview,
    "Task": Task,
    "TaskPlan": TaskPlan,
    "Run": Run,
    "Review": Review,
    "MemoryStore": MemoryStore,
    "MemoryEntry": MemoryEntry,
    "MemoryVersion": MemoryVersion,
    "MemoryBinding": MemoryBinding,
    "MemoryGrant": MemoryGrant,
    "MemoryProposal": MemoryProposal,
    "LearningExtraction": LearningExtraction,
    "MemberMessage": MemberMessage,
    "Handoff": Handoff,
    "TeamRetrospective": TeamRetrospective,
    "Automation": Automation,
    "AutomationRun": AutomationRun,
    "AutomationTriggerEvent": AutomationTriggerEvent,
    "AutomationProviderDelivery": AutomationProviderDelivery,
    "AutomationSchedulerLease": AutomationSchedulerLease,
    "AutomationApproval": AutomationApproval,
    "ApprovalWorkflow": ApprovalWorkflow,
    "PermissionPolicy": PermissionPolicy,
    "PermissionRequest": PermissionRequest,
    "PermissionGrant": PermissionGrant,
    "Skill": Skill,
    "Connector": Connector,
    "ConnectorHealthCheck": ConnectorHealthCheck,
    "EvalSuite": EvalSuite,
    "EvalResult": EvalResult,
    "Artifact": Artifact,
    "ArtifactStore": ArtifactStore,
    "ModelProfile": ModelProfile,
    "BudgetPolicy": BudgetPolicy,
    "ContextManifest": ContextManifest,
}


API_SCHEMA_MODELS: dict[str, type[AITEAMOSModel]] = {
    "AutomationCreateInput": AutomationCreateInput,
    "AutomationRunActionInput": AutomationRunActionInput,
    "AutomationTriggerInput": AutomationTriggerInput,
    "ApprovalWorkflow": ApprovalWorkflow,
    "ApprovalWorkflowEscalation": ApprovalWorkflowEscalation,
    "ApprovalWorkflowSLA": ApprovalWorkflowSLA,
    "ApprovalWorkflowSpec": ApprovalWorkflowSpec,
    "ApprovalWorkflowStage": ApprovalWorkflowStage,
    "ConnectorEscalationCandidate": ConnectorEscalationCandidate,
    "ConnectorRemediationSuggestion": ConnectorRemediationSuggestion,
    "CostAlertCandidateRecord": CostAlertCandidateRecord,
    "CostAlertOverviewRecord": CostAlertOverviewRecord,
    "CostAlertRouteInput": CostAlertRouteInput,
    "ContextCapsuleInventoryRecord": ContextCapsuleInventoryRecord,
    "DecisionAuditRecord": DecisionAuditRecord,
    "EvalCase": EvalCase,
    "EvalCaseResult": EvalCaseResult,
    "EvalJudge": EvalJudge,
    "EvalResult": EvalResult,
    "EvalResultSpec": EvalResultSpec,
    "EvalSuitePolicy": EvalSuitePolicy,
    "EvalSuiteRequirement": EvalSuiteRequirement,
    "EvalSuiteRequirementStatus": EvalSuiteRequirementStatus,
    "GateCheck": GateCheck,
    "GitActivityCorrelationGroup": GitActivityCorrelationGroup,
    "GitActivityCorrelationPreviewRecord": GitActivityCorrelationPreviewRecord,
    "GitActivityCorrelationSignal": GitActivityCorrelationSignal,
    "KnowledgeHealthIssue": KnowledgeHealthIssue,
    "KnowledgeHealthRecord": KnowledgeHealthRecord,
    "KnowledgeHealthRemediationInput": KnowledgeHealthRemediationInput,
    "KnowledgeHealthRemediationRecord": KnowledgeHealthRemediationRecord,
    "KnowledgeHealthSummary": KnowledgeHealthSummary,
    "LearningExtraction": LearningExtraction,
    "LearningExtractionProposal": LearningExtractionProposal,
    "LearningExtractionSourceContext": LearningExtractionSourceContext,
    "LearningExtractionSpec": LearningExtractionSpec,
    "MemoryEvalEvidenceRef": MemoryEvalEvidenceRef,
    "MemoryEntryCreateInput": MemoryEntryCreateInput,
    "MemoryStoreCreateInput": MemoryStoreCreateInput,
    "MemberDeleteRequestInput": MemberDeleteRequestInput,
    "MemberDeleteRequestRecord": MemberDeleteRequestRecord,
    "MemberDeleteRequestReference": MemberDeleteRequestReference,
    "MemberGrowthRecordInput": MemberGrowthRecordInput,
    "MemberGrowthPlanAction": MemberGrowthPlanAction,
    "MemberGrowthProjectionItem": MemberGrowthProjectionItem,
    "MemberGrowthProjectionRecord": MemberGrowthProjectionRecord,
    "MemberGrowthSupportSignals": MemberGrowthSupportSignals,
    "ManagerInputBundle": ManagerInputBundle,
    "ModelCostRow": ModelCostRow,
    "ModelCostSummaryRecord": ModelCostSummaryRecord,
    "PermissionAction": PermissionAction,
    "RiskAssessment": RiskAssessment,
    "RiskSignal": RiskSignal,
    "RetrospectiveSuggestion": RetrospectiveSuggestion,
    "RetrospectiveSuggestionRecord": RetrospectiveSuggestionRecord,
    "RetrospectiveSuggestionSource": RetrospectiveSuggestionSource,
    "RunAssistanceBundleFile": RunAssistanceBundleFile,
    "RunAssistanceBundleRecord": RunAssistanceBundleRecord,
    "RunAssistancePackageCommand": RunAssistancePackageCommand,
    "RunAssistancePackageContract": RunAssistancePackageContract,
    "RunAssistancePackageRecord": RunAssistancePackageRecord,
    "RunAssistedIngestInput": RunAssistedIngestInput,
    "RunAssistedMemoryProposalInput": RunAssistedMemoryProposalInput,
    "RunCloseoutInput": RunCloseoutInput,
    "RunCloseoutGateRecord": RunCloseoutGateRecord,
    "RunReviewFindingInput": RunReviewFindingInput,
    "RunReviewGateRecord": RunReviewGateRecord,
    "RunReviewInput": RunReviewInput,
    "RunReviewTargetCheckRecord": RunReviewTargetCheckRecord,
    "RunEvent": RunEvent,
    "RunProviderSourceIntegrationExecuteInput": RunProviderSourceIntegrationExecuteInput,
    "RunProviderSourceIntegrationExecutionRecord": RunProviderSourceIntegrationExecutionRecord,
    "RunProviderSourceIntegrationInput": RunProviderSourceIntegrationInput,
    "RunProviderSourceIntegrationRecord": RunProviderSourceIntegrationRecord,
    "RunSourceIntegrationInput": RunSourceIntegrationInput,
    "RunSourceIntegrationGateRecord": RunSourceIntegrationGateRecord,
    "RunSourceIntegrationRemediationInput": RunSourceIntegrationRemediationInput,
    "RunSourceIntegrationRemediationRecord": RunSourceIntegrationRemediationRecord,
    "WorkspaceHealth": WorkspaceHealth,
    "ProductUserArchiveInput": ProductUserArchiveInput,
    "ProductUserCreateInput": ProductUserCreateInput,
    "ProductUserManagementAudit": ProductUserManagementAudit,
    "ProductUserUpdateInput": ProductUserUpdateInput,
    "SessionLoginInput": SessionLoginInput,
    "SessionLoginRecord": SessionLoginRecord,
    "SessionProjectionRecord": SessionProjectionRecord,
    "SkillAttachMemberInput": SkillAttachMemberInput,
    "SkillArchiveInput": SkillArchiveInput,
    "SkillCreateInput": SkillCreateInput,
    "SkillProjectionRecord": SkillProjectionRecord,
    "SkillUpdateInput": SkillUpdateInput,
    "TaskExecutionQueueItem": TaskExecutionQueueItem,
    "TaskExecutionQueueRecord": TaskExecutionQueueRecord,
    "WorkspaceActionBoardRecord": WorkspaceActionBoardRecord,
    "WorkspaceActionItem": WorkspaceActionItem,
    "WorkspaceCatalogOption": WorkspaceCatalogOption,
    "WorkspaceCatalogRecord": WorkspaceCatalogRecord,
    "WorkspaceCatalogSpec": WorkspaceCatalogSpec,
}


def manifest_model_for_kind(kind: str) -> type[Manifest]:
    return KIND_TO_MODEL.get(kind, Manifest)


def parse_manifest(data: dict[str, Any]) -> Manifest:
    kind = data.get("kind")
    if not kind:
        raise ValueError("manifest is missing kind")
    model = manifest_model_for_kind(kind)
    return model.model_validate(data)


def timestamp_task_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"TASK-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_run_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"RUN-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_memory_proposal_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"MP-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_review_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"REVIEW-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_automation_run_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"ARUN-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_automation_event_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"AEVENT-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_automation_approval_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"AAPPROVAL-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_git_activity_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"GIT-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_git_activity_import_receipt_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"GITIMP-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"


def timestamp_git_activity_correlation_review_id(now: datetime | None = None) -> str:
    value = now or datetime.now().astimezone()
    return f"GITCORR-{value:%Y%m%dT%H%M%S}{value.microsecond // 1000:03d}"
