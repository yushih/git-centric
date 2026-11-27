"""The gc command line interface."""

from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from git import Repo
from git.exc import GitError
from typer._click.core import Context as ClickContext
from typer.core import TyperCommand, TyperGroup

from . import library
from .library.constants import GC_BRANCH

app = typer.Typer(
    no_args_is_help=True,
    help="Git-centric tools. Commands accept --repo-dir; default: current directory.",
)


RepoDir = Annotated[
    Path | None,
    typer.Option("--repo-dir", help="Repository directory; overrides the current directory."),
]


Defer = Annotated[
    bool,
    typer.Option(
        "-do-not-finalize",
        "--do-not-finalize",
        help="Mark the local metadata tip as not finalized and skip peer contact.",
    ),
]


@app.callback()
def common_options(ctx: typer.Context, do_not_finalize: Defer = False) -> None:
    """Set the default for the whole invocation; leaf commands also accept the flag."""
    ctx.obj = do_not_finalize


def _complete(
    directory: Path,
    defer: bool,
    *,
    optional_repo: bool = False,
    report: bool = False,
    branch: str = GC_BRANCH,
) -> None:
    """Run exactly one completion action and keep ordinary command stdout intact."""
    if defer:
        result = library.defer_finalization(directory)
    elif branch == GC_BRANCH:
        result = library.finalize(directory)
    else:
        result = library.finalize(directory, branch)
    if isinstance(result, library.Failure):
        # Help and web also work before initialization, when there is no tip to finalize.
        if (
            optional_repo
            and not defer
            and result.reason
            in (library.FailureReason.NOT_INITIALIZED, library.FailureReason.NOT_A_REPOSITORY)
        ):
            return
        _output(result)
        return
    for warning in result.value.warnings:
        typer.echo(f"Warning: {warning}", err=True)
    if report:
        _output(result)


