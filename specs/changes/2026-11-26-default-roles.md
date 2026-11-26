# Default roles at initialization

Implement ACCESS-006 by constructing role blobs and the owner membership before
the create-only ref transaction. Verify the exact orphan tree and role listing
through Git and the CLI, then run Python static checks and regression tests.

Verified on Linux with Python 3.12. From pygc, ruff check ., ruff format --check .
and mypy src passed. uv run pytest -q passed all 150 tests with one Starlette
TestClient deprecation warning. The initialization tests inspect the exact
parentless tree and the access lifecycle checks memberships through the CLI.
