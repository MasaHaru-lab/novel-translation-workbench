# novel-translation-workbench

This project provides a translation workflow for Chinese novel chapters into English.

## Governing documents

This project is governed by the following document priority:

1. `SKILL.md` — highest-level translation standard, scope, style rules, consistency rules, and project-memory behavior
2. `WORKFLOW.md` — default execution workflow for this project
3. local prompt wording, adapter logic, and implementation details

If these sources ever conflict, follow:

`SKILL.md` > `WORKFLOW.md` > local implementation

## Default Translation Protocol

For normal translation requests, follow the default protocol defined in `WORKFLOW.md`, but always enforce the translation standards and constraints defined in `SKILL.md`.

**Default meaning of "translate":**
- Use Prompt A to generate initial English prose
- Run one internal Prompt B review pass
- Revise once if needed
- Return final reviewed prose

Prompt files:

- Prompt A: `prompts/prompt_a.md`
- Prompt B: `prompts/prompt_b.md`

These prompt files implement the default translation and review behavior described in `WORKFLOW.md`, and must remain aligned with `SKILL.md`.

Project assets:

- `project_assets/characters.md`
- `project_assets/titles_and_terms.md`
- `project_assets/glossary.md`
- `project_assets/style_notes.md`
- `project_assets/unresolved_decisions.md`

Before translating a passage from an ongoing work, check these project assets when relevant.

Use them to maintain name consistency, term stability, style control, and awareness of still-unresolved decisions.

## Required behavior

Unless the user explicitly requests otherwise:

- do not expose full internal review notes
- do not treat translation as a rough first pass
- do not override established glossary, naming, title, or style decisions casually
- do not add unsupported specificity for ownership, gender, emotion, or causality
- do not over-modernize dialogue or flatten historical / literary atmosphere
- do not prioritize fluency over scene logic and source meaning

## Project memory expectation

When translating a book or continuing an existing work, check and maintain project-level assets when available, including:

- glossary
- character / place / title reference list
- style notes
- unresolved decision list

Each chapter should strengthen later consistency rather than restarting from zero.

## Mode overrides

- If the user explicitly asks for `translate-only`, skip internal review
- If the user explicitly asks for `review mode`, `audit`, or `style check`, use explicit review behavior
- Otherwise, `translate` means the default full internal workflow

For workflow details, see `WORKFLOW.md`.
For translation quality bar and style constraints, see `SKILL.md`.