# Simplified library policy gate

Implement the README write-action table with a default-allow checker. Remove read
and unlisted mutation checks, use the create action on base retargeting, and
wire role metadata, user administration and node edits at their snapshot writers.
Keep merge and policy-script replacement as catalog entries for future writers.
Test normalized inputs, denied/no-op/bulk updates, CLI behavior, and public reads.

Verified on Linux with Python 3.12. From pygc, Ruff lint and format checks and
mypy passed. The four policy regression tests cover effective branch pairs and
atomic denial, membership and role metadata checks, node CLI payloads and public
reads, and independent issue creation/comment permissions. The complete
`uv run pytest -q` suite passed 155 tests with one Starlette deprecation warning.
