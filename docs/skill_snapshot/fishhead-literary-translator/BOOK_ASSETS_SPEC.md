# Book Assets Spec — fishhead-literary-translator

This document defines the canonical book-asset model used by the
`fishhead-literary-translator` framework.

Book assets are **book-specific translation memory**, not reusable
framework files. They live inside a workbench (next to the book's
chapters and outputs), not inside the framework or any direction profile.

It is migrated from the existing `novel-translation-workbench/project_assets/README.md`
conventions and from the corresponding sections of the previous
`fishhead-novel-translator` skill.

## Purpose

For each new book, story, or article, gradually build and maintain
project-level translation memory and consistency assets.

These assets exist so that:

- names, titles, and terminology stay stable across chapters
- prose standards, tone, and register stay consistent
- unstable or risky decisions are not silently treated as final
- each chapter strengthens later consistency rather than restarting from
  zero

This work is cumulative.

## Canonical asset files

A book's assets live in the workbench under a per-book directory (in the
current implementation, `project_assets/`).

The canonical file roles are:

- **`characters.md`** — recurring character names and identity-stable
  renderings.

- **`titles_and_terms.md`** — titles, forms of address, ranks,
  institutions, household-status terms, and other system-level
  terminology.

- **`glossary.md`** — recurring high-risk expressions, metaphysical
  language, ritual language, and other important repeated phrases that
  are not primarily title-system items.

- **`style_notes.md`** — prose standards, tone control, register
  guidance, dialogue / narration handling, and revision discipline.

- **`unresolved_decisions.md`** — unstable or risky choices that should
  not be silently treated as final.

A workbench may keep additional book-specific files alongside these (for
example, chapter-by-chapter translation logs), but the five files above
are the canonical book-asset surface that the framework, the shared
workflow, and direction profiles refer to.

## Update rule

After each meaningful passage or chapter:

1. add newly stabilized names or terms to the appropriate file
2. record any still-unstable decisions in `unresolved_decisions.md`
3. strengthen consistency rather than restarting from zero

Do not treat glossary or character lists as static-only. Generate and
update them during translation as new recurring names, terms, titles, or
fixed expressions emerge.

## Read priority

When these files are used together to inform a translation pass, follow
this order:

1. source text
2. `characters.md`
3. `titles_and_terms.md`
4. `glossary.md`
5. `style_notes.md`
6. `unresolved_decisions.md` as cautionary reference

## Boundary: book assets are not framework files

Book assets are book-specific memory.

They MUST NOT be promoted into:

- the framework (`SKILL.md`, `shared/WORKFLOW.md`, `WORKBENCH_PROTOCOL.md`)
- any direction profile (`directions/<direction>/STYLE_RULES.md`,
  `directions/<direction>/roles/`)
- the workbench's reusable code or prompts

Do not let one book's glossary, character list, or style notes leak into
the framework or a direction profile. If a recurring problem across many
books reveals a general rule, harden that rule into the appropriate
framework or direction-level document instead of into a single book's
assets.

## Workbench responsibility

The workbench is responsible for:

- reading the relevant book assets before drafting (when they exist)
- making them available to role A and role B during the shared workflow
- supporting (or facilitating) updates to book assets after each chapter
  or meaningful passage
- keeping book assets distinct from framework, direction, and workbench
  files

See `WORKBENCH_PROTOCOL.md` for the full workbench operational contract.
