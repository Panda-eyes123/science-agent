"""Approval request orchestration for tool execution."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from science_agent.core.permission_modes import ApprovalDecision
from science_agent.types import ToolCallRecord

ControlEmitter = Callable[[dict[str, Any]], Awaitable[None]]


class ApprovalCoordinator:
    """Turns an approval wait into control-channel events."""

    def __init__(self, emit_control: ControlEmitter) -> None:
        self._emit_control = emit_control

    async def request(self, record: ToolCallRecord) -> ApprovalDecision:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[tuple[ApprovalDecision, str | None]] = (
            loop.create_future()
        )

        async def respond(decision: ApprovalDecision, note: str | None = None) -> None:
            if decision not in {"allow", "deny"}:
                raise ValueError("Approval decision must be 'allow' or 'deny'.")
            if not future.done():
                future.set_result((decision, note))

        await self._emit_control(
            {
                "type": "permission_required",
                "call": {
                    "id": record.call_id,
                    "name": record.name,
                    "arguments": record.arguments,
                    "state": record.state,
                },
                "respond": respond,
            }
        )
        decision, note = await future
        await self._emit_control(
            {
                "type": "permission_decided",
                "call_id": record.call_id,
                "decision": decision,
                "note": note,
            }
        )
        return decision
