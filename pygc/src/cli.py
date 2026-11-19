"""The gc command line interface."""

from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from git import Repo
from git.exc import GitError
from typer._click.core import Context as ClickContext
from typer.core import TyperGroup

from . import library

app = typer.Typer(
    no_args_is_help=True,
    help="Git-centric tools. Commands accept --repo-dir; default: current directory.",
)


RepoDir = Annotated[
    Path | None,
    typer.Option("--repo-dir", help="Repository directory; overrides the current directory."),
]


def _directory(repo_dir: Path | None, default: Path = Path(".")) -> Path:
    """Select a path without chdir; ambiguity checks are advisory, never fallback."""
    if repo_dir is None:
        return default
    if library.is_gc_initialized() == library.Success(True) and library.is_gc_initialized(
        repo_dir
    ) == library.Success(True):
        try:
            # Common directories identify the shared refs even across linked
            # worktrees. Resolving paths also collapses symlinks and ../ aliases.
            with (
                Repo(Path.cwd(), search_parent_directories=True, expand_vars=False) as current,
                Repo(
                    repo_dir.absolute(), search_parent_directories=True, expand_vars=False
                ) as chosen,
            ):
                different = Path(current.common_dir).resolve() != Path(chosen.common_dir).resolve()
        except (OSError, GitError):
            # A repo can disappear between inspection and discovery. Let the
            # actual operation return its normal Result rather than redirecting it.
            different = False
        if different:
            typer.echo(
                f"Warning: current directory {Path.cwd()} and --repo-dir {repo_dir.absolute()} "
                "are different initialized repositories; using --repo-dir.",
                err=True,
            )
    return repo_dir


@app.command("help")
def help_command(ctx: typer.Context, repo_dir: RepoDir = None) -> None:
    """Show the top-level help message."""
    _directory(repo_dir)
    assert ctx.parent is not None
    typer.echo(ctx.parent.get_help())


@app.command()
def init(
    directory: Annotated[
        Path,
        typer.Argument(help="Legacy repository directory; --repo-dir overrides it. Default: cwd."),
    ] = Path("."),
    repo_dir: RepoDir = None,
) -> None:
    """Initialize Git-centric metadata in an existing Git repository."""
    # Translate the library's result into CLI output and an exit status. The
    # library itself remains independent of Typer and never exits the process.
    match library.initialize_gc(_directory(repo_dir, directory)):
        case library.Success(commit):
            typer.echo(f"Initialized Git-centric ({commit})")
        case library.Failure(reason, detail):
            typer.echo(f"{reason.value}: {detail}", err=True)
            raise typer.Exit(code=1)


