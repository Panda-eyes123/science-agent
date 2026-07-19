# Documentation

The root [`README.md`](../README.md) is the general SDK introduction and quick
start. The documents in this directory provide the detailed handoff contract for
applications that integrate persistence or paper RAG infrastructure.

## Guides

- [`configuration.md`](configuration.md): dependency extras, environment
  variables, connection addresses, and secret-handling expectations.
- [`storage.md`](storage.md): JSONStore and PostgresStore behavior, connection
  lifecycle, migrations, schema, event ordering, and failure semantics.
- [`infrastructure.md`](infrastructure.md): PostgreSQL and Milvus Standalone
  Compose services, operator commands, volumes, and empty-corpus startup.
- [`wiki.md`](wiki.md): raw-ingest lifecycle, Wiki compilation and drafts,
  Markdown persistence, query routing, source citations, and maintenance.
- [`verification.md`](verification.md): completed repository checks, unverified
  external-service checks, and a downstream operator checklist.

## Scope

These documents describe an SDK handoff. The repository does not currently ship
a hosted API, application Docker image, deployment automation, distributed Agent
leases, or production backup and secret-management systems.
