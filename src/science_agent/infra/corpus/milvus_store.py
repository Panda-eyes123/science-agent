"""Milvus-backed paper corpus using native BM25 and dense vector search."""

import asyncio
import json
from dataclasses import asdict
from typing import Any

from science_agent.config import DEFAULT_MILVUS_COLLECTION, DEFAULT_MILVUS_URI
from science_agent.rag.types import (
    ChildChunk,
    ParentChunk,
    PaperDocument,
    RetrievalHit,
    SourceElement,
)


class MilvusCorpusStore:
    """Persist paper provenance and child vectors in local or remote Milvus.

    The vector collection needs Milvus 2.5+ native BM25 functions. The default URI
    points at the Docker Compose Milvus Standalone service exposed on localhost.
    """

    def __init__(
        self,
        *,
        uri: str = DEFAULT_MILVUS_URI,
        collection_name: str = DEFAULT_MILVUS_COLLECTION,
        embedding_dim: int,
    ) -> None:
        self.uri = uri
        self.collection_name = collection_name
        self.records_collection = f"{collection_name}_records"
        self.embedding_dim = embedding_dim
        self._client: Any | None = None
        self._ready = False

    async def upsert_paper(
        self,
        paper: PaperDocument,
        elements: list[SourceElement],
        parents: list[ParentChunk],
        children: list[ChildChunk],
        embeddings: list[list[float]],
    ) -> None:
        await self.replace_paper(paper, elements, parents, children, embeddings)

    async def replace_paper(
        self,
        paper: PaperDocument,
        elements: list[SourceElement],
        parents: list[ParentChunk],
        children: list[ChildChunk],
        embeddings: list[list[float]],
    ) -> None:
        if len(children) != len(embeddings):
            raise ValueError("Every child chunk must have exactly one dense embedding.")
        await self._run(
            self._replace_paper, paper, elements, parents, children, embeddings
        )

    async def delete_paper(self, paper_id: str) -> None:
        await self._run(self._delete_paper, paper_id)

    async def search_bm25(
        self,
        query: str,
        *,
        limit: int,
        section_kind: str | None = None,
        chunk_types: tuple[str, ...] | None = None,
    ) -> list[RetrievalHit]:
        return await self._run(
            self._search_bm25, query, limit, section_kind, chunk_types
        )

    async def search_dense(
        self,
        vector: list[float],
        *,
        limit: int,
        section_kind: str | None = None,
        chunk_types: tuple[str, ...] | None = None,
    ) -> list[RetrievalHit]:
        if len(vector) != self.embedding_dim:
            raise ValueError(f"Expected a {self.embedding_dim}-dimension query vector.")
        return await self._run(
            self._search_dense, vector, limit, section_kind, chunk_types
        )

    async def get_parent_chunks(self, chunk_ids: list[str]) -> list[ParentChunk]:
        return await self._run(self._get_records, "parent", chunk_ids, ParentChunk)

    async def get_source_elements(self, element_ids: list[str]) -> list[SourceElement]:
        return await self._run(self._get_records, "element", element_ids, SourceElement)

    async def get_papers(self, paper_ids: list[str]) -> list[PaperDocument]:
        return await self._run(self._get_records, "paper", paper_ids, PaperDocument)

    async def _run(self, function: Any, *args: Any) -> Any:
        return await asyncio.to_thread(function, *args)

    def _replace_paper(
        self,
        paper: PaperDocument,
        elements: list[SourceElement],
        parents: list[ParentChunk],
        children: list[ChildChunk],
        embeddings: list[list[float]],
    ) -> None:
        client = self._ensure_ready()
        self._delete_paper(paper.paper_id, client=client)
        chunk_rows = [
            {
                "chunk_id": child.chunk_id,
                "text": child.text,
                "dense_vector": embedding,
                "paper_id": child.paper_id,
                "parent_chunk_id": child.parent_chunk_id,
                "section_kind": child.section_kind,
                "metadata": {
                    **asdict(child),
                    "content_hash": paper.content_hash,
                    "source_revision": paper.revision,
                },
            }
            for child, embedding in zip(children, embeddings, strict=True)
        ]
        if chunk_rows:
            client.upsert(collection_name=self.collection_name, data=chunk_rows)
        records = [
            self._record("paper", paper.paper_id, paper),
            *[
                self._record("element", element.element_id, element)
                for element in elements
            ],
            *[self._record("parent", parent.chunk_id, parent) for parent in parents],
        ]
        client.upsert(collection_name=self.records_collection, data=records)

    def _delete_paper(self, paper_id: str, *, client: Any | None = None) -> None:
        client = client or self._ensure_ready()
        value = json.dumps(paper_id)
        client.delete(collection_name=self.collection_name, filter=f"paper_id == {value}")
        client.delete(
            collection_name=self.records_collection,
            filter=f'payload["paper_id"] == {value}',
        )

    def _search_bm25(
        self,
        query: str,
        limit: int,
        section_kind: str | None,
        chunk_types: tuple[str, ...] | None,
    ) -> list[RetrievalHit]:
        client = self._ensure_ready()
        return self._hits(
            client.search(
                collection_name=self.collection_name,
                data=[query],
                anns_field="sparse_vector",
                limit=limit,
                filter=self._search_filter(section_kind, chunk_types),
                output_fields=self._chunk_fields(),
            )
        )

    def _search_dense(
        self,
        vector: list[float],
        limit: int,
        section_kind: str | None,
        chunk_types: tuple[str, ...] | None,
    ) -> list[RetrievalHit]:
        client = self._ensure_ready()
        return self._hits(
            client.search(
                collection_name=self.collection_name,
                data=[vector],
                anns_field="dense_vector",
                limit=limit,
                filter=self._search_filter(section_kind, chunk_types),
                output_fields=self._chunk_fields(),
            )
        )

    def _get_records(self, record_type: str, ids: list[str], model: Any) -> list[Any]:
        if not ids:
            return []
        client = self._ensure_ready()
        escaped = ", ".join(
            f'"{item.replace("\\", "\\\\").replace(chr(34), '\\"')}"' for item in ids
        )
        rows = client.query(
            collection_name=self.records_collection,
            filter=f'record_type == "{record_type}" and record_id in [{escaped}]',
            output_fields=["payload"],
        )
        return [model(**row["payload"]) for row in rows]

    def _ensure_ready(self) -> Any:
        client = self._get_client()
        if self._ready:
            return client
        try:
            from pymilvus import DataType, Function, FunctionType
        except ModuleNotFoundError as exc:  # pragma: no cover - dependency boundary
            raise ModuleNotFoundError(
                "Milvus storage requires pymilvus. Install with `pip install science-agent[rag]`."
            ) from exc
        if not client.has_collection(collection_name=self.collection_name):
            schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field(
                "chunk_id", DataType.VARCHAR, is_primary=True, max_length=128
            )
            schema.add_field(
                "text", DataType.VARCHAR, max_length=65535, enable_analyzer=True
            )
            schema.add_field("sparse_vector", DataType.SPARSE_FLOAT_VECTOR)
            schema.add_field(
                "dense_vector", DataType.FLOAT_VECTOR, dim=self.embedding_dim
            )
            schema.add_field("paper_id", DataType.VARCHAR, max_length=128)
            schema.add_field("parent_chunk_id", DataType.VARCHAR, max_length=128)
            schema.add_field("section_kind", DataType.VARCHAR, max_length=32)
            schema.add_field("metadata", DataType.JSON)
            schema.add_function(
                Function(
                    name="paper_bm25",
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
                "sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25"
            )
            client.create_collection(
                collection_name=self.collection_name,
                schema=schema,
                index_params=index,
            )
        if not client.has_collection(collection_name=self.records_collection):
            schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field(
                "record_id", DataType.VARCHAR, is_primary=True, max_length=128
            )
            schema.add_field("record_type", DataType.VARCHAR, max_length=32)
            schema.add_field("payload", DataType.JSON)
            client.create_collection(
                collection_name=self.records_collection, schema=schema
            )
        self._ready = True
        return client

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from pymilvus import MilvusClient
            except ModuleNotFoundError as exc:  # pragma: no cover - dependency boundary
                raise ModuleNotFoundError(
                    "Milvus storage requires pymilvus. Install with `pip install science-agent[rag]`."
                ) from exc
            self._client = MilvusClient(uri=self.uri)
        return self._client

    @staticmethod
    def _record(record_type: str, record_id: str, payload: Any) -> dict[str, Any]:
        return {
            "record_id": record_id,
            "record_type": record_type,
            "payload": asdict(payload),
        }

    @staticmethod
    def _search_filter(
        section_kind: str | None, chunk_types: tuple[str, ...] | None
    ) -> str:
        conditions: list[str] = []
        if section_kind:
            conditions.append(f"section_kind == {json.dumps(section_kind)}")
        if chunk_types:
            values = json.dumps(list(chunk_types))
            conditions.append(f'metadata["chunk_type"] in {values}')
        return " and ".join(conditions)

    @staticmethod
    def _chunk_fields() -> list[str]:
        return [
            "chunk_id",
            "text",
            "paper_id",
            "parent_chunk_id",
            "section_kind",
            "metadata",
        ]

    @staticmethod
    def _hits(result: list[list[dict[str, Any]]]) -> list[RetrievalHit]:
        rows = result[0] if result else []
        hits: list[RetrievalHit] = []
        for row in rows:
            entity = row.get("entity", row)
            hits.append(
                RetrievalHit(
                    chunk_id=entity["chunk_id"],
                    score=float(row.get("distance", row.get("score", 0.0))),
                    text=entity.get("text", ""),
                    paper_id=entity.get("paper_id"),
                    parent_chunk_id=entity.get("parent_chunk_id"),
                    section_kind=entity.get("section_kind"),
                    metadata=entity.get("metadata", {}),
                )
            )
        return hits
