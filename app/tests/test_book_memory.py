"""Tests for the book_memory module (R1 — narrative graph memory foundation).

Covers:
- Model instantiation and defaults
- Serialization round-trip (to_dict / from_dict) for every record type
- BookMemory container serialization
- Validation — valid and invalid records
- Cross-reference validation
- Bootstrap from project_assets
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

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
from app.book_memory.serialization import (
    evidence_to_dict,
    evidence_from_dict,
    entity_to_dict,
    entity_from_dict,
    relationship_to_dict,
    relationship_from_dict,
    title_to_dict,
    title_from_dict,
    chapter_event_to_dict,
    chapter_event_from_dict,
    decision_to_dict,
    decision_from_dict,
    unresolved_to_dict,
    unresolved_from_dict,
    book_memory_to_dict,
    book_memory_from_dict,
)
from app.book_memory.validation import (
    validate_entity,
    validate_relationship,
    validate_title_record,
    validate_chapter_event,
    validate_translation_decision,
    validate_unresolved_decision,
    validate_book_memory,
)
from app.book_memory.store import InMemoryBookMemoryStore, FileBookMemoryStore
from app.book_memory.bootstrap import (
    bootstrap_entities,
    _bootstrap_titles,
    bootstrap_decisions,
    bootstrap_from_project_assets,
)


# ═════════════════════════════════════════════════════════════════════════
# Model instantiation and defaults
# ═════════════════════════════════════════════════════════════════════════


def test_evidence_ref_defaults():
    ev = EvidenceRef(chapter=5)
    assert ev.chapter == 5
    assert ev.segment is None
    assert ev.source_excerpt == ""
    assert ev.translation_excerpt == ""
    assert ev.notes == ""


def test_book_entity_defaults():
    e = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
    )
    assert e.id == "qin_liuxi"
    assert e.status == MemoryRecordStatus.TENTATIVE
    assert e.aliases == []
    assert e.evidence == []
    assert e.first_chapter is None


def test_book_entity_with_evidence():
    ev = EvidenceRef(chapter=1, source_excerpt="秦流西", notes="First appearance")
    e = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        evidence=[ev],
        tags=["protagonist"],
        first_chapter=1,
        status=MemoryRecordStatus.CONFIRMED,
    )
    assert e.status == MemoryRecordStatus.CONFIRMED
    assert e.tags == ["protagonist"]
    assert e.first_chapter == 1
    assert len(e.evidence) == 1


def test_relationship_defaults():
    r = Relationship(
        id="qin_liuxi--old_lady_qin:parent_of",
        source_id="qin_liuxi",
        target_id="old_lady_qin",
        relation_type="parent_of",
    )
    assert r.status == MemoryRecordStatus.TENTATIVE
    assert r.description == ""


def test_title_record_defaults():
    t = TitleRecord(id="young_lady", name_zh="大小姐", name_en="Young Lady")
    assert t.category == "title"
    assert t.status == MemoryRecordStatus.TENTATIVE


def test_chapter_event_defaults():
    ce = ChapterEvent(chapter=1)
    assert ce.title == ""
    assert ce.summary == ""
    assert ce.status == MemoryRecordStatus.CONFIRMED


def test_translation_decision_defaults():
    d = TranslationDecision(
        id="legal_mother_rendering",
        entity_id="legal_mother",
        decision_type="rendering",
    )
    assert d.status == MemoryRecordStatus.CONFIRMED
    assert d.old_value == ""
    assert d.chapter_decided == 0


def test_unresolved_decision_defaults():
    ud = UnresolvedDecision(
        id="momo_system",
        question="How should Momo be rendered consistently?",
    )
    assert ud.status == MemoryRecordStatus.UNRESOLVED
    assert ud.options == []
    assert ud.created_chapter == 0


def test_book_memory_defaults():
    m = BookMemory()
    assert m.entities == {}
    assert m.relationships == {}
    assert m.titles == {}
    assert m.chapter_events == {}
    assert m.translation_decisions == {}
    assert m.unresolved_decisions == {}
    assert m.version == "1.0.0"


# ═════════════════════════════════════════════════════════════════════════
# Serialization round-trip
# ═════════════════════════════════════════════════════════════════════════


def test_evidence_roundtrip():
    ev = EvidenceRef(chapter=1, segment=3, source_excerpt="秦流西")
    d = evidence_to_dict(ev)
    restored = evidence_from_dict(d)
    assert restored.chapter == 1
    assert restored.segment == 3
    assert restored.source_excerpt == "秦流西"


def test_entity_roundtrip():
    ev = EvidenceRef(chapter=1, source_excerpt="秦流西")
    e = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        evidence=[ev],
        tags=["protagonist"],
        first_chapter=1,
        status=MemoryRecordStatus.CONFIRMED,
    )
    d = entity_to_dict(e)
    restored = entity_from_dict(d)
    assert restored.id == "qin_liuxi"
    assert restored.name_en == "Qin Liuxi"
    assert restored.entity_type == EntityType.CHARACTER
    assert restored.status == MemoryRecordStatus.CONFIRMED
    assert len(restored.evidence) == 1
    assert restored.tags == ["protagonist"]


def test_relationship_roundtrip():
    r = Relationship(
        id="r1", source_id="qin_liuxi", target_id="old_lady_qin",
        relation_type="parent_of", description="Grandmother and granddaughter",
    )
    d = relationship_to_dict(r)
    restored = relationship_from_dict(d)
    assert restored.id == "r1"
    assert restored.source_id == "qin_liuxi"
    assert restored.relation_type == "parent_of"


def test_title_record_roundtrip():
    t = TitleRecord(id="young_lady", name_zh="大小姐", name_en="Young Lady",
                    category="title", notes="Household status term")
    d = title_to_dict(t)
    restored = title_from_dict(d)
    assert restored.id == "young_lady"
    assert restored.name_en == "Young Lady"
    assert restored.category == "title"
    assert restored.notes == "Household status term"


def test_chapter_event_roundtrip():
    ce = ChapterEvent(chapter=5, title="The Feast",
                      summary="A grand banquet.",
                      entities_involved=["qin_liuxi", "old_lady_qin"],
                      key_events=["Banquet begins", "Argument"],
                      status=MemoryRecordStatus.CONFIRMED)
    d = chapter_event_to_dict(ce)
    restored = chapter_event_from_dict(d)
    assert restored.chapter == 5
    assert restored.title == "The Feast"
    assert len(restored.entities_involved) == 2
    assert restored.key_events[1] == "Argument"


def test_decision_roundtrip():
    dec = TranslationDecision(
        id="legal_mother", entity_id="legal_mother",
        decision_type="rendering", old_value="principal mother",
        new_value="legal mother",
        rationale="Preserves legal-wife distinction",
        chapter_decided=1, status=MemoryRecordStatus.CONFIRMED,
    )
    d = decision_to_dict(dec)
    restored = decision_from_dict(d)
    assert restored.id == "legal_mother"
    assert restored.new_value == "legal mother"
    assert restored.rationale == "Preserves legal-wife distinction"


def test_unresolved_roundtrip():
    ud = UnresolvedDecision(
        id="momo_system", question="How to render Momo?",
        options=["Momo", "Nanny", "Nurse"],
        recommendation="Momo for now", created_chapter=1,
    )
    d = unresolved_to_dict(ud)
    restored = unresolved_from_dict(d)
    assert restored.id == "momo_system"
    assert len(restored.options) == 3
    assert restored.recommendation == "Momo for now"


def test_book_memory_roundtrip_json():
    """Full BookMemory serialization round-trip through JSON."""
    memory = BookMemory(book_title="Test Book", total_chapters=10)

    memory.entities["qin_liuxi"] = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
    )
    memory.entities["old_lady_qin"] = BookEntity(
        id="old_lady_qin", name_zh="秦老太太", name_en="Old Lady Qin",
        entity_type=EntityType.CHARACTER,
    )
    memory.relationships["r1"] = Relationship(
        id="r1", source_id="qin_liuxi", target_id="old_lady_qin",
        relation_type="parent_of",
    )
    memory.titles["young_lady"] = TitleRecord(
        id="young_lady", name_zh="大小姐", name_en="Young Lady",
    )
    memory.chapter_events[1] = ChapterEvent(
        chapter=1, summary="Introduction chapter.",
    )
    memory.translation_decisions["legal_mother"] = TranslationDecision(
        id="legal_mother", entity_id="legal_mother",
        decision_type="rendering", new_value="legal mother",
    )

    # Serialize to dict, then to JSON string, then back
    d = book_memory_to_dict(memory)
    json_str = json.dumps(d, ensure_ascii=False)
    restored = book_memory_from_dict(json.loads(json_str))

    assert restored.book_title == "Test Book"
    assert restored.total_chapters == 10
    assert len(restored.entities) == 2
    assert len(restored.relationships) == 1
    assert len(restored.titles) == 1
    assert len(restored.chapter_events) == 1
    assert len(restored.translation_decisions) == 1
    assert restored.entities["qin_liuxi"].name_en == "Qin Liuxi"
    assert restored.entities["qin_liuxi"].entity_type == EntityType.CHARACTER
    assert restored.chapter_events[1].summary == "Introduction chapter."


# ═════════════════════════════════════════════════════════════════════════
# Validation — valid records
# ═════════════════════════════════════════════════════════════════════════


def test_validate_valid_entity():
    e = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        status=MemoryRecordStatus.CONFIRMED,
    )
    result = validate_entity(e)
    assert result.is_valid


def test_validate_valid_relationship():
    r = Relationship(
        id="r1", source_id="a", target_id="b",
        relation_type="parent_of",
    )
    result = validate_relationship(r)
    assert result.is_valid


def test_validate_valid_title():
    t = TitleRecord(id="young_lady", name_zh="大小姐", name_en="Young Lady",
                    category="title")
    result = validate_title_record(t)
    assert result.is_valid


def test_validate_valid_chapter_event():
    ce = ChapterEvent(chapter=1)
    result = validate_chapter_event(ce)
    assert result.is_valid


def test_validate_valid_decision():
    d = TranslationDecision(
        id="d1", entity_id="qin_liuxi", decision_type="rendering",
    )
    result = validate_translation_decision(d)
    assert result.is_valid


def test_validate_valid_unresolved():
    ud = UnresolvedDecision(id="u1", question="How to handle X?")
    result = validate_unresolved_decision(ud)
    assert result.is_valid


# ═════════════════════════════════════════════════════════════════════════
# Validation — invalid records
# ═════════════════════════════════════════════════════════════════════════


def test_validate_entity_empty_id():
    e = BookEntity(
        id="", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
    )
    result = validate_entity(e)
    assert not result.is_valid
    assert any(err.field == "id" for err in result.errors)


def test_validate_entity_empty_name_zh():
    e = BookEntity(
        id="qin_liuxi", name_zh="", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
    )
    result = validate_entity(e)
    assert not result.is_valid
    assert any(err.field == "name_zh" for err in result.errors)


def test_validate_entity_empty_name_en():
    e = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="",
        entity_type=EntityType.CHARACTER,
    )
    result = validate_entity(e)
    assert not result.is_valid
    assert any(err.field == "name_en" for err in result.errors)


def test_validate_entity_bad_status():
    e = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        status="unknown_status",  # type: ignore
    )
    result = validate_entity(e)
    assert not result.is_valid


def test_validate_entity_invalid_first_chapter():
    e = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        first_chapter=0,
    )
    result = validate_entity(e)
    assert not result.is_valid
    assert any(err.field == "first_chapter" for err in result.errors)


def test_validate_entity_last_before_first():
    e = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        first_chapter=10, last_chapter=5,
    )
    result = validate_entity(e)
    assert not result.is_valid
    assert any(err.field == "last_chapter" for err in result.errors)


def test_validate_relationship_self_reference():
    r = Relationship(
        id="self", source_id="a", target_id="a",
        relation_type="self",
    )
    result = validate_relationship(r)
    assert not result.is_valid


def test_validate_title_bad_category():
    t = TitleRecord(id="t1", name_zh="某某", name_en="Something",
                    category="invalid_cat")
    result = validate_title_record(t)
    assert not result.is_valid
    assert any(err.field == "category" for err in result.errors)


def test_validate_decision_empty_id():
    d = TranslationDecision(
        id="", entity_id="qin_liuxi", decision_type="rendering",
    )
    result = validate_translation_decision(d)
    assert not result.is_valid
    assert any(err.field == "id" for err in result.errors)


def test_validate_decision_wrong_type():
    d = TranslationDecision(
        id="d1", entity_id="qin_liuxi", decision_type="typo_type",
    )
    result = validate_translation_decision(d)
    assert not result.is_valid
    assert any(err.field == "decision_type" for err in result.errors)


def test_validate_unresolved_empty_question():
    ud = UnresolvedDecision(id="u1", question="")
    result = validate_unresolved_decision(ud)
    assert not result.is_valid
    assert any(err.field == "question" for err in result.errors)


# ═════════════════════════════════════════════════════════════════════════
# Cross-reference validation
# ═════════════════════════════════════════════════════════════════════════


def test_cross_reference_unknown_entity_in_relationship():
    memory = BookMemory()
    memory.entities["qin_liuxi"] = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
    )
    memory.relationships["r1"] = Relationship(
        id="r1", source_id="qin_liuxi", target_id="nonexistent",
        relation_type="parent_of",
    )
    result = validate_book_memory(memory)
    assert not result.is_valid
    assert any(
        "nonexistent" in str(err.value) for err in result.errors
    )


def test_cross_reference_unknown_entity_in_chapter_event():
    memory = BookMemory()
    memory.chapter_events[1] = ChapterEvent(
        chapter=1, entities_involved=["ghost_entity"],
    )
    result = validate_book_memory(memory)
    assert not result.is_valid


def test_book_memory_valid_full():
    """A well-formed BookMemory passes validation."""
    memory = BookMemory(book_title="Test", total_chapters=10)
    memory.entities["qin_liuxi"] = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
    )
    memory.entities["old_lady_qin"] = BookEntity(
        id="old_lady_qin", name_zh="秦老太太", name_en="Old Lady Qin",
        entity_type=EntityType.CHARACTER,
    )
    memory.relationships["r1"] = Relationship(
        id="r1", source_id="qin_liuxi", target_id="old_lady_qin",
        relation_type="parent_of",
    )
    memory.titles["young_lady"] = TitleRecord(
        id="young_lady", name_zh="大小姐", name_en="Young Lady",
    )
    memory.chapter_events[1] = ChapterEvent(
        chapter=1, entities_involved=["qin_liuxi"],
    )
    memory.translation_decisions["d1"] = TranslationDecision(
        id="d1", entity_id="young_lady", decision_type="rendering",
    )

    result = validate_book_memory(memory)
    assert result.is_valid


# ═════════════════════════════════════════════════════════════════════════
# Store tests
# ═════════════════════════════════════════════════════════════════════════


def test_in_memory_store():
    memory = BookMemory(book_title="Test")
    store = InMemoryBookMemoryStore(memory)
    assert store.exists()
    loaded = store.load()
    assert loaded is not None
    assert loaded.book_title == "Test"

    # Save a new memory
    new_memory = BookMemory(book_title="Updated")
    store.save(new_memory)
    assert store.load().book_title == "Updated"


def test_in_memory_store_empty():
    store = InMemoryBookMemoryStore()
    assert store.exists()
    assert store.load() is not None
    assert store.load().book_title == ""


def test_file_store_roundtrip(tmp_path):
    memory = BookMemory(book_title="File Test", total_chapters=5)
    memory.entities["qin_liuxi"] = BookEntity(
        id="qin_liuxi", name_zh="秦流西", name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
    )

    filepath = tmp_path / "book_memory.json"
    store = FileBookMemoryStore(filepath)
    store.save(memory)

    assert filepath.is_file()

    # Load in a new store instance
    store2 = FileBookMemoryStore(filepath)
    loaded = store2.load()
    assert loaded is not None
    assert loaded.book_title == "File Test"
    assert loaded.total_chapters == 5
    assert len(loaded.entities) == 1
    assert loaded.entities["qin_liuxi"].name_en == "Qin Liuxi"


def test_file_store_not_exists(tmp_path):
    filepath = tmp_path / "nonexistent.json"
    store = FileBookMemoryStore(filepath)
    assert not store.exists()
    assert store.load() is None


# ═════════════════════════════════════════════════════════════════════════
# Bootstrap from project_assets
# ═════════════════════════════════════════════════════════════════════════


def test_bootstrap_entities():
    """Parse characters.md-style content into BookEntity dict."""
    text = """### Qin Liuxi