@app.command()
def web(
    host: Annotated[str, typer.Option(help="Address to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
    reload: Annotated[bool, typer.Option(help="Reload Python code during development.")] = False,
    repo_dir: RepoDir = None,
) -> None:
    """Start the FastAPI server and serve the built React frontend."""
    _directory(repo_dir)
    uvicorn.run("pygc.web:create_app", factory=True, host=host, port=port, reload=reload)


pr_app = typer.Typer(no_args_is_help=True, help="Create, list, update and discuss pull requests.")
app.add_typer(pr_app, name="pr")


def _output(result: library.Result[object]) -> None:
    # JSON retains multiline text and makes each returned record unambiguous.
    import json
    from dataclasses import asdict, is_dataclass

    match result:
        case library.Failure(reason, detail):
            typer.echo(f"{reason.value}: {detail}", err=True)
            raise typer.Exit(1)
        case library.Success(value):

            def record(item: object) -> object:
                return asdict(item) if is_dataclass(item) and not isinstance(item, type) else item

            typer.echo(
                json.dumps(
                    [record(item) for item in value] if isinstance(value, list) else record(value),
                    ensure_ascii=False,
                )
            )


def _text(value: str) -> str:
    import sys

    return sys.stdin.read() if value == "@-" else value


@pr_app.command("new")
def pr_new(
    compare: str, base: str, title: str, comment: str = typer.Argument(""), repo_dir: RepoDir = None
) -> None:
    """Create a PR: COMPARE BASE TITLE [COMMENT]. Quote text; @- reads stdin."""
    import asyncio

    _output(
        asyncio.run(
            library.create_pull_request(
                compare, base, title, _text(comment), directory=_directory(repo_dir)
            )
        )
    )


@pr_app.command("list")
def pr_list(
    filters: Annotated[list[str] | None, typer.Argument()] = None, repo_dir: RepoDir = None
) -> None:
    """Filter with open, mine, author=, compare=, base=, title=REGEX (AND)."""
    _output(library.list_pull_requests(filters or (), directory=_directory(repo_dir)))


def _pr_text(details: library.PullRequestDetails) -> str:
    """Render a validated conversation without recursion or Markdown styling."""
    import json

    pr = details.pull_request
    lines = [
        f"PR {pr.id}",
        f"Title: {pr.title}",
        f"Compare: {pr.compare}",
        f"Base: {pr.base}",
        f"Author: {pr.author}",
        f"Created: {pr.created_at}",
        f"Draft: {str(pr.draft).lower()}  Closed: {str(pr.closed).lower()}  "
        f"Merged: {str(pr.merged).lower()}",
        "",
    ]
    conflict = (
        "unknown" if details.merge_conflicts is None else "yes" if details.merge_conflicts else "no"
    )
    lines.append(f"Merge conflicts: {conflict}")
    if details.conflicting_files:
        lines.append("Conflicting files:")
        lines.extend(
            "  " + json.dumps(path, ensure_ascii=False) for path in details.conflicting_files
        )
    elif details.merge_conflicts:
        lines.append("Conflicting files: none reported by Git")
    if details.merge_analysis_error:
        lines.append(f"Merge analysis: {details.merge_analysis_error}")
    if details.changed_files is None:
        lines.append("Changed files: unavailable")
    elif not details.changed_files:
        lines.append("Changed files: none")
    else:
        lines.append("Changed files:")
        for change in details.changed_files:
            path = json.dumps(change.path, ensure_ascii=False)
            if change.old_path is not None:
                path = f"{json.dumps(change.old_path, ensure_ascii=False)} -> {path}"
                path += f" ({change.similarity}% similar)"
            lines.append(f"  {change.status}: {path}")
    lines.extend(["", "Comments:"])
    children: dict[str | None, list[library.Comment]] = {}
    for comment in details.comments:
        parent = comment.replies_to[0] if comment.replies_to else None
        children.setdefault(parent, []).append(comment)
    # Explicit stack avoids Python's recursion limit for long conversations.
    stack = [
        (c, "", i == len(children.get(None, [])) - 1)
        for i, c in reversed(list(enumerate(children.get(None, []))))
    ]
    while stack:
        comment, prefix, last = stack.pop()
        label = f"[{comment.id}]"
        if len(comment.replies_to) > 1:
            label += (
                f" (replies to: {', '.join(comment.replies_to)}; "
                f"tree parent: {comment.replies_to[0]})"
            )
        lines.append(prefix + ("`-- " if last else "|-- ") + label)
        continuation = prefix + ("    " if last else "|   ")
        # split rather than splitlines retains blank/trailing lines in the body.
        lines.extend(continuation + line for line in comment.text.split("\n"))
        replies = children.get(comment.id, [])
        stack.extend(
            (c, continuation, i == len(replies) - 1) for i, c in reversed(list(enumerate(replies)))
        )
    return "\n".join(lines)


@pr_app.command("show", no_args_is_help=True)
def pr_show(
    identifier: Annotated[str, typer.Argument(metavar="PR_ID", help="Pull request ID to show.")],
    text: Annotated[
        bool, typer.Option("--text", help="Show plain text with a comment tree.")
    ] = False,
    repo_dir: RepoDir = None,
) -> None:
    """Show a pull request and all comments as JSON; --text displays a reply tree.

    Includes conflicting paths and file change types since the merge base.
    Multiple reply targets use the first as tree parent and list all targets.
    """
    result = library.show_pull_request(identifier, directory=_directory(repo_dir))
    if text and isinstance(result, library.Success):
        typer.echo(_pr_text(result.value))
    else:
        _output(result)


@pr_app.command("update")
def pr_update(
    identifier: str, updates: Annotated[list[str], typer.Argument()], repo_dir: RepoDir = None
) -> None:
    """Apply compare=, base=, title=, draft/ready and close/reopen independently."""
    _output(library.update_pull_request(identifier, updates, directory=_directory(repo_dir)))


@pr_app.command("comments", no_args_is_help=True)
def pr_comments(
    identifier: Annotated[
        str, typer.Argument(metavar="PR_ID", help="Pull request ID to list comments for.")
    ],
    repo_dir: RepoDir = None,
) -> None:
    """List a pull request's comments as JSON, including text and reply IDs.

    Example: gc pr comments PR_ID --repo-dir=/path/to/repo

    The repository defaults to the current directory.
    """
    _output(library.list_comments(identifier, directory=_directory(repo_dir)))


class _CommentGroup(TyperGroup):
    """Keep the original append syntax while exposing real nested commands."""

    def parse_args(self, ctx: ClickContext, args: list[str]) -> list[str]:
        # Route the old target/text invocation through the same typed add
        # command, retaining option parsing and strict argument-count checks.
        # Help stays on the group; explicit add disambiguates action-like IDs.
        if args and args[0] not in {"add", "update", "delete", "--help"}:
            args = ["add", *args]
        return super().parse_args(ctx, args)


comment_app = typer.Typer(
    cls=_CommentGroup,
    no_args_is_help=True,
    help=(
        "Add, update or delete comments. Shorthand: gc comment PR_ID TEXT. "
        "--repo-dir selects a repo."
    ),
)
app.add_typer(comment_app, name="comment")


@comment_app.command("add")
def comment_command(target: str, comment: str, repo_dir: RepoDir = None) -> None:
    """Append quoted COMMENT to PR[:COMMENT_ID...]; @- reads stdin."""
    import asyncio

    _output(
        asyncio.run(library.add_comment(target, _text(comment), directory=_directory(repo_dir)))
    )


@comment_app.command("update")
def update_comment_command(target: str, text: str, repo_dir: RepoDir = None) -> None:
    """Replace PR_ID:COMMENT_ID text. Quote TEXT; @- reads stdin; empty text clears."""
    _output(library.update_comment(target, _text(text), directory=_directory(repo_dir)))


@comment_app.command("delete")
def delete_comment_command(target: str, repo_dir: RepoDir = None) -> None:
    """Delete PR_ID:COMMENT_ID and its reply links. Main must be cleared instead."""
    _output(library.delete_comment(target, directory=_directory(repo_dir)))
