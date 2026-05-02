# Inspection Record — Stage 2 Rehearsal

> **Rehearsal run.** This record tests the inspection template (`docs/templates/INSPECTION_RECORD_TEMPLATE.md`)
> against real model output from the Phase B validation closeout. It is not a production inspection.
>
> Source of evidence: `data/exports/phase_b_round2_fixcheck_output.md` (corrected output)
> and `data/exports/phase_b_round2_output.md` (pre-fix output — inspected for comparison).

---

## Chapter Info

| Field | Value |
|-------|-------|
| Chapter | `one_chapter_quality` (source heading: 秦流西见状抬腿要走，秦老太太叫住了她。) |
| Source | `data/source/one_chapter_quality_source.txt` |
| Output (inspected) | `data/exports/phase_b_round2_fixcheck_output.md` |
| Manifest (inspected) | `data/exports/phase_b_round2_fixcheck_output.manifest.json` |
| Pre-fix output (comparison) | `data/exports/phase_b_round2_output.md` |
| Pre-fix manifest (comparison) | `data/exports/phase_b_round2_output.manifest.json` |
| Inspector | (rehearsal — no assigned operator) |
| Date | 2026-05-02 |
| Git ref | `work/phase-c-stage-2-inspection-rehearsal` @ `204e622` basis |

---

## Run Summary (from manifest)

| Check | Fixcheck (inspected) | Round 2 (pre-fix) |
|-------|----------------------|-------------------|
| Run ID | `875b6378fce0` | `ec3f36072b32` |
| Manifest status | `COMPLETED` | `COMPLETED` |
| Quality gate | `PASSED` | `PASSED` |
| Total segments | 3 | 3 |
| Completed segments | 3 | 3 |
| Smoke test | NO | NO |

