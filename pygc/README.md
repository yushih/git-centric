# pygc

Git-centric provides a Python library, a CLI, and a local web interface for
browsing source and managing Git-backed issues and pull requests.

## Requirements and setup

- Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js 22.12+ and npm

Run from this directory:

```sh
uv sync --locked
cd frontend
npm ci
npm run build
cd ..
uv run gc help
uv run gc web
```

Open http://127.0.0.1:8000. `gc web` serves both the built frontend and `/api/rpc`.
Use `gc web --repo-dir PATH` to select a repository. Browse commit patches from
History. Open Issues or Pull requests to initialize collaboration, edit records,
and reply to comments. Files changed shows the compare-side changes and conflicts.
If another writer changes metadata, reload the conversation and review your draft.
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

### Initialize a repository

Install/update dependencies with `uv sync` before using the new GitPython API.
Git must be installed and author/committer identity configured as for a normal
commit (for example, `git config user.name` and `git config user.email`).

```sh
gc init              # work on the current directory
gc init --repo-dir=/path/to/repo # work on an existing repository
gc help              # includes init
gc init --help       # describes the optional directory argument
```

Every command accepts `--repo-dir=PATH` (or `--repo-dir PATH`) after the command,
for example `gc pr list --repo-dir=/path/to/repo` and
`gc comment update PR_ID:COMMENT_ID "Text" --repo-dir=/path/to/repo`.
Without it, repository operations use the current directory. If both the current
and selected directories are Git-centric initialized repositories and differ,
a warning is printed to stderr; the explicit option wins. Subdirectories,
symlink aliases and linked worktrees of the same repository do not warn.
An invalid explicit path fails without falling back to the current directory.
The legacy `gc init DIRECTORY` form remains supported; `--repo-dir` overrides it.
`help` and `web` also use the selected repository for finalization.

Use `uv run gc` if the virtual environment is not activated. Initialization
does not create a Git repository: use `git init` first if needed. Worktree
subdirectories, linked worktrees, and bare repositories are accepted.

```python
from pygc import Failure, Success, initialize_gc, is_gc_initialized

match is_gc_initialized():  # optionally pass a path
    case Success(False):
        match initialize_gc():
            case Success(commit_oid):
                print("Created orphan commit", commit_oid)
            case Failure(reason, detail):
                print(reason.value, detail)
    case Success(True):
        print("Already initialized")
    case Failure(reason, detail):
        print(reason.value, detail)
```

Both functions return the algebraic type `Result[T] = Success[T] | Failure`;
operational exceptions become failure values. Inspect `.value` or pattern-match
the variant; the result object itself is not a boolean. `is_gc_initialized`
returns `Success(True)` only when the local `__git-centric__` branch has a
root-level `__git-centric__` **directory in its committed tree**. A file or
symlink with that name, or an uncommitted directory, does not qualify.

`initialize_gc` requires `Success(False)` and rechecks that precondition. It
creates an orphan commit containing only an empty `__git-centric__/.gitkeep`.
GitPython invokes `hash-object`, `mktree`, `commit-tree`, and an atomic
`update-ref` create transaction. HEAD, the index, and worktree files stay intact.
Failed publication can leave unreachable Git objects for garbage collection.

Failure reasons are `not_a_repository`, `already_initialized`, `branch_conflict`
(the reserved branch already exists without the directory), `git_error`
(including missing identity or a concurrent ref creation), `io_error`, and
`unexpected_error`. Existing branches are never overwritten. CLI failures print
the reason and detail to stderr and exit with status 1.

### Participating nodes

After `gc init`, register a Git endpoint and list the repository's nodes:

```sh
gc node add office git@example.org:team/project.git
gc node list
```

Add prints a JSON object with `name` and `url`. Names are unique, and a repeated
name fails without changing its URL. List prints a JSON array ordered by name,
or `[]` for an empty registry. Both commands accept `--repo-dir PATH`.
Registration stores the endpoint locally on the metadata branch under
`__git-centric__/nodes/NAME/URL`. The Python equivalents are `add_node` and
`list_nodes`.

