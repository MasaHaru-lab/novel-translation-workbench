# Session Checkpoint — 2026-04-26 (long-run workflow infra)

## Current focus
Batch completed: established the local PR-style long-run workflow for this repo (branch model, pre-merge gate script, Fishhead/3090 usage boundary). Pure infrastructure — no application logic touched. Batch 5A is **not** started; that remains the next planning candidate.

## Long-run workflow (this batch)
- **`CLAUDE.md`** — added "Local PR-style long-run workflow" section: `main` as seal point, `work/<topic>` for施工, squash-merge back to main, gate-before-merge rule, Fishhead/3090 boundary (read-only health / contract / synthetic only; no real-sample acceptance without per-batch approval), and explicit non-authorizations (no Batch 5A, no GH Actions, no auto-push/merge).
- **`scripts/checks/pre_merge_gate.sh`** (new, executable) — offline merge-readiness gate. Checks: inside git repo, working tree clean, `data/output` / `data/exports` / `outputs` not tracked, branch is `work/<topic>` (warn on main / detached). Exits 1 on FAIL, 0 on PASS. Does **not** run pytest, call models, or contact Fishhead.
- **Fishhead health check (this session)**: `ssh Fishhead-Core 'hostname && nvidia-smi'` returned `Permission denied (publickey,password)` — TCP/SSH reachable on `192.168.68.61`, host is up, but key auth not configured for this shell. Treated as connectivity-only signal; no model verification performed. No artifacts generated.
- **Fishhead IP**: `192.168.68.61` is current and already correct in `STATUS.md` / `SESSION_CHECKPOINT.md`. No fact update needed.

## Prior batch (preserved for resume context)
Earlier focus: chapter-level quality gate hardened so a "completed" run cannot mask a failed quality check. Operator-visible (CLI) and persistent (manifest JSON) signals wired in. Committed.

## Confirmed done

### Quality gate hardening (this batch) — committed `9360892`
- **`app/chapter/quality.py`** — deterministic post-hoc gates (chapter-level CJK residue, untranslated title, per-segment empty, per-segment CJK residue). `QualityReport.to_summary()` gives a stable JSON shape.
- **Orchestrator wiring** (`app/chapter/orchestrator.py`) — both `execute()` and `run_with_manifest()` call `validate_chapter_output()` and attach `result.quality_report`. `run_with_manifest()` additionally writes the summary into `manifest.quality_summary` and re-saves the manifest after aggregation.
- **`ChapterResult.quality_report`** field added (`app/chapter/models.py`).
- **`RunManifest.quality_summary`** field added with full JSON serialize / deserialize support (`app/chapter/manifest.py`). Persisted manifest JSON now carries `{passed, error_count, warning_count, codes}`.
- **CLI visibility** (`app/cli.py`) — `_report_chapter_result()` prints a `Quality:` line right after `Status:`. On fail: `Quality: FAILED — N error(s) [codes...]` plus per-error message lines. On pass: `Quality: passed`.
- **Coverage gate enrichment** (`app/translate/translator.py`) — `check_segment_coverage()` extended with CJK residue rule and glossary-enforcement rule; uses shared `_CJK_RE` / `_count_cjk` helpers.
- **`.gitignore`** — `data/output/` added so generated runs never enter git status.
- **Tests** — `app/tests/test_quality.py` (13 cases incl. CLI capsys tests + manifest persistence test using `tmp_path`); `app/tests/test_translator.py` extended with CJK residue + glossary enforcement cases.
- **Validation**: `venv/bin/python -m pytest app/tests/ -q` → **303 passed** (was 299 baseline).
- **Files in commit (10)**: `.gitignore`, `app/chapter/manifest.py`, `app/chapter/models.py`, `app/chapter/orchestrator.py`, `app/chapter/quality.py` (new), `app/cli.py`, `app/tests/test_quality.py` (new), `app/tests/test_translator.py`, `app/translate/translator.py`, `data/source/one_chapter_quality_source.txt`.

