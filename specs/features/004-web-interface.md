# Repository web interface

State: implemented. See the [release verification record](../changes/2026-11-20-forge-ui.md) and [initial repository context record](../changes/2026-11-20-web-context.md).

## Product and information architecture

Build a local, single-repository forge. Borrow GitHub's repository tabs, branch selector, file breadcrumbs, issue lists and PR conversation/files views. Use the actual local repository name and stable entity IDs. Git author identity describes authorship. The first release assumes one local operator and covers browsing code and managing collaboration metadata. Source editing, merging, remotes, accounts and permissions require separate product decisions.

Use hash routes so bookmarks, reloads and browser history work with the current static server. Keep the repository header and Code, Issues and Pull requests tabs across detail pages. Put branch, path, active subtab and list filters in the URL. Encode branch names and paths as separate query parameters so branch names containing slashes round-trip.

| Destination | What the user sees and does |
| --- | --- |
| Code, default landing page | Repository name, branch selector, latest commit on the selected branch, directory rows and breadcrumbs. Open a file or follow History. Show setup instructions for an empty Git repository. |
| File and history | Display text with line numbers or a binary/oversize notice. History lists commits for the selected branch, newest first, with links to commit details and the tree at that revision. |
| Issues | Open/closed views, author and title filters, new issue action. Rows link to issue details. Preserve filters on Back. |
| Issue detail | Title, status, original author/date, description and threaded replies. Edit title or description, close/reopen, add/edit/delete comments. Confirm deletion and preserve drafts on errors. |
| Pull requests | Open view uses the existing ready, unclosed, unmerged definition. Provide an All view for drafts and other states. Create from two existing branches, title and optional description. |
| PR detail | Conversation shows independent draft, closed and merged flags, branch pair, description and threads. Expose existing update actions. Files changed shows compare-side changes since the merge base, rename paths, patch and conflict information. Distinguish unavailable analysis from a clean comparison. |

Render identities/times only where the library supplies them. Current comments carry ID, text and reply targets. Put each reply under its first target and link additional targets. Display user text as escaped text. Each screen needs keyboard-accessible controls, loading, empty, failure and retry states. On narrow screens preserve breadcrumbs and keep wide diffs horizontally scrollable.

## Domain and transport contracts

React calls a typed client over the existing FastAPI JSON-RPC endpoint. Bind one resolved repository directory to the application factory at launch from the existing gc web --repo-dir option. Today the CLI checks that option but does not pass the selection to the app. Carry selection through reload too. Browser requests never select filesystem directories. Bind loopback by default and restrict mutation requests to trusted local host/origin combinations, including the configured development proxy. Review non-loopback serving separately before exposing writes there.

Existing library writes already cover issue and PR creation/update and scoped comment add/update/delete. Reuse their validation, commit subjects and atomic metadata ref publication. Existing reads cover lists, show, merge analysis and conversations. Register explicit repo, code, issues and pulls methods individually. For example issues.show accepts {id}, issues.create accepts {title, description}, and issues.comments.add accepts {id, repliesTo, text}. Define corresponding methods per supported operation. Adapters translate structured filters/updates to existing library arguments. Keep target construction on the server. Reject unknown keys, conflicting actions and malformed IDs. A literal @- in a browser body is ordinary text.

Return JSON records/arrays on success. Map domain Failure to JSON-RPC error -32000 with data.reason and a user-safe message. Keep protocol/validation errors distinct. Preserve existing batch, notification and greet behavior. Run Git work off the event loop, including async creation APIs whose bodies perform synchronous Git I/O. Freeze method schemas and client response validators alongside each slice. Avoid automatic mutation retries after uncertain delivery.

### Additional Python library contracts

All functions take the server-selected directory and return Result[T]. Use GitPython argument lists and immutable Git objects. Source reads must work in bare repos, leave refs/index/worktree untouched, and exclude the reserved metadata branch from source selectors. Resolve a branch once, then pin follow-up reads to the captured commit. Validate revisions as reachable source commits, paths as repo-relative tree components and pagination limits before reading content.

| Proposed operation | Input and result | Purpose and edge cases |
| --- | --- | --- |
| get_repository | Directory → display name, bare flag, HEAD branch or detached commit, initialized flag, metadata tip or null | Establish context even on unborn HEAD. Code browsing can work before metadata initialization. |
| list_branches | Directory → local source branch names and tip OIDs | Populate selectors and PR creation. Preserve full names and distinguish an empty list. |
| list_tree | Commit OID, directory path → immediate entries with name, kind and OID | Root uses empty path. Distinguish tree, blob, symlink and submodule. Never follow a symlink into the filesystem. |
| read_blob | Commit OID, path → kind, byte size, text or omission reason | Bound reads before decoding. Show binary, invalid UTF-8 and oversized files as notices. |
| list_commits / get_commit | Tip OID, cursor, limit → page and next cursor. Commit OID → subject, body, author, timestamp and parents | Pin pagination to the tip and define deterministic traversal including merges. |
| read_commit_diff | Commit OID and optional changed path → file status, old/new paths, bounded patch, omission reason | Compare to first parent, or empty tree for root. Preserve rename and binary information. |
| read_pr_diff | PR ID and selected file → base/compare/merge-base OIDs and bounded compare-side patch | Share resolution with PR analysis. Return unavailable if branches disappear. Pin the file list and patch to the same comparison or prompt refresh when tips change. |
| Conditional metadata writes | Add optional expected metadata tip to existing update/comment writers. Browser detail reads return the tip captured with the record | Check the expected tip inside the store transaction before applying changes, then use existing compare-and-swap at publication. Return stale_snapshot on mismatch, retain the draft and offer reload. Existing Python/CLI callers may omit the precondition. An unrelated metadata write may require refresh. |
| Initialize collaboration metadata | Reuse initialize_gc after explicit setup action → creation commit OID | Preserve the existing orphan initialization and branch-conflict behavior. |

