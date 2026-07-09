"""Project-specific exception hierarchy."""


class ScienceAgentError(Exception):
    """Base exception for the SDK."""


class ConfigurationError(ScienceAgentError):
    """Raised when runtime configuration is incomplete or invalid."""


class ProviderError(ScienceAgentError):
    """Raised when a model provider fails."""


class ToolExecutionError(ScienceAgentError):
    """Raised when a tool cannot complete successfully."""


class PermissionDeniedError(ScienceAgentError):
    """Raised when a tool call is denied by the permission layer."""


class SandboxError(ScienceAgentError):
    """Raised when a sandbox operation fails."""


class StoreError(ScienceAgentError):
    """Raised when persistence fails."""
