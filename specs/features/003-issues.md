# ISSUE: Issues and conversations

State: verified.

## Problem and scope

Track repository work independently of branches, using the same local Git metadata
history as pull requests. First release: Python library and CLI, issue creation,
listing, inspection, title/state updates, and threaded comments.

Scope excludes labels, assignees, milestones, priority, attachments,
issue deletion, PR links/automatic closing, sequential issue numbers, RPC, UI,
authentication, remote synchronization, and gossip. These can be designed later.
Closing is reversible; it does not remove the issue or prevent conversation.

## Data fields

| Field | Type / default | Source and meaning |
| --- | --- | --- |
| `id` | Immutable string | `generate_id("issue")`: random UUID hex, consistent with existing IDs; no central counter |
| `title` | Nonblank string, required | Stored in directory name; preserve supplied text |
| `closed` | Boolean, initially false | Stored directory prefix; open means `closed == false` |
| `author` | `Name <email>` string | Author of the creation commit, resolved by stable issue ID along first-parent history |
| `created_at` | ISO 8601 timestamp with offset | Creation commit author timestamp, as for PRs |

The description is the required `main` comment, not a second mutable copy in the
issue record. It defaults to empty and preserves UTF-8 text verbatim. Comment
records reuse `{id, text, replies_to}`; `replies_to` is an ordered list of comment
IDs in the same issue. New comments receive random IDs; `main` is reserved.
No branch, draft, merged, or computed merge-analysis fields apply to issues.
No `updated_at` in the first version: later design should settle whether comment
activity counts as an issue update before adding that field.

## Storage

Use the existing local `refs/heads/__git-centric__` branch. Its committed tree:

```text
__git-centric__/
  .gitkeep
  pull-requests/                         # existing format unchanged
  issues/
    ISSUE_ID:Encoded%20title/            # open
      comment-main                      # UTF-8 description blob
      comment-COMMENT_ID                 # root comment
      comment-REPLY_ID:main:COMMENT_ID    # reply to existing comments
    [closed]OTHER_ID:Another%20title/     # closed
      comment-main
```

The literal IDs above are placeholders. Reuse the existing percent encoding for
titles, including separators, slashes, percent signs, and whitespace. IDs follow
existing `[A-Za-z0-9_-]+` validation. Titles and state changes rename the directory;
history lookup follows immutable IDs rather than paths. This deliberately follows
the PR format instead of introducing a database or a second JSON metadata format.
The tradeoff is history traversal for creator information and renames on edits.

An absent `issues/` subtree means an empty list; create it lazily on the first
issue. Existing initialized repositories need no migration or reinitialization.
Duplicate issue IDs, invalid names/modes, missing `main`, invalid UTF-8, duplicate
comment IDs, dangling replies, or reply cycles are `invalid_metadata`. Issue and
PR IDs occupy separate namespaces; an identical ID in each is valid.

Read each operation from one captured metadata commit. Build blobs and trees with
GitPython plumbing, then publish one commit with that captured commit as its sole
parent using compare-and-swap. A racing PR, issue, or comment writer causes the
loser to return `git_error`; never overwrite the winner or retry stale state.
Preserve HEAD, index, worktree, unrelated subtrees, and existing history. Failed
publication may leave unreachable objects. No-op updates create no commit.

Commit subjects identify every actual change and target, for example
`create issue ID title="Fix login"`, `close issue ID`, or
`update issue ID title="Revised title"; close issue ID`. Escape free text onto one
line. Comment messages name the comment and issue; deletions also describe reply
link removals when applicable. All writes use configured Git identity. As with
PRs, any local author may edit; identity metadata is not authorization.

## Commands and outputs

```sh
gc issue new "Fix login" ["Description"]
gc issue new "Fix login" @-                 # description from stdin
gc issue list                              # all issues
gc issue list open mine 'title=login.*'
gc issue list closed 'author=name@example.com'
gc issue show ISSUE_ID                      # JSON: {"issue": {...}, "comments": [...]}
gc issue show ISSUE_ID --text               # details and indented conversation
gc issue update ISSUE_ID 'title=Better title'
gc issue update ISSUE_ID close
gc issue update ISSUE_ID reopen 'title=Investigate again'
gc issue comments ISSUE_ID

gc issue comment add ISSUE_ID "More detail"
gc issue comment add ISSUE_ID:main "Reply to description"
gc issue comment add ISSUE_ID:COMMENT_ID @-
gc issue comment update ISSUE_ID:main "Revised description"
gc issue comment delete ISSUE_ID:COMMENT_ID
```

