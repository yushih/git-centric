"""Preview immutable Git comparisons with bounded output and literal pathspecs."""

from dataclasses import dataclass

from git import Git, Repo

from .initialization import _git

PATCH_LIMIT = 1024 * 1024


def patch(repo: Repo, revisions: list[str], paths: list[str]) -> str:
    process = repo.git.execute(
        [
            str(Git.GIT_PYTHON_GIT_EXECUTABLE),
            "--no-replace-objects",
            "--git-dir",
            str(repo.git_dir),
            "--literal-pathspecs",
            "diff-tree",
            "--root",
            "-r",
            "-p",
            "--no-commit-id",
            "--no-ext-diff",
            "--no-textconv",
            "--find-renames",
            "--find-copies-harder",
            *revisions,
            "--",
            *paths,
        ],
        as_process=True,
    )
    try:
        raw: bytes = process.stdout.read(PATCH_LIMIT + 1)
        if len(raw) > PATCH_LIMIT:
            process.kill()
            assert process.proc is not None
            process.proc.wait()
            return "Patch exceeds the 1 MiB preview limit."
        process.wait()
        return raw.decode("utf-8", errors="replace")
    finally:
        process.stdout.close()


@dataclass(frozen=True)
class FileChange:
    status: str
    path: str
    old_path: str | None = None
    similarity: int | None = None


def changed_files(repo: Repo, revisions: list[str]) -> list[FileChange]:
    """Read NUL-delimited paths, including both sides of copies and renames."""
    output = _git(
        repo,
        "diff-tree",
        "--root",
        "-r",
        "--no-commit-id",
        "--no-ext-diff",
        "--no-textconv",
        "--name-status",
        "--find-renames",
        "--find-copies-harder",
        "-z",
        *revisions,
        "--",
    )
    fields = iter(output.split("\0")[:-1])
    changes = []
    kinds = {
        "A": "added",
        "M": "modified",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "T": "type_changed",
        "U": "unmerged",
        "X": "unknown",
        "B": "broken",
    }
    for status in fields:
        path = next(fields)
        if status[0] in {"R", "C"}:
            changes.append(FileChange(kinds[status[0]], next(fields), path, int(status[1:])))
        else:
            changes.append(FileChange(kinds.get(status[0], "unknown"), path))
    return changes
