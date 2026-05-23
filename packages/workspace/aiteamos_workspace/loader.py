from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiteamos_schema import (
    Artifact,
    ArtifactStore,
    Assignment,
    Automation,
    AutomationApproval,
    ApprovalWorkflow,
    AutomationProviderDelivery,
    AutomationRun,
    AutomationSchedulerLease,
    AutomationTriggerEvent,
    BudgetPolicy,
    Connector,
    ConnectorHealthCheck,
    DigitalExecutionProfile,
    EvalResult,
    EvalSuite,
    GitActivity,
    GitActivityCorrelationReview,
    GitActivityImportReceipt,
    Handoff,
    HumanCollaborationProfile,
    HybridExecutionProfile,
    LearningExtraction,
    Manifest,
    MemberActivity,
    MemberMessage,
    MemoryBinding,
    MemoryEntry,
    MemoryGrant,
    MemoryProposal,
    MemoryStore,
    MemoryVersion,
    ModelProfile,
    PermissionGrant,
    PermissionPolicy,
    PermissionRequest,
    ProductUser,
    Project,
    Repository,
    Review,
    RoleTemplate,
    Run,
    RunEvent,
    ServiceAccountProfile,
    Skill,
    Task,
    TaskPlan,
    Team,
    TeamMember,
    TeamRetrospective,
    Workspace,
    parse_manifest,
)

from .io import read_jsonl, read_text_if_exists, read_yaml
from .connector_fixtures import connector_adapter_fixture_issues
from .remote import is_remote_workspace_ref, materialize_remote_workspace


@dataclass
class WorkspaceIndex:
    workspace_root: Path
    workspace: Workspace
    project: Project
    repositories: dict[str, Repository] = field(default_factory=dict)
    role_templates: dict[str, RoleTemplate] = field(default_factory=dict)
    members: dict[str, TeamMember] = field(default_factory=dict)
    product_users: dict[str, ProductUser] = field(default_factory=dict)
    teams: dict[str, Team] = field(default_factory=dict)
    assignments: dict[str, Assignment] = field(default_factory=dict)
    digital_execution_profiles: dict[str, DigitalExecutionProfile] = field(default_factory=dict)
    human_collaboration_profiles: dict[str, HumanCollaborationProfile] = field(default_factory=dict)
    hybrid_execution_profiles: dict[str, HybridExecutionProfile] = field(default_factory=dict)
    service_account_profiles: dict[str, ServiceAccountProfile] = field(default_factory=dict)
    tasks: dict[str, Task] = field(default_factory=dict)
    task_plans: dict[str, TaskPlan] = field(default_factory=dict)
    runs: dict[str, Run] = field(default_factory=dict)
    reviews: dict[str, Review] = field(default_factory=dict)
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    artifact_stores: dict[str, ArtifactStore] = field(default_factory=dict)
    eval_suites: dict[str, EvalSuite] = field(default_factory=dict)
    eval_results: dict[str, EvalResult] = field(default_factory=dict)
    memory_stores: dict[str, MemoryStore] = field(default_factory=dict)
    memory_entries: dict[str, MemoryEntry] = field(default_factory=dict)
    memory_versions: dict[str, MemoryVersion] = field(default_factory=dict)
    memory_bindings: dict[str, MemoryBinding] = field(default_factory=dict)
    memory_grants: dict[str, MemoryGrant] = field(default_factory=dict)
    memory_proposals: dict[str, MemoryProposal] = field(default_factory=dict)
    learning_extractions: dict[str, LearningExtraction] = field(default_factory=dict)
    member_messages: dict[str, MemberMessage] = field(default_factory=dict)
    handoffs: dict[str, Handoff] = field(default_factory=dict)
    team_retrospectives: dict[str, TeamRetrospective] = field(default_factory=dict)
    automations: dict[str, Automation] = field(default_factory=dict)
    automation_runs: dict[str, AutomationRun] = field(default_factory=dict)
    automation_trigger_events: dict[str, AutomationTriggerEvent] = field(default_factory=dict)
    automation_provider_deliveries: dict[str, AutomationProviderDelivery] = field(default_factory=dict)
    automation_scheduler_leases: dict[str, AutomationSchedulerLease] = field(default_factory=dict)
    automation_approvals: dict[str, AutomationApproval] = field(default_factory=dict)
    approval_workflows: dict[str, ApprovalWorkflow] = field(default_factory=dict)
    permission_policies: dict[str, PermissionPolicy] = field(default_factory=dict)
    permission_requests: dict[str, PermissionRequest] = field(default_factory=dict)
    permission_grants: dict[str, PermissionGrant] = field(default_factory=dict)
    skills: dict[str, Skill] = field(default_factory=dict)
    connectors: dict[str, Connector] = field(default_factory=dict)
    connector_health_checks: dict[str, ConnectorHealthCheck] = field(default_factory=dict)
    member_activities: dict[str, MemberActivity] = field(default_factory=dict)
    git_activities: dict[str, GitActivity] = field(default_factory=dict)
    git_activity_import_receipts: dict[str, GitActivityImportReceipt] = field(default_factory=dict)
    git_activity_correlation_reviews: dict[str, GitActivityCorrelationReview] = field(default_factory=dict)
    model_profiles: dict[str, ModelProfile] = field(default_factory=dict)
    budget_policies: dict[str, BudgetPolicy] = field(default_factory=dict)
    run_events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    run_journals: dict[str, str] = field(default_factory=dict)
    run_context_capsules: dict[str, str] = field(default_factory=dict)
    run_context_manifests: dict[str, dict[str, Any]] = field(default_factory=dict)
    task_markdown: dict[str, str] = field(default_factory=dict)
    review_markdown: dict[str, str] = field(default_factory=dict)
    health: list[dict[str, str]] = field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "workspace": manifest_to_record(self.workspace),
            "project": manifest_to_record(self.project),
            "counts": {
                "repositories": len(self.repositories),
                "roleTemplates": len(self.role_templates),
                "members": len(self.members),
                "productUsers": len(self.product_users),
                "teams": len(self.teams),
                "assignments": len(self.assignments),
                "tasks": len(self.tasks),
                "taskPlans": len(self.task_plans),
                "runs": len(self.runs),
                "reviews": len(self.reviews),
                "artifacts": len(self.artifacts),
                "artifactStores": len(self.artifact_stores),
                "evalSuites": len(self.eval_suites),
                "evalResults": len(self.eval_results),
                "memoryStores": len(self.memory_stores),
                "memoryEntries": len(self.memory_entries),
                "memoryVersions": len(self.memory_versions),
                "memoryBindings": len(self.memory_bindings),
                "memoryGrants": len(self.memory_grants),
                "memoryProposals": len(self.memory_proposals),
                "learningExtractions": len(self.learning_extractions),
                "teamRetrospectives": len(self.team_retrospectives),
                "automations": len(self.automations),
                "automationRuns": len(self.automation_runs),
                "automationTriggerEvents": len(self.automation_trigger_events),
                "automationProviderDeliveries": len(self.automation_provider_deliveries),
                "automationSchedulerLeases": len(self.automation_scheduler_leases),
                "automationApprovals": len(self.automation_approvals),
                "approvalWorkflows": len(self.approval_workflows),
                "permissions": len(self.permission_policies),
                "permissionRequests": len(self.permission_requests),
                "permissionGrants": len(self.permission_grants),
                "skills": len(self.skills),
                "connectors": len(self.connectors),
                "connectorHealthChecks": len(self.connector_health_checks),
                "memberActivities": len(self.member_activities),
                "gitActivities": len(self.git_activities),
                "gitActivityImportReceipts": len(self.git_activity_import_receipts),
                "gitActivityCorrelationReviews": len(self.git_activity_correlation_reviews),
                "modelProfiles": len(self.model_profiles),
                "budgetPolicies": len(self.budget_policies),
                "healthIssues": len(self.health),
            },
        }


