"""Pull request metadata stored in immutable Git trees, without a checkout.

Only publication mutates a ref. The old commit is supplied to update-ref so a
concurrent writer wins safely instead of having their changes silently replaced.
"""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote

from git import Repo
from git.exc import GitCommandError

from . import policy
from .constants import (
    COMMENT_MAIN,
    COMMENT_PREFIX,
    GC_DIRECTORY,
    GC_REF,
    PR_CLOSED,
    PR_COMPARE_SEPARATOR,
    PR_DIRECTORY,
    PR_DRAFT,
    PR_ID_SEPARATOR,
    PR_TITLE_SEPARATOR,
)
from .conversations import Comment as Comment
from .conversations import attributed_comments, read_comments
from .ids import generate_id
from .initialization import _branch_oid, _failure, _git, _git_result, _has_gc_directory
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
from .patches import FileChange as FileChange
from .patches import changed_files, patch
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
class PullRequestDetails:
    pull_request: PullRequest
    comments: tuple[Comment, ...]
    merge_conflicts: bool | None
    changed_files: tuple[FileChange, ...] | None
    conflicting_files: tuple[str, ...] | None
    merge_analysis_error: str | None
    metadata_tip: str = ""
    base_tip: str | None = None
    compare_tip: str | None = None
    merge_base: str | None = None


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
        commit = prepare_commit(
            self.repo, self.root, self.gc, self.prs, PR_DIRECTORY, self.oid, message, _git
        )
        publish_commit(self.repo, commit, self.oid, _git)


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
        policy.require(
            policy.PullCreate(name="pulls.create", base=base, compare=compare),
            store.repo,
            store.oid,
        )
        pr = PullRequest(identifier, title, compare, base)
        pr = replace(pr, merged=_merged(store.repo, pr, _branches(store.repo)))
        store.prs[_name(pr)] = _write_tree(
            store.repo, {COMMENT_PREFIX + COMMENT_MAIN: _blob(store.repo, comment)}
        )
        store.publish(f"create pr {identifier}: {json.dumps(title, ensure_ascii=False)}")
        return pr

    return _run(directory, create)


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


def _pr_update_message(before: PullRequest, after: PullRequest) -> str:
    """Describe persisted changes, not merely requested tokens or computed state."""
    actions = []
    if before.closed != after.closed:
        actions.append(f"{'close' if after.closed else 'reopen'} pr {after.id}")
    if before.draft != after.draft:
        actions.append(f"mark pr {after.id} {'draft' if after.draft else 'ready'}")
    for field in ("title", "compare", "base"):
        if getattr(before, field) != getattr(after, field):
            # Quoting preserves Unicode and escapes embedded newlines/control
            # characters so user text cannot introduce extra log subjects.
            value = json.dumps(getattr(after, field), ensure_ascii=False)
            actions.append(f"set pr {after.id} {field} to {value}")
    return "; ".join(actions)


