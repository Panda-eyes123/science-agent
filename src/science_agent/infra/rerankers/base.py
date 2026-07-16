"""Reranker protocol."""

from typing import Protocol

from science_agent.rag.types import RetrievalHit


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[RetrievalHit], *, limit: int) -> list[RetrievalHit]: ...
