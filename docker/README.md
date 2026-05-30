# Docker

Development environment orchestration.

## Services

- **PostgreSQL 15** with pgvector and Apache AGE extensions
- **Kafka** (KRaft mode, no ZooKeeper)
- **MinIO** (S3-compatible object storage for snapshots)
- **Temporal** server and UI

## Running

```bash
cd docker
docker compose up -d
```

## Database

| Variable | Value |
|----------|-------|
| Host | localhost |
| Port | 5432 |
| Database | aiteamos |
| User | aiteamos |
| Password | dev_password |
