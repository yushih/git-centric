# Users and roles

- ACCESS-001. Initialization registers the Git author name with an OpenSSH Ed25519
  public key. Reuse the private key in `~/.__git-centric__sk-Ed25519` across repos.
  Generate with ssh-keygen and publish a complete owner-only file without replacement.
  A failed ref publication may leave the reusable local key.
- ACCESS-006. A successful init creates owner, admin, ci and merger with empty metadata
  in the initial commit. Only owner has a member, the creating Git author.
  Existing repositories retain their registry when repeated initialization fails.
- ACCESS-002. User registration accepts a unique printable single-component name and
  an OpenSSH Ed25519 public key. Users list in name order. Existing repositories
  begin with an empty registry. Names exclude dot components, .git, separators and *.
- ACCESS-003. Roles store verbatim UTF-8 metadata, default empty. List in name order
  with sorted user names. Reject duplicate creation and deletion of occupied roles.
- ACCESS-004. Assign/unassign one registered user or all current users with '*'.
  Each user can hold multiple roles. Persist empty marker blobs under users/NAME/roles/ROLE.
  An unchanged membership creates no commit. Missing targets fail with not_found.
- ACCESS-005. All operations return Result. CLI access user add/list and access role
  create/list/delete/remove/assign/unassign emit JSON and follow existing repo and
  finalization options. Writes compare and swap one metadata tip and preserve the checkout.
  Policy execution, enforcement and RPC registration are outside this feature.

Implement the key bootstrap, registry, exports and CLI in that order. Verify actual
Git objects, key reuse, lifecycle, wildcard updates, failures and competing writes
with isolated repositories. Run Python static checks and the regression suite.

## Verification

Verified 2026-11-26 on Linux with Python 3.12. From pygc, Ruff check and format
checks passed, and mypy src passed. The initial sandboxed pytest run stalled.
The first unrestricted run exposed a CLI positional metadata parsing error.
After correcting it, `uv run pytest -q` passed all 150 tests with one Starlette
TestClient deprecation warning. The access tests cover the CLI lifecycle,
key derivation and reuse, invalid inputs, no-op writes, and competing publication.
