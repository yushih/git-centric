"""Exercise the browser contract against an independent Git repository."""

import asyncio

import httpx
import pytest
from test_initialization import git, isolated_git_config, repo  # noqa: F401

from pygc.library.constants import GC_REF
from pygc.rpc import dispatch, repository_methods
from pygc.web import create_app


def test_guarded_discussion_and_patch(repo):  # noqa: F811
    # Preserve a dirty worktree through setup, discussion and compare-side patch reads.
    file = repo / "example"
    file.write_text("base\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Base")
    git(repo, "checkout", "-b", "topic/ui")
    file.write_text("feature\n")
    git(repo, "commit", "-am", "Change example")
    file.write_text("dirty\n")
    before = git(repo, "status", "--porcelain")
    methods = repository_methods(repo)

    def rpc(method, **params):
        return dispatch(dict(jsonrpc="2.0", id=1, method=method, params=params), methods)

    assert "+base" in rpc("code.browse", branch="main", detail=True)["result"]["patch"]
    assert "result" in rpc("repo.initialize")
    for tab in ("issues", "pulls"):
        params = {"base": "main", "compare": "topic/ui"} if tab == "pulls" else {}
        identifier = rpc(tab + ".create", title="Example", description="@-", **params)["result"][
            "id"
        ]
        detail = rpc(tab + ".show", id=identifier)["result"]
        tip = detail["metadata_tip"]
        assert detail["comments"][0]["text"] == "@-"
        comment = rpc(
            tab + ".comments.add", id=identifier, expectedTip=tip, text="Reply", repliesTo=["main"]
        )
        assert comment["result"]["replies_to"] == ("main",)
        new_tip = git(repo, "rev-parse", GC_REF)
        # A stale edit cannot overwrite the newer conversation or publish another commit.
        stale = rpc(tab + ".update", id=identifier, expectedTip=tip, title="Stale")
        assert stale["error"]["data"]["reason"] == "stale_snapshot"
        assert git(repo, "rev-parse", GC_REF) == new_tip
    patch_params = dict(
        id=identifier, baseTip=detail["base_tip"], compareTip=detail["compare_tip"], path="example"
    )
    assert "+feature" in rpc("pulls.patch", **patch_params)["result"]
    git(repo, "commit", "--allow-empty", "-m", "Advance compare")
    assert rpc("pulls.patch", **patch_params)["error"]["data"]["reason"] == "stale_snapshot"
    assert git(repo, "status", "--porcelain") == before and file.read_text() == "dirty\n"


def test_setup_requires_local_request(repo):  # noqa: F811
    # Reject an entire mixed batch from a foreign origin before any notification can write.
    async def exercise():
        transport = httpx.ASGITransport(app=create_app(directory=repo))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            payload = [
                {"jsonrpc": "2.0", "method": "repo.initialize"},
                {"jsonrpc": "2.0", "id": 1, "method": "repo.get"},
            ]
            denied = await client.post(
                "/api/rpc", json=payload, headers={"origin": "https://example.org"}
            )
            assert denied.status_code == 403
            assert not git(repo, "branch", "--list")
            accepted = await client.post(
                "/api/rpc", json=payload, headers={"origin": "http://localhost:5173"}
            )
            assert accepted.json()[0]["result"]["initialized"]

    asyncio.run(exercise())


def test_pinned_source_previews(repo, tmp_path):  # noqa: F811
    # Follow Git objects in a bare clone and detached checkout; never dereference symlinks.
    from pygc.library.source import browse_source

    (repo / "binary").write_bytes(b"\x00\xff")
    (repo / "large").write_bytes(b"x" * (1024 * 1024 + 1))
    (repo / "link").symlink_to("binary")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Preview fixtures")
    revision = git(repo, "rev-parse", "HEAD")
    bare = tmp_path / "bare.git"
    git(tmp_path, "clone", "--bare", str(repo), str(bare))
    assert browse_source(bare, path="binary").value["notice"] == "Binary file"
    assert browse_source(bare, path="link").value["text"] == "binary"
    assert "1 MiB" in browse_source(bare, path="large").value["notice"]
    assert "1 MiB" in browse_source(bare, revision=revision, detail=True).value["patch"]
    git(repo, "checkout", "--detach", revision)
    assert browse_source(repo).value["detached"]
    # History remains pinned when the branch advances and the working file disappears.
    git(repo, "checkout", "main")
    git(repo, "rm", "large")
    git(repo, "commit", "-m", "Remove oversized fixture")
    assert (
        browse_source(repo, revision=revision, history=True).value["commits"][0]["id"] == revision
    )
    assert browse_source(repo, detail=True, path="large").value["changes"][0]["status"] == "deleted"


@pytest.mark.parametrize("tab", ["issues", "pulls"])
def test_reply_keeps_creation_byline(repo, monkeypatch, tab):  # noqa: F811
    # Historical entity renames and subsequent edits must retain the original reply author and date.
    git(repo, "commit", "--allow-empty", "-m", "Source")
    git(repo, "branch", "topic/byline")
    methods = repository_methods(repo)

    def rpc(method, **params):
        return dispatch(dict(jsonrpc="2.0", id=1, method=method, params=params), methods)["result"]

    rpc("repo.initialize")
    branches = {"base": "main", "compare": "topic/byline"} if tab == "pulls" else {}
    item = rpc(f"{tab}.create", title="Original", description="Opening", **branches)
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Reviewer")
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2024-04-05T10:11:12+02:00")
    reply = rpc(
        f"{tab}.comments.add",
        id=item["id"],
        expectedTip=git(repo, "rev-parse", GC_REF),
        repliesTo=["main"],
        text="Review",
    )
    author, date = git(repo, "show", "-s", "--format=%an <%ae>%n%aI", GC_REF).splitlines()
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Editor")
    rpc(f"{tab}.update", id=item["id"], expectedTip=git(repo, "rev-parse", GC_REF), title="Renamed")
    rpc(
        f"{tab}.comments.update",
        id=item["id"],
        expectedTip=git(repo, "rev-parse", GC_REF),
        comment=reply["id"],
        text="Revised",
    )
    detail = rpc(f"{tab}.show", id=item["id"])
    opening, revised = detail["comments"]
    assert opening["author"] == detail["pull_request" if tab == "pulls" else "issue"]["author"]
    assert (revised["author"], revised["created_at"], revised["text"]) == (author, date, "Revised")
