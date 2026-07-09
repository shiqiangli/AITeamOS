# AITeamOS

Version: 1.0.0

AITeamOS is a file-first, Ticket-flow-centered AI team operating system. It helps a human delegate work through Chat to Clara and AI Employees, then inspect the work through Tickets, employee ledgers, traceable assets, Settings, and System Status.

The current product is greenfield. It uses the AITeamOS model directly and does not keep legacy CRUD pages, old execution-configuration pages, or compatibility routes.

## What Works In 1.0

- Chat with Clara or a selected Employee.
- Clara can create local Tickets with an assignee, route work through assignee changes, request validation, and summarize progress.
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
       -> Kernel Commands
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
- `.aiteamos/memory/candidates.json`

Sensitive values are not written into these config files. API keys and passwords are provided through environment variables and checked from System Status.

## Quick Start

```bash
export AITEAMOS_NEO4J_PASSWORD="<choose-a-local-password>"
./scripts/dev-up.sh
```

`dev-up.sh` also exports `AITEAMOS_GRAPHITI_PASSWORD` from
`AITEAMOS_NEO4J_PASSWORD` when the Graphiti-specific env var is not already
set. If you reuse an existing Neo4j data volume, keep those password env vars
aligned with the password already stored in the volume, or reset/change the
Neo4j password before expecting the Docker healthcheck to pass.

The script prepares the local backend and dashboard, then starts:

- FastAPI: http://127.0.0.1:8000
- LangGraph Agent Server: http://127.0.0.1:2024
- Dashboard: http://127.0.0.1:5173

The local LangGraph server is started with `--allow-blocking` because the
current 1.0 implementation is intentionally file-backed under `.aiteamos`.
Set `AITEAMOS_WITH_LANGGRAPH=0` to skip the Agent Server during backend-only
debugging.

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

Manual LangGraph Agent Server start:

```bash
source .venv/bin/activate
langgraph dev --host 127.0.0.1 --port 2024 --no-reload --allow-blocking
```

Repeatable LangGraph Agent Server smoke:

