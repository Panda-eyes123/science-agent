"""Wiki-guided query routing with raw evidence verification."""

from .ports import (
    ClaimVerifier,
    RawEvidenceSearcher,
    WikiContextFormatter,
    WikiPageSearcher,
)
from .types import WikiQueryMode, WikiQueryResult


def format_wiki_context(pages: tuple) -> str:
    return "\n\n".join(
        f"## {page.title}\n{page.markdown}" for page in pages if page.status == "fresh"
    )


class WikiQueryService:
    def __init__(
        self,
        *,
        wiki: WikiPageSearcher,
        raw: RawEvidenceSearcher,
        verifier: ClaimVerifier | None = None,
        context_formatter: WikiContextFormatter = format_wiki_context,
    ) -> None:
        self.wiki = wiki
        self.raw = raw
        self.verifier = verifier
        self.context_formatter = context_formatter

    async def query(self, query: str, *, mode: WikiQueryMode = "wiki_guided") -> WikiQueryResult:
        if mode == "raw_only":
            evidence = await self.raw.search(query)
            return WikiQueryResult(
                query=query,
                mode=mode,
                wiki_pages=(),
                raw_evidence=evidence,
                raw_first=True,
            )

        if mode == "raw_first":
            evidence = await self.raw.search(query)
            pages = tuple(await self.wiki.search(query))
        else:
            pages = tuple(await self.wiki.search(query))
            evidence = await self.raw.search(query)

        verifications = ()
        if self.verifier is not None:
            verifications = tuple(
                await self.verifier.verify(
                    query=query, wiki_pages=pages, evidence=evidence
                )
            )
        return WikiQueryResult(
            query=query,
            mode=mode,
            wiki_pages=pages,
            raw_evidence=evidence,
            claim_verifications=verifications,
            context=self.context_formatter(pages),
            raw_first=mode == "raw_first",
        )
