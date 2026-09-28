"""Async agent execution, independent of HTTP and frontend concerns."""

import asyncio
import json
from contextlib import aclosing
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from science_agent.agent_runtime.approval import ApprovalCoordinator
from science_agent.agent_runtime.permission_manager import PermissionManager
from science_agent.agent_runtime.tool_runner import ToolRunner
from science_agent.config import (
    DEFAULT_CONTEXT_MESSAGES,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_WORK_DIR,
)
from science_agent.core.context_manager import ContextManager
from science_agent.core.events import EventBus, serialize_event_for_store
from science_agent.core.template import AgentTemplateRegistry
from science_agent.core.todo import TodoService
from science_agent.infra.providers.base import ModelProvider, StreamingModelProvider
from science_agent.infra.sandbox import LocalSandbox
from science_agent.infra.store.types import Store
from science_agent.tools.base import ToolExecutionContext
from science_agent.tools.registry import ToolRegistry
from science_agent.types import (
    AgentEventEnvelope,
    AgentInfo,
    Message,
    ModelResponse,
    ModelStreamEnd,
    ModelTextDelta,
    ToolCallRecord,
    utc_now_iso,
)
from science_agent.utils.agent_id import generate_agent_id


@dataclass(slots=True)
class AgentConfig:
    template_id: str
    model: ModelProvider
    store: Store | None = None
    tool_registry: ToolRegistry | None = None
    sandbox: LocalSandbox | None = None
    agent_id: str | None = None
    max_rounds: int = DEFAULT_MAX_ROUNDS
    context_max_messages: int = DEFAULT_CONTEXT_MESSAGES
    permission_mode: str = "auto"


