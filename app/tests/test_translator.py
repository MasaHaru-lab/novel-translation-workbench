import sys
import os
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.translate.schema import TranslationInput, TranslationOutput, GlossaryTerm
from app.translate.translator import (
    apply_glossary,
    translate_draft,
    polish_translation,
    build_translation_input,
    build_polish_prompt,
    build_draft_prompt,
    build_review_prompt,
    clean_polished_output,
    parse_review_findings,
    ReviewFindings,
    check_segment_coverage,
)
from app.segment.segmenter import Segment


REVIEWER_SCAFFOLD_KEYS = (
    "major_issue",
    "why_it_matters",
    "recommended_fix",
    "optional_notes",
)


def _assert_no_reviewer_scaffolding(text: str) -> None:
    lower = text.lower()
    for key in REVIEWER_SCAFFOLD_KEYS:
        assert f"{key}:" not in lower, (
            f"Polished output leaked reviewer scaffolding: {key!r}\n---\n{text}"
        )


def test_apply_glossary():
    """Test glossary term replacement."""
    terms = [
        GlossaryTerm(zh="大小姐", en="Young Lady"),
        GlossaryTerm(zh="王爷", en="Prince"),
    ]
    text = "大小姐 called 王爷"
    result = apply_glossary(text, terms)
    assert result == "Young Lady called Prince"
    # Ensure longer terms are replaced first (no need for specific test but we trust sorting)


def test_apply_glossary_no_terms():
    """Test glossary function with empty list."""
    text = "Hello world"
    result = apply_glossary(text, [])
    assert result == text


def test_translate_draft_with_glossary():
    """Test draft translation includes glossary replacements."""
    def run():
        input = TranslationInput(
            segment_id="1",
            source_text="大小姐 called 王爷",
            glossary_terms=[
                GlossaryTerm(zh="大小姐", en="Young Lady"),
                GlossaryTerm(zh="王爷", en="Prince"),
            ]
        )
        # Mock backend returns raw Chinese text; glossary replacement will apply.
        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.return_value = "大小姐 called 王爷"
            output = translate_draft(input)
            assert mock_backend.call_count == 1
            assert output.segment_id == "1"
            assert "Young Lady" in output.draft_translation
            assert "Prince" in output.draft_translation
            assert output.notes == []
            # Ensure polished_translation placeholder is empty string
            assert output.polished_translation == ""
    _with_backend_env(run)


def test_translate_draft_no_glossary():
    """Test draft translation without glossary."""
    def run():
        input = TranslationInput(
            segment_id="2",
            source_text="Hello world",
            glossary_terms=[]
        )
        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.return_value = "Hello world"
            output = translate_draft(input)
            assert mock_backend.call_count == 1
            assert output.segment_id == "2"
            assert output.draft_translation == "Hello world"
            assert output.notes == []
    _with_backend_env(run)


def _with_backend_env(fn):
    """Run fn() with MODEL_BACKEND_URL set to a stub value.

    ``app.config.config.MODEL_BACKEND_URL`` is frozen at import time from the
    env var, so patching env alone isn't enough once config has been loaded
    by an earlier test. Patch both.
    """
    from app.config import config
    original_env = os.environ.get('MODEL_BACKEND_URL')
    stub = 'http://test-backend.example.com/generate'
    os.environ['MODEL_BACKEND_URL'] = stub
    with patch.object(config, 'MODEL_BACKEND_URL', stub):
        try:
            return fn()
        finally:
            if original_env is not None:
                os.environ['MODEL_BACKEND_URL'] = original_env
            else:
                del os.environ['MODEL_BACKEND_URL']


def test_polish_translation_revises_on_major_issue_and_applies_glossary():
    """A → B → revise path: reviewer flags an issue → revision prose wins, glossary applied."""
    def run():
        input = TranslationInput(
            segment_id="3",
            source_text="大小姐 called 王爷",
            glossary_terms=[
                GlossaryTerm(zh="大小姐", en="Young Lady"),
                GlossaryTerm(zh="王爷", en="Prince"),
            ],
        )
        draft_output = TranslationOutput(
            segment_id="3",
            draft_translation="[DRAFT ENGLISH] 大小姐 called 王爷",
            polished_translation="",
            notes=[],
        )

        # First backend call = Prompt B reviewer (returns scaffolding with a
        # real major_issue). Second call = Prompt A revision (returns prose).
        review_reply = (
            "major_issue: drift on form of address for 王爷\n"
            "why_it_matters: breaks project consistency\n"
            "recommended_fix: restore the glossary rendering\n"
        )
        revision_reply = "[POLISHED] 大小姐 called 王爷"

        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.side_effect = [review_reply, revision_reply]
            output = polish_translation(input, draft_output)
            # Both passes ran: one review call + one revision call.
            assert mock_backend.call_count == 2

        assert output.segment_id == "3"
        # Revision prose wins (not the draft).
        assert "[POLISHED]" in output.polished_translation
        # Glossary applied.
        assert "Young Lady" in output.polished_translation
        assert "Prince" in output.polished_translation
        assert output.draft_translation == draft_output.draft_translation
        # Reviewer scaffolding never leaks out.
        _assert_no_reviewer_scaffolding(output.polished_translation)

    _with_backend_env(run)


