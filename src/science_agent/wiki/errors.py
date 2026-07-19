"""Wiki-domain errors."""


class WikiError(Exception):
    """Base error for the personal knowledge layer."""


class WikiValidationError(WikiError):
    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


class WikiConflictError(WikiError):
    """Raised when a changeset targets an unexpected page revision."""


class WikiNotFoundError(WikiError):
    """Raised when a changeset references a missing page."""
