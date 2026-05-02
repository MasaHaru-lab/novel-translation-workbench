# Reference Map

An agent-first index of this project's documentation, templates, prompts, and
rule files. Read the sections relevant to your task; skip the rest.

No file here is a duplicate. If you need content from multiple sections, read
each file once — their scopes are intentionally disjoint.

---

## 1. Governance — what decides what

| When to read | File | What it tells you |
|---|---|---|
| First time in this project | `CLAUDE.md` | Routing table (which skill for which intent), branch model, merge rules, scope discipline, Review Gate, safety boundaries. Read this first and keep it open. |
| Before translating anything | `SKILL.md` | Quality bar, scope, style rules, consistency rules, project-memory expectations. Non-negotiable standards. |
| Before running a workflow step | `WORKFLOW.md` | Step order (Steps 0–4), loop limits, role boundaries, Routing Architecture layer model. Also defines which layers govern which decisions. |
| When framework and project disagree | `docs/SKILL_INTEGRATION.md` | Relationship between `fishhead-literary-translator` framework and this workbench implementation. Framework wins in conflicts. |

**Priority when layers conflict:**
`SKILL.md` > `WORKFLOW.md` > book assets > role prompts > ad hoc instructions

For concrete book facts (names, titles, glossary terms), book assets win over
general rules. See `WORKFLOW.md` §"Routing Architecture" → "Explicit book-specific
memory priority".

---

## 2. Execution — how translation works

| When to read | File | What it tells you |
|---|---|---|
| Writing or editing Prompt A | `prompts/prompt_a.md` | Draft-generation instruction for the translator role. Must stay aligned with framework `roles/translator.md`. |
| Writing or editing Prompt B | `prompts/prompt_b.md` | Review-pass instruction for the reviewer role. Must stay aligned with framework `roles/reviewer.md`. |
| Running the chapter pipeline | `ORCHESTRATION.md` | Chapter-level orchestrator: planning, segmentation, execution, aggregation, consistency pass, manifest/resume. |
| Wiring a real model backend | `INTEGRATION.md` | Backend adapter, env vars, API contract, error handling. |
| Checking current project status | `STATUS.md` | Phase A seal status, R4 merge state, BookMemory support matrix. |

The orchestrator (`app/chapter/orchestrator.py`) invokes the segment-level
workflow from `WORKFLOW.md` per segment. `WORKFLOW.md` is the segment-level
protocol; `ORCHESTRATION.md` is the chapter-level caller.

---

## 3. Translation context — assets and memory

| When to read | File | What it tells you |
|---|---|---|
| Before translating any passage from this book | `project_assets/README.md` | File roles and priority order for all project assets. Read once, then read the individual asset files. |
| Checking character names | `project_assets/2. characters.md` | Recurring character name renderings. |
| Checking titles, forms of address, ranks | `project_assets/3. titles_and_terms.md` | System-level terminology. |
| Checking glossary entries | `project_assets/1. glossary.md` | High-risk recurring expressions, metaphysical/ritual language. |
| Checking prose standards | `project_assets/4. style_notes.md` | Tone control, register, dialogue/narration handling. |
| Checking unresolved decisions | `project_assets/5. unresolved_decisions.md` | Unstable or risky choices — treat as cautionary, not final. |
| Using BookMemory retrieval | `docs/book_memory.md` | Graph-based memory layer (entities, relationships, titles, chapter events, translation decisions). Source text remains primary authority. |
| Restoring session state | `SESSION_CHECKPOINT.md` | Current session's branch, focus, and shipped work. |

**Priority order when using project assets:**
source text > characters > titles_and_terms > glossary > style_notes > unresolved_decisions

---

## 4. Pipeline architecture — code structure

| When to read | File | What it tells you |
|---|---|---|
| Modifying any pipeline stage | `docs/PIPELINE_CONTRACTS.md` | Contracts between all 8 pipeline stages: inputs, outputs, owners, invariants. Read before editing any stage's code. |
| Understanding skill boundaries | `docs/SKILL_BOUNDARY_MAP.md` | What belongs in a skill vs. workflow vs. project rules. Candidate skills map and extraction readiness. |
| Using the pre-merge gate | `scripts/checks/pre_merge_gate.sh` | Working-tree cleanliness check; generated-output tracking. Run before merging. |

---

## 5. Quality processes