### Finalize metadata

Every successful CLI command, including reads, runs one finalization round in
the selected repository. `gc web` finalizes before starting the server.
Pass `-do-not-finalize` (also `--do-not-finalize`) before the command or on its
leaf to skip peer contact and add the Git note `not finalized` to the current
local metadata tip. Repeating the flag on subsequent invocations preserves
existing annotations without duplicating the note.

```sh
gc issue new "Fix login" -do-not-finalize
gc -do-not-finalize node list
```

Ordinary commands keep their usual stdout and send finalization warnings to stderr.
A finalization failure exits 1 and any completed local write remains in history.
Run `gc consensus finalize` to push the local metadata branch to registered
nodes. Use `--repo-dir PATH` to select the repository. Git 2.38+ supports
checkout-free reconciliation of divergent histories. A clean local merge counts
as a successful vote and subsequent peers receive its tip.

The command prints JSON containing `finalized`, `tip`, `successful`, `conflicts`
and `warnings`. Peer warnings also appear on stderr. A strict majority of
successful nodes finalizes the round and sends conflict notes to dissenting
peers. A strict conflict majority exits 1 with `conflict_change`. Otherwise,
including an empty registry, the command exits 0 with `finalized: false`
and records a local Git note. Inspect it with `git notes show __git-centric__`.
A later run starts from current metadata and can retry incomplete propagation.

### Pull requests and conversations

Run `gc init` first. All supplied branch names must identify existing local
branches, including branches in filters and updates. Quote titles, comments,
and update/filter values containing spaces. Extra positional words are errors.

```sh
gc pr new feature/login main "Add login" "Initial description"
gc pr new feature/login main "Add login"       # optional empty main comment
gc pr new feature/login main "Add login" @-    # read description from stdin
gc pr list open mine 'title=login.*' base=main
gc pr update PR_ID 'title=Revised title' draft
gc pr update PR_ID ready
gc pr update PR_ID compare=another-branch base=main
gc pr update PR_ID close draft  # independent states can be combined
gc pr update PR_ID reopen       # preserves draft state
gc pr show PR_ID         # JSON: pull_request and comments
gc pr show PR_ID --text  # plain text with an indented reply tree
gc pr comments PR_ID
gc pr comments --help  # also shown when called without a PR ID
gc comment PR_ID "Another comment"
gc comment add PR_ID "Another comment"  # explicit form
gc comment PR_ID:main "Reply to the description"
gc comment PR_ID:COMMENT_ID @-
gc comment update PR_ID:COMMENT_ID "Revised text"
gc comment update PR_ID:main @-
gc comment delete PR_ID:COMMENT_ID
```

The `comment` group provides `add`, `update`, and `delete`; `gc comment PR_ID TEXT`
is shorthand for `gc comment add PR_ID TEXT`. Use explicit `add` if a target ID
is one of those action words. `gc comment --help` lists the actions.

`gc pr show PR_ID` returns `{"pull_request": {...}, "comments": [...]}` with
all PR fields and complete comment records, plus `merge_conflicts`, `changed_files`,
`conflicting_files`, and `merge_analysis_error`. Changes are compare-side changes
since the merge base. Each changed-file record has `status`, `path`, `old_path`,
and `similarity`: added/modified/deleted/type_changed files have null old_path
and similarity; renamed/copied files identify source, destination and similarity
percentage. Git detects renames/copies heuristically. `conflicting_files` lists
conflicted paths ([] when clean, null when unavailable). Some structural conflicts
may have no file entries; merge_conflicts still reports true in that case.
Text mode labels each change and shows source -> destination for moves/copies.
Conflict detection simulates merging compare into
base with Git 2.38+ `merge-tree`, without touching the checkout, index or refs;
it may create unreachable Git objects. Missing branches or unrelated histories
produce null analysis fields with an explanation. Other Git failures fail the
command. `--text` displays this analysis, PR details and an
ASCII comment tree: the first reply ID determines the parent; multi-target
comments list all targets explicitly. Comments without reply IDs are roots,
with `main` first. Siblings are ordered by ID. `--repo-dir` works in both modes.
The synchronous `show_pull_request(id, directory=".")` library API returns
`Result[PullRequestDetails]`, reading PR metadata and comments from one snapshot.

