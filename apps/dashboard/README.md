# AITeamOS Dashboard

React + Vite frontend for AITeamOS 1.0.

## Product Baseline

The Dashboard opens on Chat because Clara-led Ticket flow is the main operating loop. Tickets carry assignee, status, reports, evidence, validation, and generated assets; Employees are workforce records around those Tickets, not standalone agent cards.

## Stack

- React + TypeScript
- Vite
- Tailwind CSS
- Radix UI primitives
- lucide-react icons
- Vitest + Testing Library

## Routes

| Hash route | Page |
|---|---|
| `#/chat` | Clara and Employee Chat |
| `#/tickets` | Ticket cockpit and event ledger |
| `#/employees` | Employee workforce records |
| `#/assets` | All Assets |
| `#/assets/knowledge/docs` | Knowledge Docs |
| `#/assets/knowledge/memories` | Memories |
| `#/assets/knowledge/decisions` | Decisions |
| `#/assets/capabilities/skills` | Skills |
| `#/assets/capabilities/built-in-tools` | Built-in Tools |
| `#/assets/capabilities/mcp-tools` | MCP Tools |
| `#/assets/review` | Review Queue |
| `#/settings/ai-engines` | AI Engines |
| `#/settings/tool-connectors` | Tool Connectors |
| `#/settings/code-repositories` | Code Repositories |
| `#/settings/ticket-backend` | Ticket Backend |
| `#/settings/memory-backend` | Memory Backend |
| `#/system-status` | System Status |

## Run

```bash
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

The dev server proxies `/api/v1` to the FastAPI backend.

## Verify

```bash
npm test
npm run build
```
