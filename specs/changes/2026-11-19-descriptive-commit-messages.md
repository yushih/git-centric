# Descriptive metadata commit messages

State: verified

## Contract and plan

Every application-generated Git commit must identify the concrete action and
its target. Never use a generic update message when the actual changes are known.
Future writers must follow this rule; existing history is not rewritten.

- Initialization: `initialize Git-centric metadata`.
- Creation: `create pr ID: TITLE`, with JSON-quoted title for safe one-line text.
- PR updates: describe only actual changes, in closed/draft/title/compare/base
  order, joined with `; `. Actions are `close pr ID`, `reopen pr ID`,
  `mark pr ID draft`, `mark pr ID ready`, and `set pr ID FIELD to VALUE`.
  String values are JSON quoted, preserving Unicode and escaping newlines.
  Multiple changes all appear; redundant tokens are omitted; no-op updates
  continue to make no commit. Merged state is computed and is not a stored action.
- Comments: `add comment CID on pr PID`, optionally ` replying to ID, ID`;
  `update comment CID text on pr PID`; `delete comment CID on pr PID`.
  Comment text is not duplicated into commit messages.

Keep Result, concurrency, trees, refs, command help and APIs unchanged.
Implement action summaries from before/after records, update the architecture
and contributor rule, then test actual Git messages for all writes, combined
and redundant changes, safe text escaping and no-ops. Run locked sync, Ruff,
mypy, initialization and PR tests.

## Evidence

2026-11-19, Python 3.12, from `pygc/`, with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked`: passed; dependencies unchanged.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed, 16 files.
- `uv run mypy src`: passed, 11 files.
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_pull_requests.py tests/test_initialization.py tests/test_repo_directory.py`:
  67 passed in 9.30s.
- `git diff --check`: passed.

`test_descriptive_pr_commit_messages` verifies initialization, creation, all
state/field updates, combined changes, omitted redundant tokens, escaping and
no-op ref preservation. `test_descriptive_comment_commit_messages` verifies
add/reply, update (including main), delete and no-op messages with independent
Git reads. Existing tests cover concurrency and checkout preservation.
No interface, RPC, frontend or packaging changes; no unresolved verification.
