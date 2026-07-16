"""Hybrid retrieval orchestration and provenance backtrace."""

import asyncio
from dataclasses import replace

from science_agent.infra.corpus.types import CorpusStore
from science_agent.infra.embeddings.base import EmbeddingProvider
from science_agent.infra.rerankers.base import Reranker
from science_agent.rag.routing import route_query
from science_agent.rag.types import EvidencePack, RetrievalHit


def reciprocal_rank_fusion(
    result_sets: list[list[RetrievalHit]],
    *,
    k: int = 60,
    limit: int | None = None,
) -> list[RetrievalHit]:
    """Fuse ranked lists while keeping the richest version of each hit."""
    if k < 1:
        raise ValueError("k must be positive")
    scores: dict[str, float] = {}
    best_hits: dict[str, RetrievalHit] = {}
    for result_set in result_sets:
        for rank, hit in enumerate(result_set, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            existing = best_hits.get(hit.chunk_id)
            if existing is None or hit.score > existing.score:
                best_hits[hit.chunk_id] = hit
    fused = [replace(best_hits[chunk_id], score=score) for chunk_id, score in scores.items()]
    fused.sort(key=lambda hit: hit.score, reverse=True)
    return fused[:limit] if limit is not None else fused


class RetrievalService:
    def __init__(
        self,
        *,
        corpus: CorpusStore,
        embeddings: EmbeddingProvider,
        reranker: Reranker,
        recall_limit: int = 80,
        fusion_limit: int = 40,
        result_limit: int = 12,
    ) -> None:
        self.corpus = corpus
        self.embeddings = embeddings
        self.reranker = reranker
        self.recall_limit = recall_limit
        self.fusion_limit = fusion_limit
        self.result_limit = result_limit

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        section_kind: str | None = None,
    ) -> EvidencePack:
        requested_limit = limit or self.result_limit
        route = section_kind or route_query(query)
        query_vector = await asyncio.to_thread(self.embeddings.embed_query, query)
        bm25_hits, dense_hits = await asyncio.gather(
            self.corpus.search_bm25(query, limit=self.recall_limit, section_kind=route),
            self.corpus.search_dense(query_vector, limit=self.recall_limit, section_kind=route),
        )
        fused = reciprocal_rank_fusion([bm25_hits, dense_hits], limit=self.fusion_limit)
        reranked = await asyncio.to_thread(
            self.reranker.rerank, query, fused, limit=requested_limit
        )
        parent_ids = list(dict.fromkeys(hit.parent_chunk_id for hit in reranked if hit.parent_chunk_id))
        parents = await self.corpus.get_parent_chunks(parent_ids)
        parents_by_id = {parent.chunk_id: parent for parent in parents}
        element_ids = list(
            dict.fromkeys(
                element_id
                for parent in parents
                for element_id in parent.source_element_ids
            )
        )
        elements = await self.corpus.get_source_elements(element_ids)
        return EvidencePack(
            query=query,
            hits=reranked,
            parents=parents_by_id,
            source_elements={element.element_id: element for element in elements},
            route=route,
        )
