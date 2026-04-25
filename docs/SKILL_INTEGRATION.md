# Skill Integration

This document explains how `novel-translation-workbench` relates to the
`fishhead-literary-translator` skill framework.

## Framework relationship

This repository is a **workbench implementation** of the
`fishhead-literary-translator` framework.

The framework is the reusable literary-translation production framework.
This repo is one running implementation of it. It is not the framework
itself, and the framework's standards take precedence when they
disagree.

The framework lives at:

```
~/.claude/skills/fishhead-literary-translator/
├── SKILL.md
├── shared/
│   └── WORKFLOW.md
├── WORKBENCH_PROTOCOL.md
├── BOOK_ASSETS_SPEC.md
└── directions/
    └── zh_to_en/
        ├── STYLE_RULES.md
        └── roles/
            ├── translator.md
            └── reviewer.md
```

## Active direction

The currently active direction profile is **`zh_to_en`** — Chinese to
English literary translation.

This direction profile was migrated from the previous
`fishhead-novel-translator` skill, which is now folded in as
`directions/zh_to_en/` under the framework.

## Role mapping

The framework defines two internal roles per direction profile:

| Framework role | What it does | Local prompt | Framework prompt |
|---|---|---|---|
| **A — literary translator** | Generates the full target-language prose draft. | `prompts/prompt_a.md` | `directions/zh_to_en/roles/translator.md` |
| **B — quality gate / reviewer** | Reviews A's output, identifies the single biggest issue, recommends a focused fix. | `prompts/prompt_b.md` | `directions/zh_to_en/roles/reviewer.md` |

A and B are **internal roles of the direction profile**. They are not
separately invocable skills, and they are not external prompts the user
chooses between. They are activated automatically by the shared workflow.

The local `prompts/prompt_a.md` and `prompts/prompt_b.md` files are this
workbench's executable copies of those role prompts. They must remain
aligned with the framework versions.

## Shared workflow

The framework's shared workflow is:

```
A → B → revise once if needed → final
```

Specifically:

1. Read book assets when relevant.
2. **A** generates a final-quality target-language prose draft.
3. **B** runs one internal review pass and identifies the biggest issue.
4. If B finds a major issue, A revises **once** using only the key review
   findings.
5. Return the revised prose as the default user-facing result.

Defaults:

- at most one internal review pass
- at most one internal revision pass
- no endless self-edit loop
- no exposed internal review notes by default

See `~/.claude/skills/fishhead-literary-translator/shared/WORKFLOW.md`
for the canonical definition.

## Workbench protocol coverage

This workbench is responsible for the operational contract defined in
the framework's `WORKBENCH_PROTOCOL.md`.

The protocol covers:

- **Chapter-level operation** — accept a full chapter, segment it, run
  the shared workflow per segment, aggregate, run a consistency pass,
  emit a single canonical chapter output.
- **Dry-run** — expose planned segmentation and execution intent without
  consuming the full translation budget or writing final output.
- **No-clobber** — do not silently overwrite an existing chapter output;
  require an explicit flag or confirmation to overwrite.
- **Resume** — maintain a per-chapter run record (manifest), persist
  per-segment progress, and reuse completed segments on resume.
- **Progress reporting** — show per-segment status while the run
  advances, without requiring debug logs.
- **Run summary** — produce a concise, honest summary that distinguishes
  complete vs partial runs, reports segment counts, indicates whether
  the consistency pass ran, names the output type (aggregated vs
  corrected), reports elapsed time, and points to the output file and
  run record.
- **Output traceability** — emit a final output file and a run record
  alongside it so any run can be inspected, resumed, or re-run.
- **Book asset updates** — make book-level memory readable to roles A
  and B, and support updating book assets after a chapter or meaningful
  passage.

For frozen design decisions (e.g. `chapter stream --dry-run`) and other
implementation details, see `CLAUDE.md` and `ORCHESTRATION.md`.

## Book assets are not skill files

The `project_assets/` directory holds **book-specific** translation
memory:

- `characters.md`
- `titles_and_terms.md`
- `glossary.md`
- `style_notes.md`
- `unresolved_decisions.md`

These are book-level memory, not reusable skill files. They MUST NOT be
promoted into the framework, into a direction profile, or into the
workbench's reusable prompt layer. If a recurring rule emerges across
books, harden it into the appropriate framework or direction-level
document instead.

See `BOOK_ASSETS_SPEC.md` in the framework for the canonical book-asset
spec.

## Backend and model choices are implementation details

This repo's backend, model, and service-shape choices (local vs remote
inference, mock backend, FastAPI service, CLI entry points, etc.) are
implementation details of this workbench.

They do not change the framework's standards. The framework expects:

- the same workflow standard regardless of backend
- backend choice to be real and consequential (it affects quality, speed,
  and cost) but not part of the framework identity
- future tuning aimed at reducing backend-related quality variance

A different workbench could use a completely different backend and still
satisfy the same framework.

## Future directions

Additional translation directions (for example, `en_to_zh`) should be
added as **new direction profiles** under the framework, not by
duplicating the workbench:

```
directions/
├── zh_to_en/
│   ├── STYLE_RULES.md
│   └── roles/
│       ├── translator.md
│       └── reviewer.md
└── en_to_zh/                # future, not yet implemented
    ├── STYLE_RULES.md
    └── roles/
        ├── translator.md
        └── reviewer.md
```

Do not duplicate the framework, the shared workflow, or the workbench
repository per direction. The workbench is direction-aware via the
active direction profile; new directions slot in alongside `zh_to_en/`.

## Versioned Snapshot

The skill framework lives outside this repo, at the canonical runtime
path. Because that path is not version-controlled by the workbench, this
repo also keeps a **versioned snapshot** of the framework files, used as
a backup and review copy.

Paths:

- **Canonical runtime skill path** (authoritative, executed by Claude
  Code):

  ```
  ~/.claude/skills/fishhead-literary-translator/
  ```

- **Repo snapshot path** (versioned backup and review copy, lives in
  this repo):

  ```
  docs/skill_snapshot/fishhead-literary-translator/
  ```

Rules:

- Claude Code MUST use the canonical runtime skill path when executing
  the skill. The snapshot is not on the runtime load path.
- The repo snapshot is a **versioned backup and review copy** so that
  framework changes have a diffable history alongside the workbench.
- The snapshot is **not** a second independent source of truth. The
  canonical runtime path remains authoritative.
- If the canonical skill files and the repo snapshot diverge, do **not**
  silently auto-merge. Report the divergence and sync intentionally,
  preserving the canonical path as the source of truth.

## Rule priority

When framework, workbench, and prompt files disagree, the framework
wins:

```
SKILL.md
  > shared/WORKFLOW.md
  > WORKBENCH_PROTOCOL.md
  > directions/<direction>/STYLE_RULES.md
  > directions/<direction>/roles/
  > workbench implementation (this repo)
```

The workbench is the lowest-priority layer. If this repo's runtime
behavior disagrees with the framework, the framework wins and this repo
is what needs to change.
