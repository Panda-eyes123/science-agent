"""Thin tool entry point for indexing a scientific paper."""

from dataclasses import asdict

from science_agent.rag.service import PaperIngestionService
from science_agent.tools.base import Tool, ToolExecutionContext


def create_paper_ingest_tool(service: PaperIngestionService) -> Tool:
    async def ingest(arguments: dict, context: ToolExecutionContext) -> dict:
        paper = await service.ingest(arguments["path"], paper_id=arguments.get("paper_id"))
        return asdict(paper)

    return Tool(
        name="paper_ingest",
        description="Parse and index a local scientific paper into the RAG corpus.",
        execute=ingest,
        readonly=False,
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "paper_id": {"type": "string"},
            },
            "required": ["path"],
        },
    )
