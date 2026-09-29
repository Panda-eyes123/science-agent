"""Milvus-derived index for Wiki Markdown pages.

The index stores searchable projections only. MarkdownWikiStore remains the
source of truth and can rebuild this collection after data loss or schema change.
"""

import asyncio
import os
from dataclasses import asdict
from typing import Any

from science_agent.infra.embeddings.base import EmbeddingProvider
from science_agent.wiki.types import WikiPage


class MilvusWikiIndex:
    def __init__(
        self,
        *,
        embeddings: EmbeddingProvider,
        uri: str | None = None,
        collection_name: str = "wiki_pages",
        embedding_dim: int,
    ) -> None:
        self.embeddings = embeddings
        self.uri = uri or os.getenv("MILVUS_URI", "http://milvus:19530")
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self._client: Any | None = None
        self._ready = False

    async def clear(self) -> None:
        await asyncio.to_thread(self._clear)

    async def upsert_pages(
        self, pages: list[WikiPage], embeddings: list[list[float]]
    ) -> None:
        if len(pages) != len(embeddings):
            raise ValueError("Every Wiki page must have exactly one embedding.")
        await asyncio.to_thread(self._upsert_pages, pages, embeddings)

    async def search(self, query: str, *, limit: int = 8) -> list[WikiPage]:
        vector = await self.embeddings.embed_query(query)
        if len(vector) != self.embedding_dim:
            raise ValueError(f"Expected a {self.embedding_dim}-dimension query vector.")
        return await asyncio.to_thread(self._search, vector, limit)

    def _clear(self) -> None:
        client = self._get_client()
        if client.has_collection(collection_name=self.collection_name):
            client.drop_collection(collection_name=self.collection_name)
        self._ready = False

    def _upsert_pages(self, pages: list[WikiPage], embeddings: list[list[float]]) -> None:
        client = self._ensure_ready()
        client.upsert(
            collection_name=self.collection_name,
            data=[
                {
                    "page_id": page.page_id,
                    "title": page.title,
                    "text": page.markdown,
                    "dense_vector": vector,
                    "metadata": asdict(page),
                }
                for page, vector in zip(pages, embeddings, strict=True)
            ],
        )

    def _search(self, vector: list[float], limit: int) -> list[WikiPage]:
        client = self._ensure_ready()
        rows = client.search(
            collection_name=self.collection_name,
            data=[vector],
            anns_field="dense_vector",
            limit=limit,
            output_fields=["metadata"],
        )
        return [
            WikiPage(**row.get("entity", row)["metadata"])
            for row in (rows[0] if rows else [])
        ]

    def _ensure_ready(self) -> Any:
        client = self._get_client()
        if self._ready:
            return client
        try:
            from pymilvus import DataType
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency boundary
            raise ModuleNotFoundError(
                "Milvus Wiki indexing requires pymilvus. Install `science-agent[rag]`."
            ) from exc
        if not client.has_collection(collection_name=self.collection_name):
            schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("page_id", DataType.VARCHAR, is_primary=True, max_length=128)
            schema.add_field("title", DataType.VARCHAR, max_length=512)
            schema.add_field("text", DataType.VARCHAR, max_length=65535)
            schema.add_field("dense_vector", DataType.FLOAT_VECTOR, dim=self.embedding_dim)
            schema.add_field("metadata", DataType.JSON)
            index = client.prepare_index_params()
            index.add_index("dense_vector", index_type="AUTOINDEX", metric_type="COSINE")
            client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index,
            )
        self._ready = True
        return client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from pymilvus import MilvusClient
            except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency boundary
                raise ModuleNotFoundError(
                    "Milvus Wiki indexing requires pymilvus. Install `science-agent[rag]`."
                ) from exc
            self._client = MilvusClient(uri=self.uri)
        return self._client
