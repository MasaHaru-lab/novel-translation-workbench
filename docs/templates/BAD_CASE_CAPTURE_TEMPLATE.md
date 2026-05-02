# Bad-Case Capture: `<capture_name>`

**Captured:** `<YYYY-MM-DD>`
**Status:** `open` / `investigating` / `resolved`
**Owner:** `<name or team>`
**Follow-up batch:** `<batch name or link, or "TBD">`

---

## Source Reference

- **Chapter:** `<chapter_name>`
- **Source file:** `data/source/<name>.txt`
- **Output file:** `data/exports/<name>_en.md`
- **Manifest:** `data/exports/<name>_en.manifest.json`
- **Inspection record:** `data/exports/<name>_inspection.md` (if one exists)

## Problem

- **Bad output excerpt:**
  > `<quote of the problematic rendering>`
- **Expected/correct rendering:**
  > `<what it should be>`

## Issue Category

`Type A` / `Type B` / `Type C`
(See `docs/QUALITY_LOOP.md` for definitions.)

## Gate Gap

- **Why the existing quality gate missed this:**
  `<one or two sentences — which check should have caught it, and why it didn't>`
- **Desired future regression/check behavior:**
  `<one or two sentences — what a future automated check should look for, and in
    which module it would live (e.g., "reference-aware gate: entity presence check
    against project assets")>`

## Artifacts

These files are copies stored in the capture directory:

- Source copy: `data/captures/<capture_name>/source.txt`
- Output copy: `data/captures/<capture_name>/output.md`
- Manifest: `data/captures/<capture_name>/output.manifest.json`

## Operator Notes

<Free text — what went wrong, what to investigate, whether to retry.>

## Next Actions

- [ ] Investigate root cause
- [ ] Fix underlying issue before retranslating
- [ ] Delete from captures when resolved
