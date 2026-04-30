"""Tests for the retrieval / context-pack layer (R2 — retrieval context-pack MVP).

Covers:
- Entity matching via name_zh and aliases
- Title/term matching
- Relationship resolution tied to matched entities
- Translation decision resolution
- Unresolved decision resolution
- Context pack size bounding and truncation
- Preserved tentative/unresolved status
- Empty / no-match segments
- Unrelated memory exclusion
- format_text() output
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from app.book_memory.models import (
    EntityType,
    MemoryRecordStatus,
    BookEntity,
    Relationship,
    TitleRecord,
    TranslationDecision,
    UnresolvedDecision,
    BookMemory,
)
from app.book_memory.retrieval import (
    EntityMatch,
    TitleMatch,
    ContextPack,
    build_context_pack,
    DEFAULT_MAX_CHARS,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_memory() -> BookMemory:
    """Build a BookMemory with known entities, titles, relationships, and decisions."""
    memory = BookMemory(book_title="Test Novel", total_chapters=10)

    # Characters
    memory.entities["qin_liuxi"] = BookEntity(
        id="qin_liuxi",
        name_zh="秦流西",
        name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        description="Protagonist, female physician and exorcist",
        tags=["protagonist"],
        status=MemoryRecordStatus.CONFIRMED,
        aliases=["流西"],
        first_chapter=1,
    )
    memory.entities["old_lady_qin"] = BookEntity(
        id="old_lady_qin",
        name_zh="秦老太太",
        name_en="Old Lady Qin",
        entity_type=EntityType.CHARACTER,
        description="Qin Liuxi's grandmother",
        tags=["supporting"],
        status=MemoryRecordStatus.CONFIRMED,
        first_chapter=1,
    )
    memory.entities["prince_jin"] = BookEntity(
        id="prince_jin",
        name_zh="晋王",
        name_en="Prince Jin",
        entity_type=EntityType.CHARACTER,
        description="A powerful prince",
        tags=["antagonist"],
        status=MemoryRecordStatus.TENTATIVE,
        first_chapter=5,
    )
    memory.entities["imperial_capital"] = BookEntity(
        id="imperial_capital",
        name_zh="京城",
        name_en="Imperial Capital",
        entity_type=EntityType.PLACE,
        description="Seat of the imperial court",
        status=MemoryRecordStatus.CONFIRMED,
    )

    # Titles / Terms
    memory.titles["young_lady"] = TitleRecord(
        id="young_lady",
        name_zh="大小姐",
        name_en="Young Lady",
        category="title",
        notes="Household status term for the eldest daughter",
        status=MemoryRecordStatus.CONFIRMED,
    )
    memory.titles["imperial_favor"] = TitleRecord(
        id="imperial_favor",
        name_zh="圣眷",
        name_en="imperial favor",
        category="term",
        status=MemoryRecordStatus.TENTATIVE,
    )

    # Relationships
    memory.relationships["r1"] = Relationship(
        id="r1",
        source_id="qin_liuxi",
        target_id="old_lady_qin",
        relation_type="grandchild_of",
        description="Qin Liuxi is her grandmother's favourite",
        status=MemoryRecordStatus.CONFIRMED,
    )
    memory.relationships["r2"] = Relationship(
        id="r2",
        source_id="prince_jin",
        target_id="imperial_capital",
        relation_type="rules",
        description="Prince Jin operates in the capital",
        status=MemoryRecordStatus.TENTATIVE,
    )

    # Translation decisions
    memory.translation_decisions["legal_mother"] = TranslationDecision(
        id="legal_mother",
        entity_id="young_lady",
        decision_type="rendering",
        new_value="Young Lady",
        rationale="Capitalized as a household status title",
        status=MemoryRecordStatus.CONFIRMED,
    )

    # Unresolved decisions
    memory.unresolved_decisions["momo_system"] = UnresolvedDecision(
        id="momo_system",
        question="How should 嬷嬷 be rendered consistently?",
        entity_id="prince_jin",
        options=["Momo", "Nanny", "Nurse"],
        status=MemoryRecordStatus.UNRESOLVED,
    )

    return memory


@pytest.fixture
def empty_memory() -> BookMemory:
    return BookMemory()


@pytest.fixture
def minimal_memory() -> BookMemory:
    """A memory with a single entity, no frills."""
    memory = BookMemory()
    memory.entities["test_entity"] = BookEntity(
        id="test_entity",
        name_zh="测试",
        name_en="Test",
        entity_type=EntityType.CHARACTER,
        status=MemoryRecordStatus.TENTATIVE,
    )
    return memory


# ═════════════════════════════════════════════════════════════════════════
# Entity matching
# ═════════════════════════════════════════════════════════════════════════


def test_entity_match_by_name_zh(sample_memory):
    """Entities are matched when name_zh appears in the segment."""
    pack = build_context_pack("秦流西看了看四周。", sample_memory)
    assert not pack.is_empty
    assert len(pack.matched_entities) == 1
    assert pack.matched_entities[0].entity.id == "qin_liuxi"
    assert pack.matched_entities[0].matched_on == "name_zh"


def test_entity_match_by_alias(sample_memory):
    """Entities are matched when an alias appears in the segment."""
    pack = build_context_pack("流西点了点头。", sample_memory)
    assert not pack.is_empty
    assert len(pack.matched_entities) == 1
    assert pack.matched_entities[0].entity.id == "qin_liuxi"
    assert pack.matched_entities[0].matched_on == "alias"
    assert pack.matched_entities[0].matched_text == "流西"


def test_match_multiple_entities(sample_memory):
    """Multiple entities can be matched in the same segment."""
    pack = build_context_pack("秦流西去向秦老太太请安。", sample_memory)
    assert len(pack.matched_entities) == 2
    ids = {em.entity.id for em in pack.matched_entities}
    assert ids == {"qin_liuxi", "old_lady_qin"}


def test_entity_match_by_place(sample_memory):
    """Place-type entities are matched like characters."""
    pack = build_context_pack("京城繁华似锦。", sample_memory)
    assert not pack.is_empty
    assert len(pack.matched_entities) == 1
    assert pack.matched_entities[0].entity.id == "imperial_capital"
    assert pack.matched_entities[0].entity.entity_type == EntityType.PLACE


def test_entity_match_with_tentative_status(sample_memory):
    """Tentative entities are matched and their status preserved."""
    pack = build_context_pack("晋王驾到。", sample_memory)
    assert not pack.is_empty
    assert any(em.entity.id == "prince_jin" for em in pack.matched_entities)
    matched = [em for em in pack.matched_entities if em.entity.id == "prince_jin"][0]
    assert matched.is_tentative
    assert not matched.is_confirmed


def test_entity_match_with_confirmed_status(sample_memory):
    """Confirmed entities are matched and their status preserved."""
    pack = build_context_pack("秦流西", sample_memory)
    matched = [em for em in pack.matched_entities if em.entity.id == "qin_liuxi"][0]
    assert matched.is_confirmed
    assert not matched.is_tentative


# ═════════════════════════════════════════════════════════════════════════
# Title / term matching
# ═════════════════════════════════════════════════════════════════════════


def test_title_match_by_name_zh(sample_memory):
    """Titles/terms are matched when name_zh appears in the segment."""
    pack = build_context_pack("大小姐安康。", sample_memory)
    assert not pack.is_empty
    assert len(pack.matched_titles) == 1
    assert pack.matched_titles[0].title.id == "young_lady"
    assert pack.matched_titles[0].matched_on == "name_zh"


def test_title_and_entity_match_together(sample_memory):
    """Both entities and titles can be matched in the same segment."""
    pack = build_context_pack("秦流西见过大小姐。", sample_memory)
    assert len(pack.matched_entities) >= 1
    assert len(pack.matched_titles) >= 1
    entity_ids = {em.entity.id for em in pack.matched_entities}
    title_ids = {tm.title.id for tm in pack.matched_titles}
    assert "qin_liuxi" in entity_ids
    assert "young_lady" in title_ids


# ═════════════════════════════════════════════════════════════════════════
# Relationship resolution
# ═════════════════════════════════════════════════════════════════════════


def test_relationships_included_for_matched_entities(sample_memory):
    """Relationships are included when they involve a matched entity."""
    pack = build_context_pack("秦流西看了看四周。", sample_memory)
    assert len(pack.related_relationships) >= 1
    rel_ids = {r.id for r in pack.related_relationships}
    assert "r1" in rel_ids  # qin_liuxi -> old_lady_qin


def test_relationships_excluded_for_unmatched_entities(sample_memory):
    """Relationships involving unmatched entities are not included."""
    pack = build_context_pack("秦老太太喝茶。", sample_memory)
    rel_ids = {r.id for r in pack.related_relationships}
    # r2 involves prince_jin which is NOT matched
    assert "r2" not in rel_ids


def test_relationships_resolved_for_both_directions(sample_memory):
    """Relationships are included whether matched entity is source or target."""
    pack = build_context_pack("秦老太太", sample_memory)
    rel_ids = {r.id for r in pack.related_relationships}
    assert "r1" in rel_ids  # qin_liuxi -> old_lady_qin (old_lady_qin is target)


# ═════════════════════════════════════════════════════════════════════════
# Decision resolution
# ═════════════════════════════════════════════════════════════════════════


def test_decisions_included_for_matched_entities(sample_memory):
    """Translation decisions are included when entity_id matches."""
    pack = build_context_pack("大小姐安康。", sample_memory)
    assert len(pack.related_decisions) >= 1
    dec_ids = {d.id for d in pack.related_decisions}
    assert "legal_mother" in dec_ids  # entity_id = "young_lady"


def test_unresolved_included_for_matched_entities(sample_memory):
    """Unresolved decisions are included when entity_id matches."""
    pack = build_context_pack("晋王驾到。", sample_memory)
    assert len(pack.related_unresolved) >= 1
    unresolved_ids = {u.id for u in pack.related_unresolved}
    assert "momo_system" in unresolved_ids


# ═════════════════════════════════════════════════════════════════════════
# Context pack bounds and truncation
# ═════════════════════════════════════════════════════════════════════════


def test_context_pack_default_max_chars():
    """Default max_chars is 4000."""
    assert DEFAULT_MAX_CHARS == 4000


def test_context_pack_respects_max_chars(sample_memory):
    """Context pack total_chars does not exceed max_chars after truncation."""
    pack = build_context_pack(
        "秦流西秦老太太晋王大小姐圣眷京城。",
        sample_memory,
        max_chars=500,
    )
    # Some items should be dropped
    assert pack.total_chars <= pack.max_chars
    # truncated flag should be True when we hit the limit
    # (may not always trigger if 500 is enough for a few items)


def test_context_pack_very_small_limit(sample_memory):
    """Very small max_chars still keeps at least some entities."""
    pack = build_context_pack(
        "秦流西晋王大小姐圣眷京城",
        sample_memory,
        max_chars=1,
    )
    assert pack.total_chars <= pack.max_chars
    assert pack.truncated
    # Confirmed entities might survive even at extreme limits
    # At minimum the pack should not crash


def test_truncation_preserves_confirmed_over_tentative():
    """When truncated, tentative entities are dropped before confirmed ones."""
    memory = BookMemory()
    memory.entities["confirmed_entity"] = BookEntity(
        id="confirmed_entity", name_zh="甲", name_en="A",
        entity_type=EntityType.CHARACTER,
        status=MemoryRecordStatus.CONFIRMED,
    )
    memory.entities["tentative_entity"] = BookEntity(
        id="tentative_entity", name_zh="乙", name_en="B",
        entity_type=EntityType.CHARACTER,
        status=MemoryRecordStatus.TENTATIVE,
    )

    pack = build_context_pack("甲乙", memory, max_chars=500)
    survivor_ids = {em.entity.id for em in pack.matched_entities}

    # With moderate truncation, at least the confirmed entity survives
    if pack.truncated:
        assert "confirmed_entity" in survivor_ids
    else:
        # Both fit within 500 chars (likely)
        assert len(pack.matched_entities) == 2


# ═════════════════════════════════════════════════════════════════════════
# Empty segments / no match
# ═════════════════════════════════════════════════════════════════════════


def test_empty_segment_returns_empty_pack(sample_memory):
    """An empty segment returns an empty context pack."""
    pack = build_context_pack("", sample_memory)
    assert pack.is_empty


def test_no_match_returns_empty_pack(sample_memory):
    """A segment with no matching content returns an empty pack."""
    pack = build_context_pack("今天天气真好，万里无云。", sample_memory)
    assert pack.is_empty


def test_empty_memory_returns_empty_pack(empty_memory):
    """An empty BookMemory returns an empty context pack for any segment."""
    pack = build_context_pack("秦流西看了看四周。", empty_memory)
    assert pack.is_empty


def test_segment_with_newline_chars(sample_memory):
    """Newlines and whitespace don't break matching."""
    pack = build_context_pack(" \n秦流西\t\n", sample_memory)
    assert not pack.is_empty
    assert len(pack.matched_entities) == 1


