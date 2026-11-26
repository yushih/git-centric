"""Read and publish trusted repository policy scripts at a pinned metadata tip."""

import ast
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Literal

from git.exc import GitCommandError

from . import policy
from .access import _Registry, _run
from .actions import ChangeAccessRuleScripts
from .constants import (
    GIT_EXECUTABLE_FILE_MODE,
    GIT_REGULAR_FILE_MODE,
    POLICY_DIRECTORY,
    RULE_PATTERN,
    RULES_DIRECTORY,
)
from .initialization import _branch_oid
from .metadata import _blob, _reject, _subtree, _write_tree, prepare_commit, publish_commit
from .result import FailureReason, Result


@dataclass(frozen=True)
class Rule:
    name: str
    source: str


@dataclass(frozen=True)
class RuleSnapshot:
    metadata_tip: str
    rules: list[Rule]


def list_rules(directory: str | Path = ".") -> Result[RuleSnapshot]:
    def read(store: _Registry) -> RuleSnapshot:
        access = _subtree(store.repo, store.gc, POLICY_DIRECTORY)
        entries = _subtree(store.repo, access, RULES_DIRECTORY)
        scripts = []
        for name, (mode, kind, oid) in sorted(entries.items()):
            if fnmatchcase(name, RULE_PATTERN):
                if kind != "blob" or mode not in (GIT_REGULAR_FILE_MODE, GIT_EXECUTABLE_FILE_MODE):
                    _reject(FailureReason.INVALID_METADATA, f"Expected a rule file: {name}")
                try:
                    source = store.repo.odb.stream(bytes.fromhex(oid)).read().decode()
                except UnicodeDecodeError:
                    _reject(FailureReason.INVALID_METADATA, f"Expected UTF-8 source: {name}")
                scripts.append(Rule(name, source))
        return RuleSnapshot(store.parent, scripts)

    return _run(directory, read)


def change_rule(
    operation: Literal["create", "edit", "delete"],
    name: str,
    source: str | None,
    directory: str | Path,
    *,
    expected_tip: str,
) -> Result[str]:
    def write(store: _Registry) -> str:
        if (
            not fnmatchcase(name, RULE_PATTERN)
            or not name.isprintable()
            or "/" in name
            or "\\" in name
        ):
            _reject(FailureReason.INVALID_ARGUMENT, "Expected one rule-*.py filename")
        policy.require(
            ChangeAccessRuleScripts(name="access.rules.change_scripts"), store.repo, store.parent
        )
        access = _subtree(store.repo, store.gc, POLICY_DIRECTORY)
        entries = _subtree(store.repo, access, RULES_DIRECTORY)
        if operation == "create" and name in entries:
            _reject(FailureReason.ID_CONFLICT, f"Rule already exists: {name}")
        if operation != "create" and name not in entries:
            _reject(FailureReason.NOT_FOUND, f"Unknown rule: {name}")
        if operation == "delete" and source is None:
            del entries[name]
        elif operation in ("create", "edit") and isinstance(source, str):
            # Check syntax and the entry point without executing the proposed policy.
            try:
                compile(source, name, "exec")
                tree = ast.parse(source)
            except (SyntaxError, ValueError) as exc:
                _reject(FailureReason.INVALID_ARGUMENT, f"Invalid Python: {exc}")
            if not any(
                isinstance(node, ast.FunctionDef) and node.name == "eval" for node in tree.body
            ):
                _reject(FailureReason.INVALID_ARGUMENT, "Define eval(action, user, roles)")
            mode, kind, oid = _blob(store.repo, source)
            entry = (entries[name][0] if name in entries else mode, kind, oid)
            if entries.get(name) == entry:
                return store.parent
            entries[name] = entry
        else:
            _reject(FailureReason.INVALID_ARGUMENT, "Invalid rule operation or source")
        access[RULES_DIRECTORY] = _write_tree(store.repo, entries)
        commit = prepare_commit(
            store.repo,
            store.root,
            store.gc,
            access,
            POLICY_DIRECTORY,
            store.parent,
            f"{operation} access rule {name}",
        )
        try:
            publish_commit(store.repo, commit, store.parent)
        except GitCommandError:
            if _branch_oid(store.repo) != store.parent:
                _reject(FailureReason.STALE_SNAPSHOT, "Reload the policy rules")
            raise
        return commit

    return _run(directory, write, expected_tip)
