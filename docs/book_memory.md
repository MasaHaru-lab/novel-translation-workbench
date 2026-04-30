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

## Future: retrieval / context pack design (post-R1)

The book memory is designed to support the following retrieval patterns
without depending on vector databases or external services.

### Pattern 1: Entity-centric context pack

When translating chapter N+1, the system can query:

1. "Which confirmed entities appeared in chapters N-5 through N?" →
   provides continuity for recurring characters.
2. "Which translation decisions were made in those chapters?" →
   prevents regression on settled renderings.
3. "Which unresolved decisions are still open?" →
   flags questions that the new chapter might resolve.

This produces a small, targeted context snippet injected into the
translation prompt (Prompt A), keeping the model aware of existing
decisions without overwhelming it with the full book text.

### Pattern 2: Relationship-aware entity summary

For an entity `E` appearing in a new chapter:

1. Collect all relationships where `E` is source or target.
2. Collect the most recent chapter event summaries mentioning `E`.
3. Collect the canonical rendering and known alternative renderings.
4. Format as a structured entity card injected into the context pack.

This prevents the translator from inventing new spellings, misattributing
relationships, or flattening titles inconsistently.

### Pattern 3: Consistency pre-flight

Before translating chapter N:

1. Query `chapter_events[N-1]` for the immediate preceding context.
2. Query `translation_decisions` for any decisions involving entities
   that appear in chapter N (inferred from source text mention).
3. If unresolved decisions exist for those entities, flag them for the
   reviewer.

### Integration boundary

The context pack assembly layer is **not yet built**. R1 provides only
the data model and storage — the retrieval logic that queries the graph
and injects results into translation prompts comes in a later phase.

Key design constraints for that future layer:
- **Small context windows** (< 2000 tokens per pack) — the model prompt
  has limited space; the pack builder must be selective.
- **Priority by recency and role** — a protagonist appearing in the
  previous chapter gets more context than a minor character last seen
  100 chapters ago.
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
