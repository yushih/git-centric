"""The gc command line interface."""

from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from . import library

app = typer.Typer(no_args_is_help=True, help="Git-centric command line tools.")


@app.command("help")
def help_command(ctx: typer.Context) -> None:
    """Show the top-level help message."""
    assert ctx.parent is not None
    typer.echo(ctx.parent.get_help())


@app.command()
def init(
    directory: Annotated[
        Path, typer.Argument(help="Git repository directory; defaults to the current directory.")
    ] = Path("."),
) -> None:
    """Initialize Git-centric metadata in an existing Git repository."""
    # Translate the library's result into CLI output and an exit status. The
    # library itself remains independent of Typer and never exits the process.
    match library.initialize_gc(directory):
        case library.Success(commit):
            typer.echo(f"Initialized Git-centric ({commit})")
        case library.Failure(reason, detail):
            typer.echo(f"{reason.value}: {detail}", err=True)
            raise typer.Exit(code=1)


@app.command()
def greet(name: Annotated[str, typer.Argument(help="Name to greet.")] = "world") -> None:
    """Call the library's example greeting function."""
    try:
        typer.echo(library.greet(name))
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="name") from exc


@app.command()
def web(
    host: Annotated[str, typer.Option(help="Address to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
    reload: Annotated[bool, typer.Option(help="Reload Python code during development.")] = False,
) -> None:
    """Start the FastAPI server and serve the built React frontend."""
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
def pr_new(compare: str, base: str, title: str, comment: str = typer.Argument("")) -> None:
    """Create a PR: COMPARE BASE TITLE [COMMENT]. Quote text; @- reads stdin."""
    import asyncio

    _output(asyncio.run(library.create_pull_request(compare, base, title, _text(comment))))


@pr_app.command("list")
def pr_list(filters: Annotated[list[str] | None, typer.Argument()] = None) -> None:
    """Filter with open, mine, author=, compare=, base=, title=REGEX (AND)."""
    _output(library.list_pull_requests(filters or ()))


@pr_app.command("update")
def pr_update(identifier: str, updates: Annotated[list[str], typer.Argument()]) -> None:
    """Apply compare=, base=, title=, or one of close/draft/ready. Quote each value."""
    _output(library.update_pull_request(identifier, updates))


@pr_app.command("comments")
def pr_comments(identifier: str) -> None:
    """Show a pull request's comments and reply IDs."""
    _output(library.list_comments(identifier))


@app.command("comment")
def comment_command(target: str, comment: str) -> None:
    """Append quoted COMMENT to PR[:COMMENT_ID...]; @- reads stdin."""
    import asyncio

    _output(asyncio.run(library.add_comment(target, _text(comment))))
