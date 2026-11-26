"""Issues stored beside PRs in the metadata branch, independent of source branches."""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote

from git import Repo

from . import policy
from .constants import (
    COMMENT_MAIN,
    COMMENT_PREFIX,
    GC_DIRECTORY,
    GIT_DIRECTORY_MODE,
    ISSUE_CLOSED,
    ISSUE_DIRECTORY,
    ISSUE_TITLE_SEPARATOR,
)
from .conversations import (
    Comment,
    append_comment,
    attributed_comments,
    edit_comment,
    read_comments,
    validate_cycles,
)
from .ids import generate_id
from .initialization import _branch_oid, _failure, _git, _has_gc_directory
from .metadata import (
    _blob,
    _encode,
    _identifier,
    _Problem,
    _reject,
    _subtree,
    _title,
    _tokens,
    _tree,
    _write_tree,
    prepare_commit,
    publish_commit,
)
from .result import Failure, FailureReason, Result, Success


@dataclass(frozen=True)
class Issue:
    id: str
    title: str
    closed: bool = False
    author: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class IssueDetails:
    issue: Issue
    comments: tuple[Comment, ...]
    metadata_tip: str = ""


def _name(issue: Issue) -> str:
    return (
        (ISSUE_CLOSED if issue.closed else "")
        + issue.id
        + ISSUE_TITLE_SEPARATOR
        + _encode(issue.title)
    )


def _parse(name: str) -> Issue:
    """Require canonical escaping so distinct names cannot alias the same record."""
    try:
        closed = name.startswith(ISSUE_CLOSED)
        body = name.removeprefix(ISSUE_CLOSED)
        identifier, encoded = body.split(ISSUE_TITLE_SEPARATOR, 1)
        _identifier(identifier)
        title = unquote(encoded, errors="strict")
        _title(title)
        issue = Issue(identifier, title, closed)
        if _name(issue) != name:
            raise ValueError("Noncanonical issue name")
        return issue
    except (ValueError, _Problem) as exc:
        raise _Problem(FailureReason.INVALID_METADATA, f"Invalid issue directory: {name}") from exc


class _Store:
    """Capture one snapshot; publish only if its ref still has the captured value."""

    def __init__(self, repo: Repo):
        self.repo = repo
        oid = _branch_oid(repo)
        if oid is None or not _has_gc_directory(repo, oid):
            _reject(FailureReason.NOT_INITIALIZED, "Run gc init first")
        self.oid = oid
        self.root = _tree(repo, oid)
        self.gc = _subtree(repo, self.root, GC_DIRECTORY)
        self.entries = _subtree(repo, self.gc, ISSUE_DIRECTORY)
        self.records: dict[str, tuple[str, Issue]] = {}
        for name, (mode, kind, _) in self.entries.items():
            issue = _parse(name)
            if mode != GIT_DIRECTORY_MODE or kind != "tree" or issue.id in self.records:
                _reject(FailureReason.INVALID_METADATA, "Invalid or duplicate issue directory")
            self.records[issue.id] = name, issue
            # All issue operations reject corrupt conversations, even list/update.
            self.comments(name)

    def comments(self, name: str) -> list[Comment]:
        comments = read_comments(self.repo, _subtree(self.repo, self.entries, name))
        validate_cycles(comments)
        return comments

    def get(self, identifier: str) -> tuple[str, Issue]:
        _identifier(identifier)
        if identifier not in self.records:
            _reject(FailureReason.NOT_FOUND, f"Unknown issue: {identifier}")
        return self.records[identifier]

    def origins(self) -> dict[str, tuple[str, str]]:
        # Stable IDs preserve creators when title or state renames the directory.
        origins: dict[str, tuple[str, str]] = {}
        for oid in reversed(_git(self.repo, "rev-list", "--first-parent", self.oid).splitlines()):
            gc = _subtree(self.repo, _tree(self.repo, oid), GC_DIRECTORY)
            for name in _subtree(self.repo, gc, ISSUE_DIRECTORY):
                identifier = _parse(name).id
                if identifier not in origins:
                    author, date = _git(
                        self.repo, "show", "-s", "--format=%an <%ae>%n%aI", oid
                    ).splitlines()
                    origins[identifier] = author, date
        return origins

    def publish(self, message: str, created: Issue | None = None) -> Issue | None:
        commit = prepare_commit(
            self.repo, self.root, self.gc, self.entries, ISSUE_DIRECTORY, self.oid, message, _git
        )
        # Resolve creation fields before publication: a later read failure must
        # never return Failure after a successful write has already taken effect.
        if created is not None:
            author, date = _git(
                self.repo, "show", "-s", "--format=%an <%ae>%n%aI", commit
            ).splitlines()
            created = replace(created, author=author, created_at=date)
        publish_commit(self.repo, commit, self.oid, _git)
        return created


