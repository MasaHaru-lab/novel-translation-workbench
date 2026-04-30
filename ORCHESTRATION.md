# Chapter-level Orchestrator Kernel

## Purpose

The chapter-level orchestrator (`app/chapter/orchestrator.py`) is the main internal orchestration path for translating full Chinese novel chapters into English.

It takes a full chapter as input, runs the segment-level translation workflow over each segment, aggregates the results, and returns a complete English chapter output.

**Product direction:** chapter-level orchestration, not manual segment-by-segment operation.

## Relationship to WORKFLOW.md

The orchestrator invokes the segment-level workflow defined in `WORKFLOW.md` for each segment:

- Prompt A draft generation
- Prompt B internal review  
- one revision pass if needed

`WORKFLOW.md` remains the segment-level execution protocol; the orchestrator is the chapter-level caller.

## Current capabilities (Batch 4B completed)

### 1. Planning phase
- Segment full chapter text into executable units (~800-1200 characters)
- Pre-execution strategy assessment (chapter complexity, segment risks)
- Strategy decisions: processing mode, budget profile, consistency intensity, segmentation granularity
- Granularity decision applied: "standard" (1200/800) vs "finer" (800/500) segmentation

### 2. Execution phase  
- Reuses existing segment-level translation functions (`translate_draft`, `polish_translation`)
- Each segment goes through the default workflow (draft → review → polish)
- Budget configuration resolved from strategy plan and passed to translation functions
- Assets mode control (full/none) for project-asset injection

### 3. Aggregation phase
- Concatenates segment polished translations into flowing full chapter
- Chapter title becomes top-level heading
- Segments separated by blank lines for readability

### 4. Consistency pass (limited)
- Basic consistency audit after aggregation
- Conservative correction pass for term unification
- Reference built from project assets and segment results

### 5. Manifest/resume support (basic)
- `RunManifest`-based execution with persistent progress tracking
- Segment-level failure isolation (one failure does not abort the chapter)
- Resume capability for interrupted runs
- Conservative retry/discipline (bounded, no infinite loops)
- When running via CLI (`chapter run`), the manifest is written alongside the output file as `<output>.manifest.json`. Pass `--resume` to continue a partial or interrupted run.

### 6. Strategy enactment minimal closed loop
- Budget configuration resolved from plan's strategy_plan
- Consistency intensity resolved from plan's strategy_plan  
- Enactment record built and attached to `ChapterResult`
- Conservative recording: actual segmentation granularity not tracked, `consistent` field is `None`

## Implementation notes

**Main entry points:**
- `ChapterOrchestrator.run()` – simple plan→execute→aggregate path
- `ChapterOrchestrator.run_with_manifest()` – resilient execution with progress persistence

**Segment-level engine reuse:**
- Uses existing `app/segment/segmenter` for segmentation
- Uses existing `app/translate/translator` for translation
- Uses existing `app/translate/backend_adapter` for backend integration
- No reimplementation of segment-level logic

**Internal-only parameters:**
- `assets_mode` – Python-level parameter only, not exposed via CLI/HTTP
- `budget_config` – resolved from strategy plan, not user-configurable
- `consistency_intensity` – resolved from strategy plan, not user-configurable

## Batch status

**Batch 4B completed (2026-04-23):** Strategy enactment minimal closed loop. All existing chapter-level tests pass (37 tests). Enactment record is attached to `ChapterResult`.

**Batch 5A completed (2026-04-26):** chapter Markdown output format contract sealed (commit `9e74299`).

**Batch 5B (scope-alignment, no code change):** scope check confirmed chapter-level CLI integration is already shipped (`chapter run`, `chapter stream`, dry-run, confirm, resume, no-clobber).

**Batch 5C completed (2026-04-26):** minimal chapter-level HTTP/API integration. `POST /translate/chapter` endpoint exposes `ChapterOrchestrator.run_with_manifest()` with full manifest/resume semantics, consistency audit, strategy summary, and readable output. 26 endpoint tests (all mocked, no real-model execution).

**Phase A sealed (2026-04-26):** All Phase A surfaces frozen. No further CLI/HTTP/integration work in scope.

**R3: ContextPack pipeline wiring (2026-05-01):** `build_context_pack()` output injected into per-segment Prompt A/B via `TranslationInput.context_pack_text`. `execute()`, `run()`, and `run_with_manifest()` accept `Optional[BookMemory]`. 18 new wiring tests.

**R4: BookMemory CLI activation (2026-05-01):** `--book-memory PATH` flag on chapter subcommands. BookMemory forwarded through resume/manifest paths. Observability logging. 6 new wiring tests. 616 total tests.

## Limitations

- HTTP entry point exists (`POST /translate/chapter`) but still requires the service to be running separately
- No user control over strategy parameters
- No parallel execution
- No mature resilience features beyond basic manifest/resume
- No automatic fallback design
- Consistency pass is limited and conservative
- Enactment record not yet used for downstream decisions

## Design principles

1. **Reuse, don't rebuild** – orchestrator calls existing segment-level functions
2. **Conservative recording** – don't guess unknown values, use `None` for uncertain fields  
3. **Bounded execution** – no infinite loops, bounded retries
4. **Failure isolation** – segment failures don't abort entire chapter
5. **Progress persistence** – interrupted runs can resume from saved state