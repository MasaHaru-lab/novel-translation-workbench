# Hook Safety Review

A survey of all hook layers protecting this project, their current posture,
identified risks, and recommendations for future changes.

**Author:** Claude Code (2026-05-02)  
**Context:** Single-batch documentation/architecture alignment task.  
**Rule:** This document describes observed behavior and separates it clearly from
recommended future changes. No hooks were modified as part of this review.

---

## 1. Hook Inventory

### 1.1 Project-level hooks (`.claude/settings.json`)

Both are `PreToolUse` hooks — they fire before every matching tool invocation.

| Matcher | Script | What it does | Active |
|---|---|---|---|
| `Skill` | `.claude/hooks/check-gstack.sh` | Blocks any Skill tool use if `~/.claude/skills/gstack/bin/` is missing | Yes |
| `Bash\|Edit\|Write\|MultiEdit` | `.claude/hooks/check-cwd.sh` | Blocks file/tool operations when `pwd` is outside `$CLAUDE_PROJECT_DIR` | Yes |

### 1.2 Global hooks (`~/.claude/settings.json`)

| Event | Script | What it does | Active |
|---|---|---|---|
| `SessionStart` | `~/.claude/skills/gstack/bin/gstack-session-update` | Auto-pulls gstack repo in background (throttled 1/hr) | Yes |
| `Stop` | `~/.claude/hooks/save-to-obsidian.sh` | Saves session metadata to Obsidian vault | Yes |
| `PreToolUse` | *(empty array)* | — | No |
| `PostToolUse` | *(empty array)* | — | No |
| `PostToolUseFailure` | *(empty array)* | — | No |

### 1.3 Unregistered OMC hooks (`~/.claude/hooks/`)

The following scripts exist on disk but are NOT registered in any
`settings.json` hooks array (project or global). They are **not actively loaded**
by the Claude Code harness under the current configuration.

| File | Intended purpose | Status |
|---|---|---|
| `pre-tool-use.mjs` | OMC delegation enforcement (warns on direct source edits); tracks skill active state for Stop-hook protection | Unregistered — not loaded |
| `post-tool-use.mjs` | Processes `<remember>` tags from agent output; manages `.omc/notepad.md` | Unregistered — not loaded |
| `post-tool-use-failure.mjs` | Tracks tool failures for retry guidance (writes `last-tool-error.json`) | Unregistered — not loaded |
| `persistent-mode.mjs` | Enforces continuation for ralph/autopilot/ultrawork/ultraqa/team modes | Unregistered — not loaded |
| `keyword-detector.mjs` | Auto-detects magic keywords (ralph, autopilot, ccg, etc.) and invokes skills | Unregistered — not loaded |
| `session-start.mjs` | Restores persistent-mode state when session starts | Unregistered — not loaded |
| `code-simplifier.mjs` | Code simplification utility (supporting script, not a hook) | N/A |

**Risk note:** Because these are unregistered, any protection they were designed
to provide (delegation enforcement, mode continuation, error tracking) is not
active. If they are expected to be active, this represents a significant gap
between intended and actual safety posture.

### 1.4 Pre-merge gate (`scripts/checks/pre_merge_gate.sh`)

This is a manual script, not a hook. Runs locally before merging.

