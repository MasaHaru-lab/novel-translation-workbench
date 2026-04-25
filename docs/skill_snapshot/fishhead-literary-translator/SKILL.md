---
name: fishhead-literary-translator
description: Reusable literary translation production framework for long-form narrative prose. Direction-agnostic; the first implemented direction profile is zh_to_en. Use when translating book-length or chapter-length literary fiction with project-level memory and a quality gate.
---

# fishhead-literary-translator

`fishhead-literary-translator` is a reusable literary translation
production framework for long-form narrative text.

It is the framework. The translation direction (source language → target
language) is supplied by a direction profile under `directions/`. The
first implemented direction profile is `zh_to_en`. Future directions such
as `en_to_zh` will be added as additional direction profiles under the
same framework.

This framework was migrated from the earlier
`fishhead-novel-translator` skill, which is now folded in as the
`zh_to_en` direction profile.

## Why this exists

Much of the literature the user wants to share with their child is not
available in professional translation. Current large-model translation
still often falls short in literary quality, tonal control, readability,
consistency, and narrative appeal. The goal is not merely to make the
text understandable in the target language, but to produce prose that is
natural and compelling enough that the reader genuinely wants to keep
reading.

Do not produce bland competence. Produce real prose.

## Core operating principle

When the user asks to translate, do not interpret that as "produce a
rough first pass."

Interpret "translate" as:

1. produce a full target-language prose draft
2. internally review the draft
3. revise once if needed
4. return the polished final translation

The default output should be reader-facing prose, not process commentary.

See `shared/WORKFLOW.md` for the canonical workflow definition.

## Internal roles (per direction)

Each direction profile carries two internal roles:

- **A — literary translator.** Produces the full target-language prose
  draft. Aimed at final-quality prose, not rough scratch.
- **B — quality gate / reviewer.** Reviews A's output against the
  framework standard and the direction's style rules. Identifies the
  single biggest problem rather than re-drafting.

A and B are internal roles of the direction profile. They are not
standalone external prompts, and they are not separately invocable
skills. Their prompt-level definitions live under
`directions/<direction>/roles/translator.md` and
`directions/<direction>/roles/reviewer.md`.

## Direction profiles

A direction profile defines:

- direction-specific style and fidelity rules (`STYLE_RULES.md`)
- the A and B role prompt definitions (`roles/translator.md`,
  `roles/reviewer.md`)

Currently active:

- `directions/zh_to_en/` — Chinese-to-English literary translation
  (migrated from the prior `fishhead-novel-translator` skill)

Reserved as future placeholder (not implemented):

- `directions/en_to_zh/` — see `directions/en_to_zh/README_FUTURE.md`

When a new direction is added, add it as a new direction profile under
`directions/`. Do not duplicate the framework, the shared workflow, or
the workbench. Do not duplicate the workbench repository per direction.

## Workbench protocol

A workbench is the running implementation of this framework. It executes
chapter-level translation, manages book assets, and produces traceable
output files. See `WORKBENCH_PROTOCOL.md` for the operational contract a
workbench must satisfy: chapter-level operation, dry-run, no-clobber
output protection, resume, progress reporting, run summary, output
traceability, and book asset updates.

The current implementation is the `novel-translation-workbench`
repository. It is the current implementation of the framework, not the
framework itself.

## Book assets (project-level memory)

For each new book, story, or article, gradually build and maintain
project-level translation assets.

These assets may include:

- glossary
- character / place / title reference list
- style notes
- unresolved / risky decision list

Do not treat glossary as static only. Generate and update it during
translation as new recurring names, terms, titles, or fixed expressions
emerge. Each chapter should strengthen the consistency of later
chapters.

Book assets are book-specific memory, not reusable skill files. Do not
promote per-book content into the framework. See `BOOK_ASSETS_SPEC.md`
for the canonical spec.

## Non-goals

This framework does not:

- scrape or fetch source text automatically
- judge copyright status or source legality
- train or fine-tune models inside the skill itself
- replace final human editorial judgment
- default to visible step-by-step translation notes unless the user
  explicitly asks for them

Treat output as a high-quality professional translation candidate, not as
unquestionable final authority.

## Rule priority (when documents conflict)

```
SKILL.md
  > shared/WORKFLOW.md
  > WORKBENCH_PROTOCOL.md
  > directions/<direction>/STYLE_RULES.md
  > directions/<direction>/roles/
  > workbench implementation
```

The workbench is the lowest-priority layer. If a workbench's runtime
behavior disagrees with the framework, the framework wins and the
workbench is what needs to change.

## Backend and implementation boundary

This framework is defined at the level of workflow, standards, and
project-memory behavior, not at the level of any one machine or model.

Do not define the framework around a specific hardware setup.

Fishhead, a 3090 GPU, local inference, remote inference, or hybrid
backend arrangements are all implementation options, not the identity of
the framework.

Different backends may affect quality, speed, and cost. Assume that
backend choice is real and consequential. The workflow standard should
remain the same, while future tuning and system design should aim to
reduce backend-related quality variance as much as possible.

## Validation standard

This framework is considered valid when its:

- purpose
- boundaries
- input/output behavior
- shared workflow
- workbench protocol
- book-asset model
- at least one working direction profile (currently `zh_to_en`)

are clearly defined and usable.

The following are later-stage improvements, not prerequisites for the
framework itself:

- final backend optimization
- model-specific tuning
- full deployment
- additional direction profiles
- perfect satisfaction with every output
- future refinement toward the user's ideal literary translator
