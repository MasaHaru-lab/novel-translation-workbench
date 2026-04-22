"""Pre-execution strategy assessment for chapter-level translation.

Batch 4A: before executing segments, the system assesses chapter complexity
and segment risks, producing a strategy-aware plan. Strategy decisions are
recorded and visible in artifacts but do NOT change runtime execution
behavior in this batch — that is Batch 4B's domain.

This module contains only pure planning intelligence functions with no side
effects. It does NOT import or modify any runtime execution code.
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.chapter.consistency import ConsistencyReference
from app.segment.segmenter import Segment

logger = logging.getLogger(__name__)

# ── Enums ──────────────────────────────────────────────────────────────────


class ComplexityLevel(str, Enum):
    """Overall complexity level of a chapter."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskLevel(str, Enum):
    """Risk level for a single segment."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProcessingMode(str, Enum):
    """Recommended processing mode for a segment or chapter."""
    STANDARD = "standard"
    CONSERVATIVE = "conservative"
    LIGHT = "light"


class BudgetProfile(str, Enum):
    """Recommended budget profile for a segment or chapter."""
    STANDARD = "standard"
    CONSERVATIVE = "conservative"
    LIGHT = "light"


class ConsistencyIntensity(str, Enum):
    """Recommended consistency check intensity."""
    STANDARD = "standard"
    ENHANCED = "enhanced"


# ── Data Models ────────────────────────────────────────────────────────────


@dataclass
class ComplexitySignals:
    """Raw signals extracted from the chapter source text."""

    total_chars: int = 0
    """Total character count of the source text."""

    paragraph_count: int = 0
    """Number of paragraphs in the chapter."""

    dialogue_density: float = 0.0
    """Ratio of dialogue-carrying lines to total lines (0.0–1.0)."""

    entity_density: float = 0.0
    """Known entity mentions per 1000 characters in source text."""

    long_paragraph_ratio: float = 0.0
    """Ratio of paragraphs exceeding 200 characters."""

    unique_entity_count: int = 0
    """Number of distinct entities (characters, titles, terms) found in source."""

    consistency_burden: int = 0
    """Number of entities that appear across multiple segments, indicating
    cross-segment consistency risk."""


@dataclass
class ChapterComplexity:
    """Assessed complexity for a full chapter."""

    level: ComplexityLevel = ComplexityLevel.LOW
    """Overall complexity level."""

    score: float = 0.0
    """Composite complexity score (0.0–1.0)."""

    signals: ComplexitySignals = field(default_factory=ComplexitySignals)
    """Raw signals that produced this assessment."""


@dataclass
class SegmentRiskScores:
    """Per-dimension risk scores for a single segment."""

    name_density: float = 0.0
    """Character name mentions per 100 chars in segment."""

    dialogue_density: float = 0.0
    """Dialogue-carrying lines / total lines in segment."""

    term_density: float = 0.0
    """Glossary term mentions per 100 chars in segment."""

    length_score: float = 0.0
    """Normalized segment length score (0.0–1.0), based on how close the
    segment is to the max_chars boundary."""

    entity_overlap_score: float = 0.0
    """How many named entities this segment shares with its neighbors,
    normalized. Higher values mean higher cross-segment dependency."""

    novel_entity_ratio: float = 0.0
    """Ratio of entities found in this segment that are NOT in the project
    glossary/character/title assets. Higher values mean more novel terms."""


@dataclass
class SegmentRisk:
    """Assessed risk for a single segment."""

    segment_id: int
    risk_level: RiskLevel = RiskLevel.LOW
    score: float = 0.0
    factors: List[str] = field(default_factory=list)
    """Human-readable list of risk factors that contributed to this assessment."""

    scores: SegmentRiskScores = field(default_factory=SegmentRiskScores)


@dataclass
class StrategyDecision:
    """Strategy decisions for a segment or the whole chapter.

    In Batch 4A, these are recommendations recorded in the plan but NOT
    enforced at runtime. They become actionable in Batch 4B.
    """

    processing_mode: ProcessingMode = ProcessingMode.STANDARD
    budget_profile: BudgetProfile = BudgetProfile.STANDARD
    consistency_intensity: ConsistencyIntensity = ConsistencyIntensity.STANDARD
    segmentation_granularity: str = "standard"
    """'standard' or 'finer' — finer means smaller segment sizes."""


@dataclass
class StrategyPlan:
    """Complete strategy plan for a chapter run.

    Produced during the planning phase and recorded in the ChapterPlan.
    All fields are for visibility and future use — none affect runtime in 4A.
    """

    chapter_complexity: ChapterComplexity = field(default_factory=ChapterComplexity)
    segment_risks: Dict[int, SegmentRisk] = field(default_factory=dict)
    overall_strategy: StrategyDecision = field(default_factory=StrategyDecision)
    segment_strategies: Dict[int, StrategyDecision] = field(default_factory=dict)
    rationale: List[str] = field(default_factory=list)
    """Human-readable explanations of key strategy decisions."""


# ── Chinese source entity extraction from project assets ───────────────────

# Pattern to extract Chinese names from "### EnglishName (中文名)" headings
_CHINESE_NAME_IN_PARENS_RE = re.compile(r"\(([^)]*[一-鿿][^)]*)\)")

# Pattern for markdown headings (### term)
_HEADING_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)


def _extract_chinese_entity_names(reference: ConsistencyReference) -> List[str]:
    """Extract Chinese source-language entity names from the consistency reference.

    Returns a list of Chinese strings (character names from parentheticals,
    and title/glossary headings which are already in Chinese).
    This is used for matching against the Chinese source text to compute
    entity density signals.
    """
    entities: List[str] = []

    # Characters: headings are "English (中文)", extract the Chinese part
    for char_ref in reference.characters:
        # We don't have the heading text in CharacterRef, so we parse
        # the English canonical as a hint. The Chinese names are not
        # stored in CharacterRef — they need to come from the asset file.
        # In practice, we match by scanning for the Chinese terms.
        pass

    # Titles: headings ARE Chinese (e.g. "### 大小姐")
    # Glossary: headings ARE Chinese (e.g. "### 记在名下")
    # These are not stored in the reference objects either.

    return entities


def _parse_chinese_entities_from_assets() -> List[str]:
    """Parse Chinese source terms directly from project asset files.

    Reads characters.md, titles_and_terms.md, and glossary.md to extract
    the Chinese source-language terms for entity matching.

    Handles two formats:
    - Characters: Chinese name in ``- Chinese: 秦流西`` lines
    - Titles and glossary: Chinese term in ``### 大小姐`` headings

    Returns a list of Chinese term strings.
    """
    from app.translate.project_context import load_asset

    entities: List[str] = []
    seen: set = set()

    # Pattern for "- Chinese: 中文名" lines
    chinese_line_re = re.compile(r"-\s*Chinese\s*:\s*(.+)", re.IGNORECASE)

    # Characters: extract Chinese names from "- Chinese: 秦流西" lines
    chars_text = load_asset("characters") or ""
    for match in chinese_line_re.finditer(chars_text):
        chinese_name = match.group(1).strip()
        if chinese_name and chinese_name not in seen:
            seen.add(chinese_name)
            entities.append(chinese_name)

    # Titles and glossary: extract Chinese terms from "### 中文术语" headings
    for asset_name in ("titles_and_terms", "glossary"):
        text = load_asset(asset_name) or ""
        for match in _HEADING_RE.finditer(text):
            term = match.group(1).strip()
            if term and term not in seen and bool(re.search(r'[一-鿿]', term)):
                seen.add(term)
                entities.append(term)

    return entities


# ── Chinese dialogue detection ────────────────────────────────────────────

# Chinese quotation mark patterns
_CHINESE_QUOTE_RE = re.compile(r'[“”「」『』""«»]')
# Chinese dialogue verbs (indicators that a line contains spoken dialogue)
_DIALOGUE_VERBS_RE = re.compile(r'[说曰道问答云言讲叫嚷喊呼骂喝]')


def _count_dialogue_lines(text: str) -> int:
    """Count lines in the text that contain dialogue indicators.

    A line is considered dialogue-carrying if it contains Chinese quotation
    marks (「」, "", 「」, 『』). Dialogue verbs alone are NOT counted
    because they commonly appear inside narrative words (e.g. 讲述, 听说)
    and produce false positives.
    """
    lines = text.splitlines()
    count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _CHINESE_QUOTE_RE.search(stripped):
            count += 1
    return count


def _has_dialogue_markers(text: str) -> bool:
    """Check if text contains Chinese quotation marks."""
    return bool(_CHINESE_QUOTE_RE.search(text))


# ── Entity matching in source text ────────────────────────────────────────


def _build_source_entity_patterns(chinese_entities: List[str]) -> List[re.Pattern]:
    """Build compiled regex patterns for matching Chinese entities in source text.

    Multi-character entities are matched as whole substrings. Single-character
    entities are skipped to avoid false positives.
    """
    patterns = []
    for entity in chinese_entities:
        if len(entity) < 2:
            continue
        try:
            patterns.append(re.compile(re.escape(entity)))
        except re.error:
            continue
    return patterns


def _count_entity_matches(text: str, patterns: List[re.Pattern]) -> Dict[str, int]:
    """Count occurrences of each entity pattern in the given text.

    Returns a dict mapping the entity string to its occurrence count.
    """
    matches: Dict[str, int] = {}
    for pat in patterns:
        count = len(pat.findall(text))
        if count > 0:
            matches[pat.pattern] = count
    return matches


def _find_entity_spans(patterns: List[re.Pattern], text: str) -> List[Tuple[int, int, str]]:
    """Find (start, end, entity) spans for all entity matches in text."""
    spans: List[Tuple[int, int, str]] = []
    for pat in patterns:
        for m in pat.finditer(text):
            spans.append((m.start(), m.end(), pat.pattern))
    return spans


# ── Paragraph splitting (reuse existing logic) ────────────────────────────


def _split_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs (by blank lines)."""
    paragraphs = re.split(r'\n\s*\n', text.strip())
    return [p.strip() for p in paragraphs if p.strip()]