def update_pull_request(
    identifier: str,
    updates: Sequence[str],
    directory: str | Path = ".",
    *,
    expected_tip: str | None = None,
) -> Result[PullRequest]:
    """Rename metadata atomically, retaining all comments and stable identity."""

    def update(store: _Store) -> PullRequest:
        old, pr = store.get(identifier)
        before = pr
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
        # Retargeting is equivalent to opening this PR against the proposed base.
        # Use both final branches even when the same request also changes compare.
        if pr.base != before.base:
            policy.require(
                policy.PullCreate(name="pulls.create", base=pr.base, compare=pr.compare),
                store.repo,
                store.oid,
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
            store.publish(_pr_update_message(before, pr))
        return pr

    return _run(directory, update, expected_tip)


def merge_pull_request(identifier: str, directory: str | Path = ".") -> Result[PullRequest]:
    """Authorize and merge the captured compare tip into its local base ref."""

    def merge(store: _Store) -> PullRequest:
        _, pr = store.get(identifier)
        repo = store.repo
        policy.require(
            policy.PullMerge(name="pulls.merge", id=identifier, base=pr.base), repo, store.oid
        )
        branches = _branches(repo)
        for name in (pr.base, pr.compare):
            if name not in branches:
                _reject(FailureReason.BRANCH_NOT_FOUND, f"Unknown local branch: {name}")
        base, compare = branches[pr.base], branches[pr.compare]
        if _git_result(repo, "merge-base", "--is-ancestor", compare, base)[0] == 0:
            merged = base
        elif _git_result(repo, "merge-base", "--is-ancestor", base, compare)[0] == 0:
            merged = compare
        else:
            status, tree = _git_result(repo, "merge-tree", "--write-tree", base, compare)
            if status:
                _reject(FailureReason.BRANCH_CONFLICT, f"Merge conflict in PR {identifier}")
            merged = _git(
                repo,
                "commit-tree",
                tree,
                "-p",
                base,
                "-p",
                compare,
                "-m",
                f"merge pr {identifier}: {pr.compare} into {pr.base}",
            )

        # Verify the policy/PR and both branch tips atomically, even on a no-op.
        # Git accepts only one instruction per ref if any of these names coincide.
        base_ref = f"refs/heads/{pr.base}"
        expected = {base_ref: base, f"refs/heads/{pr.compare}": compare}
        if expected.get(GC_REF, store.oid) != store.oid:
            _reject(FailureReason.STALE_SNAPSHOT, "Metadata changed during merge")
        expected[GC_REF] = store.oid
        commands = []
        for ref, oid in expected.items():
            commands.extend(
                [
                    "option no-deref",
                    f"update {ref} {merged} {oid}"
                    if ref == base_ref and merged != base
                    else f"verify {ref} {oid}",
                ]
            )
        _git(repo, "update-ref", "--stdin", stdin=("\n".join(commands) + "\n").encode())
        return replace(pr, merged=True)

    return _run(directory, merge)


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
    return read_comments(store.repo, _subtree(store.repo, store.prs, name))


def list_comments(identifier: str, directory: str | Path = ".") -> Result[list[Comment]]:
    """Read exact comment contents and reply IDs."""
    return _run(directory, lambda store: _comments(store, store.get(identifier)[0]))


def _merge_analysis(
    repo: Repo, pr: PullRequest, branches: dict[str, str]
) -> tuple[
    bool | None, tuple[str, ...] | None, tuple[FileChange, ...] | None, str | None, str | None
]:
    """Analyze captured tips using plumbing, never the caller's checkout/index."""
    missing = [name for name in dict.fromkeys((pr.compare, pr.base)) if name not in branches]
    if missing:
        return None, None, None, None, f"Missing branches: {', '.join(missing)}"
    base, compare = branches[pr.base], branches[pr.compare]
    try:
        ancestor = _git(repo, "merge-base", base, compare)
    except GitCommandError as exc:
        if exc.status == 1:
            return None, None, None, None, "Branches have unrelated histories"
        raise
    # Use the feature-side diff rather than tip-to-tip: base-only work is not
    # part of this PR. NUL separation avoids Git's filename quoting convention.
    changes = changed_files(repo, [ancestor, compare])
    # The first NUL-delimited field is the resulting tree OID. Remaining fields
    # are conflicted paths; --no-messages excludes human-readable diagnostics.
    # Exit 1 is expected for conflicts, while other errors remain Git failures.
    merge_status, merge = _git_result(
        repo,
        "merge-tree",
        "--write-tree",
        "--name-only",
        "--no-messages",
        "-z",
        base,
        compare,
    )
    conflicts = tuple(sorted(set(path for path in merge.split("\0")[1:] if path)))
    return merge_status == 1, conflicts, tuple(changes), ancestor, None


def show_pull_request(
    identifier: str, directory: str | Path = ".", *, include_comment_origins: bool = False
) -> Result[PullRequestDetails]:
    """Read a complete conversation from a single captured metadata commit."""

    def show(store: _Store) -> PullRequestDetails:
        name, pr = store.get(identifier)
        comments = _comments(store, name)
        # A first-parent cycle cannot be rendered as a tree. Validate iteratively
        # in linear time, including disconnected cycles and self references.
        parents = {c.id: c.replies_to[0] if c.replies_to else None for c in comments}
        complete: set[str] = set()
        for comment in comments:
            path: set[str] = set()
            current: str | None = comment.id
            while current is not None and current not in complete:
                if current in path:
                    _reject(FailureReason.INVALID_METADATA, "Cycle in comment reply tree")
                path.add(current)
                current = parents[current]
            complete.update(path)
        if include_comment_origins:
            attributed = attributed_comments(
                store.repo,
                store.oid,
                PR_DIRECTORY,
                lambda name: _parse(name).id == identifier,
                comments,
            )
            opening = next(c for c in attributed if c.id == COMMENT_MAIN)
            author, created_at = opening.author, opening.created_at
            comments = list(attributed)
        else:
            author, created_at = _origins(store)[identifier]
        branches = _branches(store.repo)
        pr = replace(
            pr,
            author=author,
            created_at=created_at,
            merged=_merged(store.repo, pr, branches),
        )
        has_conflicts, conflicts, files, ancestor, error = _merge_analysis(store.repo, pr, branches)
        return PullRequestDetails(
            pr,
            tuple(comments),
            has_conflicts,
            files,
            conflicts,
            error,
            store.oid,
            branches.get(pr.base),
            branches.get(pr.compare),
            ancestor,
        )

    return _run(directory, show)


async def add_comment(
    target: str, text: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Comment]:
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
        reply_detail = f" replying to {', '.join(replies)}" if replies else ""
        store.publish(f"add comment {identifier} on pr {pr_id}{reply_detail}")
        return Comment(identifier, text, tuple(replies))

    return _run(directory, add, expected_tip)


def _comment_filename(comment: Comment) -> str:
    return COMMENT_PREFIX + PR_TITLE_SEPARATOR.join([comment.id, *comment.replies_to])


def _edit_comment(
    target: str, text: str | None, directory: str | Path, *, expected_tip: str | None = None
) -> Result[Comment]:
    # None denotes deletion; empty text remains a valid replacement, including
    # for main. Validate the whole conversation before preparing any mutation.
    def edit(store: _Store) -> Comment:
        parts = target.split(PR_TITLE_SEPARATOR)
        if len(parts) != 2:
            _reject(FailureReason.INVALID_ARGUMENT, "Expected PR_ID:COMMENT_ID")
        pr_id, identifier = parts
        _identifier(identifier)
        name, _ = store.get(pr_id)
        comments = _comments(store, name)
        selected = next((comment for comment in comments if comment.id == identifier), None)
        if selected is None:
            _reject(FailureReason.NOT_FOUND, f"Unknown comment: {identifier}")
        if text is None and identifier == COMMENT_MAIN:
            _reject(
                FailureReason.INVALID_ARGUMENT, "Main cannot be deleted; update its text to empty"
            )
        if text == selected.text:
            return selected
        entries = _subtree(store.repo, store.prs, name)
        filename = _comment_filename(selected)
        if text is None:
            del entries[filename]
            # Preserve surviving reply bodies byte-for-byte. Only their filename
            # edges change so the existing no-dangling-replies invariant holds.
            for comment in comments:
                if comment.id != identifier and identifier in comment.replies_to:
                    changed = replace(
                        comment, replies_to=tuple(r for r in comment.replies_to if r != identifier)
                    )
                    entries[_comment_filename(changed)] = entries.pop(_comment_filename(comment))
            result = selected
        else:
            entries[filename] = _blob(store.repo, text)
            result = replace(selected, text=text)
        store.prs[name] = _write_tree(store.repo, entries)
        action = (
            f"delete comment {identifier}" if text is None else f"update comment {identifier} text"
        )
        store.publish(f"{action} on pr {pr_id}")
        return result

    return _run(directory, edit, expected_tip)


def update_comment(
    target: str, text: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Comment]:
    """Replace PR_ID:COMMENT_ID text, preserving identity and reply links."""
    return _edit_comment(target, text, directory, expected_tip=expected_tip)


def delete_comment(
    target: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Comment]:
    """Remove a non-main comment and incoming reply links; return the removed record."""
    return _edit_comment(target, None, directory, expected_tip=expected_tip)


def read_pr_diff(
    identifier: str, base_tip: str, compare_tip: str, path: str, directory: str | Path = "."
) -> Result[str]:
    """Pin the selected path to the same comparison displayed in Files changed."""
    detail = show_pull_request(identifier, directory)
    if isinstance(detail, Failure):
        return detail
    pr = detail.value
    if (base_tip, compare_tip) != (pr.base_tip, pr.compare_tip):
        return Failure(FailureReason.STALE_SNAPSHOT, "Comparison changed")
    change = next((f for f in pr.changed_files or () if f.path == path), None)
    if change is None or pr.merge_base is None:
        return Failure(FailureReason.NOT_FOUND, "Unknown changed file")
    try:
        with Repo(directory, search_parent_directories=True, expand_vars=False) as repo:
            paths = ([change.old_path] if change.old_path else []) + [path]
            return Success(patch(repo, [pr.merge_base, compare_tip], paths))
    except Exception as exc:
        return _failure(exc)
