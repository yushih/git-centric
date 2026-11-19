"""Transport-independent application functions.

Git-centric operations return algebraic result values instead of throwing.
"""

from .initialization import initialize_gc, is_gc_initialized
from .result import Failure, FailureReason, Result, Success

__all__ = [
    "Failure",
    "FailureReason",
    "Result",
    "Success",
    "greet",
    "initialize_gc",
    "is_gc_initialized",
]


def greet(name: str = "world") -> str:
    """Return a greeting; reject empty names consistently across interfaces."""
    name = name.strip()
    if not name:
        raise ValueError("Name must not be blank")
    return f"Hello, {name}!"
