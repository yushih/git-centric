"""An algebraic result type: either a successful value or a described failure.

Callers can use Python's structural pattern matching instead of catching
exceptions. Frozen dataclasses prevent accidental changes to a returned result.
"""

from dataclasses import dataclass
from enum import StrEnum


class FailureReason(StrEnum):
    """Stable machine-readable failure reasons; details are for people."""

    NOT_A_REPOSITORY = "not_a_repository"
    ALREADY_INITIALIZED = "already_initialized"
    BRANCH_CONFLICT = "branch_conflict"
    GIT_ERROR = "git_error"
    IO_ERROR = "io_error"
    UNEXPECTED_ERROR = "unexpected_error"


@dataclass(frozen=True)
class Success[T]:
    """The operation completed; `value` contains its result."""

    value: T


@dataclass(frozen=True)
class Failure:
    """The operation failed; no exception handling is required by the caller."""

    reason: FailureReason
    detail: str


# A sum type: a value is one of these alternatives, never both. For example,
# Result[bool] distinguishes Success(False) from a failure to inspect the repo.
type Result[T] = Success[T] | Failure
