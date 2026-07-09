"""Permission evaluation wrapper."""

from science_agent.core.permission_modes import (
    PermissionDecision,
    PermissionMode,
    decide_permission,
)


class PermissionManager:
    def __init__(self, mode: PermissionMode = "auto") -> None:
        self.mode = mode

    def evaluate(self, readonly: bool) -> PermissionDecision:
        return decide_permission(self.mode, readonly)
