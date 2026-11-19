"""Read the local repository context without changing refs or the checkout."""

from dataclasses import dataclass
from pathlib import Path

from git import Repo

from .initialization import _branch_oid, _failure, _has_gc_directory
from .result import Result, Success


@dataclass(frozen=True)
class RepositoryContext:
    name: str
    bare: bool
    branch: str | None
    head: str | None
    initialized: bool
    metadata_tip: str | None


def get_repository(directory: str | Path = ".") -> Result[RepositoryContext]:
    """An unborn HEAD still identifies its branch, while a detached HEAD has only an OID."""
    try:
        with Repo(
            Path(directory).absolute(), search_parent_directories=True, expand_vars=False
        ) as repo:
            tip = _branch_oid(repo)
            initialized = tip is not None and _has_gc_directory(repo, tip)
            return Success(
                RepositoryContext(
                    Path(repo.working_tree_dir or repo.git_dir).name,
                    repo.bare,
                    None if repo.head.is_detached else repo.active_branch.name,
                    repo.head.commit.hexsha if repo.head.is_valid() else None,
                    initialized,
                    tip if initialized else None,
                )
            )
    except Exception as exc:
        return _failure(exc)
