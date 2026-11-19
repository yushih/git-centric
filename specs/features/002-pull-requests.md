# PR: Pull requests and conversations

State: verified

## Scope and contract

This feature supersedes the pull-request non-goal in the architecture baseline.

Implement the root README's PR library and CLI, without RPC, UI, merging,
comment editing, remote refs, or gossip. All operations use Result values and
require initialized metadata. Expose async create_pull_request and add_comment;
list_pull_requests, update_pull_request, and list_comments are synchronous.
An async generate_id(kind) returns a random UUID string for pull_request/comment.

- PR-001: `gc pr new compare base title [comment]` requires exactly 3 or 4
  arguments. Empty titles fail. An omitted comment creates an empty comment-main.
- PR-002: `gc pr list [filters...]` combines open, mine, author=, compare=,
  base=, title=regex with AND. Author matches name, email, or full identity;
  mine matches Git's current author email. Output includes ID, title, branches,
  author, creation timestamp, and independent draft/closed/merged booleans. Merged means compare is ancestor of base.
- PR-003: `gc pr update id updates...` accepts compare=, base=, title=,
  close/reopen and draft/ready. Reject unknown/duplicate keys and contradictory
  actions within one axis; allow combined actions across axes.
  ready removes draft only; reopen removes closed only. Update results
  include the original author and creation timestamp, including no-op updates.
- PR-004: `gc pr comments id` lists comments; `gc comment pr[:reply-id...] text`
  appends a comment addressing existing comments. @- reads stdin verbatim.
  Malformed stored comment IDs and non-UTF-8 text return invalid_metadata.
  Fixed argument counts reject extra words; variable arguments reject unknown tokens.
- PR-005: Every explicitly supplied branch must be an existing local branch.
  Missing branches during later inspection mean merged cannot be established.
- PR-006: Store directories c~>b#id:title with optional [closed] and [draft] prefixes together,
  and comment-id[:reply-id...] blobs. Percent-encode components (including / and
  delimiters) reversibly. Ordinary names retain the README spelling. Derive author
  and creation time from first-parent Git history by stable PR ID across renames.
- PR-007: Preserve HEAD, index, working files, unrelated metadata and history.
  Build trees directly and publish one-parent commits with compare-and-swap;
  concurrent publication fails without overwriting the winner. Reject malformed
  metadata and generated ID collisions. Never edit existing comments.

Failures: existing repository/Git/IO/unexpected reasons plus invalid_argument,
not_initialized, branch_not_found, not_found, invalid_metadata, id_conflict.
No dependencies change. Public operations catch Exception, not BaseException.

## Plan and validation

1. Add constants, typed records, ID generation, safe metadata tree operations.
2. Implement domain API and strict Typer adapters; update exports and usage.
3. Test lifecycle, filters, ancestry, history, replies, malformed input, branch
   validation, dirty state preservation and concurrent publication with real Git.
4. Run locked sync, Ruff lint/format, mypy, and all Python tests. Record results.
5. Commit only this feature's files; preserve pre-existing README/workflow edits.

## Verification evidence

Acceptance map (in `pygc/tests/test_pull_requests.py`):

| Requirements | Tests |
| --- | --- |
| PR-001, PR-003, PR-004 | test_cli_counts_stdin_and_help; test_optional_comment_and_branch_updates |
| PR-002, PR-005 | test_filters_and_merged; test_bare_deleted_and_unrelated_branches |
| PR-003, PR-004, PR-006, PR-007 | test_lifecycle_history_and_preservation |
| PR-005, PR-007 | test_validation_and_collisions; test_concurrent_publication |
| Preconditions, failures, corruption | test_preconditions; test_operational_failures_and_malformed_metadata |

2026-11-19, Python 3.12: `uv sync --locked --project pygc` passed.
Initial lint found formatting and imported-fixture name warnings; corrected.
From `pygc/`: `uv run ruff check .`, `uv run mypy src`, and
`uv run pytest -q` passed (39 tests before final edge cases). Final checks from `pygc/` all passed:

- `uv run ruff check .`
- `uv run ruff format --check .` (15 files)
- `uv run mypy src` (11 source files)
- `uv run pytest -q` (42 passed in 2.13 seconds)

The test run reports one existing Starlette/httpx deprecation warning.
`git diff --check` passed. No packaging or frontend checks were necessary for
this library/CLI change.
Dependencies, package layout, assets, RPC and frontend are unchanged.

Existing untracked baseline specs and AGENTS.md and the user's root README edits
are deliberately excluded from the feature commit.

All eight draft/closed/merged combinations are supported. Writers order flags
[closed][draft]; readers accept either order and legacy single flags, rejecting
duplicates. Public JSON replaces status with three booleans. Merged is derived
for create/update/list irrespective of draft/closed. The open filter remains
!draft && !closed && !merged. See [state change](../changes/2026-11-19-independent-pr-states.md).
