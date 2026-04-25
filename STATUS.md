# Status: Phase A — Chapter-Level CLI

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

### Next phase: Quality Loop

Run/inspect real translated output and feed recurring issues back into `zh_to_en` style rules, roles, or book assets. No further architecture redesign.

---


## Current Capabilities

- ✅ **Chapter-level CLI** (`chapter run`, `chapter stream`, `chapter run --dry-run`, `chapter run --resume`)
  - Per-segment progress logging during fresh-run execution
  - Plan preview with segment count, complexity, budget, consistency intensity
  - Manifest-based resume with failure isolation, retry, and guidance
- ✅ **Chapter orchestration** (plan → execute → aggregate → consistency pass)
  - Chapter plan generation with pre-execution strategy assessment
  - Segment-level execution via existing translation engine
  - Strategy enactment closed loop (budget/consistency resolved from plan, record attached to `ChapterResult`)
- ✅ **Consistency audit** (term unification, limited automated correction)
- ✅ **Advanced CLI output** — strategy overview, consistency summary, resume guidance
- ✅ **266 tests passing** (46 CLI + 37 chapter + others)

## What's Still Missing

- Real translation models (currently mocked for tests)
- Sentence‑level splitting for long paragraphs (splits by character boundary)
- Configuration file for segment size, model paths
- Batch processing of multiple chapters
- HTTP polish endpoint (`POST /translate/polish`)

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

# Legacy segment-level pipeline
python -m app.cli run
```

## Test Instructions

```bash
python -m pytest app/tests/
```

All 266 tests should pass (46 CLI + 37 chapter + others).

## Next Immediate Steps

1. Operator-facing improvements to the chapter-level CLI (currently: plan preview, dry-run, per-segment progress, resume).

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
- **Fishhead wrapper URL**: `http://192.168.68.61:8001/generate`
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
- **Fishhead wrapper**: Reachable and functional at `http://192.168.68.61:8001/generate`
- **Polish second pass**: Successfully tested and producing distinct output from draft
- **Evidence**: 
  - Draft: `[DRAFT ENGLISH] Young Lady called Prince，然后离开了房间。`
  - Polished: `Young Lady called out to Prince and then left the room.`
- **Conclusion**: Both draft and polish stages are now operational with real backend processing

*Last updated: 2026-04-20*

## Reality Check: Fishhead Wrapper Unreachable (2026-04-25)

- **Attempt**: Reality Check discovery only — `chapter run` on real content (`one_chapter.txt`)
- **Blocker**: Fishhead wrapper at `http://192.168.68.61:8001/generate` is unreachable (ARP incomplete, all probes timed out)
- **Current status**: The wrapper was verified functional on 2026-04-20 but is unreachable from this Mac as of 2026-04-25. No other backend is configured (`MODEL_BACKEND_URL` not set, Ollama available but no models loaded).
- **No code changes made** during this discovery.
- **Next action**: Bring Fishhead wrapper online, then:
  ```bash
  MODEL_BACKEND_URL=http://192.168.68.61:8001/generate \
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

### Next natural step

Expose polish through the HTTP service (a `POST /translate/polish` endpoint
that mirrors the draft endpoint's shape and uses `translate_polish_with_backend`),
so the service surface matches the local pipeline's two-stage behavior. This
is intentionally out of scope for this batch.

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

**Next batch (Batch 5):** chapter-level CLI/HTTP integration — expose the orchestrator as the main user entry point, keeping segment-level workflow as the execution layer.

**Current focus:** improve the chapter-level path within Phase A only. Do not expand into Phase B/C/D yet.