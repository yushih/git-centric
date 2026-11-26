"""Issue acceptance tests use isolated real repositories and independent Git inspection."""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from policy_setup import grant_writes
from test_initialization import git, isolated_git_config, repo  # noqa: F401
from test_pull_requests import ready  # noqa: F401
from typer.testing import CliRunner

from pygc import (
    Failure,
    FailureReason,
    Success,
    add_issue_comment,
    create_issue,
    create_pull_request,
    delete_issue_comment,
    list_issue_comments,
    list_issues,
    show_issue,
    update_issue,
    update_issue_comment,
)
from pygc.cli import app
from pygc.library import issues
from pygc.library.constants import GC_REF


def create(path: Path, title: str = "Title / # : ~> 雪"):
    result = asyncio.run(create_issue(title, "description\n\n", path))
    assert isinstance(result, Success), result
    return result.value


def test_issue_lifecycle_preserves_git_state(ready: Path, monkeypatch) -> None:  # noqa: F811
    # Issue writes must preserve PRs, staged/unstaged bytes, HEAD and parent history.
    pr = asyncio.run(create_pull_request("feature/login", "main", "PR", directory=ready)).value
    (ready / "tracked").write_text("staged")
    git(ready, "add", "tracked")
    (ready / "tracked").write_text("unstaged")
    (ready / "untracked").write_text("keep")
    index = (ready / ".git/index").read_bytes()
    head = git(ready, "rev-parse", "HEAD")
    before = git(ready, "rev-parse", GC_REF)
    pr_tree = git(ready, "rev-parse", f"{GC_REF}:__git-centric__/pull-requests")
    assert list_issues(directory=ready) == Success([])
    item = create(ready)
    created = git(ready, "rev-parse", GC_REF)
    assert git(ready, "rev-list", "--parents", "-n", "1", GC_REF) == f"{created} {before}"
    assert item.author == "GC tests <gc-tests@example.invalid>" and item.created_at
    assert "%2F" in git(ready, "ls-tree", "-r", "--name-only", GC_REF)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Other")
    changed = update_issue(item.id, ["title=New\nTitle", "close"], ready).value
    assert changed.author == item.author and changed.created_at == item.created_at
    assert changed.closed
    assert git(ready, "log", "-1", "--format=%s", GC_REF) == (
        f'update issue {item.id} title="New\\nTitle"; close issue {item.id}'
    )
    tip = git(ready, "rev-parse", GC_REF)
    assert update_issue(item.id, ["close"], ready) == Success(changed)
    assert git(ready, "rev-parse", GC_REF) == tip
    assert update_issue(item.id, ["reopen"], ready).value.closed is False
    assert show_issue(item.id, ready).value.comments[0].text == "description\n\n"
    assert git(ready, "rev-parse", f"{GC_REF}:__git-centric__/pull-requests") == pr_tree
    assert pr.id in git(ready, "ls-tree", "--name-only", f"{GC_REF}:__git-centric__/pull-requests")
    assert git(ready, "rev-parse", "HEAD") == head
    assert (ready / ".git/index").read_bytes() == index
    assert (ready / "tracked").read_text() == "unstaged"
    assert (ready / "untracked").read_text() == "keep"


def test_issue_conversation(ready: Path) -> None:  # noqa: F811
    # Closed issues still accept replies; deleting a target detaches but preserves replies.
    item = create(ready)
    update_issue(item.id, ["close"], ready)
    first = asyncio.run(add_issue_comment(item.id + ":main", "first\n", ready)).value
    second = asyncio.run(
        add_issue_comment(item.id + ":" + first.id + ":main", "second", ready)
    ).value
    assert update_issue_comment(item.id + ":main", "", ready).value.text == ""
    tip = git(ready, "rev-parse", GC_REF)
    assert update_issue_comment(item.id + ":main", "", ready).value.text == ""
    assert git(ready, "rev-parse", GC_REF) == tip
    assert delete_issue_comment(item.id + ":main", ready).reason == FailureReason.INVALID_ARGUMENT
    assert delete_issue_comment(item.id + ":" + first.id, ready) == Success(first)
    comments = list_issue_comments(item.id, ready).value
    assert [c.id for c in comments] == ["main", second.id]
    assert comments[1].text == "second" and comments[1].replies_to == ("main",)
    subject = git(ready, "log", "-1", "--format=%s", GC_REF)
    assert first.id in subject and second.id in subject and item.id in subject


@pytest.mark.parametrize(
    "tokens", [[], ["close", "reopen"], ["title="], ["title= "], ["draft"], ["close", "close"]]
)
def test_invalid_issue_updates(ready: Path, tokens) -> None:  # noqa: F811
    # Invalid batches cannot partially modify an issue or publish a commit.
    item = create(ready)
    tip = git(ready, "rev-parse", GC_REF)
    assert update_issue(item.id, tokens, ready).reason == FailureReason.INVALID_ARGUMENT
    assert git(ready, "rev-parse", GC_REF) == tip


