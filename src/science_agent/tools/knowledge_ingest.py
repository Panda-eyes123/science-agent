"""Tool adapter for raw ingestion followed by Wiki compilation."""

from dataclasses import asdict

from science_agent.knowledge.ingestion import KnowledgeIngestionService
from science_agent.tools.base import Tool, ToolExecutionContext


def create_knowledge_ingest_tool(service: KnowledgeIngestionService) -> Tool:
    async def ingest(arguments: dict, context: ToolExecutionContext) -> dict:
        result = await service.ingest(
            arguments["path"],
            paper_id=arguments.get("paper_id"),
            apply=arguments.get("apply", False),
            force_recompile=arguments.get("force_recompile", False),
        )
        return asdict(result)

    return Tool(
        name="knowledge_ingest",
        description=(
            "Index a paper as raw evidence, then create a reviewable Wiki changeset. "
            "Set apply=true only when the Wiki update should be committed immediately."
        ),
        execute=ingest,
        readonly=False,
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "paper_id": {"type": "string"},
                "apply": {"type": "boolean"},
                "force_recompile": {"type": "boolean"},
            },
            "required": ["path"],
        },
    )
