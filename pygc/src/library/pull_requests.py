"""Pull request metadata stored in immutable Git trees, without a checkout.

Only publication mutates a ref. The old commit is supplied to update-ref so a
concurrent writer wins safely instead of having their changes silently replaced.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import quote, unquote

from git import Repo

from .constants import (
    COMMENT_MAIN,
    COMMENT_PREFIX,
    GC_DIRECTORY,
    GC_REF,
    GIT_DIRECTORY_MODE,
    GIT_REGULAR_FILE_MODE,
    PR_CLOSED,
    PR_COMPARE_SEPARATOR,
    PR_DIRECTORY,
    PR_DRAFT,
    PR_ID_SEPARATOR,
    PR_TITLE_SEPARATOR,
)
from .ids import generate_id
from .initialization import _branch_oid, _failure, _git, _has_gc_directory
from .result import Failure, FailureReason, Result, Success


@dataclass(frozen=True)
class PullRequest:
    id: str
    title: str
    compare: str
    base: str
    author: str = ""
    created_at: str = ""
    draft: bool = False
    closed: bool = False
    merged: bool = False


@dataclass(frozen=True)
class Comment:
    id: str
    text: str
    replies_to: tuple[str, ...] = ()


class _Problem(Exception):
    def __init__(self, reason: FailureReason, detail: str):
        self.reason = reason
        super().__init__(detail)


def _reject(reason: FailureReason, detail: str) -> None:
    raise _Problem(reason, detail)


def _encode(value: str) -> str:
    # urllib always leaves ~ unescaped, although it is a PR delimiter.
    return quote(value, safe="").replace("~", "%7E")


def _name(pr: PullRequest) -> str:
    prefix = (PR_CLOSED if pr.closed else "") + (PR_DRAFT if pr.draft else "")
    return (
        f"{prefix}{_encode(pr.compare)}{PR_COMPARE_SEPARATOR}{_encode(pr.base)}"
        f"{PR_ID_SEPARATOR}{pr.id}{PR_TITLE_SEPARATOR}{_encode(pr.title)}"
    )


def _parse(name: str) -> PullRequest:
    # Accept historical single flags and either combined order. Writers use a
    # canonical order; repeated flags indicate corrupt metadata.
    flags: set[str] = set()
    while name.startswith((PR_CLOSED, PR_DRAFT)):
        flag = PR_CLOSED if name.startswith(PR_CLOSED) else PR_DRAFT
        if flag in flags:
            _reject(FailureReason.INVALID_METADATA, "Repeated PR flag")
        flags.add(flag)
        name = name[len(flag) :]
    try:
        branches, rest = name.split(PR_ID_SEPARATOR, 1)
        compare, base = branches.split(PR_COMPARE_SEPARATOR, 1)
        identifier, title = rest.split(PR_TITLE_SEPARATOR, 1)
        _identifier(identifier)
        if not compare or not base or not unquote(title).strip():
            raise ValueError("Empty PR component")
        return PullRequest(
            identifier,
            unquote(title),
            unquote(compare),
            unquote(base),
            draft=PR_DRAFT in flags,
            closed=PR_CLOSED in flags,
        )
    except (ValueError, _Problem) as exc:
        raise _Problem(FailureReason.INVALID_METADATA, f"Malformed PR directory: {name}") from exc


def _identifier(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        _reject(FailureReason.INVALID_ARGUMENT, "IDs must contain letters, digits, _ or -")


# Entries retain both mode and object ID, preserving unrelated blobs and subtrees.
type Entries = dict[str, tuple[str, str, str]]


def _tree(repo: Repo, oid: str) -> Entries:
    entries = {}
    for line in _git(repo, "ls-tree", "-z", oid).split("\0"):
        if line:
            metadata, name = line.split("\t", 1)
            mode, kind, obj = metadata.split(" ")
            entries[name] = (mode, kind, obj)
    return entries


def _subtree(repo: Repo, entries: Entries, name: str) -> Entries:
    if name not in entries:
        return {}
    mode, kind, oid = entries[name]
    if mode != GIT_DIRECTORY_MODE or kind != "tree":
        _reject(FailureReason.INVALID_METADATA, f"Expected directory: {name}")
    return _tree(repo, oid)


def _write_tree(repo: Repo, entries: Entries) -> tuple[str, str, str]:
    data = b"".join(
        f"{mode} {kind} {oid}\t{name}\0".encode() for name, (mode, kind, oid) in entries.items()
    )
    return GIT_DIRECTORY_MODE, "tree", _git(repo, "mktree", "-z", stdin=data)


def _blob(repo: Repo, text: str) -> tuple[str, str, str]:
    return (
        GIT_REGULAR_FILE_MODE,
        "blob",
        _git(repo, "hash-object", "-w", "--stdin", stdin=text.encode()),
    )


class _Store:
    def __init__(self, repo: Repo):
        self.repo = repo
        oid = _branch_oid(repo)
        if oid is None or not _has_gc_directory(repo, oid):
            _reject(FailureReason.NOT_INITIALIZED, "Run gc init first")
        assert oid is not None
        self.oid = oid
        self.root = _tree(repo, oid)
        self.gc = _subtree(repo, self.root, GC_DIRECTORY)
        self.prs = _subtree(repo, self.gc, PR_DIRECTORY)
        self.records: dict[str, tuple[str, PullRequest]] = {}
        for name, entry in self.prs.items():
            pr = _parse(name)
            if entry[1] != "tree" or pr.id in self.records:
                _reject(FailureReason.INVALID_METADATA, "Invalid or duplicate PR directory")
            self.records[pr.id] = name, pr

    def get(self, identifier: str) -> tuple[str, PullRequest]:
        _identifier(identifier)
        if identifier not in self.records:
            _reject(FailureReason.NOT_FOUND, f"Unknown pull request: {identifier}")
        return self.records[identifier]

    def publish(self, message: str) -> None:
        self.gc[PR_DIRECTORY] = _write_tree(self.repo, self.prs)
        self.root[GC_DIRECTORY] = _write_tree(self.repo, self.gc)
        tree = _write_tree(self.repo, self.root)[2]
        commit = _git(self.repo, "commit-tree", tree, "-p", self.oid, "-m", message)
        _git(
            self.repo,
            "update-ref",
            "--stdin",
            stdin=(f"option no-deref\nupdate {GC_REF} {commit} {self.oid}\n").encode(),
        )


def _run[T](directory: str | Path, operation: Callable[[_Store], T]) -> Result[T]:
    try:
        with Repo(
            Path(directory).absolute(), search_parent_directories=True, expand_vars=False
        ) as repo:
            return Success(operation(_Store(repo)))
    except _Problem as exc:
        return Failure(exc.reason, str(exc))
    except Exception as exc:
        return _failure(exc)


def _branches(repo: Repo) -> dict[str, str]:
    return dict(
        line.split(" ", 1)
        for line in _git(
            repo, "for-each-ref", "--format=%(refname:strip=2) %(objectname)", "refs/heads/"
        ).splitlines()
    )


def _branch(repo: Repo, name: str) -> None:
    if name not in _branches(repo):
        _reject(FailureReason.BRANCH_NOT_FOUND, f"Unknown local branch: {name}")


def _merged(repo: Repo, pr: PullRequest, branches: dict[str, str]) -> bool:
    """Resolve ancestry independently of stored flags, using captured branch tips."""
    if pr.compare not in branches or pr.base not in branches:
        return False
    return branches[pr.compare] in _git(repo, "rev-list", branches[pr.base]).splitlines()


def _title(title: str) -> None:
    if not title.strip() or "\0" in title:
        _reject(FailureReason.INVALID_ARGUMENT, "Title must be nonblank and contain no NUL")


async def create_pull_request(
    compare: str, base: str, title: str, comment: str = "", directory: str | Path = "."
) -> Result[PullRequest]:
    """Create a PR and its main comment; normal Git identity authors the commit."""
    try:
        identifier = await generate_id("pull_request")
    except Exception as exc:
        return _failure(exc)

    def create(store: _Store) -> PullRequest:
        _identifier(identifier)
        _title(title)
        _branch(store.repo, compare)
        _branch(store.repo, base)
        if identifier in store.records:
            _reject(FailureReason.ID_CONFLICT, "Generated pull request ID already exists")
        pr = PullRequest(identifier, title, compare, base)
        pr = replace(pr, merged=_merged(store.repo, pr, _branches(store.repo)))
        store.prs[_name(pr)] = _write_tree(
            store.repo, {COMMENT_PREFIX + COMMENT_MAIN: _blob(store.repo, comment)}
        )
        store.publish(f"Create pull request {identifier}: {title}")
        return pr

    return _run(directory, create)


def _tokens(tokens: Sequence[str], keys: set[str], flags: set[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in tokens:
        key, sep, value = token.partition("=")
        if (sep and key in keys and value) or (not sep and key in flags):
            if key not in result:
                result[key] = value
                continue
        _reject(FailureReason.INVALID_ARGUMENT, f"Invalid or repeated argument: {token}")
    return result


def _origins(store: _Store) -> dict[str, tuple[str, str]]:
    """Resolve creation metadata at the captured snapshot, following stable IDs."""
    # Scan oldest to newest, matching stable IDs, so renames do not reauthor a PR.
    origins: dict[str, tuple[str, str]] = {}
    for oid in reversed(_git(store.repo, "rev-list", "--first-parent", store.oid).splitlines()):
        root = _tree(store.repo, oid)
        gc = _subtree(store.repo, root, GC_DIRECTORY)
        for name in _subtree(store.repo, gc, PR_DIRECTORY):
            identifier = _parse(name).id
            if identifier not in origins:
                author, date = _git(
                    store.repo, "show", "-s", "--format=%an <%ae>%n%aI", oid
                ).splitlines()
                origins[identifier] = author, date
    return origins


def update_pull_request(
    identifier: str, updates: Sequence[str], directory: str | Path = "."
) -> Result[PullRequest]:
    """Rename metadata atomically, retaining all comments and stable identity."""

    def update(store: _Store) -> PullRequest:
        old, pr = store.get(identifier)
        values = _tokens(
            updates, {"compare", "base", "title"}, {"close", "reopen", "draft", "ready"}
        )
        if (
            not values
            or {"close", "reopen"} <= values.keys()
            or {"draft", "ready"} <= values.keys()
        ):
            _reject(FailureReason.INVALID_ARGUMENT, "Supply updates without contradictory actions")
        for key in ("compare", "base"):
            if key in values:
                _branch(store.repo, values[key])
        if "title" in values:
            _title(values["title"])
        pr = replace(
            pr,
            compare=values.get("compare", pr.compare),
            base=values.get("base", pr.base),
            title=values.get("title", pr.title),
            draft=True if "draft" in values else False if "ready" in values else pr.draft,
            closed=True if "close" in values else False if "reopen" in values else pr.closed,
        )
        # Read history before publication: a read failure must not leave a
        # successfully committed update behind a Failure result. The snapshot
        # also gives no-op updates the same original metadata as real writes.
        author, created_at = _origins(store)[identifier]
        pr = replace(
            pr,
            author=author,
            created_at=created_at,
            merged=_merged(store.repo, pr, _branches(store.repo)),
        )
        new = _name(pr)
        if new != old:
            store.prs[new] = store.prs.pop(old)
            store.publish(f"Update pull request {identifier}")
        return pr

    return _run(directory, update)


def list_pull_requests(
    filters: Sequence[str] = (), directory: str | Path = "."
) -> Result[list[PullRequest]]:
    """List PRs, deriving creation identity from history rather than current path."""

    def listing(store: _Store) -> list[PullRequest]:
        values = _tokens(filters, {"author", "compare", "base", "title"}, {"open", "mine"})
        for key in ("compare", "base"):
            if key in values:
                _branch(store.repo, values[key])
        try:
            pattern = re.compile(values["title"]) if "title" in values else None
        except re.error as exc:
            raise _Problem(FailureReason.INVALID_ARGUMENT, str(exc)) from exc
        mine = (
            _git(store.repo, "var", "GIT_AUTHOR_IDENT").rsplit(">", 1)[0].split("<")[-1]
            if "mine" in values
            else None
        )
        origins = _origins(store)
        branches = _branches(store.repo)
        result = []
        for _, pr in store.records.values():
            author, date = origins[pr.id]
            pr = replace(
                pr, author=author, created_at=date, merged=_merged(store.repo, pr, branches)
            )
            email = author.rsplit("<", 1)[-1].removesuffix(">")
            if "open" in values and (pr.draft or pr.closed or pr.merged):
                continue
            if mine is not None and email != mine:
                continue
            if "author" in values and values["author"] not in {
                author,
                email,
                author.rsplit(" <", 1)[0],
            }:
                continue
            if any(
                key in values and values[key] != getattr(pr, key) for key in ("compare", "base")
            ):
                continue
            if pattern is not None and not pattern.search(pr.title):
                continue
            result.append(pr)
        return sorted(result, key=lambda pr: (pr.created_at, pr.id))

    return _run(directory, listing)


def _comments(store: _Store, name: str) -> list[Comment]:
    result = []
    for filename, (mode, kind, oid) in _subtree(store.repo, store.prs, name).items():
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
            text = store.repo.odb.stream(bytes.fromhex(oid)).read().decode("utf-8")
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


def list_comments(identifier: str, directory: str | Path = ".") -> Result[list[Comment]]:
    """Read exact comment contents and reply IDs."""
    return _run(directory, lambda store: _comments(store, store.get(identifier)[0]))


async def add_comment(target: str, text: str, directory: str | Path = ".") -> Result[Comment]:
    """Append a comment; target is a PR ID optionally followed by :reply IDs."""
    try:
        identifier = await generate_id("comment")
    except Exception as exc:
        return _failure(exc)

    def add(store: _Store) -> Comment:
        _identifier(identifier)
        pr_id, *replies = target.split(PR_TITLE_SEPARATOR)
        name, _ = store.get(pr_id)
        comments = _comments(store, name)
        ids = {comment.id for comment in comments}
        if identifier in ids:
            _reject(FailureReason.ID_CONFLICT, "Generated comment ID already exists")
        for reply in replies:
            _identifier(reply)
            if reply not in ids:
                _reject(FailureReason.NOT_FOUND, f"Unknown reply comment: {reply}")
        entries = _subtree(store.repo, store.prs, name)
        filename = COMMENT_PREFIX + PR_TITLE_SEPARATOR.join([identifier, *replies])
        entries[filename] = _blob(store.repo, text)
        store.prs[name] = _write_tree(store.repo, entries)
        store.publish(f"Comment on pull request {pr_id}")
        return Comment(identifier, text, tuple(replies))

    return _run(directory, add)
