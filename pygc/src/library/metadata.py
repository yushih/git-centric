"""Shared Git tree primitives; none uses the checkout or index."""

import re
from collections.abc import Callable, Sequence
from typing import NoReturn
from urllib.parse import quote

from git import Repo

from .constants import GC_DIRECTORY, GC_REF, GIT_DIRECTORY_MODE, GIT_REGULAR_FILE_MODE
from .initialization import _git
from .result import FailureReason


class _Problem(Exception):
    def __init__(self, reason: FailureReason, detail: str):
        self.reason = reason
        super().__init__(detail)


def _reject(reason: FailureReason, detail: str) -> NoReturn:
    raise _Problem(reason, detail)


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


def _blob(repo: Repo, text: str | bytes) -> tuple[str, str, str]:
    return (
        GIT_REGULAR_FILE_MODE,
        "blob",
        _git(
            repo,
            "hash-object",
            "-w",
            "--stdin",
            stdin=text.encode() if isinstance(text, str) else text,
        ),
    )


def prepare_commit(
    repo: Repo,
    root: Entries,
    gc: Entries,
    entries: Entries,
    directory: str,
    parent: str,
    message: str,
    git: Callable[..., str] = _git,
) -> str:
    """Build a one-parent metadata commit, preserving all unrelated tree entries."""
    gc[directory] = _write_tree(repo, entries)
    root[GC_DIRECTORY] = _write_tree(repo, gc)
    tree = _write_tree(repo, root)[2]
    return git(repo, "commit-tree", tree, "-p", parent, "-m", message)


def publish_commit(
    repo: Repo,
    commit: str,
    parent: str,
    git: Callable[..., str] = _git,
    *,
    branch_ref: str = GC_REF,
) -> None:
    """Compare-and-swap the selected branch ref; never overwrite a racing writer."""
    git(
        repo,
        "update-ref",
        "--stdin",
        stdin=f"option no-deref\nupdate {branch_ref} {commit} {parent}\n".encode(),
    )


def _encode(value: str) -> str:
    # urllib always leaves ~ unescaped, although it is a PR delimiter.
    return quote(value, safe="").replace("~", "%7E")


def _title(title: str) -> None:
    if not title.strip() or "\0" in title:
        _reject(FailureReason.INVALID_ARGUMENT, "Title must be nonblank and contain no NUL")


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
