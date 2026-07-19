import json

import pytest

from science_agent.infra.wiki import (
    InMemoryWikiIndex,
    JsonWikiDraftStore,
    LLMWikiCompiler,
    MarkdownWikiRepository,
)
from science_agent.knowledge import (
    KnowledgeIngestionService,
    KnowledgeQueryService,
    render_knowledge_evidence,
)
from science_agent.rag.types import (
    EvidencePack,
    PaperDocument,
    PaperIngestionResult,
    ParentChunk,
    RetrievalHit,
    SourceElement,
)
from science_agent.types import ModelResponse
from science_agent.tools import ToolRegistry, register_knowledge_tools
from science_agent.wiki import (
    SourceRef,
    WikiChangeSet,
    WikiClaim,
    WikiMaintenanceService,
    WikiOperation,
    WikiPage,
    WikiRetrievalService,
    WikiService,
    WikiSourceSnapshot,
)


class FakeEmbeddings:
    async def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    async def embed_query(self, text):
        return self._vector(text)

    @staticmethod
    def _vector(text):
        return [float(len(text)), float(text.lower().count("wiki") + 1)]


def _raw_result(content_hash="hash-new", status="created"):
    element = SourceElement(
        element_id="paper-1:element:1",
        paper_id="paper-1",
        page_no=1,
        bbox=None,
        element_type="paragraph",
        section_kind="background",
        text="Wiki organizes durable knowledge while raw RAG preserves evidence.",
    )
    return PaperIngestionResult(
        paper=PaperDocument(
            paper_id="paper-1",
            source_path="paper.txt",
            title="Wiki and raw RAG",
            content_hash=content_hash,
            revision=2 if content_hash != "hash-old" else 1,
        ),
        elements=[element],
        parents=[],
        children=[],
        status=status,
    )


class FakeRawIngestion:
    def __init__(self, result=None):
        self.result = result or _raw_result()

    async def ingest_detailed(self, path, *, paper_id=None):
        return self.result


class FakeCompiler:
    async def plan(self, source, related_pages):
        reference = source.references[0]
        page_id = f"concept/generated-{source.content_hash[-3:]}"
        return WikiChangeSet(
            change_id=f"compile-{source.content_hash}",
            source_hashes=[source.content_hash],
            compiler_version="fake-v1",
            operations=[
                WikiOperation(
                    operation="create_page",
                    page_id=page_id,
                    page=WikiPage(
                        page_id=page_id,
                        title="Generated Wiki knowledge",
                        page_type="concept",
                        body="# Generated Wiki knowledge\n\nEvidence-backed synthesis.",
                        status="tentative",
                        claims=[
                            WikiClaim(
                                claim_id="claim-generated",
                                text="Wiki keeps durable synthesis.",
                                sources=[reference],
                            )
                        ],
                    ),
                )
            ],
        )


class FakeRawRetriever:
    async def search(
        self,
        query,
        *,
        limit=None,
        section_kind=None,
        chunk_types=None,
    ):
        element = _raw_result().elements[0]
        parent = ParentChunk(
            chunk_id="parent-1",
            paper_id="paper-1",
            section_kind="background",
            text=element.text,
            source_element_ids=[element.element_id],
            page_start=1,
            page_end=1,
        )
        return EvidencePack(
            query=query,
            hits=[
                RetrievalHit(
                    chunk_id="child-1",
                    score=1.0,
                    text=element.text,
                    paper_id="paper-1",
                    parent_chunk_id="parent-1",
                    section_kind="background",
                )
            ],
            parents={parent.chunk_id: parent},
            source_elements={element.element_id: element},
        )


def _services(tmp_path):
    repository = MarkdownWikiRepository(tmp_path / "wiki")
    index = InMemoryWikiIndex()
    embeddings = FakeEmbeddings()
    wiki = WikiService(
        repository=repository,
        index=index,
        embeddings=embeddings,
    )
    retrieval = WikiRetrievalService(
        repository=repository,
        index=index,
        embeddings=embeddings,
    )
    ingestion = KnowledgeIngestionService(
        raw_ingestion=FakeRawIngestion(),
        compiler=FakeCompiler(),
        retrieval=retrieval,
        wiki=wiki,
        drafts=JsonWikiDraftStore(tmp_path / "drafts"),
        maintenance=WikiMaintenanceService(repository),
    )
    return repository, wiki, retrieval, ingestion


@pytest.mark.asyncio
async def test_knowledge_ingest_creates_reviewable_draft(tmp_path):
    repository, _, _, ingestion = _services(tmp_path)

    result = await ingestion.ingest("paper.txt")

    assert result.status == "drafted"
    assert result.changeset is not None
    assert await repository.list_pages() == []

    applied = await ingestion.apply_draft(result.changeset.change_id)

    assert applied.changed_pages[0].page_id == "concept/generated-new"


