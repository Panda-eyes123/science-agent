"""Minimal context shaping for the first runtime milestone."""

from science_agent.types import Message


class ContextManager:
    """Keeps only the most recent messages for provider calls."""

    def __init__(self, max_messages: int = 24) -> None:
        self.max_messages = max_messages

    def prepare_messages(self, messages: list[Message]) -> list[Message]:
        start = (
            max(0, len(messages) - self.max_messages) if self.max_messages > 0 else 0
        )
        # tool 结果必须与发起它的 assistant 消息一起保留。
        while start > 0 and messages[start].role == "tool":
            start -= 1
        selected = list(messages[start:])
        # 取消可能留下尚未执行完的工具批次，不把不完整协议交给下一轮模型。
        result: list[Message] = []
        index = 0
        while index < len(selected):
            message = selected[index]
            if message.tool_calls:
                end = index + 1
                while end < len(selected) and selected[end].role == "tool":
                    end += 1
                expected = {call.call_id for call in message.tool_calls}
                actual = {item.tool_call_id for item in selected[index + 1 : end]}
                if expected == actual:
                    result.extend(selected[index:end])
                index = end
            else:
                if message.role != "tool":
                    result.append(message)
                index += 1
        return result
