# Lobster–ChatGPT Handoff Interface

## Purpose

This document defines the structured communication surface between Lobster and
ChatGPT within the Lobster-mediated quality loop. The main protocol (roles,
stop conditions, escalation, gate preservation) lives in
`LOBSTER_MEDIATED_QUALITY_LOOP.md`. This document is the machine-actionable
contract between the two actors: what Lobster delivers after each cycle and
what ChatGPT must return for Lobster to continue.

## Removal rule

If the Lobster–ChatGPT handoff feature is later rejected, deleting this file
and its single cross-reference in `LOBSTER_MEDIATED_QUALITY_LOOP.md` removes
the feature cleanly. No other file in this project references this document.

## Communication flow

```
Lobster cycle → report → [User reads, forwards to ChatGPT]
                         → ChatGPT reviews, returns verdict
                         → [User reads, decides to pass or stop]
                         → Lobster receives verdict or stops
```

1. Lobster runs one cycle and produces a structured evidence report.
2. The user reads the report (in-context in the Lobster session) and
   forwards it to ChatGPT (e.g., pastes into a ChatGPT conversation).
3. ChatGPT reviews the report and returns a structured verdict.
4. The user reads the verdict and decides whether to pass it to Lobster.
5. If yes, Lobster receives the verdict and may continue **only if** it is
   a structured verdict (not vague prose).
6. If no, the loop stops at the user's discretion.

There is no direct autonomous connection between Lobster and ChatGPT. The user
is always the bridge. This is intentional — it ensures the user remains the
final gate between analysis and action, and it means the protocol works with
zero automation infrastructure (just Claude Code and a ChatGPT conversation).

---

## 1. Lobster → ChatGPT: evidence report

Lobster delivers the evidence report as a structured text document with the
following sections.

### 1.1 Metadata

| Field | Example |
|-------|---------|
| Report version | `1` |
| Pipeline version | `v6` |
| Baseline | `v5` (commit `abc1234`) |
| Source | `one_chapter_quality_source.txt` (lines 1–87) |
| Run timestamp | `2026-05-04T10:00:00Z` |
| Anomalies | `none` (or: `segment 2 retry (timeout)`, `quality gate partial`) |

### 1.2 Signal table

One row per tracked signal. Tracked signals are defined by the current
baseline's inspection record. If no prior record exists, Lobster inspects
all signals from the existing Type A/B/C categories in `QUALITY_LOOP.md`.

| Signal | Source excerpt | Baseline rendering | Current rendering | Verdict | Operator note |
|--------|---------------|-------------------|-------------------|---------|---------------|
| 嫡母 (legal mother) | `嫡母` line 9 | "legal mother" | "legal mother" | UNCHANGED | Correct, no drift |
| 脸色黑了 | `脸色黑了` line 42 | "face darkened" | "face went pale" | REGRESSED | Reversal: darkened → pale |
| … | … | … | … | … | … |

Verdict labels:

| Verdict | Meaning |
|---------|---------|
| FIXED | Issue was present in baseline, now resolved in current |
| IMPROVED | Issue present in baseline, partially better but not fully resolved |
| REGRESSED | Was acceptable in baseline, worse in current |
| UNCHANGED | Same as baseline (acceptable or not) |
| NEW | Issue not present in baseline, appears in current |

### 1.3 Quality gate result

```
Status: PASS / FAIL
Consistency audit: N findings (list: …)
```

If FAIL, include the gate output so ChatGPT can assess whether the failure is
a quality issue or an infrastructure issue.

### 1.4 Anomalies

Any unexpected behavior during the run. Empty section if none.

```
- Segment 2 retried once (HTTPS read timeout, recovered on retry 2/3)
- Quality gate passed on retry
- No output truncation or data loss
```

---

## 2. ChatGPT → Lobster: structured verdict

ChatGPT returns a structured verdict with exactly the fields below. The verdict
is the **only** valid signal for Lobster to continue — Lobster must not accept
vague prose, unstructured notes, or human encouragement.

### 2.1 Verdict type

**One of:** `STOP` / `CONTINUE` / `NARROW` / `ESCALATE`

### 2.2 Classification table

One row per signal that was not `FIXED` or `UNCHANGED`. Signals that are
`FIXED` or `UNCHANGED` and acceptable may be omitted.

