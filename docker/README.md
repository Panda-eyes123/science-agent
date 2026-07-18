# Local infrastructure

This directory owns the local PostgreSQL and Milvus Standalone infrastructure.
Milvus runs with its required etcd and MinIO dependencies; none of those internal
service ports are exposed to the host.

This Compose stack is an operator handoff artifact. It was not started in the
maintainer environment because Docker was not installed. See the
[infrastructure handoff](../docs/infrastructure.md) and
[verification status](../docs/verification.md) for the explicit validation
boundary.

Copy the optional environment overrides and start the services:

```powershell
Copy-Item docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/compose.yaml up -d
```

Check service health:

```powershell
docker compose --env-file docker/.env -f docker/compose.yaml ps
```

Install the PostgreSQL extra and apply schema migrations explicitly when needed:

```powershell
uv sync --extra postgres --extra dev
uv run science-agent-migrate
```

`PostgresStore` also applies pending migrations automatically when its pool is
opened for the first time.

Stop the services without removing persisted data:

```powershell
docker compose --env-file docker/.env -f docker/compose.yaml down
```

The SDK reads `POSTGRES_DSN` and `MILVUS_URI` from the application process
environment; it does not automatically load the root `.env` file. The Docker
credentials in this directory are local-development defaults and must be replaced
in shared or production environments.

When the application runs on the host, use `localhost` for PostgreSQL and Milvus.
When it runs inside the same Compose network, use the service names `postgres`
and `milvus` instead.

There is no Milvus Lite corpus to migrate in the current project. Standalone
starts with an empty collection, and papers can be ingested normally afterward.
