"""Minimal state tracker that can be expanded into resume support later."""


class BreakpointManager:
    def __init__(self) -> None:
        self.current = "READY"

    def set(self, value: str) -> None:
        self.current = value

    def get(self) -> str:
        return self.current
