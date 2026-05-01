# Skill Boundary Map

## Purpose

This document clarifies which responsibilities belong in skills, which belong
in workflows, and which should remain in CLAUDE.md / project-level rules. It
serves as a reference for future extraction decisions — so that new skills are
sized correctly, workflows are not turned into skills prematurely, and rules
are not promoted to skills without a clear boundary.

It does **not** define execution order. Execution protocol lives in
`WORKFLOW.md` and `shared/WORKFLOW.md`.

## Current layer architecture

The project already has a multi-layer routing architecture, documented in
`WORKFLOW.md` §"Routing Architecture". The layers are:

| Layer | Document | What it holds |
|-------|----------|---------------|
| Skill routing | CLAUDE.md routing table | Intent-to-skill mappings |
| Framework standard | `SKILL.md` (framework) | Quality bar, scope, style rules |
| Execution protocol | `WORKFLOW.md`, `shared/WORKFLOW.md` | Step order, loop limits, override modes |
| Direction profile | `directions/zh_to_en/` (framework) | Direction-specific style and roles |
| Role prompts | `prompts/prompt_a.md`, `prompts/prompt_b.md` | Draft (A) and review (B) per passage |
| Book assets | `project_assets/*` | Book-level name, term, style specifics |
| Ad hoc instruction | User's current message | Passage-level adjustments |

This map extends that layer model by identifying **what should become a skill**
vs. what should stay in its current layer.

## Skill boundary criteria

A responsibility is a good candidate for extraction into a standalone skill
when it meets **all** of:

1. **Reusable context** — It can be invoked across projects without carrying
   project-specific prompts or assets.
2. **Stable interface** — Its input/output contract is clear enough that a
   caller does not need to read the full implementation.
3. **Independent lifecycle** — It can be versioned, updated, or deprecated
   without touching the workbench workflow.
4. **Narrow scope** — It does one thing well. A skill that would need its own
   sub-layers or direction profiles is too broad.

A responsibility should **stay in a workflow** when:

- It is part of a multi-step sequence where steps depend on each other's
  output.
- It must run in a specific order with other steps.
- It needs access to project-scoped state (book assets, run manifests).

A responsibility should **stay in CLAUDE.md / project rules** when:

- It is an organizational protocol (branch model, gate sequencing, merge rules).
- It is a project-specific constraint that would be wrong in a reusable skill.
- It is a safety boundary (Fishhead usage rules, scope discipline).

## Candidate skills map

Each row identifies a potential skill, its desired scope, whether extraction is
ready, and what currently blocks it.

### Extractable (ready or near-ready)

| Candidate skill | Scope boundary | Ready? | What it would replace |
|---|---|---|---|
| **batch-close** (already extracted) | Close out a completed translation batch: manifest summary, working-tree check, stop-point confirmation. Project-scoped but the pattern is generic. | Yes | `docs/CLOSEOUT_REPORT_TEMPLATE.md` protocol |
| **commit-batch** (already extracted) | Create a mid-batch commit with review-gate summary. Same generic pattern across projects. | Yes | Manual mid-batch commit flow |
| **context-save / context-restore** (already extracted) | Capture and restore session state (git branch, uncommitted changes, task list, active plan). | Yes | Manual checkpointing |
| **scope** (already extracted) | Restrict edits to a defined set of files. Narrow, single-purpose. | Yes | Ad hoc "只改 X" discipline |

### Extractable with work

| Candidate skill | Scope boundary | Ready? | What blocks it |
|---|---|---|---|
| **Real-sample validation protocol** | A reusable workflow for: sample suitability → intake (manual paste) → dry-run → controlled execution → quality review → asset updates. The protocol in `docs/REAL_SAMPLE_VALIDATION.md` is already mostly generic, but its "controlled execution" step currently references Fishhead-specific backend config. | Near-ready | 1. Remove Fishhead-specific backend references from the workflow (make backend a parameter, not a hard-coded URI). 2. Re-validate on a non-Fishhead backend to prove generic-ness. |
| **Quality loop runner** | A reusable process for: run model output → inspect → classify findings (Type A/B/C) → resolve through appropriate channel → verify. Currently documented in `docs/QUALITY_LOOP.md`. | Near-ready | 1. Depends on `project_assets/` files that are book-scoped, not skill-scoped. 2. The Prompt Change Gate references `prompts/prompt_a.md` by project path — would need a parameterized prompt path. |
| **Pre-merge gate** | Working-tree cleanliness check + generated-output tracking check. The script `scripts/checks/pre_merge_gate.sh` is already standalone. | Near-ready | 1. Currently hard-codes project-specific gitignore patterns (`data/output/`, `data/exports/`, `outputs/`). 2. Warns on `main` branch — that warning is project-specific policy, not generic gate behavior. |
| **Fishhead SSH resolver** | Resolve Fishhead SSH target via `ssh -G` rather than hard-coding IPs. Documented as project rule in CLAUDE.md. | Might be too narrow | 1. It's a single command — a skill file for one command is over-engineering. 2. If a multi-step remote-execution protocol emerges later, extract _that_ instead. Keep as a rule for now. |

