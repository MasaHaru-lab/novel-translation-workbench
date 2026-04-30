# R1: Book Memory — Red-String Wall Foundation

> Narrative graph memory layer for long-book (1274-chapter / 2.57M-character)
> novel translation consistency.

## Purpose

The book memory layer (also called the "red-string wall") is the structured
data model that will eventually power retrieval-augmented context packs for
chapter-level translation. It stores what the project knows about entities,
relationships, titles, chapter events, and translation decisions in a
machine-queryable form.

**Source text remains the primary authority.** The graph memory is advisory
only: it accelerates retrieval and flags inconsistency but never replaces
or overrides the Chinese source.

## Data model

### Entity types (all optional, all versioned)

| Collection | Record type | Fields | Status |
|---|---|---|---|
| `entities` | `BookEntity` | id, name_zh, name_en, entity_type (CHARACTER/PLACE/FACTION/INSTITUTION), aliases, alternative_renderings, description, tags, first_chapter, last_chapter, evidence | TENTATIVE (default) / CONFIRMED / UNRESOLVED |
| `relationships` | `Relationship` | id, source_id, target_id, relation_type, description, evidence | TENTATIVE / CONFIRMED |
| `titles` | `TitleRecord` | id, name_zh, name_en, category (title/address/term), notes, evidence | TENTATIVE / CONFIRMED |
| `chapter_events` | `ChapterEvent` | chapter, title, summary, entities_involved, key_events, key_decisions | CONFIRMED (default) / TENTATIVE |
| `translation_decisions` | `TranslationDecision` | id, entity_id, decision_type (rendering/style/consistency), old_value, new_value, rationale, chapter_decided, evidence | CONFIRMED (default) / TENTATIVE |
| `unresolved_decisions` | `UnresolvedDecision` | id, question, entity_id, options, recommendation, created_chapter, evidence | UNRESOLVED (fixed) |

### Evidence trail

Every record type carries a list of `EvidenceRef` objects that pin claims
to specific source locations:

- `chapter` (int, 1-based)
- `segment` (int, optional)
- `source_excerpt` — Chinese source snippet (50-200 chars)
- `translation_excerpt` — corresponding English translation
- `notes` — free-text annotation

This ensures the graph remains auditable: any downstream consumer can
trace a "confirmed" rendering back to the chapter and passage where it
was established, and unresolved questions carry the context that raised
them.

### Status semantics

| Status | Meaning |
|---|---|
| CONFIRMED | Human-verified after translation, stable |
| TENTATIVE | Reasonable rendering, awaiting cross-chapter confirmation |
| UNRESOLVED | Open question, needs a decision |

A TENTATIVE entity means "this is what the bootstrap extracted from
project_assets, but no human has validated it after a real translation
run." Promotion to CONFIRMED happens when the entity survives a
translation chapter without needing correction.

## Storage

### Schema layer (versioned in `app/book_memory/`)

```
app/book_memory/
├── __init__.py          # Public API exports
├── models.py            # Pure dataclass definitions
├── serialization.py     # to_dict / from_dict for JSON round-trip
├── validation.py        # Record-level + cross-reference validation
├── store.py             # InMemoryBookMemoryStore + FileBookMemoryStore
└── bootstrap.py         # bootstrap_from_project_assets()
```

### Data layer (under `data/book_memory/`)

```
data/book_memory/
└── book_memory.json     # The canonical JSON file
```

`data/` is git-tracked (only `data/output/` and `data/exports/` are
gitignored). This means book memory data is versioned alongside the
codebase, so each batch commit carries the memory state at that point.

The `FileBookMemoryStore` validates on save (warn-only, non-blocking)
and writes a pretty-printed UTF-8 JSON file.

## Bootstrapping

`bootstrap_from_project_assets()` populates a `BookMemory` from the
existing `project_assets/*.md` files:

- **characters.md** → `BookEntity` records (type=CHARACTER, status=TENTATIVE)
- **titles_and_terms.md** → `TitleRecord` records (category="title")
- **glossary.md** → `TitleRecord` records (category="term")
- **unresolved_decisions.md** → `TranslationDecision` (status=TENTATIVE) + `UnresolvedDecision` records

Bootstrap decisions are always **TENTATIVE**, never CONFIRMED, because
they come from one-pass markdown parsing rather than real translation-run
validation. Promotion to CONFIRMED happens when a translation chapter
passes without needing correction.

This is a one-time or occasional import path. Once bootstrapped, the
JSON file becomes the canonical source and the project_assets markdown
files remain the human-edited originals.

## Validation

Record-level validators check:
- Required string fields (`id`, `name_zh`, `name_en`) are non-empty
- Enum fields (`entity_type`, `status`, `decision_type`, `category`)
  have valid values
- Numeric constraints (chapter >= 1, last_chapter >= first_chapter)
- Self-reference guard (relationship source != target)

Cross-reference validators check:
- Relationship `source_id` / `target_id` refer to known entity ids
- Chapter event `entities_involved` refer to known entity ids
- Translation decision `entity_id` refers to a known entity or title id

## R2: Retrieval / context pack layer (built)

The retrieval layer (`app/book_memory/retrieval.py`) is now implemented.
Given a Chinese source segment and a `BookMemory`, it returns a compact
advisory context pack suitable for Prompt A/B injection.

### Architecture

```
app/book_memory/
├── ...
└── retrieval.py          # build_context_pack() + EntityMatch, TitleMatch, ContextPack
```

### How it works

1. **Entity matching**: each entity's `name_zh` and `aliases` are checked
   as substrings in the source segment. Longer matches are prioritised as
   more specific. Places, factions, and institutions are matched identically
   to characters.

2. **Title/term matching**: each `TitleRecord.name_zh` is checked as a
   substring in the source segment.

