# Real-Sample Validation Workflow

## Purpose

This document defines the operator-safe path for bringing a new real Chinese
chapter sample into the translation pipeline and converting its output into
quality improvements (asset entries, prompt rules, book memory updates).

It exists because real samples differ fundamentally from the approved quality
sample (`data/source/one_chapter_quality_source.txt`): they are unpasteurized
novel text, from any source, of any length, at any stage of completeness, and
they must pass through the pipeline without risking operator error, pipeline
misconfiguration, or generated-output leakage into git.

**Scope:** This workflow governs the pre-translation and post-translation
handling of real samples from the operator's perspective. It does not govern
the segment-level translation protocol, which is defined in `WORKFLOW.md` and
executed by the orchestrator.

**This is not a content intake pipeline.** This document describes the current
MVP: manual paste/manual review. A future content intake layer (EPUB parsing,
URL fetching, crawler-import) would build on top of this validation path, not
replace it.

---

## Two sample types

| Type | Path | Tracked? | Purpose | Example |
|---|---|---|---|---|
| **Approved quality sample** | `data/source/one_chapter_quality_source.txt` | Yes (tracked) | Reusable benchmark for quality-loop runs (87 lines, ~2000 chars). Do not expand without a separate batch. | The single file committed to git. |
| **Real sample** | `data/source/<name>.txt` | No (untracked) | One-off novel chapter text for validation runs. Arrives via `./样本` or manual `pbpaste`. Classified as `sample_input` by the hygiene reporter. | `ch1131_v1.txt`, `ch_real_001.txt`, `ch1228_v1.txt` |

Real samples are **locally kept, never committed** to git. The hygiene reporter
(`app/hygiene/reporter.py`) flags any untracked `.txt` file under
`data/source/` as `[sample-input]`, serving as a reminder that these are
local working files, not project artifacts.

---

## Workflow

```
Sample suitability review
        │
        ▼
  Sample intake (manual paste)
        │
        ▼
  Dry-run validation (no model)
        │
        ▼
  Controlled execution (model)
        │
        ▼
  Quality review
        │
        ▼
  Asset updates
```

### Step 0 — Sample suitability review

Before any intake, assess whether the sample is appropriate for a validation
run:

- **Does it belong to an ongoing work with existing project assets?** If yes,
  the glossary, character list, and title system will apply. Ensure
  `--book-memory` is available and current before running.
- **Is the text length reasonable?** The orchestrator segments by character
  boundary (~4000 chars max per segment). Very long samples (multiple chapters)
  should be split into individual chapter files first.
- **Is the sample self-contained?** A single coherent chapter or passage works.
  Fragments, mid-chapter excerpts, or text missing context may produce
  misleading quality signals.
- **Is the source format clean?** Chinese source text only. Remove boilerplate
  (site headers, copyright notices, navigation links) before intake.

No automated check enforces these criteria. They are operator judgment.

### Step 1 — Sample intake (MVP manual entry)

Two entry methods:

**Method A — `./样本` / `./sample` (recommended)**

```bash
# Paste from clipboard
pbpaste | ./样本 ch_my_book_01

# Pipe from file
cat chapter.txt | ./样本 ch_asc_02

# Interactive paste (auto-named)
./样本
```

Validates: empty input, invalid name (alphanumeric/hyphen/underscore only),
duplicate file, content > 1 MB. Saves to `data/source/<name>.txt`. Prints
the next-step dry-run command.

**Method B — Manual file creation**

```bash
# Direct write (operator responsibility to name correctly)
pbpaste > data/source/ch_manual_01.txt
```

No validation. Use only when `./样本` is unavailable. The operator must ensure
the filename follows the naming convention (letters, digits, hyphens,
underscores) and the path is `data/source/`.

**Output:** `data/source/<name>.txt` — untracked, classified as `sample_input`
by the hygiene reporter. Delete when no longer needed.

### Step 2 — Dry-run validation

Before any model execution, validate that the pipeline can parse and plan the
sample. Dry-run requires no model backend and no live inference.

```bash
# Basic dry-run — preview segment plan
venv/bin/python -m app.cli chapter run --dry-run --source data/source/<name>.txt

# With mock fallback — full plan display without model
venv/bin/python -m app.cli chapter run --dry-run --allow-mock-fallback --source data/source/<name>.txt
```

