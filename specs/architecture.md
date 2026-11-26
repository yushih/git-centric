# Implementation architecture

State: current baseline reconstructed from the development session and repository.

## Purpose and scope

Git-centric stores collaboration metadata in Git. The current Python implementation
provides a library, `gc` CLI, and FastAPI-hosted React SPA. Initialization, pull requests, issues, and conversations are exposed through
the library, CLI, and repository web interface. The SPA also browses committed
source, history, and patches through explicit repository-scoped RPC methods. The CLI can explicitly [finalize metadata with registered peers](features/006-finalization.md).
CLI commands finalize by default. Authentication and remote deployment remain outside
the implemented contracts. See the feature specs for domain behavior.

## Layout and dependencies

| Location | Responsibility |
| --- | --- |
| `pygc/src/library/` | Domain operations and public library exports |
| `pygc/src/library/constants.py` | Reserved names and on-disk format constants |
| `pygc/src/library/result.py` | Immutable `Success[T]`, `Failure`, and failure reasons |
| `pygc/src/cli.py` | Typer commands, output/exit translation, Uvicorn launcher |
| `pygc/src/rpc.py` | Explicit JSON-RPC dispatch and argument validation |
| `pygc/src/web.py` | FastAPI application factory and static hosting |
| `pygc/src/static/` | Generated frontend build; included in distributions |
| `pygc/frontend/src/` | React UI and typed TypeScript JSON-RPC client |
| `pygc/tests/` | Library, CLI, protocol, and hosting behavior tests |

The source layout is deliberately flat. Setuptools maps `pygc/src/` to installed
package `pygc`, preserving imports such as `from pygc import initialize_gc`.
Setuptools was chosen because editable installs must support that mapping.
Do not add a redundant `src/pygc/` directory. Keep new subpackages included in the
package configuration; it currently declares packages explicitly.

Python uses uv, GitPython, Typer, Pydantic, FastAPI, and Uvicorn; verification uses
pytest, Ruff, and mypy. The frontend uses React, TypeScript, Vite, and Vitest with
npm. Exact dependencies belong in manifests and lockfiles, not duplicated here.

## Boundaries and results

Domain operations must be callable without running a CLI or web server. Public
Git-centric operations return `Success(value)` or `Failure(reason, detail)`;
callers pattern-match or inspect the variant. `Success(False)` is a successful
inspection, not a failure. The CLI renders results and sets exit codes.

`greet` remains a demonstration returning a string and raising `ValueError` for a
blank name. Its existing RPC mapping is not the wire contract for domain results.
Before exposing a new domain operation over JSON-RPC, specify its serializable
success/failure representation, typed client contract, and UI behavior.

## CLI and web contract

- `gc` is the installed entry point. `gc help` and `gc --help` show commands.
- Every leaf command accepts `--repo-dir PATH`, defaulting to cwd for repository
  operations. Explicit selection wins, warning on stderr when both paths are
  initialized and refer to different Git common directories. See
  [repository selection](changes/2026-11-19-repo-directory.md).
- `gc init [directory] [--repo-dir PATH]` initializes metadata in an existing
  repository; the option overrides the legacy positional directory.
- The greeting demo is available through Python and RPC only; there is no
  `gc greet` command.
- `gc web` launches the app factory with localhost port 8000 defaults; host, port,
  and reload options are available. It serves built assets from `src/static/`.
- Without a frontend build, `/` shows setup instructions while the API remains
  available. Missing assets and unknown API paths return 404; no client-side
  routing fallback is currently promised.
- Vite development serves the SPA separately and proxies `/api` to the backend.
  The production frontend is built before the Python distribution.

JSON-RPC 2.0 uses `POST /api/rpc`, explicit method registration, named or positional
arguments, and strict validation. Calls preserve request IDs; batches omit
notification responses. Notifications return HTTP 204 with no body, including
unknown-method notifications. Empty batches and invalid envelopes are errors.
Protocol responses use HTTP 200 with standard error codes: parse `-32700`, request
`-32600`, method `-32601`, params `-32602`, and internal `-32603`. Unexpected
exceptions are logged without exposing their details in the response.

The client validates the envelope, matching ID, error shape, and result type.
Synchronous library calls execute in a worker thread. Keep library exports separate
from the RPC allowlist; adding an export must not automatically expose it remotely.

## Existing verification map

| Behavior | Evidence source |
| --- | --- |
| CLI help, removed greeting command, and server option forwarding | `pygc/tests/test_interfaces.py` |
| RPC results, validation, notifications, batches, internal errors | `pygc/tests/test_interfaces.py` |
| Missing/build frontend hosting and 404 behavior | `pygc/tests/test_interfaces.py` |
| Browser RPC request/response handling | `pygc/frontend/src/rpc.test.ts` |
| Git initialization and state preservation | [Initialization spec](features/001-initialization.md) |

These are test locations, not a claim that the tests were executed for a given
change. Record execution evidence in that change's verification notes.

## Commit message rule

All generated Git commits must describe the concrete action and identify the
affected entity. PR updates enumerate actual state/field changes, not a generic
"update"; combined operations describe every change and omit unchanged values.
Keep subjects on one line by escaping free text. No-op operations create no
commit. See [message contract](changes/2026-11-19-descriptive-commit-messages.md).