Commands emit JSON records (lists for `list` and `comments`), preserving multiline
text. List filters combine with AND: `open`, `mine`, `author=NAME_OR_EMAIL`,
`compare=BRANCH`, `base=BRANCH`, and `title=REGEX`. Full `Name <email>` identities
also match `author=`. `mine` uses the current Git author email. Unknown or repeated
filters/updates, invalid regexes, and conflicting status actions fail.
`draft`/`ready` change only draft state; `close`/`reopen` change only closed state.
Actions across axes can be combined. Contradictory actions within an axis fail.
JSON exposes independent `draft`, `closed`, and `merged` booleans instead of the
previous exclusive `status` field. All eight combinations are valid. Merged is
computed from ancestry for every PR, including draft and closed PRs, in creation,
update and list responses. Missing branches retain a `merged=false` fallback.
The `open` filter means ready AND not closed AND not merged.


```python
from pygc import create_pull_request, list_pull_requests, add_comment

# Inside an async function (or use asyncio.run from synchronous code):
result = await create_pull_request("feature/login", "main", "Add login", "Description")
requests = list_pull_requests(["open"], directory="/path/to/repo")
reply = await add_comment("PR_ID:main", "Feedback", directory="/path/to/repo")
```

Public APIs return `Result[PullRequest]`, `Result[list[PullRequest]]`,
`Result[Comment]`, or `Result[list[Comment]]`. `update_pull_request(id, updates,
directory=".")` accepts the CLI update tokens; `list_comments(id, directory=".")`
returns exact text and `replies_to` IDs. Creation results contain stored fields and computed merged state.
Update results additionally include the original author and creation time, including no-op updates. Listing resolves
author, creation time and merged status.
`generate_id(kind)` in `pygc.library.ids` is async and currently generates random
UUID strings, distinguishing `pull_request` from `comment` requests.

Metadata follows `pull-requests/c~>b#id:title/comment-id[:reply-id...]` under the
reserved directory. Components use percent escaping for separators, spaces,
slashes and percent signs, so branch names such as `feature/login` round-trip.
Closed and draft flags may coexist as `[closed][draft]`; legacy single flags
and either combined order remain readable. Duplicate flags are invalid metadata.
The initial comment is always `comment-main`. Multiple reply IDs are supported.
Use `update_comment(target, text, directory=".")` to replace text and
`delete_comment(target, directory=".")` to delete a comment. These synchronous
APIs return the updated or removed `Comment`. Targets require exactly
`PR_ID:COMMENT_ID`. Identical updates do not create commits. Deletion preserves
replies and their text, removing links to the deleted ID. The required `main`
description cannot be deleted; clear it with `gc comment update PR_ID:main ""`.
Any local author can edit/delete comments; prior contents remain in Git history. Malformed stored comment filenames or
non-UTF-8 bodies return `invalid_metadata`; invalid caller-supplied IDs return
`invalid_argument`. Git history supplies PR creator and creation
time, tracked by stable ID through directory renames along first-parent history.
Metadata commit messages name the action and target, for example `close pr ID`
or `update comment CID text on pr PID`. Combined PR updates describe each actual
change; unchanged fields are omitted. Existing history is not rewritten.
Writes preserve the checkout and index and atomically append to metadata history;
a concurrent update fails instead of overwriting it. Failed writes may leave
unreachable Git objects. Retrying a failed write requires a fresh operation.

Additional failure reasons are `not_initialized`, `invalid_argument`,
`branch_not_found`, `not_found`, `invalid_metadata`, and `id_conflict`.
Failures print reason/detail to stderr and exit 1; CLI arity errors exit 2.
These APIs are not registered over RPC. No frontend changes are included.

