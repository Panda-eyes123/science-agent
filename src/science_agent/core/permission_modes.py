"""Simple permission mode helpers for the first milestone."""

from typing import Literal

PermissionMode = Literal["auto", "readonly", "manual", "deny"]
PermissionDecision = Literal["allow", "deny", "ask"]
ApprovalDecision = Literal["allow", "deny"]


def decide_permission(mode: PermissionMode, readonly: bool) -> PermissionDecision:
    if mode == "auto":
        return "allow"
    if mode == "deny":
        return "deny"
    if mode == "readonly":
        return "allow" if readonly else "ask"
    return "ask"
