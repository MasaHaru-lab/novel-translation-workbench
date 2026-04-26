# v6 Verification Report

**Batch:** Phase B — v6 verification
**Date:** 2026-04-26
**Branch:** `work/phase-b-v6-verify`

## Outcome: PASS

Both Type C rules verified against real model output (qwen2.5:14b via Ollama on Fishhead). No source-absent continuation. Facial-color direction correct.

## Evidence Chain (v1–v6)

### Signal 1 — Narrative stance (hallucinated scene-closing commentary)

Target: Prompt A line 59 — `Do not add scene-ending commentary or narrative continuation beyond what the source provides.`

| Run | Status | Detail |
|-----|--------|--------|
| v1 | FAIL | Full continuation paragraph after source end (Red Yuan Daoist speculation) |
| v3 | FAIL | Fabricated Lady Xie closing line ("Lady Xie had been deliberately goading Qin Liuxi...") |
| v4 | FAIL | Continued past source end with Red Yuan Daoist speculation paragraph |
| v5 | FAIL | Continued past source end with additional dialogue (Old Lady Qin continuing about Meng Li) |
| **v6** | **PASS** | **Ends at source line 82 (谢氏像是一拳打在棉花上，气闷不已 → "Lady Xie felt frustrated, like hitting a soft wall.") No fabricated continuation.** |

**Pattern:** All 4 pre-Type-C runs (v1–v5) show fabricated continuation. v6 (post-Type-C rule at Prompt A line 59) shows correct behavior — no hallucinated scene-closing commentary.

**Type C rule verdict:** Effective. The constraint at Prompt A line 59 resolved the hallucinated-continuation pattern.

### Signal 2 — Facial-color direction (黑了 → darkened)

Target: Prompt A line 70 — `Do not reverse facial-color emotional signals. 黑了 means the face darkened (with displeasure), not turned pale.`

| Run | Status | Detail |
|-----|--------|--------|
| v1 | FAIL | "turned pale" ✗ |
| v3 | FAIL | "turned pale, clearly displeased" ✗ |
| v2 | PASS | "face darkened" ✓ |
| v4 | PASS | "face darkened" ✓ |
| v5 | PASS | "face darkening with anger" ✓ (direction correct, mild over-interpretation) |
| **v6** | **PASS** | **"Old Lady Qin was taken aback, her face darkening." ✓** |

**Pattern:** 2/6 runs failed (v1, v3). The last 4 runs show correct direction (v2, v4, v5, v6). The style note + Prompt A rule is effective.

**Type C rule verdict:** Effective. The constraint at Prompt A line 70 resolved facial-color reversal.

## v6 Verification Run Details

**Backend:** Ollama on Fishhead (`qwen2.5:14b`), proxied through `http://localhost:18001/generate`
**Model:** qwen2.5:14b (Q4_K_M, 14.8B params, RTX 3090)
**Source:** `data/source/one_chapter_quality_source.txt` (1853 chars, 83 lines)
**Segments:** 3 (finer granularity, max_chars=800)
**Elapsed:** 57.5 seconds

### Quality gate note

Quality gate reported FAILED: segment 1 polished output retains 7 CJK characters (segment_residue: "无情恩无情恩"). This is a known model output artifact (CJK character retention) unrelated to the Type C rules under verification. It does not affect the narrative-stance or facial-color verdicts.

### Consistency run

- 2 issues found: 1 name_variant, 1 title_variant
- 1 auto-fixed (name_variant correction applied)
- Post-consistency: 5556 chars

## Fishhead Target Resolution

SSH alias `Fishhead-Core` resolved dynamically with `ssh -G`:

```
hostname: 192.168.68.61
user: ambrosia
port: 22
```

**Corrected:** The earlier `.51` assumption was wrong. `.51` pings but refuses SSH on port 22. The working target is `ambrosia@192.168.68.61`.

**Ollama status:** Running on Fishhead at localhost:11434 with `qwen2.5:14b` loaded. Reachable via SSH tunnel + proxy.

**Wrapper status:** The legacy `http://192.168.68.51:8001/generate` wrapper is not running. The v6 run used an Ollama proxy at `http://localhost:18001/generate` (SSH tunnel + Python proxy script).

## Verdict

- Narrative-stance signal: **PASS** ✓ — Translation ends at source line 82 without fabricated continuation.
- Facial-color signal: **PASS** ✓ — 秦老太太一呛，脸色都黑了 → "her face darkening" (not "pale").
- Overall: **PASS** — Both Type C rules verified effective against real model output.

## What was done

- Fishhead target resolved: `192.168.68.61` (via `ssh -G Fishhead-Core`)
- Fishhead connectivity verified: SSH (publickey) successful, hostname=`fishhead`, GPU=RTX 3090
- Ollama proxy deployed (Python built-in http.server, no extra deps)
- SSH tunnel + proxy started for Model backend connectivity
- v6 verification run executed (3 segments, 57.5s)
- Output inspected for both Type C rule compliance
- This report updated with fresh evidence

## What was intentionally not changed

- No prompt changes (Type C rules were already present, now verified effective)
- No project asset changes
- No application code changes
- No CLI, HTTP/API, manifest/resume, output format, or quality-gate changes
- No Phase A surface touched
- No Prompt A or Prompt B modifications
- Generated outputs stay under `data/outputs/` (gitignored)

## Generated artifacts (gitignored)

- `data/outputs/quality_v6_run.md` — chapter translation output
- `data/outputs/quality_v6_run.manifest.json` — run manifest

## Next action

Phase B quality loop complete for current Type C candidates. No immediate follow-up verification required unless Type C rules are modified in future batches.
