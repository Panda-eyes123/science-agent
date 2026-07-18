# Infrastructure handoff

The repository includes [`docker/compose.yaml`](../docker/compose.yaml) as an
optional local infrastructure definition for downstream operators. It is not a
requirement for using the core SDK or JSONStore.

## Services

| Service | Responsibility | Host exposure |
|---|---|---|
| PostgreSQL | Agent state, event history, and snapshots | `127.0.0.1:5432` by default |
| Milvus Standalone | Paper chunks, vectors, BM25 data, and provenance | `127.0.0.1:19530` and health port `9091` |
| etcd | Internal Milvus metadata | Not exposed |
| MinIO | Internal Milvus object storage | Not exposed |

Named volumes preserve service data across ordinary Compose restarts:

- `postgres-data`
- `milvus-data`
- `etcd-data`
- `minio-data`

## Operator prerequisites

- Docker Engine or Docker Desktop with Compose support.
- Enough local memory and disk for Milvus, etcd, MinIO, and PostgreSQL.
- The Python `postgres` extra for the migration command.
- Application provider credentials when exercising embeddings, reranking, VLM,
  or chat model calls.

The maintainer environment used for this change did not have Docker installed.
The Compose stack is therefore supplied as a handoff artifact rather than a
locally executed deployment.

## Start the stack

```powershell
Copy-Item docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/compose.yaml up -d
docker compose --env-file docker/.env -f docker/compose.yaml ps
```

Apply PostgreSQL migrations:

```powershell
uv sync --extra postgres
uv run science-agent-migrate
```

`PostgresStore` can also apply pending migrations automatically when its pool
opens. Explicit migration is useful when an operator separates schema changes
from application startup.

## Stop and restart

Stop services without deleting named volumes:

```powershell
docker compose --env-file docker/.env -f docker/compose.yaml down
```

Start them again with the same `up -d` command. Do not add `--volumes` unless the
operator intentionally wants to delete persisted development data.

## Health checks

The Compose file defines service health checks for PostgreSQL, etcd, MinIO, and
Milvus. Operators should wait until `docker compose ps` reports healthy services
before applying migrations or ingesting papers.

Useful endpoint and connection checks are:

```text
PostgreSQL: localhost:5432
Milvus:     http://localhost:19530
Milvus:     http://localhost:9091/healthz
```

## Milvus startup and ingest

The current project has no Milvus Lite data to preserve. No export/import tool is
required. Milvus Standalone starts with an empty collection, and the consuming
application ingests PDFs normally using `paper_ingest` or
`PaperIngestionService`.

`MilvusCorpusStore` creates the chunk and provenance collections lazily. Its
default base collection is `paper_chunks`, configurable through
`MILVUS_COLLECTION_NAME`.

## Application placement

The Compose file intentionally contains infrastructure only. It does not build
or run the consuming application.

- Applications running on the host connect through `localhost`.
- Applications added to the Compose network connect through service names
  `postgres` and `milvus`.
- A downstream application container must provide its own environment variables,
  startup command, health endpoint, and dependency policy.

## Operational responsibilities left to consumers

- Replace all development credentials.
- Decide network exposure, TLS, authentication, and firewall policy.
- Configure PostgreSQL and Milvus backups.
- Define resource limits and monitoring.
- Choose application restart and failure policies.
- Run environment-level integration checks before production use.
- Add an application image or hosted API if the SDK is not embedded directly.

