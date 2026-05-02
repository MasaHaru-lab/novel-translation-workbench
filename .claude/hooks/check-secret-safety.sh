#!/usr/bin/env bash
# PreToolUse guard: block Bash commands that would expose secrets.
#
# Scans the command string for patterns that read or dump secret material:
#   - cat/tail/head/less/more on .env* or credential files
#   - printenv, env (bare), `set` (bare — dumps shell variables)
#   - echo/variable expansion patterns for *KEY, *TOKEN, *SECRET, *PASSWORD
#   - source/export on .env* files
#
# CLAUDE_TOOL_NAME and CLAUDE_TOOL_PARAMS are set by Claude Code runtime.
# If unavailable (testing outside CC), the script passes silently.

set -u

TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
TOOL_PARAMS="${CLAUDE_TOOL_PARAMS:-}"

# If not running inside Claude Code, pass silently
if [ -z "$TOOL_NAME" ] || [ -z "$TOOL_PARAMS" ]; then
  echo '{}'
  exit 0
fi

# Only check Bash commands
if [ "$TOOL_NAME" != "Bash" ]; then
  echo '{}'
  exit 0
fi

# Try to extract the command string from JSON params using jq or python
CMD=""
if command -v jq >/dev/null 2>&1; then
  CMD=$(echo "$TOOL_PARAMS" | jq -r '.command // .input.command // ""' 2>/dev/null)
elif command -v python3 >/dev/null 2>&1; then
  CMD=$(python3 -c "
import json,sys
try:
    p = json.loads('${TOOL_PARAMS//\'/\'\"\'\"\'}')
    sys.stdout.write(p.get('command','') or p.get('input',{}).get('command',''))
except:
    pass
" 2>/dev/null)
fi

if [ -z "$CMD" ]; then
  # Fallback: check the raw params for dangerous patterns anyway
  BLOCKED=$(echo "$TOOL_PARAMS" | grep -qE '(\.env[^"\'\'']|printenv|"env"|\$.*KEY|\$.*TOKEN|\$.*SECRET|\$.*PASSWORD)' 2>/dev/null && echo "1" || echo "0")
  if [ "$BLOCKED" = "1" ]; then
    cat >&2 <<'MSG'
[check-secret-safety] BLOCKED: Command appears to read secret/credential files or environment variables.

Claude must never read, display, or echo API keys, tokens, or credentials.
Use redacted presence checks instead:
  echo "VAR_NAME=${VAR_NAME:+set (hidden)}unset"
  test -f .env.local && echo "ENV_LOCAL_PRESENT" || echo "ENV_LOCAL_MISSING"

MSG
    echo '{"permissionDecision":"deny","message":"Command blocked by secret-safety guard. See stderr for details."}'
    exit 0
  fi
  echo '{}'
  exit 0
fi

# ── Pattern checks ──────────────────────────────────────────────────────────

# Commands that read/display .env* files (cat, less, more, head, tail, nl, bat, xdg-open, open)
if echo "$CMD" | grep -qE '(^|;|&&|\|)\s*(cat|less|more|head|tail|bat|xdg-open)\s+.*\.env'; then
  cat >&2 <<'MSG'
[check-secret-safety] BLOCKED: Reading .env* files via cat/less/head/tail is prohibited.
Use a redacted presence check instead:
  test -f .env.local && echo "ENV_LOCAL_PRESENT" || echo "ENV_LOCAL_MISSING"
MSG
  echo '{"permissionDecision":"deny","message":"Reading .env files is blocked. See stderr for safe alternative."}'
  exit 0
fi

# printenv or bare `env` (full env dump)
if echo "$CMD" | grep -qE '(^|;|&&|\|)\s*(printenv)\b'; then
  cat >&2 <<'MSG'
[check-secret-safety] BLOCKED: `printenv` dumps all environment variables including secrets.
Check individual expected vars with redacted commands only:
  echo "VAR_NAME=${VAR_NAME:+set (hidden)}unset"
MSG
  echo '{"permissionDecision":"deny","message":"printenv is blocked. See stderr for safe alternative."}'
  exit 0
fi

# Bare `env` (the command `env` without arguments — dumps all env vars)
if echo "$CMD" | grep -qE '(^|;|&&)\s*env\s*(\||;|&&|$|#)'; then
  cat >&2 <<'MSG'
[check-secret-safety] BLOCKED: bare `env` dumps all environment variables including secrets.
Check individual expected vars with redacted commands only:
  echo "VAR_NAME=${VAR_NAME:+set (hidden)}unset"
MSG
  echo '{"permissionDecision":"deny","message":"Bare `env` is blocked. See stderr for safe alternative."}'
  exit 0
fi

# Bare `set` (dumps shell variables — includes env + local vars)
if echo "$CMD" | grep -qE '(^|;|&&)\s*set\s*(\||;|&&|$|#)'; then
  cat >&2 <<'MSG'
[check-secret-safety] BLOCKED: bare `set` dumps all shell variables including any secrets.
Check individual expected vars with redacted commands only.
MSG
  echo '{"permissionDecision":"deny","message":"Bare `set` is blocked. See stderr for safe alternative."}'
  exit 0
fi

# Variable expansion of secrets in echo/printf.
# Two separate patterns: (a) $VAR (no braces — always a direct expansion);
# (b) ${VAR} (exact, no modifier — direct expansion). ${VAR:+value} with
# modifiers like :+ is SAFE (it only evaluates to the literal alternative,
# never the actual variable value) and must be allowed for redacted checks.
# NOTE: patterns must be SINGLE-quoted to prevent bash $() command substitution.
SECRET_VARS='DEEPSEEK_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|MODEL_BACKEND_URL|TRANSLATION_SERVICE_URL|DEEPSEEK_BASE_URL|ANTHROPIC_AUTH_TOKEN'
if echo "$CMD" | grep -qE '\$('"${SECRET_VARS}"')' || echo "$CMD" | grep -qE '\$\{('"${SECRET_VARS}"')\}'; then
  cat >&2 <<'MSG'
[check-secret-safety] BLOCKED: Expanding a known secret/token/credential variable.
Use a redacted presence check:
  echo "VAR_NAME=${VAR_NAME:+set (hidden)}unset"
MSG
  echo '{"permissionDecision":"deny","message":"Variable expansion of known secret names is blocked. See stderr for safe alternative."}'
  exit 0
fi

# grep -v patterns on .env* — dangerous because filtered output still shows key=value pairs
if echo "$CMD" | grep -qE '(cat|grep)\s+.*\.env[^\s]*.*\|.*grep -v'; then
  cat >&2 <<'MSG'
[check-secret-safety] BLOCKED: grep-based filtering on .env* files is unreliable.
Secrets leak through grep -v filters. Use a redacted presence check instead:
  test -f .env.local && echo "ENV_LOCAL_PRESENT" || echo "ENV_LOCAL_MISSING"
MSG
  echo '{"permissionDecision":"deny","message":"grep filtering on .env files is blocked as unreliable. See stderr for safe alternative."}'
  exit 0
fi

# Sourcing .env files
if echo "$CMD" | grep -qE '(source|\.)\s+\.env'; then
  cat >&2 <<'MSG'
[check-secret-safety] BLOCKED: Sourcing .env* files imports secrets into the shell.
Check individual expected vars with redacted commands.
MSG
  echo '{"permissionDecision":"deny","message":"Sourcing .env files is blocked. See stderr for safe alternative."}'
  exit 0
fi

echo '{}'
exit 0
