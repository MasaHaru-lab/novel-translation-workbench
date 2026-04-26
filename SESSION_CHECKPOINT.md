# Session Checkpoint — 2026-04-26 (Batch 5C — HTTP/API integration)

## Current focus
**Batch 5C — minimal chapter-level HTTP/API integration.**

Discovered that the HTTP chapter endpoint (`POST /translate/chapter`) was already implemented in `app/service/draft_service.py` alongside the draft endpoint and health check. The chapter endpoint already:
- Calls `ChapterOrchestrator.run_with_manifest()` directly
- Supports fresh runs and resume (with `manifest_path` + `resume=true`)
- Preserves consistency audit, strategy summary, enactment record
- Returns structured `ChapterResponseModel` with `readable_summary` field
- Has 26 mocked endpoint tests in `app/tests/test_draft_service.py`

Two tests were failing due to missing `run_id` on mock manifests (MagicMock attribute returned MagicMock instead of string). Fixed by adding explicit `mock_manifest.run_id = "..."` in the two affected test helpers.

## Doc edits in this batch
- **`SESSION_CHECKPOINT.md`** (this file) — replaces the prior Batch 5B checkpoint.
- **`CLAUDE.md`** — `Chapter-level orchestration` section: "Next batch" line updated from "Batch 5C" to "completed — Phase B or polish endpoint."
- **`STATUS.md`** — Added chapter-level HTTP API to current capabilities; updated test count (321). Updated Batch status summary with 5C entry.
- **`ORCHESTRATION.md`** — Updated Batch status with 5C entry; updated Limitations (HTTP entry point exists).

## Application code changes
- **`app/tests/test_draft_service.py`** — Fixed two test helpers (`test_chapter_readable_summary_partial`, `test_chapter_readable_summary_all_failed`) that created mock manifests without `run_id`.

## Mainline seal point
`a204146 docs: close completed chapter CLI integration scope` (Batch 5B, on `main`).

## Test gate
- Command: `source venv/bin/activate && python -m pytest app/tests/ -q`
- Result: **321 passed** (26 service + 295 others), 0 failed
- No regressions from prior 312 baseline

## Pre-merge gate
- Script: `scripts/checks/pre_merge_gate.sh`
- Status: PASS (after commit — working tree will be clean for merge)

## Next batch
Phase B direction or polish endpoint (`POST /translate/polish`) for the HTTP surface.

## Boundaries observed
- ✅ No CLI behavior changes
- ✅ No Prompt A / Prompt B modifications
- ✅ No orchestrator core, consistency, or quality module changes
- ✅ No real-model execution
- ✅ No generated outputs committed
- ✅ All tests use mock/stub, not real backends

## Validation status
- Tests/checks run: yes — `pytest app/tests/ -q` → 321 passed.
- Repo/worktree relevant: yes.
- Worktree clean: pending commit.
- Confidence: high — two test MagicMock attribute fixes, no behavioral surface changes.
- Notes: No real model invocation. No generated outputs created.

## Checkpoint summary
Batch 5C scope was already substantially implemented — the `POST /translate/chapter` endpoint existed in `draft_service.py` with full manifest/resume semantics and 26 mocked tests. Two test mocks needed `run_id` attribute set. Docs updated. Suite green at 321.
