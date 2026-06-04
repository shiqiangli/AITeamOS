# Docker

Development environment orchestration for the file-first AITeamOS 1.0 baseline.

## Services

- **Neo4j 5.26** for the optional Graphiti temporal knowledge graph backend

## Running

Start Neo4j:

```bash
export AITEAMOS_NEO4J_PASSWORD="<choose-a-local-password>"
docker compose up -d neo4j
```

The repository-level one-command dev launcher wraps this for you:

```bash
export AITEAMOS_NEO4J_PASSWORD="<choose-a-local-password>"
../scripts/dev-up.sh
```

## Plane Ticket / Docs Backend

Plane is the default external Ticket/Docs backend for AITeamOS. It is managed
as a separate Docker service rather than vendored into this repository. The
official Plane setup and compose files are downloaded into `.aiteamos/plane/`
by the repository-level script.

Start Plane together with AITeamOS:

```bash
export AITEAMOS_NEO4J_PASSWORD="<choose-a-local-password>"
AITEAMOS_WITH_PLANE=1 ../scripts/dev-up.sh
```

Or manage Plane directly:

```bash
../scripts/plane-up.sh up
../scripts/plane-up.sh stop
../scripts/plane-up.sh logs
```

Defaults:

| Variable | Value |
|----------|-------|
| Plane release | `${AITEAMOS_PLANE_VERSION:-v1.3.1}` |
| Plane URL | `${AITEAMOS_PLANE_URL:-http://localhost:8082}` |
| Plane install dir | `${AITEAMOS_PLANE_DIR:-.aiteamos/plane}` |

After Plane starts, create an API key in Plane and configure it through
`Settings / Ticket Backend`. Keep the API key in an environment variable; do not
store it in local JSON config.

## Neo4j

| Variable | Value |
|----------|-------|
| Host | localhost |
| Browser | http://localhost:7474 |
| Bolt URI | bolt://localhost:7687 |
| User | neo4j |
| Password | `${AITEAMOS_NEO4J_PASSWORD}` required |
