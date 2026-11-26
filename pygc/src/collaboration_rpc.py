"""Explicit repository-scoped collaboration adapters, invoked in worker threads."""

import asyncio
import re
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, validate_call

from . import library as lib
from .library import policy
from .library.actions import ChangeAccessRuleScripts
from .library.constants import GC_BRANCH, PR_TITLE_SEPARATOR
from .library.nodes import get_node_snapshot

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")]
Tip = Annotated[str, Field(pattern=r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")]
checked = validate_call(config=ConfigDict(strict=True))


def collaboration_methods(directory: Path) -> dict[str, Callable[..., Any]]:
    def result(value: Any) -> Any:
        return value if isinstance(value, lib.Failure) else asdict(value.value)

    def initialize() -> Any:
        outcome = lib.initialize_gc(directory)
        return outcome.value if isinstance(outcome, lib.Success) else outcome

    def issue_create(title: str, description: str = "") -> Any:
        return result(asyncio.run(lib.create_issue(title, description, directory)))

    def pull_create(compare: str, base: str, title: str, description: str = "") -> Any:
        if GC_BRANCH in (compare, base):
            raise ValueError("Reserved branch")
        return result(
            asyncio.run(lib.create_pull_request(compare, base, title, description, directory))
        )

    def issue_update(
        id: Identifier,
        expectedTip: Tip,
        title: str | None = None,
        state: Literal["close", "reopen"] | None = None,
    ) -> Any:
        updates = [f"title={title}"] if title is not None else []
        return result(
            lib.update_issue(
                id, updates + ([state] if state else []), directory, expected_tip=expectedTip
            )
        )

    def pull_update(
        id: Identifier,
        expectedTip: Tip,
        title: str | None = None,
        state: Literal["close", "reopen"] | None = None,
        readiness: Literal["ready", "draft"] | None = None,
        base: str | None = None,
        compare: str | None = None,
    ) -> Any:
        if GC_BRANCH in (base, compare):
            raise ValueError("Reserved branch")
        updates = [
            f"{k}={v}"
            for k, v in (("title", title), ("base", base), ("compare", compare))
            if v is not None
        ]
        return result(
            lib.update_pull_request(
                id,
                updates + [v for v in (state, readiness) if v],
                directory,
                expected_tip=expectedTip,
            )
        )

    def files(id: Identifier, baseTip: Tip, compareTip: Tip, path: str) -> Any:
        outcome = lib.read_pr_diff(id, baseTip, compareTip, path, directory)
        return outcome.value if isinstance(outcome, lib.Success) else outcome

    def access_get() -> Any:
        return result(lib.get_access(directory))

    def rules_list() -> Any:
        return result(lib.list_rules(directory))

    def rule_change(
        operation: Literal["create", "edit", "delete"],
        name: str,
        expectedTip: Tip,
        source: str | None = None,
    ) -> Any:
        decision = lib.change_rule(operation, name, source, directory, expected_tip=expectedTip)
        return decision.value if isinstance(decision, lib.Success) else decision

    def user_add(name: str, publicKey: str, expectedTip: Tip) -> Any:
        return result(lib.add_user(name, publicKey, directory, expected_tip=expectedTip))

    def role_create(name: str, expectedTip: Tip, metadata: str = "") -> Any:
        return result(lib.create_role(name, metadata, directory, expected_tip=expectedTip))

    def role_delete(name: str, expectedTip: Tip) -> Any:
        return result(lib.delete_role(name, directory, expected_tip=expectedTip))

    def role_assign(user: str, role: str, expectedTip: Tip) -> Any:
        return result(lib.assign_role(user, role, directory, expected_tip=expectedTip))

    def role_unassign(user: str, role: str, expectedTip: Tip) -> Any:
        return result(lib.unassign_role(user, role, directory, expected_tip=expectedTip))

    def preview(
        actions: list[policy.Simple | policy.NodeTarget | ChangeAccessRuleScripts],
    ) -> list[bool]:
        # Preview only actions the UI can fully describe before editing. The
        # mutation independently constructs its action from the actual write.
        supported = {
            "issues.create",
            "issues.comments.add",
            "access.roles.create",
            "nodes.remove",
            "access.rules.change_scripts",
        }
        if any(action.name not in supported for action in actions):
            raise ValueError("Unsupported preview action")
        return [policy.check_action(action, directory) is True for action in actions]

    def nodes_list() -> Any:
        return result(get_node_snapshot(directory))

    def node_add(name: str, url: str, expectedTip: Tip) -> Any:
        return result(lib.add_node(name, url, directory, expected_tip=expectedTip))

    def node_change(name: str, url: str, expectedTip: Tip) -> Any:
        return result(lib.change_node_url(name, url, directory, expected_tip=expectedTip))

    def node_remove(name: str, expectedTip: Tip) -> Any:
        return result(lib.remove_node(name, directory, expected_tip=expectedTip))

    methods: dict[str, Callable[..., Any]] = {
        "permissions.preview": checked(preview),
        "nodes.list": checked(nodes_list),
        "nodes.add": checked(node_add),
        "nodes.change_url": checked(node_change),
        "nodes.remove": checked(node_remove),
        "access.rules.list": checked(rules_list),
        "access.rules.change": checked(rule_change),
        "access.get": checked(access_get),
        "access.users.add": checked(user_add),
        "access.roles.create": checked(role_create),
        "access.roles.delete": checked(role_delete),
        "access.roles.assign": checked(role_assign),
        "access.roles.unassign": checked(role_unassign),
        "repo.initialize": checked(initialize),
        "issues.create": checked(issue_create),
        "pulls.create": checked(pull_create),
        "issues.update": checked(issue_update),
        "pulls.update": checked(pull_update),
        "pulls.patch": checked(files),
    }

    def scoped(pulls: bool) -> dict[str, Callable[..., Any]]:
        def listing(
            state: Literal["open", "closed", "all"] = "all", title: str = "", author: str = ""
        ) -> Any:
            if pulls and state == "closed":
                raise ValueError("Unsupported pull request filter")
            filters: list[str] = [] if state == "all" else [state]
            if title:
                # The web search box matches literal substrings, including Git punctuation.
                filters.append("title=(?i)" + re.escape(title))
            if author:
                filters.append("author=" + author)
            records = (lib.list_pull_requests if pulls else lib.list_issues)(filters, directory)
            if isinstance(records, lib.Failure):
                return [] if records.reason == lib.FailureReason.NOT_INITIALIZED else records
            return [asdict(r) for r in records.value]

        def show(id: Identifier) -> Any:
            if pulls:
                return result(lib.show_pull_request(id, directory, include_comment_origins=True))
            return result(lib.show_issue(id, directory, include_comment_origins=True))

        def add(id: Identifier, expectedTip: Tip, text: str, repliesTo: list[Identifier]) -> Any:
            target = PR_TITLE_SEPARATOR.join([id, *repliesTo])
            return result(
                asyncio.run(
                    (lib.add_comment if pulls else lib.add_issue_comment)(
                        target, text, directory, expected_tip=expectedTip
                    )
                )
            )

        def edit(id: Identifier, expectedTip: Tip, comment: Identifier, text: str) -> Any:
            return result(
                (lib.update_comment if pulls else lib.update_issue_comment)(
                    PR_TITLE_SEPARATOR.join([id, comment]),
                    text,
                    directory,
                    expected_tip=expectedTip,
                )
            )

        def delete(id: Identifier, expectedTip: Tip, comment: Identifier) -> Any:
            return result(
                (lib.delete_comment if pulls else lib.delete_issue_comment)(
                    PR_TITLE_SEPARATOR.join([id, comment]), directory, expected_tip=expectedTip
                )
            )

        prefix = "pulls." if pulls else "issues."
        operations: dict[str, Callable[..., Any]] = {
            "list": listing,
            "show": show,
            "comments.add": add,
            "comments.update": edit,
            "comments.delete": delete,
        }
        return {prefix + k: checked(f) for k, f in operations.items()}

    return {**methods, **scoped(False), **scoped(True)}
