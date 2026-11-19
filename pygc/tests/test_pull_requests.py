"""Real Git acceptance tests, with independent plumbing assertions."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from test_initialization import git, isolated_git_config, repo  # noqa: F401
from typer.testing import CliRunner

from pygc import (
    Failure,
    FailureReason,
    Success,
    add_comment,
    create_pull_request,
    initialize_gc,
    list_comments,
    list_pull_requests,
    update_pull_request,
)
from pygc.cli import app
from pygc.library import pull_requests as pr
from pygc.library.constants import GC_REF


@pytest.fixture
def ready(repo: Path) -> Path:  # noqa: F811
    # Compare is ahead of base, so a fresh PR starts open rather than merged.
    git(repo, "commit", "--allow-empty", "-m", "Base")
    git(repo, "branch", "feature/login")
    git(repo, "checkout", "feature/login")
    git(repo, "commit", "--allow-empty", "-m", "Feature")
    assert isinstance(initialize_gc(repo), Success)
    return repo


def create(ready: Path):
    result = asyncio.run(
        create_pull_request("feature/login", "main", "Title / # : ~>", "initial\n\n", ready)
    )
    assert isinstance(result, Success)
    return result.value


def test_lifecycle_history_and_preservation(ready: Path, monkeypatch) -> None:
    # Every write preserves dirty work, while history survives directory renames.
    (ready / "tracked").write_text("staged")
    git(ready, "add", "tracked")
    (ready / "tracked").write_text("unstaged")
    (ready / "untracked").write_text("keep")
    index = (ready / ".git/index").read_bytes()
    head = git(ready, "rev-parse", "HEAD")
    before = git(ready, "rev-parse", GC_REF)
    item = create(ready)
    created = git(ready, "rev-parse", GC_REF)
    assert git(ready, "rev-list", "--parents", "-n", "1", GC_REF) == f"{created} {before}"
    assert "feature%2Flogin~>main#" in git(ready, "ls-tree", "-r", "--name-only", GC_REF)
    listed = list_pull_requests(directory=ready).value[0]
    assert listed.author == "GC tests <gc-tests@example.invalid>"
    assert listed.created_at
    assert listed.status == "open"
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Other")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "other@example.invalid")
    assert isinstance(update_pull_request(item.id, ["title=Renamed", "draft"], ready), Success)
    assert list_pull_requests(directory=ready).value[0].author == listed.author
    assert list_pull_requests(["open"], ready) == Success([])
    assert isinstance(update_pull_request(item.id, ["ready"], ready), Success)
    added = asyncio.run(add_comment(item.id + ":main", "reply\n", ready))
    assert isinstance(added, Success)
    comments = list_comments(item.id, ready).value
    assert comments[0].text == "initial\n\n"
    assert comments[1].text == "reply\n" and comments[1].replies_to == ("main",)
    assert git(ready, "rev-parse", "HEAD") == head
    assert (ready / ".git/index").read_bytes() == index
    assert (ready / "tracked").read_text() == "unstaged"
    assert (ready / "untracked").read_text() == "keep"


def test_filters_and_merged(ready: Path) -> None:
    # Filters combine with AND; advancing base makes open exclude a merged PR.
    item = create(ready)
    for filters in (
        ["mine"],
        ["author=GC tests"],
        ["author=gc-tests@example.invalid"],
        ["compare=feature/login", "base=main", "title=Title.*"],
    ):
        assert list_pull_requests(filters, ready).value[0].id == item.id
    assert list_pull_requests(["title=absent"], ready) == Success([])
    git(ready, "update-ref", "refs/heads/main", git(ready, "rev-parse", "HEAD"))
    assert list_pull_requests(["open"], ready) == Success([])
    assert list_pull_requests(directory=ready).value[0].status == "merged"
    assert isinstance(update_pull_request(item.id, ["close"], ready), Success)
    assert update_pull_request(item.id, ["ready"], ready).value.status == "closed"


def test_validation_and_collisions(ready: Path) -> None:
    # Invalid requests must fail without moving the metadata reference.
    item = create(ready)
    before = git(ready, "rev-parse", GC_REF)
    results = [
        asyncio.run(create_pull_request("missing", "main", "title", directory=ready)),
        asyncio.run(create_pull_request("main", "main", " ", directory=ready)),
        update_pull_request(item.id, ["compare=missing"], ready),
        update_pull_request(item.id, ["close", "draft"], ready),
        update_pull_request(item.id, ["title=x", "title=y"], ready),
        update_pull_request(item.id, [], ready),
        list_pull_requests(["compare=missing"], ready),
        list_pull_requests(["title=["], ready),
        list_pull_requests(["unknown"], ready),
        asyncio.run(add_comment(item.id + ":missing", "reply", ready)),
        list_comments("missing", ready),
    ]
    assert all(isinstance(result, Failure) for result in results)
    with patch.object(pr, "generate_id", return_value=item.id) as generator:
        assert (
            asyncio.run(create_pull_request("main", "main", "x", directory=ready)).reason
            == FailureReason.ID_CONFLICT
        )
        generator.assert_awaited_once_with("pull_request")
    with patch.object(pr, "generate_id", return_value="main") as generator:
        assert asyncio.run(add_comment(item.id, "x", ready)).reason == FailureReason.ID_CONFLICT
        generator.assert_awaited_once_with("comment")
    assert git(ready, "rev-parse", GC_REF) == before


def test_concurrent_publication(ready: Path) -> None:
    # A competing valid commit must survive a failed compare-and-swap publication.
    item = create(ready)
    old = git(ready, "rev-parse", GC_REF)
    tree = git(ready, "rev-parse", f"{old}^{{tree}}")
    winner = git(ready, "commit-tree", tree, "-p", old, "-m", "Concurrent update")
    original = pr._git

    def race(repository, *args, **kwargs):
        if args[0] == "update-ref":
            git(ready, "update-ref", GC_REF, winner, old)
        return original(repository, *args, **kwargs)

    with patch.object(pr, "_git", side_effect=race):
        result = update_pull_request(item.id, ["title=Lost race"], ready)
    assert isinstance(result, Failure) and result.reason == FailureReason.GIT_ERROR
    assert git(ready, "rev-parse", GC_REF) == winner
    assert list_pull_requests(directory=ready).value[0].title == item.title


def test_cli_counts_stdin_and_help(ready: Path, monkeypatch) -> None:
    # Fixed argument counts and token validation reject accidentally unquoted prose.
    monkeypatch.chdir(ready)
    runner = CliRunner()
    result = runner.invoke(
        app, ["pr", "new", "feature/login", "main", "Quoted title", "@-"], input="body\n"
    )
    assert result.exit_code == 0, result.output
    identifier = list_pull_requests().value[0].id
    assert list_comments(identifier).value[0].text == "body\n"
    assert (
        runner.invoke(app, ["comment", identifier + ":main", "@-"], input="reply\n").exit_code == 0
    )
    before = git(ready, "rev-parse", GC_REF)
    for args in (
        ["pr", "new", "main", "main"],
        ["pr", "new", "main", "main", "title", "comment", "extra"],
        ["comment", identifier],
        ["comment", identifier, "text", "extra"],
        ["pr", "comments", identifier, "extra"],
        ["pr", "update", identifier],
        ["pr", "update", identifier, "title=unquoted", "words"],
    ):
        assert runner.invoke(app, args).exit_code != 0
    assert git(ready, "rev-parse", GC_REF) == before
    assert "pr" in runner.invoke(app, ["help"]).stdout
    assert "title=" in runner.invoke(app, ["pr", "update", "--help"]).stdout


def test_preconditions(repo: Path, tmp_path: Path) -> None:  # noqa: F811
    # Missing initialization and non-repositories produce stable public failures.
    assert list_pull_requests(directory=repo).reason == FailureReason.NOT_INITIALIZED
    assert list_pull_requests(directory=tmp_path).reason == FailureReason.NOT_A_REPOSITORY


def test_bare_deleted_and_unrelated_branches(ready: Path, tmp_path: Path) -> None:
    # Bare repos need no checkout; unrelated or deleted branches cannot imply merged.
    bare = tmp_path / "bare.git"
    git(tmp_path, "clone", "--bare", str(ready), str(bare))
    item = create(bare)
    unrelated_tree = git(bare, "rev-parse", "main^{tree}")
    unrelated = git(bare, "commit-tree", unrelated_tree, "-m", "Unrelated root")
    git(bare, "update-ref", "refs/heads/main", unrelated)
    assert list_pull_requests(["open"], bare).value[0].id == item.id
    git(bare, "branch", "-D", "main")
    assert list_pull_requests(directory=bare).value[0].status == "open"
    assert list_pull_requests(["base=main"], bare).reason == FailureReason.BRANCH_NOT_FOUND


def test_optional_comment_and_branch_updates(ready: Path, monkeypatch) -> None:
    # Three arguments create an empty main comment; updates validate and store both branches.
    monkeypatch.chdir(ready)
    runner = CliRunner()
    assert runner.invoke(app, ["pr", "new", "feature/login", "main", "Title"]).exit_code == 0
    item = list_pull_requests().value[0]
    assert list_comments(item.id).value[0].text == ""
    result = runner.invoke(app, ["pr", "update", item.id, "compare=main", "base=feature/login"])
    assert result.exit_code == 0, result.output
    updated = list_pull_requests().value[0]
    assert (updated.compare, updated.base) == ("main", "feature/login")
    assert runner.invoke(app, ["pr", "list", "mine", "title=Title"]).exit_code == 0
    assert runner.invoke(app, ["pr", "comments", item.id]).exit_code == 0


def test_operational_failures_and_malformed_metadata(ready: Path) -> None:
    # Failure boundaries preserve the ref on provider/I/O failures and reject corrupt directories.
    before = git(ready, "rev-parse", GC_REF)
    with patch.object(pr, "generate_id", side_effect=OSError("provider unavailable")):
        assert asyncio.run(add_comment("any", "text", ready)).reason == FailureReason.IO_ERROR
    with patch.object(pr, "_git", side_effect=PermissionError("denied")):
        assert list_pull_requests(directory=ready).reason == FailureReason.IO_ERROR
    assert git(ready, "rev-parse", GC_REF) == before
    # Deliberately construct malformed metadata in the disposable repo only.
    with pr.Repo(ready) as repository:
        store = pr._Store(repository)
        store.prs["not-a-pr"] = pr._write_tree(repository, {})
        store.publish("Malformed fixture")
    assert list_pull_requests(directory=ready).reason == FailureReason.INVALID_METADATA
