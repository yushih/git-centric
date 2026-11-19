# Comment text updates and deletion

State: verified
Related spec: [PR](../features/002-pull-requests.md)

## Contract and decisions

- EDIT-001: Synchronous `update_comment(target, text, directory=".")` and
  `gc comment update PR_ID:COMMENT_ID TEXT` replace text verbatim, including empty
  text and CLI @- stdin. Return the updated Comment; preserve ID and reply links.
  Identical text is a successful no-op without a commit.
- EDIT-002: `delete_comment(target, directory=".")` and
  `gc comment delete PR_ID:COMMENT_ID` return the removed Comment. Remove its
  blob and links to its ID from surviving replies, preserving their text and IDs.
  Reject deletion of main with invalid_argument: it is the required description;
  update it to empty text to clear it. Previous text remains in Git history.
- EDIT-003: Require exactly one PR ID and one comment ID. Malformed targets return
  invalid_argument; missing targets not_found; corrupt conversations invalid_metadata.
  No author restriction is introduced in this local repository API.
- EDIT-004: Reuse atomic publication and failure boundaries. Preserve HEAD, index,
  working files, unrelated blobs and history. Concurrent writes fail with git_error.
  Both commands emit JSON and failures exit 1; arity errors exit 2. No RPC/UI changes.

## Plan and validation

1. Update PR contract; implement library exports and CLI commands.
2. Test exact text, no-ops, deletion with replies, main protection, invalid targets,
   corruption, dirty checkout preservation and concurrent writes using real Git.
3. Update usage/help; run locked sync, Ruff, mypy and Python tests with timeouts.
   No dependency, packaging or frontend changes.

## Evidence

2026-11-19, Python 3.12; commands from `pygc/` with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked --project pygc` from repository root: passed, locks unchanged.
- `uv run ruff check .`: passed after fixing import order and formatting.
- `uv run ruff format --check .`: passed (15 files).
- `uv run mypy src`: passed (11 files), after annotating the raising helper
  with NoReturn so type narrowing reflects its actual behavior.
- `uv run pytest -q tests/test_pull_requests.py tests/test_initialization.py`:
  55 passed in 7.13s.
- `timeout 30s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_interfaces.py`: sandbox run stalled after two tests and timed out
  (exit 124); this was not a pass.
- Same interface suite with a 60s timeout outside the sandbox: 17 passed in
  0.57s, one existing Starlette/httpx deprecation warning.
- `git diff --check`: passed.

Acceptance mapping: EDIT-001/002/004 are covered by
`test_edit_delete_comments_preserve_state`; EDIT-001/002/003 CLI behavior by
`test_comment_edit_cli_and_errors`; EDIT-004 races by
`test_comment_edit_concurrent_publication` (update and delete). Existing
`test_corrupt_comments_are_metadata_failures` now exercises both new writers.
All 72 Python tests passed across targeted runs. No unresolved verification.