def test_polish_translation_no_issue_returns_draft_as_prose():
    """A → B path: reviewer finds nothing material → polished = draft (no 2nd call)."""
    def run():
        input = TranslationInput(
            segment_id="4",
            source_text="大小姐 called 王爷",
            glossary_terms=[GlossaryTerm(zh="大小姐", en="Young Lady")],
        )
        draft_output = TranslationOutput(
            segment_id="4",
            draft_translation="Young Lady called 王爷",
            polished_translation="",
            notes=[],
        )

        review_reply = (
            "major_issue: none\n"
            "why_it_matters: n/a\n"
            "recommended_fix: n/a\n"
        )

        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.side_effect = [review_reply]
            output = polish_translation(input, draft_output)
            # Only the review call happened. No revision pass.
            assert mock_backend.call_count == 1

        # Default output is the draft (glossary re-applied as safety).
        assert output.polished_translation == "Young Lady called 王爷"
        _assert_no_reviewer_scaffolding(output.polished_translation)

    _with_backend_env(run)


def test_polish_translation_strips_leaked_reviewer_scaffolding():
    """If a backend or prompt bug causes reviewer scaffolding to leak into the
    revision output, the default polish path must strip it before returning."""
    def run():
        input = TranslationInput(
            segment_id="5",
            source_text="大小姐 called 王爷",
            glossary_terms=[],
        )
        draft_output = TranslationOutput(
            segment_id="5",
            draft_translation="Young Lady called Prince.",
            polished_translation="",
            notes=[],
        )

        review_reply = "major_issue: register drift\nrecommended_fix: restore neutral tone\n"
        # Revision reply accidentally echoes reviewer scaffolding too.
        leaked_revision = (
            "Young Lady spoke to the Prince.\n\n"
            "major_issue: register drift\n"
            "why_it_matters: tonal inconsistency\n"
            "recommended_fix: restore neutral tone\n"
        )

        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.side_effect = [review_reply, leaked_revision]
            output = polish_translation(input, draft_output)

        _assert_no_reviewer_scaffolding(output.polished_translation)
        assert "Young Lady spoke to the Prince." in output.polished_translation

    _with_backend_env(run)


def test_parse_review_findings_detects_and_rejects_no_issue():
    with_issue = parse_review_findings(
        "major_issue: drift\nwhy_it_matters: x\nrecommended_fix: y\n"
    )
    assert with_issue.has_major_issue() is True
    assert with_issue.major_issue == "drift"
    assert with_issue.recommended_fix == "y"

    no_issue = parse_review_findings("major_issue: none\n")
    assert no_issue.has_major_issue() is False

    empty = parse_review_findings("")
    assert empty.has_major_issue() is False


def test_clean_polished_output_strips_reviewer_scaffolding_only():
    raw = (
        "She turned to face him.\n\n"
        "major_issue: ownership drift\n"
        "why_it_matters: adds unsupported possessive\n"
        "recommended_fix: drop the pronoun\n"
        "optional_notes: none\n"
    )
    cleaned = clean_polished_output(raw)
    _assert_no_reviewer_scaffolding(cleaned)
    assert cleaned == "She turned to face him."


def test_build_review_prompt_uses_prompt_b_not_prompt_a():
    inp = TranslationInput(
        segment_id="r1",
        source_text="大小姐 called 王爷",
        glossary_terms=[],
    )
    review_prompt = build_review_prompt(inp, "Young Lady called Prince.", "none")
    # Prompt B's distinguishing language (reviewer output format)
    assert "major_issue" in review_prompt.lower()
    # Prompt B-specific marker
    assert "English translation under review:" in review_prompt


def test_build_polish_prompt_uses_prompt_a_and_injects_review_guidance():
    inp = TranslationInput(
        segment_id="r2",
        source_text="大小姐 called 王爷",
        glossary_terms=[],
    )
    findings = ReviewFindings(
        raw="",
        major_issue="ownership drift",
        recommended_fix="drop unsupported possessive",
    )
    prompt = build_polish_prompt(
        inp, "Young Lady called her Prince.", "none", review_guidance=findings
    )
    # Prompt A language
    assert "Polished translation:" in prompt
    assert "Draft translation to polish:" in prompt
    # Reviewer signal is injected but reviewer field scaffolding is NOT echoed.
    assert "ownership drift" in prompt
    assert "drop unsupported possessive" in prompt
    # No bare reviewer keys as section headers in the prompt we send.
    assert "major_issue:" not in prompt.lower()
    assert "why_it_matters:" not in prompt.lower()