def _count_paragraphs(text: str) -> int:
    """Count non-empty paragraphs in text."""
    return len(_split_paragraphs(text))


def _count_long_paragraphs(text: str, threshold: int = 200) -> int:
    """Count paragraphs exceeding the given character threshold."""
    paras = _split_paragraphs(text)
    return sum(1 for p in paras if len(p) > threshold)


# ── Chapter Complexity Assessment ─────────────────────────────────────────


def assess_chapter_complexity(
    source_text: str,
    segments: List[Segment],
    reference: Optional[ConsistencyReference] = None,
) -> ChapterComplexity:
    """Assess the overall complexity of a chapter based on source text signals.

    Considers:
    - Total length (char count, paragraph count)
    - Dialogue density (proportion of lines with dialogue indicators)
    - Entity density (known character/title/glossary mentions per 1000 chars)
    - Long paragraph ratio (paragraphs exceeding 200 chars)
    - Unique entity count (distinct named entities found)
    - Consistency burden (entities spanning multiple segments)

    Args:
        source_text: Full chapter source text in Chinese.
        segments: Segments produced by the segmenter (for cross-segment analysis).
        reference: Optional pre-built ConsistencyReference from project assets.
            If not provided, Chinese entities are parsed directly from assets.

    Returns:
        ChapterComplexity with level, score, and raw signals.
    """
    if not source_text.strip():
        return ChapterComplexity(
            level=ComplexityLevel.LOW,
            score=0.0,
            signals=ComplexitySignals(),
        )

    # Build entity patterns from project assets
    chinese_entities = _parse_chinese_entities_from_assets()
    entity_patterns = _build_source_entity_patterns(chinese_entities)

    # Raw signals
    total_chars = len(source_text)
    para_count = _count_paragraphs(source_text)
    total_lines = max(len(source_text.splitlines()), 1)
    dialogue_lines = _count_dialogue_lines(source_text)
    long_para_count = _count_long_paragraphs(source_text)

    # Entity signals
    entity_counts = _count_entity_matches(source_text, entity_patterns)
    total_entity_matches = sum(entity_counts.values())
    unique_entity_count = len(entity_counts)

    # Consistency burden: entities that appear in more than one segment
    entity_segment_map: Dict[str, set] = {}
    for seg in segments:
        seg_entities = _count_entity_matches(seg.text, entity_patterns)
        for entity in seg_entities:
            entity_segment_map.setdefault(entity, set()).add(seg.segment_id)
    consistency_burden = sum(
        1 for segs in entity_segment_map.values() if len(segs) > 1
    )

    # Normalized signals (0.0–1.0)
    dialogue_density = dialogue_lines / total_lines
    entity_density = (total_entity_matches / max(total_chars, 1)) * 1000.0  # per 1K chars
    long_para_ratio = long_para_count / max(para_count, 1)
    # Length factor: sigmoid-like normalization — 5000 chars = ~0.33, 10000 = ~0.5, 20000 = ~0.67
    length_factor = min(1.0, total_chars / 30000.0)
    # Entity breadth factor
    entity_breadth = min(1.0, unique_entity_count / 15.0)
    # Consistency burden factor
    burden_factor = min(1.0, consistency_burden / 10.0)

    signals = ComplexitySignals(
        total_chars=total_chars,
        paragraph_count=para_count,
        dialogue_density=round(dialogue_density, 4),
        entity_density=round(entity_density, 4),
        long_paragraph_ratio=round(long_para_ratio, 4),
        unique_entity_count=unique_entity_count,
        consistency_burden=consistency_burden,
    )

    # Weighted composite score
    score = (
        entity_density / 10.0 * 0.25       # entity density (capped by min)
        + dialogue_density * 0.20           # dialogue density
        + burden_factor * 0.20              # consistency burden
        + length_factor * 0.20              # chapter length
        + long_para_ratio * 0.15            # long paragraph ratio
    )
    score = min(1.0, max(0.0, score))

    # Level threshold
    if score < 0.33:
        level = ComplexityLevel.LOW
    elif score < 0.66:
        level = ComplexityLevel.MEDIUM
    else:
        level = ComplexityLevel.HIGH

    logger.info(
        "Chapter complexity: level=%s, score=%.3f, signals=%s",
        level.value, score, signals,
    )

    return ChapterComplexity(level=level, score=round(score, 4), signals=signals)


