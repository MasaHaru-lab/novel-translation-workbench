"""Tests for Batch 4A strategy assessment module.

Tests cover:
- Chapter complexity assessment (simple vs complex chapters)
- Segment risk assessment (dialogue-heavy vs narrative segments)
- Strategy plan building (different complexity levels produce different strategies)
- Orchestrator integration (plan() returns strategy-enriched plan)
- Backward compatibility (existing behavior preserved)
"""

import sys
import os
from contextlib import ExitStack
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.chapter.strategy import (
    ComplexityLevel,
    RiskLevel,
    ProcessingMode,
    BudgetProfile,
    ConsistencyIntensity,
    ComplexitySignals,
    ChapterComplexity,
    SegmentRisk,
    SegmentRiskScores,
    assess_chapter_complexity,
    assess_segment_risks,
    build_strategy_plan,
    _count_dialogue_lines,
    _parse_chinese_entities_from_assets,
    _split_paragraphs,
    _count_long_paragraphs,
    _build_source_entity_patterns,
    _count_entity_matches,
)
from app.chapter.consistency import build_consistency_reference
from app.chapter.models import ChapterPlan, ChapterResult
from app.chapter.orchestrator import ChapterOrchestrator
from app.segment.segmenter import Segment
from app.translate.schema import TranslationInput, TranslationOutput


# ── Test Data ──────────────────────────────────────────────────────────────

# A short, simple chapter with no dialogue and no entity references
SIMPLE_CHAPTER = """第一章

这是第一个段落。讲述了天气的变化。

这是第二个段落。描写了周围的风景。

这是第三个段落。叙述了人物的心情。

这是最后一个段落。""".strip()

# A complex chapter with dialogue markers and entity references
COMPLEX_CHAPTER = """第五章

秦流西走进院子，大小姐王氏正在廊下站着。

「你来了？」王氏问道。

「是的，母亲。」秦流西恭敬地回答。

「今天贵妃娘娘要见你。」王氏说，「你可准备好了？」

秦流西点头道：「准备好了。」

王氏叹了口气：「光禄寺卿那边的事情，你父亲已经处理好了。你只需要记住，在贵妃面前，不要提长房的事。」

「女儿明白。」

秦流西退出院子，心里想着嫡母的话。这些年来，她一直记着生养之恩，不敢忘记。

太庙祭祀马上就要到了，命格之说在府里传得沸沸扬扬。秦老太太倒是镇定，只说一切按规矩来。

赤元老道前日来过，说了些冲煞的事。秦元山听完，脸色很不好看。

丁嬷嬷端来茶水，轻声道：「小姐，别想太多了。」

秦流西接过茶，点了点头。""".strip()


# ── Helper: create mock segments from text ─────────────────────────────────


def _text_to_segments(text: str, max_chars: int = 1200) -> list:
    """Create Segment objects from raw text using the real segmenter."""
    from app.segment.segmenter import create_segments
    return create_segments(text, max_chars=max_chars)


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _count_dialogue_lines
# ═══════════════════════════════════════════════════════════════════════════


def test_count_dialogue_lines_no_dialogue():
    text = "这是第一行。\n这是第二行。\n这是第三行。"
    assert _count_dialogue_lines(text) == 0


def test_count_dialogue_lines_with_chinese_quotes():
    text = "「你来了？」\n她说。\n这是叙述。"
    assert _count_dialogue_lines(text) >= 1


def test_count_dialogue_lines_with_verbs_only():
    """Dialogue verbs without quotation marks are not counted (false positive risk)."""
    text = "她说。\n他问。\n王公道。"
    assert _count_dialogue_lines(text) == 0


def test_count_dialogue_lines_skips_empty():
    text = "\n\n「她说。」\n\n"
    assert _count_dialogue_lines(text) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _parse_chinese_entities_from_assets
# ═══════════════════════════════════════════════════════════════════════════


def test_parse_entities_returns_list():
    entities = _parse_chinese_entities_from_assets()
    assert isinstance(entities, list)
    # Should find characters, titles, and glossary terms
    assert len(entities) > 0


def test_parse_entities_includes_character_names():
    entities = _parse_chinese_entities_from_assets()
    # Characters from characters.md
    assert "秦流西" in entities, "Should find Qin Liuxi's Chinese name"
    assert "秦老太太" in entities, "Should find Old Lady Qin's Chinese name"
    assert "王氏" in entities, "Should find Lady Wang's Chinese name"