def resolve_workspace_root(path: str | Path) -> Path:
    if is_remote_workspace_ref(path):
        return materialize_remote_workspace(path)
    candidate = Path(path).expanduser().resolve()
    if candidate.is_dir() and (candidate / "workspace.yaml").exists():
        return candidate
    if candidate.is_dir() and (candidate / ".aiteamos" / "workspace.yaml").exists():
        return candidate / ".aiteamos"
    raise FileNotFoundError(f"could not find .aiteamos workspace at {candidate}")


def load_workspace(path: str | Path = ".aiteamos") -> WorkspaceIndex:
    root = resolve_workspace_root(path)
    workspace = _load_required(root / "workspace.yaml", Workspace)
    project = _load_required(root / workspace.spec.projectRef, Project)

    index = WorkspaceIndex(workspace_root=root, workspace=workspace, project=project)
    index.repositories = _load_manifest_dir(root / "repositories", Repository)
    index.role_templates = _load_manifest_dir(root / "role_templates", RoleTemplate)
    index.members = _load_manifest_dir(root / "members", TeamMember)
    index.product_users = _load_manifest_dir(root / "product_users", ProductUser)
    index.teams = _load_manifest_dir(root / "teams", Team)
    index.assignments = _load_manifest_dir(root / "assignments", Assignment)
    index.digital_execution_profiles = _load_manifest_dir(root / "execution_profiles" / "digital", DigitalExecutionProfile)
    index.human_collaboration_profiles = _load_manifest_dir(root / "execution_profiles" / "human", HumanCollaborationProfile)
    index.hybrid_execution_profiles = _load_manifest_dir(root / "execution_profiles" / "hybrid", HybridExecutionProfile)
    index.service_account_profiles = _load_manifest_dir(root / "execution_profiles" / "service", ServiceAccountProfile)
    index.tasks = _load_manifest_dir(root / "tasks", Task)
    index.task_plans = _load_manifest_dir(root / "task_plans", TaskPlan)
    index.reviews = _load_manifest_dir(root / "reviews", Review)
    index.artifacts = _load_manifest_dir(root / "artifacts" / "manifests", Artifact)
    index.artifact_stores = _load_manifest_dir(root / "artifact_stores", ArtifactStore)
    index.eval_suites = _load_manifest_dir(root / "eval_suites", EvalSuite)
    index.eval_results = _load_manifest_dir(root / "eval_results", EvalResult)
    index.memory_stores = _load_manifest_tree(root / "memory" / "stores", MemoryStore)
    index.memory_entries = _load_manifest_tree(root / "memory" / "entries", MemoryEntry)
    index.memory_versions = _load_manifest_tree(root / "memory" / "versions", MemoryVersion)
    index.memory_bindings = _load_manifest_tree(root / "memory" / "bindings", MemoryBinding)
    index.memory_grants = _load_manifest_tree(root / "memory" / "grants", MemoryGrant)
    index.memory_proposals = _load_manifest_tree(root / "memory" / "proposals", MemoryProposal)
    index.learning_extractions = _load_manifest_dir(root / "learning_extractions", LearningExtraction)
    index.member_messages = _load_manifest_tree(root / "im" / "messages", MemberMessage)
    index.handoffs = _load_manifest_tree(root / "im" / "handoffs", Handoff)
    index.team_retrospectives = _load_manifest_tree(root / "im" / "retrospectives", TeamRetrospective)
    index.automations = _load_manifest_dir(root / "automations", Automation)
    index.automation_runs = _load_manifest_tree(root / "automations" / "runs", AutomationRun)
    index.automation_trigger_events = _load_manifest_tree(root / "automations" / "events", AutomationTriggerEvent)
    index.automation_provider_deliveries = _load_manifest_tree(root / "automations" / "provider_deliveries", AutomationProviderDelivery)
    index.automation_scheduler_leases = _load_manifest_tree(root / "automations" / "leases", AutomationSchedulerLease)
    index.approval_workflows = _load_manifest_dir(root / "approval_workflows", ApprovalWorkflow)
    index.automation_approvals = _automation_approval_views_from_workflows(index.approval_workflows)
    index.permission_policies = _load_manifest_dir(root / "permissions", PermissionPolicy)
    index.permission_requests = _permission_request_views_from_workflows(index.approval_workflows)
    index.permission_grants = _load_manifest_dir(root / "permission_grants", PermissionGrant)
    index.skills = _load_manifest_dir(root / "skills", Skill)
    index.connectors = _load_manifest_dir(root / "connectors", Connector)
    index.connector_health_checks = _load_manifest_tree(root / "connectors" / "health", ConnectorHealthCheck)
    index.member_activities = _load_manifest_tree(root / "activity", MemberActivity)
    index.git_activities = _load_manifest_tree(root / "git_activity", GitActivity)
    index.git_activity_import_receipts = _load_manifest_tree(root / "git_activity" / "imports", GitActivityImportReceipt)
    index.git_activity_correlation_reviews = _load_manifest_tree(root / "git_activity" / "correlations", GitActivityCorrelationReview)
    index.model_profiles = _load_manifest_dir(root / "model_profiles", ModelProfile)
    index.budget_policies = _load_manifest_dir(root / "budget_policies", BudgetPolicy)

    for task_id in index.tasks:
        text = read_text_if_exists(root / "tasks" / f"{task_id}.md")
        if text is not None:
            index.task_markdown[task_id] = text

    for review_id in index.reviews:
        text = read_text_if_exists(root / "reviews" / f"{review_id}.md")
        if text is not None:
            index.review_markdown[review_id] = text

    for run_path in sorted((root / "runs").glob("*/run.yaml")):
        run = _load_required(run_path, Run)
        index.runs[run.object_id] = run
        run_dir = run_path.parent
        if run.spec.eventLedger:
            index.run_events[run.object_id] = _load_run_events(run_dir / run.spec.eventLedger)
        if run.spec.journal:
            journal = read_text_if_exists(run_dir / run.spec.journal)
            if journal is not None:
                index.run_journals[run.object_id] = journal
        if run.spec.contextCapsule:
            capsule = read_text_if_exists(run_dir / run.spec.contextCapsule)
            if capsule is not None:
                index.run_context_capsules[run.object_id] = capsule
        if run.spec.contextManifest:
            manifest_path = run_dir / run.spec.contextManifest
            if manifest_path.exists():
                index.run_context_manifests[run.object_id] = read_yaml(manifest_path)

    index.health = validate_workspace(index)
    return index


