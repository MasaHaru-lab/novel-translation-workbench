# zh_to_en — Style and Translation Rules

This document holds the direction-specific style, fidelity, and consistency
rules for Chinese-to-English literary translation under the
`fishhead-literary-translator` framework.

It is migrated from the existing `fishhead-novel-translator` skill content
(both `~/.claude/skills/Fishhead-novel-translator/SKILL.md` and
`novel-translation-workbench/SKILL.md`). The framework-level standards live
in `../../SKILL.md` and `../../shared/WORKFLOW.md`. This file holds
everything that is specific to the zh_to_en direction.

## Scope

Use this direction profile for Chinese-to-English long-form narrative
translation, especially:

- modern vernacular Chinese prose
- webnovels
- serialized fiction
- chapter translation
- scene translation
- dialogue-heavy narrative
- narration-heavy literary prose

Strongest on modern written vernacular Chinese, but may also be used for
broader long-form Chinese narrative translation into English.

Do not treat this as a general-purpose tool for poetry, legal writing,
academic prose, or business documents unless the user explicitly forces
that use.

## Primary goal

Translate Chinese prose into English that:

- preserves meaning
- preserves tone
- preserves narrative intent
- preserves character relationships and social dynamics
- preserves scene logic
- reads like real English fiction
- is engaging enough that the reader would want to continue

A technically understandable but lifeless translation is not good enough.

Aspiration: prose toward the level of a published literary translation
such as the English *Legend of the Condor Heroes* edition.

## Decision priority (zh_to_en specific)

When translation signals conflict, resolve them in this order:

**Chinese source text > existing book-level glossary / name-place-title
system > book-level style notes > local chapter context > model judgment**

Do not let model improvisation override established book-level consistency
without strong reason.

## Book-start protocol

When a new book, story, or article appears and no prior translation
context exists yet, do not treat the passage as fully isolated.

Before or during the first translation pass, begin establishing a working
project baseline:

- identify likely recurring personal names
- identify likely recurring place names
- identify titles, ranks, forms of address, and institutional terms
- identify obvious style signals in the source
- infer a provisional book-level tone baseline
- begin a provisional glossary for recurring or high-risk terms

These first-pass decisions may later be refined, but they should be made
in a disciplined way so the project does not restart from zero every
chapter.

## Critical translation constraints

### Preserve source information boundaries

Chinese narrative often omits information that English normally makes
explicit. Do not invent facts that are not supported by the source or
clearly required by the immediate context.

This includes, but is not limited to:

- ownership
- gender
- degree of emotional force
- interpersonal intention
- narrative causality
- stage business or scene choreography

Missing information in the Chinese source is not permission to specify it
in English.

### Do not invent possessives or ownership

Do not add possessives such as:

- his
- her
- their
- his own
- her own

unless ownership is explicit in the source or clearly anchored by the
immediate local context.

Preferred handling:

- preserve neutrality when ownership is not important
- use "the cup," "the teacup," or other neutral phrasing when possible
- allow light clarification only when it does not introduce a new fact

Example principle:

- acceptable: "lifted her teacup" when the action clearly belongs to the
  current female subject and refers to the cup before her
- not acceptable: "lifted his cup" when the source does not establish
  male ownership

Do not let English fluency pressure force false specificity.

### Do not over-assign gender

Chinese often omits or delays explicit gender marking. Do not assign he /
she / his / her merely because English prefers explicit subjects or
because the model predicts a default.

Only resolve gender when:

- the source establishes it
- the surrounding context already establishes it
- English absolutely requires it and the choice is well-grounded

If uncertainty remains, prefer solutions that reduce unnecessary gender
marking.

### Preserve ambiguity when the source is ambiguous

If the Chinese source is deliberately or naturally ambiguous, do not rush
to resolve that ambiguity in English unless readability truly requires
it.

The translator's job is not to over-explain the text.

When ambiguity must be narrowed for English readability, do so in the
least intrusive way.

### Natural English is allowed; unwarranted invention is not

Naturalization is part of literary translation. Invention is not.

Light clarification is allowed only when all of the following are true:

- the reference is already anchored in the immediate sentence or scene
  context
- the wording does not introduce a new narrative fact
- the change improves English readability without changing scene logic,
  tone, or narrative pressure

Do not confuse smoothness with permission to add information.

## Style instructions

### Understand the sentence before translating it

Do not translate by clinging to the surface wording of the Chinese
sentence.

First understand the underlying logic of the sentence:

- what is being stated
- what is being implied
- what is being contrasted
- what is being softened
- what is being emphasized
- what is being withheld

Then translate accordingly.

The job is to understand what the sentence is doing and render that
function naturally in English.

### Do not introduce unearned dramatic force

Never become theatrically overexpressive.

Do not add drama, attitude, emphasis, emotional force, or narrative color
that is not supported by the source.

Do not "perform" the sentence beyond what the original justifies.

The English should feel natural and alive because the sentence has been
understood correctly, not because the translator added force that was
never there.

### Sentence-level standard

When a sentence is accurate in meaning but still sounds too literal, too
stiff, or too translation-shaped, rewrite it into more natural English
prose if needed.

But stay disciplined.

Do not:

- add emotional amplification
- invent subtext
- exaggerate mood
- insert stylish phrasing for its own sake
- change scene logic
- change interpersonal force
- change narrative information

The target is controlled naturalization, not dramatic rewriting.

### Prose target

Aim for:

- published-literary naturalness as the base
- strong readability and narrative pull as the practical goal

The prose should feel mature and controlled, while still being readable
enough that a real reader wants to continue.

### Narrative vs dialogue

Narrative prose and dialogue should both sound natural in English, but
they should not be flattened into the same texture.

Narrative should be smooth, controlled, and readable as fiction prose.

Dialogue should preserve differences in:

- education level
- temperament
- attitude
- status
- relationship dynamics
- habitual speaking style

Do not make every character sound like the same neutral English-speaking
narrator.

### Register and era consistency

Do not default to highly contemporary, casual, chatty, or slangy English
if it breaks the historical, quasi-historical, or literary atmosphere of
the scene.

The most idiomatic modern English is not always the best translation.

A line may be grammatically natural and conversationally fluent, yet
still feel tonally anachronistic inside the narrative world.

When translating period, semi-historical, clan-household, court,
martial-arts, or similarly stylized settings:

- avoid present-day banter unless clearly justified
- avoid overly modern conversational shortcuts
- avoid sitcom-like lightness in high-pressure or status-sensitive scenes
- prefer controlled, neutral, slightly formal phrasing when needed to
  preserve atmosphere

Example principle:

- "What are you rushing for?" may fit a restrained literary-register
  scene better than "What's the hurry?"
- do not choose the more modern-sounding option merely because it feels
  more colloquial in present-day English

### Short dialogue lines: preserve pressure, not just wording

For short Chinese dialogue such as:

- 急什么
- 慌什么
- 怕什么
- 吵什么
- 闹什么

do not flatten them into generic English filler.

Preserve, in priority order:

1. interpersonal force
2. scene function
3. register fit
4. literal wording where possible

These lines often carry pressure, rank, impatience, containment,
dismissal, or social control far beyond their surface length.

Do not automatically replace them with the quickest modern idiom if that
weakens the character voice or damages the scene atmosphere.

### Do not over-stage action beats

Chinese prose often states simple actions cleanly:

- looked at her
- set down the cup
- raised his head
- turned to leave

Do not over-decorate these into unnecessary cinematic choreography.

Avoid adding:

- extra gestures
- invented physical emphasis
- ornamental body-language cues
- reaction beats not present in the source

Simple action should often remain simple action.

### Do not intensify or soften without basis

Do not make a line colder, warmer, sharper, crueler, more sarcastic,
more affectionate, more frightened, or more emotional unless the source
supports it.

Likewise, do not sand away pressure that the source clearly contains.

The translator must not quietly rewrite the social temperature of the
scene.

## Names, titles, and terminology

Handle proper nouns and fixed systems by type, not by one blanket rule.

As a default:

- personal names will often stay closer to pinyin or established naming
  form
- titles, ranks, forms of address, institutions, and similar functional
  terms should be translated according to narrative function,
  readability, and book-level consistency

Once a rendering is established for a given book, keep it stable wherever
possible.

If a choice later proves unsatisfactory, revise it systematically. Do not
let terms drift chapter by chapter.

Apply this consistency discipline especially to:

- personal names
- place names
- kinship terms
- honorifics
- forms of address
- official ranks and court titles
- sect / school / clan / institution names
- recurring cultural or technical vocabulary

### Address-term handling

- Do not mechanically concatenate Chinese characters into pinyin strings
  for forms of address (e.g., "Xixiao" for "小西"). Interpret the
  function of the address term — diminutive, honorific, kinship — and
  translate it appropriately, considering hierarchy, tone, and
  relationship.
- For common address prefixes such as "小" (little), "老" (old), "阿"
  (affectionate), translate their function rather than transliterating.
- Avoid both overly colloquial Westernizations (e.g., "Little Xi") and
  awkward mechanical transliteration (e.g., "Xixiao"). Prefer readable,
  hierarchy-aware English renderings that preserve the function and
  tone of the original.
- If a term is unresolved, choose conservatively and keep the passage
  readable.

## Output rules (zh_to_en defaults)

Unless the user explicitly asks otherwise:

- do not surround the translation with bullet-point explanation
- do not include visible internal review notes
- preserve paragraph flow
- format dialogue naturally
- translate chapter titles together with the chapter text
- place first-appearance proper-name notes at the end of the chapter

The translation should read like actual English prose intended for
reading, not like annotated machine output.

## Failure recovery rules

If a translation choice is accurate but dead on the page, revise for
more natural prose without adding force the original does not have.

If a term, title, or naming choice is unresolved, choose conservatively,
keep the chapter readable, and log the issue for later review.

If established book-level terminology conflicts with a tempting local
rewrite, prefer the established system unless there is a strong
source-based reason to change it.

If a character's language habits begin to drift, restore consistency
instead of polishing each line in isolation.

If the English becomes smoother at the cost of narrative logic, pull it
back. Meaning and scene logic come first.

If the prose sounds flashy but not earned by the source, remove the
performance.

If the translation has become more specific than the Chinese source
without necessity, pull it back.

If a line feels idiomatic in modern English but breaks the atmosphere of
the scene, pull it back.

## Quality bar

A good output should feel like a real novel in English, not like
language conversion.

It should remain faithful to the Chinese source in:

- meaning
- tone
- narrative intent
- character behavior
- scene logic
- interpersonal dynamics
- atmosphere

At the same time, it should be readable and appealing enough that the
reader would genuinely want to keep going.
