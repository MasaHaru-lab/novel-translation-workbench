"""JSON serialisation helpers for BookMemory and its component types.

Each record type has ``*_to_dict`` and ``*_from_dict`` functions that
convert between Python dataclass instances and plain JSON-compatible dicts.
"""

from enum import Enum
from typing import Dict, List, Optional

from app.book_memory.models import (
    EntityType,
    MemoryRecordStatus,
    EvidenceRef,
    BookEntity,
    Relationship,
    TitleRecord,
    ChapterEvent,
    TranslationDecision,
    UnresolvedDecision,
    BookMemory,
)


def _enum_val(v):
    """Convert an Enum to its value, or pass through."""
    return v.value if isinstance(v, Enum) else v


# ── EvidenceRef ──────────────────────────────────────────────────────────────


def evidence_to_dict(ev: EvidenceRef) -> dict:
    return {
        "chapter": ev.chapter,
        "segment": ev.segment,
        "source_excerpt": ev.source_excerpt,
        "translation_excerpt": ev.translation_excerpt,
        "notes": ev.notes,
    }


def evidence_from_dict(d: dict) -> EvidenceRef:
    return EvidenceRef(
        chapter=d["chapter"],
        segment=d.get("segment"),
        source_excerpt=d.get("source_excerpt", ""),
        translation_excerpt=d.get("translation_excerpt", ""),
        notes=d.get("notes", ""),
    )


# ── BookEntity ───────────────────────────────────────────────────────────────


def entity_to_dict(e: BookEntity) -> dict:
    return {
        "id": e.id,
        "name_zh": e.name_zh,
        "name_en": e.name_en,
        "entity_type": _enum_val(e.entity_type),
        "aliases": e.aliases,
        "alternative_renderings": e.alternative_renderings,
        "description": e.description,
        "status": _enum_val(e.status),
        "evidence": [evidence_to_dict(ev) for ev in e.evidence],
        "tags": e.tags,
        "first_chapter": e.first_chapter,
        "last_chapter": e.last_chapter,
    }


def entity_from_dict(d: dict) -> BookEntity:
    return BookEntity(
        id=d["id"],
        name_zh=d["name_zh"],
        name_en=d["name_en"],
        entity_type=EntityType(d["entity_type"]),
        aliases=d.get("aliases", []),
        alternative_renderings=d.get("alternative_renderings", []),
        description=d.get("description", ""),
        status=MemoryRecordStatus(d.get("status", "tentative")),
        evidence=[evidence_from_dict(ev) for ev in d.get("evidence", [])],
        tags=d.get("tags", []),
        first_chapter=d.get("first_chapter"),
        last_chapter=d.get("last_chapter"),
    )


# ── Relationship ─────────────────────────────────────────────────────────────


def relationship_to_dict(r: Relationship) -> dict:
    return {
        "id": r.id,
        "source_id": r.source_id,
        "target_id": r.target_id,
        "relation_type": r.relation_type,
        "description": r.description,
        "status": _enum_val(r.status),
        "evidence": [evidence_to_dict(ev) for ev in r.evidence],
    }


def relationship_from_dict(d: dict) -> Relationship:
    return Relationship(
        id=d["id"],
        source_id=d["source_id"],
        target_id=d["target_id"],
        relation_type=d["relation_type"],
        description=d.get("description", ""),
        status=MemoryRecordStatus(d.get("status", "tentative")),
        evidence=[evidence_from_dict(ev) for ev in d.get("evidence", [])],
    )


# ── TitleRecord ──────────────────────────────────────────────────────────────


def title_to_dict(t: TitleRecord) -> dict:
    return {
        "id": t.id,
        "name_zh": t.name_zh,
        "name_en": t.name_en,
        "category": t.category,
        "notes": t.notes,
        "status": _enum_val(t.status),
        "evidence": [evidence_to_dict(ev) for ev in t.evidence],
    }


def title_from_dict(d: dict) -> TitleRecord:
    return TitleRecord(
        id=d["id"],
        name_zh=d["name_zh"],
        name_en=d["name_en"],
        category=d.get("category", "title"),
        notes=d.get("notes", ""),
        status=MemoryRecordStatus(d.get("status", "tentative")),
        evidence=[evidence_from_dict(ev) for ev in d.get("evidence", [])],
    )


# ── ChapterEvent ─────────────────────────────────────────────────────────────


def chapter_event_to_dict(ce: ChapterEvent) -> dict:
    return {
        "chapter": ce.chapter,
        "title": ce.title,
        "summary": ce.summary,
        "entities_involved": ce.entities_involved,
        "key_events": ce.key_events,
        "key_decisions": ce.key_decisions,
        "status": _enum_val(ce.status),
    }


