"""Tool adapter for applying a reviewed Wiki draft."""

from dataclasses import asdict

from science_agent.knowledge.ingestion import KnowledgeIngestionService
from science_agent.tools.base import Tool, ToolExecutionContext


def create_wiki_apply_changeset_tool(service: KnowledgeIngestionService) -> Tool:
    async def apply(arguments: dict, context: ToolExecutionContext) -> dict:
        result = await service.apply_draft(arguments["change_id"])
        return asdict(result)

    return Tool(
        name="wiki_apply_changeset",
        description="Apply a previously reviewed Wiki draft by change_id.",
        execute=apply,
        readonly=False,
        input_schema={
            "type": "object",
            "properties": {"change_id": {"type": "string"}},
            "required": ["change_id"],
        },
    )
