from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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

class ChangeAccessRuleScripts(Fields):
    name: Literal["access.rules.change_scripts"]

Action = Annotated[
    Simple
    | PullCreate
    | PullMerge
    | RoleMetadata
    | RegisterUser
    | UserTarget
    | UserRoles
    | RegisterNode
    | NodeTarget
    | ChangeAccessRuleScripts,
    Field(discriminator="name"),
]
