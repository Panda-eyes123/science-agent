# science-agent

`science-agent` is an alpha-stage Python SDK for building event-driven research agents.
It currently focuses on a small but working runtime: async agent execution, event
subscription, JSON or PostgreSQL persistence, sandboxed file tools, permission
approval, and an OpenAI-compatible provider adapter.

This project is intentionally still small. The alpha goal is to keep the runtime
easy to inspect while the core contracts settle.

## Documentation

- [Documentation index](docs/README.md)
- [Configuration reference](docs/configuration.md)
- [Storage guide](docs/storage.md)
- [Infrastructure handoff](docs/infrastructure.md)
- [Personal Wiki foundation](docs/wiki.md)
- [Verification status](docs/verification.md)

## Current Status

The SDK can already:

- Run an async `Agent` with a template, model provider, message history, and event stream.
- Emit `progress`, `control`, and `monitor` events.
- Register and execute tools through `ToolRegistry`.
- Use built-in tools for todo management and sandboxed file read/write.
- Persist messages, tool calls, events, todos, snapshots, and agent info with `JSONStore`.
- Persist the same Store contract in PostgreSQL with pooled connections, atomic
  state UPSERTs, versioned migrations, and idempotent event writes.
- Enforce local sandbox path boundaries for file tools.
- Request manual tool approval through `control.permission_required`.
- Call an OpenAI-compatible `/chat/completions` endpoint with categorized provider errors and retry handling.
- Maintain a Markdown Wiki projection with cited claims, drafts, revisions,
  stale-source detection, BM25/dense indexing, and linting.
- Route personal knowledge queries through Wiki synthesis and raw RAG evidence
  without coupling the Agent runtime to either storage implementation.

## Requirements

- Python `3.13+`
- `uv`
- An `OPENAI_API_KEY` only when using the real `OpenAIProvider`
- Docker Desktop/Engine with Compose only when running the supplied local
  PostgreSQL and Milvus Standalone infrastructure

## Setup

```powershell
uv venv --python 3.13
uv sync --extra dev
```

To use the scientific-paper RAG stack, install the optional dependencies:

```powershell
uv sync --extra rag --extra dev
```

Install the PostgreSQL dependency without starting infrastructure:

```powershell
uv sync --extra postgres --extra dev
```

Operators who want the supplied local infrastructure can then run:

```powershell
Copy-Item docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/compose.yaml up -d
uv run science-agent-migrate
```

The SDK reads process environment variables; it does not automatically load the
root `.env` file. See the [configuration reference](docs/configuration.md) for
the complete variable and connection contract.

## Paper RAG (Stages 1-3)

The SDK now includes an optional, tool-layer scientific-paper RAG pipeline. The
agent runtime remains independent; applications explicitly create the parser,
embedding model, Milvus corpus, ingestion service, and retrieval service, then
register the tools they need.

```text
PDF -> Docling (PyMuPDF fallback) -> source elements -> parent/child chunks
    -> Milvus native BM25 + dense vector -> RRF -> CrossEncoder -> EvidencePack
```

- Sections are rule-routed as `background`, `method`, `experiment`, `result`,
  `discussion`, or `other`.
- Tables retain Markdown, and figures retain captions, page number, bounding box,
  exported local image paths, and source-element identity for future VLM retrieval.
- Every child hit links back to a parent chunk and then original source elements.
- Re-ingesting unchanged content is idempotent; changed content receives a new
  source revision and replaces stale chunks and provenance records.
- Milvus Standalone stores both indexed child chunks and provenance records. The
  default client URI is `http://localhost:19530`.

Minimal wiring:

```python
from science_agent.infra.corpus import MilvusCorpusStore
from science_agent.infra.document_parsing import DoclingPDFParser
from science_agent.infra.embeddings import OpenAIEmbeddingProvider
from science_agent.infra.rerankers import APIReranker
from science_agent.rag import PaperChunker, PaperIngestionService, RetrievalService
from science_agent.tools import ToolRegistry, register_rag_tools

embeddings = OpenAIEmbeddingProvider(model="text-embedding-3-small")
corpus = MilvusCorpusStore(
    embedding_dim=1536,
)
ingestion = PaperIngestionService(
    parser=DoclingPDFParser(),
    chunker=PaperChunker(),
    embeddings=embeddings,
    corpus=corpus,
)
retrieval = RetrievalService(
    corpus=corpus,
    embeddings=embeddings,
    reranker=APIReranker(model="BAAI/bge-reranker-v2-m3"),
)
tools = register_rag_tools(ToolRegistry(), ingestion=ingestion, retrieval=retrieval)
```

