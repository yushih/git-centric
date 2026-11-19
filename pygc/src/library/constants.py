"""Reserved Git-centric names and on-disk format constants.

Keeping these together makes the format visible in one place. In particular,
the branch name and directory name happen to match, but have distinct meanings.
"""

GC_BRANCH = "__git-centric__"
GC_REF = f"refs/heads/{GC_BRANCH}"
GC_DIRECTORY = "__git-centric__"
GC_KEEP_FILE = ".gitkeep"
GC_INITIAL_COMMIT_MESSAGE = "Initialize Git-centric metadata"

# These are Git tree-entry modes, not the permissions of a temporary disk file.
GIT_REGULAR_FILE_MODE = "100644"
GIT_DIRECTORY_MODE = "040000"
