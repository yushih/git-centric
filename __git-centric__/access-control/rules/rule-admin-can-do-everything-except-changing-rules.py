from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .actions import Action
else:
    # The policy loader executes copied rules outside the library package.
    from pygc.library.actions import Action


def eval(
    action: Action, user: str, roles: tuple[str, ...]
) -> Literal["grant", "deny"] | None | Exception:
    if "owner" in roles or "admin" not in roles:
        return None
    return "deny" if action.name == "access.rules.change_scripts" else "grant"
