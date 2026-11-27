"""Exercise the browser contract against an independent Git repository."""

import asyncio

import httpx
import pytest
from policy_setup import grant_writes
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
    grant_writes(repo)
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
    grant_writes(repo)
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


def test_access_snapshot_and_guarded_writes(repo, tmp_path):  # noqa: F811
    # A second session adding a user invalidates the first session's bulk preview.
    async def exercise():
        transport = httpx.ASGITransport(app=create_app(directory=repo))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:

            async def rpc(method, **params):
                response = await client.post(
                    "/api/rpc", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
                )
                return response.json()

            assert "result" in await rpc("repo.initialize")
            tip = grant_writes(repo)
            snapshot = (await rpc("access.get"))["result"]
            assert snapshot["metadata_tip"] == tip
            assert [r["name"] for r in snapshot["roles"]] == ["admin", "ci", "merger", "owner"]
            user = snapshot["users"][0]
            assert snapshot["roles"][-1]["users"] == [user["name"]]
            assert (
                await rpc(
                    "access.users.add", name="Second", publicKey=user["public_key"], expectedTip=tip
                )
            )["result"]["name"] == "Second"
            current = git(repo, "rev-parse", GC_REF)
            params = dict(user="*", role="ci", expectedTip=tip)
            stale = await rpc("access.roles.assign", **params)
            assert stale["error"]["data"]["reason"] == "stale_snapshot"
            assert git(repo, "rev-parse", GC_REF) == current
            assert (await rpc("access.roles.delete", name="ci"))["error"]["code"] == -32602
            assert (await rpc("access.get", directory="/tmp"))["error"]["code"] == -32602
            params["expectedTip"] = current
            assigned = (await rpc("access.roles.assign", **params))["result"]
            assert assigned["users"] == [user["name"], "Second"]
            assert git(repo, "rev-parse", GC_REF + "^") == current
            params["expectedTip"] = git(repo, "rev-parse", GC_REF)
            assert (await rpc("access.roles.assign", **params))["result"] == assigned
            assert git(repo, "rev-parse", GC_REF) == params["expectedTip"]
            response = await client.post(
                "/api/rpc",
                headers={"Origin": "https://example.org"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "access.roles.unassign",
                    "params": params,
                },
            )
            assert response.status_code == 403
            assert git(repo, "rev-parse", GC_REF) == params["expectedTip"]

        # An independently selected legacy repo has no implicit default records.
        legacy = tmp_path / "legacy"
        git(tmp_path, "init", str(legacy))
        marker = legacy / "__git-centric__/.gitkeep"
        marker.parent.mkdir()
        marker.touch()
        git(legacy, "add", ".")
        git(legacy, "commit", "-m", "legacy metadata")
        git(legacy, "branch", "__git-centric__")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(directory=legacy)),
            base_url="http://localhost",
        ) as client:
            assert (await rpc("access.get"))["result"] == {
                "users": [],
                "roles": [],
                "metadata_tip": git(legacy, "rev-parse", GC_REF),
            }

    asyncio.run(exercise())


def test_node_registry_rpc(repo, monkeypatch):  # noqa: F811
    # A browser's snapshot must guard deletion even if another client edits only the URL.
    from pygc import Failure, FailureReason
    from pygc.library import policy

    methods = repository_methods(repo)

    def rpc(method, **params):
        return dispatch(dict(jsonrpc="2.0", id=1, method=method, params=params), methods)

    assert "result" in rpc("repo.initialize")
    initial = grant_writes(repo)
    assert rpc("nodes.list")["result"] == {"metadata_tip": initial, "nodes": []}
    node = {"name": "office", "url": "local.git"}
    assert rpc("nodes.add", **node, expectedTip=initial)["result"] == node
    snapshot = rpc("nodes.list")["result"]
    assert snapshot["nodes"] == [node]
    mutation = {"name": "office", "url": "changed.git"}
    assert (
        rpc("nodes.change_url", **mutation, expectedTip=snapshot["metadata_tip"])["result"]
        == mutation
    )
    assert rpc("nodes.remove", name="office", expectedTip=snapshot["metadata_tip"])["error"][
        "data"
    ] == {"reason": "stale_snapshot"}
    current = git(repo, "rev-parse", GC_REF)
    assert rpc("nodes.remove", name="office")["error"]["code"] == -32602
    monkeypatch.setattr(
        policy, "check_action", lambda *_: Failure(FailureReason.ACCESS_DENIED, "keep")
    )
    assert rpc("nodes.remove", name="office", expectedTip=current)["error"]["data"] == {
        "reason": "access_denied"
    }
    assert rpc("nodes.list")["result"] == {"metadata_tip": current, "nodes": [mutation]}


