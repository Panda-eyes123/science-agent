"""Async event bus used by the runtime and tests."""

import asyncio
import contextlib
import time
from collections import defaultdict
from typing import AsyncIterator, Iterable

from science_agent.types import AgentChannel, AgentEventEnvelope


class EventBus:
    """Broadcasts runtime events to async subscribers."""

    def __init__(self) -> None:
        self._seq = 0
        self._subscribers: dict[
            AgentChannel, list[asyncio.Queue[AgentEventEnvelope]]
        ] = defaultdict(list)

    async def emit(self, channel: AgentChannel, event: dict) -> AgentEventEnvelope:
        self._seq += 1
        envelope = AgentEventEnvelope(
            seq=self._seq,
            timestamp=time.time(),
            channel=channel,
            event=event,
        )
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
        queue: asyncio.Queue[AgentEventEnvelope] = asyncio.Queue()
        selected = list(channels)
        for channel in selected:
            self._subscribers[channel].append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            for channel in selected:
                with contextlib.suppress(ValueError):
                    self._subscribers[channel].remove(queue)
