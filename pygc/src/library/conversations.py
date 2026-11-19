"""Shared conversation records, decoding, and immutable tree edits."""

from dataclasses import dataclass, replace

from git import Repo

from .constants import COMMENT_MAIN, COMMENT_PREFIX, GIT_REGULAR_FILE_MODE, PR_TITLE_SEPARATOR
from .metadata import Entries, _blob, _identifier, _Problem, _reject
from .result import FailureReason


@dataclass(frozen=True)
class Comment:
    id: str
    text: str
    replies_to: tuple[str, ...] = ()


def read_comments(repo: Repo, entries: Entries) -> list[Comment]:
    result = []
    for filename, (mode, kind, oid) in entries.items():
        if (
            not filename.startswith(COMMENT_PREFIX)
            or mode != GIT_REGULAR_FILE_MODE
            or kind != "blob"
        ):
            _reject(FailureReason.INVALID_METADATA, f"Invalid comment: {filename}")
        identifier, *replies = filename[len(COMMENT_PREFIX) :].split(PR_TITLE_SEPARATOR)
        try:
            for value in (identifier, *replies):
                _identifier(value)
        except _Problem as exc:
            # These IDs came from committed data, not the caller's arguments.
            raise _Problem(
                FailureReason.INVALID_METADATA, f"Invalid comment filename: {filename}"
            ) from exc
        # GitPython's default string output strips trailing newlines. Read blob
        # bytes directly to preserve comments exactly, including stdin text.
        try:
            text = repo.odb.stream(bytes.fromhex(oid)).read().decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _Problem(
                FailureReason.INVALID_METADATA, f"Comment is not UTF-8: {filename}"
            ) from exc
        result.append(Comment(identifier, text, tuple(replies)))
    ids = [comment.id for comment in result]
    if len(ids) != len(set(ids)) or COMMENT_MAIN not in ids:
        _reject(FailureReason.INVALID_METADATA, "Duplicate comment IDs or missing main comment")
    if any(reply not in ids for comment in result for reply in comment.replies_to):
        _reject(FailureReason.INVALID_METADATA, "Dangling comment reply")
    return sorted(result, key=lambda comment: (comment.id != COMMENT_MAIN, comment.id))


def validate_cycles(comments: list[Comment]) -> None:
    """Validate every reply edge iteratively, including secondary reply targets."""
    edges = {c.id: c.replies_to for c in comments}
    done: set[str] = set()
    active: set[str] = set()
    for identifier in edges:
        stack = [(identifier, False)]
        while stack:
            current, leaving = stack.pop()
            if leaving:
                active.remove(current)
                done.add(current)
            elif current not in done:
                if current in active:
                    _reject(FailureReason.INVALID_METADATA, "Cycle in comment replies")
                active.add(current)
                stack.append((current, True))
                stack.extend((reply, False) for reply in reversed(edges[current]))


def append_comment(
    repo: Repo, entries: Entries, identifier: str, replies: list[str], text: str
) -> Comment:
    """Validate against the captured conversation before building a new blob."""
    _identifier(identifier)
    comments = read_comments(repo, entries)
    validate_cycles(comments)
    ids = {c.id for c in comments}
    if identifier in ids:
        _reject(FailureReason.ID_CONFLICT, "Generated comment ID already exists")
    for reply in replies:
        _identifier(reply)
        if reply not in ids:
            _reject(FailureReason.NOT_FOUND, f"Unknown reply comment: {reply}")
    comment = Comment(identifier, text, tuple(replies))
    entries[comment_filename(comment)] = _blob(repo, text)
    return comment


def comment_filename(comment: Comment) -> str:
    return COMMENT_PREFIX + PR_TITLE_SEPARATOR.join([comment.id, *comment.replies_to])


def edit_comment(
    repo: Repo, entries: Entries, identifier: str, text: str | None
) -> tuple[Comment, list[str], bool]:
    """Return the selected record, detached reply IDs, and whether anything changed."""
    _identifier(identifier)
    comments = read_comments(repo, entries)
    validate_cycles(comments)
    selected = next((c for c in comments if c.id == identifier), None)
    if selected is None:
        _reject(FailureReason.NOT_FOUND, f"Unknown comment: {identifier}")
    if text is None and identifier == COMMENT_MAIN:
        _reject(FailureReason.INVALID_ARGUMENT, "Main cannot be deleted; clear its text instead")
    if text == selected.text:
        return selected, [], False
    detached = []
    if text is None:
        del entries[comment_filename(selected)]
        for comment in comments:
            if identifier in comment.replies_to:
                updated = replace(
                    comment, replies_to=tuple(r for r in comment.replies_to if r != identifier)
                )
                entries[comment_filename(updated)] = entries.pop(comment_filename(comment))
                detached.append(comment.id)
        return selected, detached, True
    updated = replace(selected, text=text)
    entries[comment_filename(updated)] = _blob(repo, text)
    return updated, detached, True
