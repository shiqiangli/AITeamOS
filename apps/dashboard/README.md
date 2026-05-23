# AITEAMOS Dashboard

The dashboard is the first product surface for AITEAMOS.

The UX baseline for accessibility, responsive layout, focus treatment, state
handling, and theme behavior lives in `docs/dashboard/ux-baseline.md`.
Dashboard shell copy and shared surface labels are routed through
`src/i18n.ts`, with English as the default locale and Chinese as the required
second locale.

Dashboard responsibilities:

- Browse the embedded `.aiteamos` workspace.
- Show projects, repositories, employees, assignments, tasks, runs, journals, context capsules, model profiles, memory proposals, and approved memory.
- Show model profile readiness on the Model Profiles page before binding a profile to a member, assignment, or run.
- Create timestamp-based tasks.
- Assign tasks to TeamMembers with assignment context.
- Filter tasks by execution readiness, including missing member, missing assignment, missing model, active, stalled, review-ready, and done states.
- Show a run launch plan before creating a run, including selected member, assignment, mode, model profile, branch preview, blockers, warnings, and next actions.
- Jump to the newly created run and highlight the execution-plan-recommended actions.
- Bind members and assignments to default model profiles.
- Update task status through the review lifecycle.
- Inspect run journals and event ledgers.
- Show run execution plans that summarize blockers, warnings, artifacts, and next actions before assisted ingest, managed execution, recovery, or human review.
- Show model execution readiness before `Execute Model` and disable provider calls when model/context/runtime/secret prerequisites are blocked.
- Show worker readiness gates before managed worker start and disable worker buttons when model/context/runtime/lock prerequisites are blocked.
- Let reviewers set or clear a run-level model profile from Run Detail; saving the model updates `.aiteamos/runs` and rebuilds the context capsule.
- Disable execution, ingest, review, and memory extraction buttons when the run execution plan says the action is not currently appropriate.
- Rebuild and review deterministic context capsules and context manifests before managed or assisted execution.
- Drill into context source decisions, including included/excluded docs, code, memory, ACL/lifecycle/freshness/confidence/ranking, dedupe keys, budget buckets, and safe snippets.
- Ingest assisted IDE results with journal text, diff patch, test log, review target URL, and a pending memory proposal.
- Extract pending memory proposals from run journals, test logs, and failure events.
- Execute a managed LLM run and persist the model result to the run journal.
- Start a managed worker run that uses an isolated branch/worktree, optional verification commands, and can record a PR, branch, or commit review target.
- Show worker attempt ids and disable duplicate starts while a run is already active.
- Inspect worker recovery state, build a visible retry plan, clear PID-proven stale locks, move reviewable stalled runs to `REVIEW`, or retry recoverable worker runs from Run Detail.
- Display review target type, URL, ref, and fallback notes so local/manual review remains visible even when GitHub PR creation is unavailable.
- Display a read-only review gate with blockers, warnings, local safety checks, worktree checks, and review checks before human review.
- Refresh and display external PR check status when a PR review target is available.
- Record human approval or changes-requested reviews from Run Detail and write them back to `.aiteamos/reviews`.
- Show worker stage, heartbeat, lease, stalled status, and preserved command/test logs.
- Show runtime readiness for git, GitHub CLI, LiteLLM, and referenced provider secrets.
- Show current API process env diagnostics and secret restart guidance without exposing secret values.
- Edit pending memory proposals, approve or reject them with a visible promotion gate, and see promoted memory items.
- Filter proposal review queues by ready, warning, repairable, blocked, closed, member, assignment, and project.
- Apply pending-proposal repair hints for missing evidence, confidence, and review guidance before approval.
- Mark approved memory stale or re-verify it so stale lessons stop entering future context capsules.
- Edit approved-memory content and evidence; edited memory is held stale until it is verified again.
- Show an approved-memory audit trail for approvals, edits, stale marks, and verification.
- Review Knowledge Health for stale, low-confidence, missing-evidence, and sensitive-topic memory risks.
- Show decision-audit provenance for permission requests, grants, reviews, and automation runs so human approvals, digital recommendations, service policy decisions, and lifecycle checks are visibly different.
- Show Session Projection product-user identity and governance authority when the API maps a bearer token or hardened ProductUser cookie session to a `ProductUser`, keep non-admin product users locked to their mapped TeamMember viewer, rely on the API-managed environment-aware session cookie, and send `X-AITEAMOS-CSRF` on unsafe cookie-backed mutations.
- Show generic worker and AutomationRun permission request/outcome state in Runs and Automations views, expose request actions only as pending `PermissionRequest` creation, and keep the global Permissions page as the approval authority.
- Project generic worker and AutomationRun permission outcomes into Project and Employee detail views as read-only scoped governance evidence without duplicating the global approval queue.
- Show Assignment-scoped permission outcome drilldowns in Project Ownership Map and Employee Projects / Assignments views by grouping worker authorization, AutomationRun, PermissionRequest, and PermissionGrant records as read-only evidence.
- Project automation scheduler presets, latest scheduler leases, latest AutomationRuns, approval gates, and next control-plane action into Project and Employee detail views without acquiring leases, triggering runs, approving gates, or executing queued automations.
- Let Project and Employee automation projection rows open a scoped global Automations control-plane focus for the same automation/project/member/assignment while keeping all durable actions on the Automations page.
- Preserve selected Project, selected Employee, and scoped Automations focus in URL query state so reloads and shared links restore the same projection without writing workspace manifests.
- Store an optional browser-local Workspace API Base from Settings so one dashboard session can read from another already-running trusted AITEAMOS API process without changing `.aiteamos` manifests.
- Show member growth/performance projections as read-only support evidence from tasks, runs, reviews, memory proposals, messages, handoffs, retrospectives, and declared growth records without rankings or punitive scoring.
- Show Project and Employee Activity Sources plus Git Activity drilldowns from durable `MemberActivity`, `GitActivity`, `GitActivityImportReceipt`, and `GitActivityCorrelationReview` manifests, including import receipt dedupe/digest/redaction/review provenance before external Git evidence is treated as source-of-truth activity.
- Open/reload AutomationRun-created TaskPlan and Run outputs through first-level URL state, showing draft plan evidence, assisted ingest gates, or managed worker readiness even when aggregate lists are still catching up.
- Let Project Git Activity Imports admit a local Git scan into a `needs-review` receipt without creating GitActivity, so reviewers can inspect redaction/digest/dedupe evidence before promotion.
- Let Project Git Activity Imports admit GitHub/GitLab provider event metadata into the same reviewed receipt queue with payload digest, sanitized refs, hashed provider metadata, and no raw payload retention or pre-review GitActivity creation.
- Let Project Git Activity Imports explain connector Git import policy before admission, including repository/installation allowlists, protected refs, actor mapping, health requirements, blockers, and warnings.
- Show Project and Employee Git Activity Correlation Preview groups for PR/external id/ref/commit/payload digest signals, including force-push, squash/merge, and multi-event risk flags before any receipt is promoted.
- Let Project reviewers create `GitActivityCorrelationReview` manifests from correlation preview groups, then show those reviewed decisions in Project and Employee Git Activity views without promoting receipts or changing memory/growth state.
- Let Project reviewers promote an approved `GitActivityCorrelationReview` into a single durable GitActivity, linking all selected receipts to one activity and surfacing idempotent reuse when the group has already been promoted.
- Let reviewers promote a reviewed GitActivityImportReceipt into durable GitActivity from the Project Git Activity Imports panel without writing memory, grants, tasks, runs, or growth records.
- Show connector health/provider delivery evidence, route bounded connector failure reminders, escalate repeated connector failures into deduplicated review-request messages, project those review requests into Project, Employee, Reviews, Settings, and Knowledge Health views, resolve them only after linked evidence/reminder review, show suppression drilldown for resolved-evidence candidates, display read-only remediation suggestions, stage proposed TaskPlan previews into a local editable draft, explicitly submit reviewed drafts through the TaskPlan submit endpoint that re-checks permission and current evidence before writing `.aiteamos/task_plans`, project submitted remediation TaskPlans back into Tasks, Reviews, Project, Employee, Settings, and Home views, accept reviewed remediation TaskPlans into ordinary Tasks, show those materialized Tasks with source TaskPlan, queue status, and launch readiness, let reviewers create ordinary Runs for ready remediation Tasks without starting workers or mutating connector/permission/memory policy, project remediation Runs across Runs, Reviews, Project, Employee, Settings, and Home with model/worker/authorization blockers plus permission request/grant outcomes and the next control-plane action, and create pending PermissionRequests for denied remediation Run actions without approving grants.

The dashboard reads indexed state from the API. Any durable mutation must be written back to `.aiteamos` workspace files.

## Verification

- `npm run test:interaction` runs the jsdom product interaction harness.
- `npm run test:e2e` runs the Playwright browser harness. The ProductUser session, human assisted-ingest, demo task-planning, demo hybrid-assist, and demo digital-execution E2E harness starts a real API and Vite server against a temporary copy of `.aiteamos`, so it does not write demo workspace source data.
- The HTTPS ProductUser E2E path starts Vite with a temporary self-signed certificate, validates `Secure` / `SameSite=None` session cookies through the dashboard proxy, and proves cookie-backed ProductUser management sends CSRF instead of bearer tokens.
- The default supported local E2E browser subset is Chromium because it is the browser installed in the normal repo test environment. To run a broader browser matrix after installing Playwright browsers, set `AITEAMOS_E2E_BROWSER_PROJECTS=chromium,firefox,webkit` before `npm run test:e2e`.