The current project has no Milvus Lite corpus requiring migration. After starting
Standalone, ingest papers normally into the empty collection.

Configure reranking with `RERANK_API_KEY`, `RERANK_MODEL`, `RERANK_BASE_URL`,
and optionally `RERANK_ENDPOINT` (default: `/rerank`). The adapter accepts the
common Jina/Cohere-style response shape with `index` and `relevance_score`.

`paper_ingest` indexes a local PDF and `paper_search` returns a serializable
evidence pack. Embeddings, reranking, and VLM inference use API adapters; no
model weights are loaded into the agent process.

## Personal Knowledge Layer (Phases 0-3)

The optional Wiki layer is a durable projection over raw paper evidence. It does
not replace `RetrievalService` and does not share the paper chunk schema.

```text
Raw ingest -> WikiSourceSnapshot -> reviewable WikiChangeSet -> Markdown Wiki
                                                        -> independent index

Question -> Wiki BM25/dense/RRF -> linked pages -> raw RAG verification
```

- `WikiPage`, `WikiClaim`, `SourceRef`, and `WikiLink` preserve stable knowledge
  identities and claim-level raw citations.
- `MarkdownWikiRepository` applies revision-checked changesets and writes an
  audit record for idempotent retries.
- `MilvusWikiIndex` stores Wiki pages in `wiki_pages`, separate from
  `paper_chunks`; `InMemoryWikiIndex` supports offline examples and tests.
- Uncited claims, unsafe page ids, duplicate links, and stale update revisions
  are rejected before page writes.
- `KnowledgeIngestionService` preserves Raw RAG success when model compilation
  fails, stores reviewable drafts, and marks claims from older source hashes stale.
- `KnowledgeQueryService` routes queries as `wiki_guided`, `raw_first`, or
  `raw_only`, then returns separated Wiki synthesis and raw evidence.
- `register_knowledge_tools` exposes `knowledge_ingest`, `knowledge_search`, and
  `wiki_apply_changeset` without modifying the Agent runtime.

Run the offline example:

```powershell
uv run python examples/wiki_knowledge_layer.py
uv run python examples/knowledge_workflow.py
```

See the [Wiki foundation guide](docs/wiki.md) for storage and failure semantics.

## Multimodal RAG (Stage 4)

Stage four adds visual evidence without coupling the core retrieval service to a
specific PDF renderer or vision model:

```text
visual query -> figure/table/mixed retrieval -> source-element backtrace
             -> Docling image or PyMuPDF bbox crop -> fallback policy
             -> optional OpenAI-compatible VLM -> structured observations
```

`PDFRegionRenderer` explicitly converts Docling bottom-left coordinates to
PyMuPDF top-left coordinates. `PDFVisualAssetResolver` reuses exported figures
when possible and only crops the source PDF when an image is missing. Generated
assets keep page, bbox, dimensions, caption, and parent context.

```python
from science_agent.infra.visual_assets import PDFVisualAssetResolver
from science_agent.infra.vlm import OpenAIVisionProvider
from science_agent.rag.multimodal import FigureSearchService

figure_search = FigureSearchService(
    retrieval=retrieval,
    paper_store=corpus,
    asset_resolver=PDFVisualAssetResolver(),
    vlm=OpenAIVisionProvider(model="gpt-4.1-mini"),
)
tools = register_rag_tools(
    ToolRegistry(),
    ingestion=ingestion,
    retrieval=retrieval,
    figure_search=figure_search,
)
```

The resulting `paper_figure_search` tool accepts `vlm_mode="auto"`, `"always"`,
or `"never"`. Auto mode invokes the VLM for explicit visual questions or when
captions do not contain enough information. VLM output is query-scoped evidence
and is not written back into the Milvus corpus.

