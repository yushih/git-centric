"""CLI repository selection against isolated real Git repositories."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from test_initialization import git, isolated_git_config, repo  # noqa: F401
from typer.testing import CliRunner

from pygc import Failure, FailureReason, Success, initialize_gc, is_gc_initialized
from pygc.cli import app
from pygc.library.constants import GC_REF


@pytest.fixture
def pair(repo: Path, tmp_path: Path) -> tuple[Path, Path]:  # noqa: F811
    # Two independent initialized repos expose accidental use of cwd or shared refs.
    other = tmp_path / "other repo"
    other.mkdir()
    git(other, "init", "--initial-branch=main")
    for directory in (repo, other):
        git(directory, "commit", "--allow-empty", "-m", "Base")
        assert isinstance(initialize_gc(directory), Success)
    return repo, other


def test_all_repo_commands_use_override(pair, monkeypatch) -> None:
    # Every command must act in the selected repo, warn once on stderr, keep
    # stdout parseable, and preserve the current repository's ref and cwd.
    current, selected = pair
    monkeypatch.chdir(current)
    before = git(current, "rev-parse", GC_REF)
    runner = CliRunner()

    def invoke(args):
        result = runner.invoke(app, [*args, f"--repo-dir={selected}"])
        assert result.exit_code == 0, result.output
        assert result.stderr.count("Warning:") == 1
        assert str(current) in result.stderr and str(selected) in result.stderr
        assert Path.cwd() == current
        assert git(current, "rev-parse", GC_REF) == before
        return json.loads(result.stdout)

    item = invoke(["pr", "new", "main", "main", "Selected PR"])
    assert invoke(["pr", "list"])[0]["id"] == item["id"]
    assert invoke(["pr", "update", item["id"], "title=Changed"])["title"] == "Changed"
    comment = invoke(["comment", item["id"], "Body"])
    target = item["id"] + ":" + comment["id"]
    assert invoke(["update-comment", target, "Updated"])["text"] == "Updated"
    assert len(invoke(["pr", "comments", item["id"]])) == 2
    assert invoke(["delete-comment", target])["id"] == comment["id"]
    assert len(invoke(["pr", "comments", item["id"]])) == 1
    # No option still means cwd, without a warning or accidental sticky selection.
    result = runner.invoke(app, ["pr", "list"])
    assert result.exit_code == 0 and json.loads(result.stdout) == [] and not result.stderr


@pytest.mark.parametrize("alias", ["same", "subdir", "symlink", "worktree"])
def test_same_repository_has_no_warning(pair, monkeypatch, tmp_path, alias) -> None:
    # Shared metadata is the identity, not the spelling or worktree location.
    current, _ = pair
    monkeypatch.chdir(current)
    selected = current
    if alias == "subdir":
        selected = current / "sub"
        selected.mkdir()
    elif alias == "symlink":
        selected = tmp_path / "alias"
        selected.symlink_to(current, target_is_directory=True)
    elif alias == "worktree":
        selected = tmp_path / "linked"
        git(current, "worktree", "add", "-b", "linked", str(selected), "main")
    result = CliRunner().invoke(app, ["pr", "list", "--repo-dir", str(selected)])
    assert result.exit_code == 0, result.output
    assert not result.stderr


def test_uninitialized_and_invalid_locations(pair, tmp_path, monkeypatch) -> None:
    # An uninitialized/nonrepo cwd does not obstruct a valid selection. A bad
    # explicit path fails in place, without falling back to an initialized cwd.
    current, selected = pair
    plain = tmp_path / "plain"
    plain.mkdir()
    runner = CliRunner()
    for initialize_git in (False, True):
        if initialize_git:
            git(plain, "init", "--initial-branch=main")
        monkeypatch.chdir(plain)
        result = runner.invoke(app, ["pr", "list", "--repo-dir", str(selected)])
        assert result.exit_code == 0 and not result.stderr
    monkeypatch.chdir(current)
    before = git(current, "rev-parse", GC_REF)
    for target, reason in ((plain, "not_initialized"), (tmp_path / "missing", "not_a_repository")):
        result = runner.invoke(app, ["pr", "list", "--repo-dir", str(target)])
        assert result.exit_code == 1 and reason in result.stderr
        assert "Warning:" not in result.stderr
    assert git(current, "rev-parse", GC_REF) == before
    # Inspection is advisory: a failure inspecting cwd must not block the target.
    with patch(
        "pygc.cli.library.is_gc_initialized", return_value=Failure(FailureReason.IO_ERROR, "x")
    ):
        result = runner.invoke(app, ["pr", "list", "--repo-dir", str(selected)])
    assert result.exit_code == 0 and not result.stderr


def test_init_option_overrides_legacy_directory(repo, tmp_path, monkeypatch) -> None:  # noqa: F811
    # The option wins over both cwd and the legacy positional argument; only
    # the chosen repository becomes initialized. Relative paths are cwd-relative.
    selected = tmp_path / "selected"
    selected.mkdir()
    git(selected, "init", "--initial-branch=main")
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ["init", str(repo), "--repo-dir=../selected"])
    assert result.exit_code == 0, result.output
    assert not result.stderr
    assert is_gc_initialized(repo) == Success(False)
    assert is_gc_initialized(selected) == Success(True)
    assert isinstance(initialize_gc(repo), Success)
    result = CliRunner().invoke(app, ["init", "--repo-dir", str(selected)])
    assert result.exit_code == 1 and "already_initialized" in result.stderr
    assert result.stderr.count("Warning:") == 1


def test_non_repo_commands_and_help(pair, monkeypatch) -> None:
    # Repository-independent commands accept the common option and retain their
    # existing behavior. All leaf help pages advertise the option.
    current, selected = pair
    monkeypatch.chdir(current)
    runner = CliRunner()
    with patch("pygc.cli.uvicorn.run") as run:
        for args in (["help"], ["web"]):
            result = runner.invoke(app, [*args, "--repo-dir", str(selected)])
            assert result.exit_code == 0, result.output
            assert result.stderr.count("Warning:") == 1
        run.assert_called_once_with(
            "pygc.web:create_app", factory=True, host="127.0.0.1", port=8000, reload=False
        )
    for args in (
        ["help"],
        ["web"],
        ["init"],
        ["pr", "new"],
        ["pr", "list"],
        ["pr", "update"],
        ["pr", "comments"],
        ["comment"],
        ["update-comment"],
        ["delete-comment"],
    ):
        result = runner.invoke(app, [*args, "--help"])
        assert result.exit_code == 0 and "--repo-dir" in result.stdout
