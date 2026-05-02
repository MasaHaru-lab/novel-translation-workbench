# Phase C Stage 3 — Quality-Gap Design Note

> **Docs-only design record.** This document captures the quality-gap finding
> from the Stage 2 rehearsal and separates it into actionable design candidates
> for future stages. No runtime code, test edits, prompt changes, quality-gate
> implementation, or real model runs.
>
> Source finding: `docs/records/phase_c_stage2_inspection_rehearsal.md` Issue #5
> (quality gate gap) and Issue #2 ("sheep immortal" terminology downgrade).
>
> **Branch:** `work/phase-c-stage-3-quality-gap-design`
> **Date:** 2026-05-02

---

## 1. Observed Failure

Two systemic issues passed the automated quality gate undetected during the
Stage 2 rehearsal:

### 1.1 Name contamination (pre-fix output, round 2)

The pre-fix output prepended "Chi Yuan Daoist" to "Old Lady Qin" throughout all
three segments, producing "Chi Yuan Daoist Lady Qin" — a compound name that
conflates two distinct characters. The source clearly distinguishes 赤元老道
(Chi Yuan Daoist) from 秦老太太 (Old Lady Qin) as separate entities, appearing
in separate sentences.

The manifest (`phase_b_round2_output.manifest.json`) reported:

- `quality_summary.passed: true`
- `quality_summary.error_count: 0`
- `quality_summary.codes: []`

All nine offline gates passed. The contamination propagated to every segment
and was consistent within each segment — the quality gate reads per-segment
output in isolation and checks for inline source text, structural issues, and
format violations. It does not cross-reference entity identity against project
assets or character lists.

### 1.2 Terminology downgrade (fixcheck output)

The fixcheck output rendered 羊仙 as "sheep immortal" rather than the
established "Ram Immortal" (which the round 2 output correctly used). The
term "sheep" was also used throughout the founding myth passage where "ram"
carries more specific ceremonial weight. This was a fidelity regression in the
fixcheck — the correction pass undid a correct rendering.

The fixcheck manifest also reported:

- `quality_summary.passed: true`
- `quality_summary.error_count: 0`

The quality gate does not verify term renderings against project assets. It
cannot distinguish "sheep immortal" from "Ram Immortal" because it has no
term-reference table.

### 1.3 Common pattern

Both failures share a characteristic: the output is **internally consistent
and well-formed** but **semantically wrong** when compared against external
reference data (character identities, established terms). The quality gate
operates on structural/format properties of the output alone. It has no
access to project assets, character lists, or glossary entries — and was
never designed to verify against them.

---

## 2. Bad-Case Capture Candidate

### 2.1 Problem

When the quality gate passes but the operator (during inspection) judges the
output to have systemic issues, there is currently no automated path to:

- Tag the good manifest/quality-report data with a "gate-passed-but-bad" flag
- Preserve the source + output + manifest + operator notes in a bounded directory
- Make the bad case retrievable for later investigation or regression testing

The current gate-passed state (quality_summary.passed: true) is indistinguishable
between "truly clean output" and "output with undetected semantic failures."

### 2.2 Candidate: operator-initiated capture

The Phase C production workflow (§10, `docs/PHASE_C_PRODUCTION_WORKFLOW.md`)
already defines a capture path (`data/captures/<source_stem>/`) for cases where
the quality gate fails. This candidate extends capture to cover a new trigger:

**Trigger:** Operator judgment during Step 4 (Inspect). The operator decides
the output has systemic issues even though the quality gate passed.

**What is captured:**

| Artifact | Source | Notes |
|----------|--------|-------|
| Source text (copy) | `data/source/<name>.txt` | Preserve the exact input |
| Output text (copy) | `data/exports/<name>_en.md` | The "passed-gate-but-bad" output |
| Manifest | `<output>.manifest.json` | Includes the quality-gate report |
| Operator note | Operator writes a markdown note | One-sentence reason + observed issues |
| Inspection record (optional) | `data/exports/<name>_inspection.md` | If inspection was already written |

**What capture means:**

1. The artifacts are preserved for later investigation
2. The original source file stays in `data/source/` (the operator may retry
   with a fixed pipeline)
3. The captured artifacts become a regression test case when the quality gate
   gains semantic verification

**What capture does NOT mean (repeated from Phase C workflow §10):**

- Not automatic. The operator decides.
- Not a quality action. Capture preserves; it does not fix.
- Not permanent. Captures can be deleted when resolved.

**Boundary:** This candidate is about the operator *workflow* for handling the
bad case. It does not specify what new quality checks should detect it (see
§3). The capture path itself is already sketched in `docs/PHASE_C_PRODUCTION_WORKFLOW.md`
§10 — the addition here is just acknowledging that the capture trigger should
also include operator judgment, not only quality-gate failures.

