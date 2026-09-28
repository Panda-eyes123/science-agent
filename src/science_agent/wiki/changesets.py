"""Compile, validate, and apply reviewable Wiki changesets."""

from .ports import WikiCompiler, WikiPageStore
from .types import RawSourceSnapshot, WikiChangeset, WikiPage


class WikiValidationError(ValueError):
    """Raised when a compiler proposal cannot be accepted for review."""


class WikiVersionConflict(RuntimeError):
    """Raised when a page changed after a changeset was generated."""


def validate_markdown(markdown: str) -> None:
    if not markdown.strip():
        raise WikiValidationError("Wiki Markdown must not be empty.")
    if "\x00" in markdown:
        raise WikiValidationError("Wiki Markdown contains a NUL character.")
    if not any(line.lstrip().startswith("# ") for line in markdown.splitlines()):
        raise WikiValidationError("Wiki Markdown must contain a level-one title.")


class WikiChangesetService:
    def __init__(self, pages: WikiPageStore) -> None:
        self.pages = pages

    async def propose(
        self,
        *,
        page_id: str,
        snapshots: tuple[RawSourceSnapshot, ...],
        instruction: str,
        compiler: WikiCompiler,
    ) -> WikiChangeset:
        page = await self.pages.get(page_id)
        if page is None:
            raise KeyError(f"Unknown Wiki page: {page_id}")
        if not snapshots:
            raise WikiValidationError("A changeset requires at least one raw snapshot.")

        draft = await compiler.compile(
            page=page, snapshots=snapshots, instruction=instruction
        )
        validate_markdown(draft.markdown)
        allowed = frozenset(
            citation for snapshot in snapshots for citation in snapshot.citation_keys()
        )
        unknown = sorted(set(draft.citation_keys) - allowed)
        if unknown:
            raise WikiValidationError(
                f"Changeset contains citations outside the snapshot whitelist: {unknown}"
            )
        return WikiChangeset(
            changeset_id=f"cs_{page_id}_{page.version + 1}",
            page_id=page.page_id,
            base_version=page.version,
            base_markdown=page.markdown,
            proposed_markdown=draft.markdown,
            summary=draft.summary,
            citation_keys=draft.citation_keys,
        )

    async def apply(
        self,
        changeset: WikiChangeset,
        *,
        approved: bool,
        snapshots: tuple[RawSourceSnapshot, ...],
    ) -> WikiPage:
        if not approved:
            changeset.status = "rejected"
            raise WikiValidationError("Changeset was not approved.")
        if changeset.status != "pending":
            raise WikiValidationError("Only pending changesets can be applied.")
        page = await self.pages.get(changeset.page_id)
        if page is None:
            raise KeyError(f"Unknown Wiki page: {changeset.page_id}")
        if page.version != changeset.base_version or page.markdown != changeset.base_markdown:
            raise WikiVersionConflict(
                f"Wiki page {page.page_id} changed after this changeset was generated."
            )
        allowed = frozenset(
            citation for snapshot in snapshots for citation in snapshot.citation_keys()
        )
        if not set(changeset.citation_keys).issubset(allowed):
            raise WikiValidationError("Changeset citations no longer match the snapshot whitelist.")
        validate_markdown(changeset.proposed_markdown)
        updated = WikiPage(
            page_id=page.page_id,
            title=page.title,
            markdown=changeset.proposed_markdown,
            version=page.version + 1,
            source_snapshot_ids=[snapshot.snapshot_id for snapshot in snapshots],
            status="fresh",
            stale_sources=[],
        )
        result = await self.pages.put(updated, expected_version=changeset.base_version)
        changeset.status = "applied"
        return result

    async def mark_stale(self, snapshot_id: str) -> list[WikiPage]:
        """Mark dependent pages stale without rewriting their authoritative Markdown."""
        updated_pages: list[WikiPage] = []
        for page in await self.pages.list():
            if snapshot_id not in page.source_snapshot_ids:
                continue
            if snapshot_id in page.stale_sources and page.status == "stale":
                updated_pages.append(page)
                continue
            stale = WikiPage(
                page_id=page.page_id,
                title=page.title,
                markdown=page.markdown,
                version=page.version,
                source_snapshot_ids=page.source_snapshot_ids,
                status="stale",
                stale_sources=[*page.stale_sources, snapshot_id],
                updated_at=page.updated_at,
            )
            updated_pages.append(
                await self.pages.put(stale, expected_version=page.version)
            )
        return updated_pages
