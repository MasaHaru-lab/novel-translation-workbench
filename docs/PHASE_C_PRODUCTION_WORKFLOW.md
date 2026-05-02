# Phase C: Production Workflow Layer

**Status:** Planning document (not yet implemented)
**Baseline:** `main` at `037649d` (tag: `phase-b-closeout`)
**Date:** 2026-05-02

---

## 1. Phase C Objective

Build a repeatable, operator-safe chapter production workflow on top of the
proven single-chapter translation kernel. The kernel handles the translation
itself (segment → draft → review → polish → aggregate → consistency → quality
gate → manifest). Phase C adds the workflow layer around it: controlled input
paths, predictable run protocols, standardized output locations, per-chapter
inspection records, capture paths for bad cases, and clear stop points that
let the operator run chapters in bounded, auditable units without needing to
navigate the kernel's internals each time.

At the end of Phase C MVP, an operator should be able to:

1. Start a new chapter production run with one command
2. See a plan preview before any model execution
3. Run the chapter safely (with progress visibility)
4. Find the output and manifest at a predictable location
5. Open a per-chapter inspection record
6. Recover from a partial/failed run via resume or capture
7. Stop cleanly at defined chapter boundaries

---

## 2. Non-Goals

Phase C explicitly does **not** address:

- **Translation quality.** Prompt behavior, style rules, asset canonization,
  book memory, and consistency auditing are Phase B concerns. Phase C wraps
  the existing pipeline; it does not change what the pipeline produces.
- **Content intake.** Bulk import from EPUB, URL fetch, crawler operations,
  catalog discovery, multi-format normalization, and provenance tracking are
  a separate intake layer. See the roadmap section below.
- **UI or dashboard.** No web UI, no progress dashboards, no operator GUI.
  The workflow is CLI-based.
- **New backend architecture.** No translation service refactoring, no model
  profile redesign, no parallel execution engine.
- **Bulk/auto-run.** No "translate all 200 chapters overnight" unattended
  batch mode. That requires the intake layer first.
- **Sales/management reporting.** No per-operator productivity tracking, no
  cost-per-chapter analytics.

---

## 3. Baseline

| Field | Value |
|-------|-------|
| Branch | `main` |
| HEAD | `037649d` (docs: close Phase B real-model validation, no fix batch needed) |
| Tag | `phase-b-closeout` |
| Working tree | clean |
| Phase B validation | closed. No further Phase B fixes. |

The translation kernel at baseline has these established capabilities:

- Chinese chapter text → segmentation (deterministic, paragraph-boundary-aware)
- Per-segment draft → Prompt B review → one revision pass if needed
- Per-segment context pack injection (book memory, `--book-memory`)
- Consistency audit (deterministic, offline, term-variant correction)
- Quality gate (deterministic, 9-gate offline validator)
- Manifest-based execution with per-segment progress persistence
- Resume support (`--resume`)
- Output path derivation (`--source` → default `--output`)
- Batch command (`chapter batch --source A --source B`)
- CLI commands: `chapter run`, `chapter stream`, `chapter batch`
- Smoke-test mode (`--smoke-test`)
- Dry-run mode (`--dry-run`)
- Strategy enactment closed loop
- Model profiles (`--model-profile`)
- Pre-run validation guardrails (Stage 4: source checks, book-memory check,
  quality-sample guard, dry-run advisory)
- Branch-aware manifests (`git_ref` in `RunManifest`, populated at run start)
- 677 tests passing (as of Stage 4 closeout)

---

## 4. Current Proven Kernel