```bash
source .venv/bin/activate
python scripts/langgraph_agent_server_ci_smoke.py --startup-timeout 120
python scripts/langgraph_agent_server_ci_smoke.py --startup-timeout 120 \
  --assistant-id aiteamos_workbench_approval_fixture \
  --thread-id agent-server-ci-smoke-approval-resume \
  --message "Trigger deterministic approval fixture" \
  --ticket-key ticket-agent-server-approval-resume \
  --seed-ticket \
  --expect-status needs_approval \
  --expect-current-node approval_interrupt \
  --expect-context-source "" \
  --expect-approval-ref approval-fixture-1 \
  --resume-approval-ref approval-fixture-1 \
  --expect-resume-status completed \
  --expect-resume-current-node final_response \
  --require-resume-ticket-report \
  --min-resume-asset-candidates 1 \
  --min-resume-linked-assets 1
python scripts/langgraph_agent_server_ci_smoke.py --startup-timeout 120 \
  --assistant-id aiteamos_workbench \
  --thread-id agent-server-ci-smoke-primary-approval-resume \
  --message "Implement code changes for ticket ticket-primary-approval-resume-smoke" \
  --ticket-key ticket-primary-approval-resume-smoke \
  --seed-ticket \
  --runtime-run-id run-primary-approval-resume-smoke \
  --expect-status needs_approval \
  --expect-current-node approval_interrupt \
  --expect-action implement_ticket \
  --expect-approval-ref approval-run-primary-approval-resume-smoke-1 \
  --resume-approval-ref approval-run-primary-approval-resume-smoke-1 \
  --review-resume-approval \
  --expect-resume-status completed \
  --expect-resume-current-node final_response \
  --require-resume-ticket-report \
  --min-resume-linked-assets 1
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

Plan v7 verification artifacts:

```bash
python scripts/plan_v7_ci_artifacts.py
python scripts/plan_v7_ci_artifacts.py --full --include-frontend
python scripts/plan_v7_ci_artifacts.py --include-agent-server-smoke
python scripts/plan_v7_ci_artifacts.py --include-agent-server-matrix-smoke
python scripts/plan_v7_ci_artifacts.py --production-readiness
AITEAMOS_LIVE_PROVIDER_DOGFOOD=1 python scripts/plan_v7_ci_artifacts.py --include-live-provider-dogfood --live-provider-executor-id codex_cli
python scripts/ticket_loop_queue_worker_smoke.py --workspace-dir /tmp/aiteamos-ticket-loop-worker-smoke
python scripts/plan_v7_artifact_summary.py
python scripts/plan_v7_artifact_summary.py --live-dogfood-max-age-hours 24
python scripts/plan_v7_artifact_summary.py --fail-on-latest-evidence-gaps --fail-on-retained-evidence-gaps
```

The script is a thin wrapper around existing pytest, LangGraph, dashboard, and
Agent Server smoke commands. The default checks include focused runtime approval
outcome contracts for reject, request-changes, and request-evidence paths, plus
Ticket loop queue reliability contracts for duplicate, stale-running,
provider-blocked, repeated-failure retrospective, worker-policy paths, and a
short-lived queue worker smoke that produces a governed failure retrospective
Asset candidate. They also include Asset provenance evidence for approved
AssetRecord relationship projection, idempotent Graphiti relationship replay,
and stale-memory cleanup. It writes a manifest plus stdout/stderr logs under
`.aiteamos/artifacts/plan_v7/<run-id>/`, so local dogfood and future CI can keep
the same evidence format without adding a custom runner.
Use `--production-readiness` for the strict local readiness profile. It expands
the backend contract coverage, includes the Agent Server matrix smoke, and ends
with `plan_v7_artifact_summary.py --fail-on-evidence-gaps`. It does not execute
live provider dogfood by itself; without a fresh retained live dogfood artifact,
the readiness profile should fail with an explicit evidence gap.
`plan_v7_artifact_summary.py` reads those saved manifests and prints a compact
operations summary for recent local or CI verification runs. The summary also
extracts first-class loop evidence when present: context retrieval recall and
excluded Graphiti hints, Employee work-history retrieval refs, approved Asset
relationship / stale cleanup evidence, multi-tick queue worker daemon health,
Runtime Replay coverage for Ticket / Employee / evidence / trace / checkpoint /
Asset-Memory refs, Agent Server matrix coverage for read-only, answer-only,
provider-blocker, approval resume, and approval review outcomes, and optional
environment/provider conformance status, live provider readiness, and dogfood
freshness. The environment smoke is read-only and surfaces Plane / Graphiti /
RuntimeExecutor setup blockers without mutating provider state. The summary
also exposes live readiness blocker details, setup requirements, and repo-write
RuntimeExecutor candidates. It keeps separate `latest_evidence_gaps` and
retained evidence gaps. Retained evidence keeps the latest complete Agent Server
matrix and a recent real dogfood artifact across later non-mutating runs, so a
lightweight run does not hide whether heavier production-compatible evidence is
still available.
Use `--fail-on-latest-evidence-gaps`, `--fail-on-retained-evidence-gaps`, or
`--fail-on-evidence-gaps` when this summary should act as a strict readiness
gate instead of a read-only operations report.
Readiness and dry-run outputs are non-mutating and do not satisfy live dogfood
completion; missing, stale, or non-completed dogfood evidence appears as
explicit gaps rather than being inferred from a green test run.
The live dogfood command is opt-in only: the artifact runner adds it only with
`--include-live-provider-dogfood`, and the dogfood script still requires
`AITEAMOS_LIVE_PROVIDER_DOGFOOD=1` before mutating provider state.

The GitHub Actions workflow in `.github/workflows/plan-v7-verification.yml`
runs the default artifact script on pushes and pull requests. `workflow_dispatch`
can opt into the broader backend suite, dashboard tests/build, local Agent
Server approval/resume smoke, the Agent Server matrix smoke, or the strict
production readiness profile. The matrix covers read-only, answer-only,
provider-blocker, approval/resume, and approval review outcomes for
evidence-requested, rejected, and changes-requested paths. The workflow
production readiness option does not execute live provider dogfood; it is
expected to fail with an explicit live dogfood evidence gap until a fresh
authorized dogfood artifact exists.

## Product Documents

- `PRODUCT_DIRECTION.md`: greenfield product direction.
- `PRODUCT_MODEL.md`: product model and entity relationships.
- `docs/PRD-core.md`: 1.0 product requirements.
- `docs/arch.md`: implementation architecture.
- `docs/USER_GUIDE.md`: Dashboard user guide.