@pytest.mark.asyncio
async def test_changed_source_marks_old_claims_stale(tmp_path):
    repository, wiki, _, ingestion = _services(tmp_path)
    old_page = WikiPage(
        page_id="concept/old",
        title="Old knowledge",
        page_type="concept",
        body="# Old knowledge\n\nPreviously compiled.",
        claims=[
            WikiClaim(
                claim_id="old-claim",
                text="Old synthesis.",
                sources=[
                    SourceRef(
                        paper_id="paper-1",
                        element_id="paper-1:element:1",
                        content_hash="hash-old",
                    )
                ],
            )
        ],
    )
    await wiki.apply(
        WikiChangeSet(
            change_id="seed-old",
            operations=[
                WikiOperation(
                    operation="create_page",
                    page_id=old_page.page_id,
                    page=old_page,
                )
            ],
        )
    )

    result = await ingestion.ingest("paper.txt")
    stored = await repository.get_page("concept/old")

    assert result.stale_changeset is not None
    assert stored is not None
    assert stored.status == "stale"
    assert stored.claims[0].status == "stale"
    assert (
        await WikiMaintenanceService(repository).plan_source_refresh(
            "paper-1", "hash-new"
        )
        is None
    )


@pytest.mark.asyncio
async def test_knowledge_query_uses_wiki_and_verifies_raw_citation(tmp_path):
    _, _, retrieval, ingestion = _services(tmp_path)
    ingested = await ingestion.ingest("paper.txt", apply=True)
    assert ingested.status == "applied"
    query = KnowledgeQueryService(wiki=retrieval, raw=FakeRawRetriever())

    evidence = await query.search("请总结 Wiki 和 raw RAG 的关系")
    rendered = render_knowledge_evidence(evidence)

    assert evidence.plan.mode == "wiki_guided"
    assert any(item.verified_in_raw_results for item in evidence.citations)
    assert "WIKI CONTEXT" in rendered
    assert "RAW EVIDENCE" in rendered


@pytest.mark.asyncio
async def test_knowledge_query_falls_back_when_wiki_is_empty(tmp_path):
    _, _, retrieval, _ = _services(tmp_path)
    query = KnowledgeQueryService(wiki=retrieval, raw=FakeRawRetriever())

    evidence = await query.search("给我一个概览")

    assert evidence.plan.mode == "raw_only"


@pytest.mark.asyncio
async def test_wiki_lint_reports_orphan_pages(tmp_path):
    repository, _, _, ingestion = _services(tmp_path)
    await ingestion.ingest("paper.txt", apply=True)

    report = await WikiMaintenanceService(repository).lint()

    assert any(issue.code == "orphan_page" for issue in report.issues)


def test_register_knowledge_tools_exposes_composed_workflow(tmp_path):
    _, _, retrieval, ingestion = _services(tmp_path)
    query = KnowledgeQueryService(wiki=retrieval, raw=FakeRawRetriever())

    registry = register_knowledge_tools(
        ToolRegistry(),
        ingestion=ingestion,
        query=query,
    )

    assert registry.names() == [
        "knowledge_ingest",
        "knowledge_search",
        "wiki_apply_changeset",
    ]


class FakePlanningModel:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        payload = {
            "operations": [
                {
                    "operation": "create_page",
                    "page_id": "concept/compiled",
                    "page": {
                        "page_id": "concept/compiled",
                        "title": "Compiled knowledge",
                        "page_type": "concept",
                        "body": "# Compiled knowledge\n\nModel synthesis.",
                        "claims": [
                            {
                                "claim_id": "claim-compiled",
                                "text": "The source supports this claim.",
                                "sources": [
                                    {
                                        "paper_id": "paper-1",
                                        "element_id": "paper-1:element:1",
                                    }
                                ],
                            }
                        ],
                    },
                }
            ]
        }
        return ModelResponse(text=f"```json\n{json.dumps(payload)}\n```")


@pytest.mark.asyncio
async def test_llm_compiler_validates_and_canonicalizes_sources():
    source = WikiSourceSnapshot(
        source_id="paper-1",
        title="Paper",
        content_hash="hash-new",
        text="Evidence",
        references=[
            SourceRef(
                paper_id="paper-1",
                element_id="paper-1:element:1",
                page_no=1,
                content_hash="hash-new",
            )
        ],
    )

    changeset = await LLMWikiCompiler(FakePlanningModel()).plan(source, [])
    reference = changeset.operations[0].page.claims[0].sources[0]

    assert changeset.change_id.startswith("wiki-")
    assert reference.content_hash == "hash-new"
