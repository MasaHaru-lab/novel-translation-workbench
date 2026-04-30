"""Tests for chapter-level consistency audit and correction (Batch 3)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.chapter.consistency import (
    ChapterConsistencyAuditor,
    ChapterCorrector,
    ConsistencyAudit,
    ConsistencyIssue,
    ConsistencyIssueCategory,
    ConsistencyReference,
    CharacterRef,
    TitleRef,
    GlossaryRef,
    CorrectionAction,
    CorrectionSummary,
    build_consistency_reference,
    run_consistency_pass,
    _ends_sentence_cleanly,
    _parse_character_refs,
    _parse_title_refs,
    _parse_glossary_refs,
)
from app.chapter.models import ChapterResult
from app.chapter.manifest import ChapterStatus, SegmentStatus


# ═════════════════════════════════════════════════════════════════════════
# Reference parsing
# ═════════════════════════════════════════════════════════════════════════


def test_parse_character_refs():
    """Parse canonical renderings and variant hints from characters.md."""
    text = """### Qin Liuxi
- Chinese: 秦流西
- English rendering: Qin Liuxi
- Notes: Do not drift to "Qi Liuxi" or other variants.

### Old Lady Qin
- Chinese: 秦老太太
- English rendering: Old Lady Qin
"""
    refs = _parse_character_refs(text)
    assert len(refs) == 2
    assert refs[0].canonical == "Qin Liuxi"
    assert "Qi Liuxi" in refs[0].variants
    assert refs[1].canonical == "Old Lady Qin"
    assert refs[1].variants == []


def test_parse_title_refs():
    """Parse title renderings from titles_and_terms.md."""
    text = """### 大小姐
- Chinese: 大小姐
- Working English rendering: Young Lady
- Notes: Keep as "Young Lady" for now.

### 贵妃
- Chinese: 贵妃
- Working English rendering: Noble Consort
"""
    refs = _parse_title_refs(text)
    assert len(refs) == 2
    assert refs[0].canonical == "Young Lady"
    assert refs[1].canonical == "Noble Consort"


def test_parse_glossary_refs():
    """Parse glossary term renderings from glossary.md."""
    text = """### 圣眷
- Chinese: 圣眷
- Working English rendering: imperial favor
- Notes: Keep stable.

