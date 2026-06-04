# AITeamOS Interaction Design

Version: 1.0.0

## 1. Interaction Thesis

AITeamOS should feel like a Ticket-flow operating surface for an AI team, not a CRUD admin console.

Chat is the main operation surface. Entity pages are inspection, audit, configuration, and review surfaces.

The user should be able to start with a natural-language request, then inspect the resulting facts without losing context.

## 2. Navigation

```text
Chat
Tickets
Employees
Assets
Settings
System Status
```

Default route opens Chat.

System Status is top-level and read-only. It is not a Settings subpage.

## 3. Chat

Chat supports:

- Clara as default Employee
- explicit Employee selection
- Ticket key binding
- current Ticket assignee visibility
- AI Engine visibility
- thread history
- run metadata
- trace events
- saved paths

Chat responses should include:

- concise result
- evidence or trace pointer
- next action
- deep links when inspection is useful

Chat should not become a full Settings editor or asset browser.

## 4. Tickets

Tickets is the work cockpit.

The page should prioritize:

- queue/state scanning
- assignee transitions and validator
- latest report
- event timeline
- evidence and linked assets
- backend status

Ticket details should make it clear what happened over time and who did the work.

## 5. Employees

Employees is a workforce record surface.

List view:

- dense list
- search
- role filter
- AI Engine filter
- current work signal
- skills and tool counts

Detail view:

- Overview
- Work Ledger
- Capabilities
- Governance
- AI Engine

Work Ledger must be Ticket-centered. Recent chat activity can appear as a communication signal, but it must not replace reports, validations, blocked records, handoffs, or contribution counters.

## 6. Assets

Assets is the unified asset entry.

Information architecture:

```text
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
```

Interaction rules:

- top search searches all assets
- selecting an item opens a right-side detail panel
- full text opens in a read-only dialog
- switching category closes stale detail state
- provenance should be visible whenever available

## 7. Settings

Settings is for operating conditions:

```text
AI Engines
Tool Connectors
Code Repositories
Ticket Backend
Memory Backend
```

Settings pages should use a stable summary + detail pattern:

- compact summary at top
- list or configuration content below
- one obvious add/configure entry
- destructive actions use confirmation
- secrets are referenced by environment variable name only

## 8. System Status

System Status is read-only.

The page should show:

- System Summary
- Secrets Health

Secrets Health should answer:

- what environment variable is required
- what it is used for
- whether it is configured
- where to configure it

It must not expose secret values.

## 9. Tool Result Pattern

Every local tool result should answer:

1. What happened.
2. What changed or was found.
3. Which Ticket, Employee, asset, or file was affected.
4. What evidence was saved.
5. What the next action is.

Deep links are expansion paths. The user should not be forced to leave Chat to understand the result.

## 10. Visual Rules

- Dense operational pages should be list-first.
- Avoid landing-page composition inside the app.
- Use tabs for sibling views.
- Use right-side details for selected list items.
- Use dialogs for full text or confirmation.
- Keep navigation names identical to product and API names.
- Avoid visible feature explanations inside the app; labels should describe the object or action.