def test_issue_filters_and_failures(ready: Path, tmp_path, monkeypatch) -> None:  # noqa: F811
    # Filters are ANDed and creator-based; failure reasons distinguish input and absence.
    item = create(ready)
    assert list_issues(["open", "mine", "author=GC tests", "title=雪"], ready).value == [item]
    assert list_issues(["closed"], ready) == Success([])
    for filters in [["open", "closed"], ["mine", "mine"], ["title=["], ["unknown"]]:
        assert list_issues(filters, ready).reason == FailureReason.INVALID_ARGUMENT
    assert show_issue("missing", ready).reason == FailureReason.NOT_FOUND
    assert show_issue("bad:id", ready).reason == FailureReason.INVALID_ARGUMENT
    assert asyncio.run(create_issue(" ", directory=ready)).reason == FailureReason.INVALID_ARGUMENT
    assert list_issues(directory=tmp_path).reason == FailureReason.NOT_A_REPOSITORY
    assert (
        asyncio.run(add_issue_comment(item.id + ":missing", "x", ready)).reason
        == FailureReason.NOT_FOUND
    )
    assert update_issue_comment(item.id, "x", ready).reason == FailureReason.INVALID_ARGUMENT
    assert delete_issue_comment(item.id + ":missing", ready).reason == FailureReason.NOT_FOUND

    async def collision(kind):
        return item.id

    monkeypatch.setattr(issues, "generate_id", collision)
    assert (
        asyncio.run(create_issue("collision", directory=ready)).reason == FailureReason.ID_CONFLICT
    )
    # An issue ID may also be a PR ID: scoped commands keep the entities distinct.
    with patch("pygc.library.pull_requests.generate_id", collision):
        assert isinstance(
            asyncio.run(create_pull_request("feature/login", "main", "PR", directory=ready)),
            Success,
        )
    assert show_issue(item.id, ready).value.issue == item


@pytest.mark.parametrize("operation", ["update", "create", "comment", "delete"])
def test_issue_concurrent_writer(ready: Path, operation) -> None:  # noqa: F811
    # A real competing PR write wins; stale issue writes fail without losing that PR.
    item = create(ready)
    comment = asyncio.run(add_issue_comment(item.id, "comment", ready)).value
    original = issues._git
    winner = []

    # Async writers already have a running event loop, so race via a synchronous
    # PR update instead; it exercises the same shared metadata ref transaction.
    pr = asyncio.run(create_pull_request("feature/login", "main", "Before", directory=ready)).value
    from pygc import update_pull_request

    def race(repository, *args, **kwargs):
        if args[0] == "update-ref":
            assert isinstance(update_pull_request(pr.id, ["title=Winner"], ready), Success)
            winner.append(git(ready, "rev-parse", GC_REF))
        return original(repository, *args, **kwargs)

    with patch.object(issues, "_git", side_effect=race):
        if operation == "update":
            result = update_issue(item.id, ["close"], ready)
        elif operation == "create":
            result = asyncio.run(create_issue("Loser", directory=ready))
        elif operation == "comment":
            result = asyncio.run(add_issue_comment(item.id, "Loser", ready))
        else:
            result = delete_issue_comment(item.id + ":" + comment.id, ready)
    assert isinstance(result, Failure) and result.reason == FailureReason.GIT_ERROR
    assert git(ready, "rev-parse", GC_REF) == winner[0]
    assert show_issue(item.id, ready).value.issue == item
    assert len(list_issue_comments(item.id, ready).value) == 2


def test_issue_cli(ready: Path, monkeypatch, tmp_path) -> None:  # noqa: F811
    # Exercise scoped commands, stdin fidelity, output shapes and explicit repo selection.
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    def invoke(args, **kwargs):
        return runner.invoke(app, [*args, "--repo-dir", str(ready)], **kwargs)

    result = invoke(["issue", "new", "CLI", "@-"], input="body\n\n")
    assert result.exit_code == 0, result.output
    item = json.loads(result.stdout)
    identifier = item["id"]
    assert invoke(["issue", "list", "open"]).exit_code == 0
    assert invoke(["issue", "update", identifier, "close"]).exit_code == 0
    result = invoke(["issue", "comment", "add", identifier + ":main", "reply"])
    comment = json.loads(result.stdout)
    assert (
        invoke(
            ["issue", "comment", "update", identifier + ":" + comment["id"], "@-"], input="new\n"
        ).exit_code
        == 0
    )
    result = invoke(["issue", "show", identifier])
    details = json.loads(result.stdout)
    assert set(details) == {"issue", "comments"}
    assert details["comments"][0]["text"] == "body\n\n"
    result = invoke(["issue", "show", identifier, "--text"])
    assert (
        result.exit_code == 0
        and "[main]" in result.stdout
        and f"[{comment['id']}]" in result.stdout
    )
    assert invoke(["issue", "comments", identifier]).exit_code == 0
    assert invoke(["issue", "comment", "delete", identifier + ":" + comment["id"]]).exit_code == 0
    assert invoke(["issue", "new", "title", "body", "extra"]).exit_code == 2
    assert invoke(["issue", "show", "missing"]).exit_code == 1
    for args in [
        ["help"],
        ["issue", "--help"],
        ["issue", "comment", "--help"],
        ["issue", "comments", "--help"],
    ]:
        assert runner.invoke(app, args).exit_code == 0


