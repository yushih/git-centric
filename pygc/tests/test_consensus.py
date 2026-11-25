"""Exercise finalization with actual pushes, divergent histories and Git notes."""

import json
from pathlib import Path

import pytest
from test_initialization import git, isolated_git_config, repo  # noqa: F401
from typer.testing import CliRunner

from pygc import FailureReason, Success, add_node, finalize, initialize_gc
from pygc.cli import app
from pygc.library.constants import GC_REF, GIT_NOTES_REF


def peer(local: Path, name: str) -> Path:
    # Bare peers accept metadata pushes without a checkout.
    path = local.parent / name
    path.mkdir()
    git(path, "init", "--bare")
    assert isinstance(add_node(name, str(path), local), Success)
    return path


def diverge(local: Path, other: Path, conflict: bool) -> None:
    # Build competing registry entries from the same parent. Identical names
    # with different URL blobs force a real add/add conflict.
    git(local, "push", str(other), GC_REF)
    assert isinstance(add_node("local-change", "local", local), Success)
    name = "local-change" if conflict else "remote-change"
    assert isinstance(add_node(name, "other", other), Success)


def test_no_finality_cli(repo):  # noqa: F811
    # Zero voters and an unreachable voter both leave one idempotent local note.
    initialize_gc(repo)
    runner = CliRunner()

    def invoke():
        result = runner.invoke(app, ["consensus", "finalize", "--repo-dir", str(repo)])
        assert result.exit_code == 0, result.output
        assert "no finality" in result.stderr
        assert json.loads(result.stdout)["finalized"] is False
        return result

    invoke()
    initial = git(repo, "rev-parse", GIT_NOTES_REF)
    invoke()
    assert git(repo, "rev-parse", GIT_NOTES_REF) == initial
    assert isinstance(add_node("offline", str(repo / "absent"), repo), Success)
    assert "node unreachable: offline" in invoke().stderr
    assert git(repo, "notes", "show", GC_REF) == "not finalized"


def test_clean_merge_and_next_push(repo):  # noqa: F811
    # The reconciled tip feeds subsequent peers; user index/worktree stay intact.
    initialize_gc(repo)
    first = peer(repo, "a-peer")
    last = peer(repo, "z-peer")
    diverge(repo, first, False)
    local, remote = (git(path, "rev-parse", GC_REF) for path in (repo, first))
    (repo / "dirty").write_text("staged")
    git(repo, "add", "dirty")
    (repo / "dirty").write_text("unstaged")
    index = (repo / ".git/index").read_bytes()
    result = finalize(repo)
    assert isinstance(result, Success), result
    # local-change was itself registered as an unreachable third voter.
    assert result.value.finalized and result.value.successful == ("a-peer", "z-peer")
    assert git(repo, "show", "-s", "--format=%P", GC_REF) == f"{local} {remote}"
    assert git(last, "rev-parse", GC_REF) == result.value.tip
    assert git(repo, "symbolic-ref", "HEAD") == "refs/heads/main"
    assert (repo / ".git/index").read_bytes() == index
    assert (repo / "dirty").read_text() == "unstaged"
    assert not (repo / ".git/FETCH_HEAD").exists()


@pytest.mark.parametrize("extra", [0, 1, 2, 3])
def test_conflict_outcomes(repo, extra):  # noqa: F811
    # Set up one conflicting peer, then configure enough successful voters
    # to test a conflict majority, a tie and a success majority.
    initialize_gc(repo)
    other = peer(repo, "opponent")
    for index in range(extra):
        peer(repo, f"support-{index}")
    git(repo, "push", str(other), GC_REF)
    base = git(repo, "rev-parse", GC_REF)
    # Diverge a non-registry file so both rounds use exactly the intended voters.
    for path, body in [(repo, "ours"), (other, "theirs")]:
        checkout = repo.parent / f"checkout-{body}"
        git(path, "worktree", "add", str(checkout), "__git-centric__")
        (checkout / "value").write_text(body)
        git(checkout, "add", "value")
        git(checkout, "commit", "-m", f"record {body}")
    git(other, "notes", "add", "-m", "prior annotation", base)
    if extra == 2:
        # Simulate a peer allowing metadata pushes but denying notes updates.
        git(other, "config", "receive.hideRefs", GIT_NOTES_REF)
    tip = git(repo, "rev-parse", GC_REF)
    result = finalize(repo)
    if extra == 0:
        assert result.reason == FailureReason.CONFLICT_CHANGE
    elif extra == 1:
        assert isinstance(result, Success) and not result.value.finalized
        assert git(repo, "notes", "show", tip) == "not finalized"
    elif extra == 2:
        assert isinstance(result, Success) and result.value.finalized
        assert "could not publish conflict note to node opponent" in result.value.warnings
        assert git(other, "notes", "show", base) == "prior annotation"
    else:
        assert isinstance(result, Success) and result.value.finalized
        assert git(other, "notes", "show", GC_REF) == "conflict: support-0, support-1, support-2"
        assert git(other, "notes", "show", base) == "prior annotation"
    assert git(repo, "rev-parse", GC_REF) == tip
    assert git(repo, "for-each-ref", "refs/notes/gc-finalize-*") == ""


def test_concurrent_local_write(repo, monkeypatch):  # noqa: F811
    # A write after the final push cannot inherit the earlier candidate's votes.
    from pygc.library import consensus

    initialize_gc(repo)
    peer(repo, "first")
    push = consensus._push

    def racing_push(repository, node, oid, ref):
        result = push(repository, node, oid, ref)
        assert isinstance(add_node("later", "other", repo), Success)
        return result

    monkeypatch.setattr(consensus, "_push", racing_push)
    assert finalize(repo).reason == FailureReason.STALE_SNAPSHOT
    assert git(repo, "log", "-1", "--format=%s", GC_REF) == "add node later"
    assert git(repo, "for-each-ref", GIT_NOTES_REF) == ""