All leaf commands support existing `--repo-dir PATH` selection and warnings.
New/update return the full issue record; list returns issue records, ordered by
ID; comments returns full comment records with `main` first, then ID order.
Show reads the issue and conversation together and reuses PR text rendering
semantics without merge analysis. JSON is default; successes exit 0, domain
failures print reason/detail to stderr and exit 1, CLI arity errors exit 2.
`gc help`, group help, and command help must explain the new forms.

Filters are ANDed: `open`, `closed`, `mine`, `author=NAME_OR_EMAIL`,
`title=REGEX`. Full Git identities also match `author=`; `mine` uses current Git
author email. Reject unknown/repeated filters, invalid regexes, and open+closed.
Updates accept only `title=`, `close`, `reopen`; require at least one token and
reject duplicates, contradictory states, and blank titles. Validate all tokens
before writing. Closing an already closed issue is a successful no-op.

Issue comments use `gc issue comment add|update|delete`, keeping existing PR
comment commands unchanged. Add accepts `ISSUE_ID[:REPLY_ID...]`; update/delete
require exactly `ISSUE_ID:COMMENT_ID`. Replies stay within the issue. Deleting a
comment preserves reply bodies and removes incoming links; `main` cannot be
deleted but can be cleared. `@-` retains existing stdin semantics for add/update.
No issue comment shorthand is planned.

## Library and implementation boundaries

Expose async `create_issue(title, comment="", directory=".") -> Result[Issue]`;
synchronous `list_issues(filters=(), directory=".") -> Result[list[Issue]]`,
`update_issue(id, updates, directory=".") -> Result[Issue]`, and
`show_issue(id, directory=".") -> Result[IssueDetails]`.
Add async `add_issue_comment(target, text, directory=".") -> Result[Comment]`,
synchronous `update_issue_comment(target, text, directory=".")` and
`delete_issue_comment(target, directory=".")` returning `Result[Comment]`, and
`list_issue_comments(id, directory=".") -> Result[list[Comment]]`.
Keep existing PR comment APIs unchanged; share their internal primitives.

Shared tree/publication, validation, and conversation decoding live in
`library/metadata.py` and `library/conversations.py`; keep issue rules in `library/issues.py`
and PR branch/merge rules in `pull_requests.py`. Put format constants in
`constants.py`, add the issue ID kind in `ids.py`, and export public records/APIs
through both package initializers. No dependencies, package-layout, RPC registry,
or frontend changes are planned.

Failures reuse `not_a_repository`, `not_initialized`, `invalid_argument`,
`not_found`, `invalid_metadata`, `id_conflict`, `git_error`, `io_error`, and
`unexpected_error`. Invalid caller targets are `invalid_argument`; valid missing
IDs are `not_found`; generated issue/comment collisions are `id_conflict`.
Operational failures return `Failure`; interrupts must propagate.

## Acceptance criteria and validation plan

| ID | Scenario and expected result | Planned coverage |
| --- | --- | --- |
| ISSUE-001 | Create with optional/multiline description; return immutable ID and original creator/time | Issue lifecycle and stdin tests |
| ISSUE-002 | Rename, close, reopen, combine changes, and repeat no-op; preserve creator and comments | State/history tests and exact commit subjects |
| ISSUE-003 | List/filter and show JSON/text consistently from one snapshot; reject invalid tokens | Library and CLI tests |
| ISSUE-004 | Add/reply/edit/delete comments; preserve replies, forbid deleting main, allow discussion when closed | Conversation tests |
| ISSUE-005 | Existing repos list empty then accept first issue; PR metadata/commands still work, including shared IDs across namespaces | Compatibility tests |
| ISSUE-006 | Invalid metadata, missing IDs, generated collisions, Git/IO failures return stable failures without publication | Failure injection and real-tree corruption tests |
| ISSUE-007 | Concurrent issue/PR/comment writes preserve the winner; dirty checkout/index and unrelated refs remain intact | Independent Git inspection of trees, refs, parents, index and files |
| ISSUE-008 | Bare repos, linked worktrees, explicit repository selection, and help behave consistently | CLI/repository tests |

## Implementation tasks

