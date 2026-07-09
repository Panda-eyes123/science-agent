"""Minimal context shaping for the first runtime milestone."""

from science_agent.types import Message


class ContextManager:
    """Keeps only the most recent messages for provider calls."""

    def __init__(self, max_messages: int = 24) -> None:
        self.max_messages = max_messages

    def prepare_messages(self, messages: list[Message]) -> list[Message]:
        if self.max_messages <= 0:
            return list(messages)
        return list(messages[-self.max_messages :])
