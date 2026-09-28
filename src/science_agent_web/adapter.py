"""SDK wiring and the only translation from internal to public events."""

from science_agent import (
    Agent,
    AgentConfig,
    AgentTemplateDefinition,
    AgentTemplateRegistry,
)
from science_agent.infra.providers.base import ModelProvider
from science_agent.infra.sandbox import LocalSandbox
from science_agent.infra.store.json_store import JSONStore
from science_agent.tools import ToolRegistry
from science_agent.tools.builtin import register_builtin_tools
from science_agent.types import AgentEventEnvelope

from .models import ApprovalEvent, RunEvent, StateEvent, TextEvent, ToolEvent


async def create_agent(
    thread_id: str, store: JSONStore, sandbox: LocalSandbox, provider: ModelProvider
) -> Agent:
    templates = AgentTemplateRegistry()
    tools = register_builtin_tools(ToolRegistry())
    templates.register(
        AgentTemplateDefinition(
            id="science-assistant",
            tools=tools.names(),
            system_prompt=(
                "你是一名严谨的科研助手，默认使用中文。帮助用户梳理研究问题、设计实验和整理记录。"
                "按需使用 todo 工具维护任务，使用文件工具记录用户要求保存的内容。"
                "文件路径必须是工作空间中的相对路径。需要写入时等待用户审批。"
                "不要宣称拥有论文检索、联网或代码执行能力，不要编造文献引用。"
            ),
        )
    )
    return await Agent.create(
        AgentConfig(
            template_id="science-assistant",
            agent_id=thread_id,
            model=provider,
            store=store,
            sandbox=sandbox,
            tool_registry=tools,
            permission_mode="readonly",
        ),
        templates,
    )


def public_event(envelope: AgentEventEnvelope) -> RunEvent | None:
    if not envelope.run_id:
        return None
    base = {
        "run_id": envelope.run_id,
        "seq": envelope.seq,
        "timestamp": envelope.timestamp,
    }
    event = envelope.event
    kind = event.get("type")
    if kind == "text_chunk":
        return TextEvent(**base, message_id=event["message_id"], delta=event["delta"])
    if kind in {"tool:start", "tool:end", "tool:error"}:
        call = event["call"]
        return ToolEvent(
            **base,
            type={
                "tool:start": "tool.started",
                "tool:end": "tool.completed",
                "tool:error": "tool.failed",
            }[kind],
            call_id=call["id"],
            name=call["name"],
            arguments=call.get("arguments", {}),
            result=call.get("result"),
            error=event.get("error"),
        )
    if kind == "permission_required":
        call = event["call"]
        return ApprovalEvent(
            **base,
            type="approval.required",
            call_id=call["id"],
            name=call["name"],
            arguments=call["arguments"],
        )
    if kind == "permission_decided":
        return ApprovalEvent(
            **base,
            type="approval.resolved",
            call_id=event["call_id"],
            decision=event["decision"],
        )
    if kind == "web_state":
        return StateEvent(**base, status=event["status"], error=event.get("error"))
    return None
