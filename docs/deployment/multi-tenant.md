# Multi-Tenant Deployment

Multi-tenant deployment is for an operator hosting AITEAMOS for multiple organizations, teams, or isolated workspaces. This mode raises the strongest requirements for tenancy isolation, identity, audit, and secret handling.

## Topology

- Route every browser and API request through an authenticated tenant context.
- Use workspace-scoped APIs such as `/workspaces/{wsId}/...`; unscoped compatibility routes are not sufficient for tenant isolation.
- Store each tenant workspace as an isolated `.aiteamos/` source of truth root or remote manifest backend namespace.
- Keep derived databases, vector indexes, object stores, and caches tenant-scoped and rebuildable.
- Isolate worker execution by tenant, workspace, and run.

A tenant must never read or infer another tenant's manifests, derived rows, vector chunks, secrets, artifacts, logs, or dashboard URL state.

## TLS

Multi-tenant deployments must enforce TLS at the public edge and should use managed certificate rotation. Configure:

- HSTS on tenant-facing domains;
- secure cookies for all authenticated sessions;
- strict origin and redirect URI allowlists;
- tenant-aware callback URLs for OAuth/OIDC providers;
- internal mTLS or equivalent authenticated service-to-service transport when crossing trust boundaries.

Plain HTTP is acceptable only for health checks on private loopback interfaces.

## Reverse Proxy

The reverse proxy, load balancer, or ingress tier is part of the tenant isolation boundary. It should:

- resolve tenant identity from hostname, path prefix, or authenticated routing metadata;
- forward tenant, workspace, request id, and scheme headers to the API;
- reject host-header confusion and cross-tenant path traversal;
- enforce upload limits, rate limits, and webhook replay windows per tenant;
- keep `/metrics`, tracing, and admin surfaces separate from tenant dashboards.

Proxy routing must not directly serve `.aiteamos/`, artifact blobs, derived SQLite, vector chunks, or generated dashboard caches.

## OAuth / SSO

Multi-tenant identity should use OAuth/OIDC or SSO with tenant-bound issuer, audience, and redirect configuration. The auth layer must bind a product principal to exactly one tenant context before resolving ProductUser and TeamMember records.

The durable identity rule remains the same:

- `ProductUser` represents the product account for a tenant.
- `TeamMember` remains the operational identity for work, permissions, memory, review, and audit.
- Raw provider subjects should be hashed or stored outside `.aiteamos/`.
- Access tokens, refresh tokens, id tokens, and session secrets are never workspace manifest data.

Cross-tenant user membership requires explicit ProductUser bindings in each tenant workspace; a shared email or SSO subject is not an operational identity by itself.

## Secret Store

Use a tenant-aware secret store such as Vault namespaces, cloud secret manager projects, Kubernetes namespaces, or another operator-controlled boundary with auditable access policy.

Requirements:

- secret values never appear in `.aiteamos/`, prompts, logs, exports, dashboard URL state, SQLite rows, vector chunks, or cached projections;
- secret references include tenant/workspace scope;
- managed workers may use provider secrets only through `EnvVar(NAME:use)` with effective permission checks;
- secret rotation should not require editing historical manifests;
- break-glass access must be review-gated and audited.

## Operational Guardrails

- Tenant isolation is a product primitive, not a best-effort filter.
- All production deploy changes, secret handling, worker sandbox changes, and permission-policy changes remain review-first.
- Non-interactive `ask` decisions resolve to deny for service and worker execution.
- Workspace export, artifact retention, logs, metrics, and traces must apply tenant-scoped redaction and lifecycle policy.
- Disaster recovery restores tenant `.aiteamos/` source manifests first, then rebuilds indexes and vector state from that source.
