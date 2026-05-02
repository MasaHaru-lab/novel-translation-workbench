# Pipeline Contracts

## Purpose

This document maps the contracts between every major stage of the chapter
translation pipeline: what each stage takes as input, what it produces, who
owns it, and what future changes must preserve to avoid breaking dry-run,
resume, quality, or book-memory behavior.

The contracts are written so that a reader modifying one stage knows exactly
what guarantees they owe to downstream consumers and what they can rely on
from upstream producers.

## Architecture overview

```
Source file
    │
    ▼
┌──────────────────┐
│  1. Source Intake │  cli.py, orchestrator.py
│  (read + extract) │
└────────┬─────────┘
         │ source_text, chapter_title
         ▼
┌──────────────────┐
│  2. Chapter Plan  │  orchestrator.plan()
│  (segment +       │  → ChapterPlan
│   strategy)       │
└────────┬─────────┘
         │ plan.segments, plan.strategy_plan
         ▼
    ┌───┴───────────────────┐
    │ for each segment:      │
    │                        │
    │  ┌────────────────────┐│
    │  │ 3. Context Retrieval││  book_memory.retrieval.build_context_pack()
    │  │ (book memory)       ││  → ContextPack.format_text()
    │  └────────┬───────────┘│
    │           │ context_pack_text
    │           ▼             │
    │  ┌────────────────────┐│
    │  │ 4. Segment Trans-  ││  orchestrator._execute_segment_with_retry()
    │  │   lation           ││  → translator.translate_draft()
    │  │   (draft→review→   ││  → translator.polish_translation()
    │  │    polish)          ││  → TranslationOutput
    │  └────────┬───────────┘│
    └───────────┼────────────┘
                │ segment_results: List[TranslationOutput]
                ▼
┌──────────────────┐
│  5. Aggregation   │  format_aggregated_translation()
│  (join segments)  │  → aggregated_translation (str)
└────────┬─────────┘
         │ aggregated_translation
         ▼
┌──────────────────┐
│  6. Consistency   │  consistency.run_consistency_pass()
│  Pass             │  → audit, correction, corrected_text
│  (audit+correct)  │
└────────┬─────────┘
         │ corrected_translation (or fallback to aggregated)
         ▼
┌──────────────────┐
│  7. Quality       │  quality.validate_chapter_output()
│  Validation       │  → QualityReport
└────────┬─────────┘
         │ quality_report (persisted in manifest)
         ▼
┌──────────────────┐
│  8. Output +      │  _report_chapter_result()
│  Manifest         │  → output file, manifest JSON
└──────────────────┘
```

Each stage is defined below.

---

## Stage 1: Source Intake

### Input

| Field | Type | Source |
|---|---|---|
| `source_path` | `Path` | CLI argument (`--source`) |

### Output

| Field | Type | Consumed by |
|---|---|---|
| `source_text` | `str` | Stage 2 (plan) |
| `chapter_title` | `str` (first non-empty line) | Stage 2, Stage 5, Stage 6 |

### Ownership

`app.cli.read_source_file()` and `orchestrator.extract_chapter_title()`.

### Contract

1. The source text is read as UTF-8. Any encoding other than UTF-8 is
   unsupported.
2. `chapter_title` is defined as the **first non-empty line** of the source
   file. For Chinese source novels this is typically `"第一章"` or a similar
   chapter heading.
3. The `chapter_title` is **metadata only**. It must never appear as visible
   Markdown in the final output. This is enforced by the quality gate
   (`title_untranslated`) and the consistency audit (`TITLE_FORMAT`).
4. The source file is read once at the beginning of the pipeline and is not
   re-read during resume. If the source file changes between runs, the
   manifest's `source_text_hash` detects the mismatch — but resume does
   NOT validate this automatically. Re-planning on resume uses the caller's
   `source_text` argument, not the manifest's stored hash.

### Non-goals

- No content-type detection (the pipeline does not distinguish chapter
  content from author notes or front matter).
- No multi-file aggregation at this stage (that's the batch command's job).
- No validation that the source is a valid novel chapter.

### What breaks if you change this

- If `chapter_title` extraction changes semantics (e.g. skips lines, or
  starts using markdown headings), the consistency audit's `TITLE_FORMAT`
  check and the quality gate's `title_untranslated` check may fire
  incorrectly or miss real failures.
- If encoding changes, all downstream string operations are affected.

---

## Stage 1b (Future): Content Intake Layer

### Current state (MVP / operator-validation path)

The current intake is a manual, operator-driven flow:

