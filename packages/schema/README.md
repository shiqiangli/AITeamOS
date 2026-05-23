# AITEAMOS Schema Package

This package will contain the versioned manifest schemas for `aiteamos.dev/v1alpha1`.

Schema ownership decision:

- Pydantic models are the source of truth.
- JSON Schema and OpenAPI are generated from Pydantic.
- Dashboard TypeScript types are generated from JSON Schema/OpenAPI.
- Zod may be used only as generated or adapter-level validation, not as a second source of truth.

Greenfield schema targets:

- Workspace
- Project
- Repository
- RoleTemplate
- TeamMember
- ProductUser
- DigitalExecutionProfile
- HumanCollaborationProfile
- HybridExecutionProfile
- ServiceAccountProfile
- Team
- Assignment
- MemberActivity
- GitActivity
- GitActivityImportReceipt
- GitActivityCorrelationReview
- Task
- Run
- RunEvent
- ContextManifest
- Artifact
- Review
- ReviewTarget
- MemoryStore
- MemoryEntry
- MemoryVersion
- MemoryBinding
- MemoryGrant
- MemoryProposal
- MemberMessage
- Handoff
- TeamRetrospective
- Automation
- AutomationRun
- DecisionAuditRecord
- PermissionPolicy
- PermissionRequest
- PermissionGrant
- Skill
- Connector
- ModelProfile
- BudgetPolicy

Schema changes affect the protocol and require human review.

Generated API records also include derived, non-manifest records such as `RetrospectiveSuggestionRecord` and `ConnectorRemediationSuggestion`. These records are safe dashboard/API projections and must not be treated as workspace source of truth.

`ModelProfile.spec.invocation` stores provider-specific execution knobs such as reasoning effort, max output tokens, and timeout. Local/manual profiles may also use `fixtureResponse` for deterministic public demo and test replays that intentionally avoid external model calls. Secrets must be referenced by environment variable name through `secretEnv`, not stored in workspace files.

`Run.spec.ingest` records assisted ingest metadata such as the last ingest id, missing required fields, and artifact paths. `MemoryProposal.spec.sourceIngestId` links proposals back to the assisted ingest payload that produced them. `MemoryProposal.spec.sourceExtractorId` and `dedupeKey` identify generated memory proposals so repeated extraction stays idempotent.

`Run.spec.outputs` may contain strings or structured artifact records. Worker command execution records `test_log` and `command_log` outputs that point to files under the run directory.

`Run.spec.worker` stores worker runtime metadata such as stage, worktree path, heartbeat timestamp, lease seconds, verification commands, and stalled/recovery details. It is runtime state, but it is still written through workspace mutations because `.aiteamos` remains the source of truth for reviewable run state.

`Review.spec.run` optionally binds a human or AI review to a specific run. `Review.spec.task` remains available for broader task-level reviews. Run-scoped reviews should be linked back through `Run.spec.reviews` and `Task.spec.relatedReviews`.

`DecisionAuditRecord` is the shared provenance shape for decisions that influence execution or governance. `human_approval` records human authority, `digital_recommendation` records AI or hybrid advice, `service_policy_decision` records policy/service enforcement, and `system_check` records lifecycle sweeps such as permission grant expiry. A decision audit record may attach a typed `RiskAssessment`; the classifier output is evidence and routing input, not a replacement for explicit allow/ask/deny policy.

`ProductUser` maps a dashboard or product principal to a TeamMember, redaction-safe identity provider metadata, status, role set, governance scopes, and an environment-variable name for the session token. `TeamMember.spec.userBinding` mirrors that relationship for member-centric projections. These records must never store raw token secrets or raw provider subjects in `.aiteamos`; the manifest is the source of truth for identity and admin/viewer role assignment, while process environment remains the secret boundary.

`SessionLoginRecord` describes a ProductUser browser session response. It may expose issued/expires timestamps, session version/id, and a CSRF token for dashboard requests, but the raw ProductUser token remains outside manifests, generated schema, and browser storage.

`PermissionAction` is the shared action payload used by permission explanation, requests, and grants. It can describe file actions, Bash commands, web/network destinations, external MCP tools, environment variables, connector operations, and artifact-store operations. Matchers reduce these payloads to canonical strings such as `WebFetch(docs.qoder.com)`, `Network(api.github.com:443)`, `mcp__github__create_issue`, `EnvVar(OPENAI_API_KEY:use)`, `Connector(github:issues:read)`, and `ArtifactStore(local-artifacts:write:retention=reviewed-runs:redaction=sanitize)`.

`PermissionRequest` records a member/action approval request as durable workspace state, including pending, approved, rejected, cancelled, and expired lifecycle states. It can carry project/member/assignment/task/run lineage or automation/automationRun lineage for control-plane execution blockers. `PermissionGrant` records the bounded approval result with scope, action, approver, source request, status, expiration, and decision-audit provenance. Runtime approval must be reconstructable from these manifests; a UI popup alone is not protocol state, and rejecting a request must not create a grant.

`Automation` records the durable configuration for scheduled, manual, webhook, or event-driven control-plane work. Creating an Automation manifest does not execute the target; execution starts only through dry-run, trigger, scheduler, or event admission flows that create `AutomationRun` records. Dashboard scheduler presets, such as daily or weekly GitActivity retention sweeps, are stored as ordinary `Automation.spec.triggers` config and do not grant execution authority by themselves.

`AutomationRun` records automation dry-runs, trigger attempts, approval waits, queued executor work, and executor outcomes. It may link to `createdMessage`, `createdTaskPlan`, `createdTask`, and `createdRun`, but the run record itself is not proof that worker code executed; worker execution remains a separate Run lifecycle. Project and Employee schedule/status views are derived from `Automation`, `AutomationSchedulerLease`, and `AutomationRun`; no separate projection manifest is required. Dashboard drilldown focus for automation/project/member/assignment is transient UI state and not a schema object. `connector_failure_reminder` is an automation target for routing connector health/provider-delivery evidence into audited `MemberMessage` records with throttling; it must not mutate connector or provider incident state. `git_activity_correlation_promotion` is a governed service-policy target that consumes only eligible approved `GitActivityCorrelationReview` candidates and still reuses the concrete GitActivity promotion permission checks before creating activity evidence. `git_activity_retention_sweep` is the automation target for scheduled GitActivity retention cleanup; it consumes expired candidates through the normal AutomationRun executor, service-member permission checks, optional approval gates, and the same GitActivity lifecycle mutation.

Dashboard route parameters such as `page`, `project`, `member`, `automation`, `assignment`, and `source` are not manifest schema fields. They are browser navigation state used to restore Project, Employee, and Automations projections; protocol state remains in `.aiteamos` manifests and generated API records.

`ContextManifest.spec.sourceDecisions` is the structured audit trail for context inclusion and exclusion. It records the source type, source ref, outcome, reason, dedupe key, budget bucket, and available ACL/lifecycle/freshness/confidence/ranking metadata, plus short doc/code/memory snippets when the compiler already included that content in the capsule. It is explainability metadata for the compiled context; it is not chain-of-thought and it does not grant access beyond the run context preview.

`MemberMessage` is the shared collaboration manifest for ordinary messages, AskForHelp, ReviewRequest, KnowledgeShare, and handoff notes. It carries workflow lifecycle fields (`status`, `priority`, `requestedResponseBy`, `resolvedAt`, `resolvedByMember`, `resolution`) so collaboration records can be projected by employee/member, project, task, run, and message type without creating separate durable objects for each subtype. Connector-failure review requests add audit metadata such as `connectorEscalationDedupeKey`, `evidenceIds`, `existingReminderMessages`, and `connectorEscalationResolution`; closing them requires the connector escalation resolution workflow rather than generic message resolution. Derived escalation candidates may report `latestResolvedReviewRequest`, `reviewedEvidenceIds`, `unreviewedEvidenceIds`, `resolvedReviewRequest`, and `suppressedByResolution` so dashboards can explain both covered evidence and newly routable evidence without adding new durable schema objects.

`TeamRetrospective` is the reviewed team-learning manifest for multi-run, multi-message, and multi-handoff synthesis. It records facilitator, participants, source runs/tasks/messages/handoffs, lessons, action items, and a linked pending `MemoryProposal`. Retrospectives do not approve memory directly; they feed the normal memory review queue.

`MemberActivity` records reviewed/imported non-Git work evidence with source type, contribution kind, visibility, timestamp, summary, and evidence links. `GitActivity` records normalized local/provider Git evidence with member, project, repository, assignment, refs, provider ids, URL, timestamp, summary, evidence, lifecycle, archive/redaction timestamps, export policy, redaction policy, retention timestamp, and decision audit. `GitActivityImportReceipt` records the reviewed import boundary for Git evidence: source type, provider, connector/repository binding, dedupe key, payload digest, redaction/import policy, reviewer or service policy decision, and linked GitActivity ids. Raw provider payloads are not stored by default. Local Git admission and GitHub/GitLab provider event admission both write `needs-review` receipts idempotently by dedupe key and leave `importedActivities` empty until a reviewed promotion creates durable GitActivity with explicit member/assignment mapping and decision audit. Provider event admission stores only sanitized refs, hashed provider actor/repository/url metadata, normalized event/activity type, and payload digest. `Connector.spec.gitActivityImport` adds the typed connector policy for provider Git evidence: repository and installation allowlists, protected ref patterns, provider actor mappings, default member/assignment fallback, import policy, auto-promotion intent, dedupe strategy, and health requirement. `GitActivityCorrelationPreviewRecord` is a read-only API shape that groups import receipts by PR/external id/ref/commit/payload digest and flags force-push, squash/merge, or multi-event risks before promotion. `GitActivityCorrelationReview` is the durable reviewed reconciliation manifest for those groups; it records receipts, reviewer member/kind, decision, risk flags, evidence, optional promotion recommendations, and imported activity links. Creating the review does not create GitActivity or change memory, permissions, growth, tasks, or runs; approved group promotion may later consume it to create or idempotently reuse one GitActivity for all selected receipts. Service-policy promotion adds a read-only candidate projection with approval freshness, import-policy, risk-flag, connector-health, and service-permission blockers before an AutomationRun may call the same promotion path. `GitActivity` lifecycle changes archive or redact the activity manifest in place and keep import/correlation/member/project lineage intact. `retainedUntil` drives read-only retention candidates and governed sweep execution; manual and automation-owned sweeps reuse the same lifecycle mutation and never delete receipts, reviews, memory, tasks, runs, permissions, or growth state. These records are projection evidence for Project, Employee, Git Activity, and Performance / Growth views; they are not scores, rankings, permission grants, or automatic profile updates.

`GitActivity.spec.exportPolicy` controls sanitized workspace export behavior. `include` is allowed only for active evidence after generic secret-value redaction; `sanitize` keeps lineage while redacting provider-facing summary, external id, URL, and refs; `manifest-only` emits an audit skeleton; and `exclude` omits the manifest from the bundle with an explicit export-manifest reason. Archived or redacted GitActivity records must not be exported with provider-facing details.

`RetrospectiveSuggestionRecord` is a read-only derived API shape. It recommends candidate retrospective payloads from explicit runs, journals, messages, and handoffs, but it does not write manifests or create memory proposals.

`ConnectorRemediationSuggestion` is a read-only derived API shape. It converts open or newly re-routable connector escalation evidence into a proposed TaskPlan payload with actionable evidence ids, suggested owner member, assignment, blockers, and warnings. The record is not a TaskPlan manifest and must not create tasks, runs, connector changes, permission grants, review closure, or memory state without a separate reviewed creation workflow.

A dashboard-staged remediation TaskPlan draft is also not a manifest. It is local UI preview state copied from `ConnectorRemediationSuggestion.spec.proposedTaskPlan`; it becomes protocol state only when the reviewed submit endpoint validates evidence freshness, permission, and required review gates, then writes a normal draft `TaskPlan` manifest with `spec.connectorRemediation` and `spec.decisionAudit`.

`ConnectorRemediationTaskPlan` is a derived API projection over ordinary `TaskPlan` manifests that carry `spec.connectorRemediation`. It normalizes connector lineage, actionable evidence ids, submitter/member kind, assigned members, assignment ids, status, and latest decision audit for Tasks, Reviews, Project, Employee, Settings, and Home views; it is not a separate manifest kind.

Accepting a connector remediation TaskPlan is a governed mutation on ordinary manifests. The accept endpoint records reviewed evidence/review-request ids, changes the TaskPlan status to `accepted`, stores created task ids in `spec.connectorRemediation.createdTasks`, and writes ordinary `Task` manifests that carry `sourceTaskPlan` and connector lineage as extra protocol fields.

Materialized connector remediation Tasks remain ordinary `Task` manifests. The derived projection reads `spec.connectorRemediation.source: connector-remediation-task-plan`, links the Task to its source TaskPlan, evidence lineage, queue status, and launch readiness, and does not create a separate manifest kind.

Launching a materialized connector remediation Task creates an ordinary `Run` manifest through the normal Run creation path. The Run carries extra protocol fields such as `sourceTaskPlan`, `sourceTaskPlanSubtask`, `connectorRemediation`, `createdByMember`, and `decisionAudit` so lineage remains inspectable without introducing a separate remediation-run manifest kind. Creating this Run is not worker execution; worker/service starts still pass the normal readiness and permission gates.

`ConnectorRemediationRun` is a derived API projection over ordinary `Run` manifests that carry `spec.connectorRemediation.source: connector-remediation-task-run-launch`. It adds source TaskPlan/Task/evidence/member provenance plus execution-plan, model-readiness, worker-readiness, worker-authorization, denied permission-action, PermissionRequest/PermissionGrant outcome state, and next-control-plane-action fields for Runs, Reviews, Project, Employee, Settings, and Home views; it is not a separate manifest kind.

Connector remediation permission initiation writes an ordinary `PermissionRequest` manifest with `source: connector-remediation-run-permission-request`; there is no separate connector permission manifest kind. The request remains pending until the normal permission review API approves or rejects it. Remediation Run projections then derive pending/approved/rejected request ids, active/expired/revoked grant ids, and policy-blocker outcomes from those ordinary manifests.

Generic worker and AutomationRun permission initiation also write ordinary `PermissionRequest` manifests. Worker requests use `source: run-worker-authorization-permission-request` with `run` lineage. Automation requests use `source: automation-run-permission-request` with both `automation` and `automationRun` lineage. Derived projections, not new manifest kinds, expose the approval outcome back to worker authorization and automation control-plane views.