- [x] Inspect current specs, code, tests, manifests, locks, and working tree.
- [x] Record proposed fields, storage, commands, compatibility, and acceptance criteria.
- [x] Implement shared storage/conversation extraction with PR regression coverage.
- [x] Add issue format, domain operations, ID kind, exports, and failure tests.
- [x] Add CLI commands/scoped comment group, help, and usage documentation.
- [x] Add commented issue acceptance tests and mixed-writer concurrency tests.
- [x] Run `uv sync --locked` from `pygc/`, then `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run mypy src`, and `uv run pytest`.
- [x] Record actual results and update feature state only after implementation.

## Verification evidence

2026-11-19: design-only change. Initial working tree was clean. Inspected current
PR and initialization code/tests and Python/frontend manifests and lockfiles.
Architecture's opening paragraph still calls PRs unimplemented; the implemented
PR code and [PR spec](002-pull-requests.md) supersede that stale statement.
During the initial design-only turn, no runtime tests ran. The subsequent
implementation and verification results are recorded below.


### Implementation verification — 2026-11-19

Python 3.12.3. Tests use temporary repositories and isolated Git configuration.
The feature adds no dependencies, frontend assets, RPC exposure, or package-layout
changes. Both root and Python READMEs and CLI help document the implemented forms.
Issue titles require canonical percent encoding; malformed stored escapes fail.
Shared PR tree/publication and conversation decoding were extracted without
changing PR storage or command syntax. Issue writes validate all reply edges for
cycles. Existing PR-specific mutation behavior remains unchanged.

| Command / working directory | Actual result |
| --- | --- |
| `uv sync --locked --project pygc` / root | Initial attempt blocked by read-only default uv cache |
| `UV_CACHE_DIR=/tmp/git-centric-uv-cache uv sync --locked --project pygc` / root | Passed; lockfiles unchanged |
| `UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run ruff check .` / `pygc/` | Passed after correcting initial lint findings |
| `UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run ruff format --check .` / `pygc/` | Passed, 20 files |
| `UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run mypy src` / `pygc/` | Passed, 14 source files |
| `UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest tests/test_initialization.py tests/test_pull_requests.py tests/test_repo_directory.py tests/test_issues.py -q` / `pygc/` | Passed: 106 tests in 15.17s, including 26 issue tests |
| `UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run --project pygc pytest pygc/tests -q` / root | Stalled after 18 tests; interrupted, exit 130 |
| `timeout --signal=INT --kill-after=5s 35s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest tests/test_interfaces.py -vv -o faulthandler_timeout=20` / `pygc/` | First two tests passed; stalled at `test_rpc_success[params0]`, then terminated (exit 137) |
| `git diff --check` / root | Passed |
| Relative Markdown link existence check / root | Passed for changed documentation |

The stalled interface traceback shows Starlette TestClient waiting in AnyIO's
thread portal during the existing greeting RPC test. The sandbox runs were not integration passes; the bounded retry outside the
sandbox passed as recorded below. No tests were weakened.

Acceptance coverage in `pygc/tests/test_issues.py`:

- ISSUE-001/002/007: `test_issue_lifecycle_preserves_git_state`.
- ISSUE-003: `test_issue_filters_and_failures`, `test_invalid_issue_updates`,
  `test_issue_cli`, `test_issue_snapshot_and_comment_collision`.
- ISSUE-004: `test_issue_conversation`, `test_issue_cli`.
- ISSUE-005: lifecycle and namespace-collision coverage in filters/failures;
  existing PR regression tests also pass.
- ISSUE-006: `test_issue_invalid_metadata`, `test_issue_failures_before_publication`,
  `test_issue_snapshot_and_comment_collision`,
  `test_issue_uninitialized_and_missing_identity`.
- ISSUE-007: `test_issue_concurrent_writer` tests racing PR updates against issue
  creation, state changes, comment addition, and comment deletion.
- ISSUE-008: `test_issue_bare_and_linked_worktree`, `test_issue_cli`, plus existing
  repository-selection regressions.


Final interface verification: the first outside-sandbox execution request was
rejected because automatic approval review timed out. The permitted single retry
was approved and ran successfully. From `pygc/`, outside the sandbox:

```sh
timeout --signal=INT --kill-after=5s 35s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest tests/test_interfaces.py -q
```

Result: **17 passed in 0.52s**, exit 0, with one existing Starlette/httpx
`StarletteDeprecationWarning`. Together with the 106-test domain run, all 123
Python tests passed. The sandbox-only stall does not remain a verification block.
No frontend/package-layout/assets changed, so no frontend build or wheel check
was required.
