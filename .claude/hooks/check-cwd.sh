#!/usr/bin/env bash
# PreToolUse guard: ensure the tool runs from inside the project tree.
# Blocks Bash/Edit/Write/MultiEdit invocations that would operate outside
# $CLAUDE_PROJECT_DIR (e.g. accidentally creating files in $HOME).

set -u

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$PROJECT_DIR" ]; then
  exit 0
fi

CWD="$(pwd -P 2>/dev/null || pwd)"
PROJECT_REAL="$(cd "$PROJECT_DIR" 2>/dev/null && pwd -P)"

if [ -z "$PROJECT_REAL" ]; then
  exit 0
fi

case "$CWD" in
  "$PROJECT_REAL"|"$PROJECT_REAL"/*)
    exit 0
    ;;
esac

cat >&2 <<EOF
[check-cwd] BLOCKED: cwd is outside the project root.
  cwd     : $CWD
  project : $PROJECT_REAL

cd into the project root before retrying. Do NOT create files at \$HOME
or any parent directory. If you genuinely need to operate outside the
project, ask the user first.
EOF
exit 2
