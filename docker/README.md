# Docker

Development environment orchestration.

## Services

- **Neo4j 5.26** for Graphiti temporal knowledge graph
- **PostgreSQL 15** with pgvector and Apache AGE extensions
- **Kafka** (KRaft mode, no ZooKeeper)
- **MinIO** (S3-compatible object storage for snapshots)
- **Temporal** server and UI

## Running

For the current file-first AITeamOS flow, start only Neo4j:

```bash
docker compose up -d neo4j
```

The repository-level one-command dev launcher wraps this for you:

```bash
../scripts/dev-up.sh
```

## Plane WorkItem / Docs Backend

Plane is the default external WorkItem/Docs backend for AITeamOS. It is managed
as a separate Docker service rather than vendored into this repository. The
official Plane setup and compose files are downloaded into `.aiteamos/plane/`
by the repository-level script.

Start Plane together with AITeamOS:

```bash
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

After Plane starts, create an API key in Plane and configure `Settings / MCP
Connectors / Plane` with the API base URL, API key, workspace slug, and optional
default project id.

Legacy services are kept in this compose file for later milestones.

```bash
cd docker
docker compose up -d
```

## Neo4j

| Variable | Value |
|----------|-------|
| Host | localhost |
| Browser | http://localhost:7474 |
| Bolt URI | bolt://localhost:7687 |
| User | neo4j |
| Password | `${AITEAMOS_NEO4J_PASSWORD:-aiteamos_dev_password}` |