# ── Segment Risk Assessment ───────────────────────────────────────────────


def _segment_dialogue_density(seg_text: str) -> float:
    """Compute dialogue density for a single segment."""
    lines = seg_text.splitlines()
    total = max(len([l for l in lines if l.strip()]), 1)
    dialogue = _count_dialogue_lines(seg_text)
    return dialogue / total


def _segment_name_density(seg_text: str, patterns: List[re.Pattern]) -> float:
    """Compute character name density (mentions per 100 chars) for a segment."""
    entity_counts = _count_entity_matches(seg_text, patterns)
    total_matches = sum(entity_counts.values())
    return total_matches / max(len(seg_text), 1) * 100.0


def _segment_term_density(seg_text: str, patterns: List[re.Pattern]) -> float:
    """Compute glossary/title term density (mentions per 100 chars) for a segment."""
    entity_counts = _count_entity_matches(seg_text, patterns)
    total_matches = sum(entity_counts.values())
    return total_matches / max(len(seg_text), 1) * 100.0


def _segment_length_score(seg_text: str, max_chars: int = 1200) -> float:
    """Normalized length score: how close segment is to max_chars boundary.

    Returns 0.0 for very short segments, approaching 1.0 for segments
    that are near or at the max_chars boundary.
    """
    length = len(seg_text)
    if length >= max_chars:
        return 1.0
    # Sigmoid-like: segments close to max_chars get higher scores
    return min(1.0, length / max_chars)


