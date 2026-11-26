# Evaluate committed access rules

Pass the writer snapshot to the checker, resolve memberships and evaluate each
rule independently. Verify the decision matrix, repository selection and ref
preservation through policy and interface tests, then run static checks and pytest.

Initialization creates no policy rules. Tests requiring authorized writes now
commit an explicit grant rule. Rule decisions use the effective Git author name,
as initialization does, and rules execute as trusted Python code.

Verified on 2026-11-26 with Python 3.12. From pygc, Ruff lint and format checks
and mypy src passed. The sandboxed suite stalled in the HTTP interface tests.
The first unrestricted run exposed an identity lookup error mapped to
access_denied. After preserving the existing git_error result, uv run pytest -q
passed all 158 tests with one Starlette deprecation warning.
