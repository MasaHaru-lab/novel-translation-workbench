# Workbench Protocol — fishhead-literary-translator

A "workbench" is a running implementation of the
`fishhead-literary-translator` framework. It executes the shared
workflow at chapter scale, manages book assets, and produces traceable
output files.

This document defines the operational contract a workbench must satisfy.
It is migrated from the existing operator-level rules already in use by
`novel-translation-workbench` (`README.md`, `CLAUDE.md`,
`ORCHESTRATION.md`, `INTEGRATION.md`). It is intentionally protocol-level
and does not bind to specific code paths, CLI flag names, or storage
formats.

The current implementation is `novel-translation-workbench`. It is the
current implementation of the framework, not the framework itself.
Future workbench implementations are allowed; they must satisfy the same
protocol.

## Governing relationship

Rule priority for any workbench:

```
SKILL.md
  > shared/WORKFLOW.md
  > WORKBENCH_PROTOCOL.md
  > directions/<direction>/STYLE_RULES.md
  > directions/<direction>/roles/
  > workbench implementation
```

If a workbench's runtime behavior disagrees with the framework, the
framework wins and the workbench is what needs to change.

## Chapter-level operation

The default unit of work is **a full chapter**, not a single segment.

The workbench must:

- accept a full chapter as input
- segment the chapter into executable units (e.g. ~800–1200 source
  characters, paragraph-aligned)
- run the segment-level shared workflow (A → B → revise once → final)
  for each segment
- aggregate segment results into a flowing full-chapter output
- run a consistency pass (name / title / term variant correction) over
  the aggregated chapter
- produce a single canonical chapter-level output

Chapter-level operation is the preferred path. Manual segment-by-segment
operation is a legacy / fallback mode, not the product direction.

## Default execution path

For a typical chapter:

1. Read book assets (see `BOOK_ASSETS_SPEC.md`) when relevant
2. Plan / segment the chapter
3. Execute each segment via the shared workflow
4. Aggregate segment outputs into a full chapter
5. Run the consistency pass over the aggregate
6. Write the final output and a run record

## Dry-run

The workbench should provide a dry-run capability that:

- exposes the planned segmentation and execution intent
- does not write final translation output
- does not consume the full translation budget
- is safe to run before a real translation pass

Dry-run is a planning aid. It is not required to fully simulate every
runtime decision.

When a dry-run feature is intentionally deferred for a particular code
path (for example, due to a stdout/stderr contract decision on a
streaming subcommand), that deferral must be explicit and out of scope
until reopened.

## No-clobber output protection

The workbench must not silently overwrite an existing chapter output
file. A user-facing flag or explicit confirmation is required to
overwrite.

This applies to:

- the chapter output file
- any persistent run artifacts the user may rely on

The intent is that an accidental rerun should not erase previous output.

## Resume

A workbench must support resumable runs:

- maintain a run record (manifest) alongside the chapter output, with
  per-segment state (completed / failed / pending)
- on resume, reuse completed segments
- re-attempt pending and failed segments, subject to bounded retry
- persist progress after each segment so an interruption is recoverable

Resume is what makes long chapter runs practical. It must be the default
shape of execution, not a special flag-only mode.

## Progress reporting

While running, the workbench should provide visible progress:

- per-segment status as it advances
- enough information for the user to understand what is happening
  without enabling debug logs

Progress is operator-facing, not reader-facing.

## Run summary

After a chapter run, the workbench must produce a concise summary that
includes at least:

- whether the run is complete or partial
- segment counts (e.g. `partial — 2/5 segments`)
- whether the consistency pass ran
- whether output is pre-consistency aggregated text or post-consistency
  corrected text
- elapsed time
- the path of the final output and the run record (when applicable)

The summary is the user's primary signal of run state. It must be
honest: a partial run must be labeled partial.

## Output traceability

Each chapter run must produce traceable output:

- a final output file (preferred: post-consistency corrected text)
- a run record (manifest) capturing per-segment progress and run
  metadata
- both files alongside each other so the run can be inspected, resumed,
  or re-run

Output artifact terms used by the workbench:

- **Aggregated** — raw concatenation of all segment translations
  (pre-consistency).
- **Corrected** — aggregated text with consistency fixes applied. This
  is the best usable output when available.
- **Partial** — only successfully translated segments are included; the
  run summary states the count.

When some segments fail, the output file must still contain whatever was
completed, labeled partial in the summary.

## Book asset updates

The workbench is the place where book assets are read and updated.

After a chapter or meaningful passage, the workbench (or its operator)
must be able to update book-level memory:

- glossary
- character / place / title reference list
- style notes
- unresolved / risky decisions

See `BOOK_ASSETS_SPEC.md` for the canonical spec.

This is cumulative work. Each chapter should strengthen the consistency
of later chapters rather than restart from zero.

## What a workbench MUST NOT do

- silently overwrite chapter output
- drop progress on interruption
- emit final output without a run summary
- promote book-specific content (a book's glossary, characters, style
  notes) into the framework or the direction profile
- bake a particular backend, model, or hardware choice into the
  framework standard
- expose internal review notes by default

## What a workbench MAY do

- choose its own backend (local inference, remote inference, hybrid)
- choose its own service shape (CLI, HTTP, library, web UI)
- add additional run modes (stream, resume-only, audit-only) on top of
  the protocol
- extend the run summary or manifest with implementation-specific fields

Backend, model, and storage details are implementation details. They do
not change the workflow standard.

## Internal-only parameters

Some parameters are internal to the workbench's orchestration and are
not user-configurable through the default product surface (for example,
budget configuration, consistency intensity, asset injection mode).

Internal parameters:

- must be resolved by the workbench, not asked of the user
- must not leak into the default user surface
- may be overridable by an explicit advanced / debug interface

This keeps the default user experience focused on:

```
provide source → translate → get final reviewed prose
```

## Failure isolation

Within a chapter run:

- a single segment failure must not abort the entire chapter
- the run record must mark which segments failed
- the run must continue and report partial completion honestly

Aggregate-level failures (e.g. consistency pass failure) must also be
reported honestly in the run summary, without faking completeness.

## Conservative recording

When the workbench records run metadata:

- do not guess unknown values
- do not back-fill planned values from actual values, or vice versa
- planned and enacted values must remain distinguishable

This preserves the integrity of the run record so that issues can be
diagnosed later.
