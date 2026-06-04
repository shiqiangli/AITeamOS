# employee-ticket-flow-design

> Design Clara and Employee collaboration around Tickets, Skills, Memory, Capabilities, and traceable Assets.

## Use When

- Clara needs to decide which Employee should own or validate a Ticket.
- A new Employee role, Skill assignment, or governance boundary is being designed.
- A Ticket flow needs a clear Clara -> Employee -> PV -> Clara collaboration shape.

## Current Model

```text
Human goal
  -> Clara
  -> Ticket
  -> Owner Employee
  -> Report / Evidence
  -> Validator Employee
  -> Asset / Memory / Decision candidate
  -> Clara summary
```

Clara is the user-facing manager and goal owner. Orchestrator behavior is a backend capability inside the flow, not a separate user-facing role.

Employees are workforce records. Their work is expressed through Ticket ownership, reports, validations, handoffs, blocked records, and contribution history.

Skills describe reusable ways of working. Memory and Knowledge describe what the team knows. Tool Connectors and Built-in Tools become Capabilities.

## Design Checklist

- Every delegated work item has a Ticket id, owner, expected evidence, and next action.
- The Ticket assignee is the routing anchor; changing assignee records the handoff.
- Each Employee has a clear mission, assigned Skills, knowledge scope, permissions, connector visibility, and default AI Engine.
- Validation is explicit when risk is high: name the validator, expected evidence, and pass/fail criteria.
- Handoffs add Ticket events instead of creating side channels.
- New Assets include source Ticket, source Employee, status, scope, and review state.

## Outputs

- Employee responsibility map.
- Skill and Capability assignment matrix.
- Clara routing rule for the Ticket flow.
- Validation and handoff notes for the Ticket event ledger.
