# Quality Loop — Phase B

## Purpose

Phase B operationalizes the "rule hardening" principle from WORKFLOW.md §"Rule
hardening behavior":

> If the same type of problem repeats across multiple passages: convert the
> repeated issue into a new hard rule for Prompt A.

This document defines the repeatable process for:

1. Running real model output through the existing chapter pipeline
2. Inspecting translation quality systematically
3. Classifying findings by type
4. Resolving each type through the appropriate channel
5. Verifying that the resolution worked

## Relationship to the existing codebase

The quality loop does NOT modify:

- CLI behavior (frozen Phase A surface)
- HTTP/API behavior (frozen Phase A surface)
- Output format contract (frozen Phase A surface)
- Manifest/resume semantics (frozen Phase A surface)
- Quality gate logic in `app/chapter/quality.py` (frozen Phase A surface)
- Strategy, budget, or enactment logic

It touches only:

- Project assets (glossary, style notes, etc.)
- Prompts, **after passing through the Prompt Change Gate** (see below)
- This document and associated findings records

## Prerequisites

### Backend

A working translation backend reachable at `MODEL_BACKEND_URL`.
Currently: Fishhead wrapper (resolve host with `ssh -G Fishhead-Core | grep hostname`,
port `8001`), model `qwen2.5:14b` via Ollama. Do not hard-code the Fishhead IP address —
it is managed via SSH config and may change.

If the backend is unreachable, no quality-loop work runs.

### Approved sample text

`data/source/one_chapter_quality_source.txt` (87 lines, ~2000 chars) is the
approved safe sample for quality-loop runs. Do not expand the sample set
without a separate batch.

### Output location

Generated artifacts (translated chapters, manifests, findings) go under
`data/output/`, `data/exports/`, or `outputs/`. All three are gitignored.
Do not commit generated outputs.

## Quality review methodology

### Run

```bash
export MODEL_BACKEND_URL=http://$(ssh -G Fishhead-Core | grep '^hostname ' | awk '{print $2}'):8001/generate
venv/bin/python -m app.cli chapter run \
  --source data/source/one_chapter_quality_source.txt \
  --output data/outputs/quality_run.md \
  --confirm
```

Use `--dry-run` first to preview the plan. Remove `--confirm` to skip the
interactive prompt when running unattended.

### Inspect

Read the output file. Compare each passage against the source text.

Focus on the failure types observed in previous quality runs:

| Category | Examples |
|----------|----------|
| Meaning errors | Wrong time units (半旬 ≠ half a decade), wrong dynasty name (大灃 ≠ Great Hong) |
| Instruction leakage | Asset field text appearing verbatim in output |
| Name/address drift | Over-Westernized "Little Xi", flat/mechanical renderings |
| Hallucinated additions | Scene-closing commentary not in source, invented introspection |
| Facial-color reversal | 黑了 rendered as "pale" instead of "darkened" |
| Register errors | Over-modern phrasing in historical setting |
| Missing content | Source paragraphs dropped from output |
| Inline Chinese | Chinese characters or pinyin left in English prose |

### Record

Create a findings record under `outputs/` following the pattern from the
existing closure report (`outputs/quality_loop_closure_report.md`):

- Signal-by-signal comparison (v1 vs v2 vs ...)
- Verdict per signal: FIXED / IMPROVED / REGRESSED / UNCHANGED
- Overall summary table
- Recommended next actions

### Classify

Each finding falls into one of three resolution types:

## Finding classification and resolution

### Type A — Glossary/lexical entries

**Characteristics:** Noun-like, stable, concrete. Names, terms, fixed
expressions. The model can follow a glossary entry when it sees one.

**Examples:** 大灃 → "Great Feng", 官家出身 → "official household background",
福礼 → "formal salute", 吉祥物 → "auspicious symbol"

**Resolution path:** Write to `project_assets/1. glossary.md`. Verify with a
v-next run. No prompt changes needed.

**Track record:** Type A entries worked in all v2–v5 quality runs. The model
follows glossary entries reliably.

### Type B — Style notes / behavioral guidance

**Characteristics:** Rules about *how* to translate, not *what* to translate.
Written as prose guidance in style notes.

**Examples:** "Preserve emotional direction of 脸色黑了", "Do not add narrative
commentary not in the source"

**Resolution path:** Write to `project_assets/4. style_notes.md`. Verify with
a v-next run.

**Track record:** Type B entries have mixed results. The model sometimes ignores
behavioral rules expressed as passive style notes. When a Type B rule fails
repeatedly, escalate to Type C.

### Type C — Prompt-level behavioral enforcement

**Characteristics:** Behavioral rules that the model does not follow from
passive style notes alone. Requires active instruction text in Prompt A,
positioned as explicit constraints.

