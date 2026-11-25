"""Local registry of participating Git repositories on the metadata branch."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from git import Repo

from .constants import GC_DIRECTORY, GIT_REGULAR_FILE_MODE, NODE_URL_FILE, NODES_DIRECTORY
from .initialization import _branch_oid, _failure, _has_gc_directory
from .metadata import (
    Entries,
    _blob,
    _Problem,
    _reject,
    _subtree,
    _tree,
    _write_tree,
    prepare_commit,
    publish_commit,
)
from .result import Failure, FailureReason, Result, Success


@dataclass(frozen=True)
class Node:
    name: str
    url: str


def _validate(node: Node, reason: FailureReason) -> None:
    # Names are literal tree components. Endpoints are opaque Git addresses.
    name = node.name
    if (
        not name.strip()
        or not name.isprintable()
        or "/" in name
        or "\\" in name
        or name.lower() in {".", "..", ".git"}
    ):
        _reject(reason, "Expected a printable node name suitable for a single directory")
    if not node.url.strip() or not node.url.isprintable():
        _reject(reason, "Expected a nonblank printable node URL")


class _Registry:
    def __init__(self, repo: Repo):
        self.repo = repo
        parent = _branch_oid(repo)
        if parent is None or not _has_gc_directory(repo, parent):
            _reject(FailureReason.NOT_INITIALIZED, "Run gc init first")
        self.parent = parent
        self.root = _tree(repo, parent)
        self.gc = _subtree(repo, self.root, GC_DIRECTORY)
        self.entries: Entries = _subtree(repo, self.gc, NODES_DIRECTORY)
        self.nodes = []
        for name in sorted(self.entries):
            entry = _subtree(repo, self.entries, name).get(NODE_URL_FILE)
            if entry is None or entry[:2] != (GIT_REGULAR_FILE_MODE, "blob"):
                _reject(FailureReason.INVALID_METADATA, f"Missing or invalid URL file for {name}")
            try:
                # Accept the conventional final newline in hand-written URL files.
                url = repo.odb.stream(bytes.fromhex(entry[2])).read().decode().removesuffix("\n")
            except UnicodeDecodeError:
                _reject(FailureReason.INVALID_METADATA, f"Invalid UTF-8 URL for {name}")
            node = Node(name, url)
            _validate(node, FailureReason.INVALID_METADATA)
            self.nodes.append(node)

    def add(self, node: Node) -> Node:
        _validate(node, FailureReason.INVALID_ARGUMENT)
        if node.name in self.entries:
            _reject(FailureReason.ID_CONFLICT, f"Node already exists: {node.name}")
        self.entries[node.name] = _write_tree(
            self.repo, {NODE_URL_FILE: _blob(self.repo, node.url)}
        )
        commit = prepare_commit(
            self.repo,
            self.root,
            self.gc,
            self.entries,
            NODES_DIRECTORY,
            self.parent,
            f"add node {node.name}",
        )
        # Publish against the snapshot we validated, preserving concurrent additions.
        publish_commit(self.repo, commit, self.parent)
        return node


def _run[T](directory: str | Path, operation: Callable[[_Registry], T]) -> Result[T]:
    try:
        with Repo(
            Path(directory).absolute(), search_parent_directories=True, expand_vars=False
        ) as repo:
            return Success(operation(_Registry(repo)))
    except _Problem as exc:
        return Failure(exc.reason, str(exc))
    except Exception as exc:
        return _failure(exc)


def add_node(name: str, url: str, directory: str | Path = ".") -> Result[Node]:
    """Register one uniquely named endpoint without contacting it."""
    return _run(directory, lambda registry: registry.add(Node(name, url)))


def list_nodes(directory: str | Path = ".") -> Result[list[Node]]:
    """Read all registered endpoints from one committed snapshot, ordered by name."""
    return _run(directory, lambda registry: registry.nodes)