New source read failures should distinguish missing branch/commit/path, wrong entry kind and invalid input. Set concrete bounds per endpoint before implementation (proposed defaults: history 50, maximum 100 commits, text and patches 1 MiB). Disable external diff and text conversion. Large/binary omission is a successful display state. No new source-ref writer is needed for these screens. A future Merge button requires a separately specified merge operation with expected base/compare tips, conflict policy and checked-out branch handling.

## Multi-session delivery and acceptance

| Session | Depends on | Deliverable and completion check |
| --- | --- | --- |
| 1. Repository context and RPC foundation | Existing web app | Wire selected directory through launch/reload, implement repository context, strict result/error mapping and typed client. Verify two selected repos remain isolated, invalid parameters fail and existing RPC tests pass. |
| 2. Repository shell and navigation | 1 | Replace greeting landing page with responsive tabs, hash routes, shared loading/error views and explicit initialization. Verify deep links, reload, Back, keyboard navigation and origin restrictions on setup. |
| 3. Code browser | 1, 2 | Implement branches/tree/blob APIs and connect selector, breadcrumbs and viewer. Test empty/bare/detached repos, slashed names, symlinks and binary/oversized files using real Git fixtures. |
| 4. Commit history | 3 | Implement history, commit details and bounded commit diffs. Verify root/merge commits, pagination with a moving branch and rename/binary presentation. |
| 5. Issue browsing | 1, 2 | Register list/show, include captured metadata tip, build filtered list and detail/conversation components. Verify empty states, multiline text, reply nesting and URL filter restoration. |
| 6. Issue mutations | 5 | Implement conditional write support, create/edit/state controls and comment actions. Test stale tabs, no-op updates, failed writes retaining drafts, and refs/index/worktree preservation. |
| 7. PR workflow | 3, 5, 6 | Reuse branch selector, lists and conversation editor. Wire PR list/show/create/update and scoped comments. Verify all state combinations, missing branches and unchanged PR CLI behavior. |
| 8. PR files changed | 4, 7 | Implement pinned PR patch reads and file navigation. Verify merge-base semantics, conflicts, changed branch tips, renames, deleted and binary files. |
| 9. Release verification | 1–8 | Exercise code → issue → discussion → PR → files in temporary repos. Check desktop/mobile and keyboard flows, production asset serving and isolated wheel installation. Update root and Python READMEs with verified usage. |

At the start of each session read this spec, the relevant existing feature contract and the preceding change record. Record the chosen method signatures, wire examples and acceptance tests before coding. End each session with a dated record under specs/changes listing completed rows, affected paths, exact checks/results, unresolved decisions and the next unblocked row. Rows 3 and 5 can proceed independently after the shell. Keep partial releases usable by exposing navigation when its destination ships.

Run Ruff, mypy and affected pytest suites for Python changes, npm test and npm run build for frontend changes, and the repository's wheel verification for asset changes. Verify Git effects independently in temporary repositories. Session evidence is recorded under specs/changes.

Landing contract revision: show source branches, commits and files only on Code.
Omit repository type, reserved branch, metadata commit and initialization status.

The collaboration tabs own the explicit setup action. Detail responses include
metadata_tip. Update and scoped comment requests require expectedTip. Use
issues/pulls.show({id}), .create, .update, and .comments.add/update/delete.
Commit detail and PR patch previews are limited to 1 MiB. A changed comparison
requires a refresh. Preserve the existing code.browse wire contract.

## Shipped RPC and routing details

The existing aggregate `code.browse` method also accepts `detail: true` for
first-parent commit details. An empty path returns the combined patch and a
changed path selects its patch, including the old path for renames. History
uses pages of 50 and an offset within the pinned revision.

Both collaboration namespaces accept these named parameters.

| Method | Parameters | Result |
| --- | --- | --- |
| list | Optional state, title substring, author name/email/identity | Records with creation identity and state flags. Default RPC state is all, default UI state is open. |
| show | id | Entity, comments and metadata_tip. PR detail also contains comparison tips, merge_base, conflicts and changed files. |
| create | title, optional description, plus base and compare for PRs | Created entity |
| update | id, expectedTip, optional title and state (close/reopen), plus optional PR base, compare and readiness (draft/ready) | Updated entity |
| comments.add | id, expectedTip, text, repliesTo (array of comment IDs) | Created comment |
| comments.update | id, expectedTip, comment, text | Updated comment |
| comments.delete | id, expectedTip, comment | Deleted comment |

`repo.initialize({})` returns the initialization commit.
`pulls.patch({id, baseTip, compareTip, path})` returns patch text or a size
notice. File links carry the comparison tips so selecting a file after a
branch moves prompts a refresh. Comparisons and patch previews use immutable
commits. Mutations require a loopback peer and Host, with same-origin browser
requests and the specified loopback Vite origins accepted.
