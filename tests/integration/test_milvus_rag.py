"""Opt-in: real PDF parser and Milvus, deterministic embeddings (no model API)."""

import os
from uuid import uuid4

import pytest

from science_agent.infra.corpus import MilvusCorpusStore
from science_agent.infra.document_parsing import DoclingPDFParser
from science_agent.infra.rerankers import FusionRanker
from science_agent.rag import PaperChunker, PaperIngestionService, RetrievalService
from science_agent.tools.rag_search import create_paper_search_tool
from science_agent.tools import ToolExecutionContext

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("SCIENCE_AGENT_TEST_MILVUS") != "1",
        reason="Set SCIENCE_AGENT_TEST_MILVUS=1 with local Milvus running",
    ),
]


async def test_real_pdf_milvus_bm25_provenance(tmp_path):
    import fitz
    from pymilvus import MilvusClient

    path = tmp_path / "study.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Yeast Growth Study", fontsize=22)
        page.insert_text((72, 120), "Methods", fontsize=16)
        page.insert_text(
            (72, 150),
            "Yeast samples were cultured at 30 C. A control group was kept at 20 C.",
        )
        pdf.save(path)

    class FixedEmbeddings:
        async def embed_documents(self, texts):
            return [[1.0, 0.0, 0.0, 0.0] for text in texts]

        async def embed_query(self, text):
            return [1.0, 0.0, 0.0, 0.0]

    uri = os.getenv("MILVUS_URI", "http://127.0.0.1:19530")
    name = f"science_test_{uuid4().hex}"
    corpus = MilvusCorpusStore(uri=uri, collection_name=name, embedding_dim=4)
    embeddings = FixedEmbeddings()
    try:
        ingestion = PaperIngestionService(
            parser=DoclingPDFParser(artifact_dir=tmp_path / "artifacts"),
            chunker=PaperChunker(),
            embeddings=embeddings,
            corpus=corpus,
        )
        paper = await ingestion.ingest(path, paper_id="integration-paper")
        retrieval = RetrievalService(
            corpus=corpus, embeddings=embeddings, reranker=FusionRanker()
        )
        result = await create_paper_search_tool(retrieval).run(
            {"query": "yeast control methods", "section_kind": "method"},
            ToolExecutionContext(),
        )
        items = result["evidence_pack"]["items"]
        assert items and items[0]["paper_id"] == paper.paper_id
        assert any(
            source["page_no"] == 1 for item in items for source in item["sources"]
        )
        assert "30" in result["evidence"]
    finally:
        await corpus.close()
        client = MilvusClient(uri=uri)
        for collection in (name, f"{name}_records"):
            if client.has_collection(collection):
                client.drop_collection(collection)
        client.close()