Configure an OpenAI-compatible vision endpoint with `VLM_API_KEY`, `VLM_MODEL`,
and `VLM_BASE_URL`. The provider falls back to the corresponding `OPENAI_*`
variables when dedicated VLM settings are absent.

## Development Commands

Run the test suite:

```powershell
uv run pytest
```

Run PostgreSQL integration tests after starting Compose:

```powershell
$env:POSTGRES_TEST_DSN="postgresql://science_agent:science-agent-dev-password@localhost:5432/science_agent"
uv run pytest tests/integration/test_postgres_store.py
```

Run lint checks:

```powershell
uv run ruff check .
```

Run all local quality checks:

```powershell
uv run pytest
uv run ruff check .
```

Run the built-in examples:

```powershell
uv run python examples\getting_started.py
uv run python examples\tool_usage.py
uv run python examples\persistence_resume.py
uv run python examples\postgres_persistence.py
```

## Local Example

`examples/getting_started.py` runs without external API calls. It uses a tiny mock
provider and prints progress events from the agent.

```python
import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    ModelResponse,
    ToolRegistry,
)


class EchoProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        last_user = next(
            message.content for message in reversed(messages) if message.role == "user"
        )
        return ModelResponse(text=f"Science agent received: {last_user}")


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You are a concise scientific research assistant.",
        )
    )

    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=EchoProvider(),
            tool_registry=ToolRegistry(),
        ),
        templates,
    )

    async def consume() -> None:
        async for envelope in agent.subscribe(["progress"]):
            print(envelope.event)
            if envelope.event["type"] == "done":
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await agent.send("Summarize the role of controls in a simple experiment.")
    await consumer


asyncio.run(main())
```

## PostgreSQL Persistence

`PostgresStore` implements the same runtime contract as `JSONStore`. It lazily
opens a Psycopg 3 async connection pool and automatically applies packaged SQL
migrations before the first operation. Agent state is committed with one UPSERT
transaction. Events use `(agent_id, seq)` as their primary key: writing identical
content twice is idempotent, while reusing a sequence with different content
raises `EventSequenceConflictError`.

The runtime still expects one active writer for each `agent_id`. PostgreSQL
detects conflicting event sequences, but this phase does not add distributed
leases or multi-worker scheduling.

```python
from science_agent import PostgresStore

async with PostgresStore() as store:
    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=provider,
            store=store,
            agent_id="stable-agent-id",
        ),
        templates,
    )
```

Use `uv run science-agent-migrate` for deployment workflows that apply migrations
before starting the application. `JSONStore` remains available for lightweight,
single-process development.

See the [storage guide](docs/storage.md) for connection lifecycle, schema,
transaction behavior, event ordering, and failure semantics.

## Tool, Persistence, And Knowledge Examples

The repository includes five practical local demos:

- `examples/tool_usage.py`: simulates a model requesting `todo_write`, then persists the agent state in `.demo_store`.
- `examples/persistence_resume.py`: creates an agent with a fixed `agent_id`, writes state through `JSONStore`, then restores a second agent instance from the same store.
- `examples/postgres_persistence.py`: performs the same restore flow through
  `PostgresStore` and its automatic migrations.
- `examples/wiki_knowledge_layer.py`: applies cited Wiki changes, writes
  Markdown pages, links concepts, and searches an offline index.
- `examples/knowledge_workflow.py`: runs raw ingestion, Wiki compilation,
  application, routed retrieval, and raw citation verification end to end.

These examples use mock providers or in-memory adapters so they remain stable
for tests and offline development.

## Real OpenAI Example

Set your API key:

```powershell
$env:OPENAI_API_KEY="sk-..."
```

Then use the real provider:

```python
import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    OpenAIProvider,
    RetryConfig,
    ToolRegistry,
)


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You are a careful scientific research assistant.",
        )
    )

    provider = OpenAIProvider(
        model="gpt-4.1-mini",
        retry=RetryConfig(max_attempts=3, backoff_seconds=0.5),
    )
    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=provider,
            tool_registry=ToolRegistry(),
        ),
        templates,
    )

    async def consume() -> None:
        async for envelope in agent.subscribe(["progress", "monitor"]):
            print(envelope.event)
            if envelope.event["type"] == "done":
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await agent.send("Give me a concise hypothesis for testing yeast growth rates.")
    await consumer


asyncio.run(main())
```

