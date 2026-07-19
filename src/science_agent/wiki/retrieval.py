"""Hybrid Wiki retrieval and bounded wikilink expansion."""

import asyncio
from dataclasses import replace

from science_agent.wiki.ports import WikiEmbedder, WikiRepository, WikiSearchIndex
from science_agent.wiki.types import WikiEvidence, WikiPage, WikiSearchHit


def reciprocal_rank_fusion(
    result_sets: list[list[WikiSearchHit]],
    *,
    k: int = 60,
    limit: int | None = None,
) -> list[WikiSearchHit]:
    if k < 1:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    best: dict[str, WikiSearchHit] = {}
    for result_set in result_sets:
        for rank, hit in enumerate(result_set, start=1):
            scores[hit.page_id] = scores.get(hit.page_id, 0.0) + 1.0 / (k + rank)
            current = best.get(hit.page_id)
            if current is None or hit.score > current.score:
                best[hit.page_id] = hit
    fused = [
        replace(best[page_id], score=score) for page_id, score in scores.items()
    ]
    fused.sort(key=lambda hit: (-hit.score, hit.page_id))
    return fused[:limit] if limit is not None else fused


class WikiRetrievalService:
    def __init__(
        self,
        *,
        repository: WikiRepository,
        index: WikiSearchIndex,
        embeddings: WikiEmbedder,
        recall_limit: int = 20,
        result_limit: int = 6,
        link_limit: int = 8,
        min_dense_score: float = 0.2,
    ) -> None:
        self.repository = repository
        self.index = index
        self.embeddings = embeddings
        self.recall_limit = recall_limit
        self.result_limit = result_limit
        self.link_limit = link_limit
        self.min_dense_score = min_dense_score

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        expand_links: bool = True,
    ) -> WikiEvidence:
        requested_limit = limit or self.result_limit
        vector = await self.embeddings.embed_query(query)
        bm25_hits, dense_hits = await asyncio.gather(
            self.index.search_bm25(query, limit=self.recall_limit),
            self.index.search_dense(vector, limit=self.recall_limit),
        )
        hits = reciprocal_rank_fusion(
            [bm25_hits, dense_hits], limit=requested_limit
        )
        direct_ids = [hit.page_id for hit in hits]
        pages = await self._get_pages(direct_ids)
        expanded_ids: list[str] = []
        if expand_links:
            linked_ids = [
                link.target_page_id
                for page_id in direct_ids
                if (page := pages.get(page_id)) is not None
                for link in page.links
                if link.target_page_id not in pages
            ]
            expanded_ids = list(dict.fromkeys(linked_ids))[: self.link_limit]
            pages.update(await self._get_pages(expanded_ids))
        return WikiEvidence(
            query=query,
            hits=hits,
            pages=pages,
            expanded_page_ids=[page_id for page_id in expanded_ids if page_id in pages],
            coverage=(
                bool(bm25_hits)
                or any(hit.score >= self.min_dense_score for hit in dense_hits)
            ),
        )

    async def _get_pages(self, page_ids: list[str]) -> dict[str, WikiPage]:
        resolved = await asyncio.gather(
            *(self.repository.get_page(page_id) for page_id in page_ids)
        )
        return {
            page.page_id: page
            for page in resolved
            if page is not None
        }
