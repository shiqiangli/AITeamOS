# resource-planning

> Plan Employee, Skill, AI Engine, repository, and connector resources for Ticket flow.

## Use When

- Clara needs to decide who should own or validate work.
- A new Employee role or Skill assignment is being proposed.
- A Ticket needs repository, Knowledge, Tool Connector, or AI Engine context.

## Planning Inputs

- Ticket goal, acceptance criteria, risk, and deadline.
- Candidate owner Employee and validator Employee.
- Required Skills and Capabilities.
- Relevant Knowledge, Memory, Decisions, and repository scope.
- Effective AI Engine and secret health.
- Human approval needs for high-risk or externally visible actions.

## Checklist

- Assign one clear owner and, when needed, one clear validator.
- Treat that owner as the Ticket assignee and handoff target.
- Prefer the Employee whose mission and Skills match the Ticket evidence needs.
- Record repository scope before asking an Employee to inspect code.
- Keep connector access least-privilege and visible in governance notes.
- Use `system` default AI Engine unless the Employee needs a specific configured engine.
- Capture blockers as Ticket events or reports, not side notes.

## Outputs

- Owner and validator recommendation.
- Skill and Capability needs.
- Knowledge and repository scope.
- AI Engine and secret readiness.
- Next action for Clara to record on the Ticket.