### Not ready for extraction

| Candidate skill | Scope boundary | Why not ready |
|---|---|---|
| **Review Gate** | Batch-completion review and merge-approval protocol. Currently defined in CLAUDE.md as a multi-step gate. | Too tightly integrated with project-specific branch model and merge rules. The gate's step 3 ("explicit approval") requires human-in-the-loop — a skill cannot guarantee that. |
| **Hygiene reporter** | Classifies files under `data/source/` as tracked/sample-input. Currently `app/hygiene/reporter.py`. | It is a Python library, not a Claude-level workflow. The orchestration layer would need to call it via Bash, which is already what the test does. No skill layer needed. |
| **Canonization Gate** | Validates proposed asset entries before canonization. Currently `app/chapter/canonization.py`. | It is a Python module with a specific API. It is already invocable by code. Turning it into a skill would add a Bash-invocation layer without benefit. |
| **Book memory updater** | Update `project_assets/` after a chapter. Currently embedded in the translator skill's workflow as Step 7. | The updater logic is inseparable from the translation output it reviews. Extracting it prematurely would create a skill that depends on the translator skill's output format — a circular dependency. |
| **Workbench protocol** | Chapter-level operation, dry-run, no-clobber, resume, progress reporting, run summary, output traceability. Currently `WORKBENCH_PROTOCOL.md` in the framework. | This is a framework-level contract, not a skill. Multiple workbenches implement it; forcing it into a single skill would couple the framework to one implementation. |

## Items that should never become skills

| Responsibility | Current home | Why it should stay |
|---|---|---|
| Branch model and merge rules | CLAUDE.md | Organizational protocol, not executable behavior. Different projects have different branch policies. |
| Fishhead IP resolution rule | CLAUDE.md | A single `ssh -G` command, not a workflow. A skill for one command is over-engineering. |
| Scope discipline ("只改 X") | CLAUDE.md | Behavioral guideline, not automation. Automating it would mean file-level edit restrictions, which is what the `freeze` skill does — the guideline itself is meta-level. |
| Gate sequencing (Review Gate → Pre-merge Gate → tests → merge) | CLAUDE.md | An ordered list of project-specific checkpoints. Reusable across projects only if all projects share the same branch model, which they do not. |
| Model/backend choice | Implementation | Backend is an operational detail, not a behavioral standard. The skill framework explicitly says "backend choice is real and consequential" but not part of the skill identity. |

## Skill sizing principle

Each skill should do **one thing well**. A skill that would need its own
sub-layers, direction profiles, or routing tables is too broad. Signs of
an oversized skill:

- It needs to read its own CLAUDE.md for sub-routing.
- It has an internal A/B role split (that's what direction profiles are for).
- It references multiple `project_assets/` files by name — those are
  book-specific, not skill-owned.
- It describes a full multi-step workflow with its own loop limits (that's
  what WORKFLOW.md is for).

The existing `fishhead-literary-translator` framework is intentionally broad
because it is a **framework**, not a task-specific skill. New skills should
be narrower.

## Architectural invariant

Skills invoke workflows. Workflows do not invoke skills.

A skill may say "run the default translation workflow" (which is defined in
WORKFLOW.md). A workflow step should never say "run skill X" — that would
make the workflow dependent on a skill's existence, breaking the reuse-first
principle.

The one exception: the routing table in CLAUDE.md invokes skills. That is
intentional — the routing table is the entry point, not a workflow step.

## When to reevaluate this map

Revisit this map when:

- A workflow step is duplicated across two workflows (signal: extract into a
  skill).
- A skill grows beyond ~200 lines or gains an internal sub-structure (signal:
  too broad).
- A new direction profile is added to the framework (signal: reevaluate
  direction-agnostic vs. direction-specific boundaries).
- A protocol is invoked manually three or more times in a session (signal:
  consider skill extraction).

Do not revisit preemptively. The map is stable until one of the above signals
triggers.
