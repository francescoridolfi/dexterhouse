# SPDX-License-Identifier: AGPL-3.0-or-later
"""Typed domain errors shared by the apps; the API maps them to RFC 9457 problems."""


class DomainError(Exception):
    """Base of the errors the API turns into `application/problem+json`."""

    status = 400
    slug = "bad-request"
    title = "Bad request"

    def __init__(self, detail: str, errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.errors = errors or []


class InvalidTransitionError(DomainError):
    """A transition the state machine does not allow; no event is emitted."""

    status = 409
    slug = "invalid-transition"
    title = "Invalid transition"


class ConflictError(DomainError):
    status = 409
    slug = "conflict"
    title = "Conflict"


class BudgetExhaustedError(DomainError):
    """A budget (project or organization) is exhausted: 402 `budget-exceeded`."""

    status = 402
    slug = "budget-exceeded"
    title = "Budget exceeded"


class ValidationFailedError(DomainError):
    """Input or pre-start validation failed; `errors` lists `{field, message}`."""

    status = 400
    slug = "validation-error"
    title = "Validation failed"


def check_transition(
    entity: str, current: str, target: str, allowed: dict[str, frozenset[str]]
) -> None:
    """Raise :class:`InvalidTransitionError` unless `current -> target` is in `allowed`."""
    if target not in allowed.get(current, frozenset()):
        raise InvalidTransitionError(f"{entity} cannot go from {current} to {target}")