def test_permission_preview_and_write_recheck(repo, monkeypatch):  # noqa: F811
    # One denied row must not mask an allowed sibling. Preview uses no writer and
    # a previously positive decision grants no authority to the subsequent write.
    from pygc import Failure, FailureReason
    from pygc.library import policy

    methods = repository_methods(repo)

    def rpc(method, **params):
        return dispatch(dict(jsonrpc="2.0", id=1, method=method, params=params), methods)

    tip = rpc("repo.initialize")["result"]
    denial = Failure(FailureReason.ACCESS_DENIED, "denied")
    observed = []

    def check(action, *_context):
        observed.append(action)
        return denial if getattr(action, "node_id", None) == "keep" else True

    monkeypatch.setattr(policy, "check_action", check)
    actions = [{"name": "nodes.remove", "node_id": n, "url": n + ".git"} for n in ("keep", "old")]
    actions.append({"name": "issues.create"})
    assert rpc("permissions.preview", actions=actions)["result"] == [False, True, True]
    assert [a.model_dump() for a in observed] == actions
    assert rpc("permissions.preview", actions=[{"name": "nodes.remove"}])["error"]["code"] == -32602
    monkeypatch.setattr(policy, "check_action", lambda *_: denial)
    assert rpc("issues.create", title="Late denial")["error"]["data"] == {"reason": "access_denied"}
    assert git(repo, "rev-parse", GC_REF) == tip


def test_rule_script_management(repo, monkeypatch):  # noqa: F811
    # The fresh owner's policy controls CRUD, including stale and denied saves.
    methods = repository_methods(repo)

    def rpc(method, **params):
        return dispatch(dict(jsonrpc="2.0", id=1, method=method, params=params), methods)

    tip = rpc("repo.initialize")["result"]
    listing = rpc("access.rules.list")["result"]
    assert listing["metadata_tip"] == tip
    assert "rule-noop.py" in [rule["name"] for rule in listing["rules"]]
    rules_path = "__git-centric__/access-control/rules"
    helper = git(repo, "rev-parse", f"{tip}:{rules_path}/actions.py")

    def change(operation, tip, **fields):
        params = {"name": "rule-test.py", "expectedTip": tip, "operation": operation}
        return rpc("access.rules.change", **(params | fields))

    source = "def eval(action, user, roles):\n    return None\n"
    for invalid in ({"source": "def broken"}, {"name": "actions.py"}, {"name": "rule-../bad.py"}):
        result = change("create", tip, **({"source": source} | invalid))
        assert result["error"]["data"]["reason"] == "invalid_argument"
    created = change("create", tip, source=source)["result"]
    assert change("edit", created, source=source)["result"] == created
    assert change("delete", tip)["error"]["data"]["reason"] == "stale_snapshot"
    edited = change("edit", created, source=source + "# reviewed\n")["result"]
    assert git(repo, "show", f"{edited}:{rules_path}/rule-test.py").endswith("# reviewed")
    with monkeypatch.context() as patch:
        patch.setenv("GIT_AUTHOR_NAME", "Other")
        assert change("delete", edited)["error"]["data"]["reason"] == "access_denied"
    deleted = change("delete", edited)["result"]
    assert git(repo, "rev-parse", f"{deleted}:{rules_path}/actions.py") == helper
    assert rpc("access.rules.list")["result"]["rules"] == listing["rules"]
