"""Example showing JSON persistence between agent instances."""

import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    JSONStore,
    ModelResponse,
    ToolRegistry,
)


class StaticProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        return ModelResponse(text="State saved and restored successfully.")


async def main() -> None:
    store = JSONStore(".resume_store")
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You preserve context for ongoing research work.",
        )
    )

    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=StaticProvider(),
            tool_registry=ToolRegistry(),
            store=store,
            agent_id="persistent-agent",
        ),
        templates,
    )
    await agent.send("Remember that my next experiment uses phosphate buffer.")

    restored = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=StaticProvider(),
            tool_registry=ToolRegistry(),
            store=store,
            agent_id="persistent-agent",
        ),
        templates,
    )
    print(len(restored.messages))
    print(restored.messages[-1].content)


if __name__ == "__main__":
    asyncio.run(main())
