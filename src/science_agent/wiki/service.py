"""Application service for validated Wiki updates and index projection."""

from science_agent.wiki.ports import WikiEmbedder, WikiRepository, WikiSearchIndex
from science_agent.wiki.types import WikiApplyResult, WikiChangeSet, WikiPage
from science_agent.wiki.validation import ensure_valid_changeset


class WikiService:
    def __init__(
        self,
        *,
        repository: WikiRepository,
        index: WikiSearchIndex,
        embeddings: WikiEmbedder,
    ) -> None:
        self.repository = repository
        self.index = index
        self.embeddings = embeddings

    async def apply(self, changeset: WikiChangeSet) -> WikiApplyResult:
        ensure_valid_changeset(changeset)
        result = await self.repository.apply(changeset)
        if result.changed_pages:
            vectors = await self.embeddings.embed_documents(
                [self.index_text(page) for page in result.changed_pages]
            )
            await self.index.replace_pages(result.changed_pages, vectors)
        if result.deleted_page_ids:
            await self.index.delete_pages(result.deleted_page_ids)
        return result

    async def reindex_all(self) -> int:
        pages = await self.repository.list_pages()
        if not pages:
            return 0
        vectors = await self.embeddings.embed_documents(
            [self.index_text(page) for page in pages]
        )
        await self.index.replace_pages(pages, vectors)
        return len(pages)

    @staticmethod
    def index_text(page: WikiPage) -> str:
        parts = [page.title, *page.aliases, page.body]
        parts.extend(claim.text for claim in page.claims)
        return "\n".join(part for part in parts if part).strip()
