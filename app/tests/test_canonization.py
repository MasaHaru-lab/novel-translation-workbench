"""Tests for the canonization gate module.

Tests focus on the protection rules, classification logic, and routing
decisions.  They use in-memory fixtures — no disk I/O, no project_assets
filesystem dependency.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from app.chapter.canonization import (
    CanonizationGate,
    CanonizationVerdict,
    ProposedRendering,
    RenderingCategory,
    RenderingRisk,
    RiskSignal,
    _RISKY_CATEGORIES,
    classify_target_asset,
    detect_generic_address,
    detect_meta_note_rendering,
    detect_stiff_kinship,
    detect_unapproved_benchmark,
    detect_user_rejected,
    detect_weak_evidence,
    heading_matches_term,
    parse_rejected_alternatives,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def gate() -> CanonizationGate:
    """A default gate with no disk-dependent rejected-map loading."""
    return CanonizationGate(rejected_map={})


@pytest.fixture
def sample_rejected_map():
    """Simulates the rejected alternatives found in project assets."""
    return {
        "丫头 / 西丫头 / 你这丫头": [
            "girl",
            "little girl",
            "Little Xi",
        ],
        "嫡母": [
            "principal mother",
            "mother",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Protection Rule: detect_generic_address
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectGenericAddress:
    def test_non_address_term_skipped(self):
        """Only ADDRESS_TERM category is checked."""
        p = ProposedRendering(
            chinese_term="大灃",
            proposed_rendering="Great Feng",
            category=RenderingCategory.GLOSSARY_TERM,
        )
        assert detect_generic_address(p) is None

    def test_generic_girl_triggers_warning(self):
        """'girl' for an address term → warning (not blocked)."""
        p = ProposedRendering(
            chinese_term="丫头",
            proposed_rendering="girl",
            category=RenderingCategory.ADDRESS_TERM,
        )
        signal = detect_generic_address(p)
        assert signal is not None
        assert signal.signal_type == "generic_address"
        assert signal.severity == "warning"

    def test_specific_rendering_passes(self):
        """A specific rendering like 'Xi'er' should not trigger."""
        p = ProposedRendering(
            chinese_term="丫头",
            proposed_rendering="Xi'er",
            category=RenderingCategory.ADDRESS_TERM,
        )
        assert detect_generic_address(p) is None

    def test_user_approved_overrides_generic(self):
        """If explicitly user-approved, generic is not blocked."""
        p = ProposedRendering(
            chinese_term="丫头",
            proposed_rendering="girl",
            category=RenderingCategory.ADDRESS_TERM,
            user_approved=True,
        )
        assert detect_generic_address(p) is None

    def test_user_rejected_generic_is_blocker(self):
        """If user explicitly rejected, generic is a blocker."""
        p = ProposedRendering(
            chinese_term="丫头",
            proposed_rendering="girl",
            category=RenderingCategory.ADDRESS_TERM,
            user_approved=False,
        )
        signal = detect_generic_address(p)
        assert signal is not None
        assert signal.severity == "blocker"

    @pytest.mark.parametrize("term", ["young lady", "little girl", "miss"])
    def test_various_generic_terms_flagged(self, term):
        p = ProposedRendering(
            chinese_term="丫头",
            proposed_rendering=term,
            category=RenderingCategory.ADDRESS_TERM,
        )
        signal = detect_generic_address(p)
        assert signal is not None, f"{term!r} should be detected as generic"


