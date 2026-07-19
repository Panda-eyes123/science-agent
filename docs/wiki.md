# Personal knowledge layer

The personal knowledge layer adds a durable Wiki projection and a composed
query workflow without changing the raw paper RAG responsibility.

```text
raw paper -> content hash and revision -> replace raw chunks
          -> WikiSourceSnapshot -> LLMWikiCompiler -> reviewable draft
          -> validated WikiChangeSet -> Markdown pages -> Wiki search index

question -> QueryPolicy -> Wiki BM25/dense/RRF -> one-hop links
         -> raw RAG verification -> KnowledgeEvidence
```

## Boundaries

- `science_agent.rag` owns raw source parsing, chunking, retrieval, and
  provenance.
- `science_agent.wiki` owns pages, claims, source references, links, revisions,
  validation, and changesets.
- `science_agent.infra.wiki` owns Markdown and index implementations.
- `science_agent.knowledge` composes raw ingest, Wiki compilation, query routing,
  and evidence rendering.
- Agent runtime remains unchanged and receives the workflow through tools.

The raw paper collection and Wiki index are deliberately separate. The paper
schema contains child and parent chunk fields, while the Wiki schema contains
page type, status, revision, aliases, claims, and links.

## Canonical pages and projections

`MarkdownWikiRepository` writes JSON metadata inside standard `---` front
matter followed by ordinary Markdown content. JSON is valid YAML, which keeps
the files human-readable without adding a YAML dependency.

Each changeset is checked before writing and records:

- stable page and claim identifiers;
- claim-level `paper_id` and `element_id` references;
- optimistic `expected_revision` values;
- a stable `change_id` audit record;
- explicit create, update, link, conflict, or stale operations.

The repository is canonical. `InMemoryWikiIndex` is available for offline
examples and tests, while `MilvusWikiIndex` provides separate BM25 and dense
search projections for applications already using Milvus.

Page metadata also carries a content hash. If a user edits the Markdown body
outside the repository API, the next read exposes a virtual revision increment,
so a changeset based on the old revision cannot silently overwrite that edit.

## Failure model

Raw ingestion calculates a SHA-256 content hash. Re-ingesting unchanged content
is a no-op; changed content increments the paper revision and replaces previous
Milvus chunks and provenance records.

Wiki repository writes occur before index projection. If index projection fails,
the Markdown page remains authoritative and can be indexed again. This avoids a
distributed transaction between the filesystem and Milvus.

`KnowledgeIngestionService` stores compiler output in `JsonWikiDraftStore` before
application. Raw ingestion remains successful when compilation fails. A source
hash change deterministically marks claims backed by older revisions as `stale`
before compiling the replacement knowledge.

## Query routing

`KnowledgeQueryPolicy` chooses one of three modes:

- `wiki_guided` for overview, relationship, comparison, and synthesis questions;
- `raw_first` for facts, metrics, sources, dates, tables, and figures;
- `raw_only` when Wiki coverage is absent, stale, or conflicting.

Wiki content is always labelled as secondary synthesis. Raw parent chunks and
source elements remain the primary evidence. The combined result reports route
reasons, stale/conflicting pages, and whether each claim citation was present in
the raw retrieval window.

## Agent tools

Applications can register three composed tools through
`register_knowledge_tools`:

- `knowledge_ingest`: ingest raw evidence and create or apply a Wiki draft;
- `knowledge_search`: retrieve Wiki context and verify it with raw RAG;
- `wiki_apply_changeset`: apply a reviewed draft by `change_id`.

`knowledge_ingest` accepts `force_recompile=true` when a new compiler version or
schema should process unchanged source content.

## Maintenance

`WikiMaintenanceService` provides deterministic source-refresh planning and
lint reports for invalid pages, dead links, duplicate aliases, and orphan pages.
`WikiService.reindex_all()` rebuilds the current canonical pages after a failed
or replaced search projection.

## Offline example

Run the example without API credentials or external infrastructure:

```powershell
uv run python examples/wiki_knowledge_layer.py
uv run python examples/knowledge_workflow.py
```

The first example demonstrates page and link persistence. The second runs the
complete raw-ingest, Wiki-compile, apply, route, and evidence-verification flow.