**Implementation would require:** Creating `data/captures/`, adding it to
`.gitignore`, and writing the operator note template — all consistent with
the existing Stage 3 scope in `PHASE_C_PRODUCTION_WORKFLOW.md` §11 Stage 3.
No code changes to the pipeline, quality gate, or orchestrator.

---

## 3. Future Gate Enhancement Candidate

### 3.1 Problem

The current quality gate has nine offline validators. None of them verify the
output against external reference data. Specifically:

| What it does NOT check | Relevance to Stage 2 failure |
|------------------------|------------------------------|
| Character/entity names against project assets | Would have caught "Chi Yuan Daoist Lady Qin" as a name not in the character list |
| Established term renderings against glossary | Would have flagged "sheep immortal" vs. "Ram Immortal" |
| Per-segment entity consistency across segments | Would have flagged Old Lady Qin appearing as a different entity in different segments |
| Instruction leakage from asset fields | Would have flagged project-asset text appearing verbatim in output |

### 3.2 Candidate: reference-aware quality gate

A future enhancement could add a new class of quality checks that cross-reference
the translated output against project assets:

**Check A — Entity presence verification:**
For each character or entity name in the source that maps to a project-asset
entry, verify that the output contains the canonical rendering at least once,
and does not contain known-aliases in contexts where the canonical form is
expected.

- Would catch: "Old Lady Qin" rendered incorrectly as "Chi Yuan Daoist Lady Qin"
  if "Old Lady Qin" is the canonical rendering for 秦老太太.
- Would not catch: Missed entity references (entity present but in wrong context).

**Check B — Term consistency verification:**
For each glossary entry (Chinese term → English rendering), scan the output
for occurrences of the Chinese term's expected rendering. Flag deviations that
are not known aliases.

- Would catch: 羊仙 → "sheep immortal" when the glossary says 羊仙 → "Ram Immortal."
- Would not catch: Contextual nuance where a deviation is intentional
  (e.g., 羊 in a non-ritual context rendered as "sheep").

**Check C — Cross-segment entity drift:**
Compare entity name renderings across segments. If a character or entity name
appears in multiple segments with different renderings (and neither is a known
alias), flag the drift.

- Would catch: Old Lady Qin rendered as "Chi Yuan Daoist Lady Qin" in seg_1
  and as "Old Lady Qin" in seg_2.
- Would not catch: Consistent but wrong renderings across all segments.

**Design constraint:** These checks must be deterministic and offline (no model
calls). They operate on pattern matching against project-asset files, which are
plain-text markdown. The quality gate must stay fast and free.

### 3.3 Limitation — what reference-aware checks still cannot catch

Even with the enhancements above, these checks would not catch failures of
translation *judgment*:

- Register/tone drift (over-modern phrasing, flattened literary voice)
- Causal or chronological misinterpretation (misread 因此 as "therefore" when
  source implies a weaker link)
- Hallucinated narrative additions when they use correct names and terms
- Facial-color or emotional-state reversals that use the correct vocabulary
  but wrong direction (黑了 → "pale" instead of "darkened" — unless a style
  note explicitly maps the exact rendering)

These remain the domain of operator inspection (Step 4 of the Phase C workflow).

---

## 4. Relationship to Existing Project Structures

### 4.1 Quality gate (`app/chapter/quality.py` — FROZEN)

The existing quality gate is frozen per Phase A sealing. This document does
not propose changes to it. The enhancement candidate in §3 is a **new, separate
gate or gate layer** — not a modification of the existing `validate_chapter_output()`.

The capture path candidate in §2 does not touch the quality gate at all.

### 4.2 Canonization Gate (`app/chapter/canonization.py`)

The canonization gate controls which renderings become canonical in project
assets. A reference-aware quality gate would *consume* canonical renderings
from project assets. The two are complementary:

- Canonization gate: *input* control — what goes into project assets
- Reference-aware gate: *output* verification — what comes out of translation

They do not overlap and do not need to be merged.

### 4.3 Project assets (`project_assets/*.md`)

A reference-aware quality gate would need to parse project assets to build its
reference table. Currently project assets are plain-text markdown files with
no machine-readable schema. An implementation would need either:

- A parser that extracts key-value pairs from markdown tables and lists, or
- A structured data file (YAML/JSON) derived from project assets

The second approach would parallel the existing book memory (`.json`) pattern.
This is a design choice for the implementation batch, not resolved here.

### 4.4 Inspection template (`docs/templates/INSPECTION_RECORD_TEMPLATE.md`)

The template already includes a "PASSED (issues found)" row in the manifest
status combinations table. However, the quality gate field itself shows only
`PASSED` / `FAILED` with no way to record "passed despite observable issues."
A template update could add a **Quality gate confidence** field or a **Gate gap
note** for the operator to flag this situation — but template changes are
out of scope for this design note (they modify the operator workflow).

