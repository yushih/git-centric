"""Inspect and initialize Git-centric without checking out its metadata branch.

GitPython supplies repository discovery and the Git process interface. Git's
plumbing commands build immutable objects directly in the object database;
neither a temporary checkout nor changes to the user's index are necessary.
"""

from pathlib import Path
from tempfile import TemporaryFile

from git import Git, Repo
from git.exc import GitError, InvalidGitRepositoryError, NoSuchPathError

from .constants import (
    GC_DIRECTORY,
    GC_INITIAL_COMMIT_MESSAGE,
    GC_KEEP_FILE,
    GC_REF,
    GIT_DIRECTORY_MODE,
    GIT_REGULAR_FILE_MODE,
)
from .result import Failure, FailureReason, Result, Success


def _git(repo: Repo, *args: str, stdin: bytes | None = None) -> str:
    """Run plumbing through GitPython, optionally feeding bytes on stdin.

    Use an argument list, never a shell command string. Explicitly identifying
    the repository also prevents an inherited GIT_DIR from redirecting a write.
    Replacement objects must not change which committed tree we inspect.
    A real temporary file provides the file descriptor GitPython's subprocess
    interface expects; BytesIO would not provide one. It is outside the repo.
    """
    command = [Git.GIT_PYTHON_GIT_EXECUTABLE, "--no-replace-objects", "--git-dir", repo.git_dir]
    command.extend(args)
    if stdin is None:
        return str(repo.git.execute(command))
    with TemporaryFile() as stream:
        stream.write(stdin)
        stream.seek(0)
        return str(repo.git.execute(command, istream=stream))


def _branch_oid(repo: Repo) -> str | None:
    """Find only the local metadata branch, not a tag or remote-tracking ref."""
    # for-each-ref succeeds with empty output for an absent branch. Other Git
    # failures remain exceptions here and become Failure at the public boundary.
    # Its filter can include descendants, so compare the complete ref name too.
    refs = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)", GC_REF)
    for line in refs.splitlines():
        ref, oid = line.split(" ", 1)
        if ref == GC_REF:
            return oid
    return None


def _has_gc_directory(repo: Repo, oid: str) -> bool:
    """Inspect the branch's committed root tree, not files in the checkout."""
    # ^{commit} also verifies that the branch points to a commit. Missing or
    # corrupt objects are errors, rather than an incorrect 'not initialized'.
    entries = _git(repo, "ls-tree", "-z", f"{oid}^{{commit}}", "--", GC_DIRECTORY)
    for entry in entries.split("\0"):
        if not entry:
            continue
        metadata, name = entry.split("\t", 1)
        mode, kind, _object_id = metadata.split(" ")
        if name == GC_DIRECTORY:
            # A file, symlink, or submodule with the reserved name is not a
            # directory. There is no requirement to find .gitkeep when checking.
            return mode == GIT_DIRECTORY_MODE and kind == "tree"
    return False


def _failure(exc: Exception) -> Failure:
    """Translate operational exceptions into the public failure vocabulary."""
    if isinstance(exc, (InvalidGitRepositoryError, NoSuchPathError, NotADirectoryError)):
        return Failure(FailureReason.NOT_A_REPOSITORY, str(exc))
    if isinstance(exc, GitError):
        return Failure(FailureReason.GIT_ERROR, str(exc))
    if isinstance(exc, OSError):
        return Failure(FailureReason.IO_ERROR, str(exc))
    return Failure(FailureReason.UNEXPECTED_ERROR, str(exc))


def is_gc_initialized(directory: str | Path = ".") -> Result[bool]:
    """Return Success(True/False), or Failure if the repository cannot be read.

    By default inspect the current directory. A subdirectory of a worktree is
    accepted, as with Git's own commands; linked worktrees and bare repos also
    work. Missing paths, regular files, and directories outside a repository
    return NOT_A_REPOSITORY. No repository files or references are modified.
    """
    try:
        path = Path(directory).absolute()
        if not path.is_dir():
            return Failure(FailureReason.NOT_A_REPOSITORY, f"Not a directory: {path}")
        with Repo(path, search_parent_directories=True, expand_vars=False) as repo:
            oid = _branch_oid(repo)
            return Success(oid is not None and _has_gc_directory(repo, oid))
    except Exception as exc:
        # This is intentionally an exception-to-value boundary. Interrupts and
        # process termination (BaseException) are not swallowed.
        return _failure(exc)


def initialize_gc(directory: str | Path = ".") -> Result[str]:
    """Create the metadata branch; return Success(new_commit_oid) or Failure.

    Precondition: is_gc_initialized(directory) returned Success(False). This
    function checks again rather than trusting a possibly stale caller result.
    An existing but malformed metadata branch is a BRANCH_CONFLICT: it must not
    be silently reset. Git's normal author/committer configuration is used, and
    missing identity or object-write failures are returned as GIT_ERROR.

    The commit has no parents and contains exactly __git-centric__/.gitkeep,
    with empty file contents. HEAD, the index, and worktree files are untouched.
    """
    try:
        path = Path(directory).absolute()
        if not path.is_dir():
            return Failure(FailureReason.NOT_A_REPOSITORY, f"Not a directory: {path}")
        with Repo(path, search_parent_directories=True, expand_vars=False) as repo:
            oid = _branch_oid(repo)
            if oid is not None:
                if _has_gc_directory(repo, oid):
                    return Failure(FailureReason.ALREADY_INITIALIZED, "Git-centric is initialized")
                return Failure(FailureReason.BRANCH_CONFLICT, f"Ref already exists: {GC_REF}")

            # Objects are constructed bottom-up. hash-object writes the empty
            # blob; the first tree contains .gitkeep; the second is the root
            # tree whose only entry is the reserved directory.
            blob = _git(repo, "hash-object", "-w", "--stdin", stdin=b"")
            directory_tree = _git(
                repo,
                "mktree",
                stdin=f"{GIT_REGULAR_FILE_MODE} blob {blob}\t{GC_KEEP_FILE}\n".encode(),
            )
            root_tree = _git(
                repo,
                "mktree",
                stdin=f"{GIT_DIRECTORY_MODE} tree {directory_tree}\t{GC_DIRECTORY}\n".encode(),
            )

            # Omitting every -p argument is what makes this an orphan commit.
            # We never run checkout, add, commit, or write-tree, so even staged
            # user changes cannot accidentally enter the new commit.
            commit = _git(repo, "commit-tree", root_tree, "-m", GC_INITIAL_COMMIT_MESSAGE)

            # 'create' asserts absence inside Git's ref transaction, closing the
            # race between the earlier check and this write. No hard-coded hash
            # length is needed (both SHA-1 and SHA-256 repositories work).
            # no-deref prevents a concurrent symbolic ref from redirecting us.
            # If publication fails, only unreferenced objects may remain; Git's
            # normal garbage collection can reclaim them without touching data.
            _git(
                repo,
                "update-ref",
                "--stdin",
                stdin=f"option no-deref\ncreate {GC_REF} {commit}\n".encode(),
            )
            return Success(commit)
    except Exception as exc:
        return _failure(exc)
