"""Ports owned by the Wiki domain."""

from typing import Protocol

from science_agent.wiki.types import (
    WikiApplyResult,
    WikiChangeSet,
    WikiPage,
    WikiSearchHit,
    WikiSourceSnapshot,
)


class WikiRepository(Protocol):
    async def get_page(self, page_id: str) -> WikiPage | None: ...

    async def list_pages(self) -> list[WikiPage]: ...

    async def apply(self, changeset: WikiChangeSet) -> WikiApplyResult: ...


class WikiDraftStore(Protocol):
    async def save(self, changeset: WikiChangeSet) -> None: ...

    async def get(self, change_id: str) -> WikiChangeSet | None: ...

    async def list(self) -> list[WikiChangeSet]: ...

    async def delete(self, change_id: str) -> None: ...


class WikiSearchIndex(Protocol):
    async def replace_pages(
        self, pages: list[WikiPage], embeddings: list[list[float]]
    ) -> None: ...

    async def delete_pages(self, page_ids: list[str]) -> None: ...

    async def search_bm25(self, query: str, *, limit: int) -> list[WikiSearchHit]: ...

    async def search_dense(
        self, vector: list[float], *, limit: int
    ) -> list[WikiSearchHit]: ...


class WikiEmbedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class WikiCompiler(Protocol):
    async def plan(
        self,
        source: WikiSourceSnapshot,
        related_pages: list[WikiPage],
    ) -> WikiChangeSet: ...