- Chinese: 秦流西
- English rendering: Qin Liuxi
- Notes: Main character. Do not drift to "Qi Liuxi" or other variants.

### Old Lady Qin
- Chinese: 秦老太太
- English rendering: Old Lady Qin
"""
    entities = bootstrap_entities(text)
    assert len(entities) == 2
    assert "qin_liuxi" in entities
    assert entities["qin_liuxi"].name_en == "Qin Liuxi"
    assert entities["qin_liuxi"].entity_type == EntityType.CHARACTER
    assert entities["qin_liuxi"].status == MemoryRecordStatus.TENTATIVE
    assert "old_lady_qin" in entities


def test_bootstrap_titles():
    """Parse titles_and_terms.md-style content into TitleRecord dict."""
    text = """### 大小姐
- Chinese: 大小姐
- Working English rendering: Young Lady
- Notes: Household status term.
"""
    records = _bootstrap_titles(text, "title")
    assert len(records) == 1
    assert "young_lady" in records
    assert records["young_lady"].name_en == "Young Lady"
    assert records["young_lady"].category == "title"


def test_bootstrap_glossary_terms():
    """Parse glossary.md-style content into TitleRecord dict with category='term'."""
    text = """### 圣眷
- Chinese: 圣眷
- Working English rendering: imperial favor
"""
    records = _bootstrap_titles(text, "term")
    assert len(records) == 1
    assert "imperial_favor" in records
    assert records["imperial_favor"].category == "term"


def test_bootstrap_decisions():
    """Parse unresolved_decisions.md-style content."""
    text = """