```
Chinese chapter text (data/source/<name>.txt)
    │
    ▼
Source Intake ───────── read_source_file(), extract_chapter_title()
    │ source_text, chapter_title
    ▼
Chapter Plan ─────────── create_segments() + strategy assessment
    │ plan.segments, strategy_plan
    ▼ (per segment, loop)
Context Retrieval ────── build_context_pack() (if --book-memory)
    │ context_pack_text
    ▼
Segment Translation ──── translate_draft() → polish_translation()
    │ TranslationOutput (draft + polished + notes)
    ▼ (aggregate)
Consistency Pass ─────── run_consistency_pass() (audit + correct)
    │ corrected_text
    ▼
Quality Gate ─────────── validate_chapter_output() (9 offline gates)
    │ QualityReport (errors → status demotion)
    ▼
Output + Manifest ────── Markdown file + <output>.manifest.json
```

This kernel is proven, tested (616 tests), and validated against real-model
output in Phase B. Phase C does not redesign it.

---

## 5. Production Workflow Layer Responsibilities

The production workflow layer wraps the kernel with:

### 5.1 Controlled Input Path

- A **designated source directory** for active chapters: `data/source/`
- A **working directory** for in-progress chapters (conceptual — same
  `data/source/`, but only chapters the operator has actively queued for
  translation)
- A **convention for chapter naming** that maps a source file to its
  predictable output paths (already partially implemented via output
  derivation)
- An **input gate** that validates the source file before execution
  (readable, non-empty, valid UTF-8, not the approved quality sample)

### 5.2 Control Run Protocol

- "What will happen" before anything runs: **dry-run as mandatory first step**
  for new chapter inputs
- "Is this safe" before real-model execution: **`--confirm` or explicit
  operator go-ahead** on real-model runs
- "What is happening right now": **per-segment progress** during execution
  (already implemented via orchestrator logging)
- "Is this done": **manifest status** (`COMPLETED`, `PARTIAL`, `FAILED`),
  quality gate summary

### 5.3 Predictable Output Paths

- Output file: `data/exports/<source_stem>_en.md`
- Manifest file: `<output_path>.manifest.json` (auto-derived)
- Inspection record: `data/exports/<source_stem>_inspection.md` (Phase C
  addition)
- Outputs are gitignored (already the case for `data/exports/`)

### 5.4 Per-Chapter Records

- **Run manifest** (already exists): `data/exports/<source_stem>_en.manifest.json`
  — segment statuses, quality summary, enactment, smoke-test flag
- **Inspection record** (Phase C addition): `data/exports/<source_stem>_inspection.md`
  — lightweight, operator-written record of what was inspected, observed
  issues, and next actions for the chapter

### 5.5 Bad-Case Capture Path

- A **capture path** for chapters that failed quality or inspection:
  `data/captures/<source_stem>/` — holds:
  - The source file (copy)
  - The failed manifest
  - The quality gate report
  - An operator note explaining why it was captured
- Capture is an operator action, not automatic. The operator decides when
  a chapter warrants capture.

### 5.6 Branch/Tag Awareness

- Each production run should know what branch and commit it ran on
- Manifest already records pipeline version implicitly. A `git_ref` field
  can be added to the manifest to pin the code state.

---

## 6. Proposed Operator Workflow

