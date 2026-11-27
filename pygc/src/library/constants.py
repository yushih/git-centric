"""Reserved Git-centric names and on-disk format constants.

Keeping these together makes the format visible in one place. In particular,
the branch name and directory name happen to match, but have distinct meanings.
"""

GC_BRANCH = "__git-centric__"
GC_REF = f"refs/heads/{GC_BRANCH}"
GC_DIRECTORY = "__git-centric__"
GC_KEEP_FILE = ".gitkeep"
GC_INITIAL_COMMIT_MESSAGE = "initialize Git-centric metadata"

# These are Git tree-entry modes, not the permissions of a temporary disk file.
GIT_REGULAR_FILE_MODE = "100644"
GIT_EXECUTABLE_FILE_MODE = "100755"
GIT_DIRECTORY_MODE = "040000"

PR_DIRECTORY = "pull-requests"
PR_CLOSED = "[closed]"
PR_DRAFT = "[draft]"
COMMENT_PREFIX = "comment-"
COMMENT_MAIN = "main"
PR_COMPARE_SEPARATOR = "~>"
PR_ID_SEPARATOR = "#"
PR_TITLE_SEPARATOR = ":"

ISSUE_DIRECTORY = "issues"
ISSUE_CLOSED = "[closed]"
ISSUE_TITLE_SEPARATOR = ":"

NODES_DIRECTORY = "nodes"
NODE_URL_FILE = "URL"

GIT_NOTES_REF = "refs/notes/commits"
FINALIZE_TEMP_PREFIX = "refs/notes/gc-finalize-"

ACCESS_DIRECTORY = "access-control"
ROLES_DIRECTORY = "roles"
USERS_DIRECTORY = "users"
PUBLIC_KEY_FILE = "pk-Ed25519"
PRIVATE_KEY_FILE = ".__git-centric__sk-Ed25519"

OWNER_ROLE = "owner"
DEFAULT_ROLES = (OWNER_ROLE, "admin", "ci", "merger")

RULES_DIRECTORY = "rules"
RULE_PATTERN = "rule-*.py"

ACTIONS_FILE = "actions.py"
