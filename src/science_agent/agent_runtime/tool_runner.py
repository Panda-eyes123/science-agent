"""Sequential tool execution for the phase-one runtime."""

from science_agent.agent_runtime.permission_manager import PermissionManager
from science_agent.tools.base import ToolExecutionContext
from science_agent.tools.registry import ToolRegistry
from science_agent.types import ToolCallRecord, ToolCallRequest, utc_now_iso


class ToolRunner:
    def __init__(self, registry: ToolRegistry, permissions: PermissionManager) -> None:
        self.registry = registry
        self.permissions = permissions

    async def run(
        self, call: ToolCallRequest, context: ToolExecutionContext
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
            if decision != "allow":
                record.state = "DENIED"
                record.error = "Tool call requires approval in this mode."
                return record
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
