"""Project-specific exception hierarchy."""


class ScienceAgentError(Exception):
    """Base exception for the SDK."""


class ConfigurationError(ScienceAgentError):
    """Raised when runtime configuration is incomplete or invalid."""


class ProviderError(ScienceAgentError):
    """Raised when a model provider fails."""

    retryable = False

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class ProviderAuthenticationError(ProviderError):
    """Raised when provider credentials or access are invalid."""


class ProviderInvalidRequestError(ProviderError):
    """Raised when a provider rejects the request payload."""


class ProviderNotFoundError(ProviderError):
    """Raised when a provider resource such as a model is not found."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider rate limit is hit."""

    retryable = True


class ProviderServerError(ProviderError):
    """Raised when a provider reports a temporary server failure."""

    retryable = True


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request times out."""

    retryable = True


class ProviderNetworkError(ProviderError):
    """Raised when the provider cannot be reached."""

    retryable = True


class ProviderResponseError(ProviderError):
    """Raised when a provider response cannot be parsed."""


class ToolExecutionError(ScienceAgentError):
    """Raised when a tool cannot complete successfully."""


class PermissionDeniedError(ScienceAgentError):
    """Raised when a tool call is denied by the permission layer."""


class SandboxError(ScienceAgentError):
    """Raised when a sandbox operation fails."""


class StoreError(ScienceAgentError):
    """Raised when persistence fails."""
