"""Rebuildable Wiki index orchestration.

Markdown pages remain authoritative. An index implementation may be deleted and
rebuilt from the page store without changing Wiki content or page versions.
"""

from typing import Protocol

from science_agent.infra.embeddings.base import EmbeddingProvider

from .ports import WikiPageStore
from .types import WikiPage


class WikiIndex(Protocol):
    async def clear(self) -> None: ...

    async def upsert_pages(
        self, pages: list[WikiPage], embeddings: list[list[float]]
    ) -> None: ...


class WikiIndexRebuilder:
    def __init__(self, *, pages: WikiPageStore, embeddings: EmbeddingProvider) -> None:
        self.pages = pages
        self.embeddings = embeddings

    async def rebuild(self, index: WikiIndex) -> int:
        pages = await self.pages.list()
        await index.clear()
        if not pages:
            return 0
        vectors = await self.embeddings.embed_documents(
            [page.markdown for page in pages]
        )
        await index.upsert_pages(pages, vectors)
        return len(pages)
