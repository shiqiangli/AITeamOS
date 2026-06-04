# AITeamOS Roadmap Plan

Version: 1.0.0 baseline
Planning date: 2026-06-04

## 0. Baseline

AITeamOS 1.0.0 is the current baseline.

Implemented baseline:

- Clara-led Chat can route work and persist conversations/traces.
- Local Ticket Backend stores append-only Ticket event ledgers.
- Employee detail is a workforce record with Work Ledger, Capabilities, Governance, and AI Engine configuration.
- Assets is unified around Knowledge, Capabilities, and Review Queue.
- Settings is aligned to AI Engines, Tool Connectors, Code Repositories, Ticket Backend, and Memory Backend.
- System Status is top-level and read-only.

Known product gap:

- Memory / Graphiti is not yet part of the active operating loop.
- Ticket Asset Graph is still implicit in event/report/asset records.
- Validation flow exists as report/event concepts, but not yet as a first-class skill-driven process.
- External Ticket Backend and AI Engine agent-platform handoff are modeled but not yet implemented deeply.

Planning principle:

Do not expand page shells first. Add working facts first, then expose them in UI.

## Milestone 1.0.1: Ticket Asset Graph MVP

Goal:

Make provenance visible as a graph of work facts, without introducing a graph database.

User value:

- A human can answer: "Which Employee created this evidence, from which Ticket, and what did it influence?"
- Clara can summarize contribution and provenance from structured edges instead of loose trace text.
- Assets page becomes an audit surface, not just an inventory.

Backend scope:

- Add a local file-backed `ticket_asset_graph` read model.
- Store graph edges derived from Ticket events, reports, evidence, assets, and repository evidence.
- Start with these edge types:
  - `ticket.assigned_to.employee`
  - `ticket.reported_by.employee`
  - `report.has_evidence`
  - `ticket.linked_asset`
  - `asset.source_ticket`
  - `asset.source_employee`
  - `report.proposes_memory_candidate`
  - `report.proposes_decision`
  - `ticket.references_code_repository`
- Add API endpoints:
  - `GET /api/v1/tickets/{ticket_id}/graph`
  - `GET /api/v1/employees/{employee_id}/graph`
  - `GET /api/v1/assets/{asset_id}/graph`
  - `GET /api/v1/asset-graph/status`
- Keep graph construction deterministic and reconstructable from local facts.

Frontend scope:

- Add graph sections in:
  - Ticket detail
  - Employee detail Work Ledger
  - Asset detail panel
- P0 graph UI can be a structured edge list with grouped nodes.
- Do not build a complex canvas visualization until edge quality is stable.

Acceptance:

- Creating a Ticket, adding a report, and linking evidence creates visible graph edges.
- Clicking a report/evidence asset shows source Ticket and source Employee.
- Employee contribution can be derived from graph edges and work ledger.
- Tests cover graph projection from existing Ticket events.

Out of scope:

- Graphiti ingestion for every Ticket event.
- Complex force-directed visual graph.
- Cross-workspace graph federation.

## Milestone 1.1: Validation Flow As Skills

Goal:

Make PV validation an explicit Clara-led and skill-backed flow.

User value:

- Clara can assign implementation to RD and validation to PV.
- Human can see whether a Ticket is awaiting validation, validated, blocked, or failed.
- Validation evidence becomes an asset with source Ticket and source Employee.

Backend scope:

- Add or formalize validation-oriented skills:
  - `pv-validation`
  - `evidence-review`
  - `regression-triage`
- Extend Ticket events:
  - `validation_requested`
  - `validation_started`
  - `validated`
  - `validation_failed`
  - `blocked`
- Add validation report types:
  - `validation`
  - `blocked`
  - `failed`
  - `needs_human`
- Add deterministic local tool behavior:
  - Clara requests validation for a Ticket.
  - PV records validation report and evidence.
  - Ticket status updates from validation outcome.
- Add policy hooks for later approval cards.

Frontend scope:

