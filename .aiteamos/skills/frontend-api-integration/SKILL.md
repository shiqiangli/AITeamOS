# frontend-api-integration

> Integrate the Dashboard with AITeamOS file-backed APIs using product-aligned TypeScript contracts.

## Use When

- Adding or changing frontend API client functions.
- Wiring a page to Chat, Tickets, Employees, Assets, Settings, or System Status APIs.
- Improving error handling for backend blockers.

## API Client Rules

- Put typed API functions under `apps/dashboard/src/api/`.
- Keep TypeScript interfaces aligned with Pydantic response fields.
- Use product names in function and type names.
- Route all requests through `apiRequest` so errors and base paths stay consistent.
- Show backend `detail` text when an operation is blocked.
- Do not expose secret values in UI models.

## Current API Areas

```text
chat.ts
tickets.ts
assets.ts
knowledge.ts
memory.ts
capabilities.ts
toolConnectors.ts
repositories.ts
systemStatus.ts
```

## Checklist

- New fields are optional only when the backend can omit them.
- Empty/loading/error states match the page workflow.
- Hash route parameters are encoded and decoded consistently.
- Detail panels close when category context changes.
- Tests cover the user-visible state, not only the fetch call.

## Verification

```bash
cd apps/dashboard
npm test -- --run
npm run build
```