### Chapter heading aggregation fix (Batch 4C) — pending commit
- **`app/chapter/orchestrator.py`**: aggregation no longer prepends raw `# {chapter_title}`.
- **`app/chapter/quality.py`**: `title_untranslated` checks final output first line, not metadata title.
- **`app/tests/test_chapter.py` and `app/tests/test_quality.py`**: updated coverage.
- **Validation**: `venv/bin/python -m pytest app/tests/ -q` → 303 passed.
- **Known residual**: `app/chapter/consistency.py` TITLE_FORMAT deferred to later chapter output format contract work.

## Live calibration (2026-04-25, no code change)
- Real Fishhead chapter run on `data/source/one_chapter_quality_source.txt` (with `MODEL_BACKEND_URL` set, `--service-url http://localhost:8000`) confirms gate behavior end-to-end.
- CLI prints `Status: completed` together with `Quality: FAILED — 2 error(s) [title_untranslated, cjk_residue]` plus per-error lines — completion no longer masks quality failure.
- Manifest `quality_summary` persisted correctly in `data/output/q_run.manifest.json`: `{passed: false, error_count: 2, warning_count: 0, codes: [title_untranslated, cjk_residue]}` alongside `status: completed`.
- Gate surfaced two real defects: chapter heading left untranslated (line 1) and bilingual paraphrasing residue (`无情(heartless)`, `恩(goodwill)`) in body.
- Threshold judgment: chapter-level residue threshold (8) is correctly tuned. The 22 CJK count is dominated by the 16-char title; body alone (~6) sits below threshold, leaving body-residue detection to the title-specific rule when only the heading fails. **No threshold adjustment needed.**
- Generated outputs (`data/output/q_run.md`, `data/output/q_run.manifest.json`) are gitignored and will not be committed.

## Still pending / blocked / unverified
- ~~Real-model verification not done.~~ Done — see "Live calibration" above. Thresholds verified against real Fishhead output; no change.
- ~~CLI quality output never exercised against a live `chapter run`.~~ Done — verified in live run.
- **`execute()` path doesn't persist quality** (no manifest in that path). Only `run_with_manifest()` persists. Acceptable today because production CLI uses `run_with_manifest()`, but worth noting if `execute()` is ever exposed.
- **Glossary enforcement rule is exact-substring**, no normalization (case, plural, possessive). May fire on legitimate paraphrases.
- **Source data file** `data/source/one_chapter_quality_source.txt` was truncated as part of an earlier batch and is now committed in that shorter form. If the original full text is wanted, restore from git history before `9360892`.
- **STATUS.md not yet updated** to reflect this batch's additions.

## Next starting action
Mainline seal point is commit `901eb89` (Batch 4C: chapter heading fix).

Next session: do big-picture project orientation first — prioritize between Batch 5 (chapter-level CLI/HTTP integration, per ORCHESTRATION.md) and the chapter output format contract residual (`consistency.py` TITLE_FORMAT). Do not execute directly; assess and decide before committing to a batch.

Secondary: update `STATUS.md` to add a "Quality gate (post-hoc)" row under Current Capabilities.

## Checkpoint saved to
`SESSION_CHECKPOINT.md` (replaced — was the prior coverage-gate checkpoint dated 2026-04-25).

## Checkpoint file and key artifacts
- `SESSION_CHECKPOINT.md` (this file)
- Source of truth for capabilities: `STATUS.md`
- Quality module: `app/chapter/quality.py`
- Manifest schema: `app/chapter/manifest.py` (`RunManifest.quality_summary`)
- CLI report function: `app/cli.py` `_report_chapter_result()`
- Quality tests: `app/tests/test_quality.py`
- Last commit: `9360892 Harden quality gates and surface chapter quality status`

## Validation status
- Tests/checks run: yes — `pytest app/tests/ -q` → 303 passed
- Repo/worktree relevant: yes
- Worktree clean: yes (post-commit, `git status --short` empty)
- Confidence: high (for the wiring); medium (for real-data calibration)
- Notes: No real model invocation in this batch. CLI block was tested via capsys, not a live run.

## Checkpoint summary
Quality gate is now operator-visible and persistent. Manifest cannot say "completed" while quality fails. Suite green at 303. Worktree clean. Real-model calibration of residue thresholds is the obvious next gap.
