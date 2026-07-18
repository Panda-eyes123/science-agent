"""Example showing PostgreSQL persistence and automatic schema migration."""

import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    ModelResponse,
    PostgresStore,
    ToolRegistry,
)


class StaticProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        return ModelResponse(text="PostgreSQL state saved successfully.")


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You preserve context for ongoing research work.",
        )
    )

    async with PostgresStore() as store:
        config = AgentConfig(
            template_id="science-assistant",
            model=StaticProvider(),
            tool_registry=ToolRegistry(),
            store=store,
            agent_id="postgres-persistent-agent",
        )
        agent = await Agent.create(config, templates)
        await agent.send("Remember that the control group receives buffer only.")

        restored = await Agent.create(config, templates)
        print([message.content for message in restored.messages])


if __name__ == "__main__":
    asyncio.run(main())
