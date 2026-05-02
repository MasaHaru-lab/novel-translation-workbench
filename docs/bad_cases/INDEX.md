# Bad-Case Index

## Purpose

A lightweight index of captured bad translation cases. Each entry points to a
capture directory in `data/captures/` that contains the source, output,
manifest, and operator note documenting a systematic failure that passed the
automated quality gate undetected.

**This is NOT:**

- A substitute for reading a capture's full note (the index is just a door)
- A duplicate of `docs/FAILURE_PATTERN_INDEX.md` — that index holds *reusable
  patterns*; this index holds *specific instances* that may or may not become
  patterns
- A backlog tracker — captures have a status and owner; follow-up batches are
  tracked separately

## When to read this index

Before starting a quality workflow, inspection, or translation batch:

1. **Read the full index.** Check whether any captured case overlaps with the
   chapter, model backend, or passage type you are working on.
2. **If a capture is relevant**, read its operator note (`capture_note.md` in
   the capture directory) and check whether the root cause has been resolved.
3. **Do not re-discover known bad cases.** If a capture has the same symptom
   as something you just observed, expand the existing capture rather than
   creating a new one.

## Entry format

Each row links to a capture directory under `data/captures/<name>/`.

| Name | Status | Date | Issue | Gate gap | Follow-up |
|------|--------|------|-------|----------|-----------|
| `<name>` | open / investigating / resolved | YYYY-MM-DD | one-line description | one-line summary | batch or TBD |

## Index

*(This section starts empty. Entries are added as captures are created.)*
