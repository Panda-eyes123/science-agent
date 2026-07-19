# Personal Wiki foundation

The Wiki foundation adds a durable knowledge projection without changing the
raw paper RAG responsibility.

```text
raw paper -> content hash and revision -> replace raw chunks
          -> validated WikiChangeSet -> Markdown pages -> Wiki search index
```

## Boundaries

- `science_agent.rag` owns raw source parsing, chunking, retrieval, and
  provenance.
- `science_agent.wiki` owns pages, claims, source references, links, revisions,
  validation, and changesets.
- `science_agent.infra.wiki` owns Markdown and index implementations.
- Agent and tool routing remain unchanged. A Wiki-guided query service belongs
  to the next application-layer phase.

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

## Offline example

Run the example without API credentials or external infrastructure:

```powershell
uv run python examples/wiki_knowledge_layer.py
```

The example creates two cited pages, links the Wiki synthesis page to the raw
RAG concept page, persists them as Markdown, and queries an in-memory index.
