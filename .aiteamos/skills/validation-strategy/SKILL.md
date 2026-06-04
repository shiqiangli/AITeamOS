# validation-strategy

> Design PV validation flows that turn Employee reports into trustworthy Ticket evidence.

## Use When

- A Ticket needs independent validation.
- Clara must decide whether a report is enough to summarize to the human.
- Evidence, failure, blocked state, or review candidates need to be recorded.

## Validation Flow

```text
Owner Employee report
  -> Clara requests validation
  -> PV Employee reviews evidence
  -> PV records validation report
  -> Ticket status changes
  -> Assets receive evidence / report provenance
```

## Validation Checklist

- Name the validator Employee or validation role.
- Define pass, fail, blocked, and needs-human outcomes.
- Identify required evidence before validation starts.
- Record validation as a Ticket report with `report_type=validation`.
- Link logs, commands, screenshots, docs, or repository paths as evidence.
- If validation fails, record the reason and the next expected owner action.
- If validation is blocked, record who or what can unblock it.

## Evidence Types

- backend test output
- dashboard test output
- build output
- code review finding
- repository inspection result
- manual review note
- external Ticket Backend link

## Outputs

- PV validation plan.
- Ticket validation report.
- Evidence asset records.
- Follow-up Ticket status recommendation.
