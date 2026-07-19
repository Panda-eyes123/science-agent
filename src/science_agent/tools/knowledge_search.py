"""Tool adapter for Wiki-guided, raw-grounded retrieval."""

from dataclasses import asdict

from science_agent.knowledge.query import KnowledgeQueryService
from science_agent.knowledge.rendering import render_knowledge_evidence
from science_agent.tools.base import Tool, ToolExecutionContext


def create_knowledge_search_tool(service: KnowledgeQueryService) -> Tool:
    async def search(arguments: dict, context: ToolExecutionContext) -> dict:
        evidence = await service.search(
            arguments["query"],
            limit=arguments.get("limit"),
            section_kind=arguments.get("section_kind"),
        )
        return {
            "evidence": render_knowledge_evidence(evidence),
            "route": asdict(evidence.plan),
            "warnings": evidence.warnings,
            "citations": [asdict(item) for item in evidence.citations],
        }

    return Tool(
        name="knowledge_search",
        description=(
            "Retrieve personal Wiki synthesis and verify it against raw paper evidence. "
            "Use this for cross-document questions, comparisons, facts, and sources."
        ),
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