| Signal | Type | Finding | Concrete fix target | Expected outcome |
|--------|------|---------|---------------------|------------------|
| 脸色黑了 (line 42) | B | Still reversing darkened → pale despite existing style note | `project_assets/4. style_notes.md` — add to "facial-color handling" section: "Do NOT reverse 黑了 → pale. 黑了 means darkened, not pale." | Next run: line 42 renders "darkened" instead of "pale" |
| Scene-closing commentary (line 87+) | C | Hallucinated continuation after source end, Prompt A rule exists but model ignores it | Escalate to Prompt Change Gate — proposed diff: strengthen Prompt A line 59 from "Do not add" to "ABSOLUTELY DO NOT add"; rationale in gate proposal doc | Next run: output stops at source line 87 with no fabricated continuation |

**Concrete fix target format (required for CONTINUE):**

A single sentence specifying:
- The file to change (asset path, style note section, or prompt file + line)
- The exact change to make
- The expected behavioral change

Example:

> `project_assets/1. glossary.md` — add entry "福礼 → formal salute (ritual bow)".
> Expected: "formal salute" in next run instead of "felicity ritual."

### 2.3 Summary recommendation

One or two sentences:

> **Recommendation:** CONTINUE. One Type B fix target identified (facial-color
> reversal for 黑了). Fix is concrete and bounded. Proposed style note entry
> added to the classification table. If v6 shows the fix is insufficient,
> escalate to Type C.

> **Recommendation:** STOP. All signals are FIXED or UNCHANGED within the
> accepted baseline. No concrete fix target remains.

> **Recommendation:** NARROW. The sample is too broad to isolate the
> register-drift issue. Re-run on lines 30–45 (dialogue-heavy section) to
> narrow the evidence.

> **Recommendation:** ESCALATE. The facial-color reversal persists despite
> a Type B fix in v5. Type C is warranted but affects prompt stability.
> User must decide whether to proceed with a Prompt Change Gate review.

---

## 3. User-mediated bridge

### 3.1 Lobster → ChatGPT direction

The user reads Lobster's evidence report (from the Lobster session) and
forwards it to ChatGPT. The user does not summarize or selectively filter —
the full structured report is forwarded.

The forwarding method is not prescribed: paste the text, attach a file, or
describe the key sections. However, if significant evidence is omitted, the
verdict may be misinformed.

### 3.2 ChatGPT → Lobster direction

The user reads ChatGPT's structured verdict and decides whether to pass it
to Lobster. The user may:

| Action | Effect |
|--------|--------|
| **Pass as-is** | Lobster receives the verdict and may act on it if structured |
| **Pass with override note** | Lobster acts on the verdict but respects the override (e.g., "skip Type C for now, apply Type B only") |
| **Reject and stop** | Loop ends. The user judged the verdict not actionable or not worth the next cycle |
| **Reject and ask ChatGPT to revise** | Back to ChatGPT for a better verdict (narrower fix target, different classification) |
| **Bypass and issue direct instruction** | User issues their own instruction to Lobster, skipping ChatGPT's verdict |

The user is never required to pass a verdict they disagree with.

---

## 4. Lobster continuation constraint

**Lobster may continue to the next cycle only from a structured verdict.**

A structured verdict has all of:

- An explicit verdict type (`STOP` / `CONTINUE` / `NARROW` / `ESCALATE`)
- For `CONTINUE`: at least one classification-table row with a concrete fix
  target (file, exact change, expected outcome)
- For `NARROW`: an identified signal or passage scope to re-run

Lobster must **NOT** continue from:

- Vague prose: "That looks better, let's try another pass"
- Unstructured notes: "Fix the tone a bit"
- Human natural-language encouragement: "Almost there, keep going"
- An empty or placeholder verdict: "Verdict: pending"

If Lobster receives something that is not a structured verdict, it must not
proceed. The user must either convert it into a structured verdict or stop
the loop.

---

## 5. What still requires user approval

Even with a valid structured `CONTINUE` verdict, these actions still need
explicit user approval before Lobster acts:

| Action | Why |
|--------|-----|
| **Prompt edits** (Type C) | The Prompt Change Gate requires user review of the diff and verification plan |
| **Canonization Gate overrides** | RISKY or REJECTED canonization verdicts need user judgment |
| **Expanding the sample set** | Beyond `one_chapter_quality_source.txt` requires a separate batch |
| **Taste-level escalations** | The user is the sole authority for aesthetic red-line decisions |
| **STOP override** | If ChatGPT says `STOP` and user wants to continue, the override must be explicit in the verdict passed to Lobster |
| **First real-cycle run** | The first Lobster run with a real model backend needs explicit approval; subsequent cycles within the same session do not need re-approval as long as they follow from a structured verdict |

---

## 6. Interface versioning

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2026-05-04 | Initial — Lobster evidence report fields, ChatGPT structured verdict format, user-mediated bridge, continuation constraint |

The interface version appears in the evidence report metadata. If the report
version and the verdict version are mismatched, the protocol is out of sync —
stop and resolve before proceeding.
