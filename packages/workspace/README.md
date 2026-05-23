# AITEAMOS Workspace Package

This package will load, validate, and index `.aiteamos` workspaces.

Workspace responsibilities:

- Discover embedded or shadow workspace roots.
- Parse workspace manifests.
- Resolve project, repository, member, assignment, model profile, task, run, collaboration, and memory references.
- Produce an in-memory index model for the API.
- Write safe dashboard mutations back to files.
- Compile deterministic run context capsules and context manifests from task, member, assignment, project docs, repository maps, scoped code excerpts, approved memory, recent runs, and model/budget settings.
- Emit structured context source decisions that explain included and excluded docs, code, memory, handoffs, permission policies, execution profiles, recent runs, dedupe keys, budget buckets, and safe snippets without relying on hidden chain-of-thought.
- Rebuild run context capsules from the dashboard/API without changing task ownership or worker state.
- Promote approved memory proposals into approved memory item manifests.
- Edit pending-review memory proposal title, kind, content, confidence, evidence, and review guidance before approval.
- Evaluate memory promotion gates from proposal status, source run, evidence, confidence, content, review guidance, and sensitive topics before approval.
- Derive and apply safe pending-proposal repair hints for missing evidence, confidence, and review guidance without auto-approving memory.
- Derive proposal review queue status for ready, warning, repairable, blocked, and closed memory proposals.
- Evaluate knowledge health for approved-memory and pending-proposal quality risks.
- Mark approved memory stale or re-verify it through explicit human mutations; stale memory is kept for audit but omitted from future context capsules.
- Edit approved-memory title, kind, content, confidence, and evidence through explicit human mutations; edits automatically mark the memory stale until it is re-verified.
- Append memory governance events to `.aiteamos/memory/events.jsonl` for approvals, edits, stale marks, and verification.
- Extract pending memory proposals from run journals, test logs, and failure events without auto-approving them.
- Derive task execution readiness queues for ready, missing-member, missing-assignment, missing-model, active, stalled, review-ready, attention-needed, and done tasks.
- Build read-only run launch plans that validate selected member, assignment, mode, model profile, branch base, blockers, warnings, and next actions before a dashboard mutation creates a run.
- Build read-only run execution plans that summarize each run's next actions from status, mode, context, journal, review target, artifacts, and recovery state.
- Evaluate read-only model profile readiness from profile manifest validity, managed execution capability, provider gateway support, package availability, and provider secret env presence.
- Evaluate read-only model execution readiness from active status, context capsule, model profile resolution, provider gateway support, package availability, and provider secret env presence.
- Evaluate provider-secret permission separately from secret presence: managed model calls must be allowed to `EnvVar(secret:use)` without exposing secret values through context, logs, or dashboards.
- Evaluate read-only worker readiness gates from active status, worker locks, task/member/assignment references, context capsule presence, model runtime prerequisites, provider secret env presence, git repository health, and planned branch.
- Report current API process runtime diagnostics, including PID, working directory, secret env exact-name presence, case-variant hints, profile references, and restart guidance without exposing secret values.
- Update run-level model profiles through explicit workspace mutations; clearing a model removes the manifest field, and dashboard/API model changes should rebuild the run context capsule.
- Execute minimal managed LLM runs and persist run status, events, and journal updates.
- Run worker verification commands with timeout, command events, `test.log`, and `command_results.jsonl` artifact recording.
- Record worker heartbeat metadata and reconcile expired active runs to `STALLED` without deleting worktrees or artifacts.
- Record worker attempt ids and run lock metadata so recovery can distinguish active ownership from stalled artifacts.
- Inspect recoverable worker runs, write `recovery_report.json`, write `retry_plan.json`, clear PID-proven stale locks, move reviewable recovered diffs to `REVIEW`, and retry stalled/failed/interrupted runs without deleting artifacts.
- Manage worker worktrees, assignment write-scope validation, patch application, local commits, PR target recording, and run locks.
- Create the strongest available review target: GitHub PR when branch push and `gh` succeed, otherwise a branch or commit target with a visible fallback note.
- Evaluate read-only review gates from run status, journals, review targets, local diffs, assignment write scope, local safety scans, worktree checks, command results, refreshed external PR checks, and linked review records.
- Refresh external PR check status into `runs/<run>/checks.json` using GitHub CLI when available, with warning-only fallbacks when unavailable.
- Write dashboard human reviews to `.aiteamos/reviews`, link them to runs/tasks, and let review gates interpret approval or changes-requested verdicts.
- Write TeamRetrospective manifests under `.aiteamos/im/retrospectives` and create linked pending MemoryProposal records for facilitator-reviewed team learning without approving memory.
- Derive read-only retrospective suggestions from runs, journals, messages, and handoffs so facilitators can review proposed team learning before creating durable retrospective or memory state.
- Normalize and explain permission actions for environment variables, connector subscopes, and artifact-store retention/redaction intent before worker, model, automation, or MCP execution.
- Attach local risk-classifier evidence to permission explanations and decision-audit records while preserving explicit allow/ask/deny as the enforcement authority.
- Append and index decision-audit records for permission requests/grants, reviews, and automation runs so approval authority and policy enforcement stay distinguishable.
- Create Automation configuration manifests and execute queued AutomationRun control-plane records after a second non-interactive permission check, creating only audited messages, connector-failure reminders, draft task plans, or linked Task/Run manifests without invoking worker code.
- Archive stale ConnectorHealthCheck and AutomationProviderDelivery manifests in place with lifecycle metadata and decision audit while preserving replay and incident-review evidence.
- Derive connector failure reminder candidates from connector health/provider delivery evidence and route them manually or through `connector_failure_reminder` automations to bounded, throttled, audited MemberMessage records without mutating connector or automation state.
- Derive GitActivity correlation promotion candidates from approved reviews and let `git_activity_correlation_promotion` automations promote only eligible service-policy groups through the normal queued AutomationRun executor.
- Execute `git_activity_retention_sweep` automations through ordinary AutomationRun records so scheduled GitActivity cleanup still uses service-member permission checks, optional approval gates, candidate limits, and the same lifecycle gate as manual retention sweeps.
- Create GitActivity retention sweep automations from dashboard/API controls with manual/daily/weekly/monthly scheduler presets, recommended approval gates, and initial dry-run evidence while keeping actual archive/redaction execution behind AutomationRun and per-activity lifecycle permissions.
- Project automation scheduler preset, latest lease, and latest run status into Project and Employee dashboard scopes from existing Automation control-plane records without writing projection manifests or changing scheduler/executor authority.
- Treat Project/Employee automation drilldown focus as dashboard-derived state only; assignment-scoped health filters read existing Automation, AutomationRun, and AutomationSchedulerLease records and never write workspace manifests.
- Treat dashboard URL query parameters as browser navigation state only. Restoring Project, Employee, or Automations focus from `page`, `project`, `member`, `automation`, `assignment`, or `source` must not validate as workspace state, write manifests, or affect scheduler, permission, memory, or worker authority.
- Derive repeated connector failure escalation candidates and route them explicitly to deduplicated `review-request` MemberMessage records when reminder throttling is no longer enough to keep diagnosis visible.
- Project connector escalation candidates and review-request messages into Knowledge Health, Project, Employee, Reviews, and Settings views while preserving one shared evidence chain.
- Resolve connector escalation review requests only through a checklist workflow that confirms linked evidence ids, reminder message ids, and optional permission or connector-policy follow-up before marking the MemberMessage resolved.
- Suppress duplicate connector escalation for already-reviewed evidence sets while exposing derived explanation fields for the latest resolved review request, reviewed evidence ids, unreviewed evidence ids, resolution actor/time, and newly routable evidence.
- Derive connector remediation suggestions from unsuppressed or newly re-routable escalation evidence, including proposed TaskPlan payloads, without writing task plans, tasks, runs, connector changes, permission grants, review closure, or memory state.
- Treat dashboard-staged remediation TaskPlan drafts as UI preview state only until a reviewed submit call writes a normal draft TaskPlan after evidence-freshness, permission, and required review-gate checks.
- Record connector remediation lineage and decision audit on submitted TaskPlans while still avoiding task/run creation, connector policy mutation, permission grants, review closure, or memory writes.
- Project submitted connector remediation TaskPlans as read-only derived rows across Tasks, Reviews, Project, Employee, Settings, and Home views using their shared `connectorRemediation` lineage and decision-audit fields.
- Accept connector remediation TaskPlans into ordinary Tasks only through a reviewed checklist that confirms evidence/review-request coverage and permission checks; acceptance remains idempotent and does not create runs or mutate connector, permission, automation, review, or memory policy.
- Project materialized connector remediation Tasks back to their source TaskPlan with queue status, launch readiness, latest run linkage, accepted/creating member provenance, and evidence lineage without creating runs or changing connector state.
- Launch materialized connector remediation Tasks into ordinary Runs only through a reviewed checklist that confirms evidence/review-request coverage, ready queue status, normal launch-plan readiness, and run-manifest write permission; launch uses the ordinary `create_run` path, records connector lineage on the Run, and does not start worker code or mutate connector, permission, automation, review, or memory policy.
- Project connector remediation Runs back to their source TaskPlan and Task with model readiness, worker readiness, worker authorization, denied permission actions, PermissionRequest/PermissionGrant outcome state, and next control-plane action fields without starting workers, executing services, or changing connector state.
- Create connector remediation PermissionRequests from denied Run actions only through the normal pending-request workflow; the request action does not approve grants, mutate permission policy, start workers, close connector reviews, or write memory. Approved, rejected, expired, revoked, and hard-deny-still-blocked outcomes are derived back onto the Run projection for retry planning.
- Create generic worker and AutomationRun PermissionRequests from denied permission decisions using the same ordinary request/grant protocol. Worker authorization and AutomationRun records project pending/approved/rejected requests plus active/expired/revoked grants while leaving unrelated blockers in place.
- Promote approved GitActivity correlation reviews into at most one durable GitActivity, linking all selected import receipts to the same activity and rejecting partial or cross-linked receipt groups so Project/Employee contribution projections do not double-count provider evidence.
- Archive or redact durable GitActivity evidence in place with lifecycle/export/redaction metadata and decision audit while preserving linked import receipts, correlation reviews, member activity projections, and project/employee drilldowns.
- Derive expired GitActivity retention candidates from `retainedUntil` and sweep them manually or through automation-owned scheduling via the same governed archive/redaction lifecycle path, with dry-run support and no deletion of receipts, reviews, memory, tasks, runs, permissions, or growth projections.
- Export sanitized workspace bundles with GitActivity-aware policy handling: `include`, `sanitize`, `manifest-only`, and `exclude` are enforced per activity, and archived/redacted GitActivity records cannot leak provider-facing refs, URLs, or external ids.
- Keep derived database/index/cache state rebuildable.
- Ingest assisted IDE or external review outputs into task, run, artifact, and memory proposal manifests with idempotent run events and `INGEST_INCOMPLETE` health reporting.

This package is the core bridge between protocol files and the UI/API product surface.
