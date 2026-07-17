"""OpenAI-compatible embeddings adapter."""

import json
import os

import httpx

from science_agent.config import DEFAULT_EMBEDDING_MODEL


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = model or DEFAULT_EMBEDDING_MODEL
        self.base_url = (
            base_url or os.getenv("EMBEDDING_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")
        self.timeout = timeout

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        data = await self._request(texts)
        data.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in data]

    async def embed_query(self, text: str) -> list[float]:
        data = await self._request([text])
        return data[0]["embedding"]

    async def _request(self, texts: list[str]) -> list[dict]:
        if not self.api_key:
            raise ValueError("Embedding API key is not set. Set EMBEDDING_API_KEY or OPENAI_API_KEY.")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "input": texts},
            )
        if response.status_code >= 400:
            try:
                body = response.json()
                message = body.get("error", {}).get("message", response.text)
            except (json.JSONDecodeError, AttributeError):
                message = response.text
            raise ValueError(f"Embeddings request failed: {response.status_code} {message}")
        return response.json()["data"]
