# Skill Router — novel-translation-workbench

An agent-first skill/workflow/doc routing protocol. Read this **before** the
project-level routing table in `CLAUDE.md` when you need to:

- resolve a conflict between two matching skills
- decide whether a task needs a skill at all
- find the right doc when no skill matches
- understand which skill source is authoritative

---

## 1. Routing priority (highest → lowest)

| Priority | Source | When it wins |
|---|---|---|
| P0 | User's explicit `/<skillname>` command | Always. The user named the skill directly. |
| P1 | `CLAUDE.md` §"Skill Routing" (project) | Project-specific skills match the intent. |
| P2 | `SKILL_ROUTER.md` (this file) | Disambiguation, conflict resolution, or when no P0/P1 match exists. |
| P3 | `docs/REFERENCE_MAP.md` | Documentation-level routing — when the task needs a protocol doc, not a skill. |
| P4 | `~/.claude/CLAUDE.md` (global OMC routing) | Only when P0–P3 produce no match. Contains project-agnostic OMC orchestration rules. |
| P5 | OMC hooks / keyword-detector auto-routing | Last resort. Auto-detected keywords only. Never override P0–P3. |

**Blocking rule:** If P1 matches, do not fall through to P4/P5. If P3 matches,
do not reach for a global skill unless the doc explicitly says "use skill X."

---

## 2. Skill source inventory

### Project-local skills (`<project>/.claude/skills/`)
10 symlinks to `~/.agents/skills/`: agent-reach, docx, humanizer-zh, last30days,
pdf, pptx, skywork-search, write-xiaohongshu, xiaohongshu-cover-generator, xlsx.

These are the **project-selected** set. Prefer these over global duplicates.

### Global skills (`~/.claude/skills/`)
97 flat skills from mixed origins (gstack, superpowers, OMC, fishhead, standalone).
Full list: see the `ls ~/.claude/skills/` output in any session.

### gstack framework (`~/.claude/skills/gstack/`)
Full repo with 50+ sub-skill dirs (browse, qa, ship, review, investigate, etc.).
The source for most gstack-prefixed skills. Routed through the project CLAUDE.md
table or the gstack skill's own SKILL.md.

### Superpowers plugin (`~/.claude/plugins/cache/superpowers-marketplace/superpowers/5.0.7/`)
Plugin-managed skills (superpowers skills, e.g. execute-plan, write-plan,
brainstorm, tdd, systematic-debugging, using-git-worktrees, etc.).

### Translation framework (`~/.claude/skills/fishhead-literary-translator/`)
6 files: SKILL.md (framework-level quality bar), shared/WORKFLOW.md,
WORKBENCH_PROTOCOL.md, BOOK_ASSETS_SPEC.md, directions/zh_to_en/STYLE_RULES.md,
directions/zh_to_en/roles/translator.md, directions/zh_to_en/roles/reviewer.md.

The framework this workbench implements. See `docs/SKILL_INTEGRATION.md` for
the framework↔workbench relationship.

### Framework snapshot (`docs/skill_snapshot/fishhead-literary-translator/`)
Versioned backup of the framework files. See `docs/REFERENCE_MAP.md` §7.
Canonical source is the runtime path — the snapshot is for diffing.

### Cross-tool skill root (`~/.agents/skills/`)
7 skills: agent-reach, find-skills, humanizer-zh, last30days, skill-creator,
write-xiaohongshu, xiaohongshu-cover-generator. The symlink source for some
project-local skills.

---

## 3. Conflict resolution

When multiple skills match an intent:

1. **Explicit `/<name>`** wins over everything (P0).
2. **More specific wins over less specific** — compare keyword density and
   scope narrowness. A skill whose description matches 3+ keywords is more
   specific than one matching 1 keyword.
3. **Project-local wins over global** — a project symlink beats a global
   skill of the same name and purpose.
4. **Framework over implementation** — for translation work, the
   `fishhead-literary-translator` framework standards override the workbench
   defaults when they conflict (per `docs/SKILL_INTEGRATION.md`).
5. **If still tied** — pick the skill listed first in the project CLAUDE.md
   routing table. If neither appears there, pick the one with the narrower
   scope description.

**Deadlock rule:** If three or more skills match and you cannot choose,
report the candidates to the user with a one-line recommendation. Do not
pick arbitrarily.

---

## 4. Selection protocol

Before any tool call, in this order:

```
1. Does the user's intent match a row in CLAUDE.md §"Skill Routing"?
   → YES: invoke that skill. Done.
   → NO or UNSURE: go to step 2.

2. Does the intent match a protocol doc in REFERENCE_MAP.md?
   → YES: read the doc and follow it. Done.
   → NO: go to step 3.

3. Does a known failure pattern or quality-loop procedure match?
   → Check docs/FAILURE_PATTERN_INDEX.md, then docs/QUALITY_LOOP.md.
   → YES: follow that protocol. Done.
   → NO: go to step 4.

4. Does the task need a skill at all?
   → Organizational protocol (branch, merge, gate)? → CLAUDE.md rules, no skill.
   → Single command or fact lookup? → No skill, just run the command.
   → Real workflow / multi-step process? → Try a global skill (P4/P5).
   → Still unsure? → Report decision gap to user.
```

---

## 5. When NOT to use a skill

