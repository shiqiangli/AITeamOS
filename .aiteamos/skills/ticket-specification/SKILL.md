# ticket-specification

> Specify AITeamOS Tickets with owner, validator, acceptance criteria, evidence, and asset expectations.

## Use When

- Clara needs to create or clarify a Ticket.
- A human goal is too broad and needs a traceable work unit.
- A Ticket needs enough structure for Employee ownership and PV validation.

## Ticket Fields

- title
- description and acceptance criteria
- namespace such as `rd`, `pv`, `arch`, `rel`, `mem`, `doc`, `ops`, or `trace`
- owner Employee or owner role
- validator Employee or validation role
- source thread and source run
- code repositories
- Knowledge, Memory, or Decision refs
- expected reports and evidence
- next expected action

## Specification Checklist

- The Ticket describes one accountable work unit.
- The Ticket has an owner Employee or owner role before it enters active flow.
- The owner can make progress without guessing the goal.
- The validator can tell pass from fail.
- Repository and Knowledge scope are bounded.
- Evidence expectations are explicit.
- High-risk or externally visible actions require human approval.
- Useful outputs can become Assets with provenance.

## Good Ticket Shape

```text
Title: Implement local Ticket event projection
Owner: AI RD / Implementer
Validator: AI PV
Acceptance: create/report/list flows pass backend tests
Evidence: pytest output and changed file list
Next action: owner implements, then PV validates
```

## Outputs

- Ticket title and description.
- Owner and validator recommendation.
- Acceptance criteria.
- Evidence checklist.
- Asset or Memory candidate expectations.