def _run[T](
    directory: str | Path, operation: Callable[[_Store], T], expected_tip: str | None = None
) -> Result[T]:
    try:
        with Repo(
            Path(directory).absolute(), search_parent_directories=True, expand_vars=False
        ) as repo:
            store = _Store(repo)
            # Validate against the same snapshot used by the existing CAS writer.
            if expected_tip is not None and expected_tip != store.oid:
                return Failure(FailureReason.STALE_SNAPSHOT, "Reload the changed conversation")
            return Success(operation(store))
    except _Problem as exc:
        return Failure(exc.reason, str(exc))
    except Exception as exc:
        return _failure(exc)


async def create_issue(title: str, comment: str = "", directory: str | Path = ".") -> Result[Issue]:
    """Create an open issue and its main description in a single commit."""
    try:
        identifier = await generate_id("issue")
    except Exception as exc:
        return _failure(exc)

    def create(store: _Store) -> Issue:
        _identifier(identifier)
        _title(title)
        if identifier in store.records:
            _reject(FailureReason.ID_CONFLICT, "Generated issue ID already exists")
        policy.require(policy.Simple(name="issues.create"), store.repo, store.oid)
        issue = Issue(identifier, title)
        store.entries[_name(issue)] = _write_tree(
            store.repo, {COMMENT_PREFIX + COMMENT_MAIN: _blob(store.repo, comment)}
        )
        result = store.publish(
            f"create issue {identifier} title={json.dumps(title, ensure_ascii=False)}", issue
        )
        assert result is not None
        return result

    return _run(directory, create)


def update_issue(
    identifier: str,
    updates: Sequence[str],
    directory: str | Path = ".",
    *,
    expected_tip: str | None = None,
) -> Result[Issue]:
    """Apply all validated changes atomically; no-op updates retain the ref."""

    def update(store: _Store) -> Issue:
        old, before = store.get(identifier)
        values = _tokens(updates, {"title"}, {"close", "reopen"})
        if not values or {"close", "reopen"} <= values.keys():
            _reject(FailureReason.INVALID_ARGUMENT, "Supply updates without contradictory actions")
        title = values.get("title", before.title)
        _title(title)
        author, date = store.origins()[identifier]
        issue = replace(
            before,
            title=title,
            author=author,
            created_at=date,
            closed=True if "close" in values else False if "reopen" in values else before.closed,
        )
        actions = []
        if before.title != issue.title:
            actions.append(
                f"update issue {identifier} title={json.dumps(title, ensure_ascii=False)}"
            )
        if before.closed != issue.closed:
            actions.append(f"{'close' if issue.closed else 'reopen'} issue {identifier}")
        if actions:
            store.entries[_name(issue)] = store.entries.pop(old)
            store.publish("; ".join(actions))
        return issue

    return _run(directory, update, expected_tip)


