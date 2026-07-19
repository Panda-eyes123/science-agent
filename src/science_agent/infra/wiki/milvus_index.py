"""Milvus-backed Wiki index kept separate from the raw paper corpus."""

import asyncio
from dataclasses import asdict
import json
from typing import Any

from science_agent.config import DEFAULT_MILVUS_URI, DEFAULT_WIKI_MILVUS_COLLECTION
from science_agent.wiki.service import WikiService
from science_agent.wiki.types import WikiPage, WikiSearchHit


class MilvusWikiIndex:
    """Index Wiki pages with native BM25 and dense vectors."""

    def __init__(
        self,
        *,
        embedding_dim: int,
        uri: str = DEFAULT_MILVUS_URI,
        collection_name: str = DEFAULT_WIKI_MILVUS_COLLECTION,
    ) -> None:
        self.embedding_dim = embedding_dim
        self.uri = uri
        self.collection_name = collection_name
        self._client: Any | None = None
        self._ready = False

    async def replace_pages(
        self, pages: list[WikiPage], embeddings: list[list[float]]
    ) -> None:
        if len(pages) != len(embeddings):
            raise ValueError("Every Wiki page must have exactly one embedding.")
        if any(len(vector) != self.embedding_dim for vector in embeddings):
            raise ValueError(
                f"Every Wiki embedding must have {self.embedding_dim} dimensions."
            )
        await asyncio.to_thread(self._replace_pages, pages, embeddings)

    async def delete_pages(self, page_ids: list[str]) -> None:
        await asyncio.to_thread(self._delete_pages, page_ids)

    async def search_bm25(self, query: str, *, limit: int) -> list[WikiSearchHit]:
        return await asyncio.to_thread(self._search_bm25, query, limit)

    async def search_dense(
        self, vector: list[float], *, limit: int
    ) -> list[WikiSearchHit]:
        if len(vector) != self.embedding_dim:
            raise ValueError(f"Expected a {self.embedding_dim}-dimension query vector.")
        return await asyncio.to_thread(self._search_dense, vector, limit)

    def _replace_pages(
        self, pages: list[WikiPage], embeddings: list[list[float]]
    ) -> None:
        if not pages:
            return
        rows = [
            {
                "page_id": page.page_id,
                "text": WikiService.index_text(page),
                "dense_vector": vector,
                "title": page.title,
                "page_type": page.page_type,
                "status": page.status,
                "revision": page.revision,
                "metadata": asdict(page),
            }
            for page, vector in zip(pages, embeddings, strict=True)
        ]
        self._ensure_ready().upsert(collection_name=self.collection_name, data=rows)

    def _delete_pages(self, page_ids: list[str]) -> None:
        if not page_ids:
            return
        self._ensure_ready().delete(
            collection_name=self.collection_name,
            filter=f"page_id in {json.dumps(page_ids)}",
        )

    def _search_bm25(self, query: str, limit: int) -> list[WikiSearchHit]:
        result = self._ensure_ready().search(
            collection_name=self.collection_name,
            data=[query],
            anns_field="sparse_vector",
            limit=limit,
            output_fields=self._output_fields(),
        )
        return self._hits(result)

    def _search_dense(self, vector: list[float], limit: int) -> list[WikiSearchHit]:
        result = self._ensure_ready().search(
            collection_name=self.collection_name,
            data=[vector],
            anns_field="dense_vector",
            limit=limit,
            output_fields=self._output_fields(),
        )
        return self._hits(result)

    def _ensure_ready(self) -> Any:
        client = self._get_client()
        if self._ready:
            return client
        try:
            from pymilvus import DataType, Function, FunctionType
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency boundary
            raise ModuleNotFoundError(
                "Milvus Wiki indexing requires pymilvus. "
                "Install with `pip install science-agent[rag]`."
            ) from exc
        if not client.has_collection(collection_name=self.collection_name):
            schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field(
                "page_id", DataType.VARCHAR, is_primary=True, max_length=256
            )
            schema.add_field(
                "text", DataType.VARCHAR, max_length=65535, enable_analyzer=True
            )
            schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
            schema.add_field(
                "dense_vector", DataType.FLOAT_VECTOR, dim=self.embedding_dim
            )
            schema.add_field("title", DataType.VARCHAR, max_length=1024)
            schema.add_field("page_type", DataType.VARCHAR, max_length=32)
            schema.add_field("status", DataType.VARCHAR, max_length=32)
            schema.add_field("revision", DataType.INT64)
            schema.add_field("metadata", DataType.JSON)
            schema.add_function(
                Function(
                    name="wiki_bm25",
                    input_field_names=["text"],
                    output_field_names=["sparse_vector"],
                    function_type=FunctionType.BM25,
                )
            )
            index = client.prepare_index_params()
            index.add_index(
                "dense_vector", index_type="AUTOINDEX", metric_type="COSINE"
            )
            index.add_index(
                "sparse_vector",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="BM25",
            )
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
            except ModuleNotFoundError as exc:  # pragma: no cover
                raise ModuleNotFoundError(
                    "Milvus Wiki indexing requires pymilvus. "
                    "Install with `pip install science-agent[rag]`."
                ) from exc
            self._client = MilvusClient(uri=self.uri)
        return self._client

    @staticmethod
    def _output_fields() -> list[str]:
        return ["page_id", "text", "title", "page_type", "status", "revision"]

    @staticmethod
    def _hits(result: list[list[dict[str, Any]]]) -> list[WikiSearchHit]:
        rows = result[0] if result else []
        hits: list[WikiSearchHit] = []
        for row in rows:
            entity = row.get("entity", row)
            hits.append(
                WikiSearchHit(
                    page_id=entity["page_id"],
                    score=float(row.get("distance", row.get("score", 0.0))),
                    title=entity.get("title", ""),
                    text=entity.get("text", ""),
                    page_type=entity.get("page_type"),
                    status=entity.get("status"),
                    revision=entity.get("revision"),
                )
            )
        return hits
