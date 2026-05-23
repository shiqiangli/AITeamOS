# Context Capsule: RUN-20260520T104310792

## Task

Implement Track A: UI-first review loop.

## Role

Project role: `aiteamos/backend`.

## Required product loop

`.aiteamos` workspace files -> Pydantic schema -> workspace loader/indexer -> SQLite derived cache -> FastAPI API -> React dashboard -> dashboard write-back to `.aiteamos`.

## Constraints

- Do not implement Managed Worker, LiteLLM, or GitHub PR automation.
- Keep SQLite as derived state.
- Durable task and memory changes must write to `.aiteamos`.
- Keep CLI thin.

## Expected outputs

- Python schema package.
- Workspace loader/indexer package.
- FastAPI API service.
- React/Vite dashboard.
- Thin CLI.
- Smoke test and verification commands.
