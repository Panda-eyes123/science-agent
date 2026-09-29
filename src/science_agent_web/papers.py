"""Managed PDF uploads and indexing; no dependency on HTTP or Agent execution."""

import asyncio
import os
from collections.abc import AsyncIterable
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from science_agent.infra.corpus import MilvusCorpusStore
from science_agent.infra.document_parsing import DoclingPDFParser
from science_agent.infra.embeddings import OpenAIEmbeddingProvider
from science_agent.infra.rerankers import FusionRanker
from science_agent.infra.store.json_store import JSONStore
from science_agent.rag import PaperChunker, PaperIngestionService, RetrievalService
from science_agent.rag.types import EvidencePack
from science_agent.tools import Tool, ToolExecutionContext
from science_agent.types import utc_now_iso

from .errors import ServiceError
from .models import PaperSummary

MAX_PDF_BYTES = 50 * 1024 * 1024


class PaperService:
    def __init__(
        self,
        data_dir: Path,
        store: JSONStore,
        ingestion: PaperIngestionService,
        retrieval: RetrievalService,
    ):
        self.store = store
        self.upload_dir = (data_dir / "papers" / "uploads").resolve()
        self.ingestion = ingestion
        self.retrieval = retrieval
        self.papers: dict[str, PaperSummary] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        # 本地解析耗费 CPU/内存，顺序入库即可；独立会话仍可继续聊天。
        self._index_lock = asyncio.Lock()

    @classmethod
    def from_config(cls, data_dir: Path, store: JSONStore) -> "PaperService":
        embeddings = OpenAIEmbeddingProvider()
        corpus = MilvusCorpusStore(
            uri=os.getenv("MILVUS_URI", "http://127.0.0.1:19530"),
            collection_name=os.getenv("MILVUS_COLLECTION", "science_web_papers"),
            embedding_dim=int(os.getenv("EMBEDDING_DIM", "1536")),
        )
        return cls(
            data_dir,
            store,
            PaperIngestionService(
                parser=DoclingPDFParser(artifact_dir=data_dir / "papers" / "artifacts"),
                chunker=PaperChunker(),
                embeddings=embeddings,
                corpus=corpus,
            ),
            RetrievalService(
                corpus=corpus,
                embeddings=embeddings,
                reranker=FusionRanker(),
                result_limit=6,
            ),
        )

    @property
    def configured(self) -> bool:
        embeddings = self.ingestion.embeddings
        return not isinstance(embeddings, OpenAIEmbeddingProvider) or bool(
            embeddings.api_key and embeddings.api_key != "your-api-key-here"
        )

    async def startup(self) -> None:
        for thread_id in await self.store.list():
            for name in await self.store.list_snapshots(thread_id):
                if name.startswith("paper_"):
                    paper = PaperSummary.model_validate(
                        await self.store.load_snapshot(thread_id, name)
                    )
                    self.papers[paper.paper_id] = paper
                    if paper.status == "indexing":
                        paper.status = "interrupted"
                        paper.error = (
                            "服务已重启，入库未完成；可让助手按论文 ID 重新入库。"
                        )
                        await self._save(paper)

    async def shutdown(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if isinstance(self.ingestion.corpus, MilvusCorpusStore):
            await self.ingestion.corpus.close()

    def list(self) -> list[PaperSummary]:
        return sorted(
            self.papers.values(), key=lambda paper: paper.created_at, reverse=True
        )

    async def upload(
        self, thread_id: str, filename: str, chunks: AsyncIterable[bytes]
    ) -> PaperSummary:
        if not self.configured:
            raise ServiceError(503, "请先配置服务端 Embedding 模型密钥。")
        if Path(filename).suffix.lower() != ".pdf":
            raise ServiceError(415, "仅支持 PDF 文件。")
        paper_id = uuid4().hex
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        target = self.upload_dir / f"{paper_id}.pdf"
        size, prefix = 0, b""
        try:
            with target.open("xb") as output:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        raise ServiceError(413, "PDF 不能超过 50 MB。")
                    if len(prefix) < 5:
                        prefix = (prefix + chunk)[:5]
                    await asyncio.to_thread(output.write, chunk)
            if prefix != b"%PDF-":
                raise ServiceError(415, "文件内容不是有效的 PDF。")
            paper = PaperSummary(
                paper_id=paper_id,
                thread_id=thread_id,
                filename=filename.replace("\\", "/").rsplit("/", 1)[-1],
                status="indexing",
                created_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
            await self._save(paper)
        except BaseException:
            # 仅清理本次生成的文件，文件名从不参与路径拼接。
            target.unlink(missing_ok=True)
            raise
        self.papers[paper_id] = paper
        self.tasks[paper_id] = asyncio.create_task(self._index(paper))
        return paper

    async def _save(self, paper: PaperSummary) -> None:
        paper.updated_at = utc_now_iso()
        await self.store.save_snapshot(
            paper.thread_id, f"paper_{paper.paper_id}", paper.model_dump(mode="json")
        )

    async def _index(self, paper: PaperSummary) -> PaperSummary:
        try:
            async with self._index_lock:
                path = self.upload_dir / f"{paper.paper_id}.pdf"
                document = await self.ingestion.ingest(path, paper_id=paper.paper_id)
                paper.title = document.title
                paper.status = "ready"
                paper.error = None
        except asyncio.CancelledError:
            paper.status = "interrupted"
            paper.error = "服务已停止，入库未完成。"
            raise
        except Exception as exc:
            paper.status = "failed"
            paper.error = str(exc)
        finally:
            await self._save(paper)
            self.tasks.pop(paper.paper_id, None)
        return paper

    async def ingest(self, paper_id: str) -> PaperSummary:
        paper = self.papers.get(paper_id)
        if paper is None:
            raise ServiceError(404, "论文未上传或 ID 不存在。")
        if paper.status == "ready":
            return paper
        task = self.tasks.get(paper_id)
        if task is None:
            paper.status, paper.error = "indexing", None
            await self._save(paper)
            task = self.tasks[paper_id] = asyncio.create_task(self._index(paper))
        # 入库由论文服务持有；用户停止聊天不会取消已经授权的上传入库任务。
        result = await asyncio.shield(task)
        if result.status != "ready":
            raise RuntimeError(result.error or "论文入库失败。")
        return result

    async def search(
        self,
        query: str,
        *,
        limit: int | None = None,
        section_kind: str | None = None,
        chunk_types: tuple[str, ...] | None = None,
    ) -> EvidencePack:
        requested = limit if limit is not None else self.retrieval.result_limit
        if not 1 <= requested <= 12:
            raise ValueError("每次检索数量必须在 1 到 12 之间。")
        ready_ids = {
            paper.paper_id for paper in self.papers.values() if paper.status == "ready"
        }
        if not ready_ids:
            return EvidencePack(query=query, hits=[], parents={}, source_elements={})
        pack = await self.retrieval.search(
            query,
            limit=self.retrieval.fusion_limit,
            section_kind=section_kind,
            chunk_types=chunk_types,
        )
        # Milvus 和本地状态不是同一事务。失败/中断入库残留的片段不能成为网页证据。
        hits = [hit for hit in pack.hits if hit.paper_id in ready_ids][:requested]
        parent_ids = {hit.parent_chunk_id for hit in hits}
        parents = {
            key: value for key, value in pack.parents.items() if key in parent_ids
        }
        element_ids = {
            key for parent in parents.values() for key in parent.source_element_ids
        }
        return replace(
            pack,
            hits=hits,
            parents=parents,
            source_elements={
                key: value
                for key, value in pack.source_elements.items()
                if key in element_ids
            },
            papers={
                key: replace(value, title=value.title or self.papers[key].filename)
                for key, value in pack.papers.items()
                if key in ready_ids
            },
        )

    def ingest_tool(self) -> Tool:
        async def execute(arguments: dict, context: ToolExecutionContext) -> dict:
            return (await self.ingest(arguments["paper_id"])).model_dump(mode="json")

        return Tool(
            name="paper_ingest",
            description="Index an already uploaded PDF by paper_id. Uploads are indexed automatically; use this to retry a failed or interrupted upload. Never accepts local paths.",
            execute=execute,
            readonly=False,
            input_schema={
                "type": "object",
                "properties": {"paper_id": {"type": "string"}},
                "required": ["paper_id"],
            },
        )
