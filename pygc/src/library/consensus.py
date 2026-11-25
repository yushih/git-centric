"""Finalize the local metadata history against its registered peers."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from git import Repo
from git.exc import GitCommandError

from .constants import FINALIZE_TEMP_PREFIX, GC_REF, GIT_NOTES_REF
from .initialization import _branch_oid, _git, _git_result, _has_gc_directory
from .metadata import _reject, publish_commit
from .nodes import Node, _Registry, _run
from .result import FailureReason, Result


@dataclass(frozen=True)
class Finalization:
    finalized: bool
    tip: str
    successful: tuple[str, ...]
    conflicts: tuple[str, ...]
    warnings: tuple[str, ...]


@contextmanager
def _temporary_ref(repo: Repo) -> Iterator[str]:
    # Git notes requires a ref under refs/notes. Each invocation owns its scratch
    # ref, so fetching does not disturb FETCH_HEAD or another finalizer.
    ref = FINALIZE_TEMP_PREFIX + uuid4().hex
    try:
        yield ref
    finally:
        _git(repo, "update-ref", "-d", ref)


def _fetch(repo: Repo, node: Node, source: str, destination: str) -> None:
    _git(
        repo,
        "fetch",
        "--no-tags",
        "--no-write-fetch-head",
        "--no-recurse-submodules",
        "--refmap=",
        "--",
        node.url,
        f"{source}:{destination}",
    )


def _push(repo: Repo, node: Node, oid: str, ref: str) -> tuple[int, str]:
    # The porcelain status distinguishes a history rejection from hook/policy
    # failures. An explicit refspec and disabled follow-tags limit the transfer.
    return _git_result(
        repo,
        "push",
        "--porcelain",
        "--no-follow-tags",
        "--recurse-submodules=no",
        "--",
        node.url,
        f"{oid}:{ref}",
    )


def _reconcile(repo: Repo, local: str, remote: str, name: str) -> str | None:
    """Return the published tip, or None for an actual content conflict."""
    if not _has_gc_directory(repo, remote):
        _reject(FailureReason.INVALID_METADATA, f"Missing Git-centric directory on node {name}")
    if _git_result(repo, "merge-base", "--is-ancestor", remote, local)[0] == 0:
        return local
    if _git_result(repo, "merge-base", "--is-ancestor", local, remote)[0] == 0:
        merged = remote
    else:
        # Independently initialized nodes can have distinct roots. Merge their
        # committed trees without involving the current checkout or index.
        status, tree = _git_result(
            repo, "merge-tree", "--write-tree", "--allow-unrelated-histories", local, remote
        )
        if status == 1:
            return None
        merged = _git(
            repo,
            "commit-tree",
            tree,
            "-p",
            local,
            "-p",
            remote,
            "-m",
            f"merge metadata from node {name}",
        )
    publish_commit(repo, merged, local)
    return merged


def _annotated_commit(repo: Repo, ref: str, target: str, message: str) -> str:
    # Check for the exact line so rerunning a finalization preserves existing
    # annotations and does not repeatedly append the same outcome.
    status, blob = _git_result(repo, "notes", f"--ref={ref}", "list", target)
    if status == 0 and message in _git(repo, "cat-file", "blob", blob).splitlines():
        return _git(repo, "rev-parse", ref)

    # Let Git lay out the notes tree, including its fanout directories. Publish
    # that tree with the original parents and a subject identifying the target.
    _git(repo, "notes", f"--ref={ref}", "append", "-m", message, target)
    tree, *parents = _git(repo, "show", "-s", "--format=%T %P", ref).split()
    ancestry = [arg for parent in parents for arg in ("-p", parent)]
    return _git(repo, "commit-tree", tree, *ancestry, "-m", f"annotate {target}: {message}")


def _notify_conflict(repo: Repo, node: Node, message: str) -> bool:
    # Refresh the peer's tip and base the annotation on its own notes history.
    with _temporary_ref(repo) as branch, _temporary_ref(repo) as notes:
        _fetch(repo, node, GC_REF, branch)
        target = _git(repo, "rev-parse", branch)
        if _git(repo, "ls-remote", "--refs", "--", node.url, GIT_NOTES_REF):
            _fetch(repo, node, GIT_NOTES_REF, notes)
        commit = _annotated_commit(repo, notes, target, message)
        status, _ = _push(repo, node, commit, GIT_NOTES_REF)
        return status == 0


def _mark_unfinalized(repo: Repo, tip: str) -> None:
    # Stage the annotation privately. Publish it only if both the candidate
    # and the original notes history still match in a single ref transaction.
    with _temporary_ref(repo) as notes:
        previous = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)", GIT_NOTES_REF)
        old = dict(line.split() for line in previous.splitlines()).get(GIT_NOTES_REF)
        if old:
            _git(repo, "update-ref", notes, old)
        new = _annotated_commit(repo, notes, tip, "not finalized")
        update = f"update {GIT_NOTES_REF} {new} {old}" if old else f"create {GIT_NOTES_REF} {new}"
        _git(repo, "update-ref", "--stdin", stdin=f"verify {GC_REF} {tip}\n{update}\n".encode())


def _finalize(registry: _Registry) -> Finalization:
    repo, tip = registry.repo, registry.parent
    successful: list[str] = []
    conflicts: list[Node] = []
    warnings: list[str] = []

    # 1. Push the current candidate to each node in the original registry.
    for node in registry.nodes:
        try:
            status, report = _push(repo, node, tip, GC_REF)
            if status == 0:
                successful.append(node.name)
                continue

            # 2. Only a history rejection calls for reconciliation. Count a
            # clean local merge as success; carry that tip to the next push.
            if not any(
                line.startswith("!\t")
                and line.endswith(("[rejected] (non-fast-forward)", "[rejected] (fetch first)"))
                for line in report.splitlines()
            ):
                warnings.append(f"push rejected by node {node.name}")
                continue
            with _temporary_ref(repo) as incoming:
                _fetch(repo, node, GC_REF, incoming)
                remote = _git(repo, "rev-parse", incoming)
        except GitCommandError:
            warnings.append(f"node unreachable: {node.name}")
            continue

        # Local Git failures (including a lost ref race) abort the operation.
        merged = _reconcile(repo, tip, remote, node.name)
        if merged is None:
            conflicts.append(node)
            warnings.append(f"conflict with node {node.name}")
        else:
            tip = merged
            successful.append(node.name)

    # 3. Decide against all registered nodes, including unreachable peers.
    if _branch_oid(repo) != tip:
        _reject(FailureReason.STALE_SNAPSHOT, "Metadata changed during finalization")
    half = len(registry.nodes) // 2
    finalized = len(successful) > half
    if finalized:
        # A success majority stands even if a conflicting peer cannot be annotated.
        message = "conflict: " + ", ".join(successful)
        for node in conflicts:
            try:
                delivered = _notify_conflict(repo, node, message)
            except GitCommandError:
                delivered = False
            if not delivered:
                warnings.append(f"could not publish conflict note to node {node.name}")
    elif len(conflicts) > half:
        # A conflict majority rejects the candidate.
        _reject(FailureReason.CONFLICT_CHANGE, "\n".join([*warnings, "conflict change"]))
    else:
        # No majority: record the unresolved candidate for a later retry.
        _mark_unfinalized(repo, tip)
        warnings.append("no finality")

    return Finalization(
        finalized, tip, tuple(successful), tuple(n.name for n in conflicts), tuple(warnings)
    )


def finalize(directory: str | Path = ".") -> Result[Finalization]:
    """Run one round using the registry and tip from the same snapshot."""

    def run(registry: _Registry) -> Finalization:
        # Registry entries are data. Disable executable Git remote helpers
        # and interactive credential prompts when contacting their endpoints.
        with registry.repo.git.custom_environment(
            LC_ALL="C", GIT_TERMINAL_PROMPT="0", GIT_ALLOW_PROTOCOL="file:git:http:https:ssh"
        ):
            return _finalize(registry)

    return _run(directory, run)
