# Lobster-Mediated Quality Loop

## Purpose

The existing Phase B quality loop (`QUALITY_LOOP.md`) defines a monolithic
process: run → inspect → classify → resolve → verify. This protocol adds an
orchestration layer that splits those responsibilities across three roles:
**Lobster** (executor/reporter), **ChatGPT** (classifier/recommender), and
**the user** (final authority).

The goal is not to replace the existing quality loop. It is to add **stop
logic** and **role separation** so that each iteration has a clear,
evidence-backed reason to proceed — and a clear, enforceable reason to stop.

## Role definitions

### Lobster — executor/reporter

Lobster runs one bounded quality-loop iteration and returns an evidence report.
It does not decide whether the loop should continue.

**What Lobster does:**
- Runs the translation pipeline on the approved quality sample
  (`one_chapter_quality_source.txt`) or on a narrower passage requested by
  ChatGPT or the user
- Runs the consistency audit and quality gate
- Inspects the output against the existing Type A/B/C classification from
  `QUALITY_LOOP.md`
- Produces a structured evidence report with signal-by-signal comparison
  (what improved, what regressed, what stayed the same)
- Applies fixes only when instructed by ChatGPT (with a concrete fix target)

**What Lobster does NOT do:**
- Classify findings or decide their resolution path
- Decide whether the loop should continue or stop
- Make taste-level or aesthetic judgments
- Bypass the Prompt Change Gate or Canonization Gate
- Expand the sample set or modify project assets independently

**Evidence report content:**
- Which pipeline version was run (vN)
- Signal-by-signal comparison (vs the previous baseline)
- Output excerpts showing each signal's current state
- Consistency audit results
- Quality gate result
- Any anomalies or unexpected behavior

### ChatGPT — classifier / decision-recommender

ChatGPT reviews Lobster's evidence report and issues a recommendation to
continue, narrow, escalate, or stop.

**What ChatGPT does:**
- Reviews the full evidence report
- Classifies each observed issue using the existing Type A/B/C taxonomy from
  `QUALITY_LOOP.md`
- Assesses whether a concrete fix target exists for the current iteration
- Recommends one of: STOP, CONTINUE (with fix target), NARROW (narrow the
  sample scope for the next Lobster run), or ESCALATE (to user)
- If CONTINUE: specifies the exact fix target (which asset entry to add,
  which style note to modify, or which prompt diff to propose)
- If NARROW: identifies the specific passage or signal type to re-run
- Verifies Lobster's fix results on the next iteration
- Opens a new Lobster cycle only when the fix target is concrete and bounded

**What ChatGPT does NOT do:**
- Override the user's taste-level authority
- Approve prompt changes without the Prompt Change Gate
- Insist on continuation when no concrete fix target exists
- Run the pipeline or inspect raw output directly

### User — final authority

The user remains the final authority for all decisions. Every recommendation
from ChatGPT is a recommendation, not a command.

**The user is the sole decision-maker for:**
- Taste-level and aesthetic red-line issues
- Whether a risky Type C prompt change is worth the stability risk
- Whether an unresolved rendering in `unresolved_decisions.md` is acceptable
- Whether the current quality level is sufficient to stop the loop entirely
- Whether the loop should expand to a new sample or passage

**The user may also:**
- Stop the loop at any point, without explanation
- Override ChatGPT's recommendation (accept a stop recommendation and
  continue anyway, or reject a continuation recommendation and stop)
- Bypass the loop entirely for urgent fixes
- Change the protocol itself

## Loop structure: one cycle

```
Lobster run + report  →  ChatGPT review  →  Decision  →  (action | stop)
```

| Step | Actor | Action |
|------|-------|--------|
| 0 | (any) | Define the target: which passage, which baseline version, what to look for. Default = full quality sample vs latest baseline. |
| 1 | Lobster | Run the pipeline and produce the evidence report. |
| 2 | ChatGPT | Review the report. Classify each finding. Issue a recommendation. |
| 3 | ChatGPT or User | Act on the recommendation: STOP, CONTINUE (with fix target), NARROW, or ESCALATE. |
| 4 | (if CONTINUE) | Lobster applies the fix (asset edit, style note, or prompt diff) and re-runs. ChatGPT verifies the result. If verified, STOP. If not, ESCALATE. |

The structured communication contract for Lobster's evidence report and
ChatGPT's verdict is defined in a standalone document:

> [`docs/LOBSTER_CHATGPT_HANDOFF_INTERFACE.md`](LOBSTER_CHATGPT_HANDOFF_INTERFACE.md)
> — evidence report format, structured verdict format, user-mediated bridge,
> continuation constraint, and removal rule.

## Stop conditions

The loop **must stop** when any of these conditions are met:

1. **No findings.** The evidence report shows no meaningful quality improvement
   remaining — all observed issues are within the accepted baseline.
2. **No concrete fix target.** ChatGPT cannot identify a specific, bounded fix
   target. The loop must not continue on vague motivation ("improve style,"
   "make it sound better").
3. **User stops it.** The user says stop, at any point, for any reason.
4. **Regression without explanation.** Lobster's report shows a regression
   from the previous quality baseline, and the root cause is not understood.
   Escalate to user before proceeding.
5. **Gate block.** A required gate (Prompt Change Gate, Canonization Gate)
   blocks the proposed fix. Do not proceed until the gate issue is resolved.
