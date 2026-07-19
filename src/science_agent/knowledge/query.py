"""Wiki-guided, raw-evidence-grounded query orchestration."""

from dataclasses import replace

from science_agent.knowledge.policy import KnowledgeQueryPolicy
from science_agent.knowledge.ports import RawEvidenceRetriever
from science_agent.knowledge.types import (
    KnowledgeCitation,
    KnowledgeEvidence,
)
from science_agent.wiki.retrieval import WikiRetrievalService
from science_agent.wiki.types import WikiEvidence


class KnowledgeQueryService:
    def __init__(
        self,
        *,
        wiki: WikiRetrievalService,
        raw: RawEvidenceRetriever,
        policy: KnowledgeQueryPolicy | None = None,
        wiki_limit: int = 6,
        raw_limit: int = 12,
        expansion_chars: int = 600,
    ) -> None:
        self.wiki = wiki
        self.raw = raw
        self.policy = policy or KnowledgeQueryPolicy()
        self.wiki_limit = wiki_limit
        self.raw_limit = raw_limit
        self.expansion_chars = expansion_chars

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        section_kind: str | None = None,
    ) -> KnowledgeEvidence:
        plan = self.policy.plan(query)
        wiki = await self.wiki.search(
            query,
            limit=self.wiki_limit,
            expand_links=plan.expand_links,
        )
        warnings = self._wiki_warnings(wiki)
        if not wiki.coverage:
            warnings.append("Wiki coverage is below the retrieval threshold")
            wiki = replace(wiki, hits=[], pages={}, expanded_page_ids=[])
        usable_pages = [
            page
            for page in wiki.pages.values()
            if page.status not in {"stale", "conflicting"}
        ]
        if plan.mode == "wiki_guided" and (not wiki.coverage or not usable_pages):
            plan = replace(
                plan,
                mode="raw_only",
                reasons=[*plan.reasons, "Wiki coverage is missing or stale"],
                expand_links=False,
            )
        raw_query = query
        if plan.mode == "wiki_guided":
            raw_query = self._expanded_query(query, wiki)
        raw = await self.raw.search(
            raw_query,
            limit=limit or self.raw_limit,
            section_kind=section_kind,
        )
        citations = self._citations(wiki, raw.source_elements)
        if wiki.hits and not any(item.verified_in_raw_results for item in citations):
            warnings.append("Wiki citations were not present in the raw retrieval window")
        return KnowledgeEvidence(
            query=query,
            plan=plan,
            wiki=wiki,
            raw=raw,
            citations=citations,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _expanded_query(self, query: str, wiki: WikiEvidence) -> str:
        additions: list[str] = []
        for hit in wiki.hits:
            page = wiki.pages.get(hit.page_id)
            if page is None or page.status in {"stale", "conflicting"}:
                continue
            additions.extend([page.title, *page.aliases])
            additions.extend(
                claim.text
                for claim in page.claims
                if claim.status not in {"stale", "conflicting"}
            )
        expansion = " ".join(dict.fromkeys(additions))[: self.expansion_chars]
        return f"{query}\nRelated Wiki concepts: {expansion}" if expansion else query

    @staticmethod
    def _wiki_warnings(wiki: WikiEvidence) -> list[str]:
        warnings: list[str] = []
        for page in wiki.pages.values():
            if page.status == "stale":
                warnings.append(f"Wiki page '{page.page_id}' is stale")
            elif page.status == "conflicting":
                warnings.append(f"Wiki page '{page.page_id}' contains conflicts")
            for claim in page.claims:
                if claim.status == "stale":
                    warnings.append(
                        f"Wiki claim '{page.page_id}#{claim.claim_id}' is stale"
                    )
                elif claim.status == "conflicting":
                    warnings.append(
                        f"Wiki claim '{page.page_id}#{claim.claim_id}' conflicts"
                    )
        return warnings

    @staticmethod
    def _citations(wiki: WikiEvidence, source_elements: dict) -> list[KnowledgeCitation]:
        citations: list[KnowledgeCitation] = []
        seen: set[tuple[str, str, str]] = set()
        for page in wiki.pages.values():
            for claim in page.claims:
                for reference in claim.sources:
                    key = (page.page_id, claim.claim_id, reference.element_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    citations.append(
                        KnowledgeCitation(
                            reference=reference,
                            page_id=page.page_id,
                            claim_id=claim.claim_id,
                            verified_in_raw_results=(
                                reference.element_id in source_elements
                            ),
                        )
                    )
        return citations