- Ticket detail shows validation stage, validator, latest validation report, and evidence.
- Employee Work Ledger separates reports from validations and blocked records.
- Assets Review Queue can show validation-derived candidates when they need approval.

Acceptance:

- A Ticket can move through RD report -> PV validation -> Clara summary.
- Validation reports appear in Employee Work Ledger and Ticket timeline.
- Validation evidence appears in Assets with provenance.
- Tests cover pass, fail, and blocked flows.

Out of scope:

- Full CI orchestration.
- External harness execution.
- Automated merge or destructive repo operations.

## Milestone 1.2: Memory / Graphiti Operating Loop

Goal:

Move Memory from passive local records into the Clara/Employee operating loop.

User value:

- Useful facts from Ticket flow can become Memory candidates.
- Approved memories can be recalled into future work.
- Graphiti becomes the long-term Memory backend without swallowing the entire Ticket graph.

Backend scope:

- Keep local Memory candidate review as the source of approval state.
- Add explicit Memory candidate links to Ticket reports and graph edges.
- Ingest approved memories into Graphiti when Memory Backend is configured.
- Use configured compatible AI Engine for Graphiti LLM usage.
- Add recall boundary:
  - query
  - employee
  - ticket
  - scopes
  - source trace
  - confidence
- Add APIs:
  - `POST /api/v1/memory/candidates/{id}/approve-and-ingest`
  - `GET /api/v1/memory/recall?ticket_id=&employee_id=&query=`
  - `GET /api/v1/memory/graphiti/status`

Frontend scope:

- Memory asset detail shows source Ticket, source Employee, approval state, and Graphiti ingestion state.
- Chat inspector shows which memories were recalled for a run.
- Settings / Memory Backend remains single-page and selects Graphiti LLM from AI Engines.

Acceptance:

- Ticket report can produce a Memory candidate.
- Approving candidate makes it available to recall.
- When Graphiti is configured, approved memory is ingested and status is visible.
- Chat run metadata shows recalled memory ids.

Out of scope:

- Auto-approval of long-term Memory.
- Writing all Ticket events into Graphiti.
- Replacing the local candidate review file.

## Milestone 1.3: Plane Ticket Backend Adapter

Goal:

Connect AITeamOS Tickets to a real external Ticket fact source while preserving the AITeamOS operating view.

User value:

- Teams can keep using Plane as their Ticket/Docs system.
- AITeamOS can still show AI-team ownership, reports, validation, and provenance.

Backend scope:

- Finalize `TicketAdapter` contract around:
  - list
  - get
  - append event/comment
  - assign
  - transition state
  - link evidence/asset
- Implement Plane adapter for a small slice:
  - read issues
  - create issue
  - add comment/report
  - transition state
  - map Plane ids to AITeamOS Ticket ids
- Keep local backend as development and offline backend.
- Store non-sensitive Plane settings in Ticket Backend config.
- Reference sensitive values through environment variables only.

Frontend scope:

- Ticket Backend page configures local / Plane / Jira modes.
- Ticket detail can show external deep link.
- System Status shows Plane secret and backend health.

Acceptance:

- Local backend tests still pass.
- Plane adapter can create and read a Ticket in a controlled test environment or mocked contract test.
- No duplicate Plane configuration exists under Tool Connectors.

Out of scope:

- Full Plane page editor.
- Full project planning UI.
- Jira implementation unless Plane path is stable.

## Milestone 1.4: AI Engine Agent-Platform Handoff

Goal:

Let selected Employees hand off deeper repo work to agent platforms while AITeamOS keeps control-plane trace and Ticket provenance.

User value:

- AITeamOS does not need to become an IDE.
- The human can still inspect which Employee requested what, what context was sent, and what came back.

Backend scope:

- Define AI Engine handoff contract:
  - engine id
  - employee id
  - ticket id
  - repository scope
  - allowed tools
  - context bundle
  - expected report schema
  - saved artifacts
