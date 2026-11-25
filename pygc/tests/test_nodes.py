"""Verify the local node registry through the CLI and independent Git reads."""

import json

from test_initialization import git, isolated_git_config, repo  # noqa: F401
from typer.testing import CliRunner

from pygc import FailureReason, Node, Success, add_node, initialize_gc, list_nodes
from pygc.cli import app
from pygc.library import nodes
from pygc.library.constants import GC_REF


def test_node_commands(repo, monkeypatch):  # noqa: F811
    # The CLI selects the explicit repository and appends to the initialized tree.
    runner = CliRunner()
    args = ["--repo-dir", str(repo)]
    assert list_nodes(repo).reason == FailureReason.NOT_INITIALIZED
    parent = initialize_gc(repo).value
    assert json.loads(runner.invoke(app, ["node", "list", *args]).stdout) == []
    (repo / "work").write_text("staged")
    git(repo, "add", "work")
    (repo / "work").write_text("unstaged")
    index = (repo / ".git/index").read_bytes()
    url = "host:team/project.git"
    result = runner.invoke(app, ["node", "add", "team two", url, *args])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"name": "team two", "url": url}
    assert git(repo, "show", f"{GC_REF}:__git-centric__/nodes/team two/URL") == url
    assert git(repo, "show", "-s", "--format=%P %s", GC_REF) == f"{parent} add node team two"
    assert git(repo, "show", f"{GC_REF}:__git-centric__/.gitkeep") == ""
    # Default cwd and local paths work too. Ordering is independent of insertion.
    monkeypatch.chdir(repo)
    assert add_node("alpha", "/shared/repo") == Success(Node("alpha", "/shared/repo"))
    assert json.loads(runner.invoke(app, ["node", "list"]).stdout) == [
        {"name": "alpha", "url": "/shared/repo"},
        {"name": "team two", "url": url},
    ]
    assert git(repo, "symbolic-ref", "HEAD") == "refs/heads/main"
    assert (repo / ".git/index").read_bytes() == index
    assert (repo / "work").read_text() == "unstaged"
    tip = git(repo, "rev-parse", GC_REF)
    for name, endpoint in [("../escape", url), ("", url), ("bad", "\n")]:
        assert add_node(name, endpoint).reason == FailureReason.INVALID_ARGUMENT
    duplicate = runner.invoke(app, ["node", "add", "alpha", "other"])
    assert duplicate.exit_code == 1 and "id_conflict" in duplicate.stderr
    assert git(repo, "rev-parse", GC_REF) == tip


def test_node_race(repo, monkeypatch):  # noqa: F811
    # Interleave a winning add after the losing commit is built, before its CAS.
    initialize_gc(repo)
    publish = nodes.publish_commit

    def race(repository, commit, parent):
        monkeypatch.setattr(nodes, "publish_commit", publish)
        assert isinstance(add_node("winner", "dest", repo), Success)
        publish(repository, commit, parent)

    monkeypatch.setattr(nodes, "publish_commit", race)
    assert add_node("stale", "other", repo).reason == FailureReason.GIT_ERROR
    assert list_nodes(repo) == Success([Node("winner", "dest")])


def test_corrupt_registry(repo):  # noqa: F811
    # A malformed existing node must surface on reads and prevent publication.
    initialize_gc(repo)
    git(repo, "switch", "__git-centric__")
    directory = repo / "__git-centric__/nodes/broken"
    directory.mkdir(parents=True)
    (directory / "URL").write_bytes(b"\xff")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "install malformed fixture")
    tip = git(repo, "rev-parse", GC_REF)
    assert list_nodes(repo).reason == FailureReason.INVALID_METADATA
    assert add_node("peer", "endpoint", repo).reason == FailureReason.INVALID_METADATA
    assert git(repo, "rev-parse", GC_REF) == tip