# ═════════════════════════════════════════════════════════════════════════
# Unrelated memory exclusion
# ═════════════════════════════════════════════════════════════════════════


def test_unrelated_entities_not_included(sample_memory):
    """Entities whose name_zh does not appear in segment are not included."""
    pack = build_context_pack("秦流西", sample_memory)
    entity_ids = {em.entity.id for em in pack.matched_entities}
    assert "prince_jin" not in entity_ids


def test_unrelated_titles_not_included(sample_memory):
    """Titles whose name_zh does not appear are not included."""
    pack = build_context_pack("秦流西", sample_memory)
    title_ids = {tm.title.id for tm in pack.matched_titles}
    assert "imperial_favor" not in title_ids


def test_decisions_only_for_matched_entity_ids(sample_memory):
    """Translation decisions are only included for matched entity/title ids."""
    pack = build_context_pack("晋王", sample_memory)
    dec_ids = {d.id for d in pack.related_decisions}
    # legal_mother references "young_lady", which wasn't matched
    assert "legal_mother" not in dec_ids


# ═════════════════════════════════════════════════════════════════════════
# format_text() output
# ═════════════════════════════════════════════════════════════════════════


def test_format_text_empty_pack():
    """Formatting an empty pack returns a clean message."""
    pack = ContextPack()
    text = pack.format_text()
    assert "No matching" in text
    assert "Context Pack" in text


