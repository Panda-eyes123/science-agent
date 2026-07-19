"""Application-facing ports for raw paper retrieval and persistence."""

from typing import Protocol

from science_agent.rag.types import (
    ChildChunk,
    ParentChunk,
    PaperDocument,
    RetrievalHit,
    SourceElement,
)


class CorpusStore(Protocol):
    """Store paper provenance and retrieval chunks.

    ``replace_paper`` is the lifecycle-aware operation. ``upsert_paper`` remains
    in the protocol for downstream stores that have not migrated yet.
    """

    async def replace_paper(
        self,
        paper: PaperDocument,
        elements: list[SourceElement],
        parents: list[ParentChunk],
        children: list[ChildChunk],
        embeddings: list[list[float]],
    ) -> None: ...

    async def upsert_paper(
        self,
        paper: PaperDocument,
        elements: list[SourceElement],
        parents: list[ParentChunk],
        children: list[ChildChunk],
        embeddings: list[list[float]],
    ) -> None: ...

    async def delete_paper(self, paper_id: str) -> None: ...

    async def search_bm25(
        self,
        query: str,
        *,
        limit: int,
        section_kind: str | None = None,
        chunk_types: tuple[str, ...] | None = None,
    ) -> list[RetrievalHit]: ...

    async def search_dense(
        self,
        vector: list[float],
        *,
        limit: int,
        section_kind: str | None = None,
        chunk_types: tuple[str, ...] | None = None,
    ) -> list[RetrievalHit]: ...

    async def get_parent_chunks(self, chunk_ids: list[str]) -> list[ParentChunk]: ...

    async def get_source_elements(self, element_ids: list[str]) -> list[SourceElement]: ...

    async def get_papers(self, paper_ids: list[str]) -> list[PaperDocument]: ...
