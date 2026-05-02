# Inspection Record

This is the canonical template for inspecting one completed chapter run.
Copy to `data/exports/<chapter_name>_inspection.md` and fill in the operator's
judgment fields during Step 4 of the Phase C production workflow.

> **Important:** This is a **human judgment record**, not an automated quality
> guarantee. The quality gate (`validate_chapter_output()`) is the automated
> check. The inspection record captures what the operator observed during
> passage-by-passage comparison of source and output.

---

## Chapter Info

| Field | Value |
|-------|-------|
| Chapter | `<chapter_name>` |
| Source | `data/source/<chapter_name>.txt` |
| Output | `data/exports/<chapter_name>_en.md` |
| Manifest | `data/exports/<chapter_name>_en.manifest.json` |
| Inspector | `<your name>` |
| Date | `<YYYY-MM-DD>` |
| Git ref | `<branch> @ <commit>` |

---

## Run Summary (from manifest)

| Check | Result |
|-------|--------|
| Manifest status | `COMPLETED` / `PARTIAL` / `FAILED` |
| Quality gate | `PASSED` / `FAILED` |
| Total segments | `<N>` |
| Completed segments | `<N>` |
| Smoke test | `YES` / `NO` |

---

## Inspection Method

Read the output passage by passage against the source. For each segment,
note any issues found. Key categories to watch for:

| Category | What to look for |
|----------|------------------|
| Meaning errors | Wrong time units, dynasty names, causal relationships |
| Instruction leakage | Asset field text appearing verbatim in output |
| Name/address drift | Over-Westernized titles, flat/mechanical renderings |
| Hallucinated additions | Scene-closing commentary not in source, invented introspection |
| Facial-color/state reversal | 黑了 rendered as "pale" instead of "darkened" |
| Register errors | Over-modern phrasing in historical setting |
| Missing content | Source paragraphs dropped from output |
| Inline Chinese | Chinese characters or pinyin left in English prose |

---

## Per-Segment Inspection

| Segment | Chars | Issues? | Notes |
|---------|-------|---------|-------|
| `seg_1` | `<N>` | `YES` / `NO` | |
| `seg_2` | `<N>` | `YES` / `NO` | |
| ... | ... | ... | ... |
| `seg_N` | `<N>` | `YES` / `NO` | |

---

## Issues Found

For each issue, record: segment, description, and issue type.

**Issue types** (see `docs/QUALITY_LOOP.md` for full definitions):
- **Type A** — Glossary/lexical: names, terms, fixed expressions. Fix: write to `project_assets/`.
- **Type B** — Style/behavioral: rules about how to translate (prose guidance). Fix: write to style notes.
- **Type C** — Persistent behavioral failures that Type A/B cannot resolve. Fix: prompt-level enforcement (requires Prompt Change Gate).

| # | Segment | Issue | Type | Action |
|---|---------|-------|------|--------|
| 1 | | | | |
| 2 | | | | |
| ... | | | | |

---

## Global Observations

- **Consistency:** Any cross-segment drift in names, terms, or style?
- **Fluency vs. fidelity:** Does the translation favor flow over meaning in any passage?
- **Tone/register:** Is the narrative voice appropriate for the genre and setting?

---

## Next Actions

- [ ] Record Type A findings in `project_assets/` glossary / titles and terms
- [ ] Record Type B findings in style notes
- [ ] Submit Type C change proposal to Prompt Change Gate (if warranted)
- [ ] Update book memory if needed
- [ ] Defer unresolved items to Phase B quality loop

---

## Verdict

| Decision | Meaning |
|----------|---------|
| **ACCEPT** | Chapter passes inspection. No blockers. Proceed to next chapter or stop. |
| **HOLD** | Minor issues found. Chapter is acceptable but observations should inform asset/prompt updates before the next chapter. |
| **REVISE** | Issues found that warrant re-translation or correction. Apply fixes, then re-inspect. |
| **CAPTURE** | Systematic failure. Capture artifacts via `docs/templates/BAD_CASE_CAPTURE_TEMPLATE.md` and register in `docs/bad_cases/INDEX.md`. Re-translate after root cause is fixed. |

**Verdict:** `ACCEPT` / `HOLD` / `REVISE` / `CAPTURE`

**Rationale:** (one or two sentences explaining the verdict)

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
| COMPLETED | PASSED (issues found) | HOLD or REVISE, or CAPTURE if systematic |
| PARTIAL | FAILED | REVISE or CAPTURE |
| PARTIAL | PASSED | REVISE or CAPTURE (should not normally occur — investigate first) |
| FAILED | N/A | CAPTURE |

---

## Capture Workflow

If the verdict is **CAPTURE** (whether due to gate failure or operator judgment
of a systematic issue that passed the gate):

1. Create a capture directory: `data/captures/<capture_name>/`
2. Copy the source, output, and manifest into it
3. Write a capture note using `docs/templates/BAD_CASE_CAPTURE_TEMPLATE.md`
4. Register the capture in `docs/bad_cases/INDEX.md`

See `docs/PHASE_C_PRODUCTION_WORKFLOW.md` §10 for the full capture rules.
