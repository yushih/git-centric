# 006 Consensus finalization

State: verified

Implement the README consensus procedure through a synchronous Python operation
and `gc sync push [BRANCH] [--repo-dir PATH]`. CLI commands also follow the [automatic finalization contract](../changes/2026-11-25-command-finalization.md). The explicit command defaults to the working branch, with `gc` as an explicit
alias for metadata. Detached HEAD and bare repositories require a branch argument.
After a successful explicit push, finalize metadata once unless it was the target.
Deferral skips all peer contact and annotates the local metadata tip.

- FIN-001. Snapshot the sorted registry from metadata once. The Python operation
  accepts a local branch name, defaulting to the metadata branch used by the CLI
  and web. Reject invalid or absent targets before contacting peers. Push the
  selected candidate to each node. After a history rejection, fetch the same
  branch and reconcile locally. Whenever reconciliation advances the candidate,
  restart at the first node with fresh votes. Only accepted pushes in the last
  pass count. A conflict counts against that candidate. Transport failures warn.
- FIN-002. A strict majority of all configured nodes must succeed for finality.
  Refresh each conflicting peer's selected branch tip, append a standard Git note
  naming the successful nodes and push its notes ref. Preserve other notes.
  Failure to notify one peer warns and processing continues.
- FIN-003. A strict conflict majority fails with conflict_change. Otherwise,
  including ties and zero nodes, append “not finalized” to the local candidate
  and warn “no finality”. This warning exits 0. List node warnings on stderr.
- FIN-004. Preserve checkout, index, unrelated refs and notes. A competing local
  write to the selected branch invalidates the candidate. Remote updates use normal
  fast-forward protection. Notes should be idempotent for an identical message.
  Failures may leave earlier successful pushes or reconciliations in place.

## Plan and acceptance checks

Reuse node discovery, tree merging and Git plumbing. Separate peer transport,
local reconciliation and outcome handling. Exercise the CLI and library against
temporary bare peers, inspecting refs, merge parents, notes and checkout state.
Run Python lint, formatting, type checking and the test suite.

## Verification evidence

2026-11-25, Python 3.12.3 and Git 2.43.0. From pygc/,
`uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy src`
passed. `uv run pytest -q tests/test_consensus.py` passed all seven cases.
The full `uv run pytest -q` run passed 141 tests with one existing TestClient
deprecation warning. Integration tests use local Git transport and bare peers.

- FIN-001 and FIN-004: test_clean_merge_and_next_push, test_concurrent_local_write.
- FIN-002 and FIN-003: test_conflict_outcomes, test_no_finality_cli.

The [branch and restart change record](../changes/2026-11-27-finalization-restart.md)
covers the revised FIN-001, including a rejected retry on a non-metadata branch
in `test_restart_selected_branch`.
