# Dashboard

React + Vite frontend for AITeamOS.

## Tech Stack

- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS + shadcn/ui components
- lucide-react icons

## Pages

| Route | Page | Description |
|-------|------|-------------|
| `#home` | Home | Summary stats, memory health, recent items |
| `#memories` | Memory | Memory CRUD, lifecycle, detail view |
| `#skills` | Skills | Skill registration, publish, deprecate |
| `#employees` | Employees | Employee creation, skill/memory assignment |
| `#departments` | Departments | Department management |
| `#projects` | Projects | Project CRUD, employee assignment |
| `#tasks` | Tasks | Task lifecycle, assignment, run history |
| `#reviews` | Reviews | Review queue, proposals, conflict resolution |
| `#metrics` | Metrics | Value metrics, system health, memory health |

## Running

```bash
npm install
npm run dev
```

API base URL: `http://localhost:5173` proxies to backend at `/api/v1`.
