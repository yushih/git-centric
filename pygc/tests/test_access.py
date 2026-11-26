"""Exercise registry operations through public entry points and inspect Git independently."""

import json
import subprocess
from pathlib import Path

from test_initialization import git, isolated_git_config, repo  # noqa: F401
from typer.testing import CliRunner

from pygc import (
    FailureReason,
    Role,
    Success,
    add_user,
    assign_role,
    create_role,
    initialize_gc,
    list_roles,
    list_users,
)
from pygc.cli import app
from pygc.library import access
from pygc.library.constants import GC_REF, PRIVATE_KEY_FILE


def test_role_lifecycle(repo):  # noqa: F811
    # Bootstrap only the current author and verify the committed public key independently.
    assert list_roles(repo).reason == FailureReason.NOT_INITIALIZED
    assert CliRunner().invoke(app, ["init", "--repo-dir", str(repo)]).exit_code == 0
    private = Path.home() / PRIVATE_KEY_FILE
    key = subprocess.check_output(["ssh-keygen", "-y", "-f", private], text=True).strip()
    assert private.stat().st_mode & 0o777 == 0o600
    base = f"{GC_REF}:__git-centric__/access-control"
    assert git(repo, "show", base + "/users/GC tests/pk-Ed25519") == key
    runner = CliRunner()

    def run(*args):
        return runner.invoke(app, ["access", *args, "--repo-dir", str(repo), "-do-not-finalize"])

    assert json.loads(run("user", "add", "Ada", key).stdout)["name"] == "Ada"
    assert [u["name"] for u in json.loads(run("user", "list").stdout)] == ["Ada", "GC tests"]
    assert json.loads(run("role", "create", "reviewer", "line\ntwo").stdout)["users"] == []
    assert git(repo, "show", base + "/roles/reviewer") == "line\ntwo"
    assert run("role", "assign", "Ada", "reviewer").exit_code == 0
    assert json.loads(run("role", "assign", "*", "reviewer").stdout)["users"] == ["Ada", "GC tests"]
    assert git(repo, "show", base + "/users/Ada/roles/reviewer") == ""
    tip = git(repo, "rev-parse", GC_REF)
    # Repeats, occupied deletion, duplicate creation and bad targets preserve the tip.
    assert run("role", "assign", "*", "reviewer").exit_code == 0
    assert run("role", "delete", "reviewer").exit_code == 1
    assert create_role("reviewer", directory=repo).reason == FailureReason.ID_CONFLICT
    assert assign_role("missing", "reviewer", repo).reason == FailureReason.NOT_FOUND
    assert add_user("../outside", key, repo).reason == FailureReason.INVALID_ARGUMENT
    assert add_user("bad", "ssh-ed25519 YQ==", repo).reason == FailureReason.INVALID_ARGUMENT
    assert git(repo, "rev-parse", GC_REF) == tip
    assert run("role", "unassign", "*", "reviewer").exit_code == 0
    assert run("role", "remove", "reviewer").exit_code == 0
    # Adding another user and editing a custom role preserve the initial memberships.
    assert json.loads(run("role", "list").stdout) == [
        {"name": name, "metadata": "", "users": ["GC tests"] if name == "owner" else []}
        for name in ("admin", "ci", "merger", "owner")
    ]


def test_key_reuse_and_failure(repo, tmp_path):  # noqa: F811
    # Two repos share a local identity. An unreadable private key prevents publication.
    initialize_gc(repo)
    other = tmp_path / "second.git"
    git(repo, "init", "--bare", str(other))
    assert isinstance(initialize_gc(other), Success)
    assert list_users(other) == list_users(repo)
    broken = tmp_path / "broken.git"
    git(repo, "init", "--bare", str(broken))
    private = Path.home() / PRIVATE_KEY_FILE
    private.write_text("damaged")
    assert initialize_gc(broken).reason == FailureReason.IO_ERROR
    assert private.read_text() == "damaged"
    assert git(broken, "for-each-ref", GC_REF) == ""


def test_access_publication_race(repo, monkeypatch):  # noqa: F811
    # Publish a competing role between object creation and the expected-tip update.
    initialize_gc(repo)
    initial = list_roles(repo).value
    publish = access.publish_commit

    def race(repository, commit, parent):
        monkeypatch.setattr(access, "publish_commit", publish)
        assert isinstance(create_role("winner", directory=repo), Success)
        publish(repository, commit, parent)

    monkeypatch.setattr(access, "publish_commit", race)
    assert create_role("loser", directory=repo).reason == FailureReason.GIT_ERROR
    assert list_roles(repo) == Success([*initial, Role("winner", "", [])])
