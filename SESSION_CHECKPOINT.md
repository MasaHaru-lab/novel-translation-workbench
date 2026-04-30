# Session Checkpoint — 2026-05-01 (R4: BookMemory ContextPack CLI Activation)

## Current focus
**R4 is merged to `main` at `393d6d2`.** This checkpoint records the post-R4 state. No new work has started.

## What shipped in this batch

### R3: ContextPack pipeline wiring (2026-05-01)
- `TranslationInput.context_pack_text` field on schema
- All three prompt builders (draft, review, polish) inject context pack after project assets, before glossary terms
- `ChapterOrchestrator.execute()` and `run_with_manifest()` accept `Optional[BookMemory]`
- `_execute_segment_with_retry()` threads context pack text through retry/resume path
- 18 new wiring tests

### R4: CLI activation (2026-05-01)
- `--book-memory PATH` flag on `chapter run/stream/batch`
- `load_book_memory()` helper in `cli.py`
- BookMemory forwarded through resume/manifest paths
- Observability logging: context pack activation status, size, truncation
- 6 new CLI wiring tests

## Current state

- **HEAD**: `393d6d2` on `main`
- **Test count**: 616 passing (0 regressions)
- **Working tree**: clean

## BookMemory support matrix

| Command | `--book-memory` |
|---|---|
| `chapter run` | ✓ (fresh, resume, dry-run) |
| `chapter stream` | ✓ |
| `chapter batch` | ✓ |
| legacy `run` | ✗ |

## Closed loop (active)
BookMemory store → `build_context_pack()` → `format_text()` → per-segment Prompt A/B injection → chapter CLI activation (`--book-memory`).

## Remaining risks (no new work started)

1. **No automatic population** — entities, relationships, and chapter events must be manually added or extracted.
2. **No retention policy** — JSON grows with book size; no compaction or archiving.
3. **No cross-book support** — one book per JSON file.
4. **No migration strategy** — `BookMemory.version` field exists but no migration logic.
5. **No pre-merge gate check** for book memory JSON validity.
6. **Legacy `run`** does not support `--book-memory`; use chapter subcommands instead.