| When to read | File | What it tells you |
|---|---|---|
| Running Phase B quality loop | `docs/QUALITY_LOOP.md` | How to inspect output, classify findings (Type A/B/C), resolve through the right channel, and verify. |
| Changing Prompt A or B | `docs/QUALITY_LOOP.md` §"Prompt Change Gate" | Gate requirements before modifying prompt files. |
| Adding new asset entries | `docs/QUALITY_LOOP.md` §"Canonization Gate" + `app/chapter/canonization.py` | Validation gate for new `project_assets/` entries. |
| Bringing in a real chapter sample | `docs/REAL_SAMPLE_VALIDATION.md` | Operator-safe path: sample suitability → intake → dry-run → controlled execution → quality review → asset updates. |
| Checking for known failure patterns | `docs/FAILURE_PATTERN_INDEX.md` | Agent-first index of cross-batch failure patterns: capture criteria, guardrail format, reading protocol, anti-bloat rules. Read before any tuning/quality work. |

---

## 6. Operational protocols

| When to read | File | What it tells you |
|---|---|---|
| Closing out a batch | `docs/CLOSEOUT_REPORT_TEMPLATE.md` | Batch closeout report format (branch, HEAD, changed files, acceptance, verification, impact). |
| Reviewing hooks and safety posture | `docs/HOOK_SAFETY_REVIEW.md` | Inventory of all hook layers (project, global, OMC), current gaps, risks, and future recommendations. |
| Running the Review Gate | `CLAUDE.md` §"Review Gate" | Mandatory review+approval step before any merge to `main`. Do not skip. |
| Running the pre-merge gate | `CLAUDE.md` §"Merging back to main" + `scripts/checks/pre_merge_gate.sh` | Mechanical gate: working-tree cleanliness, generated-output check. |
| Using Fishhead | `CLAUDE.md` §"Fishhead / 3090 usage boundary" | SSH resolution via `ssh -G`, allowed vs. not-allowed operations, operational facts. |

---

## 7. Framework snapshot (versioned backup)

The `fishhead-literary-translator` framework lives at `~/.claude/skills/...`
(runtime). This repo keeps a versioned snapshot at `docs/skill_snapshot/`.

| File | Purpose |
|---|---|
| `docs/skill_snapshot/fishhead-literary-translator/SKILL.md` | Framework-level SKILL.md (direction-agnostic) |
| `docs/skill_snapshot/fishhead-literary-translator/shared/WORKFLOW.md` | Framework shared workflow |
| `docs/skill_snapshot/fishhead-literary-translator/WORKBENCH_PROTOCOL.md` | Workbench operational contract |
| `docs/skill_snapshot/fishhead-literary-translator/BOOK_ASSETS_SPEC.md` | Canonical book-asset model |
| `docs/skill_snapshot/fishhead-literary-translator/directions/zh_to_en/STYLE_RULES.md` | Direction-specific style rules |
| `docs/skill_snapshot/fishhead-literary-translator/directions/zh_to_en/roles/translator.md` | Role A (framework reference for `prompts/prompt_a.md`) |
| `docs/skill_snapshot/fishhead-literary-translator/directions/zh_to_en/roles/reviewer.md` | Role B (framework reference for `prompts/prompt_b.md`) |

**Rule:** The canonical runtime path at `~/.claude/skills/` is the source of
truth. The snapshot is a diffable backup. If they diverge, the runtime path
wins — do not silently auto-merge.

---

## Quick-reference flowchart

```
Starting a new task?
  │
  ├─ First time in project? → CLAUDE.md (routing, rules, safety)
  │
  ├─ Translating something?
  │    1. SKILL.md (standards)
  │    2. WORKFLOW.md (execution protocol)
  │    3. project_assets/ (book context)
  │    4. prompts/prompt_a.md + prompt_b.md (role instructions)
  │
  ├─ Changing pipeline code?
  │    1. docs/PIPELINE_CONTRACTS.md (stage contracts)
  │    2. ORCHESTRATION.md (chapter orchestrator)
  │    3. INTEGRATION.md (backend wiring)
  │
  ├─ Running quality loop / tuning?
  │    1. docs/FAILURE_PATTERN_INDEX.md (known patterns — read first)
  │    2. docs/QUALITY_LOOP.md (full process)
  │    3. docs/REAL_SAMPLE_VALIDATION.md (sample intake, if needed)
  │
  ├─ Closing out a batch / merging?
  │    1. docs/CLOSEOUT_REPORT_TEMPLATE.md (report format)
  │    2. CLAUDE.md §"Review Gate" (approval step)
  │    3. scripts/checks/pre_merge_gate.sh (mechanical check)
  │
  └─ Understanding the architecture?
       1. docs/SKILL_INTEGRATION.md (framework vs workbench)
       2. docs/PIPELINE_CONTRACTS.md (pipeline stages)
       3. docs/SKILL_BOUNDARY_MAP.md (skill vs workflow vs rules)
```
