import pytest

from science_agent.infra.wiki import InMemoryWikiIndex, MarkdownWikiRepository
from science_agent.wiki import (
    SourceRef,
    WikiChangeSet,
    WikiClaim,
    WikiConflictError,
    WikiOperation,
    WikiPage,
    WikiService,
    WikiValidationError,
)


class FakeEmbeddings:
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0]


def _page(page_id: str = "concept/wiki") -> WikiPage:
    return WikiPage(
        page_id=page_id,
        title="Wiki layer",
        page_type="concept",
        body="# Wiki layer\n\nDurable evidence-backed knowledge.",
        claims=[
            WikiClaim(
                claim_id="claim-1",
                text="Wiki claims retain raw citations.",
                sources=[
                    SourceRef(
                        paper_id="paper-1",
                        element_id="paper-1:element:1",
                        page_no=1,
                        content_hash="hash-1",
                    )
                ],
            )
        ],
    )


@pytest.mark.asyncio
async def test_wiki_changeset_round_trips_and_is_idempotent(tmp_path):
    repository = MarkdownWikiRepository(tmp_path / "wiki")
    index = InMemoryWikiIndex()
    service = WikiService(
        repository=repository,
        index=index,
        embeddings=FakeEmbeddings(),
    )
    changeset = WikiChangeSet(
        change_id="create-wiki",
        operations=[
            WikiOperation(
                operation="create_page",
                page_id="concept/wiki",
                page=_page(),
            )
        ],
    )

    first = await service.apply(changeset)
    second = await service.apply(changeset)
    stored = await repository.get_page("concept/wiki")
    hits = await index.search_bm25("durable knowledge", limit=2)

    assert first.changed_pages[0].revision == 1
    assert second.changed_pages[0].revision == 1
    assert stored is not None
    assert stored.claims[0].sources[0].element_id == "paper-1:element:1"
    assert hits[0].page_id == "concept/wiki"
    assert (tmp_path / "wiki" / "concept" / "wiki.md").is_file()


@pytest.mark.asyncio
async def test_wiki_update_rejects_stale_revision(tmp_path):
    repository = MarkdownWikiRepository(tmp_path / "wiki")
    service = WikiService(
        repository=repository,
        index=InMemoryWikiIndex(),
        embeddings=FakeEmbeddings(),
    )
    await service.apply(
        WikiChangeSet(
            change_id="create-wiki",
            operations=[
                WikiOperation(
                    operation="create_page",
                    page_id="concept/wiki",
                    page=_page(),
                )
            ],
        )
    )

    with pytest.raises(WikiConflictError):
        await service.apply(
            WikiChangeSet(
                change_id="stale-update",
                operations=[
                    WikiOperation(
                        operation="update_page",
                        page_id="concept/wiki",
                        page=_page(),
                        expected_revision=0,
                    )
                ],
            )
        )


@pytest.mark.asyncio
async def test_external_markdown_edit_advances_virtual_revision(tmp_path):
    root = tmp_path / "wiki"
    repository = MarkdownWikiRepository(root)
    service = WikiService(
        repository=repository,
        index=InMemoryWikiIndex(),
        embeddings=FakeEmbeddings(),
    )
    await service.apply(
        WikiChangeSet(
            change_id="create-before-external-edit",
            operations=[
                WikiOperation(
                    operation="create_page",
                    page_id="concept/wiki",
                    page=_page(),
                )
            ],
        )
    )
    path = root / "concept" / "wiki.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "Durable evidence-backed knowledge.",
            "Externally edited durable knowledge.",
        ),
        encoding="utf-8",
    )

    edited = await repository.get_page("concept/wiki")

    assert edited is not None
    assert edited.revision == 2


@pytest.mark.asyncio
async def test_wiki_rejects_uncited_claims(tmp_path):
    page = _page()
    page.claims[0].sources = []
    service = WikiService(
        repository=MarkdownWikiRepository(tmp_path / "wiki"),
        index=InMemoryWikiIndex(),
        embeddings=FakeEmbeddings(),
    )

    with pytest.raises(WikiValidationError):
        await service.apply(
            WikiChangeSet(
                change_id="uncited",
                operations=[
                    WikiOperation(
                        operation="create_page",
                        page_id=page.page_id,
                        page=page,
                    )
                ],
            )
        )
