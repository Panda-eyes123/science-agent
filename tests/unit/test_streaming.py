import asyncio
import json

import httpx
import pytest

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
    JSONStore,
    ModelResponse,
    ModelStreamEnd,
    ModelTextDelta,
    OpenAIProvider,
    RetryConfig,
    ToolCallRequest,
    ToolRegistry,
)
from science_agent.core.context_manager import ContextManager
from science_agent.errors import ProviderResponseError
from science_agent.tools.builtin import register_builtin_tools
from science_agent.types import Message


def sse(*chunks, done=True):
    data = "".join(
        f"data: {json.dumps({'choices': [{'delta': chunk}]})}\n\n" for chunk in chunks
    )
    return data + ("data: [DONE]\n\n" if done else "")


@pytest.mark.asyncio
async def test_stream_assembles_text_and_interleaved_tool_arguments():
    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200,
            text=sse(
                {"content": "开始"},
                {"content": "整理"},
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "first",
                            "function": {"name": "todo_read", "arguments": "{"},
                        },
                        {
                            "index": 1,
                            "id": "second",
                            "function": {"name": "fs_read", "arguments": '{"path":'},
                        },
                    ]
                },
                {
                    "tool_calls": [
                        {"index": 1, "function": {"arguments": '"a.txt"}'}},
                        {"index": 0, "function": {"arguments": "}"}},
                    ]
                },
            ),
        )

    provider = OpenAIProvider(api_key="test", transport=httpx.MockTransport(handler))
    events = [
        event async for event in provider.stream([Message(role="user", content="go")])
    ]
    assert [event.text for event in events if isinstance(event, ModelTextDelta)] == [
        "开始",
        "整理",
    ]
    final = events[-1].response
    assert final.text == "开始整理"
    assert [call.call_id for call in final.tool_calls] == ["first", "second"]
    assert final.tool_calls[1].arguments == {"path": "a.txt"}


@pytest.mark.asyncio
async def test_partial_stream_is_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, text=sse({"content": "部分回答"}, done=False))

    provider = OpenAIProvider(
        api_key="test", transport=httpx.MockTransport(handler), retry=RetryConfig(3, 0)
    )
    seen = []
    with pytest.raises(ProviderResponseError, match="before"):
        async for event in provider.stream([]):
            seen.append(event)
    assert calls == 1
    assert seen[0].text == "部分回答"


@pytest.mark.asyncio
async def test_streamed_tool_roundtrip_and_restored_sequence(tmp_path):
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(
                200,
                text=sse(
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "read_todos",
                                "function": {"name": "todo_read", "arguments": "{}"},
                            }
                        ]
                    }
                ),
            )
        return httpx.Response(200, text=sse({"content": "完成"}))

    provider = OpenAIProvider(api_key="test", transport=httpx.MockTransport(handler))
    templates = AgentTemplateRegistry()
    templates.register(
        AgentTemplateDefinition(id="test", system_prompt="test", tools=["todo_read"])
    )
    config = AgentConfig(
        template_id="test",
        model=provider,
        store=JSONStore(tmp_path),
        agent_id="test",
        tool_registry=register_builtin_tools(ToolRegistry()),
    )
    agent = await Agent.create(config, templates)
    assert await agent.send("read", stream=True, run_id="one") == "完成"
    messages = requests[1]["messages"]
    assert (
        messages[-2]["tool_calls"][0]["id"]
        == messages[-1]["tool_call_id"]
        == "read_todos"
    )
    previous = [event async for event in config.store.read_events("test")]
    restored = await Agent.create(config, templates)
    await restored.send("again", stream=True, run_id="two")
    fresh = [
        event
        async for event in config.store.read_events("test", since=previous[-1].seq)
    ]
    assert fresh and all(event.run_id == "two" for event in fresh)
    assert fresh[0].seq > previous[-1].seq


def test_context_preserves_pairs_and_skips_interrupted_batches():
    call = ToolCallRequest(name="todo_read", call_id="a")
    assistant = Message(role="assistant", content="", tool_calls=[call])
    result = Message(role="tool", content="[]", tool_call_id="a")
    assert ContextManager(1).prepare_messages([assistant, result]) == [
        assistant,
        result,
    ]
    user = Message(role="user", content="continue")
    assert ContextManager(10).prepare_messages([assistant, user]) == [user]


@pytest.mark.asyncio
async def test_cancellation_keeps_partial_text_and_emits_terminal(tmp_path):
    started = asyncio.Event()

    class SlowProvider:
        async def complete(self, messages, **kwargs):
            return ModelResponse()

        async def stream(self, messages, **kwargs):
            yield ModelTextDelta(text="已有内容")
            started.set()
            await asyncio.Event().wait()
            yield ModelStreamEnd(response=ModelResponse(text="unreachable"))

    templates = AgentTemplateRegistry()
    templates.register(AgentTemplateDefinition(id="test", system_prompt="test"))
    store = JSONStore(tmp_path)
    agent = await Agent.create(
        AgentConfig(template_id="test", model=SlowProvider(), store=store), templates
    )
    task = asyncio.create_task(agent.send("go", stream=True))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await store.load_messages(agent.agent_id))[-1].content == "已有内容"
    events = [event async for event in store.read_events(agent.agent_id)]
    assert events[-1].event["reason"] == "cancelled"