class Agent:
    def __init__(self, config: AgentConfig, templates: AgentTemplateRegistry) -> None:
        self.config = config
        self.templates = templates
        self.template = templates.get(config.template_id)
        self.agent_id = config.agent_id or generate_agent_id()
        self.store = config.store
        self.tool_registry = config.tool_registry or ToolRegistry()
        self.sandbox = config.sandbox or LocalSandbox(
            Path(DEFAULT_WORK_DIR) / self.agent_id
        )
        self.events = EventBus(self._persist_event)
        self._send_lock = asyncio.Lock()
        self.context_manager = ContextManager(config.context_max_messages)
        self.todo_service = TodoService()
        self.permissions = PermissionManager(config.permission_mode)  # type: ignore[arg-type]
        self.tool_runner = ToolRunner(self.tool_registry, self.permissions)
        self.approvals = ApprovalCoordinator(self._emit_control)
        self.messages: list[Message] = []
        self.tool_records: list[ToolCallRecord] = []
        self.info = AgentInfo(agent_id=self.agent_id, template_id=self.template.id)

    @classmethod
    async def create(
        cls, config: AgentConfig, templates: AgentTemplateRegistry
    ) -> "Agent":
        agent = cls(config, templates)
        if agent.store is not None:
            agent.messages = await agent.store.load_messages(agent.agent_id)
            agent.tool_records = list(
                await agent.store.load_tool_call_records(agent.agent_id)
            )
            info = await agent.store.load_info(agent.agent_id)
            if info is not None:
                agent.info = info
            agent.info.state = "READY"
            agent.todo_service.load_snapshot(
                await agent.store.load_todos(agent.agent_id)
            )
            async for event in agent.store.read_events(agent.agent_id):
                agent.events.restore_sequence(event.seq)
        return agent

    async def subscribe(self, channels: list[str]) -> AsyncIterator:
        async for envelope in self.events.subscribe(channels):
            yield envelope

    async def send(
        self, text: str, *, stream: bool = False, run_id: str | None = None
    ) -> str:
        if stream and not isinstance(self.config.model, StreamingModelProvider):
            raise TypeError("This provider does not implement streaming.")
        async with self._send_lock:
            self.events.run_id = run_id or uuid4().hex
            self.messages.append(
                Message(role="user", content=text, run_id=self.events.run_id)
            )
            self.info.state = "WORKING"
            await self._persist_state()
            await self._emit("monitor", {"type": "state_changed", "state": "WORKING"})
            reason = "completed"
            error = None
            try:
                return await self._process_rounds(stream)
            except asyncio.CancelledError:
                reason = "cancelled"
                raise
            except Exception as exc:
                reason, error = "failed", str(exc)
                await self._emit(
                    "monitor",
                    {
                        "type": "error",
                        "message": error,
                        "error_type": type(exc).__name__,
                    },
                )
                raise
            finally:
                # 收到 done 的调用方应立即读到一致的历史，因此先保存再发终态事件。
                self.info.state = "READY"
                await self._persist_state()
                await self._emit("monitor", {"type": "state_changed", "state": "READY"})
                await self._emit(
                    "progress", {"type": "done", "reason": reason, "error": error}
                )

    async def _model_response(self, stream: bool, message: Message) -> ModelResponse:
        kwargs = {
            "tools": self.tool_registry.export_openai_tools(self.template.tools),
            "system_prompt": self.template.system_prompt,
        }
        prepared = self.context_manager.prepare_messages(self.messages)
        if not stream:
            response = await self.config.model.complete(prepared, **kwargs)
            message.content = response.text
            if response.text:
                await self._emit(
                    "progress",
                    {
                        "type": "text_chunk",
                        "message_id": message.id,
                        "delta": response.text,
                    },
                )
            return response
        provider = self.config.model
        assert isinstance(provider, StreamingModelProvider)
        # 终态返回和取消都要关闭上游 HTTP 流，不能把连接释放交给垃圾回收。
        async with aclosing(provider.stream(prepared, **kwargs)) as events:
            async for event in events:
                if isinstance(event, ModelTextDelta):
                    message.content += event.text
                    await self._emit(
                        "progress",
                        {
                            "type": "text_chunk",
                            "message_id": message.id,
                            "delta": event.text,
                        },
                    )
                elif isinstance(event, ModelStreamEnd):
                    return event.response
        raise RuntimeError("Provider stream ended without a final response.")

    async def _process_rounds(self, stream: bool) -> str:
        for _ in range(self.config.max_rounds):
            message = Message(role="assistant", content="", run_id=self.events.run_id)
            try:
                response = await self._model_response(stream, message)
            except BaseException:
                if message.content:
                    self.messages.append(message)
                raise
            message.content = response.text
            for call in response.tool_calls:
                call.call_id = call.call_id or f"call_{uuid4().hex}"
            message.tool_calls = response.tool_calls
            self.messages.append(message)
            if not response.tool_calls:
                return response.text
            for call in response.tool_calls:
                await self._emit(
                    "progress",
                    {
                        "type": "tool:start",
                        "call": {
                            "id": call.call_id,
                            "name": call.name,
                            "arguments": call.arguments,
                        },
                    },
                )
                record = await self.tool_runner.run(
                    call,
                    ToolExecutionContext(agent=self, sandbox=self.sandbox),
                    approval_handler=self.approvals.request,
                )
                record.run_id = self.events.run_id
                self.tool_records.append(record)
                self.messages.append(
                    Message(
                        role="tool",
                        content=json.dumps(
                            record.result
                            if record.state == "COMPLETED"
                            else {"error": record.error},
                            ensure_ascii=False,
                        ),
                        name=record.name,
                        tool_call_id=record.call_id,
                        run_id=self.events.run_id,
                    )
                )
                if record.state in {"FAILED", "DENIED"}:
                    await self._emit(
                        "progress",
                        {
                            "type": "tool:error",
                            "call": {
                                "id": record.call_id,
                                "name": record.name,
                                "state": record.state,
                            },
                            "error": record.error,
                        },
                    )
                    raise RuntimeError(record.error or "Tool execution failed.")
                await self._persist_state()
                await self._emit(
                    "progress",
                    {
                        "type": "tool:end",
                        "call": {
                            "id": record.call_id,
                            "name": record.name,
                            "result": record.result,
                        },
                    },
                )
        raise RuntimeError(f"Maximum model rounds reached ({self.config.max_rounds}).")

    async def _emit_control(self, event: dict) -> None:
        await self._emit("control", event)

    async def _emit(self, channel: str, event: dict) -> None:
        await self.events.emit(channel, event)

    async def _persist_event(self, envelope: AgentEventEnvelope) -> None:
        if self.store is not None:
            await self.store.append_event(
                self.agent_id,
                AgentEventEnvelope(
                    seq=envelope.seq,
                    timestamp=envelope.timestamp,
                    channel=envelope.channel,
                    event=serialize_event_for_store(envelope.event),
                    run_id=envelope.run_id,
                ),
            )

    async def _persist_state(self) -> None:
        self.info.updated_at = utc_now_iso()
        if self.store is not None:
            await self.store.save_messages(self.agent_id, self.messages)
            await self.store.save_tool_call_records(self.agent_id, self.tool_records)
            await self.store.save_info(self.agent_id, self.info)
            await self.store.save_todos(self.agent_id, self.todo_service.snapshot())