def _compute_entity_overlap(
    seg: Segment,
    all_spans: Dict[int, List[Tuple[int, int, str]]],
) -> float:
    """Compute entity overlap score between a segment and its neighbors.

    Counts entities that appear in both this segment and an adjacent segment.
    Returns normalized score (0.0–1.0).
    """
    my_entities = set(e for _, _, e in all_spans.get(seg.segment_id, []))
    if not my_entities:
        return 0.0

    neighbor_ids = []
    if seg.segment_id > 1:
        neighbor_ids.append(seg.segment_id - 1)
    if (seg.segment_id + 1) in all_spans:
        neighbor_ids.append(seg.segment_id + 1)

    if not neighbor_ids:
        return 0.0

    shared = 0
    for nid in neighbor_ids:
        neighbor_entities = set(e for _, _, e in all_spans.get(nid, []))
        shared += len(my_entities & neighbor_entities)

    avg_shared = shared / len(neighbor_ids)
    # Normalize: score 1.0 at 5+ shared entities
    return min(1.0, avg_shared / 5.0)


def _compute_novel_entity_ratio(
    seg_text: str,
    entity_patterns: List[re.Pattern],
    chinese_entities: List[str],
) -> float:
    """Compute ratio of entities in segment that are NOT in project assets.

    An entity is "novel" if its Chinese term appears in the segment text
    but does NOT match any known entity from project assets. Since we're
    matching AGAINST known entities, the "novel" entities are those
    detected patterns that don't correspond to known entities.

    In practice for Batch 4A, this is approximated by looking for
    Chinese named-entity-like patterns (2+ character sequences that look
    like names) that aren't in the known entity list.
    """
    # For now, novel entity detection is a placeholder that returns 0.
    # Full novel entity detection would require NER or character-level
    # pattern analysis beyond the scope of Batch 4A.
    return 0.0


