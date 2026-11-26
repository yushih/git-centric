# Bundle policy sources during initialization

Build the rules tree from the installed library in the initial orphan commit.
Verify the exact Git paths and blob contents, then run initialization and regression tests.

Verification on 2026-11-26: all 158 Python tests passed. Initial-tree tests
compare each policy blob to its installed source bytes. Ruff passed for changed
Python files. The frontend and wheel builds passed, and the isolated wheel
installation provided the CLI, static index and identical policy sources.
Full mypy checking stops at the existing incomplete else block in the bundled
admin rule. That rule also makes policy evaluation deny protected writes.
