"""Explicit registration for optional RAG tools."""

from science_agent.rag.retrieval import RetrievalService
from science_agent.rag.service import PaperIngestionService
from science_agent.tools.rag_ingest import create_paper_ingest_tool
from science_agent.tools.rag_search import create_paper_search_tool
from science_agent.tools.registry import ToolRegistry


def register_rag_tools(
    registry: ToolRegistry,
    *,
    ingestion: PaperIngestionService,
    retrieval: RetrievalService,
) -> ToolRegistry:
    registry.register(create_paper_ingest_tool(ingestion))
    registry.register(create_paper_search_tool(retrieval))
    return registry