**What the dry-run verifies:**

- The source file is readable and non-empty
- The orchestrator can segment the text (segment count, complexity estimate)
- Strategy parameters resolve within budget
- Book memory context pack builds (if `--book-memory` is passed)
- No import, schema, or pipeline errors

**When dry-run fails:**

| Symptom | Likely cause | Action |
|---|---|---|
| "File not found" | Wrong path or name | Verify filename under `data/source/` |
| Segmentation error | Source file encoding or format | Check for BOM, mixed encodings, or non-text content |
| Strategy resolution failure | Sample too short or empty | Check file content |
| Import error | Code changes or missing dependency | Check git status for unrelated modifications |

Do not proceed to Step 3 until dry-run exits cleanly.

### Step 3 — Controlled execution

Run the real translation against the live model backend. Always use the
chapter-level CLI (`chapter run`, not the legacy `run`).

**Prerequisites:**

1. Fishhead backend reachable (`ssh Fishhead-Core 'hostname && nvidia-smi'`)
2. `MODEL_BACKEND_URL` set to the wrapper endpoint
3. Dry-run passed (Step 2)

**Basic run (no book memory):**

```bash
MODEL_BACKEND_URL=http://192.168.68.51:8001/generate \
  venv/bin/python -m app.cli chapter run \
  --source data/source/<name>.txt \
  --output data/exports/<name>_en.md
```

**Run with book memory (ongoing work):**

```bash
MODEL_BACKEND_URL=http://192.168.68.51:8001/generate \
  venv/bin/python -m app.cli chapter run \
  --source data/source/<name>.txt \
  --output data/exports/<name>_en.md \
  --book-memory data/book_memory/book_memory.json
```

**Run with smoke-test flag (validation-only runs):**

```bash
MODEL_BACKEND_URL=http://192.168.68.51:8001/generate \
  venv/bin/python -m app.cli chapter run --smoke-test \
  --source data/source/<name>.txt \
  --output data/exports/<name>_en.md \
  --book-memory data/book_memory/book_memory.json
```

**Output location:** `data/exports/<name>_en.md` — gitignored, classified as
`generated_output` by the hygiene reporter. Never committed.

**Run isolation rules:**

- Generated artifacts stay under `data/exports/`, `data/output/`, or
  `outputs/` — all gitignored.
- One real-sample validation run per operator session unless the batch
  explicitly authorizes multiple.
- Do not use real-model output to retroactively justify pipeline changes
  inside the same batch (per Fishhead/3090 usage boundary in `CLAUDE.md`).

### Step 4 — Quality review

After execution, inspect the generated output against the source text.

The review methodology is defined in `docs/QUALITY_LOOP.md` (Phase B).
In summary:

1. **Inspect** — Compare output vs source passage by passage. Focus on
   known failure categories (meaning errors, name drift, hallucinated
   additions, register errors, missing content, inline Chinese).
2. **Classify** — Each finding is one of three types:
   - **Type A** (glossary/lexical) — noun-like, concrete. Resolve via
     `project_assets/` edits.
   - **Type B** (style/behavioral) — rule about *how* to translate.
     Resolve via style notes.
   - **Type C** (prompt enforcement) — behavioral rule the model ignores
     from passive guidance alone. Requires the Prompt Change Gate.
3. **Record** — Create or update a findings record under `outputs/`.

For the full gate procedures, see:
- **Canonization Gate** (`CanonizationGate` in `app/chapter/canonization.py`)
  — governs Type A/B asset entries
- **Prompt Change Gate** (`docs/QUALITY_LOOP.md` §"Prompt Change Gate") —
  governs Type C prompt modifications

### Step 5 — Asset updates

If the quality review identifies improvements, write them to the appropriate
permanent location:

| Target | Gate required | Update mechanism |
|---|---|---|
| `project_assets/1. glossary.md` | Canonization Gate (Type A) | Manual edit |
| `project_assets/2. characters.md` | Canonization Gate (Type A) | Manual edit |
| `project_assets/3. titles_and_terms.md` | Canonization Gate (Type A) | Manual edit |
| `project_assets/4. style_notes.md` | Canonization Gate (Type B) | Manual edit |
| `project_assets/5. unresolved_decisions.md` | None (tracking only) | Manual edit |
| `data/book_memory/book_memory.json` | None (memory store) | Manual edit or bootstrap |
| `prompts/prompt_a.md` | Prompt Change Gate (Type C) | Manual edit after gate passes |
| `prompts/prompt_b.md` | Prompt Change Gate (Type C) | Manual edit after gate passes |

