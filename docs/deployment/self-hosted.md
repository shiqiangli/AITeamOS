# Self-Hosted Deployment

Self-hosted deployment is for one organization or team operating its own AITEAMOS instance. It may support multiple product users and multiple workspaces, but the organization owns the runtime, reverse proxy, storage, and secret boundary.

## Topology

- Run the API and dashboard behind a single HTTPS origin.
- Mount each workspace as durable storage and keep `.aiteamos/` manifests as the source of truth.
- Store derived SQLite, vector chunks, and cache files on rebuildable volumes.
- Use `GET /workspaces` and workspace-scoped API paths such as `/workspaces/{wsId}/members` for multi-workspace routing.
- Prefer a stable service user for background automation, with all service permissions expressed as AITEAMOS permissions and ApprovalWorkflow records.

Backups must capture workspace manifests, reviewed artifacts, and object-store manifests. Derived databases and vector files may be rebuilt from `.aiteamos/`.

## TLS

Self-hosted deployments must serve browser traffic over TLS. TLS may terminate at a reverse proxy, load balancer, or ingress controller, but the public origin must be HTTPS. Configure:

- HSTS for production domains;
- secure cookies through `AITEAMOS_SESSION_COOKIE_SECURE=1`;
- `SameSite=Lax` or stricter unless an explicit cross-site embedding design is reviewed;
- trusted internal network paths between proxy and API.

## Reverse Proxy

Use a reverse proxy such as Nginx, Caddy, Envoy, Traefik, or a Kubernetes ingress. The proxy owns external routing and should:

- route dashboard and API paths to the AITEAMOS service;
- preserve `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and request id headers;
- enforce request body limits appropriate for assisted ingest and artifact metadata;
- disable response caching for session, governance, memory, and workspace APIs;
- apply rate limits to login, webhook, and provider-admission endpoints;
- keep `/metrics` access restricted to observability systems.

The proxy must not expose workspace files directly. All durable writes must pass through reviewed AITEAMOS APIs or CLI workflows.

## OAuth / SSO

Self-hosted teams may use local ProductUser tokens, OAuth, or SSO/OIDC. Regardless of provider, authentication resolves in two steps:

1. The product principal authenticates through the deployment auth layer.
2. A `ProductUser` manifest maps that principal to a durable `TeamMember`.

Store only safe metadata in `.aiteamos/`: identity provider label, hashed subject when needed, roles, status, and environment-variable references. Raw OAuth subjects, access tokens, refresh tokens, and id tokens remain outside workspace manifests.

## Secret Store

Use the host platform secret store: systemd environment files with restricted permissions, Kubernetes Secrets, Docker secrets, Vault, cloud secret managers, or an equivalent operator-managed store.

AITEAMOS manifests may reference secret names through fields such as `sessionTokenEnv`, `secretEnv`, or connector `secretRefs`. They must not contain secret values. Runtime components may use `EnvVar(NAME:use)` only when effective permissions allow opaque use; read/export/write of environment values are separate high-risk actions.

## Operational Guardrails

- Treat deployment configuration as review-first production infrastructure.
- Keep worker execution isolated from the reverse proxy and dashboard process.
- Log request ids, run ids, task ids, member ids, and workspace ids; do not log credentials, cookies, bearer tokens, raw webhook signatures, or raw provider payload secrets.
- Restore by replaying `.aiteamos/` manifests plus reviewed artifact storage, then rebuilding derived indexes.
