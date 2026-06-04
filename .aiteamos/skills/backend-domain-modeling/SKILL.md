# backend-domain-modeling

> Model AITeamOS backend facts around Tickets, Employees, Assets, AI Engines, and local file provenance.

## Use When

- Defining a new persisted object or read model.
- Extending Ticket lifecycle events or Employee work ledgers.
- Deciding whether a concept belongs in Settings, System Status, Assets, or Ticket Backend.

## Core Objects

Ticket:

- work request, status, assignee / owner, validator, source thread, repositories, knowledge refs
- append-only events
- reports, evidence, and linked assets

TicketEvent:

- `created`, `assigned`, `status_changed`, `reported`, `validated`, `blocked`, `asset_linked`
- later validation and handoff event types as the flow deepens

Employee:

- identity, role, mission, Skills, permissions, knowledge scope, default AI Engine
- work ledger derived from Tickets

Asset:

- Knowledge, Memory, Decision, Skill, Capability, Report, Evidence, or review candidate
- provenance: source Ticket, source Employee, status, scope, timestamps

## Modeling Rules

- Add working facts before adding screens.
- Require active Tickets to have an assignee or assigned role.
- Make current state a projection where history matters.
- Keep configuration in Settings and health in System Status.
- Treat Plane/Jira as Ticket Backend options, not separate product models.
- Treat Graphiti as Memory backend, not the whole Ticket Asset Graph.
- Avoid generic abstractions until at least two concrete product paths need them.

## Outputs

- Object shape and file location.
- Event or provenance rules.
- Read-model projection notes.
- Tests that prove state can be reconstructed from local facts.
