# system-architecture-design

> Design AITeamOS system changes around the file-first 1.0 architecture and future Ticket Asset Graph depth.

## Use When

- Introducing a new service, adapter, read model, or local file.
- Deciding how product concepts map to API routes and Dashboard pages.
- Extending Memory, Ticket Backend, AI Engine, or Tool Connector boundaries.

## Architecture Baseline

```text
Dashboard
  -> FastAPI /api/v1
  -> .aiteamos local files
```

Current product surfaces:

- Chat for Clara-led operation.
- Tickets for work ledger and lifecycle events.
- Employees for workforce records.
- Assets for Knowledge, Capabilities, reports, evidence, and review candidates.
- Settings for AI Engines, Tool Connectors, Code Repositories, Ticket Backend, Memory Backend.
- System Status for read-only health and secrets state.

## Design Rules

- Keep the first implementation file-first and inspectable.
- Let docs lead implementation, but do not document a different product.
- Add structured facts before adding complex visualizations.
- Keep Ticket Asset Graph as a product read model before introducing graph infrastructure.
- Keep Graphiti scoped to approved long-term Memory.
- Keep sensitive values in environment variables.

## Outputs

- System shape diagram.
- Local file layout and API contract.
- Boundary decision for Settings vs System Status vs Assets.
- Verification plan with backend and dashboard tests.