`OpenAIProvider` currently uses the Chat Completions API. It categorizes common
provider failures into authentication, invalid request, not found, rate limit,
server, timeout, network, and response parsing errors. Retry is applied only to
retryable failures such as `408`, `429`, `409`, `5xx`, timeout, and network errors.

## Permission Approval Example

Use `permission_mode="manual"` when tool calls should require an explicit decision.
Subscribers listen to the `control` channel and call the event's `respond` function.

```python
async for envelope in agent.subscribe(["control", "progress"]):
    if envelope.event["type"] == "permission_required":
        call = envelope.event["call"]
        if call["name"] == "fs_write":
            await envelope.event["respond"]("allow", note="approved file write")
        else:
            await envelope.event["respond"]("deny", note="tool not allowed")
```

Persisted control events are sanitized before being written to a Store, so the
runtime callback is available to subscribers but is not serialized to disk.

## Public API Surface

The alpha public exports are:

- `Agent`, `AgentConfig`
- `AgentTemplateDefinition`, `AgentTemplateRegistry`
- `JSONStore`, `PostgresStore`
- `StoreError`, `EventSequenceConflictError`, `migrate_postgres`
- `LocalSandbox`, `SandboxResult`
- `OpenAIProvider`, `RetryConfig`
- `Tool`, `ToolExecutionContext`, `ToolRegistry`
- `TodoItem`, `TodoService`
- `ModelProvider`, `ModelResponse`, `ToolCallRequest`

The `science_agent.wiki` namespace additionally exports the Wiki page, claim,
link, source-reference, changeset, validation, and service contracts. Concrete
Markdown and index adapters live under `science_agent.infra.wiki`.

The `science_agent.knowledge` namespace exports the composed ingestion, routing,
query, and rendering services. `register_knowledge_tools` is exported from
`science_agent.tools`.

## Capability Boundaries

This alpha is useful for local development, SDK contract exploration, and small
research-agent prototypes. It is not production-ready yet.

Currently supported:

- Single-process async runtime.
- Local JSON persistence and pooled PostgreSQL persistence.
- Local sandbox file read/write with path boundary checks.
- Sequential tool execution.
- Manual approval flow for tool calls.
- Minimal OpenAI-compatible provider with categorized errors and retry.
- Unit-tested core behavior.

Not yet supported:

- Streaming token-by-token provider output.
- SQLite storage.
- Distributed locks, agent leases, or multi-writer coordination beyond explicit
  event-sequence conflict detection.
- MCP tools.
- E2B/OpenSandbox remote sandboxes.
- Full breakpoint/resume state machine.
- Token-aware context compression.
- Provider usage accounting.
- CI configuration.
- A stable semantic-versioned API.

## Project Layout

```text
src/science_agent/
  core/              Agent runtime, events, templates, todos
  agent_runtime/     Tool execution, permissions, approval coordination
  rag/               Raw paper ingestion, retrieval, provenance, multimodal flow
  wiki/              Durable pages, claims, links, changesets, validation
  knowledge/         Raw/Wiki ingestion and query orchestration
  infra/             Providers, stores, sandbox implementations
  tools/             Tool primitives, registry, built-in tools
  utils/             Small utility helpers
tests/unit/          Unit tests for runtime, store, tools, provider behavior
tests/integration/   Tests requiring explicitly configured external services
examples/            Local runnable examples
docker/              Optional local PostgreSQL and Milvus infrastructure
docs/                Configuration, storage, infrastructure, verification guides
```

## Alpha Roadmap

Near-term work:

- Add an approval-control example under `examples/`.
- Add provider usage/token parsing.
- Add request logging hooks for provider calls.
- Add streaming support for OpenAI-compatible responses.
- Add CI for tests and linting.
- Decide whether Python `3.13+` remains required or whether to support `3.11+`.
