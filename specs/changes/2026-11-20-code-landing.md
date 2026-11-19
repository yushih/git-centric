Implement the Code landing contract with a branch-scoped snapshot reader,
bounded file previews, paged history and read-only collaboration lists.
Verify branch/path handling, source isolation, UI navigation and the built bundle.

Implemented branch/path/revision hash routes, committed tree and text previews,
history paging and links to read-only issue and PR lists. Source reads use the
selected repository and pin previews to commits reachable from the chosen tip.

Validation: Ruff and mypy passed, the temporary repository navigation test
passed, all five frontend tests passed and npm run build succeeded. Exercised
code, file, history and both list RPCs. Headless Chrome loaded the production
page from gc web and rendered the branch selector, README file and History link.
The old overview, repository type and metadata commit labels were absent.
