# CLI Backbone Audit

Audit date: 2026-05-02
Branch: `work/pipeline-contracts-doc`
Scope: CLI entrypoints, argument contracts, output/stream/manifest/quality-reporting contracts.
No runtime code changed.

---

## 1. Entrypoint topology

Single module: `app/cli.py` (48 KB, 1038 lines), argparse-based, no Click.

### Top-level commands

| Command | Dispatch | Phase | Status |
|---|---|---|---|
| `run` | `main()` → `run_pipeline()` | Pre-chapter | Stable |
| `chapter run` | `main()` → `run_chapter_pipeline()` | Phase A | Stable |
| `chapter stream` | `main()` → `run_chapter_stream()` | Phase A | Stable |
| `chapter batch` | `main()` → `run_chapter_batch()` | Phase A | Stable |
| `check` | `main()` → `scan_workspace().print_report()` | New (this branch) | Stable |

### Invocation pattern

```
venv/bin/python -m app.cli <command> [options]
```

No top-level subcommand grouping beyond `chapter` — `run` is a flat sibling of `chapter run`.

---

## 2. Argument contracts per command

### `run` (pre-chapter pipeline)

| Argument | Type | Default | Notes |
|---|---|---|---|
| `--source` | Path | `data/source/one_chapter_quality_source.txt` | Unchanged from early dev |
| `--output` | Path | derived from `--source` | See §3 |
| `--service-url` | str | None | If provided, try HTTP client |
| `--allow-mock-fallback` | flag | False | When service fails, drop to local mock |
| `--assets-mode` | str | `"full"` | `full` / `none` |
| `--model-profile` | str | None | Overrides `--service-url` and `MODEL_BACKEND_URL` |

**Important:** `run` is the *pre-chapter* pipeline. It segments + translates inline within `cli.py` itself, not via `ChapterOrchestrator`. It does NOT support `--resume`, `--dry-run`, `--smoke-test`, `--book-memory`, or the batch 2/3/4 features. This command will likely be subsumed by `chapter run` in the future.

### `chapter run`

| Argument | Type | Default | Notes |
|---|---|---|---|
| `--source` | Path | `data/source/one_chapter_quality_source.txt` | Same default as `run` |
| `--output` | Path | derived from `--source` | See §3 |
| `--service-url` | str | None | HTTP service client |
| `--allow-mock-fallback` | flag | False | Fallback to local mock |
| `--assets-mode` | str | `"full"` | Full / none |
| `--model-profile` | str | None | Overrides service-url and env var |
| `--resume` / `--dry-run` | flag | mutually exclusive | See §4 |
| `--max-retries` | int | 2 | Per-segment retry cap |
| `--retry-delay-seconds` | float | 1.0 | Base delay between retries |
| `--no-auto-retry-on-resume` | flag | False (auto-retry on) | Disable retry of failed segments on resume |
| `--no-clobber` | flag | False | Error if output exists |
| `--confirm` | flag | False | Show plan + prompt before execution |
| `--book-memory` | Path | None | Context pack injection (R3/R4) |
| `--smoke-test` | flag | False | Mock translation, skip quality |

**Resume/dry-run exclusivity** enforced at the argparse level via `add_mutually_exclusive_group()`. Good.

### `chapter stream`

| Argument | Type | Default | Notes |
|---|---|---|---|
| `--source` | Path | None (stdin) | Optional; omit to pipe via stdin |
| `--service-url` | str | None | |
| `--allow-mock-fallback` | flag | False | |
| `--assets-mode` | str | `"full"` | |
| `--model-profile` | str | None | |
| `--book-memory` | Path | None | |
| `--smoke-test` | flag | False | |

**Stdout/stderr contract:** final translation text goes to `sys.stdout`; all errors, diagnostics, and progress output go to `sys.stderr`. No manifest is written (manifest_path=None). This is the only command without a persistent output file.

### `chapter batch`

| Argument | Type | Default | Notes |
|---|---|---|---|
| `--source` | Path, `append` | required | Repeatable, at least one |
| `--service-url` | str | None | |
| `--allow-mock-fallback` | flag | False | |
| `--assets-mode` | str | `"full"` | |
| `--model-profile` | str | None | |
| `--resume` | flag | False | Per-chapter resume |
| `--no-clobber` | flag | False | Skip chapters with existing output |
| `--book-memory` | Path | None | |
| `--smoke-test` | flag | False | |

**Batch does NOT support** `--dry-run`, `--confirm`, `--max-retries`, or `--retry-delay-seconds`. It delegates to `run_chapter_pipeline()` for each source.

