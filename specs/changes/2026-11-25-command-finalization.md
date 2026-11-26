# Finalization after CLI commands

All successful CLI leaf commands, including reads, finalize the selected
repository once. A failed command or an eager help/usage display does not start
a round. The explicit help command and web launcher participate when the
selected repository has metadata. Web performs this step before serving.
Accept -do-not-finalize or --do-not-finalize before the command or on the leaf.
With either spelling, record the exact “not finalized” Git note on the local
metadata tip without contacting peers. Preserve existing notes and make repeats
idempotent. Ordinary command stdout retains its existing format. Finalization
warnings go to stderr and failures exit 1. A failure after a local write leaves
that write in place. Library and RPC calls do not trigger CLI completion.

## Plan

Share one completion routine across command adapters. Reuse the transactional
note writer independently of registry parsing. Cover flags, reads, writes,
failure paths and single-round dispatch with temporary repositories and run the
Python checks.

## Verification

Verified 2026-11-25 with Python 3.12.3 and Git 2.43.0. From pygc/,
`uv run pytest -q` passed all 143 tests with one existing TestClient deprecation
warning. The new cases in tests/test_consensus.py exercise default push on
write and read, both flag spellings, note preservation, failed commands,
exactly one invocation, web startup ordering and finalization failure after a
local commit. Repository-selection tests cover the revised stderr contract.
`.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`,
`.venv/bin/mypy src` and `git diff --check` passed.
