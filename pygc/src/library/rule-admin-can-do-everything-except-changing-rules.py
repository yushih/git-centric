from .actions import Action

def eval(
    action: Action, user: str, roles: tuple[str, ...]
) -> Literal["grant", "deny"] | None | Exception:
    if 'owner' not in roles and 'admin' in roles:
        if action.name == 'access.rules.change_scripts':
            return 'deny'
        else:
