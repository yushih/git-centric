# Store rule scripts alongside access records

Build one access-control subtree for roles, users and rules. Evaluate and edit
rules there. Verify the initial tree and blob bytes, policy decisions, and rule
editor operations with the Python regression suite.

Verified with uv run pytest -q (159 passed, one Starlette deprecation warning).
Ruff lint and format checks passed for the changed files. Full mypy still
reports four existing errors in rules-merger-can-merge.py; all other modules pass.