**Examples:** Facial-color direction for 黑了 (style note exists but model
ignores it in v3–v5), narrative stance/hallucinated additions (rule exists
in style notes but model adds closing commentary)

**Resolution path:**
1. **Propose**: Write the proposed Prompt A change as a diff
2. **Gate review**: Run the change past the Prompt Change Gate (see below)
3. **Verify**: Run a v-next translation with the updated prompt
4. **Confirm or revert**: Compare v-next output against the baseline

**Before any Type C resolution, the Prompt Change Gate must pass.**

## Prompt Change Gate

### What it is

A lightweight, documented review step that must precede any modification to
Prompt A (`prompts/prompt_a.md`) or Prompt B (`prompts/prompt_b.md`).

### Gate steps

**Step 1 — Evidence:** The finding must be observed in at least two quality
runs (or one run with at least two occurrences). A single stray output
does not warrant a prompt change.

**Step 2 — Lower-level check:** Verify the finding cannot be resolved as
Type A (glossary) or Type B (style note). The closure report from
`outputs/quality_loop_closure_report.md` should show that a Type B style
note was tried and failed.

**Step 3 — Change proposal:** Write the proposed prompt change as a
documented diff. Include:
- The exact text to add/modify (target position in the prompt file)
- The rationale (which finding type, how many occurrences observed)
- The expected behavioral change
- The verification plan (which version vN to compare against)

**Step 4 — Dry-run verification:** Before running a new translation, prepare
the verification comparison: choose baseline version (e.g. v5), identify
specific passages that should change, and define what a "pass" looks like
for each.

**Step 5 — Gate approval:** The change proposal + verification plan must be
reviewed and approved before editing the prompt file. Approval is documented
here in this quality-loop doc or in the findings record.

**Step 6 — Execute:** Apply the prompt change, run a v-next translation,
and compare against the verification plan.

**Step 7 — Confirm or revert:** If the verification plan passes, the change
is stable. If it regresses other signals, revert the prompt change and
reassess.

### What does NOT need the gate

- Edits to `project_assets/` files — these are Type A/Type B and do
  not require **Prompt Change Gate** approval (but see the **Canonization
  Gate** below for asset-entry canonization rules)
- Edits to `docs/QUALITY_LOOP.md` or `STATUS.md` or `SESSION_CHECKPOINT.md`
- Corrections to asset files that fix instruction leakage or stale entries
  (corrections are not new canonization decisions)

## Canonization Gate

### What it is

A gate that evaluates proposed translation choices before they become
authoritative entries in `project_assets/`. It ensures that weak, risky,
or user-rejected renderings are not silently promoted to canonical status.

The gate is implemented in `app/chapter/canonization.py` as the
`CanonizationGate` class. It is a code-level tool used during quality-loop
Type A/Type B resolution to classify proposed renderings before writing
them to asset files.

### Protection rules

The gate runs the following detectors against every proposed rendering:

| Rule | What it catches | Severity |
|------|----------------|----------|
| **Generic address** | "girl" for 丫头, "miss" for 大小姐 — generic English terms that flatten hierarchy | warning (blocker if user-rejected) |
| **Stiff kinship** | "principal mother", "concubine-born offspring" — legalistic/bureaucratic renderings | warning (blocker if user-rejected) |
| **Meta-note rendering** | "provisional, keep for now", "needs system-level review" — meta-instructions passed as renderings | blocker |
| **Unapproved benchmark** | Rendering sourced from a single quality-run model output without explicit approval | warning |
| **Weak evidence** | Risky categories (address/kinship/title) with weak or one-off evidence | warning |
| **User-rejected** | Proposed rendering matches a previously rejected alternative in project assets | blocker |

### Classification criteria

| Verdict | Meaning | Routing |
|---------|---------|---------|
| **SAFE** | No risk signals, or signals overridden by strong evidence / explicit approval | Canonical asset (e.g. `titles_and_terms.md`) |
| **RISKY** | At least one warning signal present, or risky category without sufficient evidence | `unresolved_decisions.md` — needs operator review |
| **REJECTED** | Blocker signal present (meta-note, user-rejected) | Blocked — cannot be canonized in this form |

### Category risk defaults

Even when no specific protection rule triggers, the following categories
default to RISKY unless strong evidence or explicit approval is provided:

- Address terms (e.g. 大小姐, 丫头)
- Kinship terms (e.g. 嫡母)
- Titles and ranks (e.g. 贵妃, 光禄寺卿)

This prevents the system from canonizing a rendering merely because "one
run used it." Glossary terms, character names, and style notes do not have
this default — they are SAFE when no rule triggers and evidence is adequate.

### How to use

