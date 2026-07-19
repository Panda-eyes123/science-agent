"""Build and index a small personal Wiki without external services."""

import asyncio
from tempfile import TemporaryDirectory

from science_agent.infra.wiki import InMemoryWikiIndex, MarkdownWikiRepository
from science_agent.wiki import (
    SourceRef,
    WikiChangeSet,
    WikiClaim,
    WikiOperation,
    WikiPage,
    WikiService,
)


class DemoEmbeddings:
    """Deterministic vectors used only to keep the example offline."""

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.lower()
        return [
            float(len(normalized)),
            float(normalized.count("wiki")),
            float(normalized.count("evidence")),
        ]


async def main() -> None:
    with TemporaryDirectory(prefix="science-agent-wiki-") as directory:
        repository = MarkdownWikiRepository(directory)
        index = InMemoryWikiIndex()
        embeddings = DemoEmbeddings()
        wiki = WikiService(
            repository=repository,
            index=index,
            embeddings=embeddings,
        )

        source = SourceRef(
            paper_id="paper-demo",
            element_id="paper-demo:paragraph:1",
            page_no=1,
            content_hash="demo-source-hash",
        )
        changeset = WikiChangeSet(
            change_id="demo-create-wiki-pages",
            source_hashes=["demo-source-hash"],
            operations=[
                WikiOperation(
                    operation="create_page",
                    page_id="concept/raw-rag",
                    page=WikiPage(
                        page_id="concept/raw-rag",
                        title="Raw RAG evidence",
                        page_type="concept",
                        body="# Raw RAG evidence\n\nRaw retrieval remains the evidence layer.",
                        claims=[
                            WikiClaim(
                                claim_id="claim-raw-evidence",
                                text="Raw RAG preserves the source evidence chain.",
                                sources=[source],
                                status="established",
                            )
                        ],
                    ),
                ),
                WikiOperation(
                    operation="create_page",
                    page_id="concept/wiki-layer",
                    page=WikiPage(
                        page_id="concept/wiki-layer",
                        title="Wiki knowledge layer",
                        page_type="concept",
                        body="# Wiki knowledge layer\n\nWiki pages retain durable synthesis.",
                        aliases=["LLM Wiki"],
                        claims=[
                            WikiClaim(
                                claim_id="claim-wiki-role",
                                text="The Wiki layer organizes durable knowledge.",
                                sources=[source],
                                status="tentative",
                            )
                        ],
                    ),
                ),
                WikiOperation(
                    operation="link_pages",
                    page_id="concept/wiki-layer",
                    target_page_id="concept/raw-rag",
                    expected_revision=0,
                    relation="verified_by",
                ),
            ],
        )

        result = await wiki.apply(changeset)
        hits = await index.search_bm25("durable Wiki knowledge", limit=3)

        print("Wiki root:", directory)
        print("Changed pages:", [page.page_id for page in result.changed_pages])
        print("Search hits:", [(hit.page_id, hit.score) for hit in hits])


if __name__ == "__main__":
    asyncio.run(main())
