# AITeamOS User Guide

Version: 1.0.0

This guide describes the current Dashboard experience.

## 1. Start Here

Open the Dashboard:

```text
http://localhost:5173
```

Use Chat first. Clara is the default manager and can create Tickets, route work, ask Employees for reports, request validation, and summarize the current state.

AITeamOS always calls the work object `Ticket`. Plane may use provider-native wording in external links or sync metadata, but inside AITeamOS the object remains a Ticket.

## 2. Navigation

```text
Chat
Tickets
Employees
Assets
Settings
System Status
```

Assets contains:

```text
Knowledge
  -> Docs
  -> Memories
  -> Decisions
Capabilities
  -> Skills
  -> Kernel Commands
  -> MCP Tools
Review Queue
```

Settings contains:

```text
AI Engines
Tool Connectors
Code Repositories
Ticket Backend
Memory / Asset Graph Backend
```

## 3. Chat

Use Chat to start work.

Typical flow:

1. Ask Clara to create or advance a Ticket.
2. Clara assigns the Ticket to an Employee; later assignee changes hand the Ticket to another Employee.
3. The Employee reports progress or evidence.
4. Clara requests PV validation when needed.
5. Clara summarizes the result for the human.

Chat records:

- selected Employee
- selected AI Engine
- thread id
- engine thread id
- Ticket keys
- tool calls
- trace path
- conversation path

## 4. Tickets

Tickets are the accountability ledger.

Use Tickets to inspect:

- Plane-backed Ticket records
- status
- assignee and validator
- reports
- evidence
- event timeline
- backend status

Ticket ids are namespaced. Examples:

- `rd-0001`
- `pv-0001`
- `arch-0001`

Only matching roles can create their namespace. Clara can create all namespaces.

Normal active Tickets have an assignee. If ownership changes, the assignee change is the work handoff.

## 5. Employees

Employees are workforce records.

The Employees page supports search and filtering. Click an Employee to open the detail panel.

Employee detail tabs:

- Overview: mission, current focus, identity boundary, communication signal, high-level metrics.
- Work Ledger: current Tickets, historical Tickets, reports, PV validations, blocked records, handoffs.
- Capabilities: assigned Skills, Kernel Commands, MCP Tools, other tool sources.
- Governance: knowledge scope, project access, permissions, connector visibility.
- AI Engine: effective engine, profile default, Settings active engine, default engine edit field.

Use AI Engine tab to set an Employee-specific default engine. Use `system` to follow Settings default.

## 6. Assets

Assets is the unified asset entry.

Use the top search box to search across assets. Use the first-level tabs for Knowledge, Capabilities, and Review Queue.

Selecting an asset opens a right-side detail panel. For docs, skills, review items, reports, and evidence, use the full-text action to open a read-only text dialog.

When you switch asset tabs, stale details close automatically.

## 7. Settings

Settings configures operating conditions.

AI Engines:

- select active engine
- configure supported engines such as File stub, DeepSeek, and OpenAI
- view planned engines such as Gemini, Kimi, Codex, Cursor, Qoder, and local model endpoints
- configure non-sensitive fields
- reference API key environment variables

Tool Connectors:

- configure external tool sources
- MCP Server is one connector kind
- connector tools appear as Assets / Capabilities / MCP Tools

Code Repositories:

- add local or remote repository records
- configure source kind, path or URL, branch, and enabled state
- local repository inspection can attach evidence to Ticket reports

Ticket Backend:

- configure Plane as the Ticket Backend
- map Plane provider-native records into AITeamOS Tickets
- keep Plane configuration under Ticket Backend, not Tool Connectors

Memory / Asset Graph Backend:

- configure Graphiti / Neo4j settings
- select Graphiti LLM from compatible AI Engines
- use Graphiti as the persistent asset knowledge graph projection for approved Memories, accepted Decisions, Docs, Skills, Capabilities, Tooling facts, validated Ticket summaries, and durable Employee facts
- keep temporary traces, raw logs, approval state, permissions, and secrets in AITeamOS instead of Graphiti

## 8. System Status

System Status is read-only and top-level.

It shows:

- System Summary
- Secrets Health

Secrets Health tells you which environment variables are required, what they are used for, whether they are configured, and how to configure them. It does not store or edit secret values.

## 9. Common Workflows

Create work:

1. Open Chat.
2. Ask Clara to create a Ticket with the goal, owner role, validator, and repository context.
3. Inspect the Ticket event timeline.
4. Inspect the assigned Employee Work Ledger.

Configure a real model:

1. Set `DEEPSEEK_API_KEY` or `OPENAI_API_KEY` in the environment.
2. Open System Status and confirm Secrets Health.
3. Open Settings / AI Engines and configure the engine.
4. Select an Employee default engine if needed.

Review assets:

1. Open Assets.
2. Search or choose Knowledge / Capabilities / Review Queue.
3. Select an item.
4. Open full text when available.
5. Use provenance fields to trace source Ticket and source Employee.

## 10. Limits In 1.0

- Plane and Graphiti are required base integrations for the target 1.0 operating loop.
- Agent platform engines are catalogued as planned unless a concrete adapter is implemented.
- Remote repository records are configurable; local inspection is the implemented evidence path.
