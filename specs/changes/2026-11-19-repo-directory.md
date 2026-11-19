# CLI repository selection

State: verified

## Contract

- DIR-001: Every leaf command accepts `--repo-dir PATH` (also `--repo-dir=PATH`).
  Repository operations default to the current directory and pass the selected
  directory explicitly to the library, without changing process cwd.
  Help and web accept the option but have no repository-backed operations.
- DIR-002: An explicit option always wins. If `is_gc_initialized` returns
  `Success(True)` for both cwd and the selected directory and they refer to
  different repositories, emit one warning on stderr identifying the override.
  Compare resolved Git common directories: subdirectories, symlink aliases and
  linked worktrees sharing metadata are the same repository. Separate clones differ.
- DIR-003: Advisory inspection failures do not block explicit selection or fall
  back to cwd. The selected operation reports its usual errors and exit status.
  JSON stdout stays clean. No warning if either location is not initialized.
- DIR-004: Preserve legacy `gc init [directory]`; `--repo-dir` overrides this
  positional argument too. With no option, the positional path keeps its old meaning.
  Existing library, RPC, web server behavior and dependency locks stay unchanged.

## Plan and acceptance

1. Add one shared option type and selection helper; wire every CLI leaf command.
2. Update CLI help, README, architecture and initialization/PR contracts.
3. Test all repository commands against a second repo, cwd preservation, warning
   conditions, alias/worktree identity, invalid explicit paths, init compatibility,
   and nonrepository commands. Run locked sync, Ruff, mypy and Python tests.

## Evidence

2026-11-19, Python 3.12, commands from `pygc/` with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked`: passed; manifests and locks unchanged.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed (16 files).
- `uv run mypy src`: passed (11 files).
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_repo_directory.py tests/test_pull_requests.py tests/test_initialization.py`:
  63 passed in 7.92s.
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_interfaces.py`, outside the sandbox because of the previously
  established test-client stall: 17 passed in 0.57s, one existing Starlette/httpx
  deprecation warning.
- `git diff --check`: passed.

DIR-001/002 are covered by `test_all_repo_commands_use_override` and
`test_same_repository_has_no_warning` (four path variants). DIR-003 is covered
by `test_uninitialized_and_invalid_locations`; DIR-004 by
`test_init_option_overrides_legacy_directory` and `test_non_repo_commands_and_help`.
Existing tests retain default-cwd and legacy initialization coverage. All 80
Python tests passed across targeted runs. No frontend or packaging changes.
