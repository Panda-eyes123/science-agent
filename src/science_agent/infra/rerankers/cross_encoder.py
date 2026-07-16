"""Sentence Transformers CrossEncoder adapter with lazy model loading."""

import asyncio
from typing import Any

from science_agent.rag.types import RetrievalHit


class CrossEncoderReranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self.model_name = model_name
        self._model: Any | None = None

    async def rerank(
        self, query: str, hits: list[RetrievalHit], *, limit: int
    ) -> list[RetrievalHit]:
        if not hits or limit <= 0:
            return []
        scores = await asyncio.to_thread(
            self._get_model().predict, [(query, hit.text) for hit in hits]
        )
        ranked = [
            RetrievalHit(
                chunk_id=hit.chunk_id,
                score=float(score),
                text=hit.text,
                paper_id=hit.paper_id,
                parent_chunk_id=hit.parent_chunk_id,
                section_kind=hit.section_kind,
                metadata=hit.metadata,
            )
            for hit, score in zip(hits, scores, strict=True)
        ]
        return sorted(ranked, key=lambda hit: hit.score, reverse=True)[:limit]

    def _get_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ModuleNotFoundError as exc:  # pragma: no cover - dependency boundary
                raise ModuleNotFoundError(
                    "CrossEncoder reranking requires sentence-transformers. "
                    "Install with `pip install science-agent[rag]`."
                ) from exc
            self._model = CrossEncoder(self.model_name)
        return self._model
