# Skill Router — novel-translation-workbench

Authoritative routing index when `CLAUDE.md` §Skill Routing is ambiguous.

## When to read this file

Read this file BEFORE deciding when ANY of:

- ≥2 rows in CLAUDE.md routing table match the user's intent
- 0 rows match, but the task feels skill-shaped
- User explicitly asks "which skill / 该用哪个 / 用不用 skill"
- A previously selected skill was rejected and you need an alternative

Otherwise the CLAUDE.md table is sufficient — do not load this file.

---

## 1. Routing priority (highest → lowest)

| Priority | Source | When it wins |
|---|---|---|
| P0 | User's explicit `/<skillname>` | Always. User named the skill. |
| P1 | `CLAUDE.md` §Skill Routing (project) | A project row matches the intent. |
| P2 | `SKILL_ROUTER.md` (this file) | Disambiguation; conflict resolution; no P0/P1 match. |
| P3 | `docs/REFERENCE_MAP.md` | Task needs a protocol doc, not a skill. |
| P4 | `~/.claude/CLAUDE.md` global routing | Only when P0–P3 produce no match. |
| P5 | OMC hooks / keyword auto-routing | Last resort. Never overrides P0–P3. |

Blocking: if P1 matches, do not fall through to P4/P5. If P3 matches, do not reach for a global skill unless the doc says so.

---

## 2. Skill sources

- Project-local: `<project>/.claude/skills/` — project-selected subset; prefer over globals.
- Global: `~/.claude/skills/` — mixed origins (gstack, OMC, standalone).
- gstack: `~/.claude/skills/gstack/` — gstack-prefixed skills.
- Superpowers plugin: `~/.claude/plugins/cache/superpowers-marketplace/superpowers/*/`
- Translation framework: `~/.claude/skills/fishhead-literary-translator/` — see `docs/SKILL_INTEGRATION.md`.
- Cross-tool root: `~/.agents/skills/` — symlink source for some project-local skills.

Counts and full skill names live in the filesystem, not here — they rot.

---

## 3. Conflict resolution

1. Explicit `/<name>` (P0) wins over everything.
2. More specific > less specific — keyword density of the description.
3. Project-local > global of the same name.
4. Framework > workbench when they disagree (per `docs/SKILL_INTEGRATION.md`).
5. Still tied → pick the narrower scope, invoke, do not enumerate alternatives to the user.

---

## 4. Selection protocol

```
1. CLAUDE.md §Skill Routing matches?            → invoke. done.
2. Else REFERENCE_MAP.md protocol doc matches?  → read & follow. done.
3. Else quality-loop task?                      → docs/QUALITY_LOOP.md.
   Reusable failure mode found / expected?      → docs/FAILURE_PATTERN_INDEX.md.
4. Else:
   - org protocol (branch / merge / gate)?      → CLAUDE.md rules, no skill.
   - single command or fact lookup?             → just run it.
   - real multi-step workflow?                  → try ~/.claude/skills/ (P4).
   - still unsure?                              → state the gap, don't invoke arbitrarily.
```

---

## 5. When NOT to use a skill

- **Organizational protocols** (branch model, merge gate, scope discipline) — CLAUDE.md rules, not workflows.
- **Single commands** (`grep`, `Read`, one-line `ssh -G`) — skill load cost exceeds task cost.
- **Project-owned modules** (`app/chapter/canonization.py` is a Python gate with tests, not a skill).
- **Tasks already covered by a protocol doc** — read the doc.

---

## 6. Route reporting

Report only when the routing decision is non-obvious:

> Routing: `<skill / doc>` — `<one-line rationale>`

Skip the report for trivial calls (file reads, `git status`).

---

## 7. Common routes

| Intent | Route |
|---|---|
| merge / close out a batch | `CLAUDE.md` §Review Gate (organizational, no skill) |
| ship / create PR | `ship` skill (per CLAUDE.md table) |
| validate a real chapter sample | `docs/REAL_SAMPLE_VALIDATION.md` |
| run translation quality loop | `docs/QUALITY_LOOP.md` + `docs/FAILURE_PATTERN_INDEX.md` |
| canonize new asset / glossary entry | `app/chapter/canonization.py` (run pytest) |
| capture failure pattern | `docs/templates/BAD_CASE_CAPTURE_TEMPLATE.md` → `docs/FAILURE_PATTERN_INDEX.md` |
| design new workflow / protocol doc | `docs/SKILL_BOUNDARY_MAP.md` → `docs/REFERENCE_MAP.md` |
| web / browser / pdf / docx / xlsx / pptx | global skill mapped in CLAUDE.md table |

---

## 8. Maintenance

- Keep this file under ~120 lines. Inventory and long examples belong in `docs/` and link back.
- New row in CLAUDE.md routing table → add a row in §7 only if the route is non-obvious.
- Framework priority (`docs/SKILL_INTEGRATION.md`) overrides this router.
