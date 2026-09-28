"""Async event bus used by the runtime and tests."""

import asyncio
import contextlib
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, AsyncIterator, Iterable

from science_agent.types import AgentChannel, AgentEventEnvelope


class EventBus:
    """Broadcasts runtime events to async subscribers."""

    def __init__(
        self, persist: Callable[[AgentEventEnvelope], Awaitable[None]] | None = None
    ) -> None:
        self._seq = 0
        self._persist = persist
        self.run_id: str | None = None
        self._subscribers: dict[
            AgentChannel, list[asyncio.Queue[AgentEventEnvelope]]
        ] = defaultdict(list)

    def restore_sequence(self, seq: int) -> None:
        self._seq = max(self._seq, seq)

    async def emit(self, channel: AgentChannel, event: dict) -> AgentEventEnvelope:
        self._seq += 1
        envelope = AgentEventEnvelope(
            seq=self._seq,
            timestamp=time.time(),
            channel=channel,
            event=event,
            run_id=self.run_id,
        )
        # 先落盘再通知订阅者，确保客户端收到的事件一定能够重放。
        if self._persist is not None:
            await self._persist(envelope)
        for queue in list(self._subscribers[channel]):
            await queue.put(envelope)
        return envelope

    async def emit_progress(self, event: dict) -> AgentEventEnvelope:
        return await self.emit("progress", event)

    async def emit_control(self, event: dict) -> AgentEventEnvelope:
        return await self.emit("control", event)

    async def emit_monitor(self, event: dict) -> AgentEventEnvelope:
        return await self.emit("monitor", event)

    async def subscribe(
        self, channels: Iterable[AgentChannel]
    ) -> AsyncIterator[AgentEventEnvelope]:
        async with self.listen(channels) as queue:
            while True:
                yield await queue.get()

    @contextlib.asynccontextmanager
    async def listen(self, channels: Iterable[AgentChannel]):
        # 进入上下文时即注册，便于调用方先订阅、再补读历史，消除两者之间的丢事件窗口。
        queue: asyncio.Queue[AgentEventEnvelope] = asyncio.Queue()
        selected = list(channels)
        for channel in selected:
            self._subscribers[channel].append(queue)
        try:
            yield queue
        finally:
            for channel in selected:
                with contextlib.suppress(ValueError):
                    self._subscribers[channel].remove(queue)


def serialize_event_for_store(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _serialize_value_for_store(value)
        for key, value in event.items()
        if not callable(value)
    }


def _serialize_value_for_store(value: Any) -> Any:
    if callable(value):
        return None
    if isinstance(value, dict):
        return serialize_event_for_store(value)
    if isinstance(value, list):
        return [_serialize_value_for_store(item) for item in value]
    return value