## Open items

### 嬷嬷 system
- Current working choice: retain Momo
- Why unresolved: needs system-level decision

## Resolved items

### 嫡母
- Resolution: rendered as legal mother
- Rationale: preserves the legal-wife distinction
- Rejected alternatives: principal mother
- Date resolved: 2026-04-30
"""
    decisions, unresolved = bootstrap_decisions(text)
    assert len(unresolved) == 1
    # Chinese headings are not romanised; verify content, not id form
    unresolved_ids = list(unresolved.keys())
    assert len(unresolved_ids) == 1
    assert unresolved[unresolved_ids[0]].question == "嬷嬷 system"
    assert len(decisions) == 1
    assert "legal_mother" in decisions
    dec = decisions["legal_mother"]
    assert dec.new_value == "legal mother"
    assert dec.status == MemoryRecordStatus.TENTATIVE
    # entity_id must reference a known entity/title record ID, not raw heading text
    assert dec.entity_id == "legal_mother"


def test_bootstrap_from_project_assets():
    """Full bootstrap from real project_assets files."""
    memory = bootstrap_from_project_assets()

    # Should have entities from characters.md
    assert len(memory.entities) >= 1
    assert "qin_liuxi" in memory.entities

    # Should have titles from titles_and_terms.md
    assert len(memory.titles) >= 1

    # Should have decisions from unresolved_decisions.md
    assert len(memory.translation_decisions) >= 1 or len(memory.unresolved_decisions) >= 1


def test_bootstrap_roundtrip():
    """Bootstrap then round-trip through JSON."""
    memory = bootstrap_from_project_assets()
    d = book_memory_to_dict(memory)
    json_str = json.dumps(d, ensure_ascii=False)
    restored = book_memory_from_dict(json.loads(json_str))

    assert len(restored.entities) == len(memory.entities)
    assert len(restored.titles) == len(memory.titles)
    if memory.entities:
        eid = list(memory.entities.keys())[0]
        assert restored.entities[eid].name_en == memory.entities[eid].name_en


def test_bootstrap_decisions_are_tentative():
    """Bootstrap decisions must not be CONFIRMED — they come from markdown parsing,
    not from real translation-run validation."""
    memory = bootstrap_from_project_assets()
    for did, dec in memory.translation_decisions.items():
        assert dec.status == MemoryRecordStatus.TENTATIVE, (
            f"Bootstrap decision {did!r} is {dec.status}, expected TENTATIVE"
        )


def test_bootstrap_passes_cross_reference_validation():
    """The full bootstrapped BookMemory must pass validate_book_memory,
    including cross-reference checks (entity_id references)."""
    memory = bootstrap_from_project_assets()
    result = validate_book_memory(memory)
    if not result.is_valid:
        errors = [str(e) for e in result.errors]
        pytest.fail(f"Bootstrap validation failed: {errors}")


# ═════════════════════════════════════════════════════════════════════════
# Edge cases
# ═════════════════════════════════════════════════════════════════════════


def test_empty_book_memory_serialization():
    memory = BookMemory()
    d = book_memory_to_dict(memory)
    restored = book_memory_from_dict(d)
    assert restored.book_title == ""
    assert restored.version == "1.0.0"


def test_book_memory_with_place_entity():
    e = BookEntity(
        id="great_feng", name_zh="大灃", name_en="Great Feng",
        entity_type=EntityType.PLACE,
        description="Fictional dynasty",
    )
    assert e.entity_type == EntityType.PLACE
    d = entity_to_dict(e)
    restored = entity_from_dict(d)
    assert restored.entity_type == EntityType.PLACE
    assert restored.name_en == "Great Feng"


def test_entities_of_different_types():
    """Entities can be characters, places, factions, or institutions."""
    memory = BookMemory()
    memory.entities["char1"] = BookEntity(
        id="char1", name_zh="张三", name_en="Zhang San",
        entity_type=EntityType.CHARACTER,
    )
    memory.entities["place1"] = BookEntity(
        id="place1", name_zh="京城", name_en="Capital City",
        entity_type=EntityType.PLACE,
    )
    memory.entities["faction1"] = BookEntity(
        id="faction1", name_zh="秦家", name_en="Qin Clan",
        entity_type=EntityType.FACTION,
    )

    result = validate_book_memory(memory)
    assert result.is_valid


def test_chapter_event_invalid_chapter_zero():
    ce = ChapterEvent(chapter=0)
    result = validate_chapter_event(ce)
    assert not result.is_valid


def test_validation_accumulates_multiple_errors():
    e = BookEntity(
        id="", name_zh="", name_en="",
        entity_type=EntityType.CHARACTER,
    )
    result = validate_entity(e)
    # Should have at least 3 errors (id, name_zh, name_en)
    assert result.error_count >= 3
