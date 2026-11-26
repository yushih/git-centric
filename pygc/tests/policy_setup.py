"""Install an explicit grant rule for scenarios that exercise authorized writes."""

from pathlib import Path

from git import Repo

from pygc.library.constants import GC_DIRECTORY, GC_REF, POLICY_DIRECTORY, RULES_DIRECTORY
from pygc.library.metadata import (
    _blob,
    _subtree,
    _tree,
    _write_tree,
    prepare_commit,
    publish_commit,
)


def grant_writes(directory: Path) -> str:
    """Publish a test policy without touching the scenario's checkout or index."""
    with Repo(directory) as repo:
        parent = repo.commit(GC_REF).hexsha
        root = _tree(repo, parent)
        gc = _subtree(repo, root, GC_DIRECTORY)
        rule = _blob(repo, "def eval(action, user, roles):\n    return 'grant'\n")
        entries = {RULES_DIRECTORY: _write_tree(repo, {"rule-test.py": rule})}
        commit = prepare_commit(
            repo, root, gc, entries, POLICY_DIRECTORY, parent, "install test grant rule"
        )
        publish_commit(repo, commit, parent)
        return commit
