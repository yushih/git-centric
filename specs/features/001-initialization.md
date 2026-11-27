# INIT: Git-centric initialization

State: implemented baseline; verification results must be recorded per change.

## Intent and non-goals

Inspect whether an existing Git repository contains Git-centric metadata, and
initialize it without disturbing user work. Do not create a Git repository,
overwrite an existing metadata branch, check out metadata, implement pull
requests, or expose initialization over RPC in this feature.

## Public API

```python
is_gc_initialized(directory: str | Path = ".") -> Result[bool]
initialize_gc(directory: str | Path = ".") -> Result[str]
```

Exports are available from `pygc.library` and `pygc`. The initializer's successful
value is the new commit object ID. Failures contain a `FailureReason` and human
readable detail. Public operations convert operational exceptions into values;
interrupts and process termination are not swallowed.

## Requirements

| ID | Observable contract |
| --- | --- |
| INIT-001 | Default to pwd; accept explicit paths, worktree subdirectories, linked worktrees, and bare repositories. A missing path, regular file, or directory outside a repo returns `NOT_A_REPOSITORY`. |
| INIT-002 | Return `Success(True)` only if local branch `__git-centric__` has a root-tree directory named `__git-centric__`. A remote ref, tag, working-tree directory, file, symlink, or submodule does not qualify. Checking does not require `.gitkeep`. |
| INIT-003 | A valid repo without that branch/directory returns `Success(False)`; inspection failures return failure values. Inspection is read-only. |
| INIT-004 | Initialization requires `Success(False)` and rechecks state. Already initialized returns `ALREADY_INITIALIZED`; an existing branch without the directory returns `BRANCH_CONFLICT`, preserving its ref. |
| INIT-005 | Successful initialization creates one parentless commit whose root contains only `__git-centric__/`, containing an empty regular `.gitkeep` file, the initial user public key, the default roles and the creator’s owner membership per [ACCESS](007-access.md). Include byte-for-byte copies of the library’s actions.py and all rule-*.py files under `__git-centric__/access-control/rules/`. Return its object ID. |
| INIT-006 | Preserve HEAD, existing history, index, staged changes, unstaged changes, and untracked files. Do not switch branches or populate metadata in the checkout. |
| INIT-007 | Publish with an atomic create-only ref operation. A concurrent branch creation must cause failure and preserve the competing ref; do not dereference a competing symbolic ref. |
| INIT-008 | Use normal Git identity configuration. Git failures, including missing identity and concurrent publication conflicts, return `GIT_ERROR`; filesystem failures return `IO_ERROR`; other operational failures return `UNEXPECTED_ERROR`. |
| INIT-009 | `gc init` uses pwd; `gc init --repo-dir=<dir>` uses that directory; the option overrides the legacy positional directory. Success prints confirmation and exits 0; failure prints reason/detail to stderr and exits 1. Both top-level help and command help describe the command. |
| INIT-010 | Use GitPython with plumbing; reserved names and modes live in `library/constants.py`. Do not hard-code object-ID length. |

## Implementation decisions

Create objects bottom-up with `hash-object`, `mktree`, and `commit-tree` without
parents, then use an `update-ref --stdin` create transaction with no dereferencing.
This avoids the user's index and working tree. Failed publication may leave
unreachable objects for normal garbage collection; it must not overwrite refs.

An existing malformed branch is a conflict even though inspection returns false:
the initializer creates metadata, it does not repair or replace existing history.
Tests inspect actual repository state using independent Git CLI invocations.

## Acceptance criteria and test map

All listed tests are in `pygc/tests/test_initialization.py`.

| Requirements | Scenario / test |
| --- | --- |
| INIT-001, 003, 005, 006 | Empty repository, pwd defaults, exact orphan tree: `test_empty_repo_and_default_directory` and `assert_initial_commit` |
| INIT-001 | Invalid directory/missing path/file: `test_non_repositories_return_failure` |
| INIT-001 | Subdirectory and bare repo: `test_subdirectory_and_bare_repo` |
| INIT-001, 006 | Linked checkout: `test_linked_worktree` |
| INIT-002, 004 | Absent/file/directory marker in an existing branch: `test_check_looks_at_committed_directory_and_conflicts` |
| INIT-002, 003 | Uncommitted directory: `test_uncommitted_marker_does_not_count` |
| INIT-004 | Repeat initialization preserves ref: `test_repeat_initialization_is_a_failure_without_reset` |
| INIT-005, 006 | Staged, unstaged, and untracked state: `test_dirty_index_and_worktree_are_untouched` |
| INIT-007 | Competing ref publication: `test_concurrent_branch_creation_is_not_overwritten` |
| INIT-008 | Permission error value: `test_io_exceptions_are_returned` |
| INIT-008 | Missing Git identity: `test_missing_identity_does_not_publish_branch` |
| INIT-009 | CLI explicit/default path, stderr, status, help: `test_cli_init_path_default_failure_and_help` |
| INIT-010 | Review GitPython plumbing and constants imports; inspect SHA-1/SHA-256 behavior when changing plumbing. |

Coverage gaps to retain explicitly: dedicated tag/remote-ref, symlink/submodule,
symbolic-ref race, corrupt-object, and automated SHA-256 cases are not currently
present. The implementation intends to support the requirements above; this map
does not claim exhaustive coverage or a verified test run. Add targeted cases
when working on those behaviors.

Shared selection and warning semantics: [DIR](../changes/2026-11-19-repo-directory.md).
