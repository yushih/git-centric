Git-centric (GC thereafter) is a decentralized local-first code forge to support the familiar git workflows without depending on centralized git hosting platforms (CG thereafter). The design goal of GC is low migration friction from CG.

GC has a 3 layer architecture:
1. Layer 1 (L1 thereafter) is the data format layer consisting of definitions of directory structures and file formats.
2. Layer 2 is the reference implementation. Currently, there is a Python based CLI implementation in [pygc/src](pygc/src). This is meant to be used by CLI lovers, CI/CD tools and agents.
3. Layer 3 is the reference Web shell on top of layer 2 to expose the familiar Web UI. You can run the Web server on localhost and work on your git repo in your browser.

Also, there is simple gossip protocol to support decentralization.

## Advantages over CG:
1. the evolving history left by the workflow is preserved, instead of only the history of code changes.
2. open source, self-hosted and super simple design.
3. therefore, extendable. These days everybody wants to extend their system with agentic AI. GC doesn't get in the way.


## Using the CLI

See [installation and setup](pygc/README.md#requirements-and-setup) to install
`gc`. With the Python environment active, run the commands below directly;
otherwise use `uv run gc` from `pygc/`.

```sh
gc help                  # list commands
gc pr --help             # list pull request commands
gc comment --help        # list comment commands
gc pr show --help        # get help for a specific command
```

Repository commands use the current directory by default. To select another
repository, add `--repo-dir=/path/to/repo` after the command:

```sh
gc init --repo-dir=/path/to/repo
gc pr list --repo-dir=/path/to/repo
```

If both locations are initialized but refer to different repositories, `gc`
prints a warning and uses `--repo-dir`. Quote titles, comments and filter values
that contain spaces. Pull request and comment commands output JSON by default;
`gc pr show --text` provides a readable alternative.


## Fundamental data structure

(L1)All GC data is stored in the "__git-centric__" branch under the "__git-centric__" directory. All file paths below are relative to this directory.

(L2)To initialize GC, run:
```gc init```
in the working directory. The Git repository must already exist (`git init`
creates one). Initialization preserves your current branch and working files.


## Pull requests
(L1)In the "pull-requests" directory, each open pull request is represented by a directory named "c~>b#id:t", where c is the compare branch name, b is the base branch name, id is an unique id and t is the title. If the name is prefixed with the status flag "[closed]", it is closed. If c is an ancestor of b, the pull request is considered to have been merged. If the name is prefixed with the status flag "[draft]", it is a draft pull request. Draft/ready, open/closed, and merged/not merged are independent: all eight combinations are valid. Both stored flags may be present, written as "[closed][draft]"; merged is determined by ancestry regardless of these flags. The author of the pull requrest is the creator of the pull request directory as recorded in git. The creation time the pull request is the timestamp of the commit that creates the directory.

(L2)To list pull requests, run

```gc pr list <optional filters>```

This command outputs PR IDs, titles, compare/base branches, author, creation time,
and draft/closed/merged flags. Filters combine with AND.

<optional filters> are one or more of:

```open```, filters out draft, closed and merged

```mine```

```author=<author>```

```compare=<branch name>```

```base=<branch name>```

```title=<regular expression>```

To create a pull request, run

```gc pr new <compare branch> <base branch> <title> [comment]```

Both branches must exist locally. Omit the optional comment for an empty
description, or use `@-` to read it from stdin.


To inspect one pull request, including its conversation and merge analysis, run:

```sh
gc pr show PR_ID
gc pr show PR_ID --text
```

The default JSON includes the PR record, all comments, merge-conflict status,
conflicting file paths, and changed-file details. File changes are measured on
the compare branch since its merge base with the base branch. Added, modified,
deleted and type-changed files are labeled; renamed/copied files include their
old and new paths and similarity percentage.

`--text` shows the same information with an indented comment tree. A comment
addressing several others is placed beneath its first reply target and explicitly
lists all targets. Merge analysis requires Git 2.38+ and leaves your checkout
and index untouched. Missing branches or unrelated histories produce an unknown
merge status with an explanation.

To modify a pull request, run

```gc pr update <pr id> <updates>```

where <updates> is one or more of:

```compare=<new compare branch name>```

```base=<new base branch name>```

```title=<new title>```

```close```, adds "[closed]" without changing draft status

```reopen```, removes "[closed]" without changing draft status

```draft```, makes the pull request draft without changing closed status

```ready```, removes the "[draft]" status without changing closed status

Actions on different states may be combined (for example, `close draft`).
Contradictory pairs `close reopen` and `draft ready` are errors.


## Pull request conversation
(L1)Each comment under a pull request is represented by the file "comment-id" where id is a unique id. The initial comment has id "main". Comment names can have one or more suffix ":id" where id is the comment that this comment addresses. Comment edits and deletions remain recorded in Git history. The current local
CLI does not restrict editing to the original author.

(L2)
To show comments, run

```gc pr comments <pr id>```

This lists comment IDs, text and reply targets as JSON. `gc pr comments` without
an ID.

To add a comment, run

```gc comment <pr id> <comment>```

or

```gc comment <pr id>:<comment id> <comment>```

which creates a comment addressing existing <comment id>.

If <comment> is "@-", it will be read from stdin.

You can also use the explicit `add` command and address several comments:

```sh
gc comment add PR_ID "Another comment"
gc comment PR_ID:main "Reply to the description"
gc comment PR_ID:COMMENT_ID:OTHER_COMMENT_ID "Reply to both"
```

To replace a comment's text or delete it:

```sh
gc comment update PR_ID:COMMENT_ID "Revised text"
gc comment update PR_ID:COMMENT_ID @-  # read replacement text from stdin
gc comment delete PR_ID:COMMENT_ID
```

Updating text preserves the comment ID and its reply targets. Deletion keeps
replies and their text, removing their links to the deleted comment. The `main`
description cannot be deleted; clear it with `gc comment update PR_ID:main ""`.
Previous contents remain available in Git history.

## Web interface

```sh
gc web
gc web --host 127.0.0.1 --port 9000
gc web --reload  # reload the server during development
```

`gc web` starts the local web server at http://127.0.0.1:8000 by default. Build
the frontend using the [setup instructions](pygc/README.md#requirements-and-setup)
first. The current web interface is a greeting demo; pull request and comment
operations are available through the CLI.
