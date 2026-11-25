# 006 Consensus finalization

State: verified

Implement the README consensus procedure through a synchronous Python operation
and `gc consensus finalize [--repo-dir PATH]`. Automatic triggers, PR merging,
and RPC exposure are outside this command.

- FIN-001. Snapshot the metadata tip and sorted registry once. Push only the
  candidate metadata commit to each configured node. Count an accepted push
  as success. After a non-fast-forward rejection, fetch the remote metadata
  and reconcile locally. A clean merge counts as success immediately. Subsequent
  nodes receive the resulting tip. A merge conflict counts as conflict. Other
  transport failures warn and contribute no vote.
- FIN-002. A strict majority of all configured nodes must succeed for finality.
  Refresh each conflicting peer's metadata tip, append a standard Git note
  naming the successful nodes and push its notes ref. Preserve other notes.
  Failure to notify one peer warns and processing continues.
- FIN-003. A strict conflict majority fails with conflict_change. Otherwise,
  including ties and zero nodes, append “not finalized” to the local candidate
  and warn “no finality”. This warning exits 0. List node warnings on stderr.
- FIN-004. Preserve checkout, index, unrelated refs and notes. A competing local
  metadata write invalidates the candidate. Remote updates use normal
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