### 命格
- Chinese: 命格
- Working English rendering: fate pattern
"""
    refs = _parse_glossary_refs(text)
    assert len(refs) == 2
    assert refs[0].canonical == "imperial favor"
    assert refs[1].canonical == "fate pattern"


def test_build_consistency_reference():
    """build_consistency_reference should load from real asset files."""
    ref = build_consistency_reference()
    # We expect at least the characters, titles, and glossary terms from assets
    assert len(ref.characters) >= 1
    assert len(ref.titles) >= 1
    assert len(ref.glossary_terms) >= 1
    # Qin Liuxi should be present
    names = [c.canonical for c in ref.characters]
    assert "Qin Liuxi" in names


# ═════════════════════════════════════════════════════════════════════════
# Data models
# ═════════════════════════════════════════════════════════════════════════


def test_consistency_audit_empty():
    audit = ConsistencyAudit(chapter_title="Test")
    assert not audit.has_issues
    assert audit.issue_count == 0
    assert audit.count_by_category() == {}


def test_consistency_audit_with_issues():
    issues = [
        ConsistencyIssue(
            category=ConsistencyIssueCategory.NAME_VARIANT,
            segment_id="1", term="Qin Liuxi",
            found="Qi Liuxi", expected="Qin Liuxi",
            auto_fixable=True,
        ),
        ConsistencyIssue(
            category=ConsistencyIssueCategory.TITLE_VARIANT,
            segment_id="2", term="Young Lady",
            found="young lady", expected="Young Lady",
            auto_fixable=True,
        ),
    ]
    audit = ConsistencyAudit(
        issues=issues, chapter_title="Test", total_segments=3,
    )
    assert audit.has_issues
    assert audit.issue_count == 2
    by_cat = audit.count_by_category()
    assert by_cat["name_variant"] == 1
    assert by_cat["title_variant"] == 1
    assert audit.get_summary()["total_issues"] == 2
    assert audit.get_summary()["auto_fixable"] == 2
    assert audit.get_summary()["auto_fixed"] == 0


def test_correction_summary():
    actions = [
        CorrectionAction(
            category=ConsistencyIssueCategory.NAME_VARIANT,
            segment_id="1", old_text="Qi Liuxi", new_text="Qin Liuxi",
        ),
    ]
    summary = CorrectionSummary(actions=actions, total_replaced=1)
    assert summary.has_corrections
    assert summary.correction_count == 1
    s = summary.get_summary()
    assert s["total_corrections"] == 1
    assert s["total_replacements"] == 1


# ═════════════════════════════════════════════════════════════════════════
# Audit: character name drift
# ═════════════════════════════════════════════════════════════════════════


def _make_test_reference():
    """Create a ConsistencyReference with known test data."""
    return ConsistencyReference(
        characters=[
            CharacterRef(canonical="Qin Liuxi", variants=["Qi Liuxi"]),
            CharacterRef(canonical="Old Lady Qin", variants=["Old Madam Qin"]),
            CharacterRef(canonical="Lady Wang", variants=["Madam Wang"]),
        ],
        titles=[
            TitleRef(canonical="Young Lady", variants=["young lady"]),
            TitleRef(canonical="Noble Consort", variants=["Imperial Consort"]),
            TitleRef(canonical="principal mother", variants=["principal mother"]),
        ],
        glossary_terms=[
            GlossaryRef(canonical="imperial favor", variants=["imperial favour"]),
            GlossaryRef(canonical="fate pattern", variants=[]),
        ],
    )


def test_audit_detects_name_variant():
    """Audit should detect a known character name variant."""
    ref = _make_test_reference()
    auditor = ChapterConsistencyAuditor(ref)

    segment_texts = [
        ("1", "Qin Liuxi walked through the garden."),
        ("2", "Qi Liuxi entered the hall."),
    ]
    aggregated = "# Test\n\nQin Liuxi walked through the garden.\n\nQi Liuxi entered the hall."
    audit = auditor.audit(aggregated, "Test", segment_texts)

    name_issues = audit.issues_by_category(ConsistencyIssueCategory.NAME_VARIANT)
    assert len(name_issues) >= 1
    # At least one should be the "Qi Liuxi" variant
    qi_issues = [i for i in name_issues if "Qi Liuxi" in i.found]
    assert len(qi_issues) >= 1
    assert qi_issues[0].auto_fixable is True
    assert qi_issues[0].segment_id == "2"


def test_audit_detects_title_variant():
    """Audit should detect a known title variant."""
    ref = _make_test_reference()
    auditor = ChapterConsistencyAuditor(ref)

    segment_texts = [
        ("1", "Young Lady Wang received the guests."),
        ("2", "The young lady stepped forward."),
    ]
    aggregated = "# Test\n\nYoung Lady Wang received the guests.\n\nThe young lady stepped forward."
    audit = auditor.audit(aggregated, "Test", segment_texts)

    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_VARIANT)
    assert len(title_issues) >= 1
    # "young lady" (lowercase) should be flagged as a variant
    lower_issues = [i for i in title_issues if i.found == "young lady"]
    assert len(lower_issues) >= 1


def test_audit_no_false_positive_when_canonical_present():
    """When canonical form is present in a segment, variants that are actually
    part of the canonical rendering should not be double-flagged."""
    ref = _make_test_reference()
    auditor = ChapterConsistencyAuditor(ref)

    # The canonical "Qin Liuxi" is present — no variants should be flagged
    # since "Qi Liuxi" (the only explicit variant) is not in the text.
    segment_texts = [
        ("1", "Qin Liuxi looked up at the sky."),
    ]
    audit = auditor.audit("# Test", "Test", segment_texts)
    name_issues = audit.issues_by_category(ConsistencyIssueCategory.NAME_VARIANT)
    # No explicit variant "Qi Liuxi" is present, and we no longer derive
    # partial-word variants from multi-word names (too many false positives).
    assert len(name_issues) == 0


def test_audit_skips_canonical_only_text():
    """When all text uses canonical renderings, no issues should be raised."""
    ref = _make_test_reference()
    auditor = ChapterConsistencyAuditor(ref)

    segment_texts = [
        ("1", "Qin Liuxi walked through the garden."),
        ("2", "Old Lady Qin sat by the window."),
        ("3", "Lady Wang served tea."),
    ]
    audit = auditor.audit("# Test", "Test", segment_texts)
    name_issues = audit.issues_by_category(ConsistencyIssueCategory.NAME_VARIANT)
    # "Liuxi" alone would be flagged as a partial reference (not canonical
    # "Qin Liuxi"), but since it's in a different segment, it depends on
    # whether the canonical form appears in that same segment.
    # In segment 1, "Qin Liuxi" is the canonical form and "Liuxi" is not present alone.
    # Let's check more carefully...
    fixable_issues = [i for i in name_issues if i.auto_fixable]
    assert len(fixable_issues) == 0


# ═════════════════════════════════════════════════════════════════════════
# Audit: title format
# ═════════════════════════════════════════════════════════════════════════


def test_audit_title_format_correct():
    """No issue when the first non-empty line is a translated heading.

    Heading shape (with or without leading ``#``) is the segment-level
    translator's responsibility per the chapter Markdown output format
    contract. The consistency audit must not flag a well-formed English
    first line.
    """
    auditor = ChapterConsistencyAuditor()
    audit = auditor.audit("# Chapter 1", "Chapter 1", [])
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) == 0


def test_audit_title_format_no_heading_marker_is_ok():
    """A plain English first line (no ``#``) is not a TITLE_FORMAT issue.

    The orchestrator does not inject a heading; whatever the segment-level
    translator produced is the visible heading. A plain English first
    line is contract-compliant and must not be flagged.
    """
    auditor = ChapterConsistencyAuditor()
    audit = auditor.audit("Chapter 1\n\ncontent.", "Chapter 1", [])
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) == 0


def test_audit_title_format_chinese_metadata_does_not_false_positive():
    """Chinese ``chapter_title`` metadata + English first line is OK.

    This is the realistic case: ``ChapterPlan.chapter_title`` carries the
    raw Chinese source title (``"第一章"``), while the segment-level
    translator produces an English heading (``"# Chapter 1"``). The
    consistency audit must NOT propose to overwrite the English first
    line with the Chinese metadata — that would corrupt the output.
    """
    auditor = ChapterConsistencyAuditor()
    audit = auditor.audit(
        "# Chapter 1: The Arrival\n\nShe walked into the room.",
        "第一章 到来",
        [],
    )
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) == 0


def test_audit_title_format_chinese_leak_flagged_not_autofixed():
    """When the raw Chinese source title leaks into the first line, flag
    it but do NOT mark it auto_fixable.

    A leaked source title is a structural translation failure; mechanical
    string replacement cannot recover the missing English heading.
    """
    auditor = ChapterConsistencyAuditor()
    audit = auditor.audit(
        "# 第一章\n\nShe walked into the room.",
        "第一章",
        [],
    )
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) == 1
    assert title_issues[0].auto_fixable is False


def test_audit_title_format_chinese_leak_without_hash():
    """Leaked title is detected even without a leading ``#`` marker."""
    auditor = ChapterConsistencyAuditor()
    audit = auditor.audit(
        "第一章\n\nShe walked into the room.",
        "第一章",
        [],
    )
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) == 1
    assert title_issues[0].auto_fixable is False


def test_audit_title_format_empty():
    """Issue raised when aggregated text is empty (and not auto-fixable)."""
    auditor = ChapterConsistencyAuditor()
    audit = auditor.audit("", "Chapter 1", [])
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) >= 1
    assert title_issues[0].auto_fixable is False


def test_corrector_does_not_corrupt_english_heading_with_chinese_metadata():
    """Regression: a leaked-title issue must not cause the corrector to
    overwrite the English first line with raw Chinese metadata.

    Before Batch 5A, ``_check_title_format`` raised an auto-fixable issue
    whenever the first line did not match ``# {chapter_title}`` literally.
    With Chinese ``chapter_title`` metadata that meant the corrector
    would replace the model's English heading with the raw source
    title — corrupting the chapter.
    """
    auditor = ChapterConsistencyAuditor()
    corrector = ChapterCorrector()
    aggregated = "# Chapter 1: The Arrival\n\nShe walked into the room."
    audit = auditor.audit(aggregated, "第一章 到来", [])

    corrected, summary = corrector.correct(aggregated, audit)

    assert corrected == aggregated
    assert "第一章" not in corrected
    assert "Chapter 1: The Arrival" in corrected
    assert not summary.has_corrections


# ═════════════════════════════════════════════════════════════════════════
# Audit: segment boundary
# ═════════════════════════════════════════════════════════════════════════


def test_audit_detects_boundary_overlap():
    """Detect repeated content at segment boundary."""
    ref = _make_test_reference()
    auditor = ChapterConsistencyAuditor(ref)

    tail = "She walked toward the main gate of the courtyard and stopped. " * 10
    head = "She walked toward the main gate of the courtyard and stopped. She took a deep breath." * 10
    segment_texts = [
        ("1", tail),
        ("2", head),
    ]
    audit = auditor.audit("# Test", "Test", segment_texts)
    boundary_issues = audit.issues_by_category(ConsistencyIssueCategory.SEGMENT_BOUNDARY)
    # The overlap "She walked toward the main gate of the courtyard and stopped." is > 30 chars
    assert len(boundary_issues) >= 1


def test_audit_clean_boundary():
    """No boundary issue when segments flow naturally."""
    ref = _make_test_reference()
    auditor = ChapterConsistencyAuditor(ref)

    segment_texts = [
        ("1", "She walked through the garden gate."),
        ("2", "Inside, the air was cool and still."),
    ]
    audit = auditor.audit("# Test", "Test", segment_texts)
    boundary_issues = audit.issues_by_category(ConsistencyIssueCategory.SEGMENT_BOUNDARY)
    assert len(boundary_issues) == 0


# ═════════════════════════════════════════════════════════════════════════
# Truncation detection
# ═════════════════════════════════════════════════════════════════════════


class TestEndsSentenceCleanly:
    """Unit tests for the _ends_sentence_cleanly helper."""

    def test_empty_text(self):
        assert not _ends_sentence_cleanly("")

    def test_whitespace_only(self):
        assert not _ends_sentence_cleanly("   ")

    def test_none_input(self):
        assert not _ends_sentence_cleanly(None)

    def test_ends_with_period(self):
        assert _ends_sentence_cleanly("She walked in.")

    def test_ends_with_question_mark(self):
        assert _ends_sentence_cleanly("Are you coming?")

    def test_ends_with_exclamation(self):
        assert _ends_sentence_cleanly("Watch out!")

    def test_ends_with_ellipsis(self):
        assert _ends_sentence_cleanly("She hesitated…")

    def test_ends_with_em_dash(self):
        assert _ends_sentence_cleanly("He turned—")

    def test_ends_with_cjk_period(self):
        assert _ends_sentence_cleanly("她走进来了。")

    def test_ends_with_dialogue_quote(self):
        """A closing double-quote after punctuation counts as clean."""
        assert _ends_sentence_cleanly('"I agree."')

    def test_ends_with_bare_quote(self):
        """A bare closing quote (no prior sentence punctuation) counts as clean."""
        assert _ends_sentence_cleanly('She said, "',)

    def test_ends_with_cjk_closing_bracket(self):
        assert _ends_sentence_cleanly("「我知道了」")

    def test_ends_with_letter_truncated(self):
        """Ending with an ASCII letter is a truncation signal."""
        assert not _ends_sentence_cleanly("She walked into the room and")

    def test_ends_with_cjk_truncated(self):
        """Ending with a CJK character suggests truncation."""
        assert not _ends_sentence_cleanly("她走进")

    def test_ends_with_comma_truncated(self):
        """Ending with a comma suggests mid-sentence cut."""
        assert not _ends_sentence_cleanly("She walked in,")

    def test_ends_with_semicolon(self):
        assert not _ends_sentence_cleanly("She waited;")

    def test_ends_with_digit(self):
        assert not _ends_sentence_cleanly("Chapter 1")

    def test_ends_with_newline_clean(self):
        """Trailing newline is stripped; actual last char is checked."""
        assert _ends_sentence_cleanly("She walked in.\n")

    def test_trailing_whitespace_stripped(self):
        assert _ends_sentence_cleanly("She walked in.  ")


class TestAuditTruncation:
    """Integration tests for truncation detection in the consistency auditor."""

    def test_audit_detects_truncated_segment(self):
        """A segment ending mid-word should be flagged."""
        ref = _make_test_reference()
        auditor = ChapterConsistencyAuditor(ref)

        segment_texts = [
            ("1", "She walked into the room and looked around carefully"),
            ("2", "The old woman sat by the window, her hands folded."),
        ]
        audit = auditor.audit("# Test", "Test", segment_texts)
        boundary_issues = audit.issues_by_category(
            ConsistencyIssueCategory.SEGMENT_BOUNDARY
        )
        truncation_issues = [
            i for i in boundary_issues if "truncated" in i.detail.lower()
        ]
        assert len(truncation_issues) == 1
        assert truncation_issues[0].segment_id == "1"
        assert not truncation_issues[0].auto_fixable

    def test_audit_clean_all_segments(self):
        """No truncation issues when all segments end properly."""
        ref = _make_test_reference()
        auditor = ChapterConsistencyAuditor(ref)

        segment_texts = [
            ("1", "Qin Liuxi walked through the garden."),
            ("2", "Old Lady Qin sat by the window."),
            ("3", "Lady Wang served tea."),
        ]
        audit = auditor.audit("# Test", "Test", segment_texts)
        truncation_issues = [
            i for i in audit.issues
            if i.category == ConsistencyIssueCategory.SEGMENT_BOUNDARY
            and "truncated" in i.detail.lower()
        ]
        assert len(truncation_issues) == 0

    def test_audit_truncated_multiple_segments(self):
        """Multiple truncated segments are each flagged separately."""
        ref = _make_test_reference()
        auditor = ChapterConsistencyAuditor(ref)

        segment_texts = [
            ("1", "She walked into the room and"),
            ("2", "The old woman looked up and"),
            ("3", "Lady Wang served tea."),
        ]
        audit = auditor.audit("# Test", "Test", segment_texts)
        truncation_issues = [
            i for i in audit.issues
            if i.category == ConsistencyIssueCategory.SEGMENT_BOUNDARY
            and "truncated" in i.detail.lower()
        ]
        assert len(truncation_issues) == 2
        seg_ids = {i.segment_id for i in truncation_issues}
        assert seg_ids == {"1", "2"}

    def test_audit_truncation_provides_context_snippet(self):
        """Truncation issues should include a useful context snippet."""
        ref = _make_test_reference()
        auditor = ChapterConsistencyAuditor(ref)

        segment_texts = [
            ("1", "She walked into the room"),
            ("2", "and sat down."),
        ]
        audit = auditor.audit("# Test", "Test", segment_texts)
        truncation_issues = [
            i for i in audit.issues
            if i.category == ConsistencyIssueCategory.SEGMENT_BOUNDARY
            and "truncated" in i.detail.lower()
        ]
        assert len(truncation_issues) == 1
        snippet = truncation_issues[0].context_snippet
        assert len(snippet) > 0
        assert "walked into the room" in snippet

    def test_audit_truncation_with_cjk_characters(self):
        """CJK text ending mid-sentence should be flagged."""
        ref = _make_test_reference()
        auditor = ChapterConsistencyAuditor(ref)

        segment_texts = [
            ("1", "她走进房间里，看着四周"),
            ("2", "然后坐了下来。"),
        ]
        audit = auditor.audit("# Test", "Test", segment_texts)
        truncation_issues = [
            i for i in audit.issues
            if i.category == ConsistencyIssueCategory.SEGMENT_BOUNDARY
            and "truncated" in i.detail.lower()
        ]
        assert len(truncation_issues) == 1
        assert truncation_issues[0].segment_id == "1"


# ═════════════════════════════════════════════════════════════════════════
# Correction pass
# ═════════════════════════════════════════════════════════════════════════


def test_corrector_fixes_known_variants():
    """Corrector should replace known variants with canonical forms."""
    ref = _make_test_reference()
    auditor = ChapterConsistencyAuditor(ref)
    corrector = ChapterCorrector(ref)

    text = "# Chapter 1\n\nQi Liuxi walked through the garden.\n\nOld Madam Qin sat inside."
    segment_texts = [
        ("1", "Qi Liuxi walked through the garden."),
        ("2", "Old Madam Qin sat inside."),
    ]
    audit = auditor.audit(text, "Chapter 1", segment_texts)
    corrected, summary = corrector.correct(text, audit)

    assert "Qi Liuxi" not in corrected
    assert "Qin Liuxi" in corrected
    assert "Old Madam Qin" not in corrected
    assert "Old Lady Qin" in corrected
    assert summary.has_corrections
    assert summary.total_replaced >= 2


def test_corrector_does_not_touch_clean_text():
    """Corrector should not modify text with no auto-fixable issues."""
    ref = _make_test_reference()
    corrector = ChapterCorrector(ref)

    text = "# Chapter 1\n\nQin Liuxi walked through the garden."
    audit = ConsistencyAudit(chapter_title="Test", total_segments=1)
    corrected, summary = corrector.correct(text, audit)

    assert corrected == text
    assert not summary.has_corrections


def test_corrector_no_prose_rewriting():
    """Corrector must NOT rewrite prose — only do term replacement."""
    ref = _make_test_reference()
    corrector = ChapterCorrector(ref)

    text = "# Chapter 1\n\nQi Liuxi walked through the garden."
    audit = ConsistencyAudit(
        issues=[
            ConsistencyIssue(
                category=ConsistencyIssueCategory.NAME_VARIANT,
                segment_id="1", term="Qin Liuxi",
                found="Qi Liuxi", expected="Qin Liuxi",
                auto_fixable=True,
            ),
        ],
        chapter_title="Test",
        total_segments=1,
    )
    corrected, summary = corrector.correct(text, audit)

    # Only the name should change, nothing else
    assert corrected == "# Chapter 1\n\nQin Liuxi walked through the garden."
    assert summary.total_replaced == 1


def test_corrector_handles_multiple_occurrences():
    """All occurrences of a variant should be replaced."""
    ref = _make_test_reference()
    corrector = ChapterCorrector(ref)

    text = "Qi Liuxi said hello. Then Qi Liuxi waved."
    audit = ConsistencyAudit(
        issues=[
            ConsistencyIssue(
                category=ConsistencyIssueCategory.NAME_VARIANT,
                segment_id="1", term="Qin Liuxi",
                found="Qi Liuxi", expected="Qin Liuxi",
                auto_fixable=True,
            ),
        ],
    )
    corrected, summary = corrector.correct(text, audit)

    assert corrected == "Qin Liuxi said hello. Then Qin Liuxi waved."
    assert summary.total_replaced == 2


def test_corrector_longer_matches_first():
    """Longer variant strings should be matched before shorter ones."""
    ref = _make_test_reference()
    corrector = ChapterCorrector(ref)

    text = "Old Madam Qin sat. Madam Qin served tea."
    audit = ConsistencyAudit(
        issues=[
            ConsistencyIssue(
                category=ConsistencyIssueCategory.NAME_VARIANT,
                segment_id="1", term="Old Lady Qin",
                found="Madam Qin", expected="Old Lady Qin",
                auto_fixable=True,
            ),
            ConsistencyIssue(
                category=ConsistencyIssueCategory.NAME_VARIANT,
                segment_id="2", term="Old Lady Qin",
                found="Old Madam Qin", expected="Old Lady Qin",
                auto_fixable=True,
            ),
        ],
    )
    corrected, summary = corrector.correct(text, audit)

    # Both variants should be corrected
    assert "Old Madam Qin" not in corrected
    assert "Madam Qin" not in corrected
    assert corrected.count("Old Lady Qin") == 2


def test_corrector_marks_issues_as_fixed():
    """Corrector should update audit issues to reflect what was fixed."""
    ref = _make_test_reference()
    auditor = ChapterConsistencyAuditor(ref)
    corrector = ChapterCorrector(ref)

    text = "Qi Liuxi walked in."
    segment_texts = [("1", "Qi Liuxi walked in.")]
    audit = auditor.audit(text, "Test", segment_texts)
    corrected, summary = corrector.correct(text, audit)

    # The audit issues should now have auto_fixed=True
    fixed_issues = [i for i in audit.issues if i.auto_fixed]
    assert len(fixed_issues) >= 1


# ═════════════════════════════════════════════════════════════════════════
# run_consistency_pass (end-to-end)
# ═════════════════════════════════════════════════════════════════════════


def test_run_consistency_pass_detects_and_fixes():
    """End-to-end: audit detects issues, correction fixes them."""
    ref = _make_test_reference()

    aggregated = "# Chapter 1\n\nQi Liuxi walked through the garden.\n\nOld Madam Qin sat inside.\n\nThe young lady entered."
    segment_texts = [
        ("1", "Qi Liuxi walked through the garden."),
        ("2", "Old Madam Qin sat inside."),
        ("3", "The young lady entered."),
    ]

    corrected, audit, correction = run_consistency_pass(
        aggregated_text=aggregated,
        chapter_title="Chapter 1",
        segment_texts=segment_texts,
        reference=ref,
    )

    # Audit should find issues
    assert audit.has_issues
    assert audit.get_summary()["total_issues"] > 0

    # Correction should fix auto-fixable issues
    assert correction.has_corrections
    assert "Qi Liuxi" not in corrected
    assert "Qin Liuxi" in corrected
    assert "Old Madam Qin" not in corrected
    assert "Old Lady Qin" in corrected

    # Title format is correct, so no issues there
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) == 0


def test_run_consistency_pass_clean_text():
    """Clean text should pass through unchanged."""
    ref = _make_test_reference()

    aggregated = "# Chapter 1\n\nQin Liuxi walked through the garden.\n\nOld Lady Qin sat inside."
    segment_texts = [
        ("1", "Qin Liuxi walked through the garden."),
        ("2", "Old Lady Qin sat inside."),
    ]

    corrected, audit, correction = run_consistency_pass(
        aggregated_text=aggregated,
        chapter_title="Chapter 1",
        segment_texts=segment_texts,
        reference=ref,
    )

    # No auto-fixable issues
    assert not correction.has_corrections
    # Corrected text should be identical
    assert corrected == aggregated


# ═════════════════════════════════════════════════════════════════════════
# ChapterResult integration
# ═════════════════════════════════════════════════════════════════════════


def test_chapter_result_consistency_fields():
    """ChapterResult should carry consistency audit and correction fields."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit={
            "total_issues": 2,
            "by_category": {"name_variant": 1, "title_variant": 1},
            "auto_fixable": 2,
            "auto_fixed": 2,
        },
        correction_summary={
            "total_corrections": 2,
            "total_replacements": 3,
        },
        corrected_translation="Corrected chapter text.",
    )

    assert result.consistency_audit["total_issues"] == 2
    assert result.correction_summary["total_corrections"] == 2
    assert result.corrected_translation == "Corrected chapter text."


def test_chapter_result_final_translation_prefers_corrected():
    """final_translation should prefer corrected version when available."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="Original text.",
        corrected_translation="Corrected text.",
    )
    assert result.final_translation == "Corrected text."


def test_chapter_result_final_translation_fallback():
    """final_translation should fall back to aggregated when no correction."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="Original text.",
    )
    assert result.final_translation == "Original text."


# ═════════════════════════════════════════════════════════════════════════
# Boundary: correction limits
# ═════════════════════════════════════════════════════════════════════════


def test_corrector_does_not_introduce_new_content():
    """Corrector must not introduce text that wasn't in the original."""
    ref = _make_test_reference()
    corrector = ChapterCorrector(ref)

    original = "# Chapter 1\n\nQi Liuxi stood up."
    audit = ConsistencyAudit(
        issues=[
            ConsistencyIssue(
                category=ConsistencyIssueCategory.NAME_VARIANT,
                segment_id="1", term="Qin Liuxi",
                found="Qi Liuxi", expected="Qin Liuxi",
                auto_fixable=True,
            ),
        ],
    )
    corrected, _ = corrector.correct(original, audit)

    # The correction should only replace "Qi Liuxi" with "Qin Liuxi"
    # No new sentences, no additional words
    assert corrected.count("Qin Liuxi") == 1
    assert corrected.count(" ") == original.count(" ")  # same word count
    assert corrected.endswith("stood up.")


def test_non_fixable_issues_not_corrected():
    """Issues marked as not auto-fixable should NOT be corrected."""
    ref = _make_test_reference()
    corrector = ChapterCorrector(ref)

    text = "Liuxi walked through the garden."
    audit = ConsistencyAudit(
        issues=[
            ConsistencyIssue(
                category=ConsistencyIssueCategory.NAME_VARIANT,
                segment_id="1", term="Qin Liuxi",
                found="Liuxi", expected="Qin Liuxi",
                auto_fixable=False,  # partial name, not safe to auto-fix
            ),
        ],
    )
    corrected, summary = corrector.correct(text, audit)

    # Should NOT have been corrected since it's not auto-fixable
    assert "Liuxi" in corrected
    assert not summary.has_corrections
