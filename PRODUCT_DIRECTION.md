# AITeamOS Product Direction

Version: 1.0.0

AITeamOS is an AI-team operating system. It lets a human delegate work to Clara and a set of AI Employees, then inspect the work through Tickets, employee work records, assets, and system status.

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

Tickets are the accountability ledger. Every meaningful action should append a Ticket event such as `created`, `assigned`, `status_changed`, `reported`, `validated`, `blocked`, or `asset_linked`.

Assets are traceable reusable team resources. Assets include Knowledge, Skills, Built-in Tools, MCP Tools, Decisions, Reports, Evidence, and review candidates. Every asset should carry provenance where possible: source Ticket, source Employee, status, scopes, created time, and updated time.

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
       -> Built-in Tools
       -> MCP Tools
  -> Review Queue
Settings
  -> AI Engines
  -> Tool Connectors
  -> Code Repositories
  -> Ticket Backend
  -> Memory Backend
System Status
```

System Status is a top-level read-only entry. It shows system summary and secrets health. Secrets are not edited in the UI; sensitive values are provided through environment variables, while non-sensitive configuration lives in Settings.

## AI Engines

AI Engines are the execution backends used by Clara and Employees. The catalog can contain `llm_api`, `agent_platform`, and `local_model` engines, but all are presented as AI Engines in product and code.

Examples:

- DeepSeek, ChatGPT / OpenAI API, Gemini, Kimi, Ollama, LM Studio, vLLM
- Codex, Claude Code, Cursor, Qoder
- File stub for deterministic local development

Settings / AI Engines owns non-sensitive engine configuration, model selection, base URL, enabled status, and active engine. API keys are referenced by environment variable names and checked under System Status.

Chat may offer lightweight per-run AI Engine controls, such as model or reasoning depth, but full configuration belongs in Settings.

## Tool Connectors And Capabilities

Capabilities are executable or reusable ability assets. In Assets they are visible as:

- Skills
- Built-in Tools
- MCP Tools

Tool Connectors are Settings entries that make external tools discoverable. MCP Server is a `kind` of Tool Connector, not a parallel top-level concept. AITeamOS acts as host/client, discovers MCP tools/resources/prompts, normalizes them into capabilities, and applies permission and trace boundaries.

Plane or Jira configuration belongs to Ticket Backend when they serve as the Ticket fact source. Their executable actions may still appear as capability tools, but their primary configuration should not be duplicated under Tool Connectors.

## Backends

Ticket Backend:

- P0: local file, one append-only JSONL timeline per Ticket.
- Later: Plane as preferred external backend.
- Future: Jira only if enterprise integration requires it.

Memory Backend:

- P0: local approved memories and review candidates.
- Later: Graphiti / Neo4j for long-term memory graph.
- Graphiti LLM must select a compatible configured AI Engine rather than owning a separate LLM key path.

Code Repositories:

- Configured independently in Settings.
- P0 supports local repository inspection for bounded evidence.
- Remote Git systems are stored as configuration until a connector or AI Engine can safely operate on them.

## 1.0 Scope

AITeamOS 1.0 is allowed to be file-first. It should be coherent, inspectable, and useful before introducing heavier persistence.

Included:

- Clara-led Chat workflow.
- AI Engine catalog and per-Employee default AI Engine.
- Local Ticket backend with event ledger.
- Ticket-centered Employee work ledger.
- Assets UI with Knowledge, Capabilities, and Review Queue.
- Settings aligned with AI Engines, Tool Connectors, Code Repositories, Ticket Backend, and Memory Backend.
- System Status as read-only summary and secrets health.

Not included as first-class 1.0 products:

- A user-visible work system separate from Tickets.
- Department / Project CRUD as primary navigation.
- A generic agent IDE or coding workbench.
- A separate execution-configuration product layer outside AI Engines.
- Compatibility routes for renamed APIs.

## Direction After 1.0

The next product depth should continue from working facts:

- richer Ticket Asset Graph edges
- fuller validation skills and review flows
- Graphiti-backed Memory usage in the operating loop
- external Ticket Backend integration
- more capable AI Engine handoffs for repo edit, testing, and long-running execution

The product rule remains: add facts before adding more screens.
