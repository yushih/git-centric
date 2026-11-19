# pygc

Python skeleton for Git-centric: a reusable library, a `gc` CLI, and a React SPA
calling the same library over JSON-RPC 2.0 through FastAPI. The example operation
is `greet`; Git repository operations are intentionally left for future implementation.

## Requirements and setup

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 22.12+ and npm

Run from this directory:

```sh
uv sync
cd frontend
npm ci
npm run build
cd ..
uv run gc help
uv run gc greet Ada
uv run gc web
```

Open http://127.0.0.1:8000. `gc web` serves both the built frontend and `/api/rpc`.
Use `uv run gc web --host 127.0.0.1 --port 9000` to change the binding.
The server defaults to localhost; authentication and remote deployment are outside
this skeleton's scope.

`uv run` makes the installed `gc` entry point available without activating a venv.
Alternatively, activate `.venv` and use `gc` directly. `python -m pygc` also works.

## Development

Run these in two terminals, both starting in `pygc/`:

```sh
uv run gc web --reload
```

```sh
cd frontend
npm run dev
```

Open http://localhost:5173. Vite provides hot reload and proxies `/api` to
http://127.0.0.1:8000. Update `frontend/vite.config.ts` if the backend port changes.
No cross-origin configuration is needed. Without a frontend build, the backend's
root page shows setup instructions; the API still works.

## Library and RPC

```python
from pygc import greet

print(greet("Ada"))
```

```sh
curl http://127.0.0.1:8000/api/rpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"greet","params":{"name":"Ada"},"id":1}'
```

Result: `{"jsonrpc":"2.0","result":"Hello, Ada!","id":1}`.

The adapter follows the [JSON-RPC 2.0 specification](https://www.jsonrpc.org/specification):
named/positional parameters, batch calls, notifications (HTTP 204), and standard
error codes. RPC responses, including protocol errors, use HTTP 200. Pydantic
validates arguments strictly. Library `ValueError` exceptions become invalid-params
errors; unexpected exceptions are logged and returned as generic internal errors.

## Layout and extension

```text
src/
  library/         Transport-independent functions (public API in __init__.py)
  cli.py           Typer commands and gc web launcher
  rpc.py           Explicit method registry and protocol adapter
  web.py           FastAPI app factory and static hosting
  static/          Generated frontend assets, included in wheels
frontend/
  src/rpc.ts       Typed JSON-RPC client and runtime response validation
  src/main.tsx     React interface
  vite.config.ts   Builder and development proxy
tests/             Library, CLI, server, and protocol tests
```

To add an operation, implement it in `src/library/`, export it in `src/__init__.py`, add
a Typer command, register a validated callable in `rpc.METHODS`, and extend the
TypeScript `Methods` contract, response validation, and React interface.
The setuptools build configuration maps `src/` to the installed `pygc` package, so imports
remain `from pygc import greet`. Editable installs use the same mapping.

Only explicitly registered functions are callable through RPC. Synchronous
library calls run in a worker thread, keeping the server event loop available.

## Checks and packaging

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
cd frontend
npm test
npm run build
cd ..
uv build
```

Build the frontend before `uv build` to include the SPA in the wheel. Generated
assets are ignored by Git. `package-lock.json` pins frontend dependencies. The first
`uv sync` generates `uv.lock`; commit that file, then use `uv sync --locked` and
`npm ci` for reproducible installs.