def _load_run_events(path: Path) -> list[dict[str, Any]]:
    return [
        RunEvent.model_validate(event).model_dump(mode="json", exclude_none=True)
        for event in read_jsonl(path)
    ]


def validate_workspace(index: WorkspaceIndex) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def issue(kind: str, severity: str, message: str, ref: str | None = None) -> None:
        payload = {"kind": kind, "severity": severity, "message": message}
        if ref:
            payload["ref"] = ref
        issues.append(payload)

    project_name = index.project.object_id

    if (index.workspace_root / "roles").exists():
        issue(
            "workspace_layout",
            "warning",
            ".aiteamos/roles/ directory is not loaded; use role_templates/ for reusable role vocabulary and assignments/ for project responsibility bindings",
            "roles/",
        )

    for fixture_issue in connector_adapter_fixture_issues():
        issue(
            fixture_issue["kind"],
            fixture_issue["severity"],
            fixture_issue["message"],
            fixture_issue.get("ref"),
        )

    for repo_ref in index.project.spec.repositories:
        if not (index.workspace_root / repo_ref).exists():
            issue("repository", "error", f"project references missing repository manifest {repo_ref}", repo_ref)

    for assignment_id, assignment in index.assignments.items():
        if assignment.spec.member not in index.members:
            issue("assignment", "error", f"assignment {assignment_id} references missing member {assignment.spec.member}", assignment_id)
        if assignment.spec.project != project_name:
            issue("assignment", "error", f"assignment {assignment_id} belongs to project {assignment.spec.project}, not {project_name}", assignment_id)
        if assignment.spec.roleTemplate and assignment.spec.roleTemplate not in index.role_templates:
            issue("assignment", "warning", f"assignment {assignment_id} references missing role template {assignment.spec.roleTemplate}", assignment_id)
        for repo in assignment.spec.repositories:
            if repo not in index.repositories:
                issue("assignment", "warning", f"assignment {assignment_id} references unknown repository {repo}", assignment_id)
        for requirement in assignment.spec.evalSuiteRequirements:
            suite = index.eval_suites.get(requirement.evalSuite)
            if suite is None:
                issue("assignment", "error", f"assignment {assignment_id} references missing EvalSuite {requirement.evalSuite}", assignment_id)
                continue
            if suite.spec.project != assignment.spec.project:
                issue("assignment", "error", f"assignment {assignment_id} requires EvalSuite {requirement.evalSuite} from project {suite.spec.project}", assignment_id)
            if suite.spec.assignments and assignment_id not in suite.spec.assignments:
                issue("assignment", "warning", f"assignment {assignment_id} requires EvalSuite {requirement.evalSuite} that does not list this assignment", assignment_id)
            for pattern in requirement.paths:
                if pattern.startswith("/") or ".." in pattern.split("/"):
                    issue("assignment", "error", f"assignment {assignment_id} has unsafe EvalSuite requirement path pattern {pattern}", assignment_id)

    for product_user_id, product_user in index.product_users.items():
        if product_user.spec.member and product_user.spec.member not in index.members:
            issue("product_user", "error", f"product user {product_user_id} references missing member {product_user.spec.member}", product_user_id)
        if "admin" in product_user.spec.roles and not product_user.spec.member:
            issue("product_user", "warning", f"admin product user {product_user_id} should map to a TeamMember for audit attribution", product_user_id)

    for member_id, member in index.members.items():
        binding = member.spec.userBinding
        if not binding:
            continue
        product_user = index.product_users.get(binding.productUser)
        if product_user is None:
            issue("member", "error", f"member {member_id} userBinding references missing ProductUser {binding.productUser}", member_id)
            continue
        if product_user.spec.member != member_id:
            issue("member", "error", f"member {member_id} userBinding points to ProductUser {binding.productUser} bound to {product_user.spec.member}", member_id)
        if product_user.spec.status != binding.status:
            issue("member", "warning", f"member {member_id} userBinding status {binding.status} differs from ProductUser {binding.productUser} status {product_user.spec.status}", member_id)

    for profile_id, profile in {
        **index.digital_execution_profiles,
        **index.human_collaboration_profiles,
        **index.hybrid_execution_profiles,
        **index.service_account_profiles,
    }.items():
        if profile.spec.member not in index.members:
            issue("member_profile", "error", f"profile {profile_id} references missing member {profile.spec.member}", profile_id)

    for task_id, task in index.tasks.items():
        if task.spec.project != project_name:
            issue("task", "error", f"task {task_id} belongs to project {task.spec.project}, not {project_name}", task_id)
        if task.spec.assignedMember and task.spec.assignedMember not in index.members:
            issue("task", "error", f"task {task_id} references missing member {task.spec.assignedMember}", task_id)
        if task.spec.assignment and task.spec.assignment not in index.assignments:
            issue("task", "error", f"task {task_id} references missing assignment {task.spec.assignment}", task_id)

    for plan_id, plan in index.task_plans.items():
        if plan.spec.project and plan.spec.project != project_name:
            issue("task_plan", "warning", f"task plan {plan_id} targets project {plan.spec.project}, not {project_name}", plan_id)
        if plan.spec.createdByMember and plan.spec.createdByMember not in index.members:
            issue("task_plan", "warning", f"task plan {plan_id} references missing creator member {plan.spec.createdByMember}", plan_id)
        for subtask in plan.spec.subtasks:
            if subtask.assignedMember and subtask.assignedMember not in index.members:
                issue("task_plan", "warning", f"task plan {plan_id} subtask references missing member {subtask.assignedMember}", plan_id)
            if subtask.assignment and subtask.assignment not in index.assignments:
                issue("task_plan", "warning", f"task plan {plan_id} subtask references missing assignment {subtask.assignment}", plan_id)

    for run_id, run in index.runs.items():
        if run.spec.project != project_name:
            issue("run", "error", f"run {run_id} belongs to project {run.spec.project}, not {project_name}", run_id)
        if run.spec.task not in index.tasks:
            issue("run", "error", f"run {run_id} references missing task {run.spec.task}", run_id)
        if run.spec.member not in index.members:
            issue("run", "error", f"run {run_id} references missing member {run.spec.member}", run_id)
        if run.spec.assignment and run.spec.assignment not in index.assignments:
            issue("run", "error", f"run {run_id} references missing assignment {run.spec.assignment}", run_id)

    for review_id, review in index.reviews.items():
        if review.spec.task and review.spec.task not in index.tasks:
            issue("review", "error", f"review {review_id} references missing task {review.spec.task}", review_id)
        if review.spec.run and review.spec.run not in index.runs:
            issue("review", "warning", f"review {review_id} references missing run {review.spec.run}", review_id)
        if review.spec.reviewerMember and review.spec.reviewerMember not in index.members:
            issue("review", "warning", f"review {review_id} references missing reviewer member {review.spec.reviewerMember}", review_id)
        _validate_decision_audit_actors(issue, "review", review_id, review.spec.decisionAudit, index)

    for store_id, store in index.memory_stores.items():
        if store.spec.ownerProject and store.spec.ownerProject != project_name:
            issue("memory", "warning", f"memory store {store_id} belongs to project {store.spec.ownerProject}, not {project_name}", store_id)
        if store.spec.ownerMember and store.spec.ownerMember not in index.members:
            issue("memory", "warning", f"memory store {store_id} references missing owner member {store.spec.ownerMember}", store_id)

    for entry_id, entry in index.memory_entries.items():
        if entry.spec.store not in index.memory_stores:
            issue("memory", "error", f"memory entry {entry_id} references missing store {entry.spec.store}", entry_id)
        for evidence_ref in entry.spec.evidence:
            parsed_eval_ref = _parse_eval_evidence_ref(evidence_ref)
            if parsed_eval_ref is not None:
                suite_id, result_id = parsed_eval_ref
                result = index.eval_results.get(result_id)
                if suite_id not in index.eval_suites or result is None or result.spec.evalSuite != suite_id:
                    issue("memory", "warning", f"memory entry {entry_id} references missing eval evidence {evidence_ref}", entry_id)
        for eval_ref in entry.spec.evalEvidence:
            result = index.eval_results.get(eval_ref.lastResultId)
            if eval_ref.evalSuiteId not in index.eval_suites or result is None or result.spec.evalSuite != eval_ref.evalSuiteId:
                issue("memory", "warning", f"memory entry {entry_id} references missing eval result {eval_ref.lastResultId}", entry_id)
        for member in entry.spec.relatedMembers:
            if member not in index.members:
                issue("memory", "warning", f"memory entry {entry_id} references missing member {member}", entry_id)
        for assignment in entry.spec.relatedAssignments:
            if assignment not in index.assignments:
                issue("memory", "warning", f"memory entry {entry_id} references missing assignment {assignment}", entry_id)

    for binding_id, binding in index.memory_bindings.items():
        if binding.spec.store and binding.spec.store not in index.memory_stores:
            issue("memory", "error", f"memory binding {binding_id} references missing store {binding.spec.store}", binding_id)
        if binding.spec.entry and binding.spec.entry not in index.memory_entries:
            issue("memory", "error", f"memory binding {binding_id} references missing entry {binding.spec.entry}", binding_id)
        _validate_target(issue, "memory binding", binding_id, binding.spec.targetType, binding.spec.targetId, index)

    for grant_id, grant in index.memory_grants.items():
        if grant.spec.granteeMember not in index.members:
            issue("memory", "error", f"memory grant {grant_id} references missing grantee member {grant.spec.granteeMember}", grant_id)
        if grant.spec.grantorMember and grant.spec.grantorMember not in index.members:
            issue("memory", "warning", f"memory grant {grant_id} references missing grantor member {grant.spec.grantorMember}", grant_id)
        if grant.spec.task and grant.spec.task not in index.tasks:
            issue("memory", "warning", f"memory grant {grant_id} references missing task {grant.spec.task}", grant_id)
        if grant.spec.run and grant.spec.run not in index.runs:
            issue("memory", "warning", f"memory grant {grant_id} references missing run {grant.spec.run}", grant_id)
        for store in grant.spec.stores:
            if store not in index.memory_stores:
                issue("memory", "warning", f"memory grant {grant_id} references missing store {store}", grant_id)
        for entry in grant.spec.entries:
            if entry not in index.memory_entries:
                issue("memory", "warning", f"memory grant {grant_id} references missing entry {entry}", grant_id)

    for proposal_id, proposal in index.memory_proposals.items():
        if proposal.spec.sourceRun and proposal.spec.sourceRun not in index.runs:
            issue("memory", "warning", f"memory proposal {proposal_id} references missing run {proposal.spec.sourceRun}", proposal_id)
        if proposal.spec.member and proposal.spec.member not in index.members:
            issue("memory", "warning", f"memory proposal {proposal_id} references missing member {proposal.spec.member}", proposal_id)
        if proposal.spec.assignment and proposal.spec.assignment not in index.assignments:
            issue("memory", "warning", f"memory proposal {proposal_id} references missing assignment {proposal.spec.assignment}", proposal_id)

    learning_dedupe_keys: dict[str, str] = {}
    proposal_dedupe_keys: dict[str, str] = {}
    for extraction_id, extraction in index.learning_extractions.items():
        if extraction.spec.runId not in index.runs:
            issue("learning_extraction", "warning", f"learning extraction {extraction_id} references missing run {extraction.spec.runId}", extraction_id)
        if extraction.spec.sourceContext.project and extraction.spec.sourceContext.project != project_name:
            issue("learning_extraction", "warning", f"learning extraction {extraction_id} targets project {extraction.spec.sourceContext.project}, not {project_name}", extraction_id)
        if extraction.spec.sourceContext.taskId and extraction.spec.sourceContext.taskId not in index.tasks:
            issue("learning_extraction", "warning", f"learning extraction {extraction_id} references missing task {extraction.spec.sourceContext.taskId}", extraction_id)
        if extraction.spec.sourceContext.member and extraction.spec.sourceContext.member not in index.members:
            issue("learning_extraction", "warning", f"learning extraction {extraction_id} references missing member {extraction.spec.sourceContext.member}", extraction_id)
        if extraction.spec.sourceContext.assignment and extraction.spec.sourceContext.assignment not in index.assignments:
            issue("learning_extraction", "warning", f"learning extraction {extraction_id} references missing assignment {extraction.spec.sourceContext.assignment}", extraction_id)
        if extraction.spec.dedupeKey in learning_dedupe_keys:
            issue("learning_extraction", "warning", f"learning extraction {extraction_id} duplicates dedupe key from {learning_dedupe_keys[extraction.spec.dedupeKey]}", extraction_id)
        learning_dedupe_keys[extraction.spec.dedupeKey] = extraction_id
        for proposal_index, proposal in enumerate(extraction.spec.proposals):
            if proposal.dedupeKey and proposal.dedupeKey in proposal_dedupe_keys:
                issue("learning_extraction", "warning", f"learning extraction {extraction_id} proposal {proposal_index} duplicates dedupe key from {proposal_dedupe_keys[proposal.dedupeKey]}", extraction_id)
            if proposal.dedupeKey:
                proposal_dedupe_keys[proposal.dedupeKey] = f"{extraction_id}:{proposal_index}"
        _validate_decision_audit_actors(issue, "learning extraction", extraction_id, extraction.spec.decisionAudit, index)

    for activity_id, activity in index.member_activities.items():
        if activity.spec.member not in index.members:
            issue("member_activity", "error", f"member activity {activity_id} references missing member {activity.spec.member}", activity_id)
        if activity.spec.project and activity.spec.project != project_name:
            issue("member_activity", "warning", f"member activity {activity_id} targets project {activity.spec.project}, not {project_name}", activity_id)
        if activity.spec.assignment and activity.spec.assignment not in index.assignments:
            issue("member_activity", "warning", f"member activity {activity_id} references missing assignment {activity.spec.assignment}", activity_id)
        if activity.spec.task and activity.spec.task not in index.tasks:
            issue("member_activity", "warning", f"member activity {activity_id} references missing task {activity.spec.task}", activity_id)
        if activity.spec.run and activity.spec.run not in index.runs:
            issue("member_activity", "warning", f"member activity {activity_id} references missing run {activity.spec.run}", activity_id)

    for activity_id, activity in index.git_activities.items():
        if activity.spec.member not in index.members:
            issue("git_activity", "error", f"git activity {activity_id} references missing member {activity.spec.member}", activity_id)
        if activity.spec.project != project_name:
            issue("git_activity", "warning", f"git activity {activity_id} targets project {activity.spec.project}, not {project_name}", activity_id)
        if activity.spec.repository and activity.spec.repository not in index.repositories:
            issue("git_activity", "warning", f"git activity {activity_id} references missing repository {activity.spec.repository}", activity_id)
        if activity.spec.assignment and activity.spec.assignment not in index.assignments:
            issue("git_activity", "warning", f"git activity {activity_id} references missing assignment {activity.spec.assignment}", activity_id)
        _validate_decision_audit_actors(issue, "git activity", activity_id, activity.spec.decisionAudit, index)

    receipt_dedupe_keys: dict[str, str] = {}
    for receipt_id, receipt in index.git_activity_import_receipts.items():
        if receipt.spec.project != project_name:
            issue("git_activity_import", "warning", f"git activity import receipt {receipt_id} targets project {receipt.spec.project}, not {project_name}", receipt_id)
        if receipt.spec.repository and receipt.spec.repository not in index.repositories:
            issue("git_activity_import", "warning", f"git activity import receipt {receipt_id} references missing repository {receipt.spec.repository}", receipt_id)
        if receipt.spec.serviceMember and receipt.spec.serviceMember not in index.members:
            issue("git_activity_import", "warning", f"git activity import receipt {receipt_id} references missing service member {receipt.spec.serviceMember}", receipt_id)
        if receipt.spec.importerMember and receipt.spec.importerMember not in index.members:
            issue("git_activity_import", "warning", f"git activity import receipt {receipt_id} references missing importer member {receipt.spec.importerMember}", receipt_id)
        if receipt.spec.reviewedByMember and receipt.spec.reviewedByMember not in index.members:
            issue("git_activity_import", "warning", f"git activity import receipt {receipt_id} references missing reviewer member {receipt.spec.reviewedByMember}", receipt_id)
        for activity in receipt.spec.importedActivities:
            if activity not in index.git_activities:
                issue("git_activity_import", "warning", f"git activity import receipt {receipt_id} references missing imported activity {activity}", receipt_id)
        if receipt.spec.rawPayloadArtifact and receipt.spec.redactionPolicy != "artifact-reference":
            issue("git_activity_import", "warning", f"git activity import receipt {receipt_id} references raw payload artifact without artifact-reference redaction policy", receipt_id)
        if receipt.spec.dedupeKey in receipt_dedupe_keys:
            issue("git_activity_import", "warning", f"git activity import receipt {receipt_id} duplicates dedupe key from {receipt_dedupe_keys[receipt.spec.dedupeKey]}", receipt_id)
        receipt_dedupe_keys[receipt.spec.dedupeKey] = receipt_id
        _validate_decision_audit_actors(issue, "git activity import receipt", receipt_id, receipt.spec.decisionAudit, index)

    for review_id, review in index.git_activity_correlation_reviews.items():
        if review.spec.project != project_name:
            issue("git_activity_correlation_review", "warning", f"git activity correlation review {review_id} targets project {review.spec.project}, not {project_name}", review_id)
        if review.spec.repository and review.spec.repository not in index.repositories:
            issue("git_activity_correlation_review", "warning", f"git activity correlation review {review_id} references missing repository {review.spec.repository}", review_id)
        if review.spec.reviewerMember not in index.members:
            issue("git_activity_correlation_review", "warning", f"git activity correlation review {review_id} references missing reviewer member {review.spec.reviewerMember}", review_id)
        for receipt_ref in review.spec.receipts:
            if receipt_ref not in index.git_activity_import_receipts:
                issue("git_activity_correlation_review", "warning", f"git activity correlation review {review_id} references missing receipt {receipt_ref}", review_id)
        for activity_ref in review.spec.importedActivities:
            if activity_ref not in index.git_activities:
                issue("git_activity_correlation_review", "warning", f"git activity correlation review {review_id} references missing imported activity {activity_ref}", review_id)
        for member_ref in review.spec.members:
            if member_ref not in index.members:
                issue("git_activity_correlation_review", "warning", f"git activity correlation review {review_id} references missing member {member_ref}", review_id)
        for assignment_ref in review.spec.assignments:
            if assignment_ref not in index.assignments:
                issue("git_activity_correlation_review", "warning", f"git activity correlation review {review_id} references missing assignment {assignment_ref}", review_id)
        _validate_decision_audit_actors(issue, "git activity correlation review", review_id, review.spec.decisionAudit, index)

    for retrospective_id, retrospective in index.team_retrospectives.items():
        if retrospective.spec.project != project_name:
            issue("retrospective", "warning", f"retrospective {retrospective_id} targets project {retrospective.spec.project}, not {project_name}", retrospective_id)
        if retrospective.spec.facilitatorMember not in index.members:
            issue("retrospective", "error", f"retrospective {retrospective_id} references missing facilitator member {retrospective.spec.facilitatorMember}", retrospective_id)
        for member in retrospective.spec.participants:
            if member not in index.members:
                issue("retrospective", "warning", f"retrospective {retrospective_id} references missing participant member {member}", retrospective_id)
        if retrospective.spec.sourceTaskPlan and retrospective.spec.sourceTaskPlan not in index.task_plans:
            issue("retrospective", "warning", f"retrospective {retrospective_id} references missing task plan {retrospective.spec.sourceTaskPlan}", retrospective_id)
        for run in retrospective.spec.sourceRuns:
            if run not in index.runs:
                issue("retrospective", "warning", f"retrospective {retrospective_id} references missing run {run}", retrospective_id)
        for task in retrospective.spec.sourceTasks:
            if task not in index.tasks:
                issue("retrospective", "warning", f"retrospective {retrospective_id} references missing task {task}", retrospective_id)
        for message in retrospective.spec.sourceMessages:
            if message not in index.member_messages:
                issue("retrospective", "warning", f"retrospective {retrospective_id} references missing message {message}", retrospective_id)
        for handoff in retrospective.spec.sourceHandoffs:
            if handoff not in index.handoffs:
                issue("retrospective", "warning", f"retrospective {retrospective_id} references missing handoff {handoff}", retrospective_id)
        if retrospective.spec.proposedMemory and retrospective.spec.proposedMemory not in index.memory_proposals:
            issue("retrospective", "warning", f"retrospective {retrospective_id} references missing memory proposal {retrospective.spec.proposedMemory}", retrospective_id)

    for automation_id, automation in index.automations.items():
        if automation.spec.ownerMember and automation.spec.ownerMember not in index.members:
            issue("automation", "warning", f"automation {automation_id} references missing owner member {automation.spec.ownerMember}", automation_id)
        if automation.spec.serviceMember and automation.spec.serviceMember not in index.members:
            issue("automation", "warning", f"automation {automation_id} references missing service member {automation.spec.serviceMember}", automation_id)
        if automation.spec.project and automation.spec.project != project_name:
            issue("automation", "warning", f"automation {automation_id} targets project {automation.spec.project}, not {project_name}", automation_id)

    for event_id, event in index.automation_trigger_events.items():
        if event.spec.automation not in index.automations:
            issue("automation_trigger_event", "error", f"automation trigger event {event_id} references missing automation {event.spec.automation}", event_id)
        if event.spec.project and event.spec.project != project_name:
            issue("automation_trigger_event", "warning", f"automation trigger event {event_id} targets project {event.spec.project}, not {project_name}", event_id)
        if event.spec.actorMember and event.spec.actorMember not in index.members:
            issue("automation_trigger_event", "warning", f"automation trigger event {event_id} references missing actor member {event.spec.actorMember}", event_id)
        if event.spec.automationRun and event.spec.automationRun not in index.automation_runs:
            issue("automation_trigger_event", "warning", f"automation trigger event {event_id} references missing automation run {event.spec.automationRun}", event_id)
        _validate_decision_audit_actors(issue, "automation trigger event", event_id, event.spec.decisionAudit, index)

    for lease_id, lease in index.automation_scheduler_leases.items():
        if lease.spec.automation not in index.automations:
            issue("automation_scheduler_lease", "error", f"automation scheduler lease {lease_id} references missing automation {lease.spec.automation}", lease_id)
        if lease.spec.project and lease.spec.project != project_name:
            issue("automation_scheduler_lease", "warning", f"automation scheduler lease {lease_id} targets project {lease.spec.project}, not {project_name}", lease_id)
        if lease.spec.automationTriggerEvent and lease.spec.automationTriggerEvent not in index.automation_trigger_events:
            issue("automation_scheduler_lease", "warning", f"automation scheduler lease {lease_id} references missing automation trigger event {lease.spec.automationTriggerEvent}", lease_id)
        if lease.spec.automationRun and lease.spec.automationRun not in index.automation_runs:
            issue("automation_scheduler_lease", "warning", f"automation scheduler lease {lease_id} references missing automation run {lease.spec.automationRun}", lease_id)
        _validate_decision_audit_actors(issue, "automation scheduler lease", lease_id, lease.spec.decisionAudit, index)

    for automation_run_id, automation_run in index.automation_runs.items():
        if automation_run.spec.automation not in index.automations:
            issue("automation_run", "error", f"automation run {automation_run_id} references missing automation {automation_run.spec.automation}", automation_run_id)
        if automation_run.spec.ownerMember and automation_run.spec.ownerMember not in index.members:
            issue("automation_run", "warning", f"automation run {automation_run_id} references missing owner member {automation_run.spec.ownerMember}", automation_run_id)
        if automation_run.spec.serviceMember and automation_run.spec.serviceMember not in index.members:
            issue("automation_run", "warning", f"automation run {automation_run_id} references missing service member {automation_run.spec.serviceMember}", automation_run_id)
        if automation_run.spec.createdTask and automation_run.spec.createdTask not in index.tasks:
            issue("automation_run", "warning", f"automation run {automation_run_id} references missing created task {automation_run.spec.createdTask}", automation_run_id)
        if automation_run.spec.createdRun and automation_run.spec.createdRun not in index.runs:
            issue("automation_run", "warning", f"automation run {automation_run_id} references missing created run {automation_run.spec.createdRun}", automation_run_id)
        if automation_run.spec.createdTaskPlan and automation_run.spec.createdTaskPlan not in index.task_plans:
            issue("automation_run", "warning", f"automation run {automation_run_id} references missing created task plan {automation_run.spec.createdTaskPlan}", automation_run_id)
        if automation_run.spec.createdMessage and automation_run.spec.createdMessage not in index.member_messages:
            issue("automation_run", "warning", f"automation run {automation_run_id} references missing created message {automation_run.spec.createdMessage}", automation_run_id)
        for approval in automation_run.spec.approvals:
            if approval not in index.automation_approvals:
                issue("automation_run", "warning", f"automation run {automation_run_id} references missing automation approval {approval}", automation_run_id)
        _validate_decision_audit_actors(issue, "automation run", automation_run_id, automation_run.spec.decisionAudit, index)

    for approval_id, approval in index.automation_approvals.items():
        if approval.spec.automationRun not in index.automation_runs:
            issue("automation_approval", "error", f"automation approval {approval_id} references missing automation run {approval.spec.automationRun}", approval_id)
        if approval.spec.automation not in index.automations:
            issue("automation_approval", "error", f"automation approval {approval_id} references missing automation {approval.spec.automation}", approval_id)
        if approval.spec.project and approval.spec.project != project_name:
            issue("automation_approval", "warning", f"automation approval {approval_id} targets project {approval.spec.project}, not {project_name}", approval_id)
        if approval.spec.approvalWorkflow and approval.spec.approvalWorkflow not in index.approval_workflows:
            issue("automation_approval", "error", f"automation approval {approval_id} references missing approval workflow {approval.spec.approvalWorkflow}", approval_id)
        if approval.spec.reviewerMember not in index.members:
            issue("automation_approval", "error", f"automation approval {approval_id} references missing reviewer member {approval.spec.reviewerMember}", approval_id)
        elif approval.spec.reviewerKind and approval.spec.reviewerKind != index.members[approval.spec.reviewerMember].spec.kind:
            issue("automation_approval", "warning", f"automation approval {approval_id} reviewer kind {approval.spec.reviewerKind} does not match member {approval.spec.reviewerMember}", approval_id)
        _validate_decision_audit_actors(issue, "automation approval", approval_id, approval.spec.decisionAudit, index)

    for workflow_id, workflow in index.approval_workflows.items():
        if workflow.spec.project and workflow.spec.project != project_name:
            issue("approval_workflow", "warning", f"approval workflow {workflow_id} targets project {workflow.spec.project}, not {project_name}", workflow_id)
        if workflow.spec.subjectKind == "PermissionRequest" and workflow.spec.subjectRef not in index.permission_requests:
            issue("approval_workflow", "error", f"approval workflow {workflow_id} references missing permission request {workflow.spec.subjectRef}", workflow_id)
        if workflow.spec.subjectKind == "AutomationApproval" and workflow.spec.subjectRef not in index.automation_approvals:
            issue("approval_workflow", "error", f"approval workflow {workflow_id} references missing automation approval {workflow.spec.subjectRef}", workflow_id)
        for member_ref in [workflow.spec.requesterMember, workflow.spec.ownerMember]:
            if member_ref and member_ref not in index.members:
                issue("approval_workflow", "warning", f"approval workflow {workflow_id} references missing member {member_ref}", workflow_id)
        for stage in workflow.spec.stages:
            for reviewer in stage.reviewerMembers:
                if reviewer not in index.members:
                    issue("approval_workflow", "warning", f"approval workflow {workflow_id} stage {stage.id} references missing reviewer {reviewer}", workflow_id)
            if stage.escalation and stage.escalation.targetMember not in index.members:
                issue("approval_workflow", "warning", f"approval workflow {workflow_id} stage {stage.id} references missing escalation target {stage.escalation.targetMember}", workflow_id)
        _validate_decision_audit_actors(issue, "approval workflow", workflow_id, workflow.spec.decisionAudit, index)

    for request_id, request in index.permission_requests.items():
        if request.spec.project and request.spec.project != project_name:
            issue("permission_request", "warning", f"permission request {request_id} targets project {request.spec.project}, not {project_name}", request_id)
        if request.spec.member not in index.members:
            issue("permission_request", "error", f"permission request {request_id} references missing member {request.spec.member}", request_id)
        if request.spec.assignment and request.spec.assignment not in index.assignments:
            issue("permission_request", "warning", f"permission request {request_id} references missing assignment {request.spec.assignment}", request_id)
        if request.spec.task and request.spec.task not in index.tasks:
            issue("permission_request", "warning", f"permission request {request_id} references missing task {request.spec.task}", request_id)
        if request.spec.run and request.spec.run not in index.runs:
            issue("permission_request", "warning", f"permission request {request_id} references missing run {request.spec.run}", request_id)
        if request.spec.automation and request.spec.automation not in index.automations:
            issue("permission_request", "warning", f"permission request {request_id} references missing automation {request.spec.automation}", request_id)
        if request.spec.approvalWorkflow and request.spec.approvalWorkflow not in index.approval_workflows:
            issue("permission_request", "error", f"permission request {request_id} references missing approval workflow {request.spec.approvalWorkflow}", request_id)
        if request.spec.requesterMember and request.spec.requesterMember not in index.members:
            issue("permission_request", "warning", f"permission request {request_id} references missing requester member {request.spec.requesterMember}", request_id)
        if request.spec.reviewerMember and request.spec.reviewerMember not in index.members:
            issue("permission_request", "warning", f"permission request {request_id} references missing reviewer member {request.spec.reviewerMember}", request_id)
        if request.spec.grant and request.spec.grant not in index.permission_grants:
            issue("permission_request", "warning", f"permission request {request_id} references missing permission grant {request.spec.grant}", request_id)
        _validate_decision_audit_actors(issue, "permission request", request_id, request.spec.decisionAudit, index)

    for grant_id, grant in index.permission_grants.items():
        member = grant.spec.scope.get("member")
        project = grant.spec.scope.get("project")
        assignment = grant.spec.scope.get("assignment")
        if project and project != project_name:
            issue("permission_grant", "warning", f"permission grant {grant_id} targets project {project}, not {project_name}", grant_id)
        if member and member not in index.members:
            issue("permission_grant", "error", f"permission grant {grant_id} references missing member {member}", grant_id)
        if assignment and assignment not in index.assignments:
            issue("permission_grant", "warning", f"permission grant {grant_id} references missing assignment {assignment}", grant_id)
        if grant.spec.sourceRequest and grant.spec.sourceRequest not in index.permission_requests:
            issue("permission_grant", "warning", f"permission grant {grant_id} references missing permission request {grant.spec.sourceRequest}", grant_id)
        if grant.spec.approvedByMember and grant.spec.approvedByMember not in index.members:
            issue("permission_grant", "warning", f"permission grant {grant_id} references missing approver member {grant.spec.approvedByMember}", grant_id)
        _validate_decision_audit_actors(issue, "permission grant", grant_id, grant.spec.decisionAudit, index)

    for skill_id, skill in index.skills.items():
        if skill.spec.ownerMember and skill.spec.ownerMember not in index.members:
            issue("skill", "warning", f"skill {skill_id} references missing owner member {skill.spec.ownerMember}", skill_id)
        for project in skill.spec.projects:
            if project != project_name:
                issue("skill", "warning", f"skill {skill_id} targets project {project}, not {project_name}", skill_id)
        for policy in skill.spec.requiredPermissions:
            if policy not in index.permission_policies:
                issue("skill", "warning", f"skill {skill_id} references missing permission policy {policy}", skill_id)
        _validate_decision_audit_actors(issue, "skill", skill_id, skill.spec.decisionAudit, index)

    for member_id, member in index.members.items():
        for skill in member.spec.skills:
            if skill not in index.skills:
                issue("member", "warning", f"member {member_id} references missing skill {skill}", member_id)

    for suite_id, suite in index.eval_suites.items():
        if suite.spec.project != project_name:
            issue("eval_suite", "error", f"eval suite {suite_id} belongs to project {suite.spec.project}, not {project_name}", suite_id)
        if not suite.spec.cases:
            issue("eval_suite", "warning", f"eval suite {suite_id} has no cases", suite_id)
        for member in suite.spec.members:
            if member not in index.members:
                issue("eval_suite", "warning", f"eval suite {suite_id} references missing member {member}", suite_id)
        for assignment in suite.spec.assignments:
            if assignment not in index.assignments:
                issue("eval_suite", "warning", f"eval suite {suite_id} references missing assignment {assignment}", suite_id)
        for task in suite.spec.tasks:
            if task not in index.tasks:
                issue("eval_suite", "warning", f"eval suite {suite_id} references missing task {task}", suite_id)
        judge = suite.spec.judge
        if judge.member and judge.member not in index.members:
            issue("eval_suite", "warning", f"eval suite {suite_id} judge references missing member {judge.member}", suite_id)
        if judge.modelProfile and judge.modelProfile not in index.model_profiles:
            issue("eval_suite", "warning", f"eval suite {suite_id} judge references missing model profile {judge.modelProfile}", suite_id)
        if judge.policyRef and judge.policyRef not in index.permission_policies:
            issue("eval_suite", "warning", f"eval suite {suite_id} judge references missing policy {judge.policyRef}", suite_id)
        golden_outputs = set(suite.spec.goldenOutputs)
        for case in suite.spec.cases:
            case_label = case.id or case.title
            if case.member and case.member not in index.members:
                issue("eval_suite", "warning", f"eval suite {suite_id} case {case_label} references missing member {case.member}", suite_id)
            if case.assignment and case.assignment not in index.assignments:
                issue("eval_suite", "warning", f"eval suite {suite_id} case {case_label} references missing assignment {case.assignment}", suite_id)
            if case.task and case.task not in index.tasks:
                issue("eval_suite", "warning", f"eval suite {suite_id} case {case_label} references missing task {case.task}", suite_id)
            for golden_output in case.goldenOutputRefs:
                if golden_output not in golden_outputs:
                    issue("eval_suite", "warning", f"eval suite {suite_id} case {case_label} references missing golden output {golden_output}", suite_id)

    for result_id, result in index.eval_results.items():
        if result.spec.project != project_name:
            issue("eval_result", "error", f"eval result {result_id} belongs to project {result.spec.project}, not {project_name}", result_id)
        if result.spec.evalSuite not in index.eval_suites:
            issue("eval_result", "error", f"eval result {result_id} references missing EvalSuite {result.spec.evalSuite}", result_id)
        if result.spec.task and result.spec.task not in index.tasks:
            issue("eval_result", "warning", f"eval result {result_id} references missing task {result.spec.task}", result_id)
        if result.spec.run and result.spec.run not in index.runs:
            issue("eval_result", "warning", f"eval result {result_id} references missing run {result.spec.run}", result_id)
        if result.spec.member and result.spec.member not in index.members:
            issue("eval_result", "warning", f"eval result {result_id} references missing member {result.spec.member}", result_id)
        if result.spec.assignment and result.spec.assignment not in index.assignments:
            issue("eval_result", "warning", f"eval result {result_id} references missing assignment {result.spec.assignment}", result_id)
        if result.spec.totalCases and result.spec.passedCases + result.spec.failedCases > result.spec.totalCases:
            issue("eval_result", "warning", f"eval result {result_id} has passedCases + failedCases greater than totalCases", result_id)

    return issues