```python
from app.chapter.canonization import CanonizationGate, RenderingCategory

gate = CanonizationGate()

# Evaluate a proposed rendering
verdict = gate.classify(
    chinese_term="大小姐",
    proposed_rendering="Young Lady",
    category=RenderingCategory.ADDRESS_TERM,
    evidence_strength="strong",
    user_approved=True,
)

if verdict.risk == "safe":
    # Write to the canonical asset file
    ...
elif verdict.risk == "risky":
    # Write to unresolved_decisions.md instead
    ...
else:
    # Rejected — report back to operator
    ...
```

### What does NOT need the gate

- Corrections that fix obvious typos or formatting in existing canonical entries
- Removal of stale or instruction-leakage entries from asset files
- Edits to `docs/QUALITY_LOOP.md`, `STATUS.md`, or checkpoint files
- Changes to Prompt A / Prompt B (these are governed by the Prompt Change Gate)

### Relationship to the Prompt Change Gate

| Gate | Controls | Resolution types |
|------|----------|-----------------|
| Canonization Gate | `project_assets/` entries | Type A (glossary), Type B (style notes) |
| Prompt Change Gate | `prompts/prompt_a.md`, `prompts/prompt_b.md` | Type C (prompt-level enforcement) |

Both gates must pass before their respective changes are written. They are
independent — an asset entry does not need Prompt Change Gate approval, and
a prompt change does not need Canonization Gate approval.

## Version naming convention

Quality-loop runs on the approved sample use sequential version tags:

| Version | Trigger | Purpose |
|---------|---------|---------|
| v1 | Baseline run | First run with current state |
| v2 | After asset edit | Verify Type A/Type B resolution |
| v3 | After fix commit | Verify fix for regression found in v2 |
| v4 | After prompt edit (gate-approved) | Verify Type C resolution |
| v5+ | Iteration | Further cycles |

The existing runs (v1–v5) are archived at `data/exports/one_chapter_quality_sample_v*.md`.

## Boundary map

| Area | Status | Notes |
|------|--------|-------|
| CLI (`app/cli.py`) | FROZEN | Phase A sealed surface |
| HTTP API (`app/service/`) | FROZEN | Phase A sealed surface |
| Output format contract | FROZEN | Phase A sealed surface |
| Manifest/resume semantics | FROZEN | Phase A sealed surface |
| Quality gate (`app/chapter/quality.py`) | FROZEN | Phase A sealed surface |
| Strategy/budget/enactment | FROZEN | Phase A sealed surface |
| `project_assets/*.md` | GATED | Canonization Gate controls new entries; corrections still OPEN |
| `app/chapter/canonization.py` | OPEN | Canonization gate module |
| Prompt A (`prompts/prompt_a.md`) | GATED | Changes require Prompt Change Gate |
| Prompt B (`prompts/prompt_b.md`) | GATED | Changes require Prompt Change Gate |
| `app/chapter/orchestrator.py` | FROZEN | No application logic changes in Phase B |
| `app/translate/translator.py` | FROZEN | No translation engine changes in Phase B |
| `docs/QUALITY_LOOP.md` | OPEN | This document |
| `STATUS.md` | OPEN | Status updates |
| `SESSION_CHECKPOINT.md` | OPEN | Session checkpoint updates |

## Type C gate records

### Facial-color direction for 黑了

**Gate outcome:** Resolved — Type C enforcement already in place (Prompt A §69).
See `STATUS.md` for the full gate trace.

### Narrative stance / hallucinated scene-closing commentary

**Gate outcome:** Type C enforcement added (Prompt A line 59).

**Gate steps:**
1. **Evidence** (✓): Fabricated scene continuation after source end observed in
   v1, v3, v4, v5 — four quality runs with the same failure pattern.
2. **Lower-level check** (✓): Type A (glossary) not applicable. Type B
   (style note §49-51 of `4. style_notes.md`) was tried and failed — model
   ignores it across all post-writeback runs.
3. **Change proposal** (✓): Add to Prompt A Hard constraints:
   `- Do not add scene-ending commentary or narrative continuation beyond what the source provides.`
   Rationale: existing rules (§58 "do not invent facts", §65 "do not add
   psychological interpretation") are too broad — the model treats scene
   continuation as "predicting the next beat" rather than inventing.
4. **Verification plan** (deferred): Run v6 when Fishhead is reachable.
   Pass criterion: translation ends at source line 82 without fabricated
   continuation or closing commentary.
5. **Approval** (✓): Type C warranted. Minimal targeted change applied.
6. **Execute** (✓): Prompt A diff applied in work branch
   `work/phase-b-type-c-narrative-stance`.
7. **Confirm or revert** (pending): Awaiting Fishhead availability for v6 run.

### Candidates status

Both Type C candidates identified in the closure report are now processed.
No further Type C candidates are currently open.
