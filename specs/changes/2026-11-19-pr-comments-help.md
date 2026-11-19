# Pull request comments help

State: verified

## Contract and plan

`gc pr comments` prints the full command help rather than only a missing-argument
error, using Typer's standard no-arguments help behavior (exit 2).
`gc pr comments --help` prints that same help content and exits 0.
Help describes the required PR_ID, JSON comment text/reply IDs, --repo-dir and
its cwd default, and an example. Neither help path accesses a repository.
Supplying a PR ID retains existing listing, validation, and repository selection.

Use the built-in no_args_is_help option, improve the argument/help text, and add
regression tests for both forms outside a repository. Update the feature spec
and README. Run locked sync, lint/format, mypy and affected CLI tests.

## Evidence

2026-11-19, Python 3.12, from `pygc/`, with
`UV_CACHE_DIR=/tmp/git-centric-uv-cache`:

- `uv sync --locked`: passed; locks unchanged.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`: passed.
- `timeout 60s env UV_CACHE_DIR=/tmp/git-centric-uv-cache uv run pytest -q
  tests/test_pull_requests.py tests/test_repo_directory.py`: 49 passed in 8.10s.
  Initial regression assertions expected a bare PR_ID metavar; adjusted to
  Typer's rendered required-argument `{PR_ID}` syntax, then both cases passed.
- `uv run gc pr comments` and `uv run gc pr comments --help`: manually inspected
  identical full help output, with exits 2 and 0 respectively.
- `git diff --check`: passed.

The two cases of `test_pr_comments_help_without_repository` verify complete
help and no library calls outside a repository. Existing tests cover normal
listing and repository overrides. No dependencies, frontend, or domain changes.
