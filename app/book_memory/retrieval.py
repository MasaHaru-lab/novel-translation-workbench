"""Retrieval context-pack builder for Narrative Graph Memory (R2).

Takes a Chinese source segment and a BookMemory, identifies candidate
mentions via substring matching, and returns a compact advisory context
pack suitable for Prompt A/B injection during translation.

Design constraints:
- Source text remains primary authority; retrieved memory is advisory only.
- Simple deterministic matching (no NLP, no vector DB, no external service).
- Context packs are bounded by a hard character limit.
- Confirmed records are phrased as established; tentative/unresolved records
  are clearly marked as such.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Set

from app.book_memory.models import (
    MemoryRecordStatus,
    BookEntity,
    Relationship,
    TitleRecord,
    TranslationDecision,
    UnresolvedDecision,
    BookMemory,
)


DEFAULT_MAX_CHARS = 4000
"""Default hard character limit for a formatted context pack."""

OVERHEAD_PER_ENTITY = 300
OVERHEAD_PER_TITLE = 150
OVERHEAD_PER_RELATIONSHIP = 200
OVERHEAD_PER_DECISION = 200
OVERHEAD_PER_UNRESOLVED = 200
"""Approximate overhead per item category (labels, structure, newlines)."""


# ── Match result types ─────────────────────────────────────────────────────


@dataclass
class EntityMatch:
    """A matched BookEntity with metadata showing why it was retrieved.

    ``matched_on`` indicates which field triggered the match (``name_zh``
    or ``alias``), and ``matched_text`` gives the exact substring found
    in the source segment.
    """

    entity: BookEntity
    matched_on: str  # "name_zh" or "alias"
    matched_text: str  # exact substring found in source

    @property
    def is_confirmed(self) -> bool:
        return self.entity.status == MemoryRecordStatus.CONFIRMED

    @property
    def is_tentative(self) -> bool:
        return self.entity.status == MemoryRecordStatus.TENTATIVE


@dataclass
class TitleMatch:
    """A matched TitleRecord with match metadata."""

    title: TitleRecord
    matched_on: str
    matched_text: str

    @property
    def is_confirmed(self) -> bool:
        return self.title.status == MemoryRecordStatus.CONFIRMED


@dataclass
class ContextPack:
    """Compact advisory context pack for Prompt A/B injection.

    Contains matched entities/titles from the source segment plus their
    directly related relationships, translation decisions, and unresolved
    decisions.

    ``truncated`` is True when the total formatted pack exceeded
    ``max_chars`` and items were dropped from lower-priority categories.
    """

    matched_entities: List[EntityMatch] = field(default_factory=list)
    matched_titles: List[TitleMatch] = field(default_factory=list)
    related_relationships: List[Relationship] = field(default_factory=list)
    related_decisions: List[TranslationDecision] = field(default_factory=list)
    related_unresolved: List[UnresolvedDecision] = field(default_factory=list)

    truncated: bool = False
    total_chars: int = 0
    max_chars: int = DEFAULT_MAX_CHARS

    @property
    def is_empty(self) -> bool:
        """True when no records were matched at all."""
        return (
            not self.matched_entities
            and not self.matched_titles
            and not self.related_relationships
            and not self.related_decisions
            and not self.related_unresolved
        )

    def format_text(self) -> str:
        """Render the context pack as structured text for Prompt A/B injection.

        Confirmed records are presented as established facts. Tentative and
        unresolved records are marked with ``[TENTATIVE]`` or ``[UNRESOLVED]``
        labels so the prompt can distinguish settled knowledge from speculation.
        """
        lines: List[str] = []
        lines.append("## Context Pack (retrieved from book memory)")

        if self.truncated:
            lines.append(
                f"*Note: context pack was truncated to fit within "
                f"{self.max_chars} characters.*"
            )

        if self.is_empty:
            lines.append(
                "No matching entities, titles, or decisions found in "
                "the book memory for this segment."
            )
            return "\n".join(lines)

        # Matched entities
        if self.matched_entities:
            lines.append("")
            lines.append("### Entities")
            for em in self.matched_entities:
                status_tag = ""
                if em.entity.status == MemoryRecordStatus.TENTATIVE:
                    status_tag = " [TENTATIVE]"
                elif em.entity.status == MemoryRecordStatus.UNRESOLVED:
                    status_tag = " [UNRESOLVED]"
                label = (
                    f"{em.entity.name_en} ({em.entity.name_zh})"
                    f"{status_tag}"
                )
                if em.entity.description:
                    label += f" — {em.entity.description}"
                lines.append(f"- {label}")
                lines.append(f"  - Matched via {em.matched_on}: {em.matched_text}")
                if em.entity.tags:
                    lines.append(f"  - Tags: {', '.join(em.entity.tags)}")

        # Matched titles / terms
        if self.matched_titles:
            lines.append("")
            lines.append("### Titles / Terms")
            for tm in self.matched_titles:
                status_tag = ""
                if tm.title.status == MemoryRecordStatus.TENTATIVE:
                    status_tag = " [TENTATIVE]"
                label = f"{tm.title.name_en} ({tm.title.name_zh}){status_tag}"
                if tm.title.notes:
                    label += f" — {tm.title.notes}"
                lines.append(f"- {label}")
                lines.append(f"  - Matched via {tm.matched_on}: {tm.matched_text}")

        # Related relationships
        if self.related_relationships:
            lines.append("")
            lines.append("### Relationships")
            for r in self.related_relationships:
                status_tag = ""
                if r.status == MemoryRecordStatus.TENTATIVE:
                    status_tag = " [TENTATIVE]"
                label = (
                    f"{r.source_id} → {r.target_id}: {r.relation_type}"
                    f"{status_tag}"
                )
                if r.description:
                    label += f" ({r.description})"
                lines.append(f"- {label}")

        # Related translation decisions
        if self.related_decisions:
            lines.append("")
            lines.append("### Previous Translation Decisions")
            for d in self.related_decisions:
                status_tag = ""
                if d.status == MemoryRecordStatus.TENTATIVE:
                    status_tag = " [TENTATIVE]"
                label = (
                    f"{d.entity_id}: "
                    f"\"{d.new_value}\" "
                    f"(type: {d.decision_type}){status_tag}"
                )
                if d.rationale:
                    label += f" — {d.rationale}"
                lines.append(f"- {label}")

        # Unresolved questions
        if self.related_unresolved:
            lines.append("")
            lines.append("### Unresolved Questions")
            for u in self.related_unresolved:
                label = f"{u.question} [UNRESOLVED]"
                if u.options:
                    label += f" (options: {', '.join(u.options)})"
                lines.append(f"- {label}")

        return "\n".join(lines)


# ── Matching helpers ────────────────────────────────────────────────────────


def _find_entity_matches(segment: str, memory: BookMemory) -> List[EntityMatch]:
    """Find BookEntity records whose ``name_zh`` or ``aliases`` appear in segment.

    Returns matches ordered by longest match text first (longer = more specific),
    then by confirmed status (confirmed before tentative).
    """
    matches: List[EntityMatch] = []

    for entity in memory.entities.values():
        # Check primary name_zh
        if entity.name_zh and entity.name_zh in segment:
            matches.append(
                EntityMatch(entity=entity, matched_on="name_zh", matched_text=entity.name_zh)
            )
            continue
        # Check aliases
        matched_alias = _match_aliases(segment, entity.aliases)
        if matched_alias is not None:
            matches.append(
                EntityMatch(entity=entity, matched_on="alias", matched_text=matched_alias)
            )

    # Sort: longest matched text first (more specific), then confirmed first
    matches.sort(key=lambda m: (-len(m.matched_text), 0 if m.is_confirmed else 1))
    return matches


def _match_aliases(segment: str, aliases: List[str]) -> Optional[str]:
    """Return the first alias found in segment, or None.

    Checks longer aliases first for specificity.
    """
    sorted_aliases = sorted(aliases, key=len, reverse=True)
    for alias in sorted_aliases:
        if alias and alias in segment:
            return alias
    return None


def _find_title_matches(segment: str, memory: BookMemory) -> List[TitleMatch]:
    """Find TitleRecord entries whose ``name_zh`` appears in segment.

    Returns matches ordered by longest match text first.
    """
    matches: List[TitleMatch] = []

    for title in memory.titles.values():
        if title.name_zh and title.name_zh in segment:
            matches.append(
                TitleMatch(title=title, matched_on="name_zh", matched_text=title.name_zh)
            )

    # Sort: longest matched text first, then confirmed first
    matches.sort(key=lambda m: (-len(m.matched_text), 0 if m.is_confirmed else 1))
    return matches


# ── Relationship / decision resolution ──────────────────────────────────────


def _resolve_relationships(
    matched_ids: Set[str],
    memory: BookMemory,
) -> List[Relationship]:
    """Return relationships where source or target is in matched_ids."""
    return [
        rel
        for rel in memory.relationships.values()
        if rel.source_id in matched_ids or rel.target_id in matched_ids
    ]


def _resolve_decisions(
    matched_ids: Set[str],
    memory: BookMemory,
) -> tuple:
    """Return (translation_decisions, unresolved_decisions) tied to matched_ids."""
    decisions = [
        dec
        for dec in memory.translation_decisions.values()
        if dec.entity_id in matched_ids
    ]
    unresolved = [
        ud
        for ud in memory.unresolved_decisions.values()
        if ud.entity_id is not None and ud.entity_id in matched_ids
    ]
    return decisions, unresolved


# ── Size estimation and truncation ──────────────────────────────────────────


def _estimate_formatted_size(pack: ContextPack) -> int:
    """Estimate how many characters the formatted pack will occupy.

    Uses a per-item overhead plus variable-length field sum for a fast
    upper-bound estimate without actually formatting the text.
    """
    total = 0

    for em in pack.matched_entities:
        total += (
            len(em.entity.name_zh)
            + len(em.entity.name_en)
            + len(em.entity.description or "")
            + len(em.matched_text)
            + sum(len(t) for t in em.entity.tags)
            + OVERHEAD_PER_ENTITY
        )

    for tm in pack.matched_titles:
        total += (
            len(tm.title.name_zh)
            + len(tm.title.name_en)
            + len(tm.title.notes or "")
            + len(tm.matched_text)
            + OVERHEAD_PER_TITLE
        )

    for r in pack.related_relationships:
        total += (
            len(r.source_id)
            + len(r.target_id)
            + len(r.relation_type)
            + len(r.description or "")
            + OVERHEAD_PER_RELATIONSHIP
        )

    for d in pack.related_decisions:
        total += (
            len(d.entity_id)
            + len(d.new_value or "")
            + len(d.rationale or "")
            + OVERHEAD_PER_DECISION
        )

    for u in pack.related_unresolved:
        total += (
            len(u.question or "")
            + sum(len(o) for o in u.options)
            + OVERHEAD_PER_UNRESOLVED
        )

    return total


def _truncate_pack(pack: ContextPack) -> ContextPack:
    """Truncate a context pack to fit within ``max_chars``.

    Drop order (dropped first = lowest priority):
    1. related_unresolved
    2. related_decisions
    3. related_relationships
    4. tentative titles (confirmed titles kept)
    5. tentative entities (confirmed entities kept)
    6. confirmed titles
    7. confirmed entities (kept last = highest priority)

    Matching entities are always kept ahead of relationships and decisions,
    so a relationship can never survive its related entity being dropped.
    Similarly, confirmed entities survive before tentative ones.

    Within each list, items at the end of the sorted order are dropped first.
    """
    if pack.total_chars <= pack.max_chars:
        return pack

    pack.truncated = True

    # Sort matched items so highest priority is first, then drop from the end
    pack.matched_entities.sort(
        key=lambda em: (0 if em.is_confirmed else 1, -len(em.matched_text))
    )
    pack.matched_titles.sort(
        key=lambda tm: (0 if tm.is_confirmed else 1, -len(tm.matched_text))
    )

    # Drop categories from lowest priority upward
    while pack.total_chars > pack.max_chars:
        dropped = False

        # Drop unresolved first
        if pack.related_unresolved:
            pack.related_unresolved.pop()
            dropped = True
        # Then translation decisions
        elif pack.related_decisions:
            pack.related_decisions.pop()
            dropped = True
        # Then relationships
        elif pack.related_relationships:
            pack.related_relationships.pop()
            dropped = True
        # Then tentative titles (keep confirmed titles)
        elif pack.matched_titles and any(not tm.is_confirmed for tm in pack.matched_titles):
            for i in range(len(pack.matched_titles) - 1, -1, -1):
                if not pack.matched_titles[i].is_confirmed:
                    pack.matched_titles.pop(i)
                    dropped = True
                    break
        # Then tentative entities (keep confirmed entities)
        elif pack.matched_entities and any(not em.is_confirmed for em in pack.matched_entities):
            for i in range(len(pack.matched_entities) - 1, -1, -1):
                if not pack.matched_entities[i].is_confirmed:
                    pack.matched_entities.pop(i)
                    dropped = True
                    break
        # Hard fallback: drop confirmed titles from the end (reverse priority)
        elif pack.matched_titles:
            pack.matched_titles.pop()
            dropped = True
        # Last resort: drop confirmed entities from the end (reverse priority)
        elif pack.matched_entities:
            pack.matched_entities.pop()
            dropped = True
        else:
            break

        if dropped:
            pack.total_chars = _estimate_formatted_size(pack)
        else:
            break

    return pack


# ── Main API ────────────────────────────────────────────────────────────────


def build_context_pack(
    segment: str,
    memory: BookMemory,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> ContextPack:
    """Build a compact advisory context pack from a source segment.

    Given a Chinese source segment and a BookMemory:
    1. Identify candidate mentions from existing memory records (entities,
       titles/terms) using deterministic substring matching.
    2. Retrieve only relevant records and direct relationship/decision
       records tied to those mentions.
    3. Build a compact context pack with metadata showing why each item
       was retrieved.
    4. Enforce ``max_chars`` size limit with priority-based truncation.

    Args:
        segment: Chinese source text segment to analyse.
        memory: BookMemory instance to query.
        max_chars: Hard character limit for the formatted context pack.
            Defaults to ``DEFAULT_MAX_CHARS (4000)``.

    Returns:
        A ``ContextPack`` instance with matched records. Returns an empty
        pack (``is_empty == True``) when no matches are found.
    """
    # Step 1: Match entities and titles
    entity_matches = _find_entity_matches(segment, memory)
    title_matches = _find_title_matches(segment, memory)

    # Step 2: Collect matched IDs for relationship/decision resolution
    matched_ids: Set[str] = set()
    for em in entity_matches:
        matched_ids.add(em.entity.id)
    for tm in title_matches:
        matched_ids.add(tm.title.id)

    # Step 3: Resolve relationships and decisions
    relationships = _resolve_relationships(matched_ids, memory)
    decisions, unresolved = _resolve_decisions(matched_ids, memory)

    # Step 4: Build the pack
    pack = ContextPack(
        matched_entities=entity_matches,
        matched_titles=title_matches,
        related_relationships=relationships,
        related_decisions=decisions,
        related_unresolved=unresolved,
        max_chars=max_chars,
    )

    # Step 5: Estimate size and truncate if needed
    pack.total_chars = _estimate_formatted_size(pack)
    pack = _truncate_pack(pack)

    return pack
