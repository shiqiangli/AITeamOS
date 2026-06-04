# test-engineering

> Verify AITeamOS file-backed backend behavior, Dashboard workflows, and traceable work facts.

## Use When

- Adding or changing backend routes, frontend pages, local file projections, or Chat tools.
- Proving Tickets, Employees, Assets, Settings, Memory, or System Status still behave coherently.
- Turning a bug or regression into validation evidence.

## Test Baseline

Backend:

```bash
pytest
```

Dashboard:

```bash
cd apps/dashboard
npm test -- --run
npm run build
```

## Coverage Checklist

- Ticket creation writes append-only events and reconstructs current state.
- Ticket reports create Employee ledger entries and asset records.
- Employee detail shows work ledger, capabilities, governance, and AI Engine state.
- Assets search and detail panels expose provenance and full text where available.
- Settings saves non-sensitive config only.
- System Status shows secret health without returning secret values.
- Chat tool traces include selected Employee, AI Engine, Ticket keys, and saved paths.
- API 4xx blockers surface useful `detail` text to the UI.

## Evidence Standard

Every validation report should include:

- command or test name
- pass/fail result
- relevant file or route
- saved artifact or trace path when available
- residual risk if the check is partial
