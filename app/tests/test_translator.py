import sys
import os
import pytest
from unittest.mock import patch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.translate.schema import TranslationInput, TranslationOutput, GlossaryTerm
from app.translate.translator import (
    apply_glossary,
    set_smoke_mode,
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
from app.config import config


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


# ── CJK residue rule ────────────────────────────────────────────────────


def test_check_segment_coverage_cjk_residue_triggers():
    """Candidate retains untranslated Chinese above the residue threshold."""
    source = "她说：「明天再来。」他点了点头。"
    candidate = "She said: 「明天再来。」he nodded."  # 6 CJK chars left
    result = check_segment_coverage(source, candidate)
    assert result is not None
    assert "Untranslated Chinese" in result.major_issue


def test_check_segment_coverage_cjk_residue_below_threshold_notrigger():
    """A single proper-noun Chinese span (under threshold) should not fire."""
    source = "Wang Ye stepped inside."
    candidate = "王爷 stepped inside."  # 2 CJK chars
    result = check_segment_coverage(source, candidate)
    assert result is None


# ── Glossary enforcement rule ───────────────────────────────────────────


def test_check_segment_coverage_glossary_term_missing_triggers():
    """Source contains a glossary zh term but candidate uses a generic
    English form instead of the project rendering → gate fires."""
    source = "大小姐 turned to face him."
    # Output uses a generic 'Miss' instead of the project rendering.
    candidate = "Miss turned to face him."
    glossary = [GlossaryTerm(zh="大小姐", en="Young Lady")]
    result = check_segment_coverage(source, candidate, glossary_terms=glossary)
    assert result is not None
    assert "Glossary term not honored" in result.major_issue
    assert "大小姐" in result.major_issue
    assert "Young Lady" in result.major_issue


def test_check_segment_coverage_glossary_term_honored_notrigger():
    """Project rendering present → gate does not fire."""
    source = "大小姐 turned to face him."
    candidate = "Young Lady turned to face him."
    glossary = [GlossaryTerm(zh="大小姐", en="Young Lady")]
    result = check_segment_coverage(source, candidate, glossary_terms=glossary)
    assert result is None


def test_check_segment_coverage_glossary_term_not_in_source_notrigger():
    """Glossary lists a term that does not appear in source → not enforced."""
    source = "He nodded once."
    candidate = "He nodded once."
    glossary = [GlossaryTerm(zh="大小姐", en="Young Lady")]
    result = check_segment_coverage(source, candidate, glossary_terms=glossary)
    assert result is None


def test_check_segment_coverage_priority_cjk_residue_over_glossary():
    """When both CJK residue and glossary miss are present, the residue
    rule fires first because it is a higher-signal failure type."""
    source = "大小姐 turned and 离开了 the hall."
    # Candidate retains Chinese AND drops the glossary rendering.
    candidate = "Miss 离开了 the 大厅 quickly here."
    glossary = [GlossaryTerm(zh="大小姐", en="Young Lady")]
    result = check_segment_coverage(source, candidate, glossary_terms=glossary)
    assert result is not None
    assert "Untranslated Chinese" in result.major_issue


# ── Coverage gate integration tests through polish_translation ──────────


def test_coverage_gate_triggers_revision_on_cjk_residue():
    """Prompt B says no issue but draft has Chinese residue → coverage gate
    fires → revision path runs."""
    def run():
        source = "她转身离开了房间。"
        # Draft retains heavy Chinese residue.
        draft = "She turned 离开了房间然后 walked away here."

        input = TranslationInput(
            segment_id="cg-cjk-1",
            source_text=source,
            glossary_terms=[],
        )
        draft_output = TranslationOutput(
            segment_id="cg-cjk-1",
            draft_translation=draft,
            polished_translation="",
            notes=[],
        )

        review_reply = "major_issue: none\n"
        revision_reply = "She turned, left the room, and walked away."

        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.side_effect = [review_reply, revision_reply]
            output = polish_translation(input, draft_output)
            assert mock_backend.call_count == 2

        assert output.polished_translation == revision_reply

    _with_backend_env(run)


def test_coverage_gate_triggers_revision_on_glossary_drift():
    """Prompt B says no issue but draft renders 大小姐 as generic 'Miss' →
    glossary enforcement gate fires → revision path runs."""
    def run():
        source = "大小姐 turned to face him."
        draft = "Miss turned to face him."

        input = TranslationInput(
            segment_id="cg-glos-1",
            source_text=source,
            glossary_terms=[GlossaryTerm(zh="大小姐", en="Young Lady")],
        )
        draft_output = TranslationOutput(
            segment_id="cg-glos-1",
            draft_translation=draft,
            polished_translation="",
            notes=[],
        )

        review_reply = "major_issue: none\n"
        revision_reply = "Young Lady turned to face him."

        with patch('app.translate.backend_adapter.call_model_backend') as mock_backend:
            mock_backend.side_effect = [review_reply, revision_reply]
            output = polish_translation(input, draft_output)
            assert mock_backend.call_count == 2

        assert "Young Lady" in output.polished_translation


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


# ── Smoke-test mode ─────────────────────────────────────────────────────────

def test_translate_draft_fails_without_backend_during_test():
    """Without MODEL_BACKEND_URL and without set_smoke_mode(), translate_draft
    must raise RuntimeError — it must NOT silently produce mock output."""
    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(False)
    try:
        inp = TranslationInput(
            segment_id="1",
            source_text="测试文字。",
        )
        with pytest.raises(RuntimeError, match="MODEL_BACKEND_URL not configured"):
            translate_draft(inp)
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_translate_draft_with_smoke_mode_returns_output():
    """With set_smoke_mode(True) and no MODEL_BACKEND_URL, translate_draft
    must return a TranslationOutput (not fail) — the pipeline should complete
    mechanically for smoke testing."""
    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(True)
    try:
        inp = TranslationInput(
            segment_id="1",
            source_text="测试文字。",
        )
        result = translate_draft(inp)
        assert result is not None
        assert isinstance(result, TranslationOutput)
        assert result.segment_id == "1"
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_smoke_draft_output_labeled():
    """Smoke-test draft output must contain '[SMOKE TEST]' label to distinguish
    it from real translation output."""
    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(True)
    try:
        inp = TranslationInput(
            segment_id="3",
            source_text="测试文字。",
        )
        result = translate_draft(inp)
        assert "SMOKE TEST" in result.draft_translation
        assert "3" in result.draft_translation  # segment id visible
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_smoke_internal_review_returns_no_issue():
    """Smoke-test internal review must report 'no major issue' so the polish
    pass returns the draft unchanged — no real review was performed."""
    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(True)
    try:
        from app.translate.translator import run_internal_review_with_backend
        inp = TranslationInput(
            segment_id="1",
            source_text="测试文字。",
        )
        review = run_internal_review_with_backend(inp, "mock draft text")
        assert "none" in review.lower()
        assert "major_issue" in review.lower()
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_smoke_mode_resets_between_tests():
    """set_smoke_mode(False) must disable the mode so the next normal call
    raises RuntimeError (avoids cross-test contamination)."""
    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(False)
    try:
        inp = TranslationInput(
            segment_id="1",
            source_text="测试文字。",
        )
        with pytest.raises(RuntimeError, match="MODEL_BACKEND_URL not configured"):
            translate_draft(inp)
    finally:
        config.MODEL_BACKEND_URL = original_url


# ── Profile-backed review/polish wiring ──────────────────────────────────


def test_internal_review_with_profile_uses_profile_adapter():
    """When model_profile is provided and MODEL_BACKEND_URL is empty,
    run_internal_review_with_backend must use the profile adapter path
    (call_chat_completion) instead of raising about missing MODEL_BACKEND_URL
    or falling back."""
    from app.translate.translator import run_internal_review_with_backend
    from app.translate.model_profiles import DEEPSEEK_V4_FLASH

    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(False)
    try:
        inp = TranslationInput(segment_id="1", source_text="测试文字。")
        mock_review = (
            "major_issue: none\n"
            "why_it_matters: n/a\n"
            "recommended_fix: n/a\n"
        )
        with patch(
            "app.translate.deepseek_adapter.call_chat_completion",
            return_value=mock_review,
        ) as mock_chat:
            review = run_internal_review_with_backend(
                inp, "mock draft text",
                model_profile=DEEPSEEK_V4_FLASH,
            )
            mock_chat.assert_called_once()
            assert "none" in review.lower()
            assert "major_issue" in review.lower()
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_internal_review_without_profile_still_requires_model_backend_url():
    """No silent fallback: when model_profile is NOT provided and
    MODEL_BACKEND_URL is empty, run_internal_review_with_backend
    must still raise RuntimeError."""
    from app.translate.translator import run_internal_review_with_backend

    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(False)
    try:
        inp = TranslationInput(segment_id="1", source_text="测试文字。")
        with pytest.raises(RuntimeError, match="MODEL_BACKEND_URL not configured"):
            run_internal_review_with_backend(inp, "mock draft text")
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_translate_polish_with_backend_uses_profile_adapter():
    """When model_profile is provided and MODEL_BACKEND_URL is empty,
    translate_polish_with_backend must use the profile adapter path
    instead of falling back to MODEL_BACKEND_URL."""
    from app.translate.translator import translate_polish_with_backend
    from app.translate.model_profiles import DEEPSEEK_V4_FLASH

    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(False)
    try:
        inp = TranslationInput(segment_id="1", source_text="测试文字。")
        mock_polish = "This is the polished translation text."
        with patch(
            "app.translate.deepseek_adapter.call_chat_completion",
            return_value=mock_polish,
        ) as mock_chat:
            result = translate_polish_with_backend(
                inp, "mock draft text",
                model_profile=DEEPSEEK_V4_FLASH,
            )
            mock_chat.assert_called_once()
            assert "polished translation" in result.lower()
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_translate_polish_with_backend_without_profile_requires_model_backend_url():
    """No silent fallback: when model_profile is NOT provided and
    MODEL_BACKEND_URL is empty, translate_polish_with_backend
    must raise RuntimeError."""
    from app.translate.translator import translate_polish_with_backend

    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(False)
    try:
        inp = TranslationInput(segment_id="1", source_text="测试文字。")
        with pytest.raises(RuntimeError, match="MODEL_BACKEND_URL not configured"):
            translate_polish_with_backend(inp, "mock draft text")
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_polish_translation_with_profile_no_revision():
    """When model_profile is provided and reviewer says no issue, the full
    polish flow (review + optional revision) uses the profile adapter.
    Only one backend call needed (review only)."""
    from app.translate.translator import polish_translation as pt
    from app.translate.model_profiles import DEEPSEEK_V4_FLASH

    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(False)
    try:
        inp = TranslationInput(
            segment_id="1",
            source_text="大小姐 called 王爷",
            glossary_terms=[
                GlossaryTerm(zh="大小姐", en="Young Lady"),
                GlossaryTerm(zh="王爷", en="Prince"),
            ],
        )
        draft_output = TranslationOutput(
            segment_id="1",
            draft_translation="Young Lady called Prince.",
            polished_translation="",
            notes=[],
        )
        mock_review = (
            "major_issue: none\n"
            "why_it_matters: n/a\n"
            "recommended_fix: n/a\n"
        )
        with patch(
            "app.translate.deepseek_adapter.call_chat_completion",
            return_value=mock_review,
        ) as mock_chat:
            result = pt(inp, draft_output, model_profile=DEEPSEEK_V4_FLASH)
            mock_chat.assert_called_once()  # Only review, no revision
            assert "Young Lady" in result.polished_translation
            assert "Prince" in result.polished_translation
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)