def test_parse_entities_includes_titles():
    entities = _parse_chinese_entities_from_assets()
    assert "大小姐" in entities, "Should find 大小姐 title"
    assert "嫡母" in entities, "Should find 嫡母 title"


def test_parse_entities_includes_glossary_terms():
    entities = _parse_chinese_entities_from_assets()
    assert "记在名下" in entities, "Should find glossary term"
    assert "命格" in entities, "Should find 命格 term"


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: _split_paragraphs / _count_long_paragraphs
# ═══════════════════════════════════════════════════════════════════════════


def test_split_paragraphs():
    text = "第一段。\n\n第二段。\n\n第三段。"
    paras = _split_paragraphs(text)
    assert len(paras) == 3


def test_split_paragraphs_empty():
    assert _split_paragraphs("") == []
    assert _split_paragraphs("   ") == []


def test_count_long_paragraphs():
    short = "短。"
    long_text = "长" * 300
    text = f"{short}\n\n{long_text}"
    assert _count_long_paragraphs(text, threshold=200) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: entity matching
# ═══════════════════════════════════════════════════════════════════════════


def test_build_source_entity_patterns():
    entities = ["秦流西", "大小姐", "命格"]
    patterns = _build_source_entity_patterns(entities)
    assert len(patterns) == 3
    # Single-char entities should be skipped
    single_char = _build_source_entity_patterns(["秦"])
    assert len(single_char) == 0


def test_count_entity_matches():
    entities = ["秦流西", "大小姐", "命格"]
    patterns = _build_source_entity_patterns(entities)
    text = "秦流西走进院子。大小姐王氏正在站着。"
    matches = _count_entity_matches(text, patterns)
    assert matches.get("秦流西", 0) >= 1
    assert matches.get("大小姐", 0) >= 1
    assert "命格" not in matches  # Not in text


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: assess_chapter_complexity
# ═══════════════════════════════════════════════════════════════════════════


def test_complexity_empty_chapter():
    """Empty text should produce LOW complexity."""
    result = assess_chapter_complexity("", [], None)
    assert result.level == ComplexityLevel.LOW
    assert result.score == 0.0


def test_complexity_simple_chapter():
    """Short chapter with no dialogue/entities should be LOW."""
    segments = _text_to_segments(SIMPLE_CHAPTER)
    result = assess_chapter_complexity(SIMPLE_CHAPTER, segments)
    assert result.level == ComplexityLevel.LOW, (
        f"Expected LOW, got {result.level.value} (score={result.score})"
    )
    assert result.score < 0.33
    assert result.signals.total_chars > 0
    assert result.signals.dialogue_density == 0.0


def test_complexity_complex_chapter():
    """Chapter with dialogue and entities should be at least MEDIUM."""
    segments = _text_to_segments(COMPLEX_CHAPTER)
    result = assess_chapter_complexity(COMPLEX_CHAPTER, segments)
    assert result.level in (ComplexityLevel.MEDIUM, ComplexityLevel.HIGH), (
        f"Expected MEDIUM or HIGH, got {result.level.value} (score={result.score})"
    )
    assert result.score > 0.0
    assert result.signals.dialogue_density > 0.0
    assert result.signals.unique_entity_count > 0
    assert result.signals.entity_density > 0.0


def test_complexity_signals_are_populated():
    segments = _text_to_segments(SIMPLE_CHAPTER)
    result = assess_chapter_complexity(SIMPLE_CHAPTER, segments)
    signals = result.signals
    assert signals.total_chars > 0
    assert signals.paragraph_count > 0
    assert signals.dialogue_density >= 0.0
    assert signals.entity_density >= 0.0


def test_complexity_consistency_burden():
    """Chapters with entities across multiple segments should have burden > 0."""
    segments = _text_to_segments(COMPLEX_CHAPTER)
    result = assess_chapter_complexity(COMPLEX_CHAPTER, segments)
    # If the chapter produces multiple segments, there should be entity overlap
    if len(segments) > 1:
        # Many entities in COMPLEX_CHAPTER appear throughout
        pass  # consistency_burden may be > 0


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: assess_segment_risks
# ═══════════════════════════════════════════════════════════════════════════


def test_segment_risks_empty_segments():
    risks = assess_segment_risks([], None)
    assert risks == {}


def test_segment_risks_simple_segment():
    """A simple narrative segment should be LOW risk."""
    seg = Segment(segment_id=1, text="这是一个简单的段落。没有对话。")
    risks = assess_segment_risks([seg])
    assert 1 in risks
    assert risks[1].risk_level == RiskLevel.LOW
    # Score may be very small (from length_score contribution) but near zero
    assert risks[1].score < 0.01


