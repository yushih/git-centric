# Remove the greeting CLI command

State: verified

## Contract and plan

Remove `gc greet`: invocation must exit 2 as an unknown command, and neither
`gc help` nor `gc --help` may advertise it. Retain the Python greeting function,
JSON-RPC registration and frontend example. No dependencies change.

1. Remove the CLI adapter and its usage examples; update architecture and the
   repository-option contract to cover the remaining commands.
2. Adjust interface tests to assert removal while retaining library/RPC coverage.
3. Run locked sync, Ruff lint/format, mypy, and affected interface/repo-option tests.

## Evidence

2026-11-19, Python 3.12, from `pygc/` with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked`: passed, no dependency changes.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed, 16 files.
- `uv run mypy src`: passed, 11 files.
- `uv run pytest -q tests/test_repo_directory.py`: 8 passed.
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_interfaces.py`: 17 passed outside the sandbox (the suite previously
  stalled inside it); one existing Starlette/httpx deprecation warning.
- `git diff --check`: passed.

`test_library_greeting_and_removed_cli` verifies exit 2 and unknown-command
output; `test_help_and_web` verifies both help variants omit greet. Existing
RPC tests verify the retained demo. No unresolved work.
