# Background finalization for web actions

Each successful browser metadata action (initialization, issue/PR writes and
comment writes) independently submits an empty POST /api/finalization.
RPC handlers return their ordinary result as soon as the action completes.
Reads, page loads, failed saves and polling do not schedule work.

POST applies the RPC write access guard, takes no repository path, and returns
202 with a status snapshot immediately. GET /api/finalization returns 200 with
the same shape and performs no Git work. Both disable HTTP caching. State is
idle, running, finalized, not_finalized, conflict or failed, with a pending
boolean, optional completed tip, warnings array and optional error reason.
Status describes web rounds since this server started. One worker per app runs
the synchronous library operation off the event loop. During a round, multiple
triggers coalesce into one subsequent round. A failed round also drains pending
work. Shutdown waits for accepted work.

Mount the status section in the common repository header. Poll once per second
after each response, cancel on unmount and present polling and scheduling errors
separately from save results. Preserve the header across route changes.

## Plan and validation

Implement a process-local coordinator and HTTP handlers, connect the shared save
path and app header, then test blocked-worker responsiveness, serialized follow-up
work, failures, access checks, frontend rendering and production asset packaging.

## Verification

2026-11-25–26, Python 3.12.3, Node 26.8.1. From pygc/, Ruff lint and format
checks and mypy passed. `uv run pytest -q` passed 147 tests with one existing
TestClient deprecation warning. From frontend/, `npm test` passed eight tests
and `npm run build` passed TypeScript and produced the SPA.

Built the sdist and wheel with `uv build --offline` using a temporary copy of
the populated build cache. PyPI DNS failed during isolated dependency
installation, so installed the wheel into a fresh venv and copied its runtime
dependencies from the locked development environment. Verified its import path,
CLI and packaged assets. Headless Chromium on a 390px viewport confirmed the
header across tabs, exactly one trigger each after initialization and issue
creation, draft preservation across two polls, and the new issue commit in the
status section. Browser iteration removed an unnecessary save callback from
the data-loading effect dependencies and scoped form interaction to the
new-issue page.