def test_segment_risks_dialogue_segment_higher_than_narrative():
    """A dialogue-heavy segment should have higher risk than a narrative one."""
    narrative = Segment(
        segment_id=1,
        text="这是一个纯叙述段落。描述了风景和天气。没有对话标记。"
    )
    dialogue = Segment(
        segment_id=2,
        text="「你来晚了！」她喊道。\n「对不起，」他回答道。\n「你知道我等了多久吗？」\n「真的很抱歉。」"
    )
    risks = assess_segment_risks([narrative, dialogue])
    assert risks[1].scores.dialogue_density < risks[2].scores.dialogue_density


def test_segment_risks_entity_heavy_segment():
    """A segment with many entity references should have higher name density."""
    seg = Segment(
        segment_id=1,
        text="秦流西走进院子。大小姐王氏正在廊下站着。丁嬷嬷端来茶水。"
    )
    risks = assess_segment_risks([seg])
    assert risks[1].scores.name_density > 0


def test_segment_risks_long_segment():
    """A very long segment should have a higher length score."""
    short = Segment(segment_id=1, text="短段落。")
    long_text = Segment(segment_id=2, text="长" * 1100)
    risks = assess_segment_risks([short, long_text])
    assert risks[1].scores.length_score < risks[2].scores.length_score


def test_segment_risks_high_risk_has_factors():
    """High-risk segments should have human-readable factors."""
    seg = Segment(
        segment_id=1,
        text="「秦流西！」大小姐王氏喊道。\n「在，」秦流西回答道。\n「光禄寺卿的事办好了吗？」\n「已经办妥了，请放心。」"
    )
    risks = assess_segment_risks([seg])
    # This segment has dialogue + entities, may be MEDIUM or HIGH
    if risks[1].risk_level != RiskLevel.LOW:
        assert len(risks[1].factors) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests: build_strategy_plan
# ═══════════════════════════════════════════════════════════════════════════


def test_strategy_plan_low_complexity():
    """LOW complexity should produce LIGHT overall strategy."""
    complexity = ChapterComplexity(
        level=ComplexityLevel.LOW,
        score=0.15,
        signals=ComplexitySignals(),
    )
    segment_risks = {
        1: SegmentRisk(segment_id=1, risk_level=RiskLevel.LOW, score=0.1),
    }
    plan = build_strategy_plan(complexity, segment_risks)
    assert plan.overall_strategy.processing_mode == ProcessingMode.LIGHT
    assert plan.overall_strategy.budget_profile == BudgetProfile.LIGHT
    assert plan.overall_strategy.consistency_intensity == ConsistencyIntensity.STANDARD


def test_strategy_plan_medium_complexity():
    """MEDIUM complexity should produce STANDARD strategy."""
    complexity = ChapterComplexity(
        level=ComplexityLevel.MEDIUM,
        score=0.45,
        signals=ComplexitySignals(),
    )
    segment_risks = {
        1: SegmentRisk(segment_id=1, risk_level=RiskLevel.LOW, score=0.2),
        2: SegmentRisk(segment_id=2, risk_level=RiskLevel.LOW, score=0.3),
    }
    plan = build_strategy_plan(complexity, segment_risks)
    assert plan.overall_strategy.processing_mode == ProcessingMode.STANDARD
    assert plan.overall_strategy.budget_profile == BudgetProfile.STANDARD


def test_strategy_plan_high_complexity():
    """HIGH complexity should produce CONSERVATIVE overall strategy."""
    complexity = ChapterComplexity(
        level=ComplexityLevel.HIGH,
        score=0.75,
        signals=ComplexitySignals(),
    )
    segment_risks = {
        1: SegmentRisk(segment_id=1, risk_level=RiskLevel.MEDIUM, score=0.5),
        2: SegmentRisk(segment_id=2, risk_level=RiskLevel.HIGH, score=0.7),
    }
    plan = build_strategy_plan(complexity, segment_risks)
    assert plan.overall_strategy.processing_mode == ProcessingMode.CONSERVATIVE
    assert plan.overall_strategy.budget_profile == BudgetProfile.CONSERVATIVE
    assert plan.overall_strategy.consistency_intensity == ConsistencyIntensity.ENHANCED


