Share the detail header, reply presentation and historical comment attribution
between issues and PRs. Verify authorship through renames and edits in a real
repository, run interface checks, and exercise the packaged issue page.

Completed the shared issue/PR header and reply bylines. Python lint, format
and mypy passed. The full pytest run passed 131 tests with one existing
Starlette deprecation warning. All six frontend tests and the production
build passed. Built and installed the wheel offline and exercised opening an
issue, adding a nested reply, checking the byline, hiding IDs and closing the
issue in Chrome. Restarted gc web for /tmp/git and confirmed issues.show on
port 8000 returns creation author and timestamp on live comments.
