# AITeamOS Core PRD

Version: 1.0.0
Status: Active greenfield requirements

## 1. Product Goal

AITeamOS 1.0 should let a human give work to Clara, have Clara create and move Tickets, delegate to Employees, collect reports and validation, and show all work as traceable records.

The product is Ticket-first and Employee-led. It does not introduce a separate user-visible work module outside Tickets.

## 2. Primary Users

- Human operator: delegates goals, approves high-risk work, reviews summaries.
- Clara: AI Team OS Manager, creates and routes Tickets, requests reports and validation, summarizes work.
- AI Employees: execute or validate bounded work and write evidence back to Tickets.

## 3. Core Entities

Ticket:

- stable id using namespace sequence such as `rd-0001`, `pv-0001`, `arch-0001`
- title, description, status, assignee, validator, source thread, code repositories, knowledge refs
- append-only events
- reports and evidence

TicketEvent:

- `created`
- `assigned`
- `status_changed`
- `reported`
- `validated`
- `blocked`
- `asset_linked`
- validation and handoff events as needed

Employee:

- identity, role, summary, responsibilities
- skills
- AI Engine mode and default engine
- permissions and governance boundary
- work ledger derived from Tickets

Asset:

- kind, title, status
- source Ticket
- source Employee
- scopes and assigned Employees
- created and updated time
- metadata and full-text view where possible

AI Engine:

- catalog id, display name, kind, support status
- non-sensitive config fields
- secret environment variable references
- per-Employee default selection

## 4. Functional Requirements

### Chat

- User can chat with Clara by default.
- User can select or route to a specific Employee.
- User can bind a message to a Ticket key.
- Chat response must persist conversation, trace, run metadata, and AI Engine thread id.
- Chat trace must expose selected Employee, selected AI Engine, loaded context, tool calls, and saved paths.

### Tickets

- Clara can create local Tickets.
- Namespace creation rules must be enforced:
  - Clara / manager can create any namespace.
  - RD can create `rd-*`.
  - PV can create `pv-*`.
  - Architect can create `arch-*`.
- Local backend stores one append-only JSONL timeline per Ticket.
- The current Ticket state is reconstructed from events.
- Ticket events must be queryable.
- Ticket reports must support content, report type, reporter Employee, evidence, and created time.
- Reports and evidence should create traceable asset records.

### Employees

- Employee list must be searchable and filterable.
- Home/list view must not present Employees as just chat personas.
- Employee detail must show:
  - Overview
  - Work Ledger
  - Capabilities
  - Governance
  - AI Engine
- Work Ledger must be Ticket-centered:
  - current Tickets
  - historical Tickets
  - reports
  - PV validations
  - blocked or failed records
  - handoffs
  - contribution counters
- AI Engine tab must allow selecting or typing the Employee default AI Engine.

### Assets

- Top-level `Assets` page must include a search box across all assets.
- Assets must be organized as:
  - Knowledge: Docs, Memories, Decisions
  - Capabilities: Skills, Built-in Tools, MCP Tools
  - Review Queue
- Selecting an asset must show a right-side detail panel.
- Full text must be available in a read-only dialog for docs, skills, review items, reports, and evidence where content exists.
- Switching asset category must close the stale detail panel.

### Settings

Settings order:

1. AI Engines
2. Tool Connectors
3. Code Repositories
4. Ticket Backend
5. Memory Backend

Settings must not contain System Status or Secrets Health as child pages.

### System Status

- System Status is a top-level navigation item after Settings.
- Page title is `System Status`.
- It is read-only.
- It shows:
  - System Summary
  - Secrets Health
- Secrets Health shows required environment variables, purpose, configured state, and how to configure.

## 5. Non-Functional Requirements

- File-first P0 must remain inspectable and easy to diff.
- No compatibility routes for renamed product concepts.
- API and frontend naming must stay aligned with product terms.
- Sensitive values must not be stored in JSON/YAML config or returned to the frontend.
- UI should be list-first for dense operational pages.
- User-facing errors should explain blockers instead of leaking raw transport details.

## 6. 1.0 Acceptance

1. User can open Chat and ask Clara to create or move work.
2. Ticket backend writes lifecycle events and exposes a current state.
3. Employee detail shows a useful workforce record derived from Tickets.
4. Assets exposes traceable Knowledge, Capabilities, and Review Queue views.
5. Settings pages use the same names as backend APIs and local files.
6. System Status is top-level and read-only.
7. `pytest`, dashboard tests, and dashboard build pass.

## 7. Next Requirements After 1.0

- Ticket Asset Graph with explicit edges:
  `Ticket -> Employee -> Report -> Evidence -> Decision / MemoryCandidate / Doc / Repo`
- richer validation skills for PV flow
- Graphiti-backed Memory in the operating loop
- Plane Ticket Backend adapter
- deeper AI Engine handoff to agent platforms for repo edit and long-running execution
