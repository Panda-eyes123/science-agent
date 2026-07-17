"""API-backed cross-encoder reranking adapter."""

import json
import os

import httpx

from science_agent.rag.types import RetrievalHit


class APIReranker:
    """Call a Jina/Cohere-style rerank endpoint without local model loading."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        endpoint: str | None = None,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = (
            api_key or os.getenv("RERANK_API_KEY") or os.getenv("OPENAI_API_KEY")
        )
        self.model = model or os.getenv("RERANK_MODEL") or "BAAI/bge-reranker-v2-m3"
        self.base_url = (
            base_url
            or os.getenv("RERANK_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        configured_endpoint = endpoint or os.getenv("RERANK_ENDPOINT") or "/rerank"
        self.endpoint = f"/{configured_endpoint.lstrip('/')}"
        self.timeout = timeout
        self.transport = transport

    async def rerank(
        self, query: str, hits: list[RetrievalHit], *, limit: int
    ) -> list[RetrievalHit]:
        if not hits or limit <= 0:
            return []
        if not self.api_key:
            raise ValueError(
                "Rerank API key is not set. Set RERANK_API_KEY or OPENAI_API_KEY."
            )
        payload = {
            "model": self.model,
            "query": query,
            "documents": [hit.text for hit in hits],
            "top_n": min(limit, len(hits)),
            "return_documents": False,
        }
        async with httpx.AsyncClient(
            timeout=self.timeout, transport=self.transport
        ) as client:
            response = await client.post(
                f"{self.base_url}{self.endpoint}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            try:
                body = response.json()
                message = body.get("error", {}).get("message", response.text)
            except (json.JSONDecodeError, AttributeError):
                message = response.text
            raise ValueError(f"Rerank request failed: {response.status_code} {message}")
        try:
            results = response.json()["results"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Rerank response did not contain a results array.") from exc

        reranked: list[RetrievalHit] = []
        for item in results:
            try:
                hit = hits[int(item["index"])]
                score = item.get("relevance_score", item.get("score"))
                reranked.append(
                    RetrievalHit(
                        chunk_id=hit.chunk_id,
                        score=float(score),
                        text=hit.text,
                        paper_id=hit.paper_id,
                        parent_chunk_id=hit.parent_chunk_id,
                        section_kind=hit.section_kind,
                        metadata=hit.metadata,
                    )
                )
            except (IndexError, KeyError, TypeError, ValueError) as exc:
                raise ValueError("Rerank response contained an invalid result.") from exc
        return reranked[:limit]
