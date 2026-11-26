"""Exercise real repositories; inspect results independently with the Git CLI."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pygc import Failure, FailureReason, Success, initialize_gc, is_gc_initialized
from pygc.cli import app
from pygc.library import initialization
from pygc.library.constants import GC_BRANCH, GC_DIRECTORY, GC_KEEP_FILE, GC_REF


def git(directory: Path, *args: str) -> str:
    # Run Git independently of the library so assertions verify actual repository state.
    return subprocess.check_output(["git", "-C", str(directory), *args], text=True).strip()


@pytest.fixture(autouse=True)
def isolated_git_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Never read or write the developer's identity, signing, or init defaults.
    # Explicit identity also lets these tests run on a fresh CI machine.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-config"))
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "GC tests")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "gc-tests@example.invalid")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    # Start with an unborn main branch: there is no user commit or index yet.
    directory = tmp_path / "repo"
    directory.mkdir()
    git(directory, "init", "--initial-branch=main")
    return directory


def assert_initial_commit(repo: Path, oid: str) -> None:
    # Verify the published ref, parentless history, exact tree, empty marker, and public check.
    assert git(repo, "rev-parse", GC_REF) == oid
    # rev-list emits only the commit itself if and only if there are no parents.
    assert git(repo, "rev-list", "--parents", "-n", "1", GC_REF) == oid
    assert git(repo, "ls-tree", "--name-only", GC_REF) == GC_DIRECTORY
    library = Path(initialization.__file__).parent
    sources = [library / "actions.py", *sorted(library.glob("rule-*.py"))]
    rules_path = f"{GC_DIRECTORY}/access/rules"
    assert git(repo, "ls-tree", "-r", "--name-only", GC_REF) == (
        f"{GC_DIRECTORY}/{GC_KEEP_FILE}\n"
        + "".join(
            f"{GC_DIRECTORY}/access-control/roles/{role}\n"
            for role in ("admin", "ci", "merger", "owner")
        )
        + f"{GC_DIRECTORY}/access-control/users/GC tests/pk-Ed25519\n"
        + f"{GC_DIRECTORY}/access-control/users/GC tests/roles/owner\n"
        + "\n".join(f"{rules_path}/{source.name}" for source in sources)
    )
    for source in sources:
        # Compare raw blob bytes, including source encoding and final newlines.
        assert (
            subprocess.check_output(
                ["git", "-C", str(repo), "cat-file", "blob", f"{oid}:{rules_path}/{source.name}"]
            )
            == source.read_bytes()
        )
    assert git(repo, "show", f"{GC_REF}:{GC_DIRECTORY}/{GC_KEEP_FILE}") == ""
    assert is_gc_initialized(repo) == Success(True)


def test_empty_repo_and_default_directory(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Both APIs must default to pwd and initialize a repository with no existing commits.
    monkeypatch.chdir(repo)
    assert is_gc_initialized() == Success(False)
    before_head = (repo / ".git/HEAD").read_bytes()
    result = initialize_gc()
    assert isinstance(result, Success)
    assert_initial_commit(repo, result.value)
    # Creating metadata must neither switch branches nor materialize checkout files.
    assert (repo / ".git/HEAD").read_bytes() == before_head
    assert not (repo / ".git/index").exists()
    assert sorted(p.name for p in repo.iterdir()) == [".git"]


def test_dirty_index_and_worktree_are_untouched(repo: Path) -> None:
    # Initialization must preserve the current commit, staged data, unstaged edits, and untracked
    # files.
    tracked = repo / "tracked"
    tracked.write_text("original")
    git(repo, "add", "tracked")
    git(repo, "commit", "-m", "First user commit")
    # Give HEAD, the index, and the working file three different contents.
    # This catches accidental staging, resetting, or inclusion of user data.
    tracked.write_text("staged")
    git(repo, "add", "tracked")
    tracked.write_text("unstaged")
    (repo / "untracked").write_text("keep me")
    before_head = git(repo, "rev-parse", "HEAD")
    before_index = (repo / ".git/index").read_bytes()
    result = initialize_gc(repo)
    assert isinstance(result, Success)
    assert_initial_commit(repo, result.value)
    assert git(repo, "rev-parse", "HEAD") == before_head
    assert (repo / ".git/index").read_bytes() == before_index
    assert tracked.read_text() == "unstaged"
    assert (repo / "untracked").read_text() == "keep me"


def test_repeat_initialization_is_a_failure_without_reset(repo: Path) -> None:
    # A second initialization must report ALREADY_INITIALIZED and preserve the original metadata
    # ref.
    first = initialize_gc(repo)
    assert isinstance(first, Success)
    result = initialize_gc(repo)
    assert isinstance(result, Failure)
    assert result.reason == FailureReason.ALREADY_INITIALIZED
    assert git(repo, "rev-parse", GC_REF) == first.value


@pytest.mark.parametrize("marker_kind", ["absent", "file", "directory"])
def test_check_looks_at_committed_directory_and_conflicts(repo: Path, marker_kind: str) -> None:
    # Only a committed directory qualifies; an absent marker or regular file is a branch conflict.
    marker = repo / GC_DIRECTORY
    if marker_kind == "file":
        marker.write_text("not a directory")
    elif marker_kind == "directory":
        marker.mkdir()
        (marker / "metadata").write_text("does not need a .gitkeep")
    git(repo, "add", ".")
    git(repo, "commit", "--allow-empty", "-m", "Existing data")
    git(repo, "branch", GC_BRANCH)
    original = git(repo, "rev-parse", GC_REF)
    assert is_gc_initialized(repo) == Success(marker_kind == "directory")
    result = initialize_gc(repo)
    assert isinstance(result, Failure)
    expected = (
        FailureReason.ALREADY_INITIALIZED
        if marker_kind == "directory"
        else FailureReason.BRANCH_CONFLICT
    )
    assert result.reason == expected
    assert git(repo, "rev-parse", GC_REF) == original


def test_uncommitted_marker_does_not_count(repo: Path) -> None:
    # A matching directory in the checkout alone must not make the repository initialized.
    (repo / GC_DIRECTORY).mkdir()
    (repo / GC_DIRECTORY / GC_KEEP_FILE).touch()
    assert is_gc_initialized(repo) == Success(False)


@pytest.mark.parametrize("kind", ["directory", "missing", "file"])
def test_non_repositories_return_failure(tmp_path: Path, kind: str) -> None:
    # Both APIs must return NOT_A_REPOSITORY for a plain directory, missing path, or regular file.
    target = tmp_path / "outside"
    if kind == "directory":
        target.mkdir()
    elif kind == "file":
        target.touch()
    for operation in (is_gc_initialized, initialize_gc):
        result = operation(target)
        assert isinstance(result, Failure)
        assert result.reason == FailureReason.NOT_A_REPOSITORY


def test_subdirectory_and_bare_repo(repo: Path, tmp_path: Path) -> None:
    # Discovery must work inside a worktree, and object creation must also work without a
    # checkout.
    child = repo / "child"
    child.mkdir()
    assert is_gc_initialized(child) == Success(False)
    assert isinstance(initialize_gc(child), Success)
    assert is_gc_initialized(repo) == Success(True)
    # A bare repository has an object database and refs, but no worktree or index.
    bare = tmp_path / "bare.git"
    git(tmp_path, "init", "--bare", str(bare))
    result = initialize_gc(bare)
    assert isinstance(result, Success)
    assert_initial_commit(bare, result.value)


def test_concurrent_branch_creation_is_not_overwritten(repo: Path) -> None:
    # If another writer creates the reserved branch first, our atomic create must fail without
    # resetting it.
    # Inject a competing publication immediately before our update-ref. This
    # deterministically exercises the race without relying on thread timing.
    git(repo, "commit", "--allow-empty", "-m", "Competing commit")
    competing_oid = git(repo, "rev-parse", "HEAD")
    original_git = initialization._git

    def race(repository, *args: str, stdin: bytes | None = None) -> str:
        if args[0] == "update-ref":
            git(repo, "update-ref", GC_REF, competing_oid)
        return original_git(repository, *args, stdin=stdin)

    with patch.object(initialization, "_git", side_effect=race):
        result = initialize_gc(repo)
    assert isinstance(result, Failure)
    assert result.reason == FailureReason.GIT_ERROR
    assert git(repo, "rev-parse", GC_REF) == competing_oid


def test_io_exceptions_are_returned(repo: Path) -> None:
    # A permission error during inspection must become a Failure value for either public API.
    for operation in (is_gc_initialized, initialize_gc):
        with patch.object(initialization, "_branch_oid", side_effect=PermissionError("denied")):
            result = operation(repo)
        assert result == Failure(FailureReason.IO_ERROR, "denied")


def test_missing_identity_does_not_publish_branch(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Without an author/committer identity, initialization must fail before publishing the branch.
    for role in ("AUTHOR", "COMMITTER"):
        for field in ("NAME", "EMAIL"):
            monkeypatch.delenv(f"GIT_{role}_{field}", raising=False)
    monkeypatch.delenv("EMAIL", raising=False)
    # Prevent Git from guessing an identity from the OS after removing env overrides.
    git(repo, "config", "user.useConfigOnly", "true")
    result = initialize_gc(repo)
    assert isinstance(result, Failure)
    assert result.reason == FailureReason.GIT_ERROR
    assert is_gc_initialized(repo) == Success(False)


def test_linked_worktree(repo: Path, tmp_path: Path) -> None:
    # Initialization from a linked worktree must update the shared repo without moving that
    # worktree HEAD.
    git(repo, "commit", "--allow-empty", "-m", "User commit")
    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-b", "other", str(linked))
    original_head = git(linked, "rev-parse", "HEAD")
    result = initialize_gc(linked)
    assert isinstance(result, Success)
    assert_initial_commit(repo, result.value)
    assert is_gc_initialized(linked) == Success(True)
    assert git(linked, "rev-parse", "HEAD") == original_head


def test_cli_init_path_default_failure_and_help(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exercise explicit and default paths, failure exit status/stderr, and discoverability through
    # help.
    runner = CliRunner()
    result = runner.invoke(app, ["init", str(repo)])
    assert result.exit_code == 0
    assert "Initialized Git-centric" in result.stdout
    # With no path argument, the already-initialized pwd must produce a CLI error.
    monkeypatch.chdir(repo)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert "already_initialized" in result.stderr
    assert "init" in runner.invoke(app, ["help"]).stdout
    assert "directory" in runner.invoke(app, ["init", "--help"]).stdout.lower()
