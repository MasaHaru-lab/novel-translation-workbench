# Shared Workflow — fishhead-literary-translator

This is the framework's shared default workflow. It is direction-agnostic
and applies to every direction profile under `directions/`.

It is migrated from `novel-translation-workbench/WORKFLOW.md`. Direction
profiles supply their own role prompts (A = literary translator,
B = quality gate / reviewer); the workflow itself is the same across
directions.

## Governing relationship

This workflow is the execution protocol for the standards defined in
`../SKILL.md`.

`SKILL.md` defines the framework's translation quality bar, scope
boundaries, and the boundaries between framework, workbench, direction
profile, and book assets.

`shared/WORKFLOW.md` defines how those standards are carried out in the
default product behavior.

Direction-specific style rules live in
`../directions/<direction>/STYLE_RULES.md` and must be enforced by both A
and B.

If there is ever a conflict, follow:

`SKILL.md` > `shared/WORKFLOW.md` > `WORKBENCH_PROTOCOL.md` >
`directions/<direction>/STYLE_RULES.md` > `directions/<direction>/roles/`
> workbench implementation

## Purpose

The framework's default behavior is not simple one-pass translation.

When the user provides source text and asks to translate, the system
should automatically run the internal translation workflow, enforce the
standards defined in `SKILL.md` and the active direction's
`STYLE_RULES.md`, and return a final, self-reviewed result in the target
language.

The user should not need to manually choose between drafting, polishing,
or review steps in the normal path.

## Chapter-level orchestration context

This workflow is invoked per segment by a workbench's chapter-level
orchestrator. The orchestrator handles full-chapter segmentation,
strategy planning, execution coordination, aggregation, and consistency
passes.

For chapter-level translation, the orchestrator calls this segment-level
workflow for each segment, then combines the results into a complete
chapter output.

See `../WORKBENCH_PROTOCOL.md` for the workbench-level operational
contract.

## Default user action

The following user actions should all trigger the same default workflow:

* pasting source text and clicking Translate
* entering a command such as `start translating`
* any equivalent instruction that clearly requests translation

Default meaning of "translate":

> generate final prose, internally review it once, revise if needed, and
> return the final result

## Default workflow

**Step 0: Read book assets when relevant**

Before drafting, check whether the passage belongs to an ongoing work
with existing book assets.

When relevant, read:

- characters
- titles_and_terms
- glossary
- style_notes
- unresolved_decisions

(See `../BOOK_ASSETS_SPEC.md` for the canonical asset list and roles.)

Use these files to maintain consistency, style control, and awareness of
still-unresolved choices.

**Step 1: Draft generation (role A)**

Use the direction's A role (literary translator) to generate the initial
target-language prose.

This draft should already aim at final-quality prose, not rough scratch
output.

Role A's prompt definition lives at
`../directions/<direction>/roles/translator.md`.

**Step 2: Internal review (role B)**

Immediately run one internal B-role review pass on the generated prose.

The review should identify the single biggest problem first, not produce
a long essay.

Role B's prompt definition lives at
`../directions/<direction>/roles/reviewer.md`.

**Step 3: One revision pass if needed**

If B finds a major issue, revise the prose once using only the key
review findings.

The revision must remain within A's house style and must not become
overworked.

**Step 4: Return final output**

Return the revised prose as the default user-facing result.

Do not expose the full internal review notes by default.

At most, provide a very short note about the single biggest issue
corrected, only if useful.

## Loop limit

The default workflow must be bounded.

Rules:

* run at most one internal review pass
* run at most one internal revision pass
* do not enter an endless self-edit loop
* do not silently keep rewriting until style changes too much

Default loop:

```
A → B → revise once if needed → final output
```

Not:

```
A → B → A → B → A → B … indefinitely
```

## Roles

### A — Literary translator

A operates within the constraints and style rules defined in `SKILL.md`
and the active direction's `STYLE_RULES.md`.

A is responsible for:

* translation
* polishing
* final prose generation
* preserving house style

A controls:

* source-language naming / forms of address
* hierarchy and institutional texture
* term stability
* anti-Westernization (when relevant to the direction)
* anti-over-explanation
* anti-literary-overperformance
* reasoning clarity
* controlled tone

### B — Quality gate / reviewer

B reviews against the standards and constraints defined in `SKILL.md`
and the active direction's `STYLE_RULES.md`, not merely against generic
fluency.

B is responsible for:

* review
* enforcement
* detecting drift
* catching the biggest style or fidelity problem

B does not exist to freewrite or redraft everything from scratch.

It functions as a reviewer gate, not as a second creative translator.

## Default output behavior

By default, the user should receive:

* the final target-language prose
* not the internal draft
* not the full review checklist
* not long meta commentary
* not engineering/debug information

The default user experience should feel like:

```
paste source → click translate → get final reviewed prose
```

## Override behavior

If the user explicitly asks for a different mode, allow overrides.

* **If the user asks for "translate only"**
  Use A only.
  Skip the internal B review pass.

* **If the user asks for "review mode", "audit", or "style check"**
  Use B explicitly and expose review findings.

* **If the user asks for raw draft**
  Return the A output before internal review.

* **If the user asks for deeper revision**
  Allow additional review-revision loops, but only when explicitly
  requested.

## Rule hardening behavior

If the same type of problem repeats across multiple passages:

* do not keep patching each passage endlessly
* convert the repeated issue into a new hard rule for the direction's
  `STYLE_RULES.md` (and, if needed, role A's prompt)

Improvement happens by strengthening house-style rules, not by infinite
micro-editing.

## Product intent

In the final product, "Translate" should mean:

> run the framework's default internal translation workflow and return
> the final reviewed prose

The workflow should be built into the product behavior, not left as a
manual operator habit.