6. **Consecutive narrow without convergence.** Two consecutive NARROW
   recommendations did not reduce to a concrete fix target. Escalate to user.

## Continuation rule — the concrete fix target invariant

**The loop must not continue without a concrete fix target.**

A concrete fix target is a statement of the form:

> "Issue X was observed in signal Y. The fix is to [add glossary entry Z /
> modify style note W / apply prompt diff D]. The expected effect is that
> signal Y changes from {current output} to {expected output}."

A concrete fix target is NOT:
- "Improve overall fluency"
- "Reduce translationese"
- "Make the character voices more distinct"
- "Fix the tone"

If the fix target is not concrete, the loop must not proceed. The decision is
NARROW (try to make it concrete) or ESCALATE (ask the user).

## Escalation path

When ChatGPT issues an ESCALATE recommendation:

1. **Present the evidence** — Lobster's report + ChatGPT's classification +
   the reason escalation is needed (no concrete fix target, user-level taste
   decision, unexpected regression, gate dispute).
2. **State the question** — What exactly needs the user to decide? One
   sentence.
3. **State ChatGPT's recommendation** — What ChatGPT would do if it had
   authority.
4. **Stop.** Do not continue until the user responds.

## Relationship to existing gates

| Gate | Interaction with Lobster |
|------|--------------------------|
| **Prompt Change Gate** (`QUALITY_LOOP.md` §Prompt Change Gate) | Lobster does not bypass it. If ChatGPT recommends a Type C fix, the Prompt Change Gate still applies before any prompt edit. Lobster must document the gate step in its evidence report. |
| **Canonization Gate** (`QUALITY_LOOP.md` §Canonization Gate + `app/chapter/canonization.py`) | Lobster does not bypass it. Type A/B fixes still go through canonization before being written to `project_assets/`. |
| **Pre-merge Gate** (`CLAUDE.md` + `scripts/checks/pre_merge_gate.sh`) | Not affected by the Lobster loop. The pre-merge gate runs independently before any squash-merge to main. |
| **Review Gate** (`CLAUDE.md` §Review Gate) | Not affected. The Lobster loop is a quality-loop mechanism, not a batch-completion gate. The Review Gate still requires explicit operator approval before merge. |

The Lobster protocol does not relax any existing gate. It adds an
orchestration layer on top of the existing resolution machinery.

## Boundary map

| Area | Status | Notes |
|------|--------|-------|
| `QUALITY_LOOP.md` — mechanical loop | REFERENCED | The Lobster protocol uses Type A/B/C classification and existing resolution paths. It does not rewrite the mechanical loop. |
| `app/chapter/canonization.py` — Canonization Gate | REFERENCED | Lobster must call the gate for Type A/B fixes. |
| `prompts/prompt_a.md`, `prompts/prompt_b.md` | GATED | Lobster may not edit prompts without the Prompt Change Gate passing. |
| `project_assets/*.md` | GATED | Lobster may not write new entries without Canonization Gate clearance. |
| Bad-case captures (`data/captures/`) | OPEN | Lobster may create capture entries as part of an evidence report, but only as evidence — not as a fix action. |
| Sample set (`data/source/`) | FROZEN | Lobster may not expand the approved quality sample set without a separate batch. |
| CLI, HTTP, orchestrator, quality gate | FROZEN (Phase A) | Lobster may not modify these surfaces. |

## Overlaps and conflicts with existing docs

| Existing document | Overlap | Resolution |
|-------------------|---------|------------|
| `QUALITY_LOOP.md` §"Quality review methodology" (run → inspect → record → classify → resolve → verify) | The mechanical steps overlap with Lobster's execution. | `QUALITY_LOOP.md` defines *what* to do. This protocol defines *who* does it and *when to stop*. Both documents remain valid; this one references the mechanical loop by name. |
| `WORKFLOW.md` §"Routing Architecture" | Lobster and ChatGPT are new actors not defined in the layer model. | They are orchestration actors, not workflow layers. They do not change the routing architecture. They can be added as a note in a future update to `WORKFLOW.md` if needed. |
| `PHASE_C_PRODUCTION_WORKFLOW.md` | Phase C defines operator-safe production runs. This protocol is quality-loop orchestration, not production workflow. | No overlap. They address different stages (quality tuning vs production execution). |

## Risks

1. **ChatGPT-Lobster role confusion.** If the same model instance or person
   runs both Lobster and ChatGPT roles, the role separation collapses. The
   protocol requires two independent actors.
2. **Gate creep.** If Lobster accumulates implicit authority over iterations
   (e.g., "it already ran 5 times, just let it edit the prompt"), the
   invariant weakens. Gates must be explicitly checked each cycle.
3. **Sample narrowing death spiral.** If the sample keeps getting narrower
   (NARROW → NARROW → NARROW) without ever reaching a concrete fix, the loop
   spends budget without progress. The stop condition for consecutive
   narrow-without-convergence guards against this.
4. **Escalation fatigue.** If every cycle escalates to the user, the protocol
   is adding overhead without value. If this happens, the loop target is too
   vague (see the concrete fix target invariant).

## Next stop point

This protocol is now documented. The next stop point is:

1. **Report** (this document) — delivered to the user for review
2. **User approval** — the user reviews the protocol and either approves it,
   requests changes, or rejects it
3. **First real cycle** — if approved, the first Lobster-mediated quality loop
   can begin with the current quality sample and baseline
