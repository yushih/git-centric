The Python library, CLI, and React web interface skeleton is in [pygc](pygc/README.md).

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
[L1]In the "pull-requests" directory, each open pull request is represented by a directory named "c~>b#id:t", where c is the compare branch name, b is the base branch name, id is an unique id and t is the title. If the name is prefixed with "[closed]", it is closed. If c is an ancestor of b, the pull request is considered to have been merged. If the name is prefixed with "[draft]", it is a draft pull request.

(L2)To list pull requests, run
```gc pr list```


## Pull request conversation
(L1)Each comment under a pull request is represented by the file "comment-id" where id is a unique id. The initial comment has id "main". Comment names can have one or more suffix ":id" where id is the comment that this comment addresses. Only the original author should update a comment file.

(L2)
To create a pull request, run
```gc pr new <compare branch> <base branch> <title> <comment>```
If <comment> is "@-", it will be read from stdin.

To show comments, run
```gc pr comments <id>```

To add a comment, run
```gc comment <pr id> <comment>```
or
```gc comment <pr id>:<comment id> <comment>```
If <comment> is "@-", it will be read from stdin.




