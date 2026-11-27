# Restart finalization after reconciliation

Implement FIN-001 by passing the selected branch ref through transport, local
publication, notes and stale checks. Keep a single registry snapshot and tally
each candidate independently. Validate with real bare peers, a non-metadata
branch, stale-vote and state-preservation checks, then run Python checks.

On 2026-11-27, all 10 consensus tests passed. The sandboxed full suite
stalled at the first HTTP RPC test. Running `uv run pytest -q` outside
the sandbox passed all 160 tests with one TestClient deprecation warning.
Ruff lint and formatting passed on all changed Python files. Repository-wide
Ruff and mypy reported existing issues only in `rules-merger-can-merge.py`.
Mypy passed across src when excluding that file.
