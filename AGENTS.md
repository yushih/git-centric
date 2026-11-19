# Agent guidance

## Read first

- Read [specs/README.md](specs/README.md) for the spec-driven development (SDD)
  workflow and feature index, then the spec relevant to the task.
- Read [specs/architecture.md](specs/architecture.md) for the implementation
  boundaries and [pygc/README.md](pygc/README.md) for setup and usage.
- Inspect the current code, tests, manifests, lockfiles, and working tree before
  editing. Session history is context, not proof of the current state.
- The root README describes the broader product vision. Its Bash-layer language,
  pull-request commands, and gossip protocol are not evidence of implemented
  Python features. Do not implement roadmap items as incidental scope.

## Working method

1. Identify the requested behavior and relevant spec. For a behavior change,
   create or update its spec before implementation: inputs, outputs, errors,
   invariants, non-goals, and acceptance criteria.
2. Record a short implementation plan and validation plan in the change record
   described in `specs/README.md`. Keep routine edits lightweight.
3. Implement the smallest complete change. Keep specification, code, tests,
   command help, and user documentation consistent.
4. Run the checks appropriate to the affected layers. Record actual results,
   including failures and checks that could not run; do not equate a build or
   smoke check with an integration-test pass.
5. Report the outcome, validation, and any unresolved work.

Explicit current user instructions take precedence over these repository
conventions. Update the spec when the user changes a requirement. If code and
spec disagree, identify the mismatch rather than silently treating code as the
intended contract. Resolve ordinary implementation choices autonomously; ask
only about consequential ambiguity that cannot be settled from the request and
repository. This workflow does not introduce a separate approval gate.

Preserve unrelated user edits. Do not commit, push, publish, or modify the user's
Git configuration unless requested. Do not use this checkout as a scratch repo
for initialization tests. Do not introduce agent frameworks or tool-specific
configuration merely to follow this workflow.

## Code conventions established for this project

- Keep the flattened layout: Python package contents are directly in `pygc/src/`.
  Do not recreate `pygc/src/pygc/`. Setuptools maps `src/` to import package `pygc`.
- Domain code belongs in `pygc/src/library/`. `library` is a package, not a
  `library.py` module. Export public functions through its `__init__.py` and
  `src/__init__.py` as appropriate.
- Put reserved names, file names, branch/ref names, and on-disk format constants
  in `pygc/src/library/constants.py`; import them instead of duplicating literals.
- Use GitPython for application Git access and prefer Git plumbing for metadata
  operations. Pass argument lists, not shell-interpolated commands.
- Public Git-centric library operations return `Result[T]`, with `Success(value)`
  or `Failure(reason, detail)`. Operational failures must not escape as exceptions.
  Keep failure reasons stable; do not swallow interrupts or process termination.
  The existing `greet` demo predates this convention and is not a model for new
  domain APIs.
- Keep CLI, HTTP, and React concerns out of the library. Adapters translate domain
  results into their interface's documented representation.
- Use clear type annotations and extensive explanatory comments. Explain intent,
  preconditions, non-obvious Git semantics, concurrency, and state preservation.
  Comment each test's scenario and expected outcome, plus non-obvious fixtures,
  mocks, and assertions. Keep comments accurate when behavior changes.
- Update `gc help` and relevant command help when adding or changing CLI commands.
- Use explicit JSON-RPC method registration. A new library function is not
  automatically a public RPC method. Specify exposure and wire format first.

## Verification

From `pygc/`, install with `uv sync --locked`; from `pygc/frontend/`, use `npm ci`.
Use Python 3.12+ and Node satisfying `frontend/package.json` (currently 22.12+).
For deliberate dependency changes, update the manifest and lockfile together
using the package manager; never invent lockfile entries.

Run relevant checks from `pygc/`:

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest tests/test_initialization.py
uv run pytest tests/test_interfaces.py
```

For frontend changes, run from `pygc/frontend/`:

```sh
npm test
npm run build
```

For package-layout or asset changes, build the frontend first, then run `uv build`
from `pygc/`. Verify the resulting wheel imports, CLI entry point, and packaged
static files from an isolated installation, not only the editable checkout.

Use temporary repositories and isolated Git identity/configuration in tests.
Verify actual refs, parent lists, trees, index contents, and working files with
independent Git commands. Include failure and concurrency cases for writes.
Never reset or overwrite an existing metadata branch to make a test pass.

Documentation/comment-only changes need relevant formatting/link checks, not a
mandatory full integration suite. For missing dependencies, blocked network
access, or stalled tests, report the exact limitation and stop stalled processes.
Do not weaken tests or claim success to work around an environment problem.

## Completion

A behavior change is verified when its acceptance criteria are covered, relevant
checks pass, and specs, help, docs, and dependency locks agree with the result.
If verification is blocked, describe the implementation as awaiting verification
and record what remains. Temporary local failures are not permanent project rules.

## Commit messages

Every application-generated metadata commit must name its concrete action and
target. Describe actual state/field changes (all of them for combined updates),
not generic "Update pull request" messages. Escape free text to keep subjects
on one line; do not create commits for no-op updates. Source-code commits must
also describe the concrete change. Follow specs/architecture.md and its message
contract when adding new writers.
