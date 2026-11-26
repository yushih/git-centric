"""Verify the simplified policy contract through the real metadata writers."""

import asyncio

from test_initialization import git, isolated_git_config, repo  # noqa: F401
from typer.testing import CliRunner

from pygc import library as lib
from pygc.cli import app
from pygc.library import policy
from pygc.library.constants import GC_REF


def test_branch_policy(repo, monkeypatch):  # noqa: F811
    # Reject the same effective branch pair at creation and on retargeting.
    # A denied combined edit preserves every field and the metadata ref.
    lib.initialize_gc(repo)
    git(repo, "commit", "--allow-empty", "-m", "source")
    for branch in ("new-base", "topic", "new-topic"):
        git(repo, "branch", branch)
    calls = []
    denied = lib.Failure(lib.FailureReason.ACCESS_DENIED, "protected base")

    def check(action, *_context):
        calls.append(action)
        return denied if action.base == "new-base" else True

    monkeypatch.setattr(policy, "check_action", check)
    create = lib.create_pull_request
    assert asyncio.run(create("new-topic", "new-base", "denied", directory=repo)) is denied
    pr = asyncio.run(create("topic", "main", "allowed", directory=repo)).value
    tip = git(repo, "rev-parse", GC_REF)
    assert (
        lib.update_pull_request(
            pr.id, ["base=new-base", "compare=new-topic", "title=Changed"], repo
        )
        is denied
    )
    assert (
        calls[-1]
        == calls[0]
        == policy.PullCreate(name="pulls.create", base="new-base", compare="new-topic")
    )
    assert git(repo, "rev-parse", GC_REF) == tip
    assert lib.show_pull_request(pr.id, repo).value.pull_request.title == "allowed"
    assert len(calls) == 3


def test_registry_writes(repo, monkeypatch):  # noqa: F811
    # Inspect proposed roles per user. A later denial aborts an entire wildcard mutation.
    lib.initialize_gc(repo)
    key = lib.list_users(repo).value[0].public_key
    calls = []
    blocked = ""
    denied = lib.Failure(lib.FailureReason.ACCESS_DENIED, "fixture")

    def check(action, *_context):
        calls.append(action.model_dump())
        if action.name == blocked:
            if action.name != "access.users.change_roles" or action.user == "GC tests":
                return denied
        return True

    monkeypatch.setattr(policy, "check_action", check)
    assert lib.add_user("Ada", key, repo, roles=["ci", "admin"]).value.name == "Ada"
    assert calls.pop() == {"name": "access.users.add", "user": "Ada", "roles": ("admin", "ci")}
    tip = git(repo, "rev-parse", GC_REF)
    blocked = "access.users.change_roles"
    assert lib.assign_role("*", "merger", repo) is denied
    assert [a["new_roles"] for a in calls] == [("admin", "ci", "merger"), ("merger", "owner")]
    assert git(repo, "rev-parse", GC_REF) == tip
    assert lib.change_role_metadata("ci", "Build\nchecks", repo).value == lib.Role(
        "ci", "Build\nchecks", ["Ada"]
    )
    assert calls[-1] == {
        "name": "access.roles.change_metadata",
        "role": "ci",
        "new_metadata": "Build\nchecks",
    }
    blocked = "access.roles.change_metadata"
    assert lib.change_role_metadata("ci", "unapproved", repo) is denied
    assert lib.create_role("review", directory=repo).value.name == "review"
    assert calls[-1] == {"name": "access.roles.create"}
    blocked = "access.users.change_public_key"
    assert lib.change_user_public_key("Ada", key, repo) is denied
    assert calls[-1] == {"name": blocked, "user": "Ada"}
    blocked = "access.users.delete"
    assert lib.delete_user("Ada", repo) is denied
    blocked = ""
    assert lib.delete_user("Ada", repo).value.name == "Ada"
    assert not next(r for r in lib.list_roles(repo).value if r.name == "ci").users


def test_node_policy_and_public_reads(repo, monkeypatch):  # noqa: F811
    # The registered name is the node ID. Removal uses the URL from the committed record.
    calls = []
    denied = lib.Failure(lib.FailureReason.ACCESS_DENIED, "keep node")

    def check(action, *_context):
        calls.append(action.model_dump())
        return denied if action.name == "nodes.remove" else True

    monkeypatch.setattr(policy, "check_action", check)
    lib.initialize_gc(repo)
    runner = CliRunner()
    args = ["--repo-dir", str(repo), "-do-not-finalize"]
    for command in (["add", "office", "a.git"], ["update-url", "office", "b.git"], ["list"]):
        assert runner.invoke(app, ["node", *command, *args]).exit_code == 0
    tip = git(repo, "rev-parse", GC_REF)
    assert runner.invoke(app, ["node", "remove", "office", *args]).exit_code == 1
    assert git(repo, "rev-parse", GC_REF) == tip
    assert lib.get_access(repo).value.roles
    assert lib.get_repository(repo).value.initialized
    assert calls == [
        {"name": "nodes.add", "url": "a.git"},
        {"name": "nodes.change_url", "node_id": "office", "url": "b.git"},
        {"name": "nodes.remove", "node_id": "office", "url": "b.git"},
    ]
    monkeypatch.setattr(policy, "check_action", lambda action, *_context: True)
    assert lib.remove_node("office", repo) == lib.Success(lib.Node("office", "b.git"))


def test_issue_permissions(repo, monkeypatch):  # noqa: F811
    # Creation and posting are distinct parameterless actions, and reads are public.
    lib.initialize_gc(repo)
    seen = []

    def check(action, *_context):
        seen.append(action.model_dump())
        return (
            True
            if action.name == "issues.create"
            else lib.Failure(lib.FailureReason.ACCESS_DENIED, "no comments")
        )

    monkeypatch.setattr(policy, "check_action", check)
    issue = asyncio.run(lib.create_issue("Issue", directory=repo)).value
    tip = git(repo, "rev-parse", GC_REF)
    assert (
        asyncio.run(lib.add_issue_comment(issue.id, "body", repo)).reason
        == lib.FailureReason.ACCESS_DENIED
    )
    assert lib.show_issue(issue.id, repo).value.issue == issue
    assert git(repo, "rev-parse", GC_REF) == tip
    assert seen == [{"name": "issues.create"}, {"name": "issues.comments.add"}]


def test_committed_rules(repo):  # noqa: F811
    # Replace the rule subtree in successive commits. Writes must authorize
    # against this repository even while the process is in another checkout.
    from git import Repo

    from pygc.library.constants import GC_DIRECTORY, POLICY_DIRECTORY, RULES_DIRECTORY
    from pygc.library.metadata import (
        _blob,
        _subtree,
        _tree,
        _write_tree,
        prepare_commit,
        publish_commit,
    )

    lib.initialize_gc(repo)
    action = policy.Simple(name="issues.create")
    # A fresh metadata branch has no rules directory at all.
    assert policy.check_action(action, repo) == lib.Failure(
        lib.FailureReason.ACCESS_DENIED, "No policy rule result"
    )
    cases = [
        ([], "No policy rule result"),
        (["None"], "No policy rule result"),
        (["'grant'", "None", "'grant'"], True),
        (["'deny'", "'deny'"], "Policy denied"),
        (["'grant'", "'deny'"], "Conflicting"),
        (["'grant'", "1 / 0"], "ZeroDivisionError"),
        (["[]"], "invalid rule result"),
        (
            [
                "'grant' if (action.name, user, roles) == "
                "('issues.create', 'GC tests', ('owner',)) else 'deny'"
            ],
            True,
        ),
    ]
    with Repo(repo) as database:
        for expressions, expected in cases:
            tip = git(repo, "rev-parse", GC_REF)
            root = _tree(database, tip)
            gc = _subtree(database, root, GC_DIRECTORY)
            rules = {
                f"rule-{i}.py": _blob(
                    database, f"def eval(action, user, roles):\n    return {expr}\n"
                )
                for i, expr in enumerate(expressions)
            }
            rules["ignored.py"] = _blob(database, "raise RuntimeError()")
            commit = prepare_commit(
                database,
                root,
                gc,
                {RULES_DIRECTORY: _write_tree(database, rules)},
                POLICY_DIRECTORY,
                tip,
                "replace test rules",
            )
            publish_commit(database, commit, tip)
            decision = policy.check_action(action, repo)
            if expected is True:
                assert decision is True
            else:
                assert isinstance(decision, lib.Failure)
                assert expected in decision.detail
                assert asyncio.run(lib.create_issue("blocked", directory=repo)) == decision
                assert git(repo, "rev-parse", GC_REF) == commit