**Book memory updates** (`data/book_memory/book_memory.json`) are tracked
in git and committed as part of the batch. Follow the existing pattern:
- New entities discovered from the real sample → add with `status=TENTATIVE`
- New title/term records → add with `category` matching the rendering type
- Translation decisions → add with `status=TENTATIVE` pending cross-chapter
  confirmation

**Commit pattern** from previous real-sample batches (reference):

| Commit | Real sample used | Scope |
|---|---|---|
| `38bc04d` 样本 | — | Sample intake entrypoint (infrastructure) |
| `99f8329` R5/R5a | Smoke-test sample | BookMemory ContextPack path validation |
| `4fda2ee` rules | `ch1131_v1` | +4 characters, +2 glossary, +2 titles, +35 style rules, +19 Prompt A, +4 Prompt B |
| `63355a6` R7 | Chapter 1 (DeepSeek backend) | +3 characters to book memory + assets |

---

## MVP vs Future Content Intake

### Current (MVP) — what this workflow covers

- Manual paste or pipe via `./样本`
- Manual quality review by operator
- Manual asset updates
- One-off samples stored in `data/source/`

### Future roadmap (not yet implemented)

| Capability | Status | Description |
|---|---|---|
| EPUB import | Not started | Parse EPUB chapters and feed into intake workflow |
| URL/content crawler | Not started | Fetch chapter text from web sources |
| Automated extract-transform | Not started | Clean boilerplate and format before intake |
| Bulk import | Not started | Batch-import multiple chapters for a book |
| Scheduled fetch | Not started | Cron-based chapter retrieval for serialized works |

The content intake layer (EPUB parsing, URL fetching, crawler) will call into
**this same validation workflow** as a downstream step. The intake layer
handles source acquisition; this workflow handles validation, execution, and
quality review. The two layers must remain decoupled so validation logic does
not depend on ingestion method.

---

## Quick-reference checklist for a new real sample

```
□ Step 0 — Suitability
  □ Sample belongs to an ongoing work?
    → Confirm --book-memory availability
  □ Text is self-contained (single coherent chapter)?
  □ Source format is clean (no boilerplate)?

□ Step 1 — Intake
  □ pbpaste | ./样本 <name>

□ Step 2 — Dry-run validation
  □ chapter run --dry-run passes
  □ --allow-mock-fallback variant confirmed

□ Step 3 — Controlled execution
  □ Fishhead backend reachable
  □ chapter run --source data/source/<name>.txt --output data/exports/<name>_en.md
  □ Generated output is gitignored and not committed

□ Step 4 — Quality review
  □ Output inspected passage by passage
  □ Findings classified (Type A/B/C)
  □ Findings recorded (optional: findings doc in outputs/)

□ Step 5 — Asset updates
  □ Glossary/characters/titles updated (Canonization Gate if applicable)
  □ Style notes updated (Canonization Gate if applicable)
  □ Unresolved decisions updated if needed
  □ Book memory JSON updated
  □ Prompt changes only after Prompt Change Gate
  □ All changes committed to a work/<topic> branch
  □ Pre-merge gate passes before merging to main
```

---

## Boundary map

| Area | Status | Notes |
|---|---|---|
| `data/source/*.txt` (untracked) | OPEN | Real samples are local working files |
| `data/source/one_chapter_quality_source.txt` | FROZEN | Approved sample; do not expand without separate batch |
| `样本` / `sample` entrypoint | OPEN | Sample intake helper |
| `app/hygiene/reporter.py` (classifier) | OPEN | `sample_input` classification for untracked source files |
| `docs/QUALITY_LOOP.md` | OPEN | Post-execution quality review methodology |
| `docs/REAL_SAMPLE_VALIDATION.md` | OPEN | This document |
| Pipeline code (`app/cli.py`, `app/chapter/`) | FROZEN | No application code changes from real-sample workflow |
| Content intake (EPUB, crawler, URL fetch) | FUTURE | Not implemented; not started |
| Fishhead/3090 | OPERATIONAL | Real-model execution only when reachable |
