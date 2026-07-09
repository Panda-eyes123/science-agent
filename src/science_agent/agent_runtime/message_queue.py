"""A tiny async queue wrapper for user and reminder messages."""

import asyncio
from dataclasses import dataclass
from typing import Literal

PendingKind = Literal["user", "reminder"]


@dataclass(slots=True)
class PendingMessage:
    kind: PendingKind
    text: str


class MessageQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[PendingMessage] = asyncio.Queue()

    async def put(self, kind: PendingKind, text: str) -> None:
        await self._queue.put(PendingMessage(kind=kind, text=text))

    async def get(self) -> PendingMessage:
        return await self._queue.get()

    def empty(self) -> bool:
        return self._queue.empty()
