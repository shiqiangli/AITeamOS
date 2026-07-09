# AITeamOS Product Direction

Version: 1.0.0

AITeamOS is a Ticket-flow-centered AI team operating system. A human delegates work through Chat to Clara and AI Employees, while Tickets carry ownership, validation, reports, evidence, and reusable assets across the flow. Inside AITeamOS, the product concept is always `Ticket`; provider-native names only appear inside adapters, connector metadata, or external deep links.

This is a greenfield product direction. It does not preserve legacy CRUD modules, compatibility routes, or old execution-configuration naming.

## Product Thesis

The core object is not a chat transcript and not a generic project-management form. The core object is a traceable unit of work.

AITeamOS should answer five questions:

- What work was requested?
- Which Employee owned or validated it?
- What happened over time?
- Which evidence, reports, decisions, docs, skills, memories, or tools were produced or used?
- What should the human trust, review, or do next?

## Primary Model

The operating model is:

```text
Human
  -> Clara
  -> Ticket
  -> Employee work
  -> Report / Evidence
  -> Validation
  -> Asset / Memory candidate / Decision
  -> Human summary
```

Clara is the user-facing manager. Clara can create any Ticket namespace, delegate to Employees, request PV validation, summarize evidence, and point the human to reviewable records.

Employees are workforce records. They are not just personas or chat identities. Their detail view should expose mission, current Tickets, historical Tickets, reports, validations, blocked records, handoffs, skills, tools, knowledge scope, permissions, connector visibility, and default AI Engine.

Tickets are the accountability ledger. Every active Ticket has an assignee; changing assignee is the routing primitive between AI Employees. Every meaningful action should append a Ticket event such as `created`, `assigned`, `status_changed`, `reported`, `validated`, `blocked`, or `asset_linked`.

Assets are traceable reusable team resources. Assets include Knowledge, Skills, Kernel Commands, MCP Tools, Decisions, Reports, Evidence, and review candidates. Every asset should carry provenance where possible: source Ticket, source Employee, status, scopes, created time, updated time, and later Graphiti projection metadata when the asset is durable.

## Navigation

The 1.0 product navigation is:

```text
Chat
Tickets
Employees
Assets
  -> Knowledge
       -> Docs
       -> Memories
       -> Decisions
  -> Capabilities
       -> Skills
       -> Kernel Commands
       -> MCP Tools
  -> Review Queue
Settings
  -> AI Engines
  -> Tool Connectors
  -> Code Repositories
  -> Ticket Backend
  -> Memory / Asset Graph Backend
System Status
```

System Status is a top-level read-only entry. It shows system summary and secrets health. Secrets are not edited in the UI; sensitive values are provided through environment variables, while non-sensitive configuration lives in Settings.

## AI Engines

AI Engines are the execution backends used by Clara and Employees. The catalog can contain `llm_api`, `agent_platform`, and `local_model` engines, but all are presented as AI Engines in product and code.

Examples:

- DeepSeek, ChatGPT / OpenAI API, Gemini, Kimi, Ollama, LM Studio, vLLM
- Codex, Claude Code, Cursor, Qoder

Settings / AI Engines owns non-sensitive engine configuration, model selection, base URL, enabled status, and active engine. API keys are referenced by environment variable names and checked under System Status.

Chat may offer lightweight per-run AI Engine controls, such as model or reasoning depth, but full configuration belongs in Settings.

## Tool Connectors And Capabilities

Capabilities are executable or reusable ability assets. In Assets they are visible as:

- Skills
- Kernel Commands
- MCP Tools

Tool Connectors are Settings entries that make external tools discoverable. MCP Server is a `kind` of Tool Connector, not a parallel top-level concept. AITeamOS acts as host/client, discovers MCP tools/resources/prompts, normalizes them into capabilities, and applies permission and trace boundaries.

Plane configuration belongs to Ticket Backend because Plane serves as the external Ticket fact source. Plane provider-native records are mapped into AITeamOS Tickets at the adapter boundary. Plane executable actions may still appear as capability tools, but Plane configuration should not be duplicated under Tool Connectors.

## Backends

Ticket Backend:

- Plane is the required Ticket Backend for dogfooding and self-bootstrap.
- AITeamOS API, UI, Chat, Employee ledger, Asset Graph, and analytics always call the domain object `Ticket`.
- Provider-native names stay at the adapter boundary only.
- Local-file Ticket Backend is not a product path and should be removed from the target architecture instead of maintained as a parallel mode.
- Additional Ticket providers require a separate product decision and must map into the same AITeamOS Ticket contract.

Memory / Asset Graph Backend:

- Graphiti / Neo4j is the required persistent asset temporal knowledge graph projection.
- Graphiti should manage durable semantic relationships for approved Memories, accepted Decisions, Docs, Skills, Capabilities, Tooling facts, validated Ticket summaries, and durable Employee facts.
- Graphiti must not become the source of truth for Ticket events, traces, raw logs, approval state, permissions, or secrets.
- Graphiti LLM must select a compatible configured AI Engine rather than owning a separate LLM key path.

Code Repositories:

- Configured independently in Settings.
- Local repository inspection can attach bounded evidence to Tickets.
- Remote Git systems are stored as configuration until a connector or AI Engine can safely operate on them.

## 1.0 Scope

AITeamOS 1.0 should run on Plane for Tickets and Graphiti for persistent asset recall. The goal is not to preserve a parallel local-file mode; the goal is to make the real integration base coherent enough that every later feature is built and tested on it.

Included:

- Clara-led Chat workflow.
- AI Engine catalog and per-Employee default AI Engine.
- Plane-backed Ticket backend with AITeamOS Ticket event projection.
- Ticket-centered Employee work ledger.
- Assets UI with Knowledge, Capabilities, and Review Queue.
- Settings aligned with AI Engines, Tool Connectors, Code Repositories, Ticket Backend, and Memory / Asset Graph Backend.
- System Status as read-only summary and secrets health.

Not included as first-class 1.0 products:

- A user-visible work system separate from Tickets.
- Department / Project CRUD as primary navigation.
- A generic agent IDE or coding surface.
- A separate execution-configuration product layer outside AI Engines.
- Compatibility routes for renamed APIs.

## Direction After 1.0

The next product depth should continue from working facts:

- richer Ticket Asset Graph edges
- fuller validation skills and review flows
- broader Graphiti-backed persistent asset recall in the operating loop
- deeper Plane Ticket synchronization and provenance
- more capable AI Engine handoffs for repo edit, testing, and long-running execution

The product rule remains: add facts before adding more screens.
