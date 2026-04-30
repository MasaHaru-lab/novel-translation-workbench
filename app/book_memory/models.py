"""Data models for the book memory (narrative graph memory) layer.

Covers R1 entity types:
- characters
- places / factions / institutions
- titles / forms of address / recurring terms
- relationships between entities
- chapter-level event summaries
- translation decisions
- unresolved / tentative decisions
- evidence fields pointing to chapter / source context
- status field (confirmed / tentative / unresolved)
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────────


class EntityType(str, Enum):
    """The nature of a ``BookEntity`` in the book world."""

    CHARACTER = "character"
    PLACE = "place"
    FACTION = "faction"
    INSTITUTION = "institution"


class MemoryRecordStatus(str, Enum):
    """Confidence level of a memory record.

    - CONFIRMED: Human-verified, stable.
    - TENTATIVE: Reasonable but awaiting cross-chapter confirmation.
    - UNRESOLVED: Open question, not yet decided.
    """

    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    UNRESOLVED = "unresolved"


# ── Cross-cutting types ──────────────────────────────────────────────────────


@dataclass
class EvidenceRef:
    """A concrete reference to where in the source / translation evidence exists.

    Every claim in the book memory should trace back to at least one
    evidence reference so the graph remains auditable and the Chinese
    source text stays the primary authority.
    """

    chapter: int
    """Chapter number (1-based) where the evidence appears."""

    segment: Optional[int] = None
    """Segment index within the chapter, if applicable."""

    source_excerpt: str = ""
    """Short excerpt from the Chinese source text (50-200 chars)."""

    translation_excerpt: str = ""
    """Corresponding excerpt from the English translation (50-200 chars)."""

    notes: str = ""
    """Free-text notes about this evidence instance."""


# ── Core entity types ────────────────────────────────────────────────────────


@dataclass
class BookEntity:
    """A named entity in the book world.

    An entity can be a character, place, faction, or institution. Each
    carries a canonical English rendering, known Chinese aliases, evidence
    trail, and a confidence status.
    """

    id: str
    """Stable unique identifier for this entity (e.g. ``qin_liuxi``)."""

    name_zh: str
    """Primary Chinese name (simplified or traditional as in source)."""

    name_en: str
    """Canonical English rendering (primary reference for translation)."""

    entity_type: EntityType
    """What kind of entity this is."""

    aliases: List[str] = field(default_factory=list)
    """Other Chinese names / styles / courtesy names this entity goes by."""

    alternative_renderings: List[str] = field(default_factory=list)
    """Previously considered or historically used English renderings."""

    description: str = ""
    """Free-text description of the entity (personality, role, significance)."""

    status: MemoryRecordStatus = MemoryRecordStatus.TENTATIVE
    """Confidence status of this entity record."""

    evidence: List[EvidenceRef] = field(default_factory=list)
    """Evidence trail supporting this entity's canonical rendering."""

    tags: List[str] = field(default_factory=list)
    """Categorisation tags (e.g. ``protagonist``, ``antagonist``, ``minor``)."""

    first_chapter: Optional[int] = None
    """Chapter where this entity first appears (1-based)."""

    last_chapter: Optional[int] = None
    """Most recent chapter where this entity appears (1-based)."""


@dataclass
class Relationship:
    """A directed relationship between two entities.

    Relationships are directional: source -> target. For undirected
    relationships, store two entries or use a convention like
    ``relation_type`` starting with ``mutual_``.
    """

    id: str
    """Stable unique identifier (e.g. ``qin_liuxi--old_lady_qin:parent_of``)."""

    source_id: str
    """Entity id of the source / subject."""

    target_id: str
    """Entity id of the target / object."""

    relation_type: str
    """Nature of the relationship (e.g. ``parent_of``, ``master_of``,
    ``married_to``, ``ally``, ``enemy``, ``serves``)."""

    description: str = ""
    """Free-text description of this relationship."""

    status: MemoryRecordStatus = MemoryRecordStatus.TENTATIVE
    """Confidence status of this relationship record."""

    evidence: List[EvidenceRef] = field(default_factory=list)
    """Evidence trail supporting this relationship."""


@dataclass
class TitleRecord:
    """A title, form of address, or recurring term.

    This covers items that would go in the project-level titles_and_terms.md
    or glossary.md but need a structured, queryable form for memory retrieval.
    """

    id: str
    """Stable unique identifier (e.g. ``young_lady``)."""

    name_zh: str
    """The Chinese term."""

    name_en: str
    """Canonical English rendering."""

    category: str = "title"
    """Category: ``title``, ``address``, or ``term``."""

    notes: str = ""
    """Usage notes, context, or restrictions."""

    status: MemoryRecordStatus = MemoryRecordStatus.TENTATIVE
    """Confidence status."""

    evidence: List[EvidenceRef] = field(default_factory=list)
    """Evidence trail."""


