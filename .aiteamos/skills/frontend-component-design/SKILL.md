# frontend-component-design

> Design dense, operational Dashboard surfaces for AITeamOS.

## Use When

- Building or refining Dashboard pages and shared components.
- Creating list-first entity views, detail tabs, dialogs, or settings panels.
- Making provenance, status, and review state easier to inspect.

## Interaction Baseline

The app opens on Chat. Other pages are inspection, audit, configuration, or review surfaces.

```text
Chat
Tickets
Employees
Assets
Settings
System Status
```

## Component Rules

- Dense operational pages should be list-first.
- Use tabs for sibling detail views.
- Use right-side detail panels for selected list items.
- Use dialogs for full text, confirmation, or focused editing.
- Use icons in buttons where the action is familiar.
- Keep Settings quiet and form-focused.
- Keep System Status read-only.
- Avoid landing-page layout inside the app.

## Page Expectations

- Tickets: queue, owner, validator, next action, latest report, event timeline, asset graph hints.
- Employees: overview, work ledger, capabilities, governance, AI Engine.
- Assets: Knowledge, Capabilities, Review Queue, search, provenance, full-text read.
- Settings: AI Engines, Tool Connectors, Code Repositories, Ticket Backend, Memory Backend.

## Verification

- Text fits in compact panels on desktop and mobile.
- Loading and error states do not shift fixed-format controls.
- Tests cover expected labels, tabs, dialogs, and blocked states.
