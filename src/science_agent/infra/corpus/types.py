"""Corpus persistence protocol, intentionally separate from agent state storage."""

from typing import Protocol

from science_agent.rag.types import ChildChunk, ParentChunk, PaperDocument, RetrievalHit, SourceElement


class CorpusStore(Protocol):
    async def upsert_paper(
        self,
        paper: PaperDocument,
        elements: list[SourceElement],
        parents: list[ParentChunk],
        children: list[ChildChunk],
        embeddings: list[list[float]],
    ) -> None: ...

    async def search_bm25(
        self,
        query: str,
        *,
        limit: int,
        section_kind: str | None = None,
    ) -> list[RetrievalHit]: ...

    async def search_dense(
        self,
        vector: list[float],
        *,
        limit: int,
        section_kind: str | None = None,
    ) -> list[RetrievalHit]: ...

    async def get_parent_chunks(self, chunk_ids: list[str]) -> list[ParentChunk]: ...

    async def get_source_elements(self, element_ids: list[str]) -> list[SourceElement]: ...
