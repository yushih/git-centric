"""Verify the landing page reads the selected source tree in temporary repositories."""

from test_initialization import git, isolated_git_config, repo  # noqa: F401

from pygc import initialize_gc
from pygc.library.constants import GC_BRANCH
from pygc.library.source import browse_source


def test_source_navigation(repo):  # noqa: F811
    # A metadata-only repository has no visible source commits.
    initialize_gc(repo)
    assert browse_source(repo).value["commit"] is None
    git(repo, "checkout", "-b", "topic/files")
    (repo / "docs").mkdir()
    file = repo / "docs" / "hash #.txt"
    file.write_text("committed\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Add example")
    file.write_text("local changes")
    # Follow a slashed branch and literal path while preserving checkout contents.
    view = browse_source(repo).value
    assert view["branch"] == "topic/files" and GC_BRANCH not in view["branches"]
    assert view["entries"] == [{"name": "docs", "kind": "tree"}]
    rev = view["commit"]["id"]
    assert browse_source(repo, path="docs/hash #.txt", revision=rev).value["text"] == "committed\n"
    assert browse_source(repo, history=True).value["commits"][0]["title"] == "Add example"
    assert browse_source(repo, branch=GC_BRANCH).reason.value == "branch_not_found"