def assess_segment_risks(
    segments: List[Segment],
    reference: Optional[ConsistencyReference] = None,
) -> Dict[int, SegmentRisk]:
    """Assess risk levels for each segment in a chapter.

    Evaluates each segment on multiple risk dimensions:
    - Character name density
    - Dialogue density
    - Glossary/title term density
    - Segment length
    - Entity overlap with neighbors (cross-segment dependency risk)
    - Novel entity ratio (unseen terms)

    Args:
        segments: List of Segment objects from the plan.
        reference: Optional ConsistencyReference (used for entity data).

    Returns:
        Dict mapping segment_id to SegmentRisk assessment.
    """
    if not segments:
        return {}

    chinese_entities = _parse_chinese_entities_from_assets()
    entity_patterns = _build_source_entity_patterns(chinese_entities)

    # Build entity span map for overlap computation
    all_spans: Dict[int, List[Tuple[int, int, str]]] = {}
    for seg in segments:
        all_spans[seg.segment_id] = _find_entity_spans(entity_patterns, seg.text)

    risks: Dict[int, SegmentRisk] = {}

    for seg in segments:
        seg_text = seg.text
        if not seg_text.strip():
            risks[seg.segment_id] = SegmentRisk(
                segment_id=seg.segment_id,
                risk_level=RiskLevel.LOW,
                score=0.0,
                factors=["Empty segment"],
            )
            continue

        # Compute per-dimension scores
        name_density = _segment_name_density(seg_text, entity_patterns)
        dialogue_density = _segment_dialogue_density(seg_text)
        term_density = _segment_term_density(seg_text, entity_patterns)
        length_score = _segment_length_score(seg_text)
        entity_overlap = _compute_entity_overlap(seg, all_spans)
        novel_ratio = _compute_novel_entity_ratio(seg_text, entity_patterns, chinese_entities)

        scores = SegmentRiskScores(
            name_density=round(name_density, 4),
            dialogue_density=round(dialogue_density, 4),
            term_density=round(term_density, 4),
            length_score=round(length_score, 4),
            entity_overlap_score=round(entity_overlap, 4),
            novel_entity_ratio=round(novel_ratio, 4),
        )

        # Collect risk factors
        factors: List[str] = []
        if name_density > 2.0:
            factors.append(f"High character name density ({name_density:.2f} per 100 chars)")
        if dialogue_density > 0.5:
            factors.append(f"High dialogue density ({dialogue_density:.2f})")
        if term_density > 1.0:
            factors.append(f"High term density ({term_density:.2f} per 100 chars)")
        if length_score > 0.8:
            factors.append(f"Long segment ({len(seg_text)} chars)")
        if entity_overlap > 0.4:
            factors.append(f"High entity overlap with adjacent segments ({entity_overlap:.2f})")

        # Composite risk score
        score = (
            min(1.0, name_density / 5.0) * 0.25
            + dialogue_density * 0.25
            + min(1.0, term_density / 3.0) * 0.15
            + length_score * 0.15
            + entity_overlap * 0.15
            + novel_ratio * 0.05
        )
        score = min(1.0, max(0.0, score))

        if score < 0.33:
            risk_level = RiskLevel.LOW
        elif score < 0.66:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.HIGH

        risks[seg.segment_id] = SegmentRisk(
            segment_id=seg.segment_id,
            risk_level=risk_level,
            score=round(score, 4),
            factors=factors,
            scores=scores,
        )

    return risks


# ── Strategy Plan Builder ─────────────────────────────────────────────────


def _build_overall_strategy(complexity: ChapterComplexity) -> StrategyDecision:
    """Build overall strategy decision based on chapter complexity.

    Rules:
    - LOW complexity → LIGHT processing, LIGHT budget, STANDARD consistency, STANDARD granularity
    - MEDIUM complexity → STANDARD processing, STANDARD budget, STANDARD consistency, STANDARD granularity
    - HIGH complexity → CONSERVATIVE processing, CONSERVATIVE budget, ENHANCED consistency, FINER granularity
    """
    if complexity.level == ComplexityLevel.LOW:
        return StrategyDecision(
            processing_mode=ProcessingMode.LIGHT,
            budget_profile=BudgetProfile.LIGHT,
            consistency_intensity=ConsistencyIntensity.STANDARD,
            segmentation_granularity="standard",
        )
    elif complexity.level == ComplexityLevel.HIGH:
        return StrategyDecision(
            processing_mode=ProcessingMode.CONSERVATIVE,
            budget_profile=BudgetProfile.CONSERVATIVE,
            consistency_intensity=ConsistencyIntensity.ENHANCED,
            segmentation_granularity="finer",
        )
    else:
        return StrategyDecision(
            processing_mode=ProcessingMode.STANDARD,
            budget_profile=BudgetProfile.STANDARD,
            consistency_intensity=ConsistencyIntensity.STANDARD,
            segmentation_granularity="standard",
        )