@pytest.mark.parametrize(
    "corruption",
    ["main", "duplicate", "cycle", "secondary_cycle", "utf8", "mode", "name", "dangling"],
)
def test_issue_invalid_metadata(ready: Path, corruption) -> None:  # noqa: F811
    # Construct committed corruption with plumbing, then ensure every reader/writer rejects it.
    item = create(ready)
    from git import Repo

    from pygc.library.metadata import _blob, _write_tree

    with Repo(ready) as repository:
        store = issues._Store(repository)
        name, _ = store.get(item.id)
        body = {"comment-main": _blob(repository, "")}
        if corruption == "main":
            body = {"comment-other": _blob(repository, "")}
        elif corruption == "duplicate":
            body["comment-main:main"] = _blob(repository, "")
        elif corruption == "cycle":
            body["comment-a:b"] = body["comment-b:a"] = _blob(repository, "")
        elif corruption == "secondary_cycle":
            body["comment-a:main:b"] = body["comment-b:main:a"] = _blob(repository, "")
        elif corruption == "utf8":
            oid = issues._git(repository, "hash-object", "-w", "--stdin", stdin=b"\xff")
            body["comment-main"] = ("100644", "blob", oid)
        elif corruption == "mode":
            body["comment-main"] = ("100755", "blob", body["comment-main"][2])
        elif corruption == "dangling":
            body["comment-a:missing"] = _blob(repository, "")
        else:
            name = item.id + ":bad%ZZ"
            store.entries.clear()
        store.entries[name] = _write_tree(repository, body)
        store.publish("test corrupt issue metadata")
    tip = git(ready, "rev-parse", GC_REF)
    for result in [
        list_issues(directory=ready),
        show_issue(item.id, ready),
        update_issue(item.id, ["close"], ready),
        list_issue_comments(item.id, ready),
    ]:
        assert result.reason == FailureReason.INVALID_METADATA
    assert git(ready, "rev-parse", GC_REF) == tip


def test_issue_bare_and_linked_worktree(ready: Path, tmp_path) -> None:  # noqa: F811
    # Shared refs work through a linked worktree and survive cloning into a bare repo.
    item = create(ready)
    linked = tmp_path / "linked"
    git(ready, "worktree", "add", str(linked), "-b", "linked")
    assert show_issue(item.id, linked).value.issue == item
    bare = tmp_path / "bare.git"
    git(ready, "clone", "--bare", str(ready), str(bare))
    assert update_issue(item.id, ["close"], bare).value.closed
    assert not show_issue(item.id, ready).value.issue.closed


def test_issue_failures_before_publication(ready: Path) -> None:  # noqa: F811
    # Creation metadata read failures and IO errors must not publish a partial operation.
    before = git(ready, "rev-parse", GC_REF)
    original = issues._git

    def failing(repository, *args, **kwargs):
        if args[0] == "show":
            raise OSError("read failed")
        return original(repository, *args, **kwargs)

    with patch.object(issues, "_git", side_effect=failing):
        result = asyncio.run(create_issue("fail", directory=ready))
    assert result.reason == FailureReason.IO_ERROR
    assert git(ready, "rev-parse", GC_REF) == before
    with patch.object(issues, "_git", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            asyncio.run(create_issue("interrupt", directory=ready))


def test_issue_snapshot_and_comment_collision(ready: Path, monkeypatch) -> None:  # noqa: F811
    # A comment published during history lookup must not leak into a captured show.
    item = create(ready)
    original = issues._Store.origins

    def racing_origins(store):
        assert isinstance(asyncio.run(add_issue_comment(item.id, "later", ready)), Success)
        return original(store)

    with patch.object(issues._Store, "origins", racing_origins):
        details = show_issue(item.id, ready).value
    assert len(details.comments) == 1
    assert len(list_issue_comments(item.id, ready).value) == 2

    # Generated IDs cannot replace the reserved main description.
    async def collision(kind):
        return "main"

    monkeypatch.setattr(issues, "generate_id", collision)
    before = git(ready, "rev-parse", GC_REF)
    result = asyncio.run(add_issue_comment(item.id, "overwrite", ready))
    assert result.reason == FailureReason.ID_CONFLICT
    assert git(ready, "rev-parse", GC_REF) == before


def test_issue_uninitialized_and_missing_identity(repo: Path, monkeypatch) -> None:  # noqa: F811
    # Initialization is a precondition; missing author identity fails before publication.
    from pygc import initialize_gc

    assert list_issues(directory=repo).reason == FailureReason.NOT_INITIALIZED
    assert isinstance(initialize_gc(repo), Success)
    grant_writes(repo)
    before = git(repo, "rev-parse", GC_REF)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "")
    result = asyncio.run(create_issue("Needs identity", directory=repo))
    assert result.reason == FailureReason.GIT_ERROR
    assert git(repo, "rev-parse", GC_REF) == before
