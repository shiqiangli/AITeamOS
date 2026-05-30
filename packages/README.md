# Packages — Bounded Contexts

DDD bounded context packages. Each implements domain, application, infrastructure, and API layers.

## Structure

| Package | Bounded Context | Purpose |
|---------|----------------|---------|
| `knowledge` | Knowledge | Memory lifecycle: create, version, recall, governance |
| `capability` | Capability | Skill registration, health tracking, circuit breaker |
| `workforce` | Workforce | Member, Department, Project CRUD and assignment |
| `execution` | Execution | Task state machine, Run, Context assembly |
| `validation` | Validation | Harness adapter protocol, flaky detection |
| `governance` | Governance | Review case, Conflict case, resolution workflow |
| `shared_kernel` | Shared Kernel | Common types, Outbox, projection, LLM abstraction |

## Package Layout

Each bounded context follows:

```
aiteamos_{context}/
├── domain/         # Aggregates, value objects, invariants, events
├── application/    # Command handlers, query executors, consumers
├── infrastructure/ # Repository implementations, event publishers
├── api/            # (optional) Context-local ACL interfaces
└── __init__.py
```

## Rules

- Cross-context communication via domain events only
- No direct repository imports between packages
- All write operations emit events to Outbox
- Projection consumers must implement `IdempotentProjectionConsumer`