- Add planned engine adapters in sequence:
  - Codex handoff
  - Claude Code handoff
  - Qoder handoff
  - Cursor handoff
- Start with non-destructive handoff:
  - ask external engine to inspect and report
  - import report/evidence into Ticket
- Store engine thread state in `.aiteamos/engine_threads.json`.

Frontend scope:

- Settings / AI Engines shows which agent-platform engines are configured or planned.
- Employee AI Engine tab can select an agent-platform engine as default once configured.
- Chat run inspector shows handoff context, artifacts, and imported report.

Acceptance:

- Handoff produces a Ticket report and trace event.
- AITeamOS stores no secret values.
- User can see context sent and evidence received.

Out of scope:

- Automatic repo edits without approval.
- Full terminal or IDE clone.
- Cross-engine orchestration planner.

## Milestone 1.5: Governance, Permissions, And Approval Cards

Goal:

Turn current visible governance data into enforceable boundaries.

User value:

- High-risk actions are explicit.
- Employees have auditable capabilities and connector visibility.
- Human approvals are attached to Ticket and trace facts.

Backend scope:

- Define permission checks for:
  - Ticket namespace creation
  - repository inspection
  - external connector use
  - Memory approval
  - destructive actions
- Add approval event types:
  - `approval_requested`
  - `approval_granted`
  - `approval_denied`
  - `approval_expired`
- Add approval record assets.
- Add policy hooks for Employee role, Ticket type, connector, and AI Engine.

Frontend scope:

- Chat shows approval cards for high-risk actions.
- Ticket timeline shows approval events.
- Employee Governance tab shows effective permissions and recent approval participation.
- System Status shows policy configuration health.

Acceptance:

- A high-risk tool can request approval and wait.
- Approval or denial is written to Ticket event ledger and trace.
- Employee detail shows permission-derived visibility.

Out of scope:

- Enterprise role-based access control.
- Multi-user auth and organization roles.

## Milestone 2.0: Productization And Multi-Workspace

Goal:

Move from local-first dogfooding to deployable team usage.

User value:

- A team can run AITeamOS with stable workspace boundaries, backups, and deployable services.

Backend scope:

- Workspace id and workspace settings.
- Auth boundary.
- Secret store integration option.
- Durable persistence option for non-local deployment.
- Backup/export/import for `.aiteamos` state.
- Observability for long-running AI Engine calls and connector health.

Frontend scope:

- Workspace switcher if needed.
- onboarding checklist
- setup diagnostics
- deployment docs

Acceptance:

- One local workspace and one deployed workspace can run with the same product model.
- Secrets never appear in exported files.
- Core 1.x flows still pass.

Out of scope:

- Multi-tenant billing.
- Marketplace.
- Public plugin ecosystem.

## Cross-Cutting Work

Every milestone must update:

- `PRODUCT_MODEL.md` only when the product model changes.
- `docs/PRD-core.md` when requirements change.
- `docs/arch.md` when API, persistence, or service boundaries change.
- `docs/USER_GUIDE.md` when user-facing workflow changes.
- tests for backend facts and frontend surfaces.

Every milestone must preserve:

- product/code naming consistency
- no compatibility routes for renamed concepts
- secrets through environment variables only
- local file inspectability where P0/P1 persistence remains local
- Ticket-first and Employee-work-ledger-first model

Recommended implementation rhythm:

1. Add or refine backend fact model.
2. Add projection/read API.
3. Add focused tests.
4. Expose in existing UI.
5. Update docs.
6. Run full verification.

## Immediate Next Slice

Start with Milestone 1.0.1.

Concrete first pull:

1. Add `TicketGraphEdge` model and local projection helper.
2. Project edges from existing Ticket events and reports.
3. Add `GET /api/v1/tickets/{ticket_id}/graph`.
4. Add a Ticket detail Graph section as grouped edge list.
5. Add tests using the existing RD -> report -> validation flow.

This gives the next visible product improvement while deepening the working facts instead of adding another shell page.