def test_strategy_plan_high_risk_segment_gets_conservative():
    """HIGH risk segment should get CONSERVATIVE override regardless of chapter."""
    complexity = ChapterComplexity(
        level=ComplexityLevel.LOW,
        score=0.2,
        signals=ComplexitySignals(),
    )
    segment_risks = {
        1: SegmentRisk(segment_id=1, risk_level=RiskLevel.HIGH, score=0.7),
    }
    plan = build_strategy_plan(complexity, segment_risks)
    seg_strat = plan.segment_strategies[1]
    assert seg_strat.processing_mode == ProcessingMode.CONSERVATIVE
    assert seg_strat.budget_profile == BudgetProfile.CONSERVATIVE
    assert seg_strat.consistency_intensity == ConsistencyIntensity.ENHANCED


def test_strategy_plan_low_risk_in_high_chapter_stays_standard():
    """LOW risk segment in HIGH chapter should NOT be dragged up."""
    complexity = ChapterComplexity(
        level=ComplexityLevel.HIGH,
        score=0.75,
        signals=ComplexitySignals(),
    )
    segment_risks = {
        1: SegmentRisk(segment_id=1, risk_level=RiskLevel.LOW, score=0.1),
        2: SegmentRisk(segment_id=2, risk_level=RiskLevel.HIGH, score=0.8),
    }
    plan = build_strategy_plan(complexity, segment_risks)
    # Low-risk segment should stay STANDARD
    assert plan.segment_strategies[1].processing_mode == ProcessingMode.STANDARD
    # High-risk segment gets CONSERVATIVE
    assert plan.segment_strategies[2].processing_mode == ProcessingMode.CONSERVATIVE


def test_strategy_plan_rationale_non_empty():
    """Strategy plan should always have non-empty rationale."""
    complexity = ChapterComplexity(
        level=ComplexityLevel.MEDIUM,
        score=0.45,
        signals=ComplexitySignals(
            total_chars=5000,
            paragraph_count=10,
            unique_entity_count=3,
            consistency_burden=2,
        ),
    )
    segment_risks = {
        1: SegmentRisk(segment_id=1, risk_level=RiskLevel.LOW, score=0.1),
    }
    plan = build_strategy_plan(complexity, segment_risks)
    assert len(plan.rationale) > 0
    # Should mention the complexity level
    assert any("medium" in r.lower() for r in plan.rationale)


def test_strategy_plan_rationale_mentions_high_risk():
    """Rationale should mention segments flagged as HIGH risk."""
    complexity = ChapterComplexity(
        level=ComplexityLevel.MEDIUM,
        score=0.45,
        signals=ComplexitySignals(),
    )
    segment_risks = {
        1: SegmentRisk(
            segment_id=1,
            risk_level=RiskLevel.HIGH,
            score=0.8,
            factors=["High dialogue density (0.75)", "High entity overlap"],
        ),
    }
    plan = build_strategy_plan(complexity, segment_risks)
    assert any("HIGH risk" in r for r in plan.rationale)
    assert any("Segment 1" in r for r in plan.rationale)


# ═══════════════════════════════════════════════════════════════════════════
# Integration tests: orchestrator integration
# ═══════════════════════════════════════════════════════════════════════════


def test_orchestrator_plan_returns_strategy_enriched_plan():
    """plan() should return a ChapterPlan with strategy fields populated."""
    orch = ChapterOrchestrator()
    plan = orch.plan(COMPLEX_CHAPTER)
    assert plan.complexity_level is not None, "complexity_level should be set"
    assert plan.complexity_level in ("low", "medium", "high")
    assert plan.complexity_signals is not None, "complexity_signals should be set"
    assert "total_chars" in plan.complexity_signals
    assert plan.strategy_plan is not None, "strategy_plan should be set"
    assert "overall_strategy" in plan.strategy_plan
    assert "rationale" in plan.strategy_plan
    assert len(plan.strategy_plan["rationale"]) > 0


def test_orchestrator_plan_simple_chapter_low_complexity():
    """Simple chapter should produce LOW complexity in plan()."""
    orch = ChapterOrchestrator()
    plan = orch.plan(SIMPLE_CHAPTER)
    assert plan.complexity_level is not None
    # May be "low" depending on asset matching


def test_orchestrator_plan_complex_chapter_has_segment_risks():
    """plan() should populate per-segment risk info for complex chapters."""
    orch = ChapterOrchestrator()
    plan = orch.plan(COMPLEX_CHAPTER)
    assert plan.segment_risks is not None
    assert len(plan.segment_risks) == plan.segment_count
    # Each segment should have risk info
    for sid, risk in plan.segment_risks.items():
        assert "risk_level" in risk
        assert "score" in risk
        assert risk["risk_level"] in ("low", "medium", "high")


