# technical-decision

> Capture AITeamOS technical decisions as traceable Assets with clear consequences.

## Use When

- Choosing a backend, library, AI Engine, connector, storage shape, or API boundary.
- Recording why a product or architecture direction was accepted.
- Promoting a Ticket outcome into a Decision asset.

## Decision Baseline

Current accepted direction:

- AITeamOS 1.0 is greenfield and file-first.
- Clara is the user-facing manager.
- Tickets are the accountability ledger.
- Employees are workforce records.
- Assets carry provenance and review state.
- AI Engines cover LLM APIs, local models, and agent-platform handoffs.
- Tool Connectors make external capabilities discoverable.
- System Status is read-only and owns health visibility.

## Decision Template

```markdown
# Decision: <title>

## Status
Proposed | Accepted | Superseded

## Context
Which Ticket, product question, or implementation constraint triggered this?

## Decision
What are we choosing?

## Consequences
- Product effect:
- Implementation effect:
- Risks:
- Revisit trigger:

## Provenance
- Source Ticket:
- Source Employee:
- Evidence:
```

## Checklist

- Tie each decision to a Ticket or explicit source.
- State the rejected alternatives briefly.
- Name transition costs only as future risks, not current code paths.
- Add review state before treating the decision as reusable Knowledge.
