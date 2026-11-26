from .actions import Action

def eval(
    action: Action, user: str, roles: tuple[str, ...]
) -> Literal["grant", "deny"] | None | Exception:
    if 'contributor' in roles and action.name == 'pulls.create':
        return 'granted'
