import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from science_agent import (
    JSONStore,
    ModelResponse,
    ModelStreamEnd,
    ModelTextDelta,
    ToolCallRequest,
)
from science_agent.infra.rerankers import FusionRanker
from science_agent.rag import PaperChunker, PaperIngestionService, RetrievalService
from science_agent.rag.types import PaperDocument, RetrievalHit, SourceElement
from science_agent.tools import ToolExecutionContext
from science_agent_web.papers import PaperService
from science_agent_web.service import RunService

create_app = pytest.importorskip(
    "science_agent_web.app", exc_type=ModuleNotFoundError
).create_app


class Corpus:
    def __init__(self):
        self.papers, self.parents, self.elements, self.children = {}, {}, {}, {}

    async def upsert_paper(self, paper, elements, parents, children, embeddings):
        self.papers[paper.paper_id] = paper
        self.parents.update({item.chunk_id: item for item in parents})
        self.elements.update({item.element_id: item for item in elements})
        self.children.update({item.chunk_id: item for item in children})

    async def search_bm25(self, query, *, limit, section_kind=None, chunk_types=None):
        return [
            RetrievalHit(
                chunk_id=child.chunk_id,
                paper_id=child.paper_id,
                parent_chunk_id=child.parent_chunk_id,
                score=1.0,
                text=child.text,
                section_kind=child.section_kind,
            )
            for child in self.children.values()
        ][:limit]

    async def search_dense(self, vector, **kwargs):
        return await self.search_bm25("", **kwargs)

    async def get_parent_chunks(self, ids):
        return [self.parents[key] for key in ids if key in self.parents]

    async def get_source_elements(self, ids):
        return [self.elements[key] for key in ids if key in self.elements]

    async def get_papers(self, ids):
        return [self.papers[key] for key in ids if key in self.papers]


class Parser:
    def parse(self, path, *, paper_id):
        return PaperDocument(
            paper_id=paper_id, source_path=str(path), title="Yeast growth study"
        ), [
            SourceElement(
                element_id=f"{paper_id}:method",
                paper_id=paper_id,
                page_no=2,
                bbox=None,
                element_type="paragraph",
                section_kind="method",
                text="Yeast samples were grown at 30 C with a control group.",
                raw_payload={"secret": "private parser metadata"},
                image_path="C:/private/image.png",
            )
        ]


class Embeddings:
    async def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    async def embed_query(self, text):
        return [1.0, 0.0]


class SearchProvider:
    async def complete(self, messages, **kwargs):
        raise AssertionError("Web must stream")

    async def stream(self, messages, **kwargs):
        names = {item["function"]["name"] for item in kwargs["tools"]}
        assert {"paper_search", "paper_ingest"} <= names
        if messages[-1].role == "user":
            yield ModelStreamEnd(
                response=ModelResponse(
                    tool_calls=[
                        ToolCallRequest(
                            name="paper_search",
                            call_id="search",
                            arguments={"query": "method"},
                        )
                    ]
                )
            )
        else:
            payload = json.loads(messages[-1].content)
            assert payload["evidence_pack"]["items"][0]["sources"][0]["page_no"] == 2
            yield ModelTextDelta(text="样本在 30°C 培养，设有对照组。")
            yield ModelStreamEnd(
                response=ModelResponse(text="样本在 30°C 培养，设有对照组。")
            )


