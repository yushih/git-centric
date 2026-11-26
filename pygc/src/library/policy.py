"""Typed policy boundary shared by all Git-centric interfaces."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

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


def check_action(action: Action) -> Literal[True] | Failure:
    """Placeholder for the policy evaluator. Only literal True grants access."""
    return True


class Denied(Exception):
    def __init__(self, failure: Failure):
        self.failure = failure
        super().__init__(failure.detail)


def require(action: Action) -> None:
    """Abort through the library Result boundary, preserving the policy's failure."""
    decision = check_action(action)
    if decision is not True:
        if isinstance(decision, Failure):
            raise Denied(decision)
        raise Denied(Failure(FailureReason.ACCESS_DENIED, "Policy did not grant access"))
