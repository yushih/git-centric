# PR merge analysis and changed files

State: verified

## Contract and plan

Extend PullRequestDetails and `gc pr show` JSON with `merge_conflicts` (boolean
or null), `changed_files` (array of change records or null), and
`merge_analysis_error` (null, or an explanation when branches are missing or
histories unrelated). Text mode displays conflict yes/no/unknown, changed files
or unavailable, and the explanation. Existing PR/comments output remains intact.

Changed files are the compare branch's changes since its merge base with base,
not base-only changes. Each record has `status` (added, modified, deleted,
renamed, copied, type_changed, unmerged, unknown, or broken), `path` (destination
for rename/copy), `old_path` (source for rename/copy, otherwise null), and
`similarity` (Git's percent score for rename/copy, otherwise null). Use Git's
rename/copy detection, including unchanged copy sources; detection is heuristic.
`conflicting_files` contains Git's conflicted paths, deduplicated, or [] for a
clean merge, or null when analysis is unavailable. Text mode labels change types,
shows rename/copy arrows and similarity, and lists conflicting paths. NUL-delimited Git output preserves spaces,
Unicode and newlines; text mode quotes paths with JSON escaping. No changes is [].
Capture branch OIDs once for merged status, diff, and merge simulation. Git's
`merge-tree --write-tree` simulates compare into base: exit 0 means clean, exit 1
means conflicts; other failures return normal git_error, not a false clean result.
Requires Git supporting this mode (2.38+); no checkout, index, refs or working
files are modified. Simulation may create unreachable objects for normal Git GC.
Missing branches/unrelated histories leave both analyses null, retaining details.

Implement analysis in the domain snapshot read and rendering in the CLI. Update
help/docs/spec. Test clean/conflicting/deleted/renamed paths, base-only changes,
missing/unrelated branches, operational failures, branch movement, dirty state
and bare repositories. Run locked sync, Ruff, mypy and relevant Python tests.

## Evidence

2026-11-19, Python 3.12 and Git 2.43.0, from `pygc/`, with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked`: passed; no dependency changes.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed (16 files).
- `uv run mypy src`: passed (11 files).
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_pull_requests.py tests/test_repo_directory.py tests/test_initialization.py`:
  76 passed in 10.33s.
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_interfaces.py`: 17 passed in 0.62s outside the sandbox to avoid the
  established test-client stall. The first automatic review timed out before
  launch; the permitted retry succeeded. Existing Starlette/httpx warning.
- `git diff --check`: passed.

`test_show_merge_analysis_preserves_checkout` covers clean and conflicting
merges, path changes/escaping, base-only exclusion, both CLI formats and actual
index/working-file/ref preservation. `test_show_merge_analysis_unavailable_and_bare`
covers missing/unrelated branches and bare repositories.
`test_show_merge_analysis_errors_and_captured_tips` checks operational failures,
branch movement and already-merged results. Existing show tests cover empty diffs.
All 93 Python tests passed across targeted runs. No unresolved verification.

## Expanded file details (follow-up)

User requested conflict paths and per-file change kinds before committing the
initial implementation. Replace the initial path-only changed_files format.
Read NUL-delimited merge-tree output with --name-only --no-messages, retaining
stdout on exit 1 through GitPython. No parsing of human conflict diagnostics.
Validate actual add/add and modify/delete conflicts, renames/copies/type changes,
and filenames containing tabs/newlines. Preserve previous state-safety tests.

Follow-up verification, same environment, from `pygc/`:

- `uv sync --locked`: passed, unchanged locks.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`: passed.
  Initial mypy findings in plumbing-output types were corrected before testing.
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_pull_requests.py tests/test_repo_directory.py tests/test_initialization.py`:
  80 passed in 11.28s before the final empty-conflict-list text clarification;
  targeted follow-up: `uv run pytest -q tests/test_pull_requests.py -k
  'conflict_status_without_unmerged_paths or merge_analysis or show_copy or show_conflict_file_names'`
  passed (8 tests, 48 deselected in 1.63s).
- `git diff --check`: passed.

Added `test_show_copy_and_type_changes`, `test_show_conflict_file_names` (two
conflict kinds), and `test_show_conflict_status_without_unmerged_paths`.
Updated existing tests verify exact changed-file records and conflict paths in
both outputs, captured merge tips and preserved checkout state. Structural
conflicts can have no unmerged paths: retain Git's conflict exit status and
explicitly say no file paths were reported in text mode. No interface/RPC or
frontend changes in this follow-up. No unresolved verification.
