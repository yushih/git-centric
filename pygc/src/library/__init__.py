"""Transport-independent application functions.

Git-centric operations return algebraic result values instead of throwing.
"""

from .initialization import initialize_gc, is_gc_initialized
from .pull_requests import (
    Comment,
    FileChange,
    PullRequest,
    PullRequestDetails,
    add_comment,
    create_pull_request,
    delete_comment,
    list_comments,
    list_pull_requests,
    show_pull_request,
    update_comment,
    update_pull_request,
)
from .result import Failure, FailureReason, Result, Success

__all__ = [
    "Comment",
    "FileChange",
    "PullRequest",
    "PullRequestDetails",
    "show_pull_request",
    "add_comment",
    "create_pull_request",
    "delete_comment",
    "update_comment",
    "list_comments",
    "list_pull_requests",
    "update_pull_request",
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
