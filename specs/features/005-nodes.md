# 005 Participating nodes

State: verified

Register and inspect Git endpoints locally in an initialized repository. Network
replication, remote configuration, and RPC exposure are outside this change.

- NODE-001: `gc node add NAME URL` returns a JSON object with name and url.
  Store the literal name as a directory under `__git-centric__/nodes/` on the
  metadata branch and the UTF-8 endpoint in a regular file named `URL`.
  Accept a nonblank printable name excluding slash, backslash, dot, dot-dot
  and case-insensitive .git. Endpoints are nonblank printable strings,
  including local paths and scp-style addresses.
- NODE-002: `gc node list` returns a JSON array sorted by name. An absent
  nodes directory means an empty list. Both commands accept --repo-dir.
- NODE-003: Duplicate names fail with id_conflict. Invalid arguments and
  malformed records fail with invalid_argument and invalid_metadata respectively.
  Existing repository discovery and initialization errors apply.
- NODE-004: Append one metadata commit using compare-and-swap. Preserve
  unrelated trees, the checkout and index. A stale write fails with git_error.

## Implementation and validation plan

Reuse the metadata tree and publication helpers, export synchronous Result APIs,
register the Typer commands and document usage. Exercise add/list, invalid and
duplicate records, checkout preservation and competing writers in temporary Git
repositories. Run Python lint, formatting, type checks and pytest.

## Verification evidence

2026-11-25, from pygc/ with Python 3.12.3 and Git 2.43.0. Locked sync,
`uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy src`
passed. The sandboxed suite stalled at the HTTP tests. The approved rerun of
`uv run pytest -q` passed all 134 tests with one TestClient deprecation warning.
The node cases in `tests/test_nodes.py` cover CLI behavior and Git state
(test_node_commands), corrupt data (test_corrupt_registry) and concurrent
publication (test_node_race).
