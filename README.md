# science-agent

`science-agent` is an alpha-stage Python SDK for building event-driven research agents.
It currently focuses on a small but working runtime: async agent execution, event
subscription, tool calls, local JSON persistence, sandboxed file tools, permission
approval, and an OpenAI-compatible provider adapter.

This project is intentionally still small. The alpha goal is to keep the runtime
easy to inspect while the core contracts settle.

## Current Status

The SDK can already:

- Run an async `Agent` with a template, model provider, message history, and event stream.
- Emit `progress`, `control`, and `monitor` events.
- Register and execute tools through `ToolRegistry`.
- Use built-in tools for todo management and sandboxed file read/write.
- Persist messages, tool calls, events, todos, snapshots, and agent info with `JSONStore`.
- Enforce local sandbox path boundaries for file tools.
- Request manual tool approval through `control.permission_required`.
- Call an OpenAI-compatible `/chat/completions` endpoint with categorized provider errors and retry handling.

## Requirements

- Python `3.13+`
- `uv`
- An `OPENAI_API_KEY` only when using the real `OpenAIProvider`

## Setup

```powershell
uv venv --python 3.13
uv sync --extra dev
```

## Development Commands

Run the test suite:

```powershell
uv run pytest
```

Run lint checks:

```powershell
uv run ruff check .
```

Run all local quality checks:

```powershell
uv run pytest
uv run ruff check .
```

Run the built-in examples:

```powershell
uv run python examples\getting_started.py
uv run python examples\tool_usage.py
uv run python examples\persistence_resume.py
```

## Local Example

`examples/getting_started.py` runs without external API calls. It uses a tiny mock
provider and prints progress events from the agent.

```python
import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    ModelResponse,
    ToolRegistry,
)


class EchoProvider:
    async def complete(self, messages, *, tools=None, system_prompt=None):
        last_user = next(
            message.content for message in reversed(messages) if message.role == "user"
        )
        return ModelResponse(text=f"Science agent received: {last_user}")


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You are a concise scientific research assistant.",
        )
    )

    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=EchoProvider(),
            tool_registry=ToolRegistry(),
        ),
        templates,
    )

    async def consume() -> None:
        async for envelope in agent.subscribe(["progress"]):
            print(envelope.event)
            if envelope.event["type"] == "done":
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await agent.send("Summarize the role of controls in a simple experiment.")
    await consumer


asyncio.run(main())
```

## Tool And Persistence Examples

The repository includes two practical local demos:

- `examples/tool_usage.py`: simulates a model requesting `todo_write`, then persists the agent state in `.demo_store`.
- `examples/persistence_resume.py`: creates an agent with a fixed `agent_id`, writes state through `JSONStore`, then restores a second agent instance from the same store.

These examples use mock providers so they are stable in tests and offline development.

## Real OpenAI Example

Set your API key:

```powershell
$env:OPENAI_API_KEY="sk-..."
```

Then use the real provider:

```python
import asyncio

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    OpenAIProvider,
    RetryConfig,
    ToolRegistry,
)


async def main() -> None:
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            system_prompt="You are a careful scientific research assistant.",
        )
    )

    provider = OpenAIProvider(
        model="gpt-4.1-mini",
        retry=RetryConfig(max_attempts=3, backoff_seconds=0.5),
    )
    agent = await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            model=provider,
            tool_registry=ToolRegistry(),
        ),
        templates,
    )

    async def consume() -> None:
        async for envelope in agent.subscribe(["progress", "monitor"]):
            print(envelope.event)
            if envelope.event["type"] == "done":
                break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await agent.send("Give me a concise hypothesis for testing yeast growth rates.")
    await consumer


asyncio.run(main())
```

`OpenAIProvider` currently uses the Chat Completions API. It categorizes common
provider failures into authentication, invalid request, not found, rate limit,
server, timeout, network, and response parsing errors. Retry is applied only to
retryable failures such as `408`, `429`, `409`, `5xx`, timeout, and network errors.

## Permission Approval Example

Use `permission_mode="manual"` when tool calls should require an explicit decision.
Subscribers listen to the `control` channel and call the event's `respond` function.

```python
async for envelope in agent.subscribe(["control", "progress"]):
    if envelope.event["type"] == "permission_required":
        call = envelope.event["call"]
        if call["name"] == "fs_write":
            await envelope.event["respond"]("allow", note="approved file write")
        else:
            await envelope.event["respond"]("deny", note="tool not allowed")
```

Persisted control events are sanitized before being written to `JSONStore`, so the
runtime callback is available to subscribers but is not serialized to disk.

## Public API Surface

The alpha public exports are:

- `Agent`, `AgentConfig`
- `AgentTemplateDefinition`, `AgentTemplateRegistry`
- `JSONStore`
- `LocalSandbox`, `SandboxResult`
- `OpenAIProvider`, `RetryConfig`
- `Tool`, `ToolExecutionContext`, `ToolRegistry`
- `TodoItem`, `TodoService`
- `ModelProvider`, `ModelResponse`, `ToolCallRequest`

## Capability Boundaries

This alpha is useful for local development, SDK contract exploration, and small
research-agent prototypes. It is not production-ready yet.

Currently supported:

- Single-process async runtime.
- Local JSON persistence.
- Local sandbox file read/write with path boundary checks.
- Sequential tool execution.
- Manual approval flow for tool calls.
- Minimal OpenAI-compatible provider with categorized errors and retry.
- Unit-tested core behavior.

Not yet supported:

- Streaming token-by-token provider output.
- SQLite/PostgreSQL stores.
- Distributed locks or multi-worker coordination.
- MCP tools.
- E2B/OpenSandbox remote sandboxes.
- Full breakpoint/resume state machine.
- Token-aware context compression.
- Provider usage accounting.
- CI configuration.
- A stable semantic-versioned API.

## Project Layout

```text
src/science_agent/
  core/              Agent runtime, events, templates, todos
  agent_runtime/     Tool execution, permissions, approval coordination
  infra/             Providers, stores, sandbox implementations
  tools/             Tool primitives, registry, built-in tools
  utils/             Small utility helpers
tests/unit/          Unit tests for runtime, store, tools, provider behavior
examples/            Local runnable examples
```

## Alpha Roadmap

Near-term work:

- Add an approval-control example under `examples/`.
- Add provider usage/token parsing.
- Add request logging hooks for provider calls.
- Add streaming support for OpenAI-compatible responses.
- Add CI for tests and linting.
- Decide whether Python `3.13+` remains required or whether to support `3.11+`.

