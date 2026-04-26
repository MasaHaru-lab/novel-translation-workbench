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
Currently: Fishhead wrapper at `http://192.168.68.61:8001/generate`,
model `qwen2.5:14b` via Ollama.

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
MODEL_BACKEND_URL=http://192.168.68.61:8001/generate \
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

- Edits to `project_assets/` files (glossary, style notes, characters,
  titles_and_terms, unresolved_decisions) — these are Type A/Type B and do
  not require gate approval
- Edits to `docs/QUALITY_LOOP.md` or `STATUS.md` or `SESSION_CHECKPOINT.md`
- Corrections to asset files that fix instruction leakage or stale entries

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
| `project_assets/*.md` | OPEN | Type A/Type B resolution |
| Prompt A (`prompts/prompt_a.md`) | GATED | Changes require Prompt Change Gate |
| Prompt B (`prompts/prompt_b.md`) | GATED | Changes require Prompt Change Gate |
| `app/chapter/orchestrator.py` | FROZEN | No application logic changes in Phase B |
| `app/translate/translator.py` | FROZEN | No translation engine changes in Phase B |
| `docs/QUALITY_LOOP.md` | OPEN | This document |
| `STATUS.md` | OPEN | Status updates |
| `SESSION_CHECKPOINT.md` | OPEN | Session checkpoint updates |

## Next natural step after this kickoff

The quality loop closure report (`outputs/quality_loop_closure_report.md`)
identified the first Type C candidates:

1. **Facial-color direction for 黑了** — style note exists (§45-47 of
   `4. style_notes.md`) but model still reverses the signal (dark → pale).
2. **Narrative stance / hallucinated scene-closing commentary** — style
   note exists (§49-51) but model adds closing introspection not in source.

Both have been observed across multiple runs (v1, v3, v4, v5), qualifying
for Step 1 of the Prompt Change Gate.

To proceed: write a change proposal for one of these two candidates,
run it through the gate steps above, then execute and verify.