def list_issues(filters: Sequence[str] = (), directory: str | Path = ".") -> Result[list[Issue]]:
    """AND filters over issue records; an absent issues subtree is an empty list."""

    def listing(store: _Store) -> list[Issue]:
        values = _tokens(filters, {"author", "title"}, {"open", "closed", "mine"})
        if {"open", "closed"} <= values.keys():
            _reject(FailureReason.INVALID_ARGUMENT, "open and closed are contradictory")
        try:
            pattern = re.compile(values["title"]) if "title" in values else None
        except re.error as exc:
            raise _Problem(FailureReason.INVALID_ARGUMENT, str(exc)) from exc
        mine = (
            _git(store.repo, "var", "GIT_AUTHOR_IDENT").rsplit(">", 1)[0].split("<")[-1]
            if "mine" in values
            else None
        )
        origins = store.origins()
        result = []
        for _, issue in store.records.values():
            author, date = origins[issue.id]
            email = author.rsplit("<", 1)[-1].removesuffix(">")
            if ("open" in values and issue.closed) or ("closed" in values and not issue.closed):
                continue
            if mine is not None and mine != email:
                continue
            if "author" in values and values["author"] not in {
                author,
                email,
                author.rsplit(" <", 1)[0],
            }:
                continue
            if pattern is not None and not pattern.search(issue.title):
                continue
            result.append(replace(issue, author=author, created_at=date))
        return sorted(result, key=lambda issue: issue.id)

    return _run(directory, listing)


def show_issue(
    identifier: str, directory: str | Path = ".", *, include_comment_origins: bool = False
) -> Result[IssueDetails]:
    """Read issue fields and complete conversation from the same snapshot."""

    def show(store: _Store) -> IssueDetails:
        name, issue = store.get(identifier)
        comments = store.comments(name)
        if include_comment_origins:
            attributed = attributed_comments(
                store.repo,
                store.oid,
                ISSUE_DIRECTORY,
                lambda name: _parse(name).id == identifier,
                comments,
            )
            opening = next(c for c in attributed if c.id == COMMENT_MAIN)
            author, date = opening.author, opening.created_at
            comments = list(attributed)
        else:
            author, date = store.origins()[identifier]
        return IssueDetails(
            replace(issue, author=author, created_at=date), tuple(comments), store.oid
        )

    return _run(directory, show)


def list_issue_comments(identifier: str, directory: str | Path = ".") -> Result[list[Comment]]:
    return _run(directory, lambda store: store.comments(store.get(identifier)[0]))


async def add_issue_comment(
    target: str, text: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Comment]:
    """Append a root comment or reply to existing comments within one issue."""
    try:
        identifier = await generate_id("comment")
    except Exception as exc:
        return _failure(exc)

    def add(store: _Store) -> Comment:
        issue_id, *replies = target.split(ISSUE_TITLE_SEPARATOR)
        name, _ = store.get(issue_id)
        entries = _subtree(store.repo, store.entries, name)
        policy.require(policy.Simple(name="issues.comments.add"), store.repo, store.oid)
        result = append_comment(store.repo, entries, identifier, replies, text)
        store.entries[name] = _write_tree(store.repo, entries)
        detail = f" replying to {', '.join(replies)}" if replies else ""
        store.publish(f"add comment {identifier} on issue {issue_id}{detail}")
        return result

    return _run(directory, add, expected_tip)


def _edit(
    target: str, text: str | None, directory: str | Path, *, expected_tip: str | None = None
) -> Result[Comment]:
    def edit(store: _Store) -> Comment:
        parts = target.split(ISSUE_TITLE_SEPARATOR)
        if len(parts) != 2:
            _reject(FailureReason.INVALID_ARGUMENT, "Expected ISSUE_ID:COMMENT_ID")
        issue_id, identifier = parts
        name, _ = store.get(issue_id)
        entries = _subtree(store.repo, store.entries, name)
        result, detached, changed = edit_comment(store.repo, entries, identifier, text)
        if changed:
            store.entries[name] = _write_tree(store.repo, entries)
            action = (
                f"delete comment {identifier}"
                if text is None
                else f"update comment {identifier} text"
            )
            detail = (
                f"; remove replies to {identifier} from comments "
                f"{', '.join(detached)} on issue {issue_id}"
                if detached
                else ""
            )
            store.publish(f"{action} on issue {issue_id}{detail}")
        return result

    return _run(directory, edit, expected_tip)


def update_issue_comment(
    target: str, text: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Comment]:
    return _edit(target, text, directory, expected_tip=expected_tip)


def delete_issue_comment(
    target: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Comment]:
    return _edit(target, None, directory, expected_tip=expected_tip)
