#!/usr/bin/env bash
# Stop hook — refresh HANDOFF.md so the next session can resume cheaply.
#
# Reads {session_id, transcript_path?, ...} on stdin; writes <project-root>/HANDOFF.md.
# All failures are silent: this hook must never block Claude.

set -u

PROJECT_ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
HANDOFF="$PROJECT_ROOT/HANDOFF.md"

INPUT=$(cat 2>/dev/null || echo '{}')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)

cd "$PROJECT_ROOT" 2>/dev/null || exit 0

BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
HEAD_LINE=$(git log -1 --oneline 2>/dev/null || echo "(no commits)")
RECENT=$(git log -3 --pretty='- %h %s' 2>/dev/null || echo "(no commits)")
STATUS=$(git status --short 2>/dev/null)
TS=$(date '+%Y-%m-%d %H:%M:%S %z')

# Resolve JSONL path: prefer transcript_path from input; else search by session_id.
JSONL=""
if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
  JSONL="$TRANSCRIPT"
elif [ -n "$SESSION_ID" ]; then
  JSONL=$(find "$HOME/.claude/projects" -name "${SESSION_ID}.jsonl" -type f 2>/dev/null | head -1)
fi

LAST_PROMPTS=""
if [ -n "$JSONL" ] && [ -f "$JSONL" ]; then
  LAST_PROMPTS=$(jq -sr '
    [.[]
      | select(.type == "user" and .message.role == "user" and (.message.content | type) == "string")
      | .message.content
      | gsub("\\s+"; " ")
    ]
    | .[-3:]
    | map("- " + (if length > 240 then .[0:237] + "..." else . end))
    | join("\n\n")
  ' "$JSONL" 2>/dev/null)
fi

{
  echo "# Handoff"
  echo
  echo "_Auto-refreshed by Stop hook. Last updated: ${TS}_"
  echo
  echo "## Branch"
  echo
  echo "\`$BRANCH\` — HEAD: $HEAD_LINE"
  echo
  echo "## Recent commits"
  echo
  echo "$RECENT"
  echo
  echo "## Working tree"
  echo
  if [ -z "$STATUS" ]; then
    echo "Clean."
  else
    echo '```'
    echo "$STATUS"
    echo '```'
  fi
  if [ -n "$LAST_PROMPTS" ]; then
    echo
    echo "## Last user prompts (this session)"
    echo
    echo "$LAST_PROMPTS"
  fi
  echo
  echo "## Notes"
  echo
  echo "_(Edit this section manually to leave a resume hint for the next session.)_"
} > "$HANDOFF" 2>/dev/null

exit 0
