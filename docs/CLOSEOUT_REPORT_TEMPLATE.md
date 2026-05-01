# Batch Closeout Report

Copy this template into the batch summary output at the end of every batch.
Supports both **feature** batches (implementation + verification) and **review-only** batches (review + merge, no new implementation).

---

## Batch Info

- **Branch:** `work/<topic>`
- **HEAD:** `<commit-sha>`
- **Type:** `feature` / `review+merge` / `docs-only`

## Changed Files

| File | Summary |
|------|---------|
| `path/to/file` | one sentence per file |

## Acceptance

- [✓/✗] **Goal:** restate the batch goal — is it met?
- [✓/✗] **Boundary:** was any boundary tested, approached, or respected?
- [✓/✗] **Stop point:** was the defined stop point reached?

## Verification

- **Tests:** PASS / FAIL / SKIPPED (reason)
- **Pre-merge gate:** PASS / FAIL / SKIPPED (reason)
- **Working tree:** CLEAN / DIRTY (details)

## Impact

- **Runtime behavior changed:** YES / NO (if yes, what and why)
- **Risks / limitations:** one sentence per item, max 3
- **Scope boundaries approached:** if any, how handled
