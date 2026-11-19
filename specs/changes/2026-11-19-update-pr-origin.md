# Preserve creation metadata in PR update responses

State: verified
Related spec: [PR](../features/002-pull-requests.md)

## Contract and plan

Update responses must include the original author and creation timestamp, even
for no-op updates, following the stable ID through directory renames. Extract
listing's first-parent history lookup into a shared helper. Resolve metadata
before publishing so lookup failure cannot report failure after a successful
write. No changes to creation responses, merged-status resolution, CLI schema,
dependencies or on-disk format.

Test library responses and CLI JSON with a different updating author/time,
including repeated no-op updates; independently compare creation commit metadata
and verify no-op ref preservation. Test history read failure before publication.
Run Ruff, format, mypy, and relevant Python tests.

## Evidence

2026-11-19, Python 3.12, from `pygc/` with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked`: passed, no dependency changes.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed (15 files).
- `uv run mypy src`: passed (11 source files).
- `uv run pytest -q tests/test_pull_requests.py tests/test_initialization.py`:
  35 passed in 3.31 seconds.
- `git diff --check` from repository root: passed.

Regression tests: `test_update_returns_original_creation_metadata` covers both
library and CLI responses; `test_update_history_failure_does_not_publish`
covers failure before ref mutation.

`timeout 60s uv run pytest -q tests/test_interfaces.py` outside the sandbox:
17 passed in 0.52 seconds, with the existing Starlette/httpx deprecation warning.
The first escalation review timed out before execution; the permitted retry
succeeded. All 52 tests passed across the two runs.

