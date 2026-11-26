# Manage policy rules in Access

Add snapshot-based rule list and mutation operations, explicit RPC methods and
a Rules view. Repair the bundled rule templates so a newly initialized owner's
policy can authorize edits. Test the real rule lifecycle, denials, invalid input,
stale writes, frontend contracts and production build.

Use the dedicated access.rules.change_scripts action for previews and writes.
access.rules.list returns metadata_tip and an array of {name, source}.
access.rules.change accepts operation, name, expectedTip and source for create
or edit, returning the resulting metadata tip. HTTP mutations use the local
write guard. The packaged owner, admin and contributor scripts were repaired
for fresh repositories; existing committed policies govern their own changes.

Verified 2026-11-26: 159 Python tests and 11 frontend tests passed. The frontend
and wheel builds passed. Chromium against an isolated wheel installation
initialized a repository, created, edited, reloaded and deleted a rule through
the Rules view. Ruff and mypy passed excluding the existing
rules-merger-can-merge.py file, which has unresolved type and lint errors and
does not match the rule-*.py pattern.
