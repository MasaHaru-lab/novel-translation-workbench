# novel-translation-workbench Default Translation Protocol

## Governing relationship

This workflow is the execution protocol for the standards defined in `SKILL.md`.

`SKILL.md` defines the project’s translation quality bar, scope boundaries, style rules, consistency rules, and project-memory expectations.

`WORKFLOW.md` defines how those standards are carried out in the default product behavior.

If there is ever a conflict, follow:

`SKILL.md` > `WORKFLOW.md`

## Routing Architecture

This project uses multiple guidance layers. This section clarifies when each applies, so future agents can distinguish workflow-level guidance, skill-level guidance, CLAUDE.md rules, and ad hoc prompts.

### Layer map

| Layer | Document | Responsibility |
|-------|----------|----------------|
| Skill routing | `CLAUDE.md` routing table | Maps user intent to the correct skill or tool |
| Framework standard | `SKILL.md` | Quality bar, scope, style rules, project-memory expectations |
| Execution protocol | `WORKFLOW.md` (this document) | Step order, prompt roles, loop limits, override modes |
| Role prompts | `prompts/prompt_a.md`, `prompts/prompt_b.md` | Draft (A) and review (B) instructions per passage |
| Book assets | `project_assets/*` | Book-level name, term, and style specifics |
| Ad hoc instruction | User's current message | Passage-level adjustments not yet in permanent rules |

### Decision flow for "translate"

1. CLAUDE.md routing table → `fishhead-literary-translator` skill
2. Skill's SKILL.md → framework standards and scope
3. This WORKFLOW.md → execution protocol (Steps 0–4, A→B→revise→output)
4. Book assets (`project_assets/`) → context for Step 0
5. Role prompts (`prompts/prompt_a.md`, `prompts/prompt_b.md`) → draft and review
6. User's ad hoc instructions → passage adjustments within the workflow

### Priority when layers conflict

Two priority rules apply. The correct one depends on what kind of question is being decided.

**General governance priority** — for structural questions (who defines the workflow, quality bar, execution protocol, loop limits):

**SKILL.md > WORKFLOW.md > book assets > role prompts > ad hoc instructions**

**Explicit book-specific memory priority** — for concrete facts about this book (character names, titles, forms of address, glossary entries, established style notes):

**`project_assets/*` entries are authoritative for this book's established facts.** A general rule in SKILL.md or WORKFLOW.md does not override an explicit book-asset entry. Treat book assets as ground truth for this book's names, titles, relationships, glossary terms, and style memory.

If a general style rule (SKILL.md) and a book-specific entry (project_assets/*) disagree about a concrete fact — for example, a character name, a title rendering, or a glossary term — the book asset wins for that book. The general rule still applies to everything the book assets do not address.

Ad hoc instructions are legitimate for one passage but do not permanently override any layer above. Repeated corrections should be hardened into permanent rules (style notes or prompt edits) rather than applied as one-off patches.

### What each layer is not

| Layer | Is not responsible for |
|-------|----------------------|
| CLAUDE.md rules | Translation standards, workflow steps, or style enforcement |
| SKILL.md | Execution order, loop limits, or prompt role boundaries |
| WORKFLOW.md | Direction-specific style rules, quality bar, or prompt wording |
| Ad hoc instructions | Permanent rule changes; they apply only to the current passage |

## Purpose

This project’s default behavior is not simple one-pass translation.

When the user provides Chinese source text and asks to translate, the system should automatically run the project’s internal translation workflow, enforce the standards defined in `SKILL.md`, and return a final, self-reviewed English result.

The user should not need to manually choose between drafting, polishing, or review steps in the normal path.

## Chapter-level orchestration context

This workflow is invoked per segment by the chapter-level orchestrator (`app/chapter/orchestrator.py`). The orchestrator handles full-chapter segmentation, strategy planning, execution coordination, aggregation, and consistency passes.

For chapter-level translation, the orchestrator calls this segment-level workflow for each segment, then combines the results into a complete chapter output.

## Default user action

The following user actions should all trigger the same default workflow:

* pasting Chinese source text and clicking Translate
* entering a command such as `start translating`
* any equivalent instruction that clearly requests translation

Default meaning of “translate” in this project:

> generate final prose, internally review it once, revise if needed, and return the final result

## Default workflow

**Step 0: Read project assets when relevant**

Before drafting, check whether the passage belongs to an ongoing work with existing project assets.

When relevant, read:

- `project_assets/characters.md`
- `project_assets/titles_and_terms.md`
- `project_assets/glossary.md`
- `project_assets/style_notes.md`
- `project_assets/unresolved_decisions.md`

Use these files to maintain consistency, style control, and awareness of still-unresolved choices.

**Step 1: Draft generation**

Use Prompt A to generate the initial English prose.

This draft should already aim at final-quality prose, not rough scratch output.

**Step 2: Internal review**

Immediately run one internal Prompt B review pass on the generated prose.

The review should identify the single biggest problem first, not produce a long essay.

**Step 3: One revision pass if needed**

If Prompt B finds a major issue, revise the prose once using only the key review findings.

The revision must remain within Prompt A house style and must not become overworked.

**Step 4: Return final output**

Return the revised prose as the default user-facing result.

Do not expose the full internal review notes by default.

At most, provide a very short note about the single biggest issue corrected, only if useful.

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

## Prompt roles

Prompt file locations:

- Prompt A: `prompts/prompt_a.md`
- Prompt B: `prompts/prompt_b.md`

These files are the executable prompt-layer implementation of the roles defined in this workflow.

They must remain aligned with `SKILL.md`.

### Prompt A

Prompt A must operate within the constraints and style rules defined in `SKILL.md`.

Prompt A is responsible for:

* translation
* polishing
* final prose generation
* preserving house style

Prompt A controls:

* Chinese naming / forms of address
* hierarchy and institutional texture
* term stability
* anti-Westernization
* anti-over-explanation
* anti-literary-overperformance
* reasoning clarity
* controlled tone

### Prompt B

Prompt B must review against the standards and constraints defined in `SKILL.md`, not merely against generic fluency.

Prompt B is responsible for:

* review
* enforcement
* detecting drift
* catching the biggest style or fidelity problem

Prompt B does not exist to freewrite or redraft everything from scratch.

It should function as a reviewer gate, not as a second creative translator.

## Default output behavior

By default, the user should receive:

* the final English prose
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

* **If the user asks for “translate only”**  
  Use Prompt A only.  
  Skip the internal Prompt B review pass.

* **If the user asks for “review mode”, “audit”, or “style check”**  
  Use Prompt B explicitly and expose review findings.

* **If the user asks for raw draft**  
  Return the Prompt A output before internal review.

* **If the user asks for deeper revision**  
  Allow additional review-revision loops, but only when explicitly requested.

## Rule hardening behavior

If the same type of problem repeats across multiple passages:

* do not keep patching each passage endlessly
* convert the repeated issue into a new hard rule for Prompt A

This project should improve by strengthening house style rules, not by infinite micro-editing.

## Product intent

In the final product, “Translate” should mean:

> run the project’s default internal translation workflow and return the final reviewed prose

The workflow should be built into the product behavior, not left as a manual operator habit.