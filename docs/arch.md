# AITeamOS Architecture

Version: 1.0.0

## 1. Architecture Principle

AITeamOS 1.0 runs on an external-backed base: Plane for Tickets and Graphiti for persistent asset recall. The architecture does not maintain a parallel local-file Ticket mode.

Inside AITeamOS, the domain object is always `Ticket`. Provider-native names from Plane or other external systems may appear in adapter metadata and external links, but API routes, Chat flows, Employee ledgers, Asset Graph projections, and analytics use AITeamOS Ticket terminology.

The system is organized around:

- Clara-led Chat
- Ticket event ledgers
- Employee work ledgers
- Assets with provenance
- Settings for operating conditions
- System Status for read-only health

There are no compatibility routes for old product names.

## 2. System Shape

```text
Dashboard
  -> FastAPI /api/v1
      -> Chat service
      -> Ticket service
      -> Knowledge / Memory / Asset Graph service
      -> Capability service
      -> Repository service
      -> Tool Connector service
      -> System Status service
  -> .aiteamos local files for config, traces, and audit mirrors
```

The Dashboard is a React/Vite application. The API is FastAPI with Pydantic models. Plane and Graphiti are the target persistence base. Local files are only configuration, traces, and audit mirrors; they are not the Ticket backend.

## 3. Local Config And Audit Mirror Layout

```text
.aiteamos/
  employees/
    clara.yaml
    alex.yaml
    peter.yaml
  threads/
    index.json
  conversations/
    <thread_id>.jsonl
  traces/
    <run_id>.jsonl
  ai_engines.json
  runtime_executors.json
  engine_threads.json
  code_repositories.json
  tool_connectors.json
  memory/
    candidates.json
    approved.json
    graphiti_state.json
  graphiti.json
```

Historical conversations and traces are append-only audit records. Current configuration files may be rewritten by Settings or Kernel Commands. Ticket state is not stored here as a local backend; it is accessed through the Plane-backed TicketAdapter and projected into AITeamOS Ticket facts.

## 4. Services

Chat service:

- loads Employees, Skills, approved Memory snippets, and Knowledge snippets
- selects Clara or the requested Employee
- selects the effective AI Engine
- invokes Kernel Commands or remote AI Engine calls
- answers self-bootstrap learning summaries from the TicketService read model through a read-only Kernel Command
- persists conversation, trace events, run metadata, and engine thread state

Ticket service:

- owns `TicketAdapter`
- maps Plane provider-native records into AITeamOS Tickets
- enforces an assignee for active Tickets
- reconstructs AITeamOS Ticket state from Plane sync plus AITeamOS Ticket events
- exposes Ticket events, Employee work ledger, Ticket assets, backend settings, and backend status
- exposes rebuildable Ticket, Employee, and Asset graph projections for provenance edges across Tickets, Employees, reports, evidence, repositories, and recalled assets
- exposes Phase 4a Employee analytics derived from Ticket, report, event, and asset graph facts
- exposes Ticket performance projections for contribution and quality signals derived from the same rebuildable facts
- exposes Ticket evidence requirement checklists and blocks validation pass records when required evidence is missing

Capability service:

- exposes Kernel Commands
- reads Tool Connector capabilities
- normalizes tools into capability records for Assets and Employee details

Repository service:

- stores Code Repository settings
- validates local paths lightly
- supports local bounded inspection for evidence

Knowledge / Memory / Asset Graph service:

- stores local approved memories and candidates
- stores or indexes durable asset projection metadata
- exposes Memory / Asset Graph Backend settings and status
- lets Graphiti choose a compatible AI Engine for LLM usage
- writes approved persistent assets to Graphiti when configured
- projects durable asset relationship facts such as supersedes, conflicts_with, derived_from, used_by, and validated_by to Graphiti with provenance
- projects ready Capability summaries to Graphiti without raw tool logs, secret settings, or permission authority
- writes validated durable assets such as Ticket summaries to Graphiti with AITeamOS provenance
- projects accepted Decisions to Graphiti as durable assets with AITeamOS provenance
- projects approved Doc summaries to Graphiti as durable assets with AITeamOS provenance
- projects approved Employee profile summaries to Graphiti as durable assets without raw permission authority
- projects approved Skill summaries to Graphiti as durable assets with AITeamOS provenance
- projects validated Ticket report and evidence summaries to Graphiti from Plane-backed Ticket facts
- keeps Graphiti search results linked back to AITeamOS asset, Ticket, run, report, and evidence refs

Runtime executor approval records:

- are created from `ExecutionResult.approval_requests`
- read non-sensitive adapter configuration from `.aiteamos/runtime_executors.json`, while API keys and tokens remain environment variables only
- preserve source ExecutionRequest / ExecutionResult provenance
- are listed, reviewed, and approved-run through `/api/v1/runtime-executors/{executor_id}/approvals`
- appear in the existing Assets Review Queue alongside memory, decision, skill, and tool candidates
- keep external repo mutation approval inside AITeamOS governance instead of a separate agent console

System Status service:

- aggregates AI Engine, Tool Connector, Ticket Backend, Memory / Asset Graph Backend, capability, and secret health
- returns read-only status only

## 5. Ticket Event Ledger

AITeamOS Ticket events are the internal work ledger projection over Plane-backed Tickets. Plane owns the external Ticket record; AITeamOS owns AI-team events, reports, evidence, validation, handoff, and asset provenance.

