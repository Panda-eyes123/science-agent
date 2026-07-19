"""Offline end-to-end example for raw ingest, Wiki compile, and grounded query."""

import asyncio
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from science_agent.infra.wiki import (
    InMemoryWikiIndex,
    JsonWikiDraftStore,
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
from science_agent.wiki import (
    WikiChangeSet,
    WikiClaim,
    WikiMaintenanceService,
    WikiOperation,
    WikiPage,
    WikiRetrievalService,
    WikiService,
)


class DemoEmbeddings:
    async def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    async def embed_query(self, text):
        return self._vector(text)

    @staticmethod
    def _vector(text):
        normalized = text.lower()
        return [float(len(text)), float(normalized.count("wiki") + 1)]


class DemoRawKnowledge:
    def __init__(self) -> None:
        self.result = None

    async def ingest_detailed(self, path, *, paper_id=None):
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        resolved_id = paper_id or "paper-demo"
        content_hash = sha256(text.encode("utf-8")).hexdigest()
        element = SourceElement(
            element_id=f"{resolved_id}:element:1",
            paper_id=resolved_id,
            page_no=1,
            bbox=None,
            element_type="paragraph",
            section_kind="background",
            text=text,
        )
        self.result = PaperIngestionResult(
            paper=PaperDocument(
                paper_id=resolved_id,
                source_path=str(file_path),
                title="Personal Wiki architecture",
                content_hash=content_hash,
            ),
            elements=[element],
            parents=[],
            children=[],
            status="created",
        )
        return self.result

    async def search(
        self,
        query,
        *,
        limit=None,
        section_kind=None,
        chunk_types=None,
    ):
        assert self.result is not None
        element = self.result.elements[0]
        parent = ParentChunk(
            chunk_id="parent-demo",
            paper_id=element.paper_id,
            section_kind=element.section_kind,
            text=element.text,
            source_element_ids=[element.element_id],
            page_start=1,
            page_end=1,
        )
        return EvidencePack(
            query=query,
            hits=[
                RetrievalHit(
                    chunk_id="child-demo",
                    score=1.0,
                    text=element.text,
                    paper_id=element.paper_id,
                    parent_chunk_id=parent.chunk_id,
                    section_kind=element.section_kind,
                )
            ],
            parents={parent.chunk_id: parent},
            source_elements={element.element_id: element},
        )


class DemoCompiler:
    async def plan(self, source, related_pages):
        return WikiChangeSet(
            change_id=f"demo-{source.content_hash[:16]}",
            source_hashes=[source.content_hash],
            compiler_version="demo-v1",
            operations=[
                WikiOperation(
                    operation="create_page",
                    page_id="concept/wiki-guided-rag",
                    page=WikiPage(
                        page_id="concept/wiki-guided-rag",
                        title="Wiki-guided RAG",
                        page_type="concept",
                        body=(
                            "# Wiki-guided RAG\n\n"
                            "Wiki organizes durable synthesis; raw RAG verifies it."
                        ),
                        aliases=["knowledge-layer RAG"],
                        status="established",
                        claims=[
                            WikiClaim(
                                claim_id="claim-layering",
                                text=(
                                    "Wiki synthesis must retain a raw evidence chain."
                                ),
                                sources=[source.references[0]],
                                status="established",
                            )
                        ],
                    ),
                )
            ],
        )


async def main() -> None:
    with TemporaryDirectory(prefix="science-agent-knowledge-") as directory:
        root = Path(directory)
        paper = root / "paper.txt"
        paper.write_text(
            "Wiki organizes durable synthesis. Raw RAG preserves and verifies evidence.",
            encoding="utf-8",
        )
        embeddings = DemoEmbeddings()
        repository = MarkdownWikiRepository(root / "wiki")
        index = InMemoryWikiIndex()
        wiki = WikiService(
            repository=repository,
            index=index,
            embeddings=embeddings,
        )
        wiki_retrieval = WikiRetrievalService(
            repository=repository,
            index=index,
            embeddings=embeddings,
        )
        raw = DemoRawKnowledge()
        ingestion = KnowledgeIngestionService(
            raw_ingestion=raw,
            compiler=DemoCompiler(),
            retrieval=wiki_retrieval,
            wiki=wiki,
            drafts=JsonWikiDraftStore(root / "drafts"),
            maintenance=WikiMaintenanceService(repository),
        )
        ingested = await ingestion.ingest(paper, apply=True)
        query = KnowledgeQueryService(wiki=wiki_retrieval, raw=raw)
        evidence = await query.search("总结 Wiki 与 raw RAG 的关系")

        print("Ingestion status:", ingested.status)
        print(render_knowledge_evidence(evidence))


if __name__ == "__main__":
    asyncio.run(main())
