# Status: Phase A Sealed

**Phase A is frozen as of 2026-04-26.** All Phase A surfaces (CLI, HTTP, output format, framework migration, quality gate) are sealed. No further Phase A work will be opened.

## Framework Migration Complete (2026-04-25)

The translation framework has been migrated to a reusable, direction-agnostic skill. **Sealed — no further architecture changes in this phase.**

- **Framework**: `fishhead-literary-translator` is the reusable literary translation production framework.
- **Direction profile**: `zh_to_en` is the first implemented direction profile.
- **Roles**: A = literary translator. B = quality gate / reviewer.
- **Implementation**: `novel-translation-workbench` (this repo) is the current implementation, **not** the skill itself.
- **Canonical skill (runtime)**: `~/.claude/skills/fishhead-literary-translator/`
- **Versioned snapshot (this repo)**: `docs/skill_snapshot/fishhead-literary-translator/`
- **Mapping doc**: `docs/SKILL_INTEGRATION.md` explains how this implementation maps to the skill.
- **Migration commits**:
  - `f754654` — docs: add SKILL_INTEGRATION explaining fishhead-literary-translator mapping
  - `e685c10` — docs: add versioned snapshot of fishhead-literary-translator skill

---


## Current Capabilities

- ✅ **Chapter-level CLI** (`chapter run`, `chapter stream`, `chapter run --dry-run`, `chapter run --resume`)
  - Per-segment progress logging during fresh-run execution
  - Plan preview with segment count, complexity, budget, consistency intensity
  - Manifest-based resume with failure isolation, retry, and guidance
- ✅ **Book memory retrieval / context-pack layer (R2)**
  - `build_context_pack(segment, memory)` for deterministic substring matching of entities, titles, and relationships
  - Hard 4000-char context pack limit with priority-based truncation (confirmed kept over tentative)
  - Status-preserving output with `[TENTATIVE]` and `[UNRESOLVED]` labels
  - 36 dedicated tests, all passing; module is built, tested, but not yet wired into translation pipeline
- ✅ **Chapter-level HTTP API** (`POST /translate/chapter`)
  - Full manifest/resume semantics (fresh run, resume with existing manifest)
  - Direct access to `ChapterOrchestrator.run_with_manifest()`
  - Returns structured JSON: aggregated translation, consistency audit, strategy, enactment, readable summary
  - 26 endpoint tests (mocked, no real-model execution)
  - No quality-gate bypass, no CLI logic duplication
- ✅ **Chapter orchestration** (plan → execute → aggregate → consistency pass)
  - Chapter plan generation with pre-execution strategy assessment
  - Segment-level execution via existing translation engine
  - Strategy enactment closed loop (budget/consistency resolved from plan, record attached to `ChapterResult`)
- ✅ **Consistency audit** (term unification, limited automated correction)
- ✅ **Advanced CLI output** — strategy overview, consistency summary, resume guidance
- ✅ **592 tests passing** (26 service + 74 CLI + 39 chapter + 36 retrieval + others)

## What's Still Missing (Phase B and later)

- **Phase B**: Real translation models (currently mocked for tests)
- **Phase B+**: Sentence‑level splitting for long paragraphs (splits by character boundary)
- **Phase B+**: Configuration file for segment size, model paths
- **Phase B+**: HTTP polish endpoint (`POST /translate/polish`)

## Known Limitations

- Segmentation is greedy: adds paragraphs until the next would exceed `max_chars`, can create segments much smaller than `max_chars`.
- No sentence‑level splitting within long paragraphs.
- Strategy parameters are internal-only (no CLI/HTTP user control).

## Run Instructions

```bash
# Chapter-level CLI (recommended)
python -m app.cli chapter run                          # fresh run
python -m app.cli chapter run --dry-run                # preview plan
python -m app.cli chapter run --resume                 # resume partial run
python -m app.cli chapter stream                       # stdout-only mode
python -m app.cli chapter batch --source f1 --source f2   # batch multi-file

# Legacy segment-level pipeline
python -m app.cli run
```

## Test Instructions

```bash
python -m pytest app/tests/
```

All 592 tests should pass (74 CLI + 39 chapter + 36 retrieval + others).

## Phase B — Quality Loop

**Phase B is active as of 2026-04-26.** The quality-loop methodology and Prompt Change Gate are documented in `docs/QUALITY_LOOP.md`.

### Current slice: Prompt Change Gate established

- **Quality review methodology** documented (run → inspect → classify → gate → revise → verify)
- **Finding classification** defined: Type A (glossary/lexical), Type B (style notes), Type C (prompt-level enforcement)
- **Prompt Change Gate** defined: required 7-step review process before any modification to Prompt A or Prompt B
- **Boundary map** documented (frozen surfaces vs open vs gated areas)
- **No application code or prompt files modified** in this kickoff slice

