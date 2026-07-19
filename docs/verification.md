# Verification status

This document separates repository-level checks completed on 2026-07-18 from
checks that require external infrastructure and were intentionally left to
downstream operators.

## Personal knowledge checks (2026-07-19)

The focused offline verification for the Raw RAG lifecycle and personal
knowledge layer completed with these results:

| Check | Result |
|---|---|
| Complete unit test suite | `43 passed` |
| Ruff static analysis | Passed |
| Wiki foundation example | Passed |
| End-to-end knowledge workflow example | Passed |
| `git diff --check` | Passed |

The knowledge-focused tests cover content-hash idempotency, revisions, Wiki
changeset validation, draft application, stale-source propagation, Wiki/raw
routing, citation verification, LLM JSON parsing, linting, and tool registration.
The complete suite also covers Agent, Store, provider, tool, and multimodal RAG
behavior.

Live Milvus verification remains part of the external-infrastructure boundary.
In particular, operators should validate paper replacement filters and the
separate `wiki_pages` collection against their deployed Milvus version.

## Completed checks

The latest verification performed for the Store and Milvus interface change
completed with these results:

| Check | Result |
|---|---|
| Unit and Store contract tests | `31 passed` |
| Live PostgreSQL integration test | `1 skipped` because no database was configured |
| Ruff static analysis | Passed |
| Source distribution build | Passed |
| Wheel build | Passed |
| Migration resource inside wheel | Confirmed |
| Migration CLI help/import | Passed |
| `git diff --check` | Passed |

The Store contract suite covers JSONStore behavior, state round trips, event
filters, idempotent duplicate writes, sequence conflicts, snapshots, deletion,
listing, and restored event numbering.

## Not executed in the maintainer environment

Docker, PostgreSQL, and Milvus were not installed in the maintainer environment.
The following environment-level checks were not executed:

- Starting the supplied Compose stack.
- Applying SQL migrations to a live PostgreSQL server.
- Running the PostgresStore contract against a live database.
- Restarting PostgreSQL and confirming volume persistence.
- Starting Milvus Standalone, etcd, and MinIO.
- Ingesting a PDF into the empty Standalone collection.
- Exercising BM25, dense retrieval, RRF, reranking, and provenance against the
  deployed Milvus service.

This is an explicit verification boundary, not a claim that the live integrations
failed.

## Optional downstream checklist

Operators who choose to deploy the integrations can run:

```powershell
Copy-Item docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/compose.yaml up -d
docker compose --env-file docker/.env -f docker/compose.yaml ps
uv run science-agent-migrate
$env:POSTGRES_TEST_DSN="postgresql://science_agent:science-agent-dev-password@localhost:5432/science_agent"
uv run pytest tests/integration/test_postgres_store.py
```

For Milvus, ingest one representative PDF and verify:

- Collection creation succeeds.
- BM25 and dense searches return results.
- RRF and reranking produce a stable evidence ordering.
- Parent chunks and source elements can be resolved from child hits.
- A service restart preserves the collection and provenance records.

These checks are recommendations for consumers who deploy the services. They are
not required to import or inspect the SDK source.