### 4.5 Quality loop (`docs/QUALITY_LOOP.md`)

The quality loop deals with rule hardening: Type A/B/C resolution driven by
observed failures. The quality-gap finding from Stage 2 is a Type C candidate
(systemic behavioral failure that Type A/B cannot resolve). However, Type C
resolution means prompt-level enforcement, which is a *prevention* strategy.
This document describes a *detection* strategy (capture + gate enhancement).
The two are complementary:

- Prevention (Type C): Improve prompts so the model does not make the error
- Detection (capture + gate): Catch errors that prevention missed

Both paths should exist. This document focuses on detection.

---

## 5. Non-Goals / Stop Line

The following are explicitly **not** within scope of this design document or
its immediate implementation batch:

| Non-goal | Reason |
|----------|--------|
| **Implement the capture path.** Creating `data/captures/`, writing to `.gitignore`, or building a capture helper script. | That is Stage 3 implementation work, separate from this design record. This document only sketches the design. |
| **Implement the reference-aware quality gate or any new validator.** Writing code in `app/chapter/quality.py` or creating a new validation module. | The quality gate is frozen (Phase A). A new gate or gate layer requires a separate design review, implementation batch, and test suite. |
| **Modify the existing quality gate.** Any change to `validate_chapter_output()`, its signatures, its error codes, or its reporting format. | Phase A frozen surface. Even adding a field would require unfreezing. |
| **Modify prompts (Prompt A / Prompt B).** Any Type C prompt-level enforcement to prevent name contamination or terminology downgrade. | The Prompt Change Gate governs prompt edits. This document's scope is detection, not prevention. |
| **Create structured project-asset files (JSON/YAML).** Deriving machine-readable reference tables from project assets. | Implementation work that depends on decisions not yet made. Not needed for the design record. |
| **Modify the inspection record template.** Adding new fields for gate-gap flagging. | The inspection template is the operator workflow surface. A template update needs Stage 2 review/approval, not a design note. |
| **Broad quality-gate redesign.** Re-architecting the existing 9-gate validator, changing its pass/fail semantics, or adding semantic model-based checks that require a model backend. | The gate is meant to stay deterministic, offline, and fast. Any model-based checks belong in a separate layer with different latency/cost characteristics. |
| **Real model run or Fishhead access.** Running the pipeline against real model output to validate any of the proposals in this document. | Not authorized without explicit per-batch approval (per the Fishhead usage boundary in CLAUDE.md). |
| **Entity/name contamination investigation.** Analyzing the root cause of why the model produced "Chi Yuan Daoist Lady Qin." | That is a debugging exercise, not a workflow/gate design question. If needed, it belongs in a separate investigation batch. |
| **Add runtime fields to `ChapterPlan`, backfill enactment from plan, or merge planned/enacted data structures.** | Violates the "Planned vs Enacted" architecture constraint in CLAUDE.md. |

---

## 6. Design Decisions Deferred

| Decision | Context | Suggested trigger for resolution |
|----------|---------|----------------------------------|
| Capture path — CLI helper vs. manual copy | Whether to write a `chapter capture` command (approach in PHASE_C_PRODUCTION_WORKFLOW.md §11 Stage 3) or let the operator copy files manually | When Stage 3 capture-path implementation begins |
| Reference-aware gate — parse project assets vs. derive structured reference file | Parser works on existing markdown files; structured file is more reliable but adds maintenance burden | When gate enhancement batch begins |
| Reference-aware gate — new module vs. extension of existing quality gate | New module keeps Phase A surface frozen; extension touches frozen code | Prior to gate enhancement implementation |
| Template gap flag — add to inspection template vs. keep as operator judgment | Template change standardizes the flag; keeping it informal avoids process overhead | If the gap pattern recurs in ≥2 more inspections |
| Capture trigger — quality-gate failure only vs. include operator judgment | Including operator judgment covers the Stage 2 finding; limiting to gate-failure-only is simpler | When Stage 3 capture-path design is finalized |

---

## 7. Summary

| Layer | What | Status |
|-------|------|--------|
| Observed failure | Automated gate passed; manual inspection found entity contamination and terminology downgrade | Documented in `docs/records/phase_c_stage2_inspection_rehearsal.md` |
| Capture candidate | Extend capture trigger to include operator judgment (gate-passed-but-bad) | Design sketched in §2. Implementation deferred to Stage 3 capture path |
| Gate enhancement candidate | Reference-aware quality checks against project assets | Design sketched in §3. Requires a new batch |
| Prevention (separate) | Type C prompt-level enforcement for name contamination | Prompt Change Gate governs this. Not in scope of this document |
| Non-goals | Implementation, code changes, prompt edits, template changes, broad redesign | Listed in §5 — these are the stop line |