class _FinalizingCommand(TyperCommand):
    """Complete repository commands only after their callback returns successfully."""

    def invoke(self, ctx: ClickContext) -> None:
        super().invoke(ctx)
        # init also accepts a positional directory. Resolve the same precedence
        # as the command itself without repeating its directory-selection warning.
        directory = ctx.params.get("repo_dir") or ctx.params.get("directory") or "."
        _complete(Path(directory), ctx.obj or ctx.params["do_not_finalize"])


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
def help_command(
    ctx: typer.Context, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Show the top-level help message."""
    directory = _directory(repo_dir)
    assert ctx.parent is not None
    typer.echo(ctx.parent.get_help())
    _complete(directory, ctx.obj or do_not_finalize, optional_repo=True)


@app.command(cls=_FinalizingCommand)
def init(
    directory: Annotated[
        Path,
        typer.Argument(help="Legacy repository directory; --repo-dir overrides it. Default: cwd."),
    ] = Path("."),
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Create metadata and default roles, registering the Git author as owner."""
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
    ctx: typer.Context,
    host: Annotated[str, typer.Option(help="Address to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535)] = 8000,
    reload: Annotated[bool, typer.Option(help="Reload Python code during development.")] = False,
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Start the FastAPI server and serve the built React frontend."""
    import os

    # Uvicorn reload workers inherit the selected absolute directory.
    directory = _directory(repo_dir).resolve()
    _complete(directory, ctx.obj or do_not_finalize, optional_repo=True)
    previous = os.environ.get("PYGC_WEB_REPO")
    os.environ["PYGC_WEB_REPO"] = str(directory)
    try:
        uvicorn.run("pygc.web:create_app", factory=True, host=host, port=port, reload=reload)
    finally:
        if previous is None:
            os.environ.pop("PYGC_WEB_REPO", None)
        else:
            os.environ["PYGC_WEB_REPO"] = previous


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
                # Browser preconditions are transport fields outside the CLI output contract.
                if isinstance(item, (library.IssueDetails, library.PullRequestDetails)):
                    return {
                        k: v
                        for k, v in asdict(item).items()
                        if k not in {"metadata_tip", "base_tip", "compare_tip", "merge_base"}
                    }
                return asdict(item) if is_dataclass(item) and not isinstance(item, type) else item

            typer.echo(
                json.dumps(
                    [record(item) for item in value] if isinstance(value, list) else record(value),
                    ensure_ascii=False,
                )
            )


sync_app = typer.Typer(
    no_args_is_help=True, help="Synchronize local branches with registered peers."
)
app.add_typer(sync_app, name="sync")


@sync_app.command("push")
def sync_push(
    ctx: typer.Context,
    branch: Annotated[
        str | None,
        typer.Argument(help="Local branch; gc selects metadata. Defaults to the working branch."),
    ] = None,
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Finalize the selected branch, then metadata, and report the selected outcome."""
    directory = _directory(repo_dir)
    defer = ctx.obj or do_not_finalize
    if branch is None:
        context = library.get_repository(directory)
        if isinstance(context, library.Failure):
            _output(context)
            return
        branch = context.value.branch
        if branch is None or context.value.bare:
            _output(
                library.Failure(
                    library.FailureReason.INVALID_ARGUMENT,
                    "Specify a local branch when there is no working branch",
                )
            )
            return
    elif branch == "gc":
        branch = GC_BRANCH
    _complete(directory, defer, branch=branch, report=True)
    if not defer and branch != GC_BRANCH:
        _complete(directory, False)


@pr_app.command("merge")
def pr_merge(
    ctx: typer.Context, identifier: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Check permission, merge compare into base locally, then sync compare and metadata."""
    directory = _directory(repo_dir)
    result = library.merge_pull_request(identifier, directory)
    _output(result)
    if isinstance(result, library.Success):
        defer = ctx.obj or do_not_finalize
        if not defer and result.value.compare != GC_BRANCH:
            _complete(directory, False, branch=result.value.compare)
        _complete(directory, defer)


node_app = typer.Typer(no_args_is_help=True, help="Register and list participating repositories.")
app.add_typer(node_app, name="node")


@node_app.command("add", cls=_FinalizingCommand)
def node_add(name: str, url: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False) -> None:
    """Register NAME with its Git URL or local path."""
    _output(library.add_node(name, url, _directory(repo_dir)))


@node_app.command("list", cls=_FinalizingCommand)
def node_list(repo_dir: RepoDir = None, do_not_finalize: Defer = False) -> None:
    """List registered nodes by name as JSON."""
    _output(library.list_nodes(_directory(repo_dir)))


def _text(value: str) -> str:
    import sys

    return sys.stdin.read() if value == "@-" else value


@pr_app.command("new", cls=_FinalizingCommand)
def pr_new(
    compare: str,
    base: str,
    title: str,
    comment: str = typer.Argument(""),
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
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


@pr_app.command("list", cls=_FinalizingCommand)
def pr_list(
    filters: Annotated[list[str] | None, typer.Argument()] = None,
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
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
    return "\n".join(lines) + "\n" + _conversation_text(details.comments)


def _conversation_text(comments: tuple[library.Comment, ...]) -> str:
    """Render either entity conversation with the same iterative tree layout."""
    lines: list[str] = []
    children: dict[str | None, list[library.Comment]] = {}
    for comment in comments:
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


@pr_app.command("show", no_args_is_help=True, cls=_FinalizingCommand)
def pr_show(
    identifier: Annotated[str, typer.Argument(metavar="PR_ID", help="Pull request ID to show.")],
    text: Annotated[
        bool, typer.Option("--text", help="Show plain text with a comment tree.")
    ] = False,
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
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


@pr_app.command("update", cls=_FinalizingCommand)
def pr_update(
    identifier: str,
    updates: Annotated[list[str], typer.Argument()],
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Apply compare=, base=, title=, draft/ready and close/reopen independently."""
    _output(library.update_pull_request(identifier, updates, directory=_directory(repo_dir)))


@pr_app.command("comments", no_args_is_help=True, cls=_FinalizingCommand)
def pr_comments(
    identifier: Annotated[
        str, typer.Argument(metavar="PR_ID", help="Pull request ID to list comments for.")
    ],
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
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


@comment_app.command("add", cls=_FinalizingCommand)
def comment_command(
    target: str, comment: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Append quoted COMMENT to PR[:COMMENT_ID...]; @- reads stdin."""
    import asyncio

    _output(
        asyncio.run(library.add_comment(target, _text(comment), directory=_directory(repo_dir)))
    )


@comment_app.command("update", cls=_FinalizingCommand)
def update_comment_command(
    target: str, text: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Replace PR_ID:COMMENT_ID text. Quote TEXT; @- reads stdin; empty text clears."""
    _output(library.update_comment(target, _text(text), directory=_directory(repo_dir)))


@comment_app.command("delete", cls=_FinalizingCommand)
def delete_comment_command(
    target: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Delete PR_ID:COMMENT_ID and its reply links. Main must be cleared instead."""
    _output(library.delete_comment(target, directory=_directory(repo_dir)))


issue_app = typer.Typer(no_args_is_help=True, help="Create, list, update and discuss issues.")
issue_comment_app = typer.Typer(no_args_is_help=True, help="Add, update or delete issue comments.")
app.add_typer(issue_app, name="issue")
issue_app.add_typer(issue_comment_app, name="comment")


@issue_app.command("new", cls=_FinalizingCommand)
def issue_new(
    title: str,
    comment: str = typer.Argument(""),
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Create an open issue: TITLE [COMMENT]. Quote text; @- reads stdin."""
    import asyncio

    _output(
        asyncio.run(library.create_issue(title, _text(comment), directory=_directory(repo_dir)))
    )


@issue_app.command("list", cls=_FinalizingCommand)
def issue_list(
    filters: Annotated[list[str] | None, typer.Argument()] = None,
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """List all issues, or AND filters: open, closed, mine, author=, title=REGEX."""
    _output(library.list_issues(filters or (), directory=_directory(repo_dir)))


@issue_app.command("update", cls=_FinalizingCommand)
def issue_update(
    identifier: str,
    updates: Annotated[list[str], typer.Argument()],
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Apply title=, close or reopen. Combined title/state updates are atomic."""
    _output(library.update_issue(identifier, updates, directory=_directory(repo_dir)))


@issue_app.command("show", no_args_is_help=True, cls=_FinalizingCommand)
def issue_show(
    identifier: str,
    text: Annotated[bool, typer.Option("--text", help="Show details and a reply tree.")] = False,
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Show issue fields and all comments as JSON; --text displays a reply tree."""
    result = library.show_issue(identifier, directory=_directory(repo_dir))
    if text and isinstance(result, library.Success):
        issue = result.value.issue
        typer.echo(
            "\n".join(
                [
                    f"Issue {issue.id}",
                    f"Title: {issue.title}",
                    f"Author: {issue.author}",
                    f"Created: {issue.created_at}",
                    f"Closed: {str(issue.closed).lower()}",
                    "",
                    "Comments:",
                    _conversation_text(result.value.comments),
                ]
            )
        )
    else:
        _output(result)


@issue_app.command("comments", no_args_is_help=True, cls=_FinalizingCommand)
def issue_comments(
    identifier: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """List issue comments as JSON, including exact text and reply IDs."""
    _output(library.list_issue_comments(identifier, directory=_directory(repo_dir)))


@issue_comment_app.command("add", cls=_FinalizingCommand)
def issue_comment_add(
    target: str, text: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Append TEXT to ISSUE_ID[:COMMENT_ID...]. Quote text; @- reads stdin."""
    import asyncio

    _output(
        asyncio.run(library.add_issue_comment(target, _text(text), directory=_directory(repo_dir)))
    )


@issue_comment_app.command("update", cls=_FinalizingCommand)
def issue_comment_update(
    target: str, text: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Replace ISSUE_ID:COMMENT_ID text; @- reads stdin; empty text clears."""
    _output(library.update_issue_comment(target, _text(text), directory=_directory(repo_dir)))


@issue_comment_app.command("delete", cls=_FinalizingCommand)
def issue_comment_delete(
    target: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Delete ISSUE_ID:COMMENT_ID and incoming reply links; main cannot be deleted."""
    _output(library.delete_issue_comment(target, directory=_directory(repo_dir)))


access_app = typer.Typer(no_args_is_help=True, help="Manage registered users and roles.")
app.add_typer(access_app, name="access")
role_app = typer.Typer(no_args_is_help=True, help="Manage role metadata and membership.")
user_app = typer.Typer(no_args_is_help=True, help="Register and list user public keys.")
access_app.add_typer(role_app, name="role")
access_app.add_typer(user_app, name="user")


@user_app.command("add", cls=_FinalizingCommand)
def user_add(
    name: str,
    public_key: str,
    role: Annotated[
        list[str] | None, typer.Option("--role", help="Initial role (repeatable).")
    ] = None,
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Register a named user with a quoted OpenSSH Ed25519 public key."""
    _output(library.add_user(name, public_key, roles=role or (), directory=_directory(repo_dir)))


@user_app.command("list", cls=_FinalizingCommand)
def user_list(repo_dir: RepoDir = None, do_not_finalize: Defer = False) -> None:
    """List registered users and their public keys."""
    _output(library.list_users(directory=_directory(repo_dir)))


@role_app.command("list", cls=_FinalizingCommand)
def role_list(repo_dir: RepoDir = None, do_not_finalize: Defer = False) -> None:
    """List roles with their metadata and assigned users."""
    _output(library.list_roles(directory=_directory(repo_dir)))


@role_app.command("create", cls=_FinalizingCommand)
def role_create(
    name: str,
    metadata: Annotated[str, typer.Argument()] = "",
    repo_dir: RepoDir = None,
    do_not_finalize: Defer = False,
) -> None:
    """Create a role with optional text metadata."""
    _output(library.create_role(name, metadata, directory=_directory(repo_dir)))


@role_app.command("remove", cls=_FinalizingCommand)
@role_app.command("delete", cls=_FinalizingCommand)
def role_delete(name: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False) -> None:
    """Delete an empty role."""
    _output(library.delete_role(name, directory=_directory(repo_dir)))


@role_app.command("assign", cls=_FinalizingCommand)
def role_assign(
    user: str, role: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Assign a role to a user. Quote * to select all users."""
    _output(library.assign_role(user, role, directory=_directory(repo_dir)))


@role_app.command("unassign", cls=_FinalizingCommand)
def role_unassign(
    user: str, role: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Remove a role from a user. Quote * to select all users."""
    _output(library.unassign_role(user, role, directory=_directory(repo_dir)))


@node_app.command("update-url", cls=_FinalizingCommand)
def change_node_url(
    name: str, url: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Change a registered node endpoint."""
    _output(library.change_node_url(name, url, directory=_directory(repo_dir)))


@node_app.command("remove", cls=_FinalizingCommand)
def remove_node(name: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False) -> None:
    """Remove a registered node."""
    _output(library.remove_node(name, directory=_directory(repo_dir)))


@role_app.command("update-metadata", cls=_FinalizingCommand)
def change_role_metadata(
    name: str, metadata: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Replace metadata for an existing role."""
    _output(library.change_role_metadata(name, metadata, directory=_directory(repo_dir)))


@user_app.command("update-key", cls=_FinalizingCommand)
def change_user_public_key(
    name: str, public_key: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False
) -> None:
    """Replace a registered user’s Ed25519 public key."""
    _output(library.change_user_public_key(name, public_key, directory=_directory(repo_dir)))


@user_app.command("delete", cls=_FinalizingCommand)
def delete_user(name: str, repo_dir: RepoDir = None, do_not_finalize: Defer = False) -> None:
    """Delete a registered user and their memberships."""
    _output(library.delete_user(name, directory=_directory(repo_dir)))