Do not invoke a skill for:

- **Organizational protocols** — branch model, merge rules, gate sequencing,
  scope discipline language. These live in CLAUDE.md and are behavioral
  constraints, not executable workflows.
- **Single commands** — a one-line `ssh -G` check, a `grep` lookup, a file
  read. The skill overhead exceeds the benefit.
- **Project-specific assets** — `project_assets/` entries, prompt files,
  pipeline code. These are owned by the workbench, not by any skill.
  Skills may reference them, but skills should not be invoked just to
  "run a canonization gate" (that gate is a Python module, not a skill).
- **Already-covered protocol docs** — if `docs/QUALITY_LOOP.md` already
  defines the full process, reading the doc is sufficient. Do not look for
  a "quality loop skill" that does not exist.
- **Narrow lookup that a grep could solve** — a five-second `grep` is faster
  than loading a skill's context.

---

## 6. Route reporting

Before executing a selected route, state briefly:

> Routing: [skill name / doc path] — [one-line rationale]

Examples:
- "Routing: `scope` — user asked for minimal change, pre-edit guard."
- "Routing: `docs/QUALITY_LOOP.md` — quality-loop inspection task, following
  the defined protocol."
- "Routing: `CLAUDE.md` §Review Gate — batch completion with merge approval
  needed, organizational protocol."
- "Routing: no skill — single `grep` lookup, not a workflow."

Do not report the route if the tool call is trivially obvious (e.g. reading
a file, running `git status`). Report when a non-obvious routing decision
was made.

---

## 7. Routing examples

### Merge / review gate

Intent: "ready to merge" / "close out this batch" / "run the gate"

1. `CLAUDE.md` §"Review Gate" — match for batch-completion + merge approval.
2. Follow gate steps: closeout report → pre-merge gate → tests.
3. Do not invoke a skill for the gate itself — it's a CLAUDE.md protocol.
4. If the user says "ship" or "create a PR": the CLAUDE.md table maps to
   the `ship` skill.

### Real-sample validation

Intent: "validate a real chapter sample" / "run a sample through the pipeline"

1. `docs/REAL_SAMPLE_VALIDATION.md` — the complete protocol.
2. Read the doc, follow its sample-intake → dry-run → execution path.
3. Do not look for a "real-sample skill" — the protocol doc is the right
   artifact.
4. If the sample intake tool needs the `sample` entrypoint: use
   `CLAUDE.md` §"Local development" commands, not a skill.

### Translation quality loop

Intent: "run quality loop" / "inspect output" / "classify findings"

1. `docs/QUALITY_LOOP.md` — the full process.
2. `docs/FAILURE_PATTERN_INDEX.md` — read before tuning.
3. Classify findings per the protocol (Type A/B/C).
4. For Type C (rule hardening): follow the Prompt Change Gate in
   `docs/QUALITY_LOOP.md`.
5. For canonization: use the canonization gate
   (`app/chapter/canonization.py`), not a skill.

### Book-memory canonicalization

Intent: "canonize new asset entry" / "update glossary" / "add style rule"

1. `app/chapter/canonization.py` — the canonization gate is a Python module
   with tests. Run `venv/bin/python -m pytest app/tests/test_canonization.py`.
2. `docs/QUALITY_LOOP.md` §"Canonization Gate" — gate requirements.
3. Do not invoke a skill for canonization. It is a code-level check, not a
   workflow-level step.

### Failure-pattern capture

Intent: "capture a bad case" / "record a failure pattern" / "add to index"

1. `docs/templates/BAD_CASE_CAPTURE_TEMPLATE.md` — capture format.
2. `docs/FAILURE_PATTERN_INDEX.md` — append new entry.
3. No skill needed — the templates and index are documentation artifacts.
4. If the pattern is a recurring translation issue: route through the
   quality loop instead (`docs/QUALITY_LOOP.md`).

### Documentation / workflow design

Intent: "design a new workflow" / "write a protocol doc" / "add a template"

1. `docs/SKILL_BOUNDARY_MAP.md` — check whether it should be a skill, a
   workflow step, or a rule.
2. `docs/REFERENCE_MAP.md` — check for existing coverage to avoid
   duplication.
3. If a new doc: place in `docs/` or `docs/templates/` per the existing
   convention.
4. If a new workflow: define in WORKFLOW.md or protocol doc, not as a skill.

### Global / non-project skills

Intent: "search the web" / "open a browser" / "write a PDF" / "create a docx"

1. Check `CLAUDE.md` §"Skill Routing" — several global skills are already
   mapped (skywork-search, browse, pdf, docx, pptx, xlsx, make-pdf).
2. If not mapped: check `~/.claude/skills/` for a matching skill name.
3. If a skill exists: invoke it. The skill will handle its own context.
4. If no skill exists: do the task directly (Bash / Python / platform tool).

---

## 8. Maintenance notes

- SKILL_ROUTER.md must stay thin. When it exceeds ~200 lines, extract
  sections into `docs/` and reference them.
- When a new skill is added to the project CLAUDE.md routing table, check
  whether this router needs a corresponding example in §7.
- When a skill is deprecated, remove or update its references in this file.
- This router does not override the framework priority defined in
  `docs/SKILL_INTEGRATION.md`. Framework wins when framework and workbench
  disagree.
