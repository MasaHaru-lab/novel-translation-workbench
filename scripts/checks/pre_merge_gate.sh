#!/usr/bin/env bash
# Pre-merge gate for novel-translation-workbench.
#
# Purpose: a lightweight local check that must pass before a work/<topic>
# branch is merged back into main. Designed to run offline, without any
# real model backend, without contacting Fishhead/3090, and without
# requiring an active venv.
#
# Exit codes:
#   0 — PASS (all checks ok; merge is permitted from a workflow standpoint)
#   1 — FAIL (at least one check failed; do not merge)
#
# Checks (all local, read-only):
#   1. Repo state: must be inside the project git repo.
#   2. Working tree: no uncommitted changes (tracked files clean).
#   3. Generated outputs not tracked: data/output/, data/exports/,
#      and outputs/ must not contain git-tracked files.
#   4. Branch hint: warn (not fail) when running on `main`. Real merge
#      gating happens when invoked on a work/<topic> branch.
#
# This script intentionally does NOT:
#   - run the test suite (operator runs `python -m pytest app/tests/` separately)
#   - call any model backend
#   - require Fishhead/3090 reachability
#   - mutate git state, push, or merge

set -u

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT" || { echo "FAIL: cannot cd to repo root"; exit 1; }

failures=0
warnings=0

fail() { echo "FAIL: $*"; failures=$((failures + 1)); }
warn() { echo "WARN: $*"; warnings=$((warnings + 1)); }
ok()   { echo "OK:   $*"; }

# 1. Repo state
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  fail "not inside a git repository"
  echo
  echo "RESULT: FAIL"
  exit 1
fi
ok "inside git repo at $REPO_ROOT"

# 2. Working tree clean
dirty="$(git status --porcelain)"
if [ -n "$dirty" ]; then
  fail "working tree has uncommitted changes:"
  echo "$dirty" | sed 's/^/      /'
else
  ok "working tree clean"
fi

# 3. Generated-output paths must not be git-tracked
tracked_outputs="$(git ls-files data/output data/exports outputs 2>/dev/null || true)"
if [ -n "$tracked_outputs" ]; then
  fail "generated-output paths are tracked in git (should be ignored):"
  echo "$tracked_outputs" | sed 's/^/      /'
else
  ok "no generated-output paths tracked (data/output, data/exports, outputs)"
fi

# 4. Branch hint
current_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")"
case "$current_branch" in
  main)
    warn "currently on main; pre-merge gate is intended to run on work/<topic> before merge"
    ;;
  work/*)
    ok "on work branch: $current_branch"
    ;;
  "")
    warn "could not determine current branch (detached HEAD?)"
    ;;
  *)
    warn "current branch '$current_branch' does not match main or work/<topic>"
    ;;
esac

echo
echo "Recommended next steps before merging:"
echo "  - Activate venv:    source venv/bin/activate"
echo "  - Run test suite:   python -m pytest app/tests/"
echo "  - Squash-merge into main once tests pass."
echo

if [ "$failures" -gt 0 ]; then
  echo "RESULT: FAIL ($failures error(s), $warnings warning(s))"
  exit 1
fi

echo "RESULT: PASS ($warnings warning(s))"
exit 0