1. The operator places a `.txt` source file in `data/source/` (or any
   convenient path).
2. The operator invokes `chapter run --source <path>` or `chapter batch`.
3. `read_source_file()` reads the file as UTF-8 text and hands it to
   `ChapterOrchestrator`.

This path has no content-type detection, no source validation, no
multi-source normalization, and no metadata handling beyond extracting
the first non-empty line as `chapter_title`. It is adequate for:
- operator validation of the translation pipeline
- quality-loop sample runs
- one-off chapter translation by the project operator

It is **not** designed for:
- bulk ingestion of an entire book (dozens to hundreds of chapters)
- ingestion from non-`.txt` formats (EPUB, DOCX, HTML, catalog exports)
- ingestion from remote sources (URL fetch, API catalog queries)
- automated chapter discovery, ordering, or deduplication
- provenance tracking (source URL, format origin, import date, hash)

**Explicit statement:** The current manual file-placement + CLI path is
an MVP operator-validation mechanism, not the final bulk-ingestion design.
It exists to validate the translation pipeline, not to solve content
acquisition.

### Future vision

A content intake layer that normalizes external content into source
chapter files + metadata, then hands off to the existing pipeline
(Stage 2+).

### Boundary

The intake layer is responsible for **acquisition → normalization →
dispatch** and nothing else. It stops at the pipeline boundary:

```
[External sources]
    │ paste │ local file │ EPUB │ TXT │ URL │ catalog
    ▼
┌──────────────────────────────────────┐
│  Content Intake Layer                │
│  (acquisition → normalize → dispatch)│
│                                     │
│  1. Source discovery / import       │
│  2. Format normalization            │
│  3. Metadata extraction             │
│  4. Chapter ordering & dedup        │
│  5. Provenance annotation           │
└──────────────┬──────────────────────┘
               │ normalized chapter files
               │ + metadata
               ▼
┌──────────────────────────────────────┐
│  Existing Pipeline (Stage 2–8)       │  ← unchanged
│  (plan → translate → aggregate →     │
│   consistency → quality → manifest)  │
└──────────────────────────────────────┘
```

The pipeline contract at Stage 1's output (`source_text`, `chapter_title`)
remains the canonical intake boundary. The intake layer produces
pipeline-compatible inputs; it does not modify the pipeline.

### Candidate intake sources

| Source | Priority | Risk / constraint |
|--------|----------|-------------------|
| Paste (text fragment) | Highest | Already the MVP path — formalize as an endpoint |
| Local file/folder import (`.txt`) | High | Bulk directory scan, chapter ordering |
| EPUB import | Medium | Need EPUB parsing (e.g. `ebooklib`), chapter splitting, metadata extraction |
| TXT import (large concatenated file) | Medium | Need chapter-boundary detection (separator patterns, chapter-heading regex) |
| URL fetch (single chapter) | Lower | Legal/ToS considerations; cache policy; rate limits |
| Catalog fetch (chapter list from known source) | Lower | Requires catalog URL configuration, pagination, change detection |

### What the intake layer must NOT do

- **Execute translation.** The intake layer normalizes content and stops.
  Translation is the pipeline's job, not the intake layer's.
- **Judge copyright or legality.** The intake layer may annotate provenance
  (source URL, fetch date, hash) but must not make legal determinations.
  Copyright judgment is an operator responsibility.
- **Modify pipeline contracts.** Stage 1's output contract (`source_text`,
  `chapter_title`) is the fixed boundary. The intake layer adapts to it,
  not the reverse.
- **Duplicate into an independent pipeline.** Intake produces
  pipeline-compatible files. It does not reimplement planning,
  translation, or quality validation.

### Non-goals for the roadmap

- No crawler implementation (purpose-built fetch for known sources only)
- No general web spider or auto-discovery
- No automatic content acquisition without operator intent
- No EPUB library integration until a dedicated intake batch
- No URL-source legality review (operator responsibility)
- No change to any existing pipeline code

### Relationship to SKILL.md

`SKILL.md` states as a non-goal: *"Do not: scrape or fetch source text
automatically."* The intake layer does not override this — it provides
the infrastructure so that the operator (not the skill) can ingest
sources. The skill itself remains focused on translation, not acquisition.

### Relationship to existing pipeline contracts

- Stage 1 (Source Intake) is the intake layer's output boundary. The
  intake layer produces files that `read_source_file()` can consume.
- Stage 2+ are unchanged. The intake layer normalizes content into
  the shape the pipeline already expects.
- Manifest/resume semantics are unaffected — the manifest records
  pipeline execution, not intake provenance. Provenance tracking
  (source URL, import date, format origin) is the intake layer's
  responsibility and should be stored alongside the chapter source
  file, not in the translation manifest.

### Implementation order (tentative, not committed)

1. **Paste endpoint** — formalize the existing paste flow as a documented
   intake surface (API or CLI subcommand).
2. **Local folder import** — bulk directory scan with chapter ordering
   (filename-based or heading-based).
3. **Metadata extraction** — chapter title, chapter number, source format,
   import timestamp, content hash for change detection.
4. **EPUB import** — parse EPUB container, extract chapters by spine
   order, preserve metadata (book title, author, chapter mapping).
5. **Single-URL fetch** — parameterized fetch for a known chapter URL
   with caching and ToS-aware rate limiting. Operator-enabled per source.
6. **Catalog fetch** — discover and fetch chapter list from a configured
   catalog URL. Requires per-source authorization (operator opt-in).

Steps 1–3 are the minimal viable intake layer that covers the bulk of
expected operator workflow. Steps 4–6 add format coverage for
real-world book sources.

Each step is a separate batch. No implementation work has been scheduled
or started.

---

## Stage 2: Chapter Plan

### Input

| Field | Type | From |
|---|---|---|
| `source_text` | `str` | Stage 1 |

### Output

| Field | Type | Consumed by |
|---|---|---|
| `ChapterPlan.segments` | `List[Segment]` | Stage 4 (execution) |
| `ChapterPlan.strategy_plan` | `Optional[dict]` | Stage 4 (budget + intensity) |
| `ChapterPlan.complexity_level` | `Optional[str]` | Reporting, enactment record |
| `ChapterPlan.segment_risks` | `Optional[dict]` | Reporting |

### Ownership

`orchestrator.ChapterOrchestrator.plan()` → `ChapterPlan`.

Internally delegates to:
- `segment.segmenter.create_segments()` for text splitting
- `chapter.strategy.assess_chapter_complexity()` for complexity
- `chapter.strategy.assess_segment_risks()` for per-segment risk
- `chapter.strategy.build_strategy_plan()` for strategy decisions

### Contract

1. **Segmentation must be deterministic** for the same source text. Resume
   expects that re-planning produces the same segment IDs in the same order.
   If segmentation changes between runs (e.g. due to a non-deterministic
   algorithm), resume will produce a warning about segment count mismatch
   and will fall back to the manifest's segment set.
2. `ChapterPlan.segment_count` is a property derived from `len(segments)`.
3. `strategy_plan` fields are **planned values** — they express intent
   before execution. They must NOT be confused with enacted (actual runtime)
   values. The enactment record (`ChapterResult.enactment`) carries the
   runtime values and is the authoritative source for what actually happened.
4. Strategy assessment failures are non-fatal: `plan()` falls back to a basic
   plan (no strategy fields) and logs a warning.
5. When `segmentation_granularity == "finer"`, the segments are re-created
   with tighter size targets (800/500 chars) and strategy is re-assessed
   so that segments, risks, and strategies are internally consistent.

### Non-goals

- The plan does not execute any translation.
- The plan does not guarantee that all segments will succeed.
- The plan does not reserve backend capacity.

### What breaks if you change this

- **Segment ID format**: If `segment_id` format changes (e.g. from `"seg_1"`
  to `"s1"`), the manifest's per-segment records lose their mapping to plan
  segments. Resume breaks because `get_pending_segment_ids()` won't match
  the plan's segment IDs.
- **Strategy field names**: If `budget_profile`, `consistency_intensity`, or
  `segmentation_granularity` keys change, `_resolve_budget_from_plan()` and
  `_resolve_consistency_intensity_from_plan()` silently fall back to
  defaults. No error is raised.
- **Segment count**: If the same source text produces different segment counts
  across runs, resume warns and ignores the plan's segments in favor of the
  manifest's. This is safe but means strategy intent from re-planning is lost.

---

## Stage 3: Context Retrieval (Book Memory)

### Input

| Field | Type | From |
|---|---|---|
| `segment.text` | `str` | Stage 2 (a single segment) |
| `BookMemory` | `BookMemory` | CLI-loaded JSON file (`--book-memory`) |

### Output

| Field | Type | Consumed by |
|---|---|---|
| `ContextPack.format_text()` | `str` | Stage 4 (injected into `TranslationInput.context_pack_text`) |

### Ownership

`app.book_memory.retrieval.build_context_pack()`.

### Contract

1. **Deterministic substring matching only.** No NLP, no embeddings, no
   external services. Matching is `name_zh in segment` (substring check).