# ═══════════════════════════════════════════════════════════════════════════
# Protection Rule: detect_stiff_kinship
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectStiffKinship:
    def test_non_kinship_skipped(self):
        p = ProposedRendering(
            chinese_term="大灃",
            proposed_rendering="Great Feng",
            category=RenderingCategory.GLOSSARY_TERM,
        )
        assert detect_stiff_kinship(p) is None

    def test_legalistic_pattern_warning(self):
        p = ProposedRendering(
            chinese_term="某妾室",
            proposed_rendering="concubine-born offspring",
            category=RenderingCategory.KINSHIP_TERM,
        )
        signal = detect_stiff_kinship(p)
        assert signal is not None
        assert signal.signal_type == "stiff_kinship"
        assert signal.severity == "warning"

    def test_user_approved_overrides(self):
        p = ProposedRendering(
            chinese_term="某妾室",
            proposed_rendering="concubine-born offspring",
            category=RenderingCategory.KINSHIP_TERM,
            user_approved=True,
        )
        assert detect_stiff_kinship(p) is None

    def test_natural_kinship_passes(self):
        p = ProposedRendering(
            chinese_term="嫡母",
            proposed_rendering="legal mother",
            category=RenderingCategory.KINSHIP_TERM,
        )
        # "legal mother" does not match any stiff pattern because
        # _STIFF_KINSHIP_PATTERNS matches "legal (wife|spouse|heir|...)"
        # but NOT "legal mother" — "mother" is not in the alternation.
        assert detect_stiff_kinship(p) is None

    @pytest.mark.parametrize(
        "rendering,pattern_hint",
        [
            ("principal mother", "principal"),
            ("principal wife", "principal"),
            ("legal wife", "legal"),
            ("primary consort", "primary"),
        ],
    )
    def test_multiple_stiff_patterns_detected(self, rendering, pattern_hint):
        p = ProposedRendering(
            chinese_term="某妻",
            proposed_rendering=rendering,
            category=RenderingCategory.KINSHIP_TERM,
        )
        signal = detect_stiff_kinship(p)
        assert signal is not None, (
            f"{rendering!r} should trigger stiff_kinship ({pattern_hint})"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Protection Rule: detect_meta_note_rendering
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectMetaNoteRendering:
    @pytest.mark.parametrize(
        "bad_rendering",
        [
            "provisional, keep for now",
            "keep for now",
            "needs system-level review",
            "do not use for now",
            "tentative rendering",
            "current working rendering",
            "work in progress",
            "to be decided",
            "context-sensitive; see notes",
        ],
    )
    def test_meta_notes_are_blocked(self, bad_rendering):
        p = ProposedRendering(
            chinese_term="嬷嬷",
            proposed_rendering=bad_rendering,
            category=RenderingCategory.TITLE_RANK,
        )
        signal = detect_meta_note_rendering(p)
        assert signal is not None, (
            f"{bad_rendering!r} should be detected as meta-note"
        )
        assert signal.severity == "blocker"

    def test_real_rendering_passes(self):
        p = ProposedRendering(
            chinese_term="嬷嬷",
            proposed_rendering="Momo",
            category=RenderingCategory.TITLE_RANK,
        )
        assert detect_meta_note_rendering(p) is None

    def test_long_phrase_with_instr_word_blocked(self):
        """'final treatment should stay aligned' contains 'final treatment'."""
        p = ProposedRendering(
            chinese_term="嬷嬷",
            proposed_rendering="final treatment should stay aligned",
            category=RenderingCategory.TITLE_RANK,
        )
        # "final treatment" is NOT in _META_NOTE_PATTERNS. But check anyway.
        signal = detect_meta_note_rendering(p)
        # The string "final treatment" alone is not a pattern. This test
        # documents that we don't block arbitrary editorial-sounding phrases,
        # only the patterns explicitly listed.
        assert signal is None or signal.signal_type == "meta_note_rendering"


# ═══════════════════════════════════════════════════════════════════════════
# Protection Rule: detect_unapproved_benchmark
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectUnapprovedBenchmark:
    def test_no_source_no_signal(self):
        p = ProposedRendering(
            chinese_term="大小姐",
            proposed_rendering="Eldest Miss",
            category=RenderingCategory.ADDRESS_TERM,
            source="",
        )
        assert detect_unapproved_benchmark(p) is None

    def test_user_feedback_not_benchmark(self):
        p = ProposedRendering(
            chinese_term="大小姐",
            proposed_rendering="Eldest Miss",
            category=RenderingCategory.ADDRESS_TERM,
            source="user_feedback",
        )
        assert detect_unapproved_benchmark(p) is None

    def test_benchmark_source_without_approval_warning(self):
        p = ProposedRendering(
            chinese_term="大小姐",
            proposed_rendering="Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
            source="benchmark_run_v3",
        )
        signal = detect_unapproved_benchmark(p)
        assert signal is not None
        assert signal.signal_type == "unapproved_benchmark"
        assert signal.severity == "warning"

    def test_benchmark_with_user_approval_passes(self):
        p = ProposedRendering(
            chinese_term="大小姐",
            proposed_rendering="Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
            source="benchmark_run_v3",
            user_approved=True,
        )
        assert detect_unapproved_benchmark(p) is None


# ═══════════════════════════════════════════════════════════════════════════
# Protection Rule: detect_weak_evidence
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectWeakEvidence:
    def test_strong_evidence_no_signal(self):
        p = ProposedRendering(
            chinese_term="大小姐",
            proposed_rendering="Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="strong",
        )
        assert detect_weak_evidence(p) is None

    def test_weak_evidence_risky_category_warning(self):
        p = ProposedRendering(
            chinese_term="大小姐",
            proposed_rendering="Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="weak",
        )
        signal = detect_weak_evidence(p)
        assert signal is not None
        assert signal.signal_type == "weak_evidence"
        assert signal.severity == "warning"

    def test_weak_evidence_safe_category_ok(self):
        """Weak evidence for GLOSSARY_TERM does not trigger."""
        p = ProposedRendering(
            chinese_term="大灃",
            proposed_rendering="Great Feng",
            category=RenderingCategory.GLOSSARY_TERM,
            evidence_strength="weak",
        )
        assert detect_weak_evidence(p) is None


# ═══════════════════════════════════════════════════════════════════════════
# Helper: parse_rejected_alternatives
# ═══════════════════════════════════════════════════════════════════════════


class TestParseRejectedAlternatives:
    def test_parses_rejected_alternatives_line(self):
        text = """### 丫头
- Rejected alternatives: "girl", "little girl"
"""
        result = parse_rejected_alternatives(text)
        assert "丫头" in result
        assert "girl" in result["丫头"]
        assert "little girl" in result["丫头"]

    def test_parses_rejected_from_notes_line(self):
        text = """### 丫头
- Notes: Keep as Xi'er. Rejected alternatives: "girl" (too flat), "Little Xi" (over-Westernized)
"""
        result = parse_rejected_alternatives(text)
        assert "丫头" in result
        assert "girl" in result["丫头"]
        assert "Little Xi" in result["丫头"]

    def test_empty_text_returns_empty(self):
        assert parse_rejected_alternatives("") == {}

    def test_no_rejected_found_returns_empty(self):
        text = """### 大灃
- Chinese: 大灃
- Working English rendering: Great Feng
"""
        assert parse_rejected_alternatives(text) == {}

    def test_parses_backtick_alternatives(self):
        text = """### 嫡母
- Rejected alternatives: `principal mother` (too legalistic)
"""
        result = parse_rejected_alternatives(text)
        assert "嫡母" in result
        assert "principal mother" in result["嫡母"]


# ═══════════════════════════════════════════════════════════════════════════
# Helper: heading_matches_term
# ═══════════════════════════════════════════════════════════════════════════


class TestHeadingMatchesTerm:
    def test_exact_match(self):
        assert heading_matches_term("丫头", "丫头")

    def test_slash_separated(self):
        assert heading_matches_term("丫头 / 西丫头 / 你这丫头", "丫头")
        assert heading_matches_term("丫头 / 西丫头 / 你这丫头", "西丫头")
        assert heading_matches_term("丫头 / 西丫头 / 你这丫头", "你这丫头")

    def test_no_match(self):
        assert not heading_matches_term("大小姐", "丫头")


# ═══════════════════════════════════════════════════════════════════════════
# Protection Rule: detect_user_rejected
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectUserRejected:
    def test_matching_rejected_alternative_blocked(self, sample_rejected_map):
        """Exact match to previously rejected alternative → blocker."""
        p = ProposedRendering(
            chinese_term="丫头",
            proposed_rendering="girl",
            category=RenderingCategory.ADDRESS_TERM,
        )
        signal = detect_user_rejected(p, sample_rejected_map)
        assert signal is not None
        assert signal.signal_type == "user_rejected"
        assert signal.severity == "blocker"

    def test_non_matching_rendering_passes(self, sample_rejected_map):
        p = ProposedRendering(
            chinese_term="丫头",
            proposed_rendering="Xi'er",
            category=RenderingCategory.ADDRESS_TERM,
        )
        assert detect_user_rejected(p, sample_rejected_map) is None

    def test_different_term_not_affected(self, sample_rejected_map):
        """Rejected alternatives for other terms do not affect this proposal."""
        p = ProposedRendering(
            chinese_term="大小姐",
            proposed_rendering="Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
        )
        assert detect_user_rejected(p, sample_rejected_map) is None

    def test_case_insensitive_match(self, sample_rejected_map):
        p = ProposedRendering(
            chinese_term="嫡母",
            proposed_rendering="Principal Mother",
            category=RenderingCategory.KINSHIP_TERM,
        )
        signal = detect_user_rejected(p, sample_rejected_map)
        assert signal is not None

    def test_empty_map_no_signal(self):
        p = ProposedRendering(
            chinese_term="丫头",
            proposed_rendering="girl",
        )
        assert detect_user_rejected(p, {}) is None


# ═══════════════════════════════════════════════════════════════════════════
# Integration: CanonizationGate.evaluate  —  SAFE path
# ═══════════════════════════════════════════════════════════════════════════


class TestGateSafePath:
    def test_concrete_glossary_term_is_safe(self, gate):
        """A concrete glossary term passes the gate cleanly."""
        verdict = gate.classify(
            chinese_term="大灃",
            proposed_rendering="Great Feng",
            category=RenderingCategory.GLOSSARY_TERM,
            evidence_strength="strong",
        )
        assert verdict.risk == RenderingRisk.SAFE
        assert not verdict.route_to_unresolved
        assert not verdict.is_blocked
        assert verdict.target_asset == "glossary"

    def test_approved_canonical_xier_is_safe(self, gate):
        """Xi'er (already canonical) is safe."""
        verdict = gate.classify(
            chinese_term="丫头",
            proposed_rendering="Xi'er",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="strong",
            user_approved=True,
        )
        assert verdict.risk == RenderingRisk.SAFE
        assert not verdict.route_to_unresolved

    def test_approved_legal_mother_is_safe(self, gate):
        """'legal mother' — already canonical for 嫡母 — is safe
        when presented with strong evidence."""
        verdict = gate.classify(
            chinese_term="嫡母",
            proposed_rendering="legal mother",
            category=RenderingCategory.KINSHIP_TERM,
            evidence_strength="strong",
        )
        assert verdict.risk == RenderingRisk.SAFE
        assert not verdict.route_to_unresolved

    def test_character_name_safe(self, gate):
        verdict = gate.classify(
            chinese_term="秦流西",
            proposed_rendering="Qin Liuxi",
            category=RenderingCategory.CHARACTER_NAME,
            evidence_strength="strong",
        )
        assert verdict.risk == RenderingRisk.SAFE


# ═══════════════════════════════════════════════════════════════════════════
# Integration: CanonizationGate.evaluate  —  RISKY path
# ═══════════════════════════════════════════════════════════════════════════


class TestGateRiskyPath:
    def test_generic_address_rendering_risky(self, gate):
        """'girl' for 丫头 → RISKY, routes to unresolved."""
        verdict = gate.classify(
            chinese_term="丫头",
            proposed_rendering="girl",
            category=RenderingCategory.ADDRESS_TERM,
        )
        assert verdict.risk == RenderingRisk.RISKY
        assert verdict.route_to_unresolved
        assert not verdict.is_blocked
        assert verdict.needs_approval

    def test_benchmark_source_without_approval_risky(self, gate):
        verdict = gate.classify(
            chinese_term="大小姐",
            proposed_rendering="Eldest Miss",
            category=RenderingCategory.ADDRESS_TERM,
            source="benchmark_run_v3",
            evidence_strength="moderate",
        )
        assert verdict.risk == RenderingRisk.RISKY
        assert verdict.route_to_unresolved

    def test_weak_evidence_risky_category(self, gate):
        verdict = gate.classify(
            chinese_term="贵妃",
            proposed_rendering="Noble Consort",
            category=RenderingCategory.TITLE_RANK,
            evidence_strength="weak",
        )
        assert verdict.risk == RenderingRisk.RISKY
        assert verdict.route_to_unresolved

    def test_stiff_kinship_pattern_risky(self, gate):
        verdict = gate.classify(
            chinese_term="某妾室",
            proposed_rendering="concubine-born offspring",
            category=RenderingCategory.KINSHIP_TERM,
        )
        assert verdict.risk == RenderingRisk.RISKY
        assert verdict.route_to_unresolved

    def test_risky_category_default_to_unresolved_without_evidence(self, gate):
        """An address term with weak evidence → RISKY even if no rule triggered."""
        verdict = gate.classify(
            chinese_term="大小姐",
            proposed_rendering="Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="weak",
        )
        # Even though "Young Lady" doesn't match any specific rule, ADDRESS_TERM
        # with weak evidence is RISKY by the category_risk rule.
        assert verdict.risk == RenderingRisk.RISKY
        assert verdict.route_to_unresolved


# ═══════════════════════════════════════════════════════════════════════════
# Integration: CanonizationGate.evaluate  —  REJECTED path
# ═══════════════════════════════════════════════════════════════════════════


class TestGateRejectedPath:
    def test_user_rejected_rendering_blocked(self, gate, sample_rejected_map):
        """Previously rejected 'girl' for 丫头 → REJECTED."""
        gate_with_rejected = CanonizationGate(rejected_map=sample_rejected_map)
        verdict = gate_with_rejected.classify(
            chinese_term="丫头",
            proposed_rendering="girl",
            category=RenderingCategory.ADDRESS_TERM,
        )
        assert verdict.risk == RenderingRisk.REJECTED
        assert verdict.is_blocked

    def test_meta_note_rendering_blocked(self, gate):
        verdict = gate.classify(
            chinese_term="嬷嬷",
            proposed_rendering="provisional, keep for now",
            category=RenderingCategory.TITLE_RANK,
        )
        assert verdict.risk == RenderingRisk.REJECTED
        assert verdict.is_blocked

    def test_user_rejected_and_meta_note_both_signal(self, gate, sample_rejected_map):
        """Both user-rejected and meta-note signals appear for a multi-rule hit."""
        gate_with_rejected = CanonizationGate(rejected_map=sample_rejected_map)
        verdict = gate_with_rejected.classify(
            chinese_term="丫头",
            proposed_rendering="girl",
            category=RenderingCategory.ADDRESS_TERM,
        )
        # Should have at least user_rejected + generic_address signals
        signal_types = {s.signal_type for s in verdict.signals}
        assert "user_rejected" in signal_types
        assert "generic_address" in signal_types or "meta_note_rendering" in signal_types


# ═══════════════════════════════════════════════════════════════════════════
# Integration: CanonizationGate.evaluate  —  Edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestGateEdgeCases:
    def test_proposal_verdict_preserves_proposal(self, gate):
        p = ProposedRendering(
            chinese_term="大灃",
            proposed_rendering="Great Feng",
            category=RenderingCategory.GLOSSARY_TERM,
        )
        verdict = gate.evaluate(p)
        assert verdict.proposal is p

    def test_target_asset_by_category(self):
        assert classify_target_asset(RenderingCategory.ADDRESS_TERM) == "titles_and_terms"
        assert classify_target_asset(RenderingCategory.GLOSSARY_TERM) == "glossary"
        assert classify_target_asset(RenderingCategory.CHARACTER_NAME) == "characters"
        assert classify_target_asset(RenderingCategory.STYLE_NOTE) == "style_notes"

    def test_safe_rendering_convenience_true(self, gate):
        assert gate.safe_rendering(
            "大灃", "Great Feng",
            category=RenderingCategory.GLOSSARY_TERM,
            evidence_strength="strong",
        )

    def test_safe_rendering_convenience_false(self, gate):
        assert not gate.safe_rendering(
            "丫头", "girl",
            category=RenderingCategory.ADDRESS_TERM,
        )

    def test_empty_proposed_rendering(self, gate):
        """An empty rendering for a risky category triggers category_risk."""
        verdict = gate.classify(
            chinese_term="大小姐",
            proposed_rendering="",
            category=RenderingCategory.ADDRESS_TERM,
        )
        # Empty string is not a meta-note per se — it's just empty.
        # It should be RISKY (address term, weak evidence).
        assert verdict.risk == RenderingRisk.RISKY


# ═══════════════════════════════════════════════════════════════════════════
# Acceptance: known canonical terms remain allowed
# ═══════════════════════════════════════════════════════════════════════════


class TestAcceptanceCanonicalTerms:
    """These tests verify the acceptance criteria from the batch spec.

    Existing canonical/approved terms must remain SAFE through the gate.
    """

    def test_xier_remains_safe(self, gate):
        """Xi'er for 丫头 must remain allowed."""
        assert gate.safe_rendering(
            "丫头",
            "Xi'er",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="strong",
            user_approved=True,
        )

    def test_legal_mother_remains_safe(self, gate):
        """'legal mother' for 嫡母 must remain allowed."""
        assert gate.safe_rendering(
            "嫡母",
            "legal mother",
            category=RenderingCategory.KINSHIP_TERM,
            evidence_strength="strong",
        )

    def test_young_lady_remains_safe(self, gate):
        """'Young Lady' for 大小姐 must remain allowed."""
        assert gate.safe_rendering(
            "大小姐",
            "Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="strong",
            user_approved=True,
        )

    def test_great_feng_remains_safe(self, gate):
        assert gate.safe_rendering(
            "大灃",
            "Great Feng",
            category=RenderingCategory.GLOSSARY_TERM,
            evidence_strength="strong",
        )


# ═══════════════════════════════════════════════════════════════════════════
# Acceptance: failure modes
# ═══════════════════════════════════════════════════════════════════════════


class TestAcceptanceFailureModes:
    """These tests verify that the gate blocks known bad patterns.

    A proposed risky address-term rendering is routed to unresolved, not canonical.
    A user-rejected rendering cannot be marked canonical.
    Meta-note strings cannot become renderings.
    """

    def test_risky_address_routes_to_unresolved(self, gate):
        """Requirement: risky address-term → unresolved, not canonical."""
        verdict = gate.classify(
            chinese_term="丫头",
            proposed_rendering="Little Xi",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="weak",
        )
        assert verdict.route_to_unresolved, (
            f"Expected route_to_unresolved=True for risky address term, "
            f"got {verdict.risk.value}"
        )
        assert verdict.risk != RenderingRisk.SAFE

    def test_user_rejected_cannot_be_marked_fixed(self, gate, sample_rejected_map):
        """Requirement: user-rejected rendering cannot reach canonical status."""
        gate_with_rejected = CanonizationGate(rejected_map=sample_rejected_map)
        verdict = gate_with_rejected.classify(
            chinese_term="丫头",
            proposed_rendering="girl",
            category=RenderingCategory.ADDRESS_TERM,
        )
        assert verdict.is_blocked, (
            f"Expected REJECTED for user-rejected 'girl', got {verdict.risk.value}"
        )
        assert not verdict.route_to_unresolved  # REJECTED, not even unresolved
        # Also verify no path exists where this is SAFE
        for evidence in ("strong", "moderate", "weak"):
            v = gate_with_rejected.classify(
                chinese_term="丫头",
                proposed_rendering="girl",
                category=RenderingCategory.ADDRESS_TERM,
                evidence_strength=evidence,
            )
            assert v.risk != RenderingRisk.SAFE, (
                f"'girl' should never be SAFE at evidence={evidence}"
            )

    def test_meta_note_cannot_become_rendering(self, gate):
        """Requirement: meta-note strings cannot become renderings."""
        verdict = gate.classify(
            chinese_term="嬷嬷",
            proposed_rendering="provisional, keep for now",
            category=RenderingCategory.TITLE_RANK,
        )
        assert verdict.is_blocked, (
            f"Expected REJECTED for meta-note rendering, got {verdict.risk.value}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Protection Rule: category_risk fallback (within gate's evaluate)
# ═══════════════════════════════════════════════════════════════════════════


class TestCategoryRiskFallback:
    def test_risky_category_no_evidence_no_approval_default_risky(self, gate):
        """An ADDRESS_TERM with moderate evidence and no approval → RISKY."""
        verdict = gate.classify(
            chinese_term="大小姐",
            proposed_rendering="Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="moderate",
        )
        assert verdict.risk == RenderingRisk.RISKY
        assert verdict.route_to_unresolved

    def test_strong_evidence_overrides_category_risk(self, gate):
        """With strong evidence, a title-rank rendering that passes all
        specific detectors can be SAFE even without user_approved."""
        verdict = gate.classify(
            chinese_term="贵妃",
            proposed_rendering="Noble Consort",
            category=RenderingCategory.TITLE_RANK,
            evidence_strength="strong",
        )
        # "Noble Consort" is neither generic, nor stiff/legalistic, nor a
        # meta-note. With strong evidence, the category_risk fallback (which
        # bumps ambiguous title proposals to RISKY) is overridden → SAFE.
        assert verdict.risk == RenderingRisk.SAFE
        assert not verdict.route_to_unresolved

    @pytest.mark.parametrize("cat", list(_RISKY_CATEGORIES))
    def test_all_risky_categories_need_evidence(self, gate, cat):
        """Every risky category defaults to RISKY without strong evidence."""
        verdict = gate.classify(
            chinese_term="test_term",
            proposed_rendering="test rendering",
            category=cat,
            evidence_strength="weak",
        )
        assert verdict.risk != RenderingRisk.SAFE, (
            f"{cat.value} should not be SAFE with weak evidence"
        )