@dataclass
class ChapterEvent:
    """A structured summary of what happens in one chapter.

    Chapter events are the highest-level memory structure — they let
    future retrieval answer "which chapter introduced X?" or "where
    did Y happen?" without re-reading the entire source.
    """

    chapter: int
    """Chapter number (1-based)."""

    title: str = ""
    """Chapter title (English), if known."""

    summary: str = ""
    """Brief narrative summary (2-5 sentences)."""

    entities_involved: List[str] = field(default_factory=list)
    """Entity ids that appear in this chapter."""

    key_events: List[str] = field(default_factory=list)
    """Short bullet-list of key events."""

    key_decisions: List[str] = field(default_factory=list)
    """Translation decisions made or confirmed in this chapter."""

    status: MemoryRecordStatus = MemoryRecordStatus.CONFIRMED
    """Always CONFIRMED for a chapter we have translated. TENTATIVE only
    for chapters inferred from the source without a full translation run."""


@dataclass
class TranslationDecision:
    """A specific translation decision recorded during the workflow.

    Unlike unresolved decisions, a TranslationDecision is a settled choice
    that subsequent chapters should follow unless explicitly revisited.
    """

    id: str
    """Stable unique identifier."""

    entity_id: str
    """The entity, title, or term this decision concerns."""

    decision_type: str
    """Type: ``rendering`` (name/term choice), ``style`` (stylistic rule),
    ``consistency`` (cross-chapter unification)."""

    old_value: str = ""
    """Previous rendering or behaviour (empty for first-time decisions)."""

    new_value: str = ""
    """Newly chosen canonical rendering or behaviour."""

    rationale: str = ""
    """Why this decision was made."""

    chapter_decided: int = 0
    """Chapter (1-based) where the decision was made."""

    status: MemoryRecordStatus = MemoryRecordStatus.CONFIRMED
    """CONFIRMED by default. Can be TENTATIVE for decisions awaiting review."""

    evidence: List[EvidenceRef] = field(default_factory=list)


@dataclass
class UnresolvedDecision:
    """A translation question that is still open.

    Tracks questions across chapters so we don't repeatedly debate the
    same decision and can identify patterns of uncertainty.
    """

    id: str
    """Stable unique identifier."""

    question: str
    """The open question (e.g. "How should 嬷嬷 be rendered consistently?")."""

    entity_id: Optional[str] = None
    """Entity or term this question relates to, if any."""

    options: List[str] = field(default_factory=list)
    """Candidate renderings under consideration."""

    recommendation: str = ""
    """Tentative recommendation, if one exists."""

    status: MemoryRecordStatus = MemoryRecordStatus.UNRESOLVED
    """Always UNRESOLVED. Resolved decisions move to TranslationDecision."""

    created_chapter: int = 0
    """Chapter where this question first arose."""

    evidence: List[EvidenceRef] = field(default_factory=list)
    """Evidence that prompted this question."""


# ── Top-level container ──────────────────────────────────────────────────────


@dataclass
class BookMemory:
    """Top-level container for all narrative graph memory data.

    This is the single root object that holds every entity, relationship,
    title record, chapter event, and decision for a given book. It is
    designed to be serialised to JSON and loaded on demand during
    translation retrieval / context pack assembly.

    The Chinese source text remains the primary authority. This graph is
    advisory: it accelerates retrieval and flags inconsistency, but it
    never replaces the source.
    """

    book_title: str = ""
    """Book title in English."""

    book_title_zh: str = ""
    """Book title in Chinese."""

    total_chapters: int = 0
    """Total known chapter count (may grow as translation progresses)."""

    entities: Dict[str, BookEntity] = field(default_factory=dict)
    """Entities keyed by entity id."""

    relationships: Dict[str, Relationship] = field(default_factory=dict)
    """Relationships keyed by relationship id."""

    titles: Dict[str, TitleRecord] = field(default_factory=dict)
    """Titles / terms keyed by record id."""

    chapter_events: Dict[int, ChapterEvent] = field(default_factory=dict)
    """Chapter-event summaries keyed by chapter number."""

    translation_decisions: Dict[str, TranslationDecision] = field(default_factory=dict)
    """Settled translation decisions keyed by decision id."""

    unresolved_decisions: Dict[str, UnresolvedDecision] = field(default_factory=dict)
    """Open translation questions keyed by decision id."""

    version: str = "1.0.0"
    """Schema version for forward-compatibility checks."""
