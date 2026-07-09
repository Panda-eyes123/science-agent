"""Agent identifier generation."""

from uuid import uuid4


def generate_agent_id(prefix: str = "agent") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
