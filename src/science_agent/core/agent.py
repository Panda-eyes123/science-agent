"""Phase-one async agent runtime."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from science_agent.agent_runtime.breakpoint_manager import BreakpointManager
from science_agent.agent_runtime.message_queue import MessageQueue
from science_agent.agent_runtime.permission_manager import PermissionManager
from science_agent.agent_runtime.tool_runner import ToolRunner
from science_agent.config import (
    DEFAULT_CONTEXT_MESSAGES,
    DEFAULT_MAX_ROUNDS,
    DEFAULT_WORK_DIR,
)
from science_agent.core.context_manager import ContextManager
from science_agent.core.events import EventBus
from science_agent.core.template import AgentTemplateRegistry
from science_agent.core.todo import TodoService
from science_agent.infra.providers.base import ModelProvider
from science_agent.infra.sandbox import LocalSandbox
from science_agent.infra.store.types import Store
from science_agent.tools.base import ToolExecutionContext
from science_agent.tools.registry import ToolRegistry
from science_agent.types import AgentInfo, Message, ToolCallRecord
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
        self.events = EventBus()
        self.message_queue = MessageQueue()
        self.context_manager = ContextManager(config.context_max_messages)
        self.todo_service = TodoService()
        self.permissions = PermissionManager(config.permission_mode)  # type: ignore[arg-type]
        self.tool_runner = ToolRunner(self.tool_registry, self.permissions)
        self.breakpoints = BreakpointManager()
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
            todos = await agent.store.load_todos(agent.agent_id)
            if todos:
                agent.todo_service.load_snapshot(todos)
        return agent

    async def subscribe(self, channels: list[str]) -> AsyncIterator:
        async for envelope in self.events.subscribe(channels):
            yield envelope

    async def send(self, text: str) -> str:
        await self.message_queue.put("user", text)
        last_text = ""
        while not self.message_queue.empty():
            pending = await self.message_queue.get()
            self.messages.append(Message(role="user", content=pending.text))
            last_text = await self._process_rounds()
        return last_text

    async def _process_rounds(self) -> str:
        self.info.state = "WORKING"
        await self._emit("monitor", {"type": "state_changed", "state": self.info.state})
        final_text = ""
        try:
            for _ in range(self.config.max_rounds):
                prepared = self.context_manager.prepare_messages(self.messages)
                response = await self.config.model.complete(
                    prepared,
                    tools=self.tool_registry.export_openai_tools(self.template.tools),
                    system_prompt=self.template.system_prompt,
                )
                if response.text:
                    final_text = response.text
                    self.messages.append(
                        Message(role="assistant", content=response.text)
                    )
                    await self._emit(
                        "progress", {"type": "text_chunk", "delta": response.text}
                    )
                if not response.tool_calls:
                    break
                for call in response.tool_calls:
                    await self._emit(
                        "progress",
                        {
                            "type": "tool:start",
                            "call": {"name": call.name, "arguments": call.arguments},
                        },
                    )
                    record = await self.tool_runner.run(
                        call, ToolExecutionContext(agent=self, sandbox=self.sandbox)
                    )
                    self.tool_records.append(record)
                    if record.state in {"FAILED", "DENIED"}:
                        await self._emit_tool_error(record)
                        raise RuntimeError(record.error or "Tool execution failed.")
                    await self._emit(
                        "progress",
                        {
                            "type": "tool:end",
                            "call": {"name": record.name, "result": record.result},
                        },
                    )
                    self.messages.append(
                        Message(
                            role="tool",
                            content=json.dumps(record.result, ensure_ascii=False),
                            name=record.name,
                            tool_call_id=record.call_id,
                        )
                    )
            await self._persist_state()
            await self._emit("progress", {"type": "done", "reason": "completed"})
            return final_text
        except Exception as exc:
            await self._emit(
                "monitor",
                {"type": "error", "message": str(exc), "error_type": type(exc).__name__},
            )
            await self._emit("progress", {"type": "done", "reason": "failed"})
            raise
        finally:
            self.info.state = "READY"
            await self._emit(
                "monitor", {"type": "state_changed", "state": self.info.state}
            )
            await self._persist_state()

    async def _emit_tool_error(self, record: ToolCallRecord) -> None:
        await self._emit(
            "progress",
            {
                "type": "tool:error",
                "call": {"name": record.name, "state": record.state},
                "error": record.error,
            },
        )

    async def _emit(self, channel: str, event: dict) -> None:
        if channel == "progress":
            envelope = await self.events.emit_progress(event)
        elif channel == "control":
            envelope = await self.events.emit_control(event)
        else:
            envelope = await self.events.emit_monitor(event)
        if self.store is not None:
            await self.store.append_event(self.agent_id, envelope)

    async def _persist_state(self) -> None:
        if self.store is None:
            return
        await self.store.save_messages(self.agent_id, self.messages)
        await self.store.save_tool_call_records(self.agent_id, self.tool_records)
        await self.store.save_info(self.agent_id, self.info)
        await self.store.save_todos(self.agent_id, self.todo_service.snapshot())