```
┌──────────────────────────────────────────────────────────┐
│               CHAPTER PRODUCTION RUN                      │
│                                                           │
│  1. QUEUE CHAPTER                                         │
│     Place source file in data/source/<name>.txt           │
│     (or confirm existing file)                            │
│                                                           │
│  2. DRY-RUN (MANDATORY FIRST STEP)                        │
│     venv/bin/python -m app.cli chapter run --dry-run \    │
│       --source data/source/<name>.txt                     │
│     → Review plan: segments, complexity, risks            │
│                                                           │
│  3. CONFIRM AND RUN                                       │
│     venv/bin/python -m app.cli chapter run \              │
│       --source data/source/<name>.txt \                   │
│       --book-memory data/book_memory/book_memory.json \   │
│       --model-profile deepseek-v4-flash                    │
│     → Watch per-segment progress                          │
│     → Check exit status and manifest state                │
│                                                           │
│  4. INSPECT                                               │
│     Read data/exports/<name>_en.md                        │
│     Compare passage by passage against source             │
│     Write data/exports/<name>_inspection.md               │
│                                                           │
│  5. GATE DECISION                                         │
│     ┌─────────────────────────────────────┐               │
│     │  PASS → QA pass, ready for next step│               │
│     │  PARTIAL → resume or capture        │               │
│     │  FAIL → capture to data/captures/   │               │
│     └─────────────────────────────────────┘               │
│                                                           │
│  6. NEXT CHAPTER OR STOP                                  │
│     → Return to step 1, or stop at batch boundary         │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### 6.1 Operator Steps in Detail

**Step 1 — Queue chapter:**
The operator places a `.txt` source file in `data/source/`. Existing
chapters in that directory are candidates. The `./样本` helper can be used
for paste intake.

**Step 2 — Dry-run (mandatory first step):**
Before any model execution, run `--dry-run` to preview the plan. This
verifies that the pipeline can parse the source, segment it, resolve
strategy parameters, and build context packs. No model backend is needed.

The operator reviews:
- Segment count (sanity check: does it match expectations for the chapter?)
- Complexity assessment
- Budget profile
- Consistency intensity

If dry-run fails, diagnose before proceeding. Common causes: file encoding,
empty content, corrupt file.

**Step 3 — Confirm and run:**
Run the real translation. Include `--book-memory` if the chapter belongs
to an ongoing work with established book memory, and `--model-profile` if
using a specific model backend.

The operator watches per-segment progress and waits for completion.

Exit codes:
- `0` — run completed (may be `PARTIAL` or `COMPLETED`)
- Non-zero — infrastructure error (not a chapter failure; needs
  investigation)

**Step 4 — Inspect:**
The operator reads the output file and compares it against the source,
passage by passage. This is the same quality review methodology defined in
`docs/QUALITY_LOOP.md` but applied per chapter rather than per quality-loop
run.

The operator writes a lightweight inspection record to
`data/exports/<name>_inspection.md` documenting what was checked, any
issues found, and next actions.

**Step 5 — Gate decision:**

| Manifest status | Quality gate | Inspection | Action |
|-----------------|--------------|------------|--------|
| COMPLETED | passed | no issues found | Chapter done. Proceed to next chapter or stop. |
| COMPLETED | passed | minor style observations (not blockers) | Chapter done. Optionally record observations for future style-note hardening. |
| COMPLETED | passed | issues found | Determine if finding is Type A/B/C. Apply asset fix, or defer to Phase B quality loop. If deferred, record in inspection. Chapter status remains done for production purposes. |
| PARTIAL | failed | N/A | Resume with `--resume`. If retries exhausted, capture. |
| PARTIAL | passed | N/A | (Should not normally occur — manifest PARTIAL + quality pass means segments are incomplete but the partial output is clean.) Capture or resume. |
| FAILED | N/A | N/A | Capture to `data/captures/`. |

**Step 6 — Next chapter or stop:**
If more chapters are queued in the same batch, return to Step 1. Otherwise,
stop at the batch boundary. A batch is one or more chapters the operator
intends to complete before merging to `main`.

---

## 7. Expected Input/Output Paths

| Role | Path | Tracked? | Notes |
|------|------|----------|-------|
| Source (input) | `data/source/<chapter_name>.txt` | No (untracked; classified `sample_input`) | The approved quality sample (`one_chapter_quality_source.txt`) is tracked. Real sources are not. |
| Output (translation) | `data/exports/<chapter_name>_en.md` | No (gitignored) | Derived from source filename. |
| Manifest | `data/exports/<chapter_name>_en.manifest.json` | No (gitignored) | Auto-derived from output path. |
| Inspection record | `data/exports/<chapter_name>_inspection.md` | No (gitignored) | Operator-written. Lightweight markdown. |
| Capture record | `data/captures/<chapter_name>/` | No (Stage 3) | Planned. To be gitignored. Source + manifest + quality report + operator note. |
| Book memory | `data/book_memory/book_memory.json` | Yes (tracked) | Versioned alongside code. |
| Project assets | `project_assets/*.md` | Yes (tracked) | Versioned alongside code. |
| Real samples (intermediate) | `data/samples/` | No (gitignored) | For multi-file real samples during validation. |

### 7.1 Path Derivation Rule

The output path derivation (already implemented) follows this convention:

```
data/source/<name>.txt → data/exports/<name>_en.md
```

For example:
- `data/source/chapter_03.txt` → `data/exports/chapter_03_en.md`
- `data/source/ch_asc_01.txt` → `data/exports/ch_asc_01_en.md`

The manifest path is derived by appending `.manifest.json` to the output
path (already implemented):
- `data/exports/chapter_03_en.md` → `data/exports/chapter_03_en.manifest.json`

The inspection record path follows the same convention:
- `data/exports/chapter_03_en.md` → `data/exports/chapter_03_inspection.md`

These derivation rules are **conventions**, not enforced. The operator can
override `--output` to place files elsewhere. But the default convention
ensures predictability for the common case.

---

## 8. Required Per-Chapter Records/Artifacts

### 8.1 Run Manifest (already exists)

Produced automatically by `chapter run`. See `docs/PIPELINE_CONTRACTS.md`
Stage 8 for the full schema. Key fields for production tracking:

```json
{
  "run_id": "a1b2c3d4e5f6",
  "chapter_title": "...",
  "source_text_hash": "abc123...",
  "total_segments": 5,
  "status": "completed",
  "segments": {
    "seg_1": { "status": "COMPLETED", "retry_count": 0 },
    ...
  },
  "quality_summary": { "passed": true, "error_count": 0, "codes": [] },
  "smoke_test": false
}
```

### 8.2 Inspection Record (Phase C addition)

A lightweight, operator-written markdown file at
`data/exports/<name>_inspection.md`. Template:

```markdown
# Inspection: <chapter_name>

**Source:** `data/source/<name>.txt`
**Output:** `data/exports/<name>_en.md`
**Manifest:** `data/exports/<name>_en.manifest.json`
**Inspected:** 2026-05-02

## Summary
- Status: COMPLETED / PARTIAL / FAILED
- Quality gate: PASSED / FAILED
- Segments: N/N

## Issues Found
| Passage | Issue | Type | Action |
|---------|-------|------|--------|
| seg_2 | ... | Type A/B/C | ... |

## Next Actions
- [ ] Record findings in style notes / glossary / prompts
- [ ] Update book memory if needed
- [ ] Deferred items (if any)

## Verdict
PASS / HOLD / CAPTURE
```

This is a human-readable record. A script could auto-populate the header
from the manifest, but the inspection content is the operator's judgment.

### 8.3 Capture Record (Phase C addition)

When a chapter fails quality or the operator decides it cannot proceed:

- The operator writes a **capture note** using the `BAD_CASE_CAPTURE_TEMPLATE.md`
  and places it at `data/captures/<capture_name>/capture_note.md`.
- Artifacts (source copy, output copy, manifest) are placed in the same directory.
- The bad case is indexed in `docs/bad_cases/INDEX.md` for future reference.

**Template:** `docs/templates/BAD_CASE_CAPTURE_TEMPLATE.md`
**Index:** `docs/bad_cases/INDEX.md`
**Directory:** `data/captures/` (gitignored — created, exists as of Stage 3A)

---

## 9. Quality and Inspection Gates

### 9.1 Dry-Run Gate

| What it checks | Severity |
|----------------|----------|
| Source file is readable | blocker |
| Source file is non-empty | blocker |
| Source file is valid UTF-8 | blocker |
| Orchestrator can segment and plan | blocker |
| Strategy parameters resolve | warning |
| Book memory context pack builds (if `--book-memory`) | warning |

**Action:** Run `chapter run --dry-run --source <path>`. Must pass before
real-model execution.

### 9.2 Run-Time Gate

Already implemented by the orchestrator:
- Per-segment failure isolation (one failed segment does not abort)
- Bounded retries (`ResumeConfig.max_retries`, default 2)
- Manifest saved after each segment

### 9.3 Quality Gate (already exists)

Nine deterministic, offline gates documented in `docs/PIPELINE_CONTRACTS.md`
Stage 7. Error-level issues demote manifest status from `COMPLETED` to
`PARTIAL`.

### 9.4 Inspection Gate (operator judgment)

The operator reads the output and decides:
- Has the chapter passed quality review?
- Are there findings for the Phase B quality loop?
- Should the chapter be captured?

This is the same review methodology from `docs/QUALITY_LOOP.md` and
`docs/REAL_SAMPLE_VALIDATION.md`, applied iteratively per chapter rather
than only during formal quality-loop runs.

### 9.5 Pre-Merge Gate (already exists)

`scripts/checks/pre_merge_gate.sh` — verifies working tree cleanliness and
generated-output tracking before merging to `main`. This gate is not
per-chapter; it is per-batch.

---

## 10. Bad-Case Capture Rule

### When to capture

A chapter should be captured when any of these conditions are met:

1. **Quality gate failed** after resume max retries
2. **Manifest status is `FAILED`** (all segments failed)
3. **Operator judgment:** the output has systematic issues (e.g., pervasive
   meaning errors, wrong book detected, source file corrupt)
4. **Infrastructure failure** prevented completion and the run state is
   unrecoverable

### What capture means

- A capture note is written using the template at
  `docs/templates/BAD_CASE_CAPTURE_TEMPLATE.md` and placed in
  `data/captures/<capture_name>/capture_note.md`
- Source file is copied to `data/captures/<capture_name>/source.txt`
- Output file is copied to `data/captures/<capture_name>/output.md`
- Manifest is copied to `data/captures/<capture_name>/output.manifest.json`
- The bad case is registered in `docs/bad_cases/INDEX.md`
- The original `data/source/<name>.txt` is **not deleted** (the operator
  may retry with a fixed pipeline)

### What capture does NOT mean

- Not automatic. The operator decides.
- Not a quality action. Capture preserves the bad case for investigation;
  it does not fix anything.
- Not permanent. Captures can be deleted when the underlying issue is
  resolved and the chapter is retranslated successfully.

### Captures cleanup

Captured chapters have no automatic lifecycle. The operator should clean
up captures when the underlying issue is resolved. A periodic reminder
(e.g., weekly check) is sufficient.

---

## 11. Staged Implementation Plan

### Stage 1: Convention Documentation (docs-only)

**What:** This document. Define the production workflow conventions without
changing any code. Document:
- Path conventions
- Operator workflow
- Inspection record template
- Capture record template
- Stop points

**Verification:** This document exists and is reviewed.

**Estimate:** 1 session (this batch).

### Stage 2: Inspection Record Template File

**What:** Create a script or CLI command that auto-generates the inspection
record template from a manifest:

```
venv/bin/python -m app.cli chapter inspect --source data/source/<name>.txt
```

This would read the manifest (if available), pre-fill the header fields,
and write a template `_inspection.md` file. The operator fills in the rest.

**Not implemented yet.** Pending Stage 1 approval.

### Stage 3: Capture Path Creation

**What:** Create the `data/captures/` directory and add it to `.gitignore`.
Write an operator-facing bad-case capture template and a lightweight bad-case
index for future reference.

**Delivered:** Stage 3A (partial — directory, gitignore, template, index).

| Artifact | Path | Status |
|----------|------|--------|
| Capture directory | `data/captures/` | created + gitignored |
| Capture template | `docs/templates/BAD_CASE_CAPTURE_TEMPLATE.md` | created |
| Bad-case index | `docs/bad_cases/INDEX.md` | created |
| Capture helper script | — | deferred (operator workflow is manual for now) |

### Stage 4: Pre-Run Validation Gate

**Delivered (Stage 4 — 2026-05-02).**

Adds a lightweight pre-run validation step to the CLI that performs the
following deterministic, offline checks before any chapter translation begins:

| Check | Type | Behavior |
|-------|------|----------|
| Source file validity | Hard error | File must exist, be a regular file, valid UTF-8, and non-empty |
| Quality sample guard | Warning | Warns when the approved quality sample is used as source (it is reserved for quality-loop runs) |
| Book memory existence | Hard error | File declared via `--book-memory` must exist and be a regular file |
| Dry-run advisory | Warning | Suggests `--dry-run` first when running a new source that has no existing manifest |

Validated by `app/chapter/validator.py` and wired into `run_chapter_pipeline()`
and `run_chapter_stream()`. Tested with 35 dedicated tests.

**Delivered as a package with Stage 4B (branch awareness):**

| Check | Type | Behavior |
|-------|------|----------|
| Git ref capture | Metadata | Resolves `<branch> @ <short-commit>` at run start and populates `git_ref` in `RunManifest` for all downstream artifacts |

The `git_ref` field is added to `RunManifest` (`app/chapter/manifest.py`) and
populated in the CLI after the orchestrator run completes. It provides run
traceability without modifying the orchestrator kernel.

**Stage 4 explicitly does not include:**
- Modifications to the orchestrator, quality gate, prompts, or translation logic
- Changes to how `chapter run`, `chapter stream`, or `chapter batch` decide what
  to translate or how to translate it
- A `--no-validate` skip flag (advisory warnings can already be safely ignored;
  hard errors are always legitimate problems)
- Automation of the capture path or bad-case helper scripts

### Stage 5: Complete Production Workflow Integration

**What:** Tie all the pieces together. The operator workflow from §6 should
be executable end-to-end with CLI commands at each step.

**Not implemented yet.** This is the MVP endpoint.

### Implementation Boundary

Each stage is a separate batch with its own acceptance criteria, stop
points, and review gate. Stage 1 must pass review before Stage 2 begins.
Do not overlap stages in the same batch unless the operator explicitly
authorizes it.

---

## 12. Acceptance Criteria for Phase C MVP

Phase C MVP is reached when all of the following are true:

1. [ ] **Convention documented.** The path conventions, operator workflow,
   and record templates defined in this document are accepted as the
   project standard.

2. [ ] **Inspection record creation.** There is a documented way (script
   or manual) to create an inspection record for a completed chapter.

3. [x] **Capture path exists.** `data/captures/` exists, is gitignored,
   and can hold a captured chapter's artifacts.

4. [x] **Pre-run validation.** The CLI warns the operator before running
   without a prior `--dry-run` on a new (untracked) source file. The
   warning is advisory (not a blocker) — experienced operators can proceed
   past it.

5. [x] **Branch awareness.** Each chapter run produces artifacts that the
   operator can trace back to the code state (branch + commit). The
   `RunManifest` now includes a `git_ref` field, populated from `git
   rev-parse` at run start.

6. [ ] **End-to-end operator workflow.** An operator can complete a chapter
   from source file to inspection record using the documented workflow
   without encountering unexpected pipeline behavior.

7. [ ] **Bad-case handling.** The operator knows what to do when a chapter
   fails and can capture the state for later investigation.

8. [x] **Test suite still passes.** All 677+ existing tests pass. Any new
   code added in Phase C has test coverage.

9. [ ] **Working tree discipline maintained.** Generated outputs remain
   gitignored. The pre-merge gate continues to pass.

---

## 13. Explicit Stop Points Requiring User Approval

These actions within Phase C require explicit operator approval before
proceeding:

| Stop point | Context | Why |
|-----------|---------|-----|
| **Stage boundary** | Completion of any Stage 1–5 implementation stage | Each stage changes the operator workflow. The operator must review and approve before the next stage begins. |
| **First inspection record template** | Stage 2: before writing the first `chapter inspect` command or helper script | The inspection record format affects the operator's daily workflow. The template must be reviewed. |
| **New `data/captures/` directory** | Stage 3: before creating the capture path and `.gitignore` entry | Capture is a new concept. The operator must agree it is worth implementing. |
| **Pre-run validation warning** | Stage 4: CLI validation logic | Adding CLI warnings changes the operator's command behavior. The operator must agree on the warning text and behavior. |
| **Branch awareness (git_ref)** | Stage 4B: RunManifest `git_ref` field | Adding run traceability requires a manifest schema change. The operator must agree on the field format and population strategy. |
| **Any code change to kernel** | Any stage that touches `app/chapter/orchestrator.py`, `app/chapter/quality.py`, prompts, or translation logic | The kernel is frozen. Any Phase C code change to the kernel requires a written justification and explicit approval. |

---

## 14. Roadmap-Only: Content Intake Layer

**This section is future roadmap, not Phase C scope.** It is included here
so that the boundary between Phase C and the content intake layer is clear.

### What it is

A separate layer that handles external content acquisition and normalization
before the translation pipeline. Documented conceptually in
`docs/PIPELINE_CONTRACTS.md` Stage 1b. The intake layer produces files that
the existing pipeline can consume; it does not modify the pipeline.

### High-level capabilities (not committed)

| Capability | Description | Priority | Dependency |
|-----------|-------------|----------|------------|
| Paste endpoint | Formalize the existing `./样本` flow as a documented intake surface | Highest | None |
| Local folder import | Bulk directory scan with chapter ordering | High | Phase C output conventions |
| Metadata extraction | Chapter title, number, source format, import timestamp, hash | High | Phase C manifest |
| EPUB import | Parse EPUB container, extract chapters by spine order | Medium | Metadata extraction |
| Single-URL fetch | Parameterized fetch for a known chapter URL | Lower | Legal/ToS review |
| Catalog fetch | Discover and fetch chapter list from a configured catalog URL | Lower | Authorization infra |

### Relationship to Phase C

Phase C and the intake layer are independent:

- Phase C defines the **output-side** workflow: how the operator runs, inspects,
  and captures chapters after the pipeline processes them.
- The intake layer handles the **input-side** workflow: how source text gets
  from external formats into `data/source/`.

The two layers meet at `data/source/`. The intake layer deposits files there;
Phase C's operator workflow picks them up. No architectural coupling is needed.

### Boundary summary

```
[External sources]          [Chapter production]
  │                           │
  ▼                           ▼
┌──────────────┐         ┌──────────────┐
│ Intake Layer │ ──→ data/source/ ──→ │ Phase C Workflow │
│ (roadmap)    │         │ (operator workflow) │
│              │         │                │
│ src → file   │         │ dry-run → run  │
│ │            │         │ → inspect      │
│ │            │         │ → gate         │
│ │            │         │ → capture      │
│ │            │         └───────┬────────┘
│ │            │                 │
│ │            │         data/exports/
│ │            │         data/captures/
│ │            │         data/book_memory/
│ │            │
└──────────────┘

Phase C does not build intake. Intake does not redesign the pipeline.
```

### What the intake layer must NOT do (restated from PIPELINE_CONTRACTS.md)

- Execute translation
- Judge copyright or legality
- Modify pipeline contracts (Stage 1's output contract is fixed)
- Duplicate into an independent pipeline
- Implement web crawling or automatic content acquisition without operator intent
- Change any existing pipeline code

### Non-goals for the intake roadmap

- No crawler implementation (purpose-built fetch for known sources only)
- No general web spider or auto-discovery
- No automatic content acquisition without operator intent
- No EPUB library integration until a dedicated intake batch
- No URL-source legality review (operator responsibility)
- No change to any existing pipeline code
