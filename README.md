# AITeamOS

Version: 1.0.0

AITeamOS is a file-first AI-team operating system. It helps a human delegate work to Clara and AI Employees, then inspect the work through Tickets, employee ledgers, traceable assets, Settings, and System Status.

The current product is greenfield. It uses the AITeamOS model directly and does not keep legacy CRUD pages, old execution-configuration pages, or compatibility routes.

## What Works In 1.0

- Chat with Clara or a selected Employee.
- Clara can create local Tickets, assign work, request validation, and summarize progress.
- Tickets are stored as append-only local event ledgers.
- Employee details show a workforce record: mission, current Tickets, historical Tickets, reports, validations, blocked records, handoffs, skills, tools, governance, and default AI Engine.
- Assets has a unified entry for Knowledge, Capabilities, and Review Queue.
- Settings owns AI Engines, Tool Connectors, Code Repositories, Ticket Backend, and Memory Backend.
- System Status is a top-level read-only page for system summary and secrets health.

Memory is present as local candidates and approved records, but the full Graphiti-backed operating loop is still the next product depth.

## Navigation

```text
Chat
Tickets
Employees
Assets
  -> Knowledge
       -> Docs
       -> Memories
       -> Decisions
  -> Capabilities
       -> Skills
       -> Built-in Tools
       -> MCP Tools
  -> Review Queue
Settings
  -> AI Engines
  -> Tool Connectors
  -> Code Repositories
  -> Ticket Backend
  -> Memory Backend
System Status
```

## Local Data

AITeamOS stores P0 state under `.aiteamos/`:

- `.aiteamos/employees/*.yaml`
- `.aiteamos/tickets/**/<ticket_id>.ticket.jsonl`
- `.aiteamos/threads/index.json`
- `.aiteamos/conversations/*.jsonl`
- `.aiteamos/traces/*.jsonl`
- `.aiteamos/ai_engines.json`
- `.aiteamos/engine_threads.json`
- `.aiteamos/code_repositories.json`
- `.aiteamos/tool_connectors.json`
- `.aiteamos/mcp_connectors.json`
- `.aiteamos/memory/candidates.json`

Sensitive values are not written into these config files. API keys and passwords are provided through environment variables and checked from System Status.

## Quick Start

```bash
./scripts/dev-up.sh
```

The script prepares the local backend and dashboard, then starts:

- FastAPI: http://127.0.0.1:8000
- Dashboard: http://127.0.0.1:5173

Manual frontend start:

```bash
cd apps/dashboard
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Manual backend start:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn aiteamos_api.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

## Configuration

AI Engines:

- Configure non-sensitive fields in `Settings / AI Engines`.
- Store sensitive values as environment variables such as `DEEPSEEK_API_KEY` and `OPENAI_API_KEY`.
- Select Employee defaults from the Employee detail page.

Memory Backend:

- Configure Graphiti / Neo4j in `Settings / Memory Backend`.
- Select the Graphiti LLM from compatible configured AI Engines.

Code Repositories:

- Configure local or remote repository records in `Settings / Code Repositories`.
- P0 can inspect configured local repositories and attach evidence to Ticket reports.

Ticket Backend:

- P0 uses local files.
- Plane and Jira are backend choices for future integration, not separate Ticket products inside AITeamOS.

## Testing

Backend:

```bash
pytest
```

Dashboard:

```bash
cd apps/dashboard
npm test
npm run build
```

## Product Documents

- `PRODUCT_DIRECTION.md`: greenfield product direction.
- `PRODUCT_MODEL.md`: product model and entity relationships.
- `docs/PRD-core.md`: 1.0 product requirements.
- `docs/arch.md`: implementation architecture.
- `docs/USER_GUIDE.md`: Dashboard user guide.
