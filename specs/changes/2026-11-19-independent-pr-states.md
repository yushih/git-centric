# Independent PR states

State: verified
Related spec: [PR](../features/002-pull-requests.md)

## Contract and plan

Replace exclusive status with independent boolean draft, closed, merged fields
in the public record and JSON (intentional API change). All eight combinations
are valid. Persist draft/closed as optional [closed][draft] prefixes; read legacy
single flags and combined flags in either order, rejecting duplicates. Derive
merged from ancestry for every PR, including create/update/list responses;
missing branches retain the existing false fallback. No manual merged toggle.

Draft/ready modify only draft; close/reopen modify only closed. Permit actions
across axes; reject contradictory actions within an axis. Keep the legacy open
filter as !draft && !closed && !merged. Preserve author/time and atomic writes.

Implement shared ancestry resolution before publication, update specs/docs/help,
and test all eight states, CLI transitions and contradictions, legacy/combined
prefix parsing, response consistency and branch movement. Run locked sync,
Ruff, mypy, Python tests, and whitespace checks. No dependencies/layout changes.

## Evidence

2026-11-19, Python 3.12, `pygc/`, with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked`: passed; no dependency changes.
- `uv run ruff check .`: passed.
- `uv run mypy src`: passed, 11 source files.
- `uv run pytest -q tests/test_pull_requests.py tests/test_initialization.py`:
  51 passed in 6.22 seconds.
- `git diff --check` from repository root: passed.

Acceptance: test_independent_states covers all eight combinations and single-axis
transitions; test_state_cli_and_conflicts covers JSON, combined actions and
contradictions; test_state_prefix_compatibility and test_duplicate_flags_rejected
cover format compatibility; test_merged_create_and_branch_change covers ancestry
in write responses and no-op updates. Existing tests retain author/history,
comment preservation and concurrent publication coverage.

`uv run ruff format --check .`: passed, 15 files.
`timeout 60s uv run pytest -q tests/test_interfaces.py` outside the sandbox:
17 passed in 0.51 seconds with the existing Starlette/httpx deprecation warning.
Automatic approval review timed out before the first run; the retry succeeded.
All 68 tests passed across the two runs. No frontend or packaging changes.

