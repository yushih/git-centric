"""Exercise finalization with actual pushes, divergent histories and Git notes."""

import json
from pathlib import Path

import pytest
from policy_setup import grant_writes
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
    grant_writes(repo)
    runner = CliRunner()

    def invoke():
        result = runner.invoke(app, ["sync", "push", "gc", "--repo-dir", str(repo)])
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
    grant_writes(repo)
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
    assert git(first, "rev-parse", GC_REF) == result.value.tip
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
    grant_writes(repo)
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
    grant_writes(repo)
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


def test_command_completion_uses_current_metadata_tip(repo, tmp_path):  # noqa: F811
    # A write pushes its own commit. A deferred write only annotates it, and a
    # subsequent read retries propagation even though it creates no metadata.
    runner = CliRunner()
    args = ["--repo-dir", str(repo)]
    remote = tmp_path / "peer.git"
    remote.mkdir()
    git(remote, "init", "--bare")
    assert runner.invoke(app, ["init", str(repo), "-do-not-finalize"]).exit_code == 0
    assert git(repo, "notes", "show", GC_REF) == "not finalized"
    grant_writes(repo)
    assert runner.invoke(app, ["node", "add", "peer", str(remote), *args]).exit_code == 0
    old = git(repo, "rev-parse", GC_REF)
    assert git(remote, "rev-parse", GC_REF) == old

    result = runner.invoke(app, ["issue", "new", "Repair", "-do-not-finalize", *args])
    assert result.exit_code == 0 and json.loads(result.stdout)["title"] == "Repair"
    tip = git(repo, "rev-parse", GC_REF)
    assert tip != old and git(remote, "rev-parse", GC_REF) == old
    assert git(repo, "notes", "show", tip) == "not finalized"
    git(repo, "notes", "append", "-m", "existing annotation", tip)
    notes = git(repo, "rev-parse", GIT_NOTES_REF)

    # Either spelling and placement defers even the explicit finalize command.
    for flag in ("-do-not-finalize", "--do-not-finalize"):
        result = runner.invoke(app, [flag, "sync", "push", "gc", *args])
        assert result.exit_code == 0 and not json.loads(result.stdout)["finalized"]
    assert git(repo, "rev-parse", GIT_NOTES_REF) == notes
    assert git(remote, "rev-parse", GC_REF) == old
    # A command error and eager help do not start a round or alter refs.
    assert runner.invoke(app, ["issue", "show", "missing", *args]).exit_code == 1
    assert runner.invoke(app, ["node", "list", "--help", *args]).exit_code == 0
    assert git(remote, "rev-parse", GC_REF) == old
    result = runner.invoke(app, ["issue", "list", *args])
    assert result.exit_code == 0 and json.loads(result.stdout)[0]["title"] == "Repair"
    assert git(remote, "rev-parse", GC_REF) == tip == git(repo, "rev-parse", GC_REF)


def test_cli_runs_one_round_and_surfaces_failure(repo, monkeypatch):  # noqa: F811
    # Ordinary reads, explicit finalize, help and web each dispatch exactly once.
    # Web must do so before Uvicorn starts. A failed round returns exit status 1.
    from pygc import Failure, cli

    initialize_gc(repo)
    grant_writes(repo)
    calls = []
    expected = finalize(repo)

    def record(directory):
        calls.append(directory)
        return expected

    monkeypatch.setattr(cli.library, "finalize", record)
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **kw: calls.append("serve"))
    runner = CliRunner()
    for command in (["node", "list"], ["sync", "push", "gc"], ["help"], ["web"]):
        calls.clear()
        result = runner.invoke(app, [*command, "--repo-dir", str(repo)])
        assert result.exit_code == 0, result.output
        assert calls == ([repo, "serve"] if command == ["web"] else [repo])
    expected = Failure(FailureReason.CONFLICT_CHANGE, "conflict change")
    result = runner.invoke(app, ["issue", "new", "local work", "--repo-dir", str(repo)])
    assert result.exit_code == 1 and "conflict_change" in result.stderr
    assert json.loads(result.stdout)["title"] == "local work"
    assert "local work" in git(repo, "log", "-1", "--format=%s", GC_REF)


def test_restart_selected_branch(repo, monkeypatch):  # noqa: F811
    # A late fast-forward invalidates the first peer's vote. Its failed retry
    # leaves a tie and annotates the selected branch without moving metadata.
    from pygc.library import consensus

    initialize_gc(repo)
    grant_writes(repo)
    first = peer(repo, "first")
    last = peer(repo, "last")
    metadata = git(repo, "rev-parse", GC_REF)
    git(repo, "commit", "--allow-empty", "-m", "base")
    branch = "release/v1"
    git(repo, "branch", branch)
    base = git(repo, "rev-parse", branch)
    git(repo, "commit", "--allow-empty", "-m", "advance")
    advanced = git(repo, "rev-parse", "HEAD")
    git(repo, "push", str(last), f"HEAD:refs/heads/{branch}")
    push = consensus._push

    def reject_retry(repository, node, oid, ref):
        if node.name == "first" and oid == advanced:
            return 1, "policy rejection"
        return push(repository, node, oid, ref)

    monkeypatch.setattr(consensus, "_push", reject_retry)
    result = finalize(repo, branch)
    assert isinstance(result, Success) and not result.value.finalized
    assert result.value.successful == ("last",)
    assert git(first, "rev-parse", branch) == base
    assert git(repo, "rev-parse", branch) == advanced
    assert git(repo, "notes", "show", advanced) == "not finalized"
    assert git(repo, "rev-parse", GC_REF) == metadata
    assert finalize(repo, "absent").reason == FailureReason.BRANCH_NOT_FOUND
    assert finalize(repo, "bad..branch").reason == FailureReason.INVALID_ARGUMENT


def test_sync_push_selects_working_or_explicit_branch(repo):  # noqa: F811
    # Branch selection follows the chosen repository's HEAD. Explicit targets
    # also work in detached HEAD, and each successful push propagates metadata.
    initialize_gc(repo)
    grant_writes(repo)
    remote = peer(repo, "peer")
    git(repo, "commit", "--allow-empty", "-m", "main")
    runner = CliRunner()
    args = ["--repo-dir", str(repo)]
    assert runner.invoke(app, ["sync", "push", *args]).exit_code == 0
    assert git(remote, "rev-parse", "main") == git(repo, "rev-parse", "main")
    assert git(remote, "rev-parse", GC_REF) == git(repo, "rev-parse", GC_REF)
    git(repo, "branch", "topic")
    git(repo, "switch", "--detach")
    assert runner.invoke(app, ["sync", "push", *args]).exit_code == 1
    assert runner.invoke(app, ["sync", "push", "topic", *args]).exit_code == 0
    assert git(remote, "rev-parse", "topic") == git(repo, "rev-parse", "topic")
