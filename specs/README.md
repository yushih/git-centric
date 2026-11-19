# Spec-driven development

Specifications describe observable behavior; code implements it; tests provide
evidence. This workflow is local Markdown and requires no external SDD tooling.

## Specification index

| Document | Purpose | State |
| --- | --- | --- |
| [architecture.md](architecture.md) | Package layout, boundaries, tools, interfaces | Current baseline |
| [features/001-initialization.md](features/001-initialization.md) | Initialization API, CLI, and repository invariants | Implemented; verification tracked separately |
| [features/002-pull-requests.md](features/002-pull-requests.md) | Pull requests and conversations | Implemented; see feature and change records |
| [features/003-issues.md](features/003-issues.md) | Issue fields, storage, commands, and implementation plan | Verified; see feature evidence |
| [features/004-web-interface.md](features/004-web-interface.md) | Repository web interface architecture, Git APIs and session backlog | Session 1 implemented |
| [templates/change.md](templates/change.md) | Spec, plan, task, and evidence template for new work | Reusable template |

The baseline captures the session's decisions and current implementation. It does
not certify that all tests pass in every environment. The root README's remaining
product concepts are roadmap material, not accepted implementation tasks.

## Change workflow

1. Read the relevant baseline spec and code. State the user-visible problem and
   scope, including what will not change.
2. For a new feature, copy the template to `specs/features/NNN-short-name.md`,
   choosing the next unused number. For a substantial change to an existing
   feature, keep its spec current and create a record at
   `specs/changes/YYYY-MM-DD-short-name.md` using the same template.
3. Give observable requirements stable IDs, such as `INIT-001`. Write acceptance
   scenarios before implementation, including errors and state that must survive.
   Record design choices, affected files, and a short sequence of tasks.
4. Implement and add meaningful behavioral tests. Connect criteria to test names
   in the spec. New cases may extend existing tests; do not duplicate tests solely
   to mirror an implementation detail.
5. Run relevant checks. Record date, environment, exact command, result, and any
   limitation. Separate planned checks from executed evidence.
6. Update state to `verified` only after required checks pass. Otherwise use
   `implemented; awaiting verification` and leave the remaining work explicit.

Small refactors and comment/documentation edits can update the relevant document
directly without a new numbered spec or change record. Do not add empty paperwork.
Keep current contracts in feature specs; change records explain the work and its
evidence. User-directed contract changes are allowed: revise the spec and affected
tests together, and note compatibility implications.

## Decisions and open questions

Record a design decision alongside its feature unless it affects multiple features;
cross-cutting decisions belong in `architecture.md`. Each should state the choice,
reason, and consequence. A separate ADR tool or directory is not required.

Mark unresolved questions explicitly. Do not silently turn an assumption into a
requirement or block independent work on an optional preference. RPC exposure of
Git initialization, for example, requires a wire-format and filesystem-access
decision; it is not part of the current initialization spec.