def test_build_polish_prompt_without_guidance_has_no_review_section():
    inp = TranslationInput(
        segment_id="r3",
        source_text="大小姐 called 王爷",
        glossary_terms=[],
    )
    prompt = build_polish_prompt(inp, "Young Lady called Prince.", "none")
    assert "Reviewer guidance" not in prompt


def test_build_translation_input():
    """Test converting Segment to TranslationInput."""
    segment = Segment(
        segment_id=42,
        text="Some text",
        prev_segment_text="Previous",
        next_segment_text="Next"
    )
    glossary = [GlossaryTerm(zh="text", en="textual")]
    input = build_translation_input(segment, glossary)
    assert input.segment_id == "42"
    assert input.source_text == "Some text"
    assert input.prev_context == "Previous"
    assert input.next_context == "Next"
    assert input.glossary_terms == glossary


# ── check_segment_coverage unit tests ────────────────────────────────────


def test_check_segment_coverage_paragraph_triggers():
    """4+ source paragraphs but candidate has ≤1 → gate fires."""
    source = "A.\n\nB.\n\nC.\n\nD."
    candidate = "A."
    result = check_segment_coverage(source, candidate)
    assert result is not None
    assert "Possible omission" in result.major_issue


def test_check_segment_coverage_dialogue_u201c_triggers():
    """Source uses U+201C left double quotation marks for dialogue,
    candidate preserves only one exchange → gate fires."""
    source = (
        "“Hello.”\n\n"
        "“How are you?”\n\n"
        "“I am fine.”\n\n"
        "“And you?”\n\n"
        "“Me too.”"
    )
    candidate = "\"Hello.\""
    result = check_segment_coverage(source, candidate)
    assert result is not None
    assert "Possible omission" in result.major_issue


def test_check_segment_coverage_length_ratio_triggers():
    """Long source but candidate <20% → gate fires."""
    source = "“" + "X" * 299
    candidate = "Y" * 50  # ~16.7% of source length
    result = check_segment_coverage(source, candidate)
    assert result is not None
    assert "Output too short" in result.major_issue


def test_check_segment_coverage_adequate_notrigger():
    """Short source with adequate candidate → gate does not fire."""
    source = "Short normal text."
    candidate = "Short normal translation."
    result = check_segment_coverage(source, candidate)
    assert result is None


# ── Coverage gate integration tests through polish_translation ──────────


def test_coverage_gate_triggers_revision_on_paragraph_omission():
    """Prompt B says no issue but draft omits 3 paragraphs → coverage gate
    injects major_issue → revision path fires."""
    def run():
        source = "A.\n\nB.\n\nC.\n\nD."
        draft = "A."

        input = TranslationInput(
            segment_id="cg-int-1",
            source_text=source,
            glossary_terms=[],
        )
        draft_output = TranslationOutput(
            segment_id="cg-int-1",
            draft_translation=draft,
            polished_translation="",
            notes=[],
        )

        # Prompt B sees no issue — coverage gate must catch the omission.
        review_reply = "major_issue: none\n"
        revision_reply = "A.\n\nB.\n\nC.\n\nD."

        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.side_effect = [review_reply, revision_reply]
            output = polish_translation(input, draft_output)
            # Two calls: review + revision (coverage gate overrides findings)
            assert mock_backend.call_count == 2

        assert output.polished_translation == revision_reply
        _assert_no_reviewer_scaffolding(output.polished_translation)

    _with_backend_env(run)


def test_coverage_gate_no_false_positive_adequate_draft():
    """Prompt B says no issue and draft has adequate coverage → no revision."""
    def run():
        source = "Short normal text."
        draft = "Short normal translation."

        input = TranslationInput(
            segment_id="cg-int-2",
            source_text=source,
            glossary_terms=[],
        )
        draft_output = TranslationOutput(
            segment_id="cg-int-2",
            draft_translation=draft,
            polished_translation="",
            notes=[],
        )

        review_reply = "major_issue: none\n"

        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.side_effect = [review_reply]
            output = polish_translation(input, draft_output)
            # Only review call — coverage gate does not fire, no revision.
            assert mock_backend.call_count == 1

        assert output.polished_translation == draft

    _with_backend_env(run)


if __name__ == "__main__":
    test_apply_glossary()
    test_apply_glossary_no_terms()
    test_translate_draft_with_glossary()
    test_translate_draft_no_glossary()
    test_polish_translation_revises_on_major_issue_and_applies_glossary()
    test_polish_translation_no_issue_returns_draft_as_prose()
    test_polish_translation_strips_leaked_reviewer_scaffolding()
    test_parse_review_findings_detects_and_rejects_no_issue()
    test_clean_polished_output_strips_reviewer_scaffolding_only()
    test_build_review_prompt_uses_prompt_b_not_prompt_a()
    test_build_polish_prompt_uses_prompt_a_and_injects_review_guidance()
    test_build_polish_prompt_without_guidance_has_no_review_section()
    test_build_translation_input()
    print("All translator tests passed.")