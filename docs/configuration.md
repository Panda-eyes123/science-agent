# Configuration reference

`science-agent` reads configuration from the process environment through
`os.getenv`. The SDK does not automatically load the repository-root `.env`
file. A consuming application must export variables through its shell or
deployment platform, or call `python-dotenv` before importing modules whose
defaults are read at import time.

## Dependency extras

Install only the integrations required by the application:

```powershell
# Core runtime and JSONStore
uv sync

# PostgreSQL persistence
uv sync --extra postgres

# Scientific-paper RAG and Milvus
uv sync --extra rag

# Both integrations plus development tools
uv sync --extra postgres --extra rag --extra dev
```

Docker is not required to import the SDK or use `JSONStore`. A PostgreSQL server
is required for `PostgresStore`, and a Milvus 2.5+ server is required for
`MilvusCorpusStore`.

## Application variables

The root [`.env.example`](../.env.example) is a template for the application
process.

| Variable | Default or fallback | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | None | OpenAI-compatible chat provider credential |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Chat provider endpoint |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Default chat model |
| `EMBEDDING_API_KEY` | Falls back to `OPENAI_API_KEY` | Embedding credential |
| `EMBEDDING_BASE_URL` | Falls back to `OPENAI_BASE_URL` | Embedding endpoint |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `VLM_API_KEY` | Falls back to `OPENAI_API_KEY` | Vision provider credential |
| `VLM_BASE_URL` | Falls back to `OPENAI_BASE_URL` | Vision provider endpoint |
| `VLM_MODEL` | `gpt-4.1-mini` | Vision model |
| `RERANK_API_KEY` | Falls back to `OPENAI_API_KEY` | Reranker credential |
| `RERANK_BASE_URL` | Falls back to `OPENAI_BASE_URL` | Reranker endpoint |
| `RERANK_MODEL` | `BAAI/bge-reranker-v2-m3` | Reranker model |
| `RERANK_ENDPOINT` | `/rerank` | Reranker API path |
| `POSTGRES_DSN` | Local development DSN | PostgresStore and migration connection |
| `POSTGRES_TEST_DSN` | No implicit test activation | Enables the live PostgreSQL integration test |
| `MILVUS_URI` | `http://localhost:19530` | Milvus Standalone endpoint |
| `MILVUS_COLLECTION_NAME` | `paper_chunks` | Base paper chunk collection name |

The corpus implementation derives a provenance collection named
`<MILVUS_COLLECTION_NAME>_records`.

## Compose variables

[`docker/.env.example`](../docker/.env.example) configures the supplied Compose
services rather than the Python application.

| Variable | Development default | Purpose |
|---|---|---|
| `POSTGRES_DB` | `science_agent` | Database created by the PostgreSQL image |
| `POSTGRES_USER` | `science_agent` | Development database user |
| `POSTGRES_PASSWORD` | `science-agent-dev-password` | Development database password |
| `POSTGRES_PORT` | `5432` | Host-bound PostgreSQL port |
| `MILVUS_PORT` | `19530` | Host-bound Milvus client port |
| `MILVUS_HEALTH_PORT` | `9091` | Host-bound Milvus health port |
| `MINIO_ROOT_USER` | `minioadmin` | Milvus object-store development user |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | Milvus object-store development password |
| `*_IMAGE` | Pinned in the template | Service image overrides |

## Host and container addresses

Connection addresses depend on where the consuming application runs:

| Application location | PostgreSQL address | Milvus URI |
|---|---|---|
| Host machine | `localhost:5432` | `http://localhost:19530` |
| Same Compose network | `postgres:5432` | `http://milvus:19530` |

The supplied Compose file does not define an application service. A downstream
operator placing an application container in the network must set its own DSN,
for example:

```text
postgresql://science_agent:<password>@postgres:5432/science_agent
```

## Secret and network expectations

- Values in both `.env.example` files are development examples, not production
  credentials.
- Operators must replace PostgreSQL and MinIO passwords outside isolated local
  development.
- Do not commit populated `.env` files.
- The supplied Compose file binds PostgreSQL and Milvus to `127.0.0.1`.
- etcd and MinIO are internal Milvus dependencies and are not exposed to the
  host by the supplied configuration.
- The SDK does not provide a secret manager, TLS termination, authentication
  proxy, firewall rules, or credential rotation.
