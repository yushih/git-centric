# Comment subcommands

State: verified

## Contract and plan

Rename the CLI operations to `gc comment update PR_ID:COMMENT_ID TEXT` and
`gc comment delete PR_ID:COMMENT_ID`. Remove the former top-level
`update-comment` and `delete-comment` commands. Preserve library API names,
JSON output, stdin, strict arity, failure codes and --repo-dir semantics.

Retain `gc comment PR_ID TEXT` for appending through a default add action;
explicit `gc comment add PR_ID TEXT` is also accepted. Action words add/update/delete
are reserved in the first position; explicit add disambiguates such target IDs.
`gc comment --help` lists the actions and documents the shorthand.

1. Update current contracts/docs and register a Typer comment group with a
   default-add parser for backward-compatible appending.
2. Adapt CLI acceptance and repository-routing tests; verify old commands fail,
   new nested help works, and existing add/stdin/arity behavior survives.
3. Run locked sync, lint/format, mypy and Python tests. No dependencies change.

## Evidence

2026-11-19, Python 3.12, from `pygc/` with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked`: passed, no dependency changes.
- `uv run ruff check .` and `uv run ruff format --check .`: passed (16 files).
  Initial long help string was reformatted.
- `uv run mypy src`: passed (11 files), after using the base parser's Context
  type for the override rather than its narrower Typer subclass.
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_pull_requests.py tests/test_repo_directory.py tests/test_initialization.py`:
  63 passed in 8.45s.
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_interfaces.py`: 17 passed in 0.49s outside the sandbox, avoiding the
  previously established test-client stall; existing Starlette/httpx warning.
- `git diff --check`: passed.

`test_comment_edit_cli_and_errors` covers nested operations, stdin, arity,
removed names and explicit add. Existing add-command tests cover shorthand;
repository-directory tests exercise both nested operations against another repo.
All 80 tests passed across targeted runs. No unresolved work.
