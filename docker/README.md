# Local infrastructure

This directory owns the local PostgreSQL and Milvus Standalone infrastructure.
Milvus runs with its required etcd and MinIO dependencies; none of those internal
service ports are exposed to the host.

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

The application connects through `POSTGRES_DSN` and `MILVUS_URI` in the root
`.env` file. The Docker credentials in this directory are local-development
defaults and must be replaced in shared or production environments.

There is no Milvus Lite corpus to migrate in the current project. Standalone
starts with an empty collection, and papers can be ingested normally afterward.
