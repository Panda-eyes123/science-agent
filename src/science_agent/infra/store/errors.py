"""Persistence-specific errors shared by store implementations."""


class StoreError(RuntimeError):
    """Base class for persistence failures with stable SDK semantics."""


class EventSequenceConflictError(StoreError):
    """Raised when an event sequence is reused with different content."""
