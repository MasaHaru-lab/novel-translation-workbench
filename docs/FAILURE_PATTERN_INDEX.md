# Failure-Pattern Index

## Purpose

A lightweight, agent-first index of reusable failure patterns that have occurred
multiple times across batches, quality runs, or translation sessions. Its only
reason to exist: to prevent the same issue from being rediscovered batch after
batch, conversation after conversation.

**This is NOT:**
- A library of every issue ever observed (that is noise)
- A migration target for old conversation logs or closeout reports
- A quality-run log (those live in `outputs/` as findings records)
- A substitute for project assets, style notes, or prompt rules

## Relationship to existing processes

| Process | What it handles | This index handles |
|---------|-----------------|-------------------|
| Quality loop (Type A/B/C) | Current-passage issues resolved into assets, style notes, or prompts | Patterns that survive resolution — things that reappear even after asset/prompt fixes |
| Canonization Gate | New asset-entry validation | Entries that passed the gate but later caused instruction leakage or naming drift |
| Closeout reports | One-batch summary of what happened | Cross-batch patterns — trends visible only across multiple closeouts |
| Real-sample validation | One-chapter workflow safety | Bottlenecks or failure modes common to real-sample pipelines |

## Capture criteria

A failure pattern qualifies for this index only when it meets **all** of:

1. **Repeatable** — observed in at least two separate runs, batches, or
   conversations (or one run with at least three occurrences in distinct
   passages).
2. **Distinct from existing coverage** — not already caught by an existing
   project asset, style note, or prompt rule. If the fix already exists, the
   pattern should be a verification gap, not a new entry.
3. **Has a clear guardrail** — there is a concrete action an agent can take
   (check X before running, verify Y after translation) that would catch or
   prevent it.
4. **Would save time** — the pattern is non-obvious enough that a future
   agent would not naturally look for it.

A pattern does NOT qualify when:
- It was a one-off (tool error, typo, configuration mistake)
- It is already captured by an existing asset, style note, or prompt rule
  (the proper fix is to improve the rule's coverage — the pattern index is
  not a second copy)
- It is a known limitation of the current model backend (check with
  `ssh -G Fishhead-Core` first)
- The root cause is already described in the pipeline contracts
  (`docs/PIPELINE_CONTRACTS.md`) or a canonical design document

## Entry format

Each entry is a single light-weight record. No multi-paragraph analysis.

```markdown
### Pattern: [short name]

**Symptom:** one sentence describing what goes wrong
**Root cause:** one sentence — what triggers the pattern
**Guardrail:** the concrete check or action that prevents rediscovery
**First seen:** where and when (batch / quality-run version / closeout report URL)
**Status:** active / mitigated / closed
```

**Status meanings:**
- **active** — the pattern is still possible; guardrail has not been implemented
- **mitigated** — a guardrail exists but is not yet proven across multiple runs
- **closed** — no longer possible (e.g. the code path was removed, or the guardrail
  has been verified across ≥3 runs with no recurrence)

## Reading protocol

When entering this project for any task involving translation, quality, or tuning:

1. **Read this index.** Scan the entries. If none match your current task, skip.
2. **If you observe a new quality failure**, also check `docs/bad_cases/INDEX.md`
   for specific captured instances — a pattern may have already been captured
   as a bad case before it earned a formal pattern index entry.
3. **If an entry matches** your current domain, read the guardrail. Apply it
   before and during your work.
4. **If you observe a new instance of an active pattern**, note it in your
   closeout report so the entry can be updated.
5. **If you observe a pattern that is not in this index** but meets the capture
   criteria, add an entry. One sentence per field. Do not write a multi-paragraph
   analysis — the closeout report is where the full record lives.

## Growth rules (anti-bloat)

- **Max 20 entries.** If the index reaches 20, no new entries may be added
  without archiving an old one. Archive candidates: closed entries first, then
  least-recently-observed active entries.
- **No multi-paragraph entries.** Each entry fits in 5 lines. Full analysis goes
  in closeout reports or findings records, which this index can reference.
- **No historical migration.** The index starts empty and grows organically from
  future observations. Do not bulk-copy old conversation logs, closeout reports,
  or quality-run findings into this index. Each entry must earn its place by
  meeting the capture criteria in a real future observation.
- **Annual sweep (or at 20-entry limit).** Review every entry. Remove any where:
  - The root cause is no longer possible (code change, prompt change)
  - The pattern has not been observed in ≥6 months
  - The guardrail has been verified across ≥5 runs with no recurrence
- **When a prompt or asset rule fully resolves a pattern**, mark the entry as
  closed. Do not keep it as active "just in case." The rule is the fix; the index
  entry is only a cross-reference.

## Index

(This section starts empty. Entries are added according to the capture criteria
and growth rules above.)
