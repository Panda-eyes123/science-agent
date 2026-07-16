"""Thin tool entry point for hybrid paper retrieval."""

from dataclasses import asdict

from science_agent.rag.retrieval import RetrievalService
from science_agent.tools.base import Tool, ToolExecutionContext


def create_paper_search_tool(service: RetrievalService) -> Tool:
    async def search(arguments: dict, context: ToolExecutionContext) -> dict:
        evidence = await service.search(
            arguments["query"],
            limit=arguments.get("limit"),
            section_kind=arguments.get("section_kind"),
        )
        return asdict(evidence)

    return Tool(
        name="paper_search",
        description="Retrieve reranked evidence from indexed scientific papers.",
        execute=search,
        readonly=True,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "section_kind": {"type": "string"},
            },
            "required": ["query"],
        },
    )
