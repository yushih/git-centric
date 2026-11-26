from .actions import Action

def eval(
    action: Action, user: str, roles: tuple[str, ...]
) -> Literal["grant", "deny"] | None | Exception:
    if 'owner' in roles:
        return 'grant'
