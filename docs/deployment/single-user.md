# Single-User Deployment

Single-user deployment is the local-first shape for one operator running AITEAMOS against one embedded workspace. It is intended for development, personal automation, fixture replay, and private self-hosting on a trusted machine.

## Topology

- Run the API and dashboard from one checkout with `./aiteamos serve --workspace .aiteamos`.
- Keep `.aiteamos/` on a local filesystem path owned by the operator.
- Treat SQLite, vector chunks, dashboard caches, and generated indexes as derived state under `.aiteamos/indexes/`.
- Rebuild derived state with `./aiteamos workspace index --workspace .aiteamos` after manifest changes or checkout restore.
- Validate source manifests with `./aiteamos workspace validate --workspace .aiteamos` before starting long-lived work.

The `.aiteamos/` directory is the source of truth. Do not back up only SQLite or dashboard cache files; they are rebuildable projections.

## TLS

Local single-user mode may bind to `127.0.0.1` without TLS when the browser and API run on the same host. If the dashboard is exposed beyond loopback, terminate TLS before traffic reaches the AITEAMOS API. Self-signed certificates are acceptable only for private development hosts where the operator controls the trust store.

## Reverse Proxy

A reverse proxy is optional for loopback use. When used, it should:

- forward one public origin to the AITEAMOS API and dashboard;
- preserve `Host`, `X-Forwarded-Proto`, and request path headers;
- reject cleartext external traffic;
- avoid caching authenticated API responses.

Do not put `.aiteamos/` or derived index files behind static file serving.

## OAuth / SSO

OAuth and SSO are not required in single-user mode. The recommended local identity path is either:

- `open-local` for trusted loopback demos; or
- a `ProductUser` with `sessionTokenEnv` pointing to a local environment variable.

Raw login tokens, OAuth subjects, refresh tokens, and email addresses are not stored in `.aiteamos/`. Product identity maps to `TeamMember` through the ProductUser-to-TeamMember binding.

## Secret Store

Use process environment variables, a local OS keychain wrapper, or a developer secret manager that exports environment variables at process start. Workspace manifests may name secret environment variables such as `OPENAI_API_KEY`, but must not store secret values.

The local secret store can feed provider access through the same `EnvVar(NAME:use)` permission shape used by larger deployments.

Secrets must not enter prompts, logs, dashboard URL parameters, exports, SQLite indexes, vector chunks, or `.aiteamos/` manifests.

## Operational Guardrails

- All governance, permission policy, worker sandbox, secret handling, and production deploy changes remain review-first.
- Any `ask` permission decision in non-interactive execution resolves to deny.
- Dashboard URL state may contain `auth`, `workspace`, and `viewer`, but never token values.
- Local backups should include `.aiteamos/` manifests and reviewed artifacts; derived indexes can be regenerated.
