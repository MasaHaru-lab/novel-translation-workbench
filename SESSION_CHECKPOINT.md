# Session Checkpoint – 2026-04-24

## Current focus
Phase A (`chapter run` CLI friction reduction) is complete. No active batch.

## Confirmed done

- **Elapsed-time reporting** (`19ae52b`)
  - `time.monotonic()` wraps both fresh-run and resume orchestrator paths
  - Output: `Elapsed: 12.3s` line before `Done.` in final summary
  - 3 new tests (fresh, formatting, resume path), all passing

- **`--no-clobber` output protection** (`a6d2a79`)
  - Flag on `chapter run` subparser only
  - Check fires before any orchestrator execution (before dry-run, resume, or fresh-run paths)
  - Error output:
    ```
      Error: Output file already exists: <path>
      Use --no-clobber to protect existing output. Remove the file or omit --no-clobber to overwrite.
    ```
  - Exits with code 1, orchestrator never instantiated
  - 3 new tests (exists+exit, absent+proceed, default+overwrite), all passing

- **CLI friction batch: `--no-clobber` msg + resume progress + `--confirm`** (`3f444d0`)
  - Fixed `--no-clobber` self-referential error message ("Remove the file or use a different --output path.")
  - Extracted `_orchestrator_progress_logging()` context manager, used in both fresh-run and resume paths
  - Added `--confirm` flag with interactive prompt after plan preview
  - 4 new tests (confirm yes/no, dry-run+confirm yes/no), 56 CLI tests total

## Still pending / blocked / broken

- **Env var fallback for source/output defaults** — deferred by user. Opens a broader config-surface question (env var names, chapter/stream/legacy consistency, future config-file interaction). Not the right next batch.
- **Stream mode isolation** — already done in an earlier batch, not touched in these two batches.
- **`chapter stream` lacks `--dry-run`** — FROZEN. stdout/stderr contract ambiguity: stream reserves stdout for output, dry-run would require an explicit interface decision. Removed from Phase A scope. Only reopen if user explicitly says so.
- **`chapter run` other candidates** — none identified in this session.
- **Unaddressed larger items** (Phase B/C/D): HTTP polish endpoint, batch processing, real translation models, sentence-level splitting, config file.

## Next starting action

Next batch candidates (user to decide direction):
- Phase B: HTTP polish endpoint
- Phase C: batch processing / config file

## Key artifacts
- `app/cli.py` — `_orchestrator_progress_logging()` (context manager, before `read_source_file`), `run_chapter_pipeline` (--confirm at line ~260, --no-clobber at line ~247), `chapter run` parser (--confirm flag at line ~605)
- `app/tests/test_cli.py` — confirm tests (lines ~416-455), mock function (line ~262)

## Validation status
- Tests/checks run: yes (full suite 276 passed, 56 CLI)
- Repo/worktree relevant: yes
- Worktree clean: yes
- Confidence: high
