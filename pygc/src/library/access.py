"""Snapshot-based user and role registry on the shared metadata branch."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from git import Repo
from git.exc import GitCommandError

from . import policy
from .constants import (
    ACCESS_DIRECTORY,
    GC_DIRECTORY,
    GIT_REGULAR_FILE_MODE,
    PUBLIC_KEY_FILE,
    ROLES_DIRECTORY,
    USERS_DIRECTORY,
)
from .initialization import _branch_oid, _failure, _has_gc_directory
from .keys import public_key
from .metadata import (
    Entries,
    _blob,
    _Problem,
    _reject,
    _subtree,
    _tree,
    _write_tree,
    prepare_commit,
    publish_commit,
)
from .result import Failure, FailureReason, Result, Success


@dataclass(frozen=True)
class User:
    name: str
    public_key: str


@dataclass(frozen=True)
class Role:
    name: str
    metadata: str
    users: list[str]


@dataclass(frozen=True)
class AccessSnapshot:
    metadata_tip: str
    users: list[User]
    roles: list[Role]


def validate_name(name: str, reason: FailureReason = FailureReason.INVALID_ARGUMENT) -> None:
    if (
        not name.strip()
        or not name.isprintable()
        or "/" in name
        or "\\" in name
        or name.lower() in {".", "..", ".git", "*"}
    ):
        _reject(reason, f"Invalid user or role name: {name!r}")


def user_tree(repo: Repo, key: str) -> Entries:
    return {PUBLIC_KEY_FILE: _blob(repo, key + "\n")}


class _Registry:
    def __init__(self, repo: Repo, expected_tip: str | None):
        self.expected_tip = expected_tip
        self.repo = repo
        parent = _branch_oid(repo)
        if expected_tip is not None and parent != expected_tip:
            _reject(FailureReason.STALE_SNAPSHOT, "Registry changed; reload before saving")
        if parent is None or not _has_gc_directory(repo, parent):
            _reject(FailureReason.NOT_INITIALIZED, "Run gc init first")
        self.parent = parent
        self.root = _tree(repo, parent)
        self.gc = _subtree(repo, self.root, GC_DIRECTORY)
        self.access = _subtree(repo, self.gc, ACCESS_DIRECTORY)
        self.roles = _subtree(repo, self.access, ROLES_DIRECTORY)
        self.users = _subtree(repo, self.access, USERS_DIRECTORY)
        self.keys: dict[str, str] = {}
        self.metadata: dict[str, str] = {}
        self.members: dict[str, list[str]] = {}
        for role in sorted(self.roles):
            validate_name(role, FailureReason.INVALID_METADATA)
            self.metadata[role] = self.text(self.roles, role)
            self.members[role] = []
        for user in sorted(self.users):
            validate_name(user, FailureReason.INVALID_METADATA)
            entry = _subtree(repo, self.users, user)
            try:
                self.keys[user] = public_key(self.text(entry, PUBLIC_KEY_FILE))
            except ValueError as exc:
                _reject(FailureReason.INVALID_METADATA, str(exc))
            memberships = _subtree(repo, entry, ROLES_DIRECTORY)
            for role in memberships:
                if role not in self.roles or self.text(memberships, role) != "":
                    _reject(FailureReason.INVALID_METADATA, f"Invalid membership: {user}, {role}")
                self.members[role].append(user)

    def list_users(self) -> list[User]:
        return [User(n, k) for n, k in self.keys.items()]

    def list_roles(self) -> list[Role]:
        return [self.role(n) for n in self.metadata]

    def text(self, entries: Entries, name: str) -> str:
        entry = entries.get(name)
        if not entry or entry[:2] != (GIT_REGULAR_FILE_MODE, "blob"):
            _reject(FailureReason.INVALID_METADATA, f"Expected regular file: {name}")
        try:
            data: bytes = self.repo.odb.stream(bytes.fromhex(entry[2])).read()
            return data.decode()
        except UnicodeDecodeError:
            _reject(FailureReason.INVALID_METADATA, f"Invalid UTF-8: {name}")

    def save(self, name: str, entries: Entries, message: str) -> None:
        self.access[name] = _write_tree(self.repo, entries)
        commit = prepare_commit(
            self.repo, self.root, self.gc, self.access, ACCESS_DIRECTORY, self.parent, message
        )
        try:
            publish_commit(self.repo, commit, self.parent)
        except GitCommandError:
            # Translate a lost publication race only for conditional callers.
            if self.expected_tip is not None and _branch_oid(self.repo) != self.parent:
                _reject(FailureReason.STALE_SNAPSHOT, "Registry changed; reload before saving")
            raise

    def add(self, name: str, key: str, roles: Sequence[str]) -> User:
        validate_name(name)
        if name in self.users:
            _reject(FailureReason.ID_CONFLICT, f"User already exists: {name}")
        try:
            key = public_key(key)
        except ValueError as exc:
            _reject(FailureReason.INVALID_ARGUMENT, str(exc))
        if isinstance(roles, str):
            _reject(FailureReason.INVALID_ARGUMENT, "Expected a sequence of role names")
        initial = tuple(sorted(set(roles)))
        for role in initial:
            self.role(role)
        policy.require(policy.RegisterUser(name="access.users.add", user=name, roles=initial))
        entry = user_tree(self.repo, key)
        if initial:
            marker = _blob(self.repo, "")
            entry[ROLES_DIRECTORY] = _write_tree(self.repo, dict.fromkeys(initial, marker))
        self.users[name] = _write_tree(self.repo, entry)
        suffix = f" with roles {', '.join(initial)}" if initial else ""
        self.save(USERS_DIRECTORY, self.users, f"register user {name}{suffix}")
        return User(name, key)

    def role(self, name: str) -> Role:
        validate_name(name)
        if name not in self.roles:
            _reject(FailureReason.NOT_FOUND, f"Unknown role: {name}")
        return Role(name, self.metadata[name], self.members[name])

    def create(self, name: str, metadata: str) -> Role:
        validate_name(name)
        if name in self.roles:
            _reject(FailureReason.ID_CONFLICT, f"Role already exists: {name}")
        policy.require(policy.Simple(name="access.roles.create"))
        self.roles[name] = _blob(self.repo, metadata)
        self.save(ROLES_DIRECTORY, self.roles, f"create role {name}")
        return Role(name, metadata, [])

    def delete(self, name: str) -> Role:
        role = self.role(name)
        if role.users:
            _reject(FailureReason.INVALID_ARGUMENT, f"Role has users: {name}")
        del self.roles[name]
        self.save(ROLES_DIRECTORY, self.roles, f"delete role {name}")
        return role

    def metadata_update(self, name: str, metadata: str) -> Role:
        role = self.role(name)
        policy.require(
            policy.RoleMetadata(
                name="access.roles.change_metadata", role=name, new_metadata=metadata
            )
        )
        if metadata != role.metadata:
            self.roles[name] = _blob(self.repo, metadata)
            self.save(ROLES_DIRECTORY, self.roles, f"change metadata for role {name}")
        return Role(name, metadata, role.users)

    def edit_user(self, name: str, key: str | None) -> User:
        validate_name(name)
        if name not in self.keys:
            _reject(FailureReason.NOT_FOUND, f"Unknown user: {name}")
        previous = self.keys[name]
        if key is None:
            policy.require(policy.UserTarget(name="access.users.delete", user=name))
            del self.users[name]
            self.save(USERS_DIRECTORY, self.users, f"delete user {name}")
            return User(name, previous)
        try:
            key = public_key(key)
        except ValueError as exc:
            _reject(FailureReason.INVALID_ARGUMENT, str(exc))
        policy.require(policy.UserTarget(name="access.users.change_public_key", user=name))
        if key != previous:
            entry = _subtree(self.repo, self.users, name)
            entry[PUBLIC_KEY_FILE] = _blob(self.repo, key + "\n")
            self.users[name] = _write_tree(self.repo, entry)
            self.save(USERS_DIRECTORY, self.users, f"change public key for user {name}")
        return User(name, key)

    def membership(self, user: str, name: str, assign: bool) -> Role:
        role = self.role(name)
        if user != "*":
            validate_name(user)
            if user not in self.users:
                _reject(FailureReason.NOT_FOUND, f"Unknown user: {user}")
        members = set(role.users)
        targets = sorted(self.users) if user == "*" else [user]
        changed = tuple(target for target in targets if (target in members) != assign)
        # Authorize all resulting memberships before staging any part of a bulk edit.
        for target in changed:
            resulting = {role for role, users in self.members.items() if target in users}
            if assign:
                resulting.add(name)
            else:
                resulting.discard(name)
            policy.require(
                policy.UserRoles(
                    name="access.users.change_roles",
                    user=target,
                    new_roles=tuple(sorted(resulting)),
                )
            )
        for target in changed:
            entry = _subtree(self.repo, self.users, target)
            markers = _subtree(self.repo, entry, ROLES_DIRECTORY)
            if assign:
                markers[name] = _blob(self.repo, "")
                members.add(target)
            else:
                del markers[name]
                members.remove(target)
            entry[ROLES_DIRECTORY] = _write_tree(self.repo, markers)
            self.users[target] = _write_tree(self.repo, entry)
        # Wildcards operate on the validated snapshot and publish in one ref update.
        if changed:
            verb = "assign" if assign else "unassign"
            self.save(USERS_DIRECTORY, self.users, f"{verb} role {name}: {', '.join(changed)}")
        return Role(name, role.metadata, sorted(members))


def _run[T](
    directory: str | Path, operation: Callable[[_Registry], T], expected_tip: str | None = None
) -> Result[T]:
    try:
        with Repo(
            Path(directory).absolute(), search_parent_directories=True, expand_vars=False
        ) as repo:
            return Success(operation(_Registry(repo, expected_tip)))
    except _Problem as exc:
        return Failure(exc.reason, str(exc))
    except Exception as exc:
        return _failure(exc)


def add_user(
    name: str,
    public_key: str,
    directory: str | Path = ".",
    *,
    roles: Sequence[str] = (),
    expected_tip: str | None = None,
) -> Result[User]:
    return _run(directory, lambda r: r.add(name, public_key, roles), expected_tip)


def list_users(directory: str | Path = ".") -> Result[list[User]]:
    return _run(directory, _Registry.list_users)


def list_roles(directory: str | Path = ".") -> Result[list[Role]]:
    return _run(directory, _Registry.list_roles)


def create_role(
    name: str, metadata: str = "", directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Role]:
    return _run(directory, lambda r: r.create(name, metadata), expected_tip)


def delete_role(
    name: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Role]:
    return _run(directory, lambda r: r.delete(name), expected_tip)


def assign_role(
    user: str, role: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Role]:
    return _run(directory, lambda r: r.membership(user, role, True), expected_tip)


def unassign_role(
    user: str, role: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Role]:
    return _run(directory, lambda r: r.membership(user, role, False), expected_tip)


def get_access(directory: str | Path = ".") -> Result[AccessSnapshot]:
    """Read both views at one immutable tip, including the precondition for writes."""
    return _run(
        directory,
        lambda r: AccessSnapshot(r.parent, r.list_users(), r.list_roles()),
    )


def change_role_metadata(
    name: str, metadata: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[Role]:
    return _run(directory, lambda r: r.metadata_update(name, metadata), expected_tip)


def delete_user(
    name: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[User]:
    return _run(directory, lambda r: r.edit_user(name, None), expected_tip)


def change_user_public_key(
    name: str, public_key: str, directory: str | Path = ".", *, expected_tip: str | None = None
) -> Result[User]:
    return _run(directory, lambda r: r.edit_user(name, public_key), expected_tip)