> **Note:** The quality gate passed for both runs, but the round 2 output has a
> demonstrable name-contamination issue (see Issue #1 below). The automated quality
> gate did not catch it — the fixcheck was a manual re-run triggered by operator review.

---

## Inspection Method

Compared the fixcheck English output passage by passage against the Chinese source text.
Also compared the round 2 output against both to identify what was fixed and whether
any issues survived into the fixcheck.

---

## Per-Segment Inspection

| Segment | Chars (source) | Issues? | Notes |
|---------|---------------|---------|-------|
| seg_1 | ~1190 | NO | Clean. Correctly uses "Old Lady Qin" throughout. No name contamination. |
| seg_2 | ~950 | YES | "sheep immortal" instead of established "Ram Immortal" (Type A). "sheep" used for 羊 in founding myth context. |
| seg_3 | ~630 | NO | Clean. Consistent with source. |

---

## Issues Found

**Issue types (per docs/QUALITY_LOOP.md):**
- **Type A** — Glossary/lexical: names, terms, fixed expressions. Fix: write to `project_assets/`.
- **Type B** — Style/behavioral: rules about how to translate (prose guidance). Fix: write to style notes.
- **Type C** — Persistent behavioral failures that Type A/B cannot resolve. Fix: prompt-level enforcement (requires Prompt Change Gate).

| # | Segment | Issue | Type | Action |
|---|---------|-------|------|--------|
| 1 | seg_1 (pre-fix) | **Name contamination (FIXED).** The round 2 output prepended "Chi Yuan Daoist" to "Old Lady Qin" throughout — producing "Chi Yuan Daoist Lady Qin" as a compound name. The source clearly distinguishes 赤元老道 (Chi Yuan Daoist) from 秦老太太 (Old Lady Qin) as separate characters. The fixcheck resolved this correctly. | Type A | Already fixed. Consider adding an asset note about the separate identities of Chi Yuan Daoist and Old Lady Qin to prevent regression. |
| 2 | seg_2 (fixcheck) | **"sheep immortal" downgrade.** The fixcheck renders 羊仙 as "sheep immortal" rather than the established "Ram Immortal." The round 2 output correctly used "Ram Immortal." The fixcheck also uses "sheep" throughout the founding myth where "ram" carries more specific ceremonial weight. | Type A | Restore "Ram Immortal" in `project_assets/titles_and_terms.md`. Add 羊仙→Ram Immortal to glossary if not present. |
| 3 | seg_1–2 (pre-fix) | **Segment boundary overlap (FIXED).** Round 2 output had seg_1 and seg_2 both starting with "Qin Liuxi made to leave / was about to leave when [X] called her back" — covering the same narrative moment. The fixcheck corrected this: seg_1 ends with the sacrificial ram, seg_2 picks up with the founding legend. | Type B (workflow) | Already fixed. The orchestrator's segment-split logic produced the overlap; the fixcheck re-run resolved it. No further action unless boundary overlaps recur. |
| 4 | seg_1 (pre-fix) | **Chapter title variation.** Three renderings of 小人作崇所为 across the outputs: "The Work of Petty Villains" (round 2 v1), "The Work of a Petty Schemer" (round 2 v2), "The Mischief of Petty People" (fixcheck). "Petty schemer" over-specifies (作祟 = cause mischief, not necessarily scheming). The fixcheck's "The Mischief of Petty People" is best aligned with the source. | Type B | Add a style note about chapter title translation registering the preferred rendering. |
| 5 | All (pre-fix) | **Quality gate gap.** Both manifests report `quality_summary.passed: true` with zero warnings, but the round 2 output contains a clear name-contamination issue affecting every segment. The automated gate did not flag it. | Type C (candidate) | This suggests the current quality gate does not detect character-name instruction leakage or string pollution. A capture candidate for future investigation. |

---

## Global Observations

- **Consistency:** The fixcheck output is internally consistent — no cross-segment name drift. The round 2 output had a systemic "Chi Yuan Daoist Lady Qin" contamination that propagated to all three segments, consistent within each segment but globally wrong.
- **Fluency vs. fidelity:** The fixcheck translation is fluent and idiomatic. At one point it chooses "sheep" over "ram" (which weakens the ceremonial register) — this is a fidelity tradeoff in favor of more common vocabulary.
- **Tone/register:** The fixcheck preserves the historical novel register well. "serving the sovereign is like sleeping beside a tiger" is a good rendering of 伴君如伴虎. "The Mischief of Petty People" as a chapter title is appropriately literary without being archaic.
- **Quality gate blind spot:** The `phase_b_round2_output` quality gate passed despite a clear, systemic name-translation failure. This is the most significant finding of this rehearsal — the automated gate did not detect a character-identity reversal.

---

## Next Actions

- [ ] Record Type A finding #2 (羊仙 → Ram Immortal) in `project_assets/titles_and_terms.md`
- [ ] Record Type A finding #1 (Chi Yuan Daoist / Old Lady Qin separate identities) in `project_assets/characters.md` if not already present
- [ ] Record Type B finding #4 (chapter title style) in style notes
- [ ] Consider whether Type C finding #5 (quality gate gap on name contamination) warrants capture automation or gate enhancement — **deferred to Stage 3 discussion**
- [ ] The template felt complete for this rehearsal. See friction notes below.

---

## Verdict

| Decision | Meaning |
|----------|---------|
| **ACCEPT** | Chapter passes inspection. No blockers. Proceed to next chapter or stop. |
| **HOLD** | Minor issues found. Chapter is acceptable but observations should inform asset/prompt updates before the next chapter. |
| **REVISE** | Issues found that warrant re-translation or correction. Apply fixes, then re-inspect. |
| **CAPTURE** | Systematic failure. Capture artifacts to `data/captures/<chapter_name>/` for later investigation. Re-translate after root cause is fixed. |

**Verdict:** `HOLD`

**Rationale:** The fixcheck output is acceptable as a chapter translation and reads well. However, two actionable artifacts remain: (1) the established term "Ram Immortal" was replaced with "sheep immortal" in the fixcheck (should be restored in project assets), and (2) the quality gate gap on name contamination is a systemic concern that should inform the Stage 3 capture design discussion. The chapter itself does not require re-translation.

---

## Supporting Details

### Verdict -> Workflow Mapping

| Verdict | Phase C action |
|---------|---------------|
| ACCEPT | Chapter done. Optionally record observations for future style hardening. |
| HOLD | Chapter accepted. Findings deferred to quality loop or next batch. |
| REVISE | Fix findings, re-run translation, re-inspect. |
| CAPTURE | Capture artifacts. Investigate root cause before retranslation. |

### Manifest status combinations

| Manifest status | Quality gate | Typical verdict |
|----------------|--------------|----------------|
| COMPLETED | PASSED | ACCEPT or HOLD |
| COMPLETED | PASSED (issues found) | HOLD or REVISE |
| PARTIAL | FAILED | REVISE or CAPTURE |
| PARTIAL | PASSED | REVISE or CAPTURE (should not normally occur — investigate first) |
| FAILED | N/A | CAPTURE |

### Template Friction Notes (Rehearsal Feedback)

1. **Per-segment char count ambiguity.** The template asks for `<N>` chars per segment. The source char count is not trivial to extract for a multi-segment run — the operator needs to count source chars per segment boundary. Consider whether a "total source chars" summary field would be more practical, or whether the orchestrator should emit per-segment source char counts.

2. **Pre-fix vs. fixcheck handling.** When a re-run produces a corrected output, the single-segment table row doesn't easily capture "issue was in pre-fix, resolved in fixcheck." Option: let the per-segment notes field reference pre-fix issues explicitly, or add a "Regression?" column.

3. **Quality gate gap.** The template assumes `PASSED` implies no issues, but this rehearsal found a case where `PASSED` masked a systemic failure. The template could note this possibility explicitly (the "Manifest status combinations" table already partially covers this with the "PASSED (issues found)" row, but the quality gate field itself only shows PASSED/FAILED with no way to record "passed despite observable issues").