### `check` (workspace hygiene)

| Argument | Type | Default | Notes |
|---|---|---|---|
| `--project-root` | Path | None (auto-detect) | |

Implemented in `app/hygiene/reporter.py`. Reports dirty/untracked/generated file classifications. Not a test, not a gate — informational only.

---

## 3. Output path convention

`_derive_output_path(source: Path) -> Path` at line 52:

```
data/source/chapter3.txt  →  data/exports/chapter3_en.md
data/source/ch1131_v1.txt →  data/exports/ch1131_v1_en.md
```

Key contract: the output stem is `{source.stem}_en.md`, always under `data/exports/`.

The output directory is created on demand (`mkdir(parents=True, exist_ok=True)`) before writing. The output file is plain UTF-8 Markdown with no wrapper structure. No line-length guarantee, no metadata header, no YAML frontmatter in the output file.

**Output only written when** the chapter result has at least one completed segment (`is_complete` or `is_partial`) and `final_translation` is non-empty.

---

## 4. Manifest contract

Manifest path derived from output path:

```python
RunManifest.default_manifest_path(str(output_path))
# → output_path.with_suffix(".manifest.json")
```

So `data/exports/chapter3_en.md` → manifest at `data/exports/chapter3_en.manifest.json`.

### RunManifest structure (app/chapter/manifest.py)

| Field | Type | Notes |
|---|---|---|
| `run_id` | str | uuid4 hex[:12] |
| `chapter_title` | str | |
| `source_text_hash` | str | sha256 hex digest of full source |
| `total_segments` | int | |
| `status` | ChapterStatus enum | pending/running/partial/completed/failed |
| `segments` | dict[str, SegmentRecord] | keyed by segment_id |
| `resume_config` | ResumeConfig | max_retries, retry_delay_seconds, auto_retry_on_resume |
| `started_at` | float (epoch) | |
| `completed_at` | float (epoch) | |
| `manifest_path` | str (optional) | |
| `quality_summary` | dict (optional) | Persisted quality gate result (passed/errors/warnings) |
| `smoke_test` | bool | |

### SegmentRecord

| Field | Type | Notes |
|---|---|---|
| `segment_id` | str | |
| `status` | SegmentStatus | pending/running/completed/failed |
| `retry_count` | int | |
| `error_message` | str | |
| `polished_text` | str | **Persisted so resume can reconstruct TranslationOutput** |
| `started_at` | float | epoch |
| `completed_at` | float | epoch |
| `duration_seconds` | float | |

### Resume semantics

- Manifest saved to disk after **each segment** completes
- On `--resume`:
  1. Load manifest from `<output>.manifest.json`
  2. Show summary (completed/failed/pending, run_id, status)
  3. Completed segments are **reused** (their `polished_text` is read from the manifest)
  4. Pending segments are translated fresh
  5. Failed segments are retried (up to `max_retries`, unless `--no-auto-retry-on-resume`)
  6. If manifest fails to load or is not resumable, falls back to **fresh run** (prints notice, does not exit with error)
- If the chapter is already `COMPLETED`, resume is a no-op (not resumable)

---

## 5. Quality reporting contract

`_report_chapter_result()` at line 521 displays to stdout:

### Smoke-test mode

- Banner: `"■■■  SMOKE TEST MODE ■■■"`
- Quality: `"SKIPPED (smoke test)"`
- Consistency: `"SKIPPED (smoke test)"`
- Output labeled "not a real translation"

### Normal mode

- `ChapterResult.chapter_status.value` — one of `completed`/`partial`/`failed`
- Completed/failed segment counts
- **Quality gate** (from `result.quality_report`):
  - `"passed"` — clean pass (zero errors, zero warnings)
  - `"passed (N warning(s))"` — pass with warnings
  - `"FAILED — N error(s) [code1, code2]""` — fail with error codes
  - Error details printed per issue (code, segment_id, message)
- **Consistency audit** (from `result.consistency_audit`):
  - `"no issues found"` / `"all resolved (N issue(s) auto-fixed)"` / `"N issues (M auto-fixed)"` / `"N issues found"`
  - Category breakdown when issues exist
- **Correction summary** (from `result.correction_summary`): counts by category
- **Strategy summary** (from `result.strategy_plan_summary`):
  - Complexity level + score, processing mode
  - Segmentation granularity, segment count, budget profile
  - Consistency intensity
- **Elapsed time** in seconds
- Output path + labels (post-consistency, partial, or smoke test)
- Manifest path + resume guidance (when partial/resumable)

---

## 6. Translation function resolution

