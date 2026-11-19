"""Transport-independent application functions.

Git-centric operations return algebraic result values instead of throwing.
"""

from .initialization import initialize_gc, is_gc_initialized
from .issues import (
    Issue,
    IssueDetails,
    add_issue_comment,
    create_issue,
    delete_issue_comment,
    list_issue_comments,
    list_issues,
    show_issue,
    update_issue,
    update_issue_comment,
)
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
    read_pr_diff,
    show_pull_request,
    update_comment,
    update_pull_request,
)
from .repository import RepositoryContext, get_repository
from .result import Failure, FailureReason, Result, Success

__all__ = [
    "RepositoryContext",
    "get_repository",
    "Issue",
    "IssueDetails",
    "create_issue",
    "update_issue",
    "list_issues",
    "show_issue",
    "add_issue_comment",
    "update_issue_comment",
    "delete_issue_comment",
    "list_issue_comments",
    "Comment",
    "FileChange",
    "PullRequest",
    "PullRequestDetails",
    "show_pull_request",
    "read_pr_diff",
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
