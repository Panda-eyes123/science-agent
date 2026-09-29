"""Thin tool entry point for hybrid paper retrieval."""

from science_agent.rag.multimodal.ports import EvidenceRetriever
from science_agent.rag.rendering import evidence_view, render_evidence_view
from science_agent.tools.base import Tool, ToolExecutionContext


def create_paper_search_tool(service: EvidenceRetriever) -> Tool:
    async def search(arguments: dict, context: ToolExecutionContext) -> dict:
        evidence = await service.search(
            arguments["query"],
            limit=arguments.get("limit"),
            section_kind=arguments.get("section_kind"),
        )
        view = evidence_view(evidence)
        return {
            "evidence": render_evidence_view(view),
            "route": evidence.route,
            "evidence_pack": view.model_dump(mode="json"),
        }

    return Tool(
        name="paper_search",
        description="Retrieve ranked evidence and page-addressable sources from indexed scientific papers.",
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
