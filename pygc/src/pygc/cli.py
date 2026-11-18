"""The gc command line interface."""

from typing import Annotated

import typer
import uvicorn

from pygc import library

app = typer.Typer(no_args_is_help=True, help="Git-centric command line tools.")


@app.command("help")
def help_command(ctx: typer.Context) -> None:
    """Show the top-level help message."""
    assert ctx.parent is not None
    typer.echo(ctx.parent.get_help())


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