def _parse_eval_evidence_ref(ref: str) -> tuple[str, str] | None:
    if not ref.startswith("eval://"):
        return None
    rest = ref[len("eval://") :]
    parts = rest.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def manifest_to_record(manifest: Manifest) -> dict[str, Any]:
    data = manifest.model_dump(mode="json")
    data["id"] = manifest.object_id
    return data


def _validate_target(
    issue: Any,
    label: str,
    object_id: str,
    target_type: str,
    target_id: str,
    index: WorkspaceIndex,
) -> None:
    targets = {
        "member": index.members,
        "project": {index.project.object_id: index.project},
        "assignment": index.assignments,
        "task": index.tasks,
        "run": index.runs,
        "team": index.teams,
        "context-capsule": index.runs,
    }
    records = targets.get(target_type)
    if records is not None and target_id not in records:
        issue("reference", "warning", f"{label} {object_id} references missing {target_type} {target_id}", object_id)


def _validate_decision_audit_actors(
    issue: Any,
    label: str,
    object_id: str,
    records: list[Any],
    index: WorkspaceIndex,
) -> None:
    for offset, record in enumerate(records, start=1):
        if record.actorMember and record.actorMember not in index.members:
            issue("audit", "warning", f"{label} {object_id} decision audit #{offset} references missing actor member {record.actorMember}", object_id)


