# Branch sync and pull request merging

Replace the explicit consensus command with branch selection under sync push.
Implement authorized local PR merges with Git plumbing and guarded ref updates.
Exercise CLI selection, deferral, merge ancestry, denial, conflicts and peer
refs using temporary repositories. Run the Python suite and static checks.

On 2026-11-27, `uv run pytest -q` passed all 163 cases collected, with the
existing Starlette warning. The subsequently added deferred fast-forward
case passed individually. Ruff lint, formatting and mypy pass when excluding
the pre-existing rules-merger-can-merge.py errors (undefined Literal,
invalid/missing return and formatting). No dependencies or wire APIs changed.
