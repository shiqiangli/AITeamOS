# Services

Runtime services that orchestrate the bounded contexts.

## Structure

| Service | Purpose |
|---------|---------|
| `api` | FastAPI gateway — CQRS read routes, write commands, middleware |
| `worker` | Background workers — Outbox relay, projection consumers |
| `saga` | Temporal workflow definitions and activities |

## API Service

The API service (`aiteamos_api`) is the single HTTP entry point:

- `read/` — Query routes (GET) backed by projection executors
- `command/` — Mutation routes (POST/PUT/PATCH) backed by command handlers
- `middleware/` — Auth, CORS, error handling
- `composition.py` — DI container and route registration

## Running

```bash
# API server
uvicorn aiteamos_api.main:create_app --factory --reload

# Worker
python -m aiteamos_worker

# Saga worker
python -m aiteamos_saga
```
