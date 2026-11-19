# Web repository context (session 1)

Expose get_repository(directory) and repo.get with empty parameters. Return name,
bare, branch, head, initialized and metadata_tip. Branch and object IDs may be null.
Bind repository selection at application construction, including reload workers.
Verify isolation, parameter rejection, unborn HEAD, error mapping and existing RPC.

Session 1 complete. The CLI passes an absolute directory to the reload factory
through its inherited environment and restores the prior value when the server
exits. Each app captures its own registry. The context library, CLI, RPC adapter,
app factory and TypeScript client carry this contract.

Validation from pygc/: Ruff check and format check passed. Mypy passed for 15
source files. The bounded outside-sandbox run of pytest tests/test_interfaces.py
tests/test_repo_directory.py -q passed all 27 tests, including factory isolation
and reload selection. A sandboxed ASGI probe stalled and was interrupted.
From frontend/, npm test passed 5 tests and npm run build passed. Next is row 2,
the visible repository shell and guarded setup action.
