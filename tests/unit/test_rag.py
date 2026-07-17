from dataclasses import replace
import json

import httpx
import pytest

from science_agent.infra.rerankers import APIReranker
from science_agent.rag.chunking import PaperChunker
from science_agent.rag.retrieval import RetrievalService, reciprocal_rank_fusion
from science_agent.rag.routing import classify_section, route_query
from science_agent.rag.types import (
    ParentChunk,
    RetrievalHit,
    SourceElement,
)
from science_agent.tools.base import ToolExecutionContext
from science_agent.tools.rag_search import create_paper_search_tool


def _element(
    element_id: str,
    text: str,
    *,
    kind: str = "method",
    element_type: str = "paragraph",
) -> SourceElement:
    return SourceElement(
        element_id=element_id,
        paper_id="paper-1",
        page_no=1,
        bbox=None,
        element_type=element_type,
        section_kind=kind,
        text=text,
    )


def test_section_routing_covers_scientific_intents():
    assert classify_section("3. Experimental Setup") == "experiment"
    assert classify_section("Limitations and Future Work") == "discussion"
    assert route_query("这篇论文的消融实验结果如何？") == "result"
    assert route_query("Explain the method and algorithm") == "method"


def test_chunker_keeps_table_and_figure_source_provenance():
    elements = [
        _element("heading", "Methods", element_type="section_heading"),
        _element("paragraph", "We train the model with Adam."),
        replace(
            _element("table", "Table 1", element_type="table"),
            table_markdown="| model | score |\n| - | - |\n| ours | 91 |",
        ),
        replace(
            _element("figure", "Architecture", element_type="figure"),
            raw_payload={"caption": "The proposed architecture."},
        ),
    ]

    chunked = PaperChunker(parent_max_chars=2_000, child_max_chars=60).chunk(elements)

    assert chunked.parents[0].source_element_ids == ["paragraph", "table", "figure"]
    assert {source_id for child in chunked.children for source_id in child.source_element_ids} == {
        "paragraph",
        "table",
        "figure",
    }
    assert "| model | score |" in chunked.parents[0].text
    assert "The proposed architecture." in chunked.parents[0].text


def test_rrf_fuses_duplicate_chunks_by_rank():
    bm25 = [RetrievalHit(chunk_id="a", score=4.0), RetrievalHit(chunk_id="b", score=3.0)]
    dense = [RetrievalHit(chunk_id="b", score=0.9), RetrievalHit(chunk_id="c", score=0.8)]

    fused = reciprocal_rank_fusion([bm25, dense], k=10)

    assert [hit.chunk_id for hit in fused] == ["b", "a", "c"]
    assert fused[0].score == pytest.approx(1 / 12 + 1 / 11)


@pytest.mark.asyncio
async def test_api_reranker_uses_remote_scores():
    hits = [
        RetrievalHit(chunk_id="a", score=0.1, text="first"),
        RetrievalHit(chunk_id="b", score=0.2, text="second"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["documents"] == ["first", "second"]
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.95},
                    {"index": 0, "relevance_score": 0.4},
                ]
            },
            request=request,
        )

    reranker = APIReranker(
        api_key="test",
        transport=httpx.MockTransport(handler),
    )

    result = await reranker.rerank("query", hits, limit=2)

    assert [hit.chunk_id for hit in result] == ["b", "a"]
    assert [hit.score for hit in result] == [0.95, 0.4]


class FakeEmbeddings:
    async def embed_query(self, text: str) -> list[float]:
        return [0.1, 0.2]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


class FakeReranker:
    async def rerank(
        self, query: str, hits: list[RetrievalHit], *, limit: int
    ) -> list[RetrievalHit]:
        return sorted(hits, key=lambda hit: hit.chunk_id, reverse=True)[:limit]


class FakeCorpus:
    def __init__(self) -> None:
        self.parent = ParentChunk(
            chunk_id="parent-1",
            paper_id="paper-1",
            section_kind="method",
            text="Parent context",
            source_element_ids=["element-1"],
        )
        self.element = _element("element-1", "Original method evidence")

    async def search_bm25(self, query, *, limit, section_kind):
        return [
            RetrievalHit(
                chunk_id="child-a",
                score=1.0,
                text="BM25 hit",
                paper_id="paper-1",
                parent_chunk_id="parent-1",
                section_kind="method",
            )
        ]

    async def search_dense(self, vector, *, limit, section_kind):
        return [
            RetrievalHit(
                chunk_id="child-b",
                score=1.0,
                text="Dense hit",
                paper_id="paper-1",
                parent_chunk_id="parent-1",
                section_kind="method",
            )
        ]

    async def get_parent_chunks(self, chunk_ids):
        return [self.parent] if "parent-1" in chunk_ids else []

    async def get_source_elements(self, element_ids):
        return [self.element] if "element-1" in element_ids else []


@pytest.mark.asyncio
async def test_retrieval_backtraces_parent_and_source_elements():
    service = RetrievalService(
        corpus=FakeCorpus(),
        embeddings=FakeEmbeddings(),
        reranker=FakeReranker(),
    )

    evidence = await service.search("Explain the method", limit=1)

    assert evidence.route == "method"
    assert evidence.hits[0].chunk_id == "child-b"
    assert evidence.parents["parent-1"].text == "Parent context"
    assert evidence.source_elements["element-1"].text == "Original method evidence"


@pytest.mark.asyncio
async def test_paper_search_tool_returns_serializable_evidence():
    service = RetrievalService(
        corpus=FakeCorpus(),
        embeddings=FakeEmbeddings(),
        reranker=FakeReranker(),
    )
    tool = create_paper_search_tool(service)

    result = await tool.run({"query": "method"}, ToolExecutionContext())

    assert result["route"] == "method"
    assert "Parent context" in result["evidence"]
    assert "paper-1" in result["evidence"]
