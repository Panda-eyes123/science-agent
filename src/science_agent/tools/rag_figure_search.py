"""Thin tool entry point for figure retrieval and optional VLM analysis."""

from dataclasses import asdict

from science_agent.rag.multimodal.service import FigureSearchService
from science_agent.tools.base import Tool, ToolExecutionContext


def create_paper_figure_search_tool(service: FigureSearchService) -> Tool:
    async def search(arguments: dict, context: ToolExecutionContext) -> dict:
        result = await service.search(
            arguments["query"],
            limit=arguments.get("limit"),
            section_kind=arguments.get("section_kind"),
            vlm_mode=arguments.get("vlm_mode", "auto"),
        )
        return {
            "query": result.query,
            "route": result.retrieval.route,
            "assets": [asdict(asset) for asset in result.assets],
            "vlm_used": result.vlm_used,
            "trigger_reasons": result.decision.reasons,
            "asset_errors": result.asset_errors,
            "vlm_error": result.vlm_error,
            "vlm_response": (
                asdict(result.vlm_response) if result.vlm_response else None
            ),
        }

    return Tool(
        name="paper_figure_search",
        description=(
            "Retrieve figures, tables, or formulas from scientific papers and "
            "optionally analyze them with a vision model."
        ),
        execute=search,
        readonly=True,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
                "section_kind": {"type": "string"},
                "vlm_mode": {
                    "type": "string",
                    "enum": ["auto", "always", "never"],
                },
            },
            "required": ["query"],
        },
    )