Required event shape:

```json
{
  "event_id": "evt-...",
  "ticket_id": "rd-0001",
  "type": "created",
  "at": "2026-06-04T00:00:00Z",
  "actor": { "id": "clara", "role": "AI Team OS Manager" },
  "data": {}
}
```

The Plane-backed TicketAdapter must support:

- namespace sequence allocation
- role-based namespace authority
- assignment events for created Tickets and later handoffs
- event append
- state projection
- report append
- asset projection
- employee work projection

## 5.1 Persistent Asset Graph Projection

Graphiti is the selected persistent asset temporal knowledge graph projection. It is not the authoritative store for the work ledger.

AITeamOS owns these authoritative facts:

- Ticket events
- Employee work ledger projections
- reports, evidence, validations, and handoffs
- local traces and run metadata
- Review Queue state
- permission and approval policy
- source docs, skill files, connector configuration, and secrets references

Graphiti may ingest durable asset facts after approval or validation:

- approved Memories
- accepted Decisions
- Docs or Doc summaries
- Skills and Skill summaries
- Kernel Commands, MCP Tools, and durable capability facts
- validated Ticket summaries
- validated Report or Evidence summaries
- durable Employee profile facts
- asset `supersedes`, `conflicts_with`, `derived_from`, `used_by`, and `validated_by` relationships

Graphiti must not ingest raw temporary streams by default:

- every chat turn
- every Ticket event
- every trace line
- raw terminal output
- raw tool-call logs
- unapproved or rejected candidates
- API keys, passwords, or secret values
- permission policy as executable authority

Every Graphiti episode or fact written by AITeamOS must include enough provenance to round-trip back to the local or external fact source: `asset_id`, `asset_type`, status, version/hash, source Ticket, source Employee, source run/trace, report/evidence refs when available, scope, timestamps, and source ref.

## 6. Employee Work Ledger

The Employee work ledger is a read model derived from Tickets. It should not be manually edited.

Fields:

- current Tickets
- historical Tickets
- reports
- validations
- blocked records
- handoffs
- contribution counters

This keeps Employee detail auditable and prevents the UI from reducing Employees to personas or chat activity.

## 7. AI Engine Boundary

AI Engine is the product and code term for model API, local model, or agent platform execution backend.

Configuration:

- `.aiteamos/ai_engines.json`
- API: `/api/v1/chat/ai-engines`
- Employee default API: `/api/v1/chat/employees/{employee_id}/ai-engine`
- current engine thread state: `.aiteamos/engine_threads.json`

Sensitive values are referenced by environment variable name and checked by System Status.

## 8. API Naming

Current API surfaces:

- `/api/v1/chat`
- `/api/v1/employees/{employee_id}/graph`
- `/api/v1/employees/{employee_id}/analytics`
- `/api/v1/employees/analytics/summary`
- `/api/v1/tickets`
- `/api/v1/tickets/{ticket_id}/assets`
- `/api/v1/tickets/{ticket_id}/evidence-requirements`
- `/api/v1/tickets/{ticket_id}/graph`
- `/api/v1/tickets/{ticket_id}/performance`
- `/api/v1/tickets/self-bootstrap/summary`
- `/api/v1/assets`
- `/api/v1/assets/{asset_id}/graph`
- `/api/v1/asset-graph/status`
- `/api/v1/capabilities`
- `/api/v1/knowledge`
- `/api/v1/memory/graphiti/asset-relationships`
- `/api/v1/memory`
- `/api/v1/memory/graphiti/capabilities/durable-assets`
- `/api/v1/memory/graphiti/capabilities/{capability_id}/durable-asset`
- `/api/v1/memory/graphiti/durable-assets`
- `/api/v1/memory/graphiti/decisions/durable-assets`
- `/api/v1/memory/graphiti/decisions/{decision_id}/durable-asset`
- `/api/v1/memory/graphiti/docs/durable-assets`
- `/api/v1/memory/graphiti/docs/{doc_id}/durable-asset`
- `/api/v1/memory/graphiti/employees/durable-assets`
- `/api/v1/memory/graphiti/employees/{employee_id}/durable-asset`
- `/api/v1/memory/graphiti/skills/durable-assets`
- `/api/v1/memory/graphiti/skills/{skill_id}/durable-asset`
- `/api/v1/memory/graphiti/tickets/{ticket_id}/durable-assets`
- `/api/v1/repositories`
- `/api/v1/runtime-executors/{executor_id}/smoke`
- `/api/v1/runtime-executors/{executor_id}/approvals`
- `/api/v1/runtime-executors/{executor_id}/approvals/{approval_id}/review`
- `/api/v1/runtime-executors/{executor_id}/approvals/{approval_id}/run`
- `/api/v1/tool-connectors`
- `/api/v1/system-status`

Removed concepts must not keep compatibility endpoints.

## 9. Verification

Backend verification:

```bash
pytest
```

Dashboard verification:

```bash
cd apps/dashboard
npm test
npm run build
```

Useful focused checks:

```bash
pytest tests/test_file_chat_routes.py tests/test_file_knowledge_and_tickets.py tests/test_file_memory_routes.py tests/test_file_system_status_routes.py
cd apps/dashboard && npm test -- --run src/__tests__/employees-page.test.tsx src/__tests__/settings-page.test.tsx src/__tests__/system-status-page.test.tsx
```
