# Context Capsule: RUN-0001

## Task

Write the initial AITEAMOS architecture into the repository and initialize an embedded `.aiteamos/` workspace for self-hosting.

## Role

Project role: `aiteamos/architect`.

Responsibilities:

- Define the AITEAMOS architecture.
- Protect the boundary between open-source core and workspace data.
- Design workspace protocol, memory, run logging, worker isolation, dashboard, API, CLI, MCP, and self-hosting governance.

## Key requirements

- Use Chinese for the architecture document.
- Use public self-hosting data and protocol fixtures as examples.
- Do not make the implementation route overly fragmented.
- Create `.aiteamos/` in `/home/shiqiangli/projects/aiteamos` so AITEAMOS can accumulate its own project experience.
- Keep large logs, raw provider responses, and artifacts out of Git by default.

## Expected outputs

- `docs/architecture.md`
- updated `README.md`
- embedded `.aiteamos/` workspace manifests
- run journal and memory proposal
