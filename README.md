The Python library, CLI, and React web interface skeleton is in [pygc](pygc/README.md).

Contributor and agent workflow: [AGENTS.md](AGENTS.md) and
[spec-driven development](specs/README.md). These distinguish the current Python
implementation from the broader product vision below.

Git-centric (GC thereafter) is a decentralized platform to let you and your team do whatever you do on centralized git hosting platforms (CG thereafter) without CG. GC has a 3 layer architecture:
1. Layer 1 (L1 thereafter) is the standard layer consisting of definitions of directory structures and file formats.
2. Layer 2 is the reference implementation in Bash scripts. With layer 2,  GC can be used in the command line interface.
3. Layer 3 is the reference Web implementation on top of layer 2. With layer 3, GC exposes a familiar Web interface.

Also, there is simple gossip protocol to support decentralization.

## Advantages over CG:
1. the evolving history the repo is preserved, instead of only the history of code changes.
2. open source and self-hosted.
3. therefore, extendable. These days everybody wants to extend their system with agentic AI. GC doesn't get in the way.


## Fundamental data structure

(L1)All GC data is stored in the "__git-centric__" branch under the "__git-centric__" directory. All file paths below are relative to this directory.

(L2)To initialize GC, run:
```gc init```
in the working directory.


## Pull requests
[L1]In the "pull-requests" directory, each open pull request is represented by a directory named "c~>b#id:t", where c is the compare branch name, b is the base branch name, id is an unique id and t is the title. If the name is prefixed with the status flag "[closed]", it is closed. If c is an ancestor of b, the pull request is considered to have been merged. If the name is prefixed with the status flag "[draft]", it is a draft pull request. Draft/ready, open/closed, and merged/not merged are independent: all eight combinations are valid. Both stored flags may be present, written as "[closed][draft]"; merged is determined by ancestry regardless of these flags. The author of the pull requrest is the creator of the pull request directory as recorded in git. The creation time the pull request is the timestamp of the commit that creates the directory.

(L2)To list pull requests, run

```gc pr list <optional filters>```

this command outputs the pr id, title, compare and base branch, auther and creation time.

<optional fitlers> are one or more of:

```open```, filters out draft, closed and merged

```mine```

```author=<author>```

```compare=<branch name>```

```base=<branch name>```

```title=<regular expression>```

To create a pull request, run

```gc pr new <compare branch> <base branch> <title> <comment>```

If the optional <comment> is "@-", it will be read from stdin.

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
JSON uses independent `draft`, `closed`, and `merged` booleans. The `open` list
filter still excludes any draft, closed, or merged PR.

## Pull request conversation
(L1)Each comment under a pull request is represented by the file "comment-id" where id is a unique id. The initial comment has id "main". Comment names can have one or more suffix ":id" where id is the comment that this comment addresses. Only the original author should update a comment file.

(L2)
To show comments, run

```gc pr comments <id>```

To add a comment, run

```gc comment <pr id> <comment>```

or

```gc comment <pr id>:<comment id> <comment>```

which creates a comment addressing existing <comment id>.

If <comment> is "@-", it will be read from stdin.
