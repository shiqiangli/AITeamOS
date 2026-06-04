# AITeamOS Architecture

Version: 1.0.0

## 1. Architecture Principle

AITeamOS 1.0 is a file-first greenfield system for Clara-led Ticket flow. The architecture favors inspectable local facts over premature platform infrastructure.

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
      -> Knowledge / Memory service
      -> Capability service
      -> Repository service
      -> Tool Connector service
      -> System Status service
  -> .aiteamos local files
```

The Dashboard is a React/Vite application. The API is FastAPI with Pydantic models. The local file layer is the P0 persistence boundary.

## 3. Local File Layout

```text
.aiteamos/
  employees/
    clara.yaml
    alex.yaml
    peter.yaml
  tickets/
    index.json
    rd/
      rd-0001.ticket.jsonl
  threads/
    index.json
  conversations/
    <thread_id>.jsonl
  traces/
    <run_id>.jsonl
  ai_engines.json
  engine_threads.json
  code_repositories.json
  tool_connectors.json
  memory/
    candidates.json
```

Historical conversations and traces are append-only audit records. Current configuration files may be rewritten by Settings or Kernel Commands.

## 4. Services

Chat service:

- loads Employees, Skills, approved Memory snippets, and Knowledge snippets
- selects Clara or the requested Employee
- selects the effective AI Engine
- invokes Kernel Commands or remote AI Engine calls
- persists conversation, trace events, run metadata, and engine thread state

Ticket service:

- owns `TicketAdapter`
- implements local file backend
- enforces an assignee for active local Tickets
- reconstructs Ticket state from append-only events
- exposes Ticket events, Employee work ledger, Ticket assets, backend settings, and backend status

Capability service:

- exposes Kernel Commands
- reads Tool Connector capabilities
- normalizes tools into capability records for Assets and Employee details

Repository service:

- stores Code Repository settings
- validates local paths lightly
- supports local bounded inspection for evidence

Memory service:

- stores local approved memories and candidates
- exposes Memory Backend settings and status
- lets Graphiti choose a compatible AI Engine for LLM usage

System Status service:

- aggregates AI Engine, Tool Connector, Ticket Backend, Memory Backend, capability, and secret health
- returns read-only status only

## 5. Ticket Event Ledger

Each Ticket is one JSONL file. Every line is an event. Current state is a projection.

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

The local backend must support:

- namespace sequence allocation
- role-based namespace authority
- assignment events for created Tickets and later handoffs
- event append
- state projection
- report append
- asset projection
- employee work projection

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
- `/api/v1/tickets`
- `/api/v1/assets`
- `/api/v1/capabilities`
- `/api/v1/knowledge`
- `/api/v1/memory`
- `/api/v1/repositories`
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