def chapter_event_from_dict(d: dict) -> ChapterEvent:
    return ChapterEvent(
        chapter=d["chapter"],
        title=d.get("title", ""),
        summary=d.get("summary", ""),
        entities_involved=d.get("entities_involved", []),
        key_events=d.get("key_events", []),
        key_decisions=d.get("key_decisions", []),
        status=MemoryRecordStatus(d.get("status", "confirmed")),
    )


# ── TranslationDecision ──────────────────────────────────────────────────────


def decision_to_dict(d: TranslationDecision) -> dict:
    return {
        "id": d.id,
        "entity_id": d.entity_id,
        "decision_type": d.decision_type,
        "old_value": d.old_value,
        "new_value": d.new_value,
        "rationale": d.rationale,
        "chapter_decided": d.chapter_decided,
        "status": _enum_val(d.status),
        "evidence": [evidence_to_dict(ev) for ev in d.evidence],
    }


def decision_from_dict(d: dict) -> TranslationDecision:
    return TranslationDecision(
        id=d["id"],
        entity_id=d["entity_id"],
        decision_type=d["decision_type"],
        old_value=d.get("old_value", ""),
        new_value=d.get("new_value", ""),
        rationale=d.get("rationale", ""),
        chapter_decided=d.get("chapter_decided", 0),
        status=MemoryRecordStatus(d.get("status", "confirmed")),
        evidence=[evidence_from_dict(ev) for ev in d.get("evidence", [])],
    )


# ── UnresolvedDecision ───────────────────────────────────────────────────────


def unresolved_to_dict(ud: UnresolvedDecision) -> dict:
    return {
        "id": ud.id,
        "question": ud.question,
        "entity_id": ud.entity_id,
        "options": ud.options,
        "recommendation": ud.recommendation,
        "status": _enum_val(ud.status),
        "created_chapter": ud.created_chapter,
        "evidence": [evidence_to_dict(ev) for ev in ud.evidence],
    }


def unresolved_from_dict(d: dict) -> UnresolvedDecision:
    return UnresolvedDecision(
        id=d["id"],
        question=d["question"],
        entity_id=d.get("entity_id"),
        options=d.get("options", []),
        recommendation=d.get("recommendation", ""),
        status=MemoryRecordStatus(d.get("status", "unresolved")),
        created_chapter=d.get("created_chapter", 0),
        evidence=[evidence_from_dict(ev) for ev in d.get("evidence", [])],
    )


# ── BookMemory (composite) ───────────────────────────────────────────────────


def book_memory_to_dict(memory: BookMemory) -> dict:
    """Serialise a BookMemory to a JSON-compatible dict."""
    return {
        "book_title": memory.book_title,
        "book_title_zh": memory.book_title_zh,
        "total_chapters": memory.total_chapters,
        "version": memory.version,
        "entities": {
            eid: entity_to_dict(e) for eid, e in sorted(memory.entities.items())
        },
        "relationships": {
            rid: relationship_to_dict(r)
            for rid, r in sorted(memory.relationships.items())
        },
        "titles": {
            tid: title_to_dict(t) for tid, t in sorted(memory.titles.items())
        },
        "chapter_events": {
            str(cnum): chapter_event_to_dict(ce)
            for cnum, ce in sorted(memory.chapter_events.items())
        },
        "translation_decisions": {
            did: decision_to_dict(d)
            for did, d in sorted(memory.translation_decisions.items())
        },
        "unresolved_decisions": {
            did: unresolved_to_dict(ud)
            for did, ud in sorted(memory.unresolved_decisions.items())
        },
    }


def book_memory_from_dict(d: dict) -> BookMemory:
    """Deserialise a BookMemory from a JSON-compatible dict.

    Handles both integer and string keys for chapter_events.
    """
    memory = BookMemory(
        book_title=d.get("book_title", ""),
        book_title_zh=d.get("book_title_zh", ""),
        total_chapters=d.get("total_chapters", 0),
        version=d.get("version", "1.0.0"),
    )

    for eid, ed in d.get("entities", {}).items():
        memory.entities[eid] = entity_from_dict(ed)

    for rid, rd in d.get("relationships", {}).items():
        memory.relationships[rid] = relationship_from_dict(rd)

    for tid, td in d.get("titles", {}).items():
        memory.titles[tid] = title_from_dict(td)

    for cnum_str, cd in d.get("chapter_events", {}).items():
        memory.chapter_events[int(cnum_str)] = chapter_event_from_dict(cd)

    for did, dd in d.get("translation_decisions", {}).items():
        memory.translation_decisions[did] = decision_from_dict(dd)

    for did, ud in d.get("unresolved_decisions", {}).items():
        memory.unresolved_decisions[did] = unresolved_from_dict(ud)

    return memory
