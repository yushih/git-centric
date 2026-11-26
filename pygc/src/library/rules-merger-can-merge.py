from .actions import Action

def eval(
    action: Action, user: str, roles: tuple[str, ...]
) -> Literal["grant", "deny"] | None | Exception:
    if 'merger' in roles and action.name == 'pulls.merge':
        return 'granted'