### Prompt Change Gate — facial-color direction (verified v6)

**Gate outcome:** Resolved — Type C enforcement effective. Verified v6 PASS (2026-04-26).

**Evidence (gate Step 1):** Facial-color reversal for 脸色都黑了 observed across
multiple runs (v1: "turned pale" ✗; v3: "turned pale, clearly displeased" ✗;
v2/v4/v5/v6: correct). Two failures met the multi-occurrence bar; last 4 runs confirm fix.

**Lower-level check (gate Step 2):** Type B (style note at §45-47 of
`4. style_notes.md`) was tried and failed in v3 — model captured the displeasure
emotion but reversed the color signal ("pale" instead of "darkened").

**Change proposal (gate Step 3):** The Type C rule already exists at Prompt A
line 69: *"Do not reverse facial-color emotional signals. 黑了 means the face
darkened (with displeasure), not turned pale."* Added in commit `06e04cd`
before the gate was formalized.

**Verification (gate Step 4):** v6 run on 2026-04-26, `qwen2.5:14b` via Ollama.
秦老太太一呛，脸色都黑了 → "Old Lady Qin was taken aback, her face darkening."
**PASS** — direction correct. Type C rule effective.

### Prompt Change Gate — narrative stance / hallucinated scene-closing commentary (verified v6)

**Gate outcome:** Type C enforcement effective. Verified v6 PASS (2026-04-26).

**Evidence (gate Step 1):** Fabricated scene continuation after source end
observed in all quality runs (v1: full continuation paragraph; v3: continuation
with invented dialogue; v4/v5: same pattern). 4 of 4 runs show the failure.

**Lower-level check (gate Step 2):** Type B (style note at §49-51 of
`4. style_notes.md`) was tried and failed across v3, v4, v5 — the style note
exists but the model ignores it for scene-closing content.

**Change proposal (gate Step 3):** Add to Prompt A Hard constraints:
`- Do not add scene-ending commentary or narrative continuation beyond what the source provides.`
Positioned after existing "Do not invent facts" rule (§58) since this is a
specific subclass of that constraint. Existing rules were too broad — the model
treats scene continuation as "generating the next expected beat" rather than
"inventing facts."

**Verification (gate Step 4):** v6 run on 2026-04-26, `qwen2.5:14b` via Ollama.
Translation ends at source line 82: 谢氏像是一拳打在棉花上，气闷不已 →
"Lady Xie felt frustrated, like hitting a soft wall."
**PASS** — no fabricated continuation. Type C rule effective.

**Applied in:** work branch `work/phase-b-type-c-narrative-stance`,
Prompt A diff committed.

## HTTP Translation Service (New)

A minimal FastAPI service for draft translation has been added.

### What's Included

- `app/service/draft_service.py` – FastAPI app with POST `/translate/draft` endpoint
- `app/service/client.py` – HTTP client for the service (optional)
- `app/config.py` – Simple configuration for service URL
- `run_translation_service.py` – Convenience script to start the service
- `requirements.txt` – Optional dependencies (FastAPI, uvicorn, requests)
- Updated CLI with `--service-url` flag to use remote service

### How to Use

1. Install optional dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Start the translation service:
   ```bash
   python run_translation_service.py
   ```
   The service will run at `http://localhost:8000`. Health check: `GET /health`.

3. Run the CLI with service URL:
   ```bash
   python -m app.cli run --service-url http://localhost:8000
   ```
   If the service is unavailable, CLI falls back to local mock.

### Testing

- Run existing tests: `pytest app/tests/`
- New endpoint tests: `pytest app/tests/test_draft_service.py` (requires FastAPI)
- New client tests: `pytest app/tests/test_client.py` (mocked)

---

## Fishhead Wrapper Integration (2026-04-19)
- **Fishhead wrapper URL**: `http://192.168.68.51:8001/generate`
- **Model**: `qwen2.5:14b`
- **Protocol**: `POST /generate` with `{"prompt":"..."}` → `{"text":"..."}`
- **Adapter status**: existing `backend_adapter.py` works without modification

## Verified Call Path
- `app/cli.py` → service → `backend_adapter.py` → fishhead wrapper

## Validation Results
- Direct backend integration test passed
- Service endpoint test passed  
- CLI real-call-path test passed

## Next Natural Step
- Run one real chapter through the current pipeline and review output quality