3. **Relationship resolution**: all relationships where the matched
   entity is either source or target are included.

4. **Decision resolution**: `TranslationDecision` and `UnresolvedDecision`
   records whose `entity_id` matches a matched entity or title id are
   included.

5. **Context pack assembly**: results are packed into a `ContextPack`
   dataclass with metadata showing why each item was retrieved.

6. **Size bounding**: an estimated formatted size is calculated; if it
   exceeds `max_chars` (default 4000), items are dropped from lowest
   priority first:
   - Unresolved decisions (droppped first)
   - Translation decisions
   - Relationships
   - Tentative titles (confirmed titles kept)
   - Tentative entities (confirmed entities kept)

7. **Uncertainty preservation**: the formatted output marks each record
   with `[TENTATIVE]` or `[UNRESOLVED]` status labels. Confirmed records
   are presented as established without labels.

### ContextPack API

```python
pack = build_context_pack(source_segment, book_memory, max_chars=4000)

pack.matched_entities      # List[EntityMatch] — entity + matched_on + matched_text
pack.matched_titles        # List[TitleMatch]   — title + matched_on + matched_text
pack.related_relationships # List[Relationship]
pack.related_decisions     # List[TranslationDecision]
pack.related_unresolved    # List[UnresolvedDecision]

pack.is_empty              # True when nothing matched
pack.truncated             # True if items were dropped due to size limit
pack.total_chars           # Estimated formatted character count

pack.format_text()         # Rendered text suitable for Prompt A/B injection
```

### Prompt A/B integration (wired in R3, active since R4)

The `ContextPack.format_text()` output is designed to be injected at a
specific marker in Prompt A:

```
## Context Pack (retrieved from book memory)
...formatted output...

## Translation Instructions
...existing instructions follow...
```

For Prompt B (review), the same pack can be included to verify
consistency against known renderings and decisions.

### CLI integration (R3/R4)

The retrieval layer is **wired into the chapter-level translation
pipeline**. Context packs are built and injected per segment when
`--book-memory` is passed to a chapter subcommand.

The context pack text is assembled by the orchestrator and forwarded
to `run_with_manifest()`, which includes it in each segment's input
as `context_pack_text`. Prompt A/B inject it at the `## Context Pack
(retrieved from book memory)` marker if present.

**CLI `--book-memory` support** (added R4):

| Command | `--book-memory` | Notes |
|---|---|---|
| `python -m app.cli chapter run` | ✓ | Fresh run, resume, dry-run |
| `python -m app.cli chapter stream` | ✓ | Stdout-only mode |
| `python -m app.cli chapter batch` | ✓ | Multi-file batch |
| `python -m app.cli run` (legacy) | ✗ | Segment-level pipeline, no book-memory support |

Design constraints (remain valid since R1):
- **Small context windows** — default 4000 characters (~1000 tokens), the
  pack builder enforces this by dropping lower-priority items as needed.
- **Chinese source is the arbiter** — if the graph says "Qin Liuxi" but
  the source says something different, the source wins. The graph flags
  the discrepancy, it does not override.
- **No automatic writeback** — the translation pipeline never silently
  updates the book memory. Decisions are recorded as a separate human
  review step after translation.

## Comparison to GraphRAG

R1 mirrors GraphRAG's conceptual layers at a much smaller, domain-specific
scale:

| GraphRAG concept | R1 equivalent | Status |
|---|---|---|
| Entity extraction | `BookEntity` records | ✓ Bootstrap from assets |
| Relationship extraction | `Relationship` records | ✓ Schema, no data yet |
| Community detection | (out of scope) | ❌ Phase B? |
| Summarization | `ChapterEvent` summaries | ✓ Schema, no data yet |
| Local search (entity-centric) | Pattern 1-2 above | ❌ Post-R1 |
| Global search (community) | (out of scope) | ❌ Not planned |

The key difference: R1's entities are pre-defined (from project_assets
and human curation), not extracted via NLP. This gives higher precision
for literary translation where entity identity is author-intentional
rather than statistically inferred.

## Remaining risks

1. **No automatic population yet** — entities, relationships, and chapter
   events must be manually added or extracted in a future batch.
2. **No retention policy** — as the book grows past 1000 chapters, the
   JSON file becomes large. No compaction or archiving strategy exists.
3. **No cross-book support** — the model assumes one book per JSON file.
   A multi-book series would need a separate instance per book.
4. **No migration strategy** — schema version field exists on
   `BookMemory.version` but no migration logic is wired.
5. **Bootstrap fidelity** — the project_assets parser extracts canonical
   renderings but does not infer relationships, tags, or descriptions.
   Human enrichment is still needed.
6. **No pre-merge gate check** — no hook validates the book memory JSON
   before merge. A future batch could add this to `pre_merge_gate.sh`.
7. **No `--book-memory` on legacy `run`** — the legacy segment-level
   pipeline (`python -m app.cli run`) does not accept `--book-memory`.
   Only chapter subcommands (`chapter run`, `chapter stream`,
   `chapter batch`) support it. Adding support to the legacy pipeline
   is out of scope; use the chapter-level commands instead.

## Acceptance criteria (R1)

- [x] Data model: entities, relationships, titles, chapter events,
  translation decisions, unresolved decisions, evidence, status
- [x] Validation: record-level + cross-reference, valid + invalid cases
- [x] JSON storage: in-memory + file-backed store
- [x] Project-asset bootstrap: characters, titles, glossary, decisions
- [x] Tests: 52 tests covering all record types, round-trip serialization,
  validation, store, bootstrap, and edge cases
- [x] Full test suite green (554 passing)
- [x] Generated outputs untracked (data/book_memory/ is tracked, but
  bootstrap only reads project_assets; no model-generated output)