def test_polish_translation_with_profile_full_revision_flow():
    """With model_profile and reviewer flags a major issue, polish_translation
    performs BOTH internal review AND revision pass via the profile adapter
    (two backend calls), not via MODEL_BACKEND_URL."""
    from app.translate.translator import polish_translation as pt
    from app.translate.model_profiles import DEEPSEEK_V4_FLASH

    original_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(False)
    try:
        inp = TranslationInput(
            segment_id="2",
            source_text="大小姐 called 王爷",
            glossary_terms=[
                GlossaryTerm(zh="大小姐", en="Young Lady"),
                GlossaryTerm(zh="王爷", en="Prince"),
            ],
        )
        draft_output = TranslationOutput(
            segment_id="2",
            draft_translation="[DRAFT] 大小姐 called 王爷",
            polished_translation="",
            notes=[],
        )
        mock_review = (
            "major_issue: drift on form of address for 王爷\n"
            "why_it_matters: breaks project consistency\n"
            "recommended_fix: restore the glossary rendering\n"
        )
        mock_revision = "[POLISHED] Young Lady called Prince."
        with patch(
            "app.translate.deepseek_adapter.call_chat_completion",
            side_effect=[mock_review, mock_revision],
        ) as mock_chat:
            result = pt(inp, draft_output, model_profile=DEEPSEEK_V4_FLASH)
            assert mock_chat.call_count == 2  # review + revision
            assert "[POLISHED]" in result.polished_translation
            assert "Prince" in result.polished_translation
            assert "Young Lady" in result.polished_translation
    finally:
        config.MODEL_BACKEND_URL = original_url
        set_smoke_mode(False)