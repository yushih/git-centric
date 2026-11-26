# Users and roles in the repository web UI

State: implemented and verified.

This extends the [registry](../features/007-access.md) and the [repository web
interface](../features/004-web-interface.md). The local operator should be able to
perform the same registry operations in the browser as via `gc access`. Role
membership describes repository data. Authentication, permission enforcement,
key rotation, user deletion and role metadata editing are outside this proposal.

## Operator workflow

Add an **Access** tab alongside Code, Issues and Pull requests. Use `#access` for
Roles and `#access?view=users` for Users so reload and Back restore the view.

- **Roles** shows each role’s name, verbatim metadata and assigned users. Provide
  creation with optional multiline metadata, assignment and removal for one
  user or all current users, and deletion of an empty role. Make “All users”
  an explicit choice and show the affected count before applying a bulk change.
  Explain occupied-role deletion inline. Default roles follow the same rules as
  custom roles.
- **Users** shows each registered name, its roles and an expandable public key.
  Derive each user's roles from the same snapshot as the roles view. Register
  a user by entering a name and pasting one OpenSSH Ed25519 public key.
- **Setup** reuses the existing explicit initialization action. Explain that it
  creates or reuses the local key and registers the Git author as owner. Read
  role names and memberships from Git after setup. An initialized legacy
  repository with an empty registry gets empty lists and creation controls.

## Implementation sequence

1. **Read a consistent snapshot.** In `library/access.py`, expose one Result-returning
   operation that returns the registry’s captured parent OID, sorted users and
   sorted roles from one _Registry instance. Calling the two existing lists
   separately can mix revisions. Add an optional keyword-only expected tip to
   the five access writers. Compare it with the captured parent before applying
   changes, including no-ops. Retain compare-and-swap publication. If a concurrent
   writer wins, distinguish a changed ref from other Git failures and surface
   stale_snapshot to a conditional caller. Preserve ordinary CLI behavior and the
   existing disk format.
2. **Register the web contract.** Bind the methods below to the repository selected
   by the server. Use the existing strict RPC validation, worker-thread dispatch,
   local request checks and domain error mapping. In `frontend/src/rpc.ts`, add
   matching calls and runtime validators for the snapshot and mutation results.
   The browser handles public keys only.

   | RPC method | Named parameters | Successful result |
   | --- | --- | --- |
   | access.get | none | {metadata_tip, users, roles} |
   | access.users.add | name, publicKey, expectedTip | User |
   | access.roles.create | name, optional metadata (default empty), expectedTip | Role |
   | access.roles.delete | name, expectedTip | Removed role |
   | access.roles.assign | user, role, expectedTip | Updated role |
   | access.roles.unassign | user, role, expectedTip | Updated role |

   User fields are name and public_key. Role fields are name, metadata and users
   (an array of names). The membership methods accept the existing '*' selector.
   Using the displayed snapshot tip also protects a bulk change if another user
   registers after the operator reviews the affected users.
3. **Ship the screens.** Wire the tab in `frontend/src/main.tsx`. Put forms and
   registry rendering in a dedicated Access component. Render metadata as plain
   text with line breaks. Provide labeled inputs, keyboard navigation, loading,
   empty and retry states. Disable duplicate submissions while saving. After
   confirmed success, trigger existing background finalization once and reload
   the registry. A read or failed action never triggers finalization. Preserve
   inputs on validation or stale errors and let the operator reload and review
   before resubmitting. On uncertain delivery or refresh failure, retry the read
   independently of the write.
4. **Verify and document.** Add the web workflow to the Python README and record
   release evidence against the scenarios below.

## Acceptance and verification

| Scenario | Evidence to collect |
| --- | --- |
| Fresh setup and legacy registry | Through the real RPC endpoint verify four default roles, only the creator in owner, and empty lists for a legacy marker-only tree. Check isolation between server-selected repositories. |
| User and role lifecycle | From the UI register a key, create a role with multiline metadata, assign, unassign and delete. Compare the snapshot with CLI output and independent Git tree reads. Exercise duplicate names, invalid keys, missing targets and occupied-role deletion. |
| Bulk and concurrent changes | With two clients, register a user after the first previews a bulk assignment. The stale request must preserve the ref and the draft. After reload, explicit resubmission changes all intended memberships in one commit. A repeated assignment creates no commit. |
| Browser and transport behavior | Check malformed responses and request fields, local-origin restrictions, finalization trigger counts, read retry after a successful write, deep links, Back, keyboard controls and narrow layouts. |
| Release | Run Ruff lint/format, mypy and pytest in pygc, then npm test and npm run build in pygc/frontend. Build the wheel and smoke-test its installed web assets and Access workflow in a temporary repository. |

## Verification evidence

2026-11-26, Linux, Python 3.12 and Node 26. From pygc, Ruff lint and format checks
and mypy passed. `uv run pytest -q` passed 151 tests with one Starlette deprecation
warning. From pygc/frontend, `npm test` passed 9 tests and `npm run build` passed.
An initial offline package build lacked setuptools in its cache. Using the populated
build cache, `uv build --offline` produced the wheel and sdist. Installed the wheel
and its dependencies into a fresh virtual environment with registry access.

Chromium exercised the installed CLI server with a temporary Git repo and home:
direct Users link, initialization, public key display, registration, keyboard
navigation, multiline role creation, stale wildcard assignment after a CLI write,
reload preserving the selection, assignment, removal and confirmed deletion.
A simulated failed refresh after deletion recovered with a read-only retry.
The six successful UI writes issued six finalization requests. Browser Back restored
Users and the 390-pixel viewport had no document overflow.