2. **Advisory only.** The context pack is injected into Prompt A as
   supplementary context. The source text is the primary authority. If book
   memory says "Qin Liuxi" but the source says something different, the
   source wins — the model must not be forced to override the source.
3. **Size bounded.** Default `max_chars=4000`. If the formatted pack exceeds
   this limit, items are dropped from lowest priority first: unresolved
   decisions → translation decisions → relationships → tentative titles →
   tentative entities → confirmed titles → confirmed entities.
4. **Status-aware formatting.** Confirmed records are presented as established
   facts. TENTATIVE and UNRESOLVED records are explicitly labeled.
5. **Not written back.** The translation pipeline never silently updates the
   book memory. Decisions are recorded as a separate human review step.
6. When `book_memory` is `None` (no `--book-memory` flag), the context pack
   is skipped entirely and `context_pack_text` is an empty string.

### Non-goals

- No automatic entity extraction from source text.
- No relationship inference.
- No cross-chapter consistency enforcement (that's Stage 6).
- The context pack does not override or replace Prompt A's asset block.

### What breaks if you change this

- If `build_context_pack()` changes its signature or return type, the
  orchestrator's segment loop `for seg in plan.segments: pack = build_context_pack(seg.text, book_memory)` breaks immediately (type error).
- If `ContextPack.format_text()` changes its output format, Prompt A/B may
  misinterpret the injected section. The section marker string
  `"## Context Pack (retrieved from book memory)"` is the injection anchor.
- If the `max_chars` default changes, context pack size changes silently
  for all callers. Existing segment inputs may become larger or smaller,
  affecting token counts and translation behavior.
- If drop priority order changes, segments that previously saw entity
  matches may no longer see them under the same size constraints, changing
  translation output for those segments on resume.

---

## Stage 4: Segment Translation

### Input

| Field | Type | From |
|---|---|---|
| `Segment` (from plan) | `Segment` | Stage 2 |
| `TranslationInput` (built from segment) | `TranslationInput` | `build_translation_input()` |
| `context_pack_text` | `str` | Stage 3 (or empty) |
| `glossary` | `List[GlossaryTerm]` | Mock or caller-provided |
| `budget_config` | `BudgetConfig` | Stage 2 (from strategy_plan) |
| `model_profile` | `Optional[ModelProfile]` | CLI argument |

### Output (per segment)

| Field | Type | Consumed by |
|---|---|---|
| `TranslationOutput.draft_translation` | `str` | Stage 5 (via polish) |
| `TranslationOutput.polished_translation` | `str` | Stage 5 (aggregation) |
| `TranslationOutput.notes` | `List[str]` | Reporting |

Manifest persistence (for resume):

| Field | Type | Stored in |
|---|---|---|
| `polished_text` | `str` | `SegmentRecord.polished_text` |
| `status` | `SegmentStatus` | `SegmentRecord.status` |
| `retry_count` | `int` | `SegmentRecord.retry_count` |
| `error_message` | `str` | `SegmentRecord.error_message` |

### Ownership

`orchestrator.ChapterOrchestrator._execute_segment_with_retry()`.

Internally calls:
- `translator.translate_draft()` for draft generation
- `translator.polish_translation()` for review+polish

`translate_draft_fn` may be overridden by callers (service client, profile
adapter, test mock).

### Contract

1. **Each segment is isolated.** One failed segment does not abort the chapter.
   Failed segments are recorded in the manifest and can be retried on resume.
2. **Retry discipline** is bounded: `ResumeConfig.max_retries` (default 2)
   attempts per segment, with `ResumeConfig.retry_delay_seconds` (default 1s)
   between attempts.
3. The **manifest is saved after each segment** completes or fails. This is
   the mechanism that makes resume possible.
4. The translation engine (draft → review → polish) is the standard workflow
   defined in `WORKFLOW.md`. Stage 4 does not bypass or modify this workflow.
5. When `model_profile` is provided, review and polish passes use the
   profile's adapter path instead of `MODEL_BACKEND_URL`.
6. During smoke-test mode (`smoke_test=True`), the output is deterministic
   mock text. This is NOT a real translation. Quality gates and consistency
   passes are skipped downstream because the manifest records `smoke_test`.

### Non-goals

- No cross-segment consistency (that's Stage 6).
- No segment reordering.
- No prose polishing beyond the standard draft→review→polish workflow.

### What breaks if you change this

- **`TranslationInput` / `TranslationOutput` schema**: Adding or renaming
  fields requires updating `build_translation_input()`, `translate_draft()`,
  `polish_translation()`, the segment loop in `run_with_manifest()`, the
  resume reconstruction path (lines 500-513 in orchestrator.py), and all
  tests that construct these types.
- **Manifest `polished_text` storage**: The resume path reconstructs
  `TranslationOutput` from `SegmentRecord.polished_text`. If the field
  name changes in `SegmentRecord`, resume silently produces empty output
  for previously completed segments.
- **`context_pack_text` field**: This field on `TranslationInput` is how
  book memory reaches Prompt A. If the field is renamed or removed, context
  packs silently disappear from translations.
- **Retry semantics**: Changing `ResumeConfig` defaults affects all callers.
  If `max_retries` drops to 0, transient backend failures become hard
  segment failures with no recovery.

---

## Stage 5: Aggregation

### Input

| Field | Type | From |
|---|---|---|
| `chapter_title` | `str` | Stage 1 |
| `segment_results` | `List[TranslationOutput]` | Stage 4 |

### Output

| Field | Type | Consumed by |
|---|---|---|
| `aggregated_translation` | `str` | Stage 6 |

### Ownership

`orchestrator.format_aggregated_translation()`.

### Contract

1. **Segments are joined in `segment_id` order** with a blank line between
   sections. Empty polished outputs are skipped.
2. The orchestrator **MUST NOT prepend the source-derived `chapter_title`**
   as a heading. The chapter heading is whatever the segment-level translator
   produced inside segment 1. (Output format contract rule 1.)
3. The raw Chinese `chapter_title` must not appear as the first non-empty
   line of the visible output (rule 2). This is enforced by the quality
   gate (`title_untranslated`) and consistency audit (`TITLE_FORMAT`).
4. Heading shape (`# Title` vs plain English first line) is the segment-level
   translator's responsibility, not the orchestrator's (rule 4).
5. The aggregation function returns a plain string. It does not write to disk.

### Non-goals

- No prose editing or reformatting.
- No reordering of segments.
- No cross-segment deduplication (that's Stage 6).

### What breaks if you change this

- If the join separator changes, the consistency auditor's boundary checks
  (which operate on segment pairs from the ordered list, not the aggregated
  string) are unaffected, but the quality gate's `segment_overlap` check
  still works (it uses the non-separated segment results).
- If rule 1 or 2 of the output format contract is violated (chapter_title
  leaked, CJK first line), both the quality gate and the consistency audit
  fire errors. These are separate detection paths — a change that silences
  one without the other would mask real failures.
- The `final_translation` property on `ChapterResult` (`corrected_translation`
  ?? `aggregated_translation`) means that callers reading the result never
  read the raw aggregated string directly. If aggregation logic changes but
  consistency pass logic doesn't, `final_translation` may return different
  text depending on whether corrections were applied.

---

## Stage 6: Consistency Pass

### Input

| Field | Type | From |
|---|---|---|
| `aggregated_text` | `str` | Stage 5 |
| `chapter_title` | `str` | Stage 1 |
| `segment_texts` | `List[Tuple[str, str]]` | Stage 4 (segment_id + polished_text pairs) |
| `reference` | `Optional[ConsistencyReference]` | `build_consistency_reference()` from project assets |
| `intensity` | `str` ("standard" / "enhanced") | Stage 2 (from strategy_plan) |

### Output

| Field | Type | Consumed by |
|---|---|---|
| `audit_summary` | `Optional[dict]` | `ChapterResult.consistency_audit` |
| `correction_summary` | `Optional[dict]` | `ChapterResult.correction_summary` |
| `corrected_text` | `Optional[str]` | `ChapterResult.corrected_translation` |

### Ownership

`consistency.run_consistency_pass()` → delegates to
`ChapterConsistencyAuditor.audit()` and `ChapterCorrector.correct()`.

### Contract

1. **No full-chapter rewriting.** Corrections are limited to term-level
   string replacements.
2. **No model calls.** The consistency pass is purely deterministic regex
   parsing and replacement, running entirely offline.
3. **No prose polishing.** The auditor finds issues; the corrector applies
   only known-variant → canonical substitutions (auto_fixable=True).
4. **Safe replacement only.** Values containing `[`, `]`, or ` / ` are
   considered unsafe patterns (placeholders or candidate lists) and are
   never used as replacement targets. This is checked both at parse time
   (in `_parse_rendering_value()`) and at apply time (in `ChapterCorrector`).
5. **Word-boundary matching.** All variant detection uses `\b` word boundaries
   to prevent substring corruption (e.g. `"king"` in `"joking"`).
6. **Skips when no segment texts** (empty list → returns None, None, None).
7. **Skips in smoke-test mode** (orchestrator checks `smoke_test`).
8. **Non-fatal.** If the consistency pass raises an exception, the
   orchestrator logs a warning and continues with uncorrected output.

### Non-goals

- No cross-chapter consistency (that's book memory's role).
- No glossary expansion (only corrects known variants to known canonicals).
- No dialogue-tag normalization or punctuation standardization.
- No "enhanced" corrections marked as auto-fixable (they are audit-only).

### What breaks if you change this

- **`ConsistencyReference` structure**: If the reference data classes
  (`CharacterRef`, `TitleRef`, `GlossaryRef`) change their fields, both
  the auditor and corrector need updates. The `build_consistency_reference()`
  function is the single point where asset markdown is parsed into these
  types.
- **Intensity semantics**: The "enhanced" mode adds partial-name drift
  detection. If the intensity keyword changes (e.g. "enhanced" → "strict"),
  the orchestrator silently falls back to "standard".
- **`_is_unsafe_rendering()`**: If the safety check is relaxed (allowing
  `[` or ` / ` through), replacements could corrupt output. If tightened
  (rejecting more patterns), legitimate substitutions might be silently
  skipped. Either change must verify against the quality gate's
  `placeholder_leak` and `slash_list_leak` detectors.
- The quality gate and the consistency audit both check `title_format`
  independently. A change that desynchronizes these two checks (e.g. one
  uses a different definition of "first non-empty line") creates a gap
  where a title leak can pass one gate but not the other.

---

## Stage 7: Quality Validation

### Input

| Field | Type | From |
|---|---|---|
| `ChapterResult` | `ChapterResult` | Stage 5 + Stage 6 |

### Output

| Field | Type | Consumed by |
|---|---|---|
| `QualityReport` | `QualityReport` | `ChapterResult.quality_report` |
| (persisted) `quality_summary` | `dict` | `RunManifest.quality_summary` |

### Quality gates

| Gate code | What it detects | Severity |
|---|---|---|
| `title_untranslated` | First non-empty output line has ≥1 CJK char | error |
| `cjk_residue` | ≥4 CJK chars in final text | error |
| `placeholder_leak` | Unresolved `[Placeholder]` in output | error |
| `slash_list_leak` | Slash-separated candidate list in output | error |
| `empty_segment` | Segment with empty polished output | error |
| `segment_residue` | ≥3 CJK chars in a single segment | error |
| `short_output` | Segment <30 non-space chars | error |
| `segment_truncation` | Non-final segment without sentence-ending punctuation | error |
| `segment_overlap` | Adjacent segments share ≥25 chars at boundary | error |

### Ownership

`quality.validate_chapter_output()` → `QualityReport`.

Populated in `run_with_manifest()` (lines 567-576 of orchestrator.py).

### Contract

1. **Deterministic and offline.** No model calls, no network, no randomness.
   Same input always produces the same report.
2. **Read-only.** The function never modifies `ChapterResult`.
3. **Errors are must-fix.** A `QualityReport` with any `error`-severity issue
   means the manifest's status is demoted from `COMPLETED` to `PARTIAL`. This
   prevents a "completed" manifest from masking bad output.
4. **Warnings are informational.** They do not affect the manifest status.
5. **Skipped in smoke-test mode.** Smoke-test manifests record
   `quality_summary: {smoke_test: true, passed: false}`.
6. **Empty report = passed.** `QualityReport()` with no issues means `passed`.
7. The gate operates on `result.final_translation`, which prefers the
   consistency-corrected text when available.
8. The `title_untranslated` gate and the consistency audit's `TITLE_FORMAT`
   check enforce the same output-format contract independently. Both must
   remain synchronized — see the contract docstring in
   `orchestrator.format_aggregated_translation()`.

### Non-goals

- No translation-quality assessment (fluency, fidelity, style).
- No cross-chapter consistency checks.
- No content verification beyond the deterministic gate list.
- No auto-correction (the quality gate reports, it does not fix).

### What breaks if you change this

- **Demotion logic**: If `validate_chapter_output()` changes its severity
  classification, the orchestrator's demotion logic (lines 573-576 of
  orchestrator.py) may promote or demote status incorrectly. Currently,
  *any* `error`-severity issue triggers demotion to `PARTIAL`.
- **Quality gate thresholds**: If `_CHAPTER_RESIDUE_THRESHOLD` changes from
  4 to a higher value, some CJK residue passes undetected. If it drops to 1,
  isolated characters like "的" in English output trigger false positives.
- **New gate codes**: Adding a new gate code requires updating the manifest's
  `quality_summary` structure (which stores `codes: [str]`). Any downstream
  tool that reads quality summaries must handle the new code.
- If `final_translation` property semantics change (e.g. always returns
  aggregated, never corrected), the quality gate stops inspecting the
  corrected text, creating a gap where consistency fixes could introduce
  issues that the gate misses.

---

## Stage 8: Output and Manifest

### Input

| Field | Type | From |
|---|---|---|
| `ChapterResult` | `ChapterResult` | All previous stages |
| `output_path` | `Path` | CLI argument |

### Output

| Item | Location |
|---|---|
| Chapter Markdown file | `output_path` (e.g. `data/exports/chapter1_en.md`) |
| Run manifest JSON | `<output_path>.manifest.json` |
| Stdout report | CLI console output via `_report_chapter_result()` |

### Ownership

`cli._report_chapter_result()` writes the output and calls `manifest.save()`.

The `RunManifest` class in `manifest.py` owns the serialization format.

### Contract

1. **Output file is written only when** the chapter has at least one
   completed segment (`is_complete or is_partial`).
2. **Output file content** is `result.final_translation` (prefers
   consistency-corrected text when available).
3. **Manifest is always written**, even for partial/failed runs. The manifest
   is the persistent run record.
4. **Manifest path** defaults to `<output_path>.manifest.json` via
   `RunManifest.default_manifest_path()`.
5. **Manifest shape** (key fields):
   - `run_id`: unique 12-char hex identifier
   - `chapter_title`: from source
   - `source_text_hash`: SHA-256 prefix for change detection
   - `total_segments`: int
   - `status`: one of `pending`|`running`|`completed`|`partial`|`failed`
   - `segments`: dict of `segment_id → {status, retry_count, polished_text, ...}`
   - `resume_config`: retry bounds
   - `quality_summary`: `{passed, error_count, warning_count, codes}` or
     `{smoke_test: true, passed: false}`
   - `smoke_test`: bool
6. The manifest is **the single source of truth** for what happened during a
   run. If the manifest says a segment is `COMPLETED`, the resume path trusts
   it and skips that segment.
7. Generated output files (`data/exports/`, `data/output/`, `outputs/`) are
   gitignored. The pre-merge gate (`pre_merge_gate.sh`) verifies they are
   not tracked.

### Manifest state transitions

```
    PENDING
       │
       ▼
    RUNNING ──► COMPLETED (all segments done)
       │          │
       │          ├── quality gate failed → PARTIAL
       │          │
       ├──────► PARTIAL (some segments failed)
       │
       └──────► FAILED (all segments failed)
```

Resumable states: `RUNNING`, `PARTIAL`, `FAILED`.

Terminal states: `COMPLETED` (not resumable — use fresh run to retranslate).

### Non-goals

- No output validation beyond the quality gate.
- No automatic upload or export.
- No diffing against previous output.
- No cleanup of old manifests.

### What breaks if you change this

- **Manifest JSON schema**: Adding, renaming, or removing fields from the
  serialized JSON breaks resume for any manifest written by an older version.
  The `from_dict()` deserialization uses `.get()` with defaults for some
  fields (`quality_summary`, `smoke_test`) but raises `KeyError` for missing
  required fields. See the versioning note below.
- **Manifest path derivation**: If `default_manifest_path()` changes its
  convention, `--resume` won't find existing manifests. Callers would need
  to explicitly pass the manifest path (currently not supported by the CLI).
- **Output path derivation**: If `_derive_output_path()` changes, batch runs
  produce output files at different locations than fresh runs for the same
  source.
- **Smoke-test labeling**: The output file's content is the same format
  regardless of smoke-test mode. Only the console report labels it. If a
  downstream tool reads the output file directly, it cannot distinguish
  smoke-test output from real output without inspecting the manifest.

### Manifest versioning note

The manifest schema has evolved with batches and currently carries optional
fields (`quality_summary`, `smoke_test`, `enactment`) that may be null or
missing in manifests from older runs. The `from_dict()` path uses `.get()`
with safe defaults for these optional fields. However, required fields
(`run_id`, `chapter_title`, `total_segments`, `status`, `segments`) are
accessed with direct key lookup and will raise `KeyError` if absent.

Any future schema change must:
1. Add the new field as optional (nullable or default), with `.get()`
   fallback in `from_dict()`.
2. Update `to_json()` to include the new field.
3. Update `default_manifest_path()` only with a migration strategy for
   existing manifests.

---

## Cross-stage invariants

These are invariants that span multiple stages. Breaking any one requires
coordinated changes across all affected stages.

### Invariant: segment_id is the join key

`segment_id` (a string) is the primary key that joins:
- `ChapterPlan.segments` (list of Segment objects, each with `.segment_id`)
- `RunManifest.segments` (dict[str, SegmentRecord])
- `TranslationInput.segment_id`
- `TranslationOutput.segment_id`
- Consistency auditor's `segment_texts` (list of `(segment_id, text)` tuples)
- Quality gate's per-segment iteration over `segment_results`

**If `segment_id` format changes, all of these must update in sync.**

### Invariant: ChapterResult is the aggregate data contract

`ChapterResult` is the single object that carries output from all stages
through to the CLI/API layer. Adding a field to `ChapterResult` is the
standard way to expose new pipeline output. Removing or renaming a field
affects:
- The orchestrator's `run()` and `run_with_manifest()` return types
- The CLI's `_report_chapter_result()` display logic
- The quality gate's `validate_chapter_output()` input
- The consistency audit report
- The HTTP API's response schema

### Invariant: planned ≠ enacted

`ChapterPlan.strategy_plan` fields are planned values (intent before
execution). `ChapterResult.enactment` fields are actual runtime values.

- `planned.budget_profile` = what the strategy assessment chose
- `enacted.budget.draft_max_tokens` = what was actually passed as
  `BudgetConfig` to the translation functions

These can diverge when budget resolution falls back to defaults (e.g.
unknown profile name → "standard"). The `enactment.consistent` field
reports whether planned and enacted matched.

**Never backfill enactment values into the plan.** The plan must remain
a record of pre-execution intent.

### Invariant: quality gate + consistency audit agree on title format

The chapter Markdown output format contract (documented in
`orchestrator.format_aggregated_translation()`) is enforced by two
independent detectors:

| Detector | Location | Enforces |
|---|---|---|
| `title_untranslated` quality gate | `quality.py:167-177` | First non-empty line has no CJK |
| `TITLE_FORMAT` consistency audit | `consistency.py:557-634` | Raw `chapter_title` not verbatim in output |

Both must agree on:
- What constitutes "first non-empty line"
- What constitutes a CJK title leak
- What "fixed" looks like (neither proposes re-inserting the source title)

Changing one without the other creates a detection gap.

### Invariant: manifest is truth, segments are advisory

On resume, the manifest's list of completed segments is authoritative. The
plan's segment list is advisory (used for ordering and for missing segments).
If the plan and manifest disagree on segment count, the manifest wins
(`orchestrator.py:416-421`). This means:

- Existing completed polished text in the manifest is reused as-is.
- The quality gate sees the manifest's stored text (reconstructed through
  `TranslationOutput`).
- Strategy decisions from re-planning are applied to new segments only.
- Changing the strategy's segmentation granularity on resume affects only
  newly planned segments, which won't match existing manifest segment IDs.

This is by design: it guarantees that a partial run can always be resumed
even if the code has been updated, but it also means that strategy changes
between runs may not take full effect until a fresh run.

### Invariant: manifest path is derived from output path

`RunManifest.default_manifest_path(output_path)` derives the manifest path
by swapping the suffix of the output path. Currently:
`<output>.manifest.json` from `<output>.md` (or any other extension).

This means:
- Two different output paths for the same source produce two independent
  manifests.
- If the output path changes between runs, `--resume` won't find the old
  manifest even for the same source.
- If the suffix-swapping logic changes, existing manifests become
  orphaned — their path no longer matches the derivation rule.

### Invariant: quality gate status demotion

When the quality gate reports any `error`-severity issue, the orchestrator
demotes `chapter_status` from `COMPLETED` to `PARTIAL` and persists this
demotion in the manifest (`orchestrator.py:573-576`).

This means:
- A manifest with `status: "completed"` is a guarantee that the quality
  gate passed (or the manifest predates the quality gate).
- A manifest with `status: "partial"` does not necessarily mean segments
  failed — it may mean segments all completed but quality failed.
- The resume path treats `PARTIAL` as resumable, so a quality-failed run
  can be re-run with `--resume`. However, since all segments are already
  `COMPLETED` in the manifest, resume finds nothing to redo. The quality
  gate fires again on the same output and produces the same result. This
  is a known limitation — re-running a quality-failed chapter requires a
  fresh run (or retranslating at least one segment to invalidate the
  manifest's completed state).
