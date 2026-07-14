"""Sequential tool execution for the phase-one runtime."""

from collections.abc import Awaitable, Callable

from science_agent.agent_runtime.permission_manager import PermissionManager
from science_agent.core.permission_modes import ApprovalDecision
from science_agent.tools.base import ToolExecutionContext
from science_agent.tools.registry import ToolRegistry
from science_agent.types import ToolCallRecord, ToolCallRequest, utc_now_iso

ApprovalHandler = Callable[[ToolCallRecord], Awaitable[ApprovalDecision]]


class ToolRunner:
    def __init__(self, registry: ToolRegistry, permissions: PermissionManager) -> None:
        self.registry = registry
        self.permissions = permissions

    async def run(
        self,
        call: ToolCallRequest,
        context: ToolExecutionContext,
        approval_handler: ApprovalHandler | None = None,
    ) -> ToolCallRecord:
        record = ToolCallRecord(
            call_id=call.call_id or f"call_{utc_now_iso()}",
            name=call.name,
            arguments=call.arguments,
            state="PENDING",
        )
        try:
            tool = self.registry.get(call.name)
            decision = self.permissions.evaluate(readonly=tool.readonly)
            if decision == "deny":
                record.state = "DENIED"
                record.error = "Tool call denied by permission policy."
                return record
            if decision == "ask":
                if approval_handler is None:
                    record.state = "DENIED"
                    record.error = "Tool call requires approval in this mode."
                    return record
                record.state = "APPROVAL_REQUIRED"
                record.updated_at = utc_now_iso()
                approval = await approval_handler(record)
                if approval != "allow":
                    record.state = "DENIED"
                    record.error = "Tool call denied by approval response."
                    return record
                record.state = "APPROVED"
                record.updated_at = utc_now_iso()
            record.state = "EXECUTING"
            record.updated_at = utc_now_iso()
            record.result = await tool.run(call.arguments, context)
            record.state = "COMPLETED"
        except Exception as exc:
            record.state = "FAILED"
            record.error = str(exc)
        finally:
            record.updated_at = utc_now_iso()
        return record
