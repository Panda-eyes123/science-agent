"""Paper ingestion service coordinating parse, chunking, embeddings, and storage."""

import asyncio
from hashlib import sha256
from pathlib import Path

from science_agent.rag.ports import CorpusStore
from science_agent.infra.document_parsing.types import DocumentParser
from science_agent.infra.embeddings.base import EmbeddingProvider
from science_agent.rag.chunking import PaperChunker
from science_agent.rag.types import PaperDocument, PaperIngestionResult, SourceElement


class PaperIngestionService:
    def __init__(
        self,
        *,
        parser: DocumentParser,
        chunker: PaperChunker,
        embeddings: EmbeddingProvider,
        corpus: CorpusStore,
    ) -> None:
        self.parser = parser
        self.chunker = chunker
        self.embeddings = embeddings
        self.corpus = corpus

    async def ingest(self, path: str | Path, *, paper_id: str | None = None) -> PaperDocument:
        return (await self.ingest_detailed(path, paper_id=paper_id)).paper

    async def ingest_detailed(
        self, path: str | Path, *, paper_id: str | None = None
    ) -> PaperIngestionResult:
        paper, elements = await asyncio.to_thread(self.parser.parse, path, paper_id=paper_id)
        content_hash = await asyncio.to_thread(self._content_hash, paper, elements)
        existing = await self._get_existing(paper.paper_id)
        if existing is not None and existing.content_hash == content_hash:
            return PaperIngestionResult(
                paper=existing,
                elements=elements,
                parents=[],
                children=[],
                status="unchanged",
            )
        paper.content_hash = content_hash
        paper.revision = (existing.revision + 1) if existing is not None else 1
        paper.metadata = {
            **paper.metadata,
            "content_hash": content_hash,
            "source_revision": paper.revision,
        }
        chunks = self.chunker.chunk(elements)
        vectors = await self.embeddings.embed_documents(
            [child.text for child in chunks.children]
        )
        replace = getattr(self.corpus, "replace_paper", None)
        if callable(replace):
            await replace(paper, elements, chunks.parents, chunks.children, vectors)
        else:  # compatibility with pre-lifecycle CorpusStore implementations
            await self.corpus.upsert_paper(
                paper, elements, chunks.parents, chunks.children, vectors
            )
        return PaperIngestionResult(
            paper=paper,
            elements=elements,
            parents=chunks.parents,
            children=chunks.children,
            status="updated" if existing is not None else "created",
        )

    async def _get_existing(self, paper_id: str) -> PaperDocument | None:
        get_papers = getattr(self.corpus, "get_papers", None)
        if not callable(get_papers):
            return None
        papers = await get_papers([paper_id])
        return papers[0] if papers else None

    @staticmethod
    def _content_hash(paper: PaperDocument, elements: list[SourceElement]) -> str:
        source = Path(paper.source_path)
        if source.is_file():
            digest = sha256()
            with source.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest()
        # Parser adapters used in tests or remote sources may not expose a local file.
        payload = "\n".join(
            f"{element.element_id}|{element.element_type}|{element.text}"
            for element in elements
        )
        return sha256(payload.encode("utf-8")).hexdigest()