def _build_segment_strategy(
    risk: SegmentRisk,
    overall: StrategyDecision,
) -> StrategyDecision:
    """Build per-segment strategy, potentially overriding the overall strategy.

    Rules:
    - HIGH risk segment → CONSERVATIVE budget + ENHANCED consistency regardless of chapter
    - LOW risk segment in HIGH chapter → stays STANDARD (not dragged up by chapter)
    - Otherwise → inherit from overall strategy
    """
    if risk.risk_level == RiskLevel.HIGH:
        return StrategyDecision(
            processing_mode=ProcessingMode.CONSERVATIVE,
            budget_profile=BudgetProfile.CONSERVATIVE,
            consistency_intensity=ConsistencyIntensity.ENHANCED,
            segmentation_granularity=overall.segmentation_granularity,
        )
    elif risk.risk_level == RiskLevel.LOW and overall.processing_mode == ProcessingMode.CONSERVATIVE:
        # Low-risk segment in a high-complexity chapter: don't drag it up
        return StrategyDecision(
            processing_mode=ProcessingMode.STANDARD,
            budget_profile=BudgetProfile.STANDARD,
            consistency_intensity=ConsistencyIntensity.STANDARD,
            segmentation_granularity="standard",
        )
    else:
        return StrategyDecision(
            processing_mode=overall.processing_mode,
            budget_profile=overall.budget_profile,
            consistency_intensity=overall.consistency_intensity,
            segmentation_granularity=overall.segmentation_granularity,
        )


def _build_rationale(
    complexity: ChapterComplexity,
    segment_risks: Dict[int, SegmentRisk],
    overall: StrategyDecision,
) -> List[str]:
    """Build a human-readable list of rationale statements explaining key decisions."""
    rationale: List[str] = []

    rationale.append(
        f"Chapter complexity assessed as '{complexity.level.value}' "
        f"(composite score: {complexity.score:.3f})"
    )

    if complexity.signals.unique_entity_count > 0:
        rationale.append(
            f"Found {complexity.signals.unique_entity_count} unique entities "
            f"with {complexity.signals.consistency_burden} spanning multiple segments"
        )

    if complexity.signals.dialogue_density > 0.5:
        rationale.append(
            f"High dialogue density ({complexity.signals.dialogue_density:.2f})"
        )

    rationale.append(
        f"Overall strategy: {overall.processing_mode.value} processing, "
        f"{overall.budget_profile.value} budget, "
        f"{overall.consistency_intensity.value} consistency"
    )

    # Per-segment highlights
    high_risk_segments = [
        sid for sid, r in segment_risks.items() if r.risk_level == RiskLevel.HIGH
    ]
    if high_risk_segments:
        for sid in high_risk_segments:
            r = segment_risks[sid]
            factors_str = "; ".join(r.factors) if r.factors else "composite risk score"
            rationale.append(
                f"Segment {sid} flagged as HIGH risk: {factors_str}"
            )

    low_risk_segments = [
        sid for sid, r in segment_risks.items() if r.risk_level == RiskLevel.LOW
    ]
    if low_risk_segments and len(low_risk_segments) == len(segment_risks):
        rationale.append("All segments assessed as low risk — standard processing suitable")

    return rationale


def build_strategy_plan(
    complexity: ChapterComplexity,
    segment_risks: Dict[int, SegmentRisk],
) -> StrategyPlan:
    """Build a complete strategy plan from complexity and risk assessments.

    Produces overall strategy decisions and per-segment strategy overrides
    with human-readable rationale.

    Args:
        complexity: ChapterComplexity from assess_chapter_complexity().
        segment_risks: Dict from assess_segment_risks().

    Returns:
        StrategyPlan with all strategy decisions and rationale.
    """
    overall = _build_overall_strategy(complexity)

    segment_strategies: Dict[int, StrategyDecision] = {}
    for seg_id, risk in segment_risks.items():
        segment_strategies[seg_id] = _build_segment_strategy(risk, overall)

    rationale = _build_rationale(complexity, segment_risks, overall)

    return StrategyPlan(
        chapter_complexity=complexity,
        segment_risks=segment_risks,
        overall_strategy=overall,
        segment_strategies=segment_strategies,
        rationale=rationale,
    )