def _load_required(path: Path, expected_type: type[Manifest]) -> Any:
    data = read_yaml(path)
    manifest = parse_manifest(data)
    if not isinstance(manifest, expected_type):
        raise ValueError(f"{path} is {manifest.kind}, expected {expected_type.__name__}")
    return manifest


def _load_manifest_dir(path: Path, expected_type: type[Manifest]) -> dict[str, Any]:
    return _load_manifest_paths(sorted(path.glob("*.yaml")) if path.exists() else [], expected_type)


def _permission_request_views_from_workflows(workflows: dict[str, ApprovalWorkflow]) -> dict[str, PermissionRequest]:
    records: dict[str, PermissionRequest] = {}
    for workflow in workflows.values():
        if workflow.spec.subjectKind != "PermissionRequest":
            continue
        subject_record = _workflow_subject_record(workflow, "PermissionRequest")
        if not subject_record:
            continue
        subject_record.setdefault("spec", {})["approvalWorkflow"] = workflow.object_id
        request = PermissionRequest.model_validate(subject_record)
        records[request.object_id] = request
    return records


def _automation_approval_views_from_workflows(workflows: dict[str, ApprovalWorkflow]) -> dict[str, AutomationApproval]:
    records: dict[str, AutomationApproval] = {}
    for workflow in workflows.values():
        if workflow.spec.subjectKind != "AutomationApproval":
            continue
        subject_record = _workflow_subject_record(workflow, "AutomationApproval")
        if not subject_record:
            continue
        subject_record.setdefault("spec", {})["approvalWorkflow"] = workflow.object_id
        approval = AutomationApproval.model_validate(subject_record)
        records[approval.object_id] = approval
    return records


def _workflow_subject_record(workflow: ApprovalWorkflow, expected_kind: str) -> dict[str, Any]:
    audit = workflow.spec.audit if isinstance(workflow.spec.audit, dict) else {}
    subject_record = audit.get("subjectRecord")
    if not isinstance(subject_record, dict):
        return {}
    data = dict(subject_record)
    data["kind"] = expected_kind
    data.setdefault("metadata", {})["id"] = workflow.spec.subjectRef
    data.setdefault("apiVersion", workflow.apiVersion)
    return data


def _load_manifest_tree(path: Path, expected_type: type[Manifest]) -> dict[str, Any]:
    return _load_manifest_paths(sorted(path.glob("**/*.yaml")) if path.exists() else [], expected_type)


def _load_manifest_paths(paths: list[Path], expected_type: type[Manifest]) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for manifest_path in paths:
        data = read_yaml(manifest_path)
        manifest = parse_manifest(data)
        if isinstance(manifest, expected_type):
            records[manifest.object_id] = manifest
    return records
