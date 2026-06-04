# architecture-review

> Review whether AITeamOS architecture and implementation stay aligned with the file-first, Ticket-flow-centered product model.

## Use When

- A change touches Chat, Tickets, Employees, Assets, Settings, System Status, or local file persistence.
- Product docs and code may have drifted.
- A new backend, connector, AI Engine, or asset flow is proposed.

## Review Baseline

AITeamOS 1.0 is file-first and greenfield. The current architecture is:

```text
Dashboard
  -> FastAPI /api/v1
      -> Chat
      -> Tickets
      -> Assets / Knowledge / Memory
      -> Capabilities / Tool Connectors
      -> Repositories
      -> Settings
      -> System Status
  -> .aiteamos local files
```

The core facts are Ticket events, Employee work ledgers, Assets with provenance, AI Engine configuration, and read-only system health.

## Review Checklist

- Product terms in UI, API, tests, and docs match: Chat, Tickets, Employees, Assets, Settings, System Status.
- Tickets are projected from append-only event files, not edited as loose records.
- Active Tickets have an assignee, and assignee changes are the Employee routing primitive.
- Employee detail is a workforce ledger, not only a persona/profile page.
- Assets expose provenance and review state when the source facts exist.
- Secrets are referenced by environment variable names and never stored in JSON config.
- Plane and Jira belong to Ticket Backend when used as Ticket fact sources.
- MCP Server is a Tool Connector kind; discovered tools are Capabilities / MCP Tools.
- System Status remains top-level and read-only.

## Outputs

- Findings ordered by severity with file and line references.
- Product-model drift notes.
- Missing test or acceptance coverage.
- Small, concrete follow-up changes.
