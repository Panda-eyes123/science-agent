"""Template definitions and registry helpers."""

from dataclasses import dataclass, field
from typing import Any

from science_agent.errors import ConfigurationError


@dataclass(slots=True)
class AgentTemplateDefinition:
    id: str
    system_prompt: str
    model: str | None = None
    tools: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)


class AgentTemplateRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, AgentTemplateDefinition] = {}

    def register(self, template: AgentTemplateDefinition) -> None:
        self._templates[template.id] = template

    def get(self, template_id: str) -> AgentTemplateDefinition:
        try:
            return self._templates[template_id]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown template: {template_id}") from exc