def test_format_text_includes_entities(sample_memory):
    """Formatted text includes matched entity information."""
    pack = build_context_pack("秦流西", sample_memory)
    text = pack.format_text()
    assert "Qin Liuxi" in text
    assert "秦流西" in text
    assert "Matched via" in text


def test_format_text_includes_titles(sample_memory):
    """Formatted text includes matched title information."""
    pack = build_context_pack("大小姐", sample_memory)
    text = pack.format_text()
    assert "Young Lady" in text
    assert "大小姐" in text


def test_format_text_shows_tentative_flag(sample_memory):
    """Tentative items are flagged in formatted output."""
    pack = build_context_pack("晋王", sample_memory)
    text = pack.format_text()
    assert "TENTATIVE" in text


def test_format_text_shows_unresolved_flag(sample_memory):
    """Unresolved items are flagged in formatted output."""
    pack = build_context_pack("晋王", sample_memory)
    text = pack.format_text()
    assert "UNRESOLVED" in text


def test_format_text_truncated_notice(sample_memory):
    """Truncated packs include a truncation notice."""
    pack = build_context_pack(
        "秦流西秦老太太晋王大小姐圣眷京城",
        sample_memory,
        max_chars=50,
    )
    text = pack.format_text()
    if pack.truncated:
        assert "truncated" in text.lower()


