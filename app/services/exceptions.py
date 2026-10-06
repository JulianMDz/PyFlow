"""Domain errors raised by the service layer.

Services know nothing about HTTP; main.py maps each category to a status code.
"""


class DomainError(Exception):
    """Base class for business-rule failures."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    """A referenced resource does not exist (→ 404)."""


class ConflictError(DomainError):
    """The request clashes with the current state of a resource (→ 409)."""


class BusinessRuleError(DomainError):
    """The input is well-formed but violates a business rule (→ 422)."""