### Issues

Issues track work independently of branches. Each issue has an immutable random
ID, title, `closed` flag, original author, and creation timestamp. The description
is its editable `main` comment. New issues are open; closing is reversible and
still allows comments.

```sh
gc issue new "Fix login" "Steps to reproduce"
gc issue new "Fix login" @-              # description from stdin
gc issue list                            # all issues, ordered by ID
gc issue list open mine 'title=login.*'
gc issue list closed 'author=name@example.com'
gc issue show ISSUE_ID                    # JSON: issue and comments
gc issue show ISSUE_ID --text             # details and reply tree
gc issue update ISSUE_ID 'title=Revised title' close
gc issue update ISSUE_ID reopen
gc issue comments ISSUE_ID
gc issue comment add ISSUE_ID "More detail"
gc issue comment add ISSUE_ID:main "Reply to description"
gc issue comment add ISSUE_ID:COMMENT_ID @-
gc issue comment update ISSUE_ID:main "Revised description"
gc issue comment delete ISSUE_ID:COMMENT_ID
gc issue --help
```

Omitting the description creates an empty `main` comment. Filters combine with
AND: `open`, `closed`, `mine`, `author=`, and `title=REGEX`. Author matches a name,
email, or full Git identity; `mine` matches the current Git author email. Updates
accept `title=`, `close`, and `reopen`. Unknown/repeated tokens, contradictory
states, blank titles, and invalid regular expressions fail without writing.
All leaf commands accept `--repo-dir PATH`; text containing spaces must be quoted.
Commands output JSON by default; `show --text` provides a readable conversation.

Issue comments use the same threaded model as PR comments. Multiple reply targets
are supported as `ISSUE_ID:COMMENT_ID:OTHER_ID`. Text and trailing newlines are
preserved; `@-` reads stdin for creation and comment add/update. Deleting a comment
keeps replies and removes their links to it. `main` cannot be deleted; clear it
with `gc issue comment update ISSUE_ID:main ""`. Existing `gc comment` commands
continue to address PRs.

Issues are stored on the existing `__git-centric__` branch under
`__git-centric__/issues/ID:encoded-title/`, prefixed with `[closed]` when closed.
Titles use percent escaping; comment blobs use `comment-ID[:REPLY_ID...]` names.
Creator and creation time come from first-parent Git history by stable ID, so
renaming or closing retains them. Existing initialized repositories need no
migration. Writes preserve the checkout, index, PRs, and unrelated metadata.
Concurrent publication fails instead of overwriting another writer; retry with a
fresh operation. No-op updates create no commit. Any local Git author can edit;
previous content remains in history.

Issues are available through Python and the CLI. Labels, assignees, milestones,
PR linking, issue deletion, and issue RPC/web UI are not implemented.

Python exports include async `create_issue(title, comment="", directory=".")`
and `add_issue_comment(target, text, directory=".")`, plus synchronous
`list_issues`, `show_issue`, `update_issue`, `list_issue_comments`,
`update_issue_comment`, and `delete_issue_comment`. All return `Result` values;
`show_issue` returns `IssueDetails(issue, comments)`. Creation and updates return
complete `Issue` records, including original author and creation time. Issue
failures use the existing domain reasons, including `invalid_argument`,
`invalid_metadata`, `not_found`, `id_conflict`, and `git_error`.

### Greeting example over RPC

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
    constants.py       Reserved names and Git tree modes
    initialization.py  GitPython inspection and initialization
    result.py          Success / Failure algebraic result types
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
a Typer command as appropriate. RPC exposure requires a separately specified wire
contract, explicit registration in `rpc.METHODS`, and corresponding client updates.
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

The browser can inspect the repository selected by `gc web --repo-dir PATH`
with the parameterless JSON-RPC method `repo.get`. It returns the repository
name, bare flag, HEAD branch and commit, initialization status and metadata tip.
Reload workers inherit the same selection.
