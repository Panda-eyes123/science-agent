"""Paper ingestion service coordinating parse, chunking, embeddings, and storage."""

import asyncio
from pathlib import Path

from science_agent.infra.corpus.types import CorpusStore
from science_agent.infra.document_parsing.types import DocumentParser
from science_agent.infra.embeddings.base import EmbeddingProvider
from science_agent.rag.chunking import PaperChunker
from science_agent.rag.types import PaperDocument


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
        paper, elements = await asyncio.to_thread(self.parser.parse, path, paper_id=paper_id)
        chunks = self.chunker.chunk(elements)
        vectors = await self.embeddings.embed_documents(
            [child.text for child in chunks.children]
        )
        await self.corpus.upsert_paper(paper, elements, chunks.parents, chunks.children, vectors)
        return paper