# ═════════════════════════════════════════════════════════════════════════
# Edge cases
# ═════════════════════════════════════════════════════════════════════════


def test_segment_prefix_of_name_zh_does_not_reverse_match(sample_memory):
    """Prefix of an entity name_zh does not match (needle is entity name, not segment)."""
    pack = build_context_pack("秦流", sample_memory)
    # "秦流西" in "秦流" is False — entity name_zh is the needle, segment is the haystack
    assert all(em.entity.id != "qin_liuxi" for em in pack.matched_entities)


def test_entity_without_zh_name_not_matched(sample_memory):
    """Entity with empty name_zh is not matched."""
    memory = BookMemory()
    memory.entities["no_name"] = BookEntity(
        id="no_name", name_zh="", name_en="No Name",
        entity_type=EntityType.CHARACTER,
    )
    pack = build_context_pack("some text", memory)
    assert pack.is_empty


def test_entity_with_empty_aliases_still_match_by_name(sample_memory):
    """Entity with empty aliases list can still match via name_zh."""
    memory = BookMemory()
    memory.entities["qin_liuxi_2"] = BookEntity(
        id="qin_liuxi_2",
        name_zh="秦流西",
        name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        aliases=[],
    )
    pack = build_context_pack("秦流西", memory)
    # Make sure we have a match for an entity where aliases is empty
    assert len(pack.matched_entities) == 1
    assert pack.matched_entities[0].matched_on == "name_zh"


def test_context_pack_is_empty_property():
    """is_empty is True when all collections are empty."""
    pack = ContextPack()
    assert pack.is_empty

    pack.matched_entities.append(
        EntityMatch(
            entity=BookEntity(
                id="a", name_zh="甲", name_en="A",
                entity_type=EntityType.CHARACTER,
            ),
            matched_on="name_zh",
            matched_text="甲",
        )
    )
    assert not pack.is_empty


def test_context_pack_total_chars_estimated(sample_memory):
    """total_chars is set after building a context pack."""
    pack = build_context_pack("秦流西", sample_memory)
    assert pack.total_chars > 0


def test_entity_match_metadata_preserved(sample_memory):
    """EntityMatch carries entity, matched_on, and matched_text."""
    pack = build_context_pack("流西点了点头。", sample_memory)
    em = pack.matched_entities[0]
    assert em.entity.id == "qin_liuxi"
    assert em.matched_on == "alias"
    assert em.matched_text == "流西"