| Check | Enforces |
|---|---|
| In-git-repo | Yes |
| Working tree clean | Yes (tracked files only) |
| Generated outputs untracked | Yes (data/output/, data/exports/, outputs/) |
| Branch hint | Warn-only for non-work/* branches |

This script has no model backend dependency and is intentionally offline.

---

## 2. What Each Active Hook Protects

### `check-gstack.sh` (Skill matcher)

**Protects against:** Invoking skills (review, qa, ship, browse, etc.) without
gstack installed. Since skills are how most higher-order work gets done, this
ensures gstack is always present as a prerequisite.

**Failure mode:** If gstack is installed but broken (e.g., binary missing but
skills dir exists), the hook passes and skills fire with no further guard. In
practice, gstack's own self-check handles deeper validation.

**Scope note:** This hook uses a `matcher: "Skill"` with no args restriction,
so it covers ALL skill invocations — both gstack and non-gstack skills. This is
correct if gstack is truly a universal prerequisite, but it also means a
non-gstack skill (e.g., `humanizer-zh`) would be blocked by a missing gstack
install even if gstack is not needed for that skill.

### `check-cwd.sh` (Bash|Edit|Write|MultiEdit matcher)

**Protects against:** Creating files in `$HOME`, writing outside the project
tree, or any other "wrong directory" accident. This is the single most valuable
operational safety guard.

**Implementation detail:** Resolves symlinks via `pwd -P` and `cd + pwd -P`
to file actual physical paths, so a symlink-based escape is not possible.

**Failure mode:** If `$CLAUDE_PROJECT_DIR` is unset, the hook silently passes
(exit 0). This means the guard is only effective when the project is loaded
through a mechanism that sets this variable.

### `gstack-session-update` (SessionStart)

**Protects against:** Stale gstack version. Runs in background with a 1-hour
throttle and stale-lock detection.

**Risk:** Forces `git pull --ff-only` during session startup. If the network is
slow or the repo has diverged, the background process may hold a lock file for
up to the timeout duration (implemented via `mkdir` lock directory). The lock is
self-cleaning via PID staleness check.

**Risk:** The update runs `./setup -q` when HEAD changes. If the setup script
has side effects (e.g., modifying settings, installing dependencies), these
happen silently in the background during an active session.

### `save-to-obsidian.sh` (Stop)

**Protects against:** Session context loss. Saves a markdown summary to the
Obsidian vault `鱼头知识酷` for later reference.

**Data exposure (low risk):** The script reads `~/.claude/history.jsonl` (the
last 15 entries, truncated to 120 chars each) and `~/.claude/usage-data/session-meta/*.json`
(contains session ID, project path, tool counts, token usage, line counts).
The first prompt is saved at up to 200 characters. Full history is NOT saved.

**Reliability:** The script has no error handling for missing directories or
file read failures. It uses `|| echo ""` for most field extractions but does
not check if `python3` is available. It also uses macOS-specific `stat -f`
syntax, which would fail on Linux.

---

## 3. Observed Gaps and Risks

### Gap A: OMC hooks are not wired up (Severity: Medium)

The OMC hook scripts (`pre-tool-use.mjs`, `persistent-mode.mjs`,
`keyword-detector.mjs`, `post-tool-use.mjs`, `post-tool-use-failure.mjs`,
`session-start.mjs`) exist in `~/.claude/hooks/` but are registered in no
settings.json hooks array.

**Observed current behavior:** These scripts are not executed by the Claude Code
harness for any event type (PreToolUse, PostToolUse, PostToolUseFailure,
SessionStart).

**Impact (if they are expected to be active):**
- No delegation enforcement (direct source edits proceed without notice)
- No mode continuation for ralph/autopilot/ultrawork
- No keyword auto-detection for skills
- No error tracking across tool failures

**Recommended future change (not implemented here):**
Register these in `~/.claude/settings.json` hooks arrays, or verify whether
they are loaded through a mechanism not visible in settings.json (e.g., a
plugin runtime that scans `~/.claude/hooks/` by filename convention). If the
latter, the behavior is undocumented and should be confirmed.

### Gap B: No commit-time hooks (Severity: Low-Medium)

No pre-commit, commit-msg, or pre-push hooks are installed. Quality gates are
manual (pre-merge gate is a separately invoked script, not a hook).

**Observed current behavior:** Any commit can be made at any time without
automated checks. The pre-merge gate runs only when explicitly called.

**Impact:** Commits can include generated outputs, dirty worktrees, or
non-conforming messages. These are caught at merge time (pre-merge gate) but
are not prevented at commit time. In practice, this project uses squash-merges
to main, so individual commit hygiene matters less — the gate catches issues
before the final merge commit.

**Recommended future change (not implemented here):**
If tighter enforcement is desired, consider a pre-commit hook that:
- Checks working tree cleanliness (fast-fail before commit)
- Verifies no generated outputs are being committed
Would need to be paired with `git config core.hooksPath` pointing to the
project's hook directory.

### Gap C: Stop hook has implicit venv dependency (Severity: Low)

The `save-to-obsidian.sh` hook calls `python3` directly (not project venv). On
this system `python3` resolves to Homebrew Python, which has `json` and
`datetime` — so it works. On a system without `python3`, the hook would
silently produce an incomplete save.

**Observed current behavior:** Works on this macOS setup. Silent failure would
occur on systems where `python3` is not available or has limited stdlib.

### Gap D: CWD guard depends on CLAUDE_PROJECT_DIR (Severity: Low)

If `$CLAUDE_PROJECT_DIR` is not set (e.g., session launched from outside the
project), the `check-cwd.sh` hook silently permits all operations.

**Observed current behavior:** The guard is effective when the project is opened
through the normal mechanism. Edge cases (manual `claude` launch from random
directory) bypass it.

### Gap E: Pre-merge gate does not enforce branch naming (Severity: Low)

The gate warns on non-`work/*` branches but does not fail. A merge could
proceed from any branch.

**Observed current behavior:** Warn-only. The workflow document assumes
`work/<topic>` branch naming, but nothing enforces it mechanically.

### Gap F: Stale Fishhead IP in settings.local.json (Severity: Low)

The project's `settings.local.json` contains several permissions referencing
`192.168.68.61:8001` (stale Fishhead IP). The current Fishhead address is
`192.168.68.51:8001`. Both IPs appear in allowlists.

**Observed current behavior:** Both old and new IPs are permitted. No immediate
risk since the old IP is unreachable (connection timeout), which is handled
gracefully by the application code. The stale entries clutter the permission
allowlist.

---

## 4. Recommended Future Changes (Separated — NOT implemented in this batch)

These are recommendations only. Each would need its own batch with explicit
approval before implementation.

### Recommendation 1: Wire OMC hooks (if applicable)

If the OMC hook scripts are intended to be active:
- Register `pre-tool-use.mjs` in the global `settings.json` PreToolUse array
- Register `post-tool-use.mjs` in PostToolUse
- Register `post-tool-use-failure.mjs` in PostToolUseFailure
- Register `session-start.mjs` in SessionStart (alongside gstack update)
- Register `persistent-mode.mjs` and `keyword-detector.mjs` as appropriate

**Reality-check first:** Before wiring, verify that these scripts are compatible
with the current Claude Code hooks API. The `.mjs` files use `import()` for
dynamic loading and read from stdin — both supported by the hooks API, but
should be confirmed with a dry-run or smoke test on each script.

### Recommendation 2: Add pre-commit hook (selective)

Add a lightweight pre-commit hook that:
- Rejects commits containing generated output files in git-tracked paths
- Optionally runs a fast lint check
Does NOT need to compile, run tests, or contact any backend.

Location: `scripts/hooks/pre-commit` + `git config core.hooksPath scripts/hooks`

### Recommendation 3: Clean stale Fishhead permissions

Remove stale `192.168.68.61:8001` entries from `settings.local.json` after
confirming they are no longer in use.

### Recommendation 4: Add Stop hook reliability checks

Consider adding basic guardrails to `save-to-obsidian.sh`:
- Check `python3` availability before calling it
- Check that the Obsidian vault directory exists before writing
- Use `/usr/bin/stat` for macOS compatibility explicitly

---

## 5. Summary Table

| Hook | Type | Layer | Status | Risk if missing |
|---|---|---|---|---|
| `check-cwd.sh` | PreToolUse | Project | Active | File writes outside project |
| `check-gstack.sh` | PreToolUse | Project | Active | Skills invoked without gstack |
| `gstack-session-update` | SessionStart | Global | Active | Stale gstack version |
| `save-to-obsidian.sh` | Stop | Global | Active | Session context not saved |
| `pre-tool-use.mjs` | PreToolUse | Global (OMC) | **Not loaded** | No delegation enforcement |
| `post-tool-use.mjs` | PostToolUse | Global (OMC) | **Not loaded** | `<remember>` tags not processed |
| `post-tool-use-failure.mjs` | PostToolUseFailure | Global (OMC) | **Not loaded** | No error tracking |
| `persistent-mode.mjs` | *(multiple)* | Global (OMC) | **Not loaded** | No mode continuation |
| `keyword-detector.mjs` | PreToolUse | Global (OMC) | **Not loaded** | No skill auto-detection |
| `session-start.mjs` | SessionStart | Global (OMC) | **Not loaded** | No mode state restoration |
| `pre_merge_gate.sh` | Manual | Project | Active (manual) | Generated outputs leaked to main |

**Overall posture:** The two project-level PreToolUse hooks provide solid
operational safety (CWD confinement, gstack dependency). The global Stop hook
adds session persistence. The OMC automation layer (keyword detection, mode
continuation, delegation enforcement, error tracking) is present on disk but
inactive. Whether this is intentional or a gap depends on whether OMC is active
in the current configuration.
