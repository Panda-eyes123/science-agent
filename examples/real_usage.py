"""Example using OpenAIProvider with real API calls.

Requires a .env file at the project root with at minimum:
    OPENAI_API_KEY=your-api-key-here

Optional overrides (see .env.example):
    OPENAI_BASE_URL, OPENAI_MODEL
"""

import asyncio

from dotenv import load_dotenv

load_dotenv()

from science_agent import (  # noqa: E402
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    OpenAIProvider,
    ToolRegistry,
)
from science_agent.tools.builtin import register_builtin_tools  # noqa: E402


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You are a concise scientific research assistant.",
            tools=["todo_write", "todo_read", "fs_read", "fs_write"],
        )
    )

    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=OpenAIProvider(),
            tool_registry=register_builtin_tools(ToolRegistry()),
        ),
        templates,
    )

    response = await agent.send(
        "Briefly explain what a control group is in a scientific experiment."
    )
    print(response)


if __name__ == "__main__":
    asyncio.run(main())
