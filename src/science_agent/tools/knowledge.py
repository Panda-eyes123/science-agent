"""Explicit registration for the composed knowledge tools."""

from science_agent.knowledge.ingestion import KnowledgeIngestionService
from science_agent.knowledge.query import KnowledgeQueryService
from science_agent.tools.knowledge_ingest import create_knowledge_ingest_tool
from science_agent.tools.knowledge_search import create_knowledge_search_tool
from science_agent.tools.registry import ToolRegistry
from science_agent.tools.wiki_apply_changeset import create_wiki_apply_changeset_tool


def register_knowledge_tools(
    registry: ToolRegistry,
    *,
    ingestion: KnowledgeIngestionService,
    query: KnowledgeQueryService,
) -> ToolRegistry:
    registry.register(create_knowledge_ingest_tool(ingestion))
    registry.register(create_knowledge_search_tool(query))
    registry.register(create_wiki_apply_changeset_tool(ingestion))
    return registry
