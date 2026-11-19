"""Browse committed objects through local branch names, never worktree paths."""

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from git import Repo

from .constants import GC_BRANCH
from .initialization import _failure
from .patches import changed_files, patch
from .result import Failure, FailureReason, Result, Success


def browse_source(
    directory: Path,
    branch: str | None = None,
    path: str = "",
    revision: str | None = None,
    history: bool = False,
    offset: int = 0,
    detail: bool = False,
) -> Result[dict[str, Any]]:
    """Read directory, file or history from a single captured source revision."""
    if (
        offset < 0
        or offset > 2**31 - 1
        or (path and any(part in {"", ".", ".."} for part in path.split("/")))
    ):
        return Failure(FailureReason.INVALID_ARGUMENT, "Invalid source location")
    try:
        with Repo(directory, search_parent_directories=True, expand_vars=False) as repo:
            branches = {ref.name: ref.commit for ref in repo.heads if ref.name != GC_BRANCH}
            detached = repo.head.is_detached and repo.head.is_valid()
            if branch is None and not detached:
                current = repo.active_branch.name
                branch = current if current in branches else next(iter(branches), None)
            if branch is not None and branch not in branches:
                return Failure(FailureReason.BRANCH_NOT_FOUND, "Unknown source branch")
            tip = branches[branch] if branch else repo.head.commit if detached else None
            # Detached HEAD may itself point into the reserved branch history.
            if detached and branch is None and GC_BRANCH in repo.heads:
                if repo.is_ancestor(repo.head.commit, repo.heads[GC_BRANCH].commit):
                    branch = next(iter(branches), None)
                    tip = branches.get(branch) if branch else None
                    detached = False
            data: dict[str, Any] = dict(
                name=Path(repo.working_tree_dir or repo.git_dir).name,
                branches=sorted(branches),
                branch=branch,
                detached=detached,
                commit=None,
                entries=[],
                text=None,
                notice=None,
                commits=[],
                more=False,
            )
            if revision:
                if not tip or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
                    return Failure(FailureReason.INVALID_ARGUMENT, "Invalid revision")
                if not repo.is_ancestor(repo.commit(revision), tip):
                    return Failure(FailureReason.NOT_FOUND, "Revision outside branch")
                tip = repo.commit(revision)
            if tip is None:
                return Success(data)

            def summary(commit: Any) -> dict[str, str]:
                return dict(
                    id=commit.hexsha,
                    title=commit.summary,
                    author=commit.author.name,
                    date=commit.authored_datetime.isoformat(),
                )

            data["commit"] = summary(tip)
            if detail:
                parents = [c.hexsha for c in tip.parents]
                revisions = parents[:1] + [tip.hexsha]
                changes = changed_files(repo, revisions)
                paths = []
                if path:
                    change = next((f for f in changes if f.path == path), None)
                    if change is None:
                        return Failure(FailureReason.NOT_FOUND, "Unknown changed path")
                    paths = ([change.old_path] if change.old_path else []) + [path]
                data.update(
                    changes=[asdict(change) for change in changes],
                    body=tip.message,
                    parents=parents,
                    patch=patch(repo, revisions, paths),
                )
                return Success(data)
            if history:
                page = list(repo.iter_commits(tip.hexsha, max_count=51, skip=offset))
                data.update(commits=[summary(c) for c in page[:50]], more=len(page) > 50)
                return Success(data)
            # Resolve components as literal Git tree entries (including symlinks).
            obj = tip.tree
            if path:
                for part in path.split("/"):
                    if obj.type != "tree":
                        return Failure(FailureReason.NOT_FOUND, "Unknown path")
                    obj = obj[part]
            if obj.type == "tree":
                rows = [
                    dict(
                        name=e.name,
                        kind={"160000": "submodule", "120000": "symlink"}.get(
                            format(e.mode, "o"), e.type
                        ),
                    )
                    for e in obj
                ]
                data["entries"] = sorted(rows, key=lambda e: (e["kind"] != "tree", e["name"]))
            elif obj.type != "blob":
                data["notice"] = "Submodule at " + obj.hexsha
            elif obj.size > 1024 * 1024:
                data["notice"] = "This file exceeds the 1 MiB preview limit."
            else:
                raw = obj.data_stream.read()
                try:
                    if b"\0" in raw:
                        data["notice"] = "Binary file"
                    else:
                        data["text"] = raw.decode("utf-8")
                except UnicodeDecodeError:
                    data["notice"] = "Binary file"
            return Success(data)
    except KeyError:
        return Failure(FailureReason.NOT_FOUND, "Unknown path")
    except Exception as exc:
        return _failure(exc)