## Validation Completed (2026-04-20)
- **Fishhead wrapper**: Reachable and functional at `http://192.168.68.51:8001/generate`
- **Polish second pass**: Successfully tested and producing distinct output from draft
- **Evidence**: 
  - Draft: `[DRAFT ENGLISH] Young Lady called Prince，然后离开了房间。`
  - Polished: `Young Lady called out to Prince and then left the room.`
- **Conclusion**: Both draft and polish stages are now operational with real backend processing

*Last updated: 2026-04-20*

## Reality Check: Fishhead Wrapper Unreachable (2026-04-25)

- **Attempt**: Reality Check discovery only — `chapter run` on real content (`one_chapter.txt`)
- **Blocker**: Fishhead wrapper at `http://192.168.68.51:8001/generate` is unreachable (ARP incomplete, all probes timed out)
- **Current status**: The wrapper was verified functional on 2026-04-20 but is unreachable from this Mac as of 2026-04-25. No other backend is configured (`MODEL_BACKEND_URL` not set, Ollama available but no models loaded).
- **No code changes made** during this discovery.
- **Next action**: Bring Fishhead wrapper online, then:
  ```bash
  MODEL_BACKEND_URL=http://192.168.68.51:8001/generate \
    venv/bin/python -m app.cli chapter run \
    --source one_chapter.txt \
    --output data/exports/reality_chapter.md \
    --dry-run --confirm
  ```
- **Frozen**: `chapter stream --dry-run` remains frozen per Batch 4B design freeze.

*Last updated: 2026-04-25*

## Default Workflow Implementation

Implements the contract defined in WORKFLOW.md:

- **Prompt A** (`prompts/prompt_a.md`) = draft / revision / final prose generation
- **Prompt B** (`prompts/prompt_b.md`) = internal review only
- **Default workflow** = A → B → revise once if needed → final prose
- **Reviewer scaffolding** (major_issue:, why_it_matters:, recommended_fix:, optional_notes:) is parsed internally and never exposed to user
- **Default output** = final prose only, no internal review notes
- **Loop limit** = at most one review pass, at most one revision pass

Implementation details:
- `polish_translation()` orchestrates the workflow: calls `run_internal_review_with_backend` (Prompt B), parses findings, conditionally calls `translate_polish_with_backend` (Prompt A) with extracted review guidance.
- Reviewer scaffolding is stripped via `clean_polished_output()` before returning.
- Glossary terms are applied as a safety net after each step.

Tests verify that the reviewer is never bypassed and the default output contains no reviewer scaffolding.

*Last updated: 2026-04-22*

## Draft-Path Unification (2026-04-22)

Integration milestone recording the current implementation state after prompt
and project-asset plumbing work.

### What is now true

- **On-disk prompt loading**: `prompts/prompt_a.md` and `prompts/prompt_b.md`
  are read from disk at prompt-build time via `app/translate/project_context.py`
  (`load_prompt`). `build_draft_prompt` and `build_polish_prompt` no longer
  inline their instruction blocks.
- **On-disk project-asset loading**: The five governed assets
  (`characters`, `titles_and_terms`, `glossary`, `style_notes`,
  `unresolved_decisions`) are read from `project_assets/` via
  `load_asset` / `load_all_assets`. The loader tolerates the ordered-prefix
  filenames currently on disk (e.g. `1. glossary.md`).
- **Asset injection into prompts**: `build_project_assets_block` renders
  non-empty assets into a single labeled "Project memory" block that is
  injected into both the draft and polish prompts.
- **Internal `assets_mode` control**: Prompt builders and the translator-layer
  entry points accept an internal `assets_mode` parameter with values
  `"full"` (default, inject all non-empty assets) and `"none"` (skip asset
  injection). Unknown values raise `ValueError`.
- **Unified draft prompt across paths**: Both the local pipeline path
  (`app.translate.translator.translate_draft`) and the service/backend path
  (`app.translate.backend_adapter.translate_draft_with_backend` →
  `POST /translate/draft`) build their draft prompt via the same
  `translator.build_draft_prompt`, so prompt-file content, project-asset
  injection, glossary handling, and output cleaning are consistent regardless
  of caller.
- **Unchanged public HTTP surface**: `POST /translate/draft` request and
  response shapes are unchanged. No new fields, no new endpoints.

### What remains internal-only

- `assets_mode` is a Python-level parameter only. It is not exposed through
  any CLI flag or HTTP request field; callers that want to override it do so
  internally by passing the argument directly.
- The project-assets block is assembled and injected entirely inside the
  prompt builders; service and CLI callers do not pass asset content in.

### What is still not exposed publicly

- No CLI flag controls `assets_mode` or prompt/asset selection.
- No HTTP parameter controls `assets_mode` or prompt/asset selection.
- Polish translation is **not** exposed through the HTTP service. Only
  `POST /translate/draft` exists; polish currently runs only via the local
  pipeline path (`polish_translation` → `translate_polish_with_backend`).

### Next natural step (Phase B+)

Expose polish through the HTTP service (a `POST /translate/polish` endpoint
that mirrors the draft endpoint's shape and uses `translate_polish_with_backend`),
so the service surface matches the local pipeline's two-stage behavior. This
is Phase B+ scope; not part of the sealed Phase A contract.

## Batch 4B: Strategy Enactment Minimal Closed Loop (2026-04-23)

Completes the minimal closed loop from strategy decisions → orchestrator → downstream → enactment record.

### What is now true

- **Strategy enactment helpers** (`_resolve_budget_from_plan`, `_resolve_consistency_intensity_from_plan`, `_build_enactment`) are in place and tested.
- **Budget configuration** resolved from plan's strategy_plan is passed to `translate_draft` and `polish_translation`.
- **Consistency intensity** resolved from plan's strategy_plan is passed to the consistency pass.
- **Enactment record** is built in both `execute()` and `run_with_manifest()` and attached to `ChapterResult.enactment`.
- **Conservative recording**: enacted segmentation granularity is `None` (actual granularity not tracked), `consistent` field is `None`, unknown fields remain `None`.
- **All existing tests pass** (37 chapter tests), no missing helper or signature errors.

### Implementation details

- `orchestrator.py` lines 261 and 453: `_build_enactment` called with resolved `consistency_intensity`, `segment_count`, and `segmentation_granularity=None`.
- `ChapterResult` model already had `enactment` field defined (Batch 4A).
- No refactoring, no scope expansion, no new validation scripts, no guessing of unknown values.

### What remains internal-only

- Enactment record is attached to result but not yet used for any downstream decision or reporting.
- `consistent` field is `None` (cannot be determined without more context).
- Actual segmentation granularity not tracked (enacted.segmentation.granularity = None).

### Next natural step

Use the enactment record to drive post‑run reporting or adaptive behavior in later batches (out of scope for this minimal loop).

## Batch status summary

**Batch 4B completed (2026-04-23):** Strategy enactment minimal closed loop. All existing chapter-level tests pass (37 tests). Enactment record is attached to `ChapterResult`.

**Batch 5A completed (2026-04-26):** chapter Markdown output format contract sealed. Squash-merged into `main` as `9e74299 Seal chapter output format contract`. Test suite: 312 passed.

**Batch 5B (scope-alignment, no code change):** scope check found chapter-level CLI integration was already shipped by earlier batches (`chapter run`, `chapter stream`, dry-run, confirm, resume, no-clobber, manifest/resume preservation, ~46 CLI tests). No new CLI feature was added; stale next-batch pointers were corrected instead.

**Batch 5C completed (2026-04-26):** minimal chapter-level HTTP/API integration. `POST /translate/chapter` endpoint exposes `ChapterOrchestrator.run_with_manifest()` with full manifest/resume semantics, consistency audit, strategy summary, and readable output. 26 endpoint tests (all mocked, no real-model execution). Test suite: 321 passed.

**Phase B+ operator usability (PR #9, PR #10, 2026-04-26):**

Two changes to eliminate operator footguns in daily use:

- **Default output derivation (#9):** Both `run` and `chapter run` now derive `--output` from `--source` when omitted (e.g. `data/source/chapter3.txt` → `data/exports/chapter3_en.md`), instead of always defaulting to `chapter1_en.md`. Prevents silent overwrites. 10 new tests. Commit `9369504`.
- **`chapter batch` command (#10):** `python -m app.cli chapter batch --source path1 --source path2` runs chapter-level translation on multiple source files in one invocation. Each source gets a safe default output via the same derivation helper. Failure isolation — one failed chapter does not block the rest. Compact per-chapter summary after completion. KeyboardInterrupt/Ctrl+C propagates naturally. 8 dedicated batch tests. Commit `6e6c605`.

Test suite: 592 passed (74 CLI + 39 chapter + 36 retrieval + 26 service + others).

**Next batch:** Phase B — quality loop. No further Phase A or Phase B+ operator-usability work.

## Tech Debt

### Exports directory clutter
`data/exports/` has accumulated many one-off experiment files across quality validation runs. Generated exports are gitignored but the directory is noisy. A cleanup policy (auto-clean files older than 15 days, or archive to a dated subfolder) should be implemented before exports become unmanageable. Adding to `project_assets/`, `outputs/`, and `data/outputs/` should also be considered in the same policy since those directories have similar accumulation. (ref: 2026-04-30 self-audit, DeepSeek profile validation run)