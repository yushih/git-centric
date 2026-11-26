# Web permission previews

Implement the read RPC using the existing checker, validate correlated decision
counts in the client, and gate only controls with known actions. Cover direct
links, individual node rows, late or failed requests, and denied writes after a
preview. Verify the frontend build, Python regression tests, and installed UI.

Verified on Linux, Python 3.12 and Node 26. In pygc, Ruff lint/format and mypy
passed, and uv run pytest -q passed 157 tests with one Starlette deprecation
warning. In pygc/frontend, npm test passed 11 tests and npm run build passed.
Built and installed the wheel into an isolated environment. Chromium with a
selectively denying checker verified disabled issue creation including direct
links, replies, role creation, independent node row decisions, preview retry,
navigation during a pending request, and draft retention for input-dependent
and late write denials. Denied operations triggered zero finalization requests.