def make_service(tmp_path, embeddings=None):
    corpus, embeddings = Corpus(), embeddings or Embeddings()
    return PaperService(
        tmp_path,
        JSONStore(tmp_path / "store"),
        PaperIngestionService(
            parser=Parser(),
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


async def chunks(data=b"%PDF-1.7\nfixture"):
    yield data[:3]
    yield data[3:]


async def wait_for(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_upload_shared_search_evidence_and_restart(tmp_path):
    papers = make_service(tmp_path)
    runtime = RunService(tmp_path, SearchProvider(), papers=papers)
    app = create_app(runtime)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            first = (await client.post("/api/v1/threads")).json()["id"]
            response = await client.post(
                f"/api/v1/threads/{first}/papers",
                files={
                    "file": ("../research.pdf", b"%PDF-1.7\nfixture", "application/pdf")
                },
            )
            assert response.status_code == 202
            paper_id = response.json()["paper_id"]
            await wait_for(lambda: papers.papers[paper_id].status == "ready")
            assert len(list(papers.upload_dir.glob("*.pdf"))) == 1
            assert papers.papers[paper_id].filename == "research.pdf"
            second = (await client.post("/api/v1/threads")).json()["id"]
            path = f"/api/v1/threads/{second}"
            run = (
                await client.post(f"{path}/runs", json={"text": "论文的方法是什么？"})
            ).json()
            await wait_for(lambda: runtime.runs[run["id"]].status == "succeeded")
            history = (await client.get(path)).json()
            pack = history["evidence"][0]["evidence_pack"]
            item = pack["items"][0]
            assert item["title"] == "Yeast growth study"
            assert item["paper_id"] == paper_id
            assert item["sources"][0]["page_no"] == 2
            assert "source_path" not in json.dumps(pack)
            assert "private" not in json.dumps(pack)
            replay = (await client.get(f"{path}/runs/{run['id']}/events")).text
            event = next(
                json.loads(line[6:])
                for line in replay.splitlines()
                if line.startswith("data: ") and '"tool.completed"' in line
            )
            assert event["evidence_pack"] == pack
            assert "evidence_pack" not in event["result"]
            assert not any(
                '"approval.required"' in line for line in replay.splitlines()
            )
            assert (await client.get("/api/v1/papers")).json()[0]["status"] == "ready"
    restored = make_service(tmp_path)
    await restored.startup()
    assert restored.list()[0].paper_id == paper_id
    # 引用随 Run 历史持久化，不依赖再次连接检索库。
    restored_runtime = RunService(tmp_path, SearchProvider(), papers=restored)
    await restored_runtime.startup()
    assert (await restored_runtime.thread(second)).evidence[
        0
    ].evidence_pack.model_dump() == pack
    await restored_runtime.shutdown()


@pytest.mark.asyncio
async def test_bad_pdf_and_unknown_paper_never_escape_upload_root(
    tmp_path, monkeypatch
):
    from science_agent_web.errors import ServiceError

    papers = make_service(tmp_path)
    runtime = RunService(tmp_path, SearchProvider(), papers=papers)
    thread = await runtime.create_thread()
    for name, data, status in [("a.txt", b"%PDF-1", 415), ("a.pdf", b"not pdf", 415)]:
        with pytest.raises(ServiceError) as error:
            await papers.upload(thread.id, name, chunks(data))
        assert error.value.status == status
    monkeypatch.setattr("science_agent_web.papers.MAX_PDF_BYTES", 8)
    with pytest.raises(ServiceError) as error:
        await papers.upload(thread.id, "large.pdf", chunks())
    assert error.value.status == 413
    assert not list(papers.upload_dir.glob("*.pdf"))
    with pytest.raises(ServiceError, match="不存在"):
        await papers.ingest_tool().run(
            {"paper_id": "../../secret.pdf"}, ToolExecutionContext()
        )


@pytest.mark.asyncio
async def test_failed_and_interrupted_ingestion_can_be_retried_without_duplicates(
    tmp_path,
):
    class FailingEmbeddings(Embeddings):
        async def embed_documents(self, texts):
            raise ValueError("Embedding unavailable")

    papers = make_service(tmp_path, FailingEmbeddings())
    runtime = RunService(tmp_path, SearchProvider(), papers=papers)
    thread = await runtime.create_thread()
    paper = await papers.upload(thread.id, "study.pdf", chunks())
    await wait_for(lambda: paper.status == "failed")
    assert paper.error == "Embedding unavailable"
    papers.ingestion.embeddings = Embeddings()
    await papers.ingest(paper.paper_id)
    before = len(papers.ingestion.corpus.children)
    await papers.ingest(paper.paper_id)
    assert len(papers.ingestion.corpus.children) == before
    papers.ingestion.corpus.papers[paper.paper_id] = replace(
        papers.ingestion.corpus.papers[paper.paper_id], title=None
    )
    assert (await papers.search("method")).papers[paper.paper_id].title == "study.pdf"
    # 即使向量库仍有片段，非 ready 文献也不能进入网页证据。
    paper.status = "interrupted"
    assert not (await papers.search("method")).hits
    paper.status = "indexing"
    await papers._save(paper)
    recovered = make_service(tmp_path)
    await recovered.startup()
    assert recovered.papers[paper.paper_id].status == "interrupted"
    assert not recovered.tasks


@pytest.mark.asyncio
async def test_ingest_tool_keeps_existing_write_approval(tmp_path):
    papers = make_service(tmp_path)
    runtime = RunService(tmp_path, SearchProvider(), papers=papers)
    thread = await runtime.create_thread()
    agent = await runtime.agent(thread.id)
    decisions = []

    async def deny(record):
        decisions.append(record.name)
        return "deny"

    record = await agent.tool_runner.run(
        ToolCallRequest(name="paper_ingest", arguments={"paper_id": "missing"}),
        ToolExecutionContext(agent=agent),
        approval_handler=deny,
    )
    assert record.state == "DENIED"
    assert decisions == ["paper_ingest"]