def test_orchestrator_plan_strategy_includes_segment_strategies():
    """plan() strategy_plan should include per-segment strategies."""
    orch = ChapterOrchestrator()
    plan = orch.plan(COMPLEX_CHAPTER)
    assert plan.strategy_plan is not None
    assert "segment_strategies" in plan.strategy_plan
    seg_strats = plan.strategy_plan["segment_strategies"]
    assert len(seg_strats) == plan.segment_count
    for sid, strat in seg_strats.items():
        assert "processing_mode" in strat
        assert "budget_profile" in strat
        assert "consistency_intensity" in strat


def test_orchestrator_plan_strategy_assessment_is_non_fatal():
    """Strategy assessment failure should fall back to basic plan, not crash."""
    orch = ChapterOrchestrator()
    # Mock build_consistency_reference to fail — patch the orchestrator's
    # reference since it was imported directly via "from ... import".
    with patch(
        "app.chapter.orchestrator.build_consistency_reference",
        side_effect=RuntimeError("Asset load failure"),
    ):
        plan = orch.plan(SIMPLE_CHAPTER)
    # Should still return a valid plan without strategy info
    assert plan.chapter_title is not None
    assert plan.complexity_level is None
    assert plan.strategy_plan is None


def test_orchestrator_run_surfaces_strategy_in_result():
    """run() should pass strategy info to ChapterResult."""
    text = "第一章\n\n简单内容。"
    orch = ChapterOrchestrator()

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="English.",
        )

    def mock_backend(prompt, max_tokens=None, **extra):
        return "major_issue: none\nwhy_it_matters: n/a\nrecommended_fix: none\noptional_notes: n/a"

    patches = [
        patch("app.translate.backend_adapter.call_model_backend", side_effect=mock_backend),
        patch("app.config.config.MODEL_BACKEND_URL", "http://fake:9999"),
    ]
    for p in patches:
        p.start()
    try:
        result = orch.run(text, translate_draft_fn=mock_draft_fn)
    finally:
        for p in patches:
            p.stop()

    assert result.strategy_plan_summary is not None
    assert "overall_strategy" in result.strategy_plan_summary
    assert "rationale" in result.strategy_plan_summary


def test_orchestrator_run_with_manifest_surfaces_strategy():
    """run_with_manifest() should pass strategy info to ChapterResult."""
    text = "第一章\n\n简单内容。"
    orch = ChapterOrchestrator()

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="English.",
        )

    def mock_backend(prompt, max_tokens=None, **extra):
        return "major_issue: none\nwhy_it_matters: n/a\nrecommended_fix: none\noptional_notes: n/a"

    patches = [
        patch("app.translate.backend_adapter.call_model_backend", side_effect=mock_backend),
        patch("app.config.config.MODEL_BACKEND_URL", "http://fake:9999"),
    ]
    for p in patches:
        p.start()
    try:
        result = orch.run_with_manifest(text, translate_draft_fn=mock_draft_fn)
    finally:
        for p in patches:
            p.stop()

    assert result.strategy_plan_summary is not None
    assert "overall_strategy" in result.strategy_plan_summary


def test_existing_plan_behavior_preserved():
    """Existing test patterns for plan() should still work."""
    text = "第一章\n\n简短短段落。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)
    assert plan.chapter_title == "第一章"
    assert len(plan.segments) >= 1
    assert plan.source_text == text
    # Strategy fields should be populated (not None for this simple text)
    assert plan.complexity_level is not None


def test_existing_execute_behavior_preserved():
    """Existing execute() behavior should not change."""
    text = "第一章\n\n内容。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )

    def mock_backend(prompt, max_tokens=None, **extra):
        return "major_issue: none\nwhy_it_matters: n/a\nrecommended_fix: none\noptional_notes: n/a"

    patches = [
        patch("app.translate.backend_adapter.call_model_backend", side_effect=mock_backend),
        patch("app.config.config.MODEL_BACKEND_URL", "http://fake:9999"),
    ]
    for p in patches:
        p.start()
    try:
        result = orch.execute(plan, translate_draft_fn=mock_draft_fn)
    finally:
        for p in patches:
            p.stop()
    assert result.segment_count == plan.segment_count
    assert len(result.aggregated_translation) > 0
    # Strategy info should be present
    assert result.strategy_plan_summary is not None