`_resolve_translate_fn()` at line 251 implements a three-tier fallback:

1. **Model profile** (`--model-profile`): highest priority. Uses `translate_draft_with_profile()` from `app.translate.model_profiles`. Errors on unknown profile name with available list.
2. **HTTP service** (`--service-url`): creates `TranslationServiceClient(base_url=...)` and uses `client.translate_draft`. If import fails and mock fallback is allowed, falls through.
3. **Local mock** (`config.MODEL_BACKEND_URL` or hardcoded local): uses `translate_draft()` from `app.translate.translator`.

The resolved function is passed to `ChapterOrchestrator.run_with_manifest()` and `orchestrator.resume()` as `translate_draft_fn`.

---

## 7. Orchestrator integration points

The CLI calls `ChapterOrchestrator` in these modes:

| Method | Used by | Manifest? | Notes |
|---|---|---|---|
| `orchestrator.plan(text)` | `--dry-run` / `--confirm` | No | Preview only, no execution |
| `orchestrator.run_with_manifest(...)` | `chapter run` (fresh), `chapter stream` | Yes (except stream) | Fresh execution |
| `orchestrator.resume(...)` | `chapter run --resume` | Yes | Load manifest, continue |
| `orchestrator.load_manifest(path)` | `chapter run --resume` (pre-check) | — | Load + validate manifest |

The CLI only passes `ChapterOrchestrator` the translate function, assets mode, resume config, smoke flag, optional profile object, and optional book memory. All segment-level orchestration, quality gating, consistency checks, and output aggregation live in the orchestrator — not the CLI.

---

## 8. Batch run contract

`run_chapter_batch()` at line 752:

- Processes sources **sequentially** (single-threaded, blocking)
- Each source delegates to `run_chapter_pipeline()` with its derived output path
- One failed chapter does **not** stop subsequent chapters (exception caught per iteration)
- Produces a batch summary table at the end: source name / status / error
- Batch summary shows completed/failed counts

Failure detection: checks whether the output file exists after `run_chapter_pipeline()` returns. This is a heuristic — the pipeline function can return without SystemExit but still produce no output (e.g. model backend unavailable).

No `--dry-run` at the batch level. No parallelism. No concurrency.

---

## 9. Fragile contracts future work must preserve

These are the implicit and explicit interfaces that, if broken, would silently break something downstream (CLI consumers, orchestration, monitoring, or developers expecting consistent behavior).

### 9.1 Output path derivation (FRAGILE)

```
_source_stem_ + "_en.md" under data/exports/
```

**Why fragile:** This is a simple string derivation with no config file, no override mechanism (beyond explicit `--output`), and no versioning. Any code that assumes a specific output path will break if this logic changes.

**Preserve:** If the derivation rule changes, all callers that compute output paths independently must be updated in sync.

### 9.2 Manifest path convention (FRAGILE)

```
<output_path>.with_suffix(".manifest.json")
```

**Why fragile:** Callers that compute the manifest path from the output path use this convention. If the convention changes, resume breaks silently (old manifests are not found).

**Preserve:** Keep `RunManifest.default_manifest_path()` as the single source of truth for this mapping.

### 9.3 Manifest polished_text persistence (FRAGILE)

SegmentRecord.polished_text preserves the raw polished translation text.

**Why fragile:** Resume depends on this field to reconstruct TranslationOutput without re-translating. If the field is renamed, omitted on serialization, or truncated, resume will produce empty or broken output.

**Preserve:** polished_text must always be written, always be serialized, and always be sufficient to reconstruct the segment output.

### 9.4 Stdout/stderr contract for `chapter stream` (FRAGILE)

- stdout: final translation text ONLY
- stderr: errors and diagnostics

**Why fragile:** Any caller piping `chapter stream` output into another tool depends on this separation. Adding progress output to stdout would corrupt the pipe target.

**Preserve:** Never mix translation output with diagnostics on stdout in stream mode.

### 9.5 Manifest persistence after each segment (FRAGILE)

The orchestrator saves the manifest to disk after each segment completes.

**Why fragile:** Resume correctness depends on the invariant that a killed process never loses more than one segment of work. If the save frequency changes (e.g., batch-at-end), resume becomes unreliable.

**Preserve:** Save-after-each-segment. Do not batch-save.

### 9.6 `--resume` fallback behavior (FRAGILE)

When a resume fails or the manifest is unreadable, the CLI silently falls back to a fresh run (with a notice).

**Why fragile:** Downstream automation that expects resume-or-fail semantics would silently get a fresh run, re-translating already-done segments and potentially doubling token cost.

**Preserve:** This is the current behavior. Any future change should be opt-in (e.g., `--resume=strict`).

### 9.7 ChapterResult output fields (FRAGILE)

The CLI's `_report_chapter_result()` reads `result.final_translation` for output. Prefers `result.corrected_translation` when available (post-consistency).

**Why fragile:** If the orchestrator renames or restructures these fields, the CLI writes the wrong text or writes nothing.

**Preserve:** The CLI reads `final_translation` and checks `corrected_translation`. Keep these field names stable, or update the CLI in the same change.

### 9.8 `run` command's divergence from `chapter run` (FRAGILE)

The `run` command uses `translate_draft` + `polish_translation` inline with `create_segments`. It does NOT use `ChapterOrchestrator`.

**Why fragile:** Any change to the orchestrator's segment-level workflow (e.g., new prompt steps, new intermediate formats) will NOT be reflected in the `run` command. The two commands must be kept consistent manually, or `run` must be retired.

**Preserve:** When adding orchestrator features, either update `run` in parallel or deprecate it explicitly to avoid a silent quality gap.

### 9.9 Quality gate contract (FRAGILE)

`_report_chapter_result()` accesses `result.quality_report` as an object with `.passed`, `.error_count`, `.warning_count`, `.issues`, `.codes()`.

**Why fragile:** The quality report type is typed as `Optional[object]` in `ChapterResult` to avoid a forward-import cycle. There is no static type guard. If the quality module changes its result shape, `_report_chapter_result()` may access nonexistent attributes at runtime.

**Preserve:** Either add a proper type reference, or keep the quality report interface stable.

### 9.10 Batch failure detection heuristic (FRAGILE)

`run_chapter_batch()` uses `output.exists()` to determine success.

**Why fragile:** A chapter that completes with zero segments of output (all segments failed) produces no file. The batch code correctly marks it FAILED. But a chapter that produces output but has issues (quality failures, partial results) cannot be distinguished from a clean pass by file-existence alone.

**Preserve:** For accurate batch success determination, use the manifest or ChapterResult fields rather than file-existence heuristic.

### 9.11 `set_smoke_mode()` global state (FRAGILE)

`set_smoke_mode(smoke_test)` at line 397 sets a module-level flag in `app.translate.translator`.

**Why fragile:** This is process-global mutable state. If the CLI ever supports concurrent chapter runs (e.g., batch parallelism), this flag will race. It only works because the current batch is sequential.

**Preserve:** If parallelism is added, thread/process-local smoke mode must replace the global flag.

### 9.12 BookMemory context pack contract (FRAGILE)

When `--book-memory` is provided, the CLI loads a `BookMemory` JSON file and passes the object to the orchestrator.

**Why fragile:** The JSON schema (`book_memory_from_dict` / `book_memory_to_dict`) is defined in `app.book_memory.serialization`. If the schema changes, existing JSON files become unreadable and resume with a prior manifest's book memory context could produce inconsistent context packs.

**Preserve:** Keep the serialization schema backward-compatible, or add a migration path for old JSON files.

---

## 10. Smoke-test mode behavior

`set_smoke_mode(True)` → deterministic mock translation in `app.translate.translator`.

CLI effects:
- Quality gate: `_report_chapter_result()` prints `"SKIPPED (smoke test)"`
- Consistency pass: `"SKIPPED (smoke test)"`
- Output banner: `"■■■  SMOKE TEST MODE ■■■"`
- Output file: labeled as smoke test
- All orchestrator quality checks disabled (orchestrator responsibility)

The smoke-test flag is persisted in `RunManifest.smoke_test` so a resumed run's smoke-test status is preserved across restarts.

---

## 11. Translation function resolution: three-tier fallback

```
_model_profile_  →  translate_draft_with_profile()  [from app.translate.model_profiles]
_service_url_    →  TranslationServiceClient(base_url).translate_draft  [HTTP]
_neither_        →  translate_draft()  [local mock / configured MODEL_BACKEND_URL]
```

`_resolve_translate_fn()` returns `(Callable | None, mode_label)`. The CLI exits on `(None, "error")`.

Only `model_profile` supports the optional profile object (`profile_obj`) passed to the orchestrator for review/polish orchestration. The HTTP service path does not support `profile_obj`.

---

## 12. Verification status

- **Tests run:** Not applicable (audit-only batch, no code changes)
- **Pre-merge gate:** Not applicable
- **Working tree:** Dirty (new docs/CLI_BACKBONE_AUDIT.md + hygiene module is untracked)
- **Runtime behavior changed:** NO
