"""Typed policy boundary shared by all Git-centric interfaces."""

from fnmatch import fnmatchcase
from pathlib import Path
from typing import Annotated, Any, Literal

from git import Repo
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from .constants import (
    ACCESS_DIRECTORY,
    GC_DIRECTORY,
    GC_REF,
    GIT_EXECUTABLE_FILE_MODE,
    GIT_REGULAR_FILE_MODE,
    POLICY_DIRECTORY,
    ROLES_DIRECTORY,
    RULE_PATTERN,
    RULES_DIRECTORY,
    USERS_DIRECTORY,
)
from .result import Failure, FailureReason


class Fields(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Simple(Fields):
    name: Literal[
        "issues.create", "issues.comments.add", "access.roles.create", "policy.scripts.change"
    ]


class PullCreate(Fields):
    name: Literal["pulls.create"]
    base: str
    compare: str


class PullMerge(Fields):
    name: Literal["pulls.merge"]
    id: str
    base: str


class RoleMetadata(Fields):
    name: Literal["access.roles.change_metadata"]
    role: str
    new_metadata: str


class RegisterUser(Fields):
    name: Literal["access.users.add"]
    user: str
    roles: tuple[str, ...]


class UserTarget(Fields):
    name: Literal["access.users.delete", "access.users.change_public_key"]
    user: str


class UserRoles(Fields):
    name: Literal["access.users.change_roles"]
    user: str
    new_roles: tuple[str, ...]


class RegisterNode(Fields):
    name: Literal["nodes.add"]
    url: str


class NodeTarget(Fields):
    name: Literal["nodes.change_url", "nodes.remove"]
    node_id: str
    url: str  # Proposed endpoint on update, stored endpoint on removal.


Action = Annotated[
    Simple
    | PullCreate
    | PullMerge
    | RoleMetadata
    | RegisterUser
    | UserTarget
    | UserRoles
    | RegisterNode
    | NodeTarget,
    Field(discriminator="name"),
]
# Pydantic accepts discriminated unions here as well as concrete model classes.
policy_action: TypeAdapter[Action] = TypeAdapter(Action)  # type: ignore[arg-type]


def check_action(
    action: Action, directory: str | Path | Repo = ".", parent: str | None = None
) -> Literal[True] | Failure:
    """Evaluate trusted rule modules from a single committed metadata snapshot."""
    from .initialization import _failure
    from .metadata import _Problem

    try:
        if isinstance(directory, Repo):
            return _evaluate(action, directory, parent)
        with Repo(
            Path(directory).absolute(), search_parent_directories=True, expand_vars=False
        ) as repo:
            return _evaluate(action, repo, parent)
    except _Problem as exc:
        return Failure(exc.reason, str(exc))
    except Exception as exc:
        return _failure(exc)


def _evaluate(action: Action, repo: Repo, parent: str | None) -> Literal[True] | Failure:
    from .initialization import _git
    from .metadata import _subtree, _tree

    oid = parent or _git(repo, "rev-parse", "--verify", GC_REF)
    gc = _subtree(repo, _tree(repo, oid), GC_DIRECTORY)
    rules = _subtree(repo, _subtree(repo, gc, POLICY_DIRECTORY), RULES_DIRECTORY)
    user = _git(repo, "var", "GIT_AUTHOR_IDENT").rsplit(" <", 1)[0]
    access = _subtree(repo, gc, ACCESS_DIRECTORY)
    users = _subtree(repo, access, USERS_DIRECTORY)
    memberships = _subtree(repo, _subtree(repo, users, user), ROLES_DIRECTORY)
    registered = _subtree(repo, access, ROLES_DIRECTORY)
    for role, (mode, kind, marker) in memberships.items():
        if (
            role not in registered
            or (mode, kind) != (GIT_REGULAR_FILE_MODE, "blob")
            or repo.odb.info(bytes.fromhex(marker)).size != 0
        ):
            return Failure(FailureReason.INVALID_METADATA, f"Invalid membership: {user}, {role}")
    roles = tuple(sorted(memberships))
    votes: set[str] = set()
    errors = []
    for name in sorted(rules):
        if not fnmatchcase(name, RULE_PATTERN):
            continue
        try:
            mode, kind, blob = rules[name]
            if kind != "blob" or mode not in (GIT_REGULAR_FILE_MODE, GIT_EXECUTABLE_FILE_MODE):
                raise ValueError("expected a regular Python file")
            source = repo.odb.stream(bytes.fromhex(blob)).read()
            namespace: dict[str, Any] = {"__name__": name}
            exec(compile(source, name, "exec"), namespace)
            vote = namespace["eval"](action, user, roles)
            if vote is None:
                continue
            if type(vote) is not str or vote not in ("grant", "deny"):
                raise ValueError(f"invalid rule result: {vote!r}")
            votes.add(vote)
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    if errors:
        detail = "Policy rule error: " + "; ".join(errors)
    elif votes == {"grant"}:
        return True
    elif votes == {"deny"}:
        detail = "Policy denied access"
    elif votes:
        detail = "Conflicting policy rule results"
    else:
        detail = "No policy rule result"
    return Failure(FailureReason.ACCESS_DENIED, detail)


class Denied(Exception):
    def __init__(self, failure: Failure):
        self.failure = failure
        super().__init__(failure.detail)


def require(action: Action, repo: Repo, parent: str) -> None:
    """Abort through the library Result boundary, preserving the policy's failure."""
    decision = check_action(action, repo, parent)
    if decision is not True:
        if isinstance(decision, Failure):
            raise Denied(decision)
        raise Denied(Failure(FailureReason.ACCESS_DENIED, "Policy did not grant access"))
