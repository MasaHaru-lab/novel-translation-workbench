"""Canonization gate for translation-quality findings.

Before a proposed rendering becomes authoritative project memory
(a ``project_assets/`` entry), it must pass through this gate to ensure
that weak, risky, or user-rejected choices are not silently promoted
to canonical status.

This gate does not replace human judgment — it surfaces risk signals
so that operators can make informed decisions about what becomes
canonical project memory.

Usage::

    gate = CanonizationGate()
    proposal = ProposedRendering(
        chinese_term="大小姐",
        proposed_rendering="Young Lady",
        category=RenderingCategory.ADDRESS_TERM,
        evidence_strength="strong",
        user_approved=True,
    )
    verdict = gate.evaluate(proposal)
    if verdict.risk == RenderingRisk.SAFE:
        # Safe to promote to canonical assets
        ...
    elif verdict.risk == RenderingRisk.RISKY:
        # Route to unresolved_decisions — needs approval
        ...
    else:
        # REJECTED — do not canonize
        ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set


# ── Categories and Risk Levels ────────────────────────────────────────────


class RenderingCategory(str, Enum):
    """Category of a proposed asset entry.

    Used to determine applicable protection rules and routing.
    """

    ADDRESS_TERM = "address_term"
    """Address terms like 丫头, 大小姐 — high risk of flat translation."""

    KINSHIP_TERM = "kinship_term"
    """Kinship terms like 嫡母 — risk of legalistic or unnatural rendering."""

    TITLE_RANK = "title_rank"
    """Official titles and ranks like 贵妃, 光禄寺卿 — culturally loaded."""

    GLOSSARY_TERM = "glossary_term"
    """Concrete lexical entries like 大灃, 福礼 — lower risk."""

    CHARACTER_NAME = "character_name"
    """Character names — usually safe if phonetically accurate."""

    STYLE_NOTE = "style_note"
    """Behavioral guidance in style notes — low canonization risk."""

    UNKNOWN = "unknown"
    """Unclassified — treated cautiously."""


class RenderingRisk(str, Enum):
    """Risk level assigned by the self-audit step."""

    SAFE = "safe"
    """Canonization is safe — concrete, well-evidenced, no risk factors.
    May proceed directly to authoritative assets."""

    RISKY = "risky"
    """Risky — should go to unresolved_decisions instead of canonical files.
    Requires explicit approval or stronger evidence before promotion."""

    REJECTED = "rejected"
    """Rejected — cannot be canonized in this form.
    Typically meta-note strings, known-bad patterns, or user-rejected terms."""


# ── Data Models ───────────────────────────────────────────────────────────


@dataclass
class ProposedRendering:
    """A proposed rendering being evaluated for canonization."""

    chinese_term: str
    """The source Chinese term (e.g. '大小姐')."""

    proposed_rendering: str
    """The proposed English rendering (e.g. 'Young Lady')."""

    category: RenderingCategory = RenderingCategory.UNKNOWN
    """Category of the proposed entry."""

    source: str = ""
    """Source of the proposal (e.g. 'user_feedback', 'quality_audit',
    'benchmark_run_v3')."""

    user_approved: Optional[bool] = None
    """Whether the user explicitly approved this rendering.
    None = unknown, True = approved, False = rejected."""

    evidence_strength: str = "weak"
    """Strength of evidence: 'strong', 'moderate', or 'weak'."""

    notes: str = ""
    """Additional context or notes about the proposal."""


@dataclass
class RiskSignal:
    """A single risk signal detected during the self-audit."""

    signal_type: str
    """Identifier for the type of risk (e.g. 'generic_address',
    'meta_note_rendering', 'user_rejected')."""

    description: str
    """Human-readable explanation of the risk."""

    severity: str = "warning"
    """'blocker' (rendering rejected) or 'warning' (rendering risky)."""


@dataclass
class CanonizationVerdict:
    """Result of evaluating a proposed rendering through the canonization gate."""

    proposal: ProposedRendering
    risk: RenderingRisk = RenderingRisk.SAFE
    signals: List[RiskSignal] = field(default_factory=list)
    target_asset: str = ""
    """Which canonical asset file the rendering would target if safe."""

    verdict_summary: str = ""
    """One-line summary of the gate decision."""

    route_to_unresolved: bool = False
    """True if this proposal should be written to unresolved_decisions
    rather than a canonical asset file."""

    @property
    def is_blocked(self) -> bool:
        return self.risk == RenderingRisk.REJECTED

    @property
    def needs_approval(self) -> bool:
        return self.risk == RenderingRisk.RISKY


# ── Risk Category Defaults ────────────────────────────────────────────────

_RISKY_CATEGORIES: Set[RenderingCategory] = {
    RenderingCategory.ADDRESS_TERM,
    RenderingCategory.KINSHIP_TERM,
    RenderingCategory.TITLE_RANK,
}


# ── Protection Rule: Generic Address Terms ────────────────────────────────

_GENERIC_ENG_ADDRESS_TERMS: Set[str] = {
    "girl",
    "boy",
    "woman",
    "man",
    "lady",
    "sir",
    "miss",
    "mister",
    "master",
    "young lady",
    "young man",
    "old woman",
    "old man",
    "young woman",
    "young man",
    "little girl",
    "little boy",
}


def detect_generic_address(proposal: ProposedRendering) -> Optional[RiskSignal]:
    """Detect generic address-term renderings that risk flattening.

    Example: proposing 'girl' for 丫头 without explicit approval.
    """
    if proposal.category != RenderingCategory.ADDRESS_TERM:
        return None

    rendering_lower = proposal.proposed_rendering.strip().lower()

    if rendering_lower in _GENERIC_ENG_ADDRESS_TERMS:
        if proposal.user_approved is True:
            return None  # Explicitly approved — allow

        severity = "warning" if proposal.user_approved is None else "blocker"
        return RiskSignal(
            signal_type="generic_address",
            description=(
                f"Generic address rendering {proposal.proposed_rendering!r} for "
                f"Chinese address term {proposal.chinese_term!r}. "
                f"Generic English address terms risk flattening register and "
                f"household hierarchy in the translation."
            ),
            severity=severity,
        )

    return None


# ── Protection Rule: Stiff Kinship / Legalistic Renderings ────────────────

_STIFF_KINSHIP_PATTERNS: List[str] = [
    r"principal\s+(mother|wife|spouse)",
    r"primary\s+(mother|wife|spouse|consort|heir)",
    r"legal\s+(wife|spouse|heir|offspring|daughter|son)",
    r"concubine-born",
    r"legitimate\s+(son|daughter|child|heir|issue)",
    r"offspring\s+of\s+the\s+(main|principal|primary)",
    r"first\s+wife\s+(and\s+)?legal",
    r"born\s+of\s+the\s+(principal|legal|main)\s+wife",
]


def detect_stiff_kinship(proposal: ProposedRendering) -> Optional[RiskSignal]:
    """Detect stiff or legalistic kinship/status renderings.

    Already-canonical entries like 'legal mother' for 嫡母 are grandfathered
    (the gate only evaluates *new* proposals). New canonization attempts using
    similarly legalistic patterns for other terms require scrutiny.
    """
    if proposal.category not in (
        RenderingCategory.KINSHIP_TERM,
        RenderingCategory.TITLE_RANK,
    ):
        return None

    for pattern in _STIFF_KINSHIP_PATTERNS:
        if re.search(pattern, proposal.proposed_rendering.lower()):
            if proposal.user_approved is True:
                return None  # Explicitly approved

            return RiskSignal(
                signal_type="stiff_kinship",
                description=(
                    f"Proposed kinship/status rendering "
                    f"{proposal.proposed_rendering!r} matches stiff pattern "
                    f"{pattern!r}. Legal or bureaucratic renderings risk "
                    f"sounding unnatural in prose."
                ),
                severity="warning" if proposal.user_approved is None else "blocker",
            )

    return None


# ── Protection Rule: Meta-note as Rendering ────────────────────────────────

_META_NOTE_PATTERNS: List[str] = [
    r"keep\s+.*for\s+now",
    r"provisional",
    r"needs?\s+.*review",
    r"do\s+not",
    r"may\s+vary",
    r"tentative",
    r"for\s+now",
    r"work\s+in\s+progress",
    r"to\s+be\s+(decided|determined|reviewed|resolved)",
    r"under\s+discussion",
    r"current\s+working",
    r"context.sensitive",
    r"in\s+running\s+prose",
    r"in\s+context",
    r"see\s+notes",
    r"final\s+treatment",
    r"keep\s+stable",
    r"for\s+now",
    r"prefer",
    r"do\s+not\s+use",
]


def detect_meta_note_rendering(proposal: ProposedRendering) -> Optional[RiskSignal]:
    """Detect editorial/meta notes being proposed as renderings.

    Examples: 'keep Momo for now', 'provisional rendering',
    'needs system-level review'. These are meta-instructions, not English
    renderings, and must never become canonical.
    """
    rendering_lower = proposal.proposed_rendering.lower()

    for pattern in _META_NOTE_PATTERNS:
        if re.search(pattern, rendering_lower):
            return RiskSignal(
                signal_type="meta_note_rendering",
                description=(
                    f"Proposed rendering {proposal.proposed_rendering!r} "
                    f"contains editorial/meta language matching pattern "
                    f"{pattern!r}. Meta-instructions must not become "
                    f"canonical renderings."
                ),
                severity="blocker",
            )

    return None


# ── Protection Rule: Unapproved Benchmark Samples ─────────────────────────

_BENCHMARK_SOURCE_KEYWORDS: List[str] = [
    "benchmark",
    "quality run",
    "quality_run",
    "model output",
    "model_output",
    "translation run",
    "translation_run",
    "pipeline output",
]


def detect_unapproved_benchmark(proposal: ProposedRendering) -> Optional[RiskSignal]:
    """Detect benchmark-derived proposals that lack explicit approval.

    A rendering observed in a quality-run benchmark output should not become
    canonical merely because it appeared once in a model output.
    """
    if not proposal.source:
        return None

    source_lower = proposal.source.lower()
    has_benchmark_source = any(kw in source_lower for kw in _BENCHMARK_SOURCE_KEYWORDS)

    if has_benchmark_source and proposal.user_approved is not True:
        return RiskSignal(
            signal_type="unapproved_benchmark",
            description=(
                f"Proposal sourced from {proposal.source!r} but lacks "
                f"explicit user approval. A rendering produced by the model "
                f"in a single run is not sufficient evidence for canonization."
            ),
            severity="warning",
        )

    return None


# ── Protection Rule: Weak Evidence for Risky Categories ───────────────────

def detect_weak_evidence(proposal: ProposedRendering) -> Optional[RiskSignal]:
    """Enforce evidence thresholds for canonization.

    - 'strong': observed in multiple runs or explicitly user-approved
    - 'moderate': single reliable observation
    - 'weak': one-off occurrence, uncertain, or model-derived only

    Weak evidence for risky categories is a warning signal.
    """
    if proposal.evidence_strength in ("strong",):
        return None

    if proposal.category in _RISKY_CATEGORIES and proposal.evidence_strength == "weak":
        return RiskSignal(
            signal_type="weak_evidence",
            description=(
                f"Weak evidence ({proposal.evidence_strength!r}) for "
                f"{proposal.category.value} category rendering "
                f"{proposal.proposed_rendering!r}. Risky categories require "
                f"stronger evidence or explicit approval before canonization."
            ),
            severity="warning",
        )

    return None


# ── Rejected Alternatives Parsing (for user-rejection detection) ──────────

_REJECTED_ALT_LINE_RE = re.compile(
    r"Rejected alternatives?\s*:\s*(.+)", re.IGNORECASE
)
# Match terms inside double quotes or backticks
_QUOTED_TERM_RE = re.compile(r"""["`]([^"`]+)["`]""")


def parse_rejected_alternatives(asset_text: str) -> Dict[str, List[str]]:
    """Parse rejected alternatives from an asset file's markdown text.

    Looks for ``### {term}`` sections containing ``Rejected alternatives:``
    lines or ``- Notes:`` lines with quoted rejected forms.

    Returns a dict mapping the section heading (Chinese term) to a list of
    rejected rendering strings.
    """
    rejected: Dict[str, List[str]] = {}

    sections = re.split(r"^### ", asset_text, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().splitlines()
        chinese_heading = lines[0].strip() if lines else ""
        full_text = "\n".join(lines)

        # Collect all rejected alternatives from "Rejected alternatives:" lines
        for rej_match in _REJECTED_ALT_LINE_RE.finditer(full_text):
            alt_text = rej_match.group(1)
            quoted = _QUOTED_TERM_RE.findall(alt_text)
            if quoted:
                if chinese_heading not in rejected:
                    rejected[chinese_heading] = []
                for q in quoted:
                    qs = q.strip()
                    if qs and qs not in rejected[chinese_heading]:
                        rejected[chinese_heading].append(qs)

        # Also collect from Notes lines (which may embed rejected alternatives)
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- Notes:") or stripped.startswith("- notes:"):
                notes_text = stripped[len("- Notes:"):].strip()
                if "rejected" in notes_text.lower():
                    quoted = _QUOTED_TERM_RE.findall(notes_text)
                    if quoted:
                        if chinese_heading not in rejected:
                            rejected[chinese_heading] = []
                        for q in quoted:
                            qs = q.strip()
                            if qs and qs not in rejected[chinese_heading]:
                                rejected[chinese_heading].append(qs)

    return rejected


def heading_matches_term(heading: str, chinese_term: str) -> bool:
    """Check whether a section heading (e.g. '丫头 / 西丫头 / 你这丫头')
    matches the given Chinese term (e.g. '丫头')."""
    # Exact match
    if heading.strip() == chinese_term.strip():
        return True
    # The heading may contain multiple terms separated by /, ／, 、
    parts = re.split(r"\s*[/／、]\s*", heading)
    return chinese_term.strip() in parts


# ── Protection Rule: User-Rejected Renderings ────────────────────────────

def detect_user_rejected(
    proposal: ProposedRendering,
    rejected_map: Dict[str, List[str]],
) -> Optional[RiskSignal]:
    """Check if the proposed rendering matches a previously rejected alternative.

    ``rejected_map`` is a dict from ``parse_rejected_alternatives()``
    mapping Chinese-term headings to lists of rejected rendering strings.
    """
    rendering_lower = proposal.proposed_rendering.strip().lower()

    for heading, rejected_list in rejected_map.items():
        if not heading_matches_term(heading, proposal.chinese_term):
            continue
        for rejected in rejected_list:
            if rejected.lower() == rendering_lower:
                return RiskSignal(
                    signal_type="user_rejected",
                    description=(
                        f"Rendering {proposal.proposed_rendering!r} for "
                        f"{proposal.chinese_term!r} matches a previously "
                        f"rejected alternative ('{rejected}') under heading "
                        f"'{heading}'. User-rejected renderings must not be "
                        f"re-promoted to canonical status."
                    ),
                    severity="blocker",
                )

    return None


# ── Asset Classification ─────────────────────────────────────────────────

_CLASSIFICATION_MAP: Dict[RenderingCategory, str] = {
    RenderingCategory.ADDRESS_TERM: "titles_and_terms",
    RenderingCategory.KINSHIP_TERM: "titles_and_terms",
    RenderingCategory.TITLE_RANK: "titles_and_terms",
    RenderingCategory.GLOSSARY_TERM: "glossary",
    RenderingCategory.CHARACTER_NAME: "characters",
    RenderingCategory.STYLE_NOTE: "style_notes",
    RenderingCategory.UNKNOWN: "titles_and_terms",
}


def classify_target_asset(category: RenderingCategory) -> str:
    """Determine which project asset file a canonization should target."""
    return _CLASSIFICATION_MAP.get(category, "titles_and_terms")


# ── Main Gate ─────────────────────────────────────────────────────────────

_DEFAULT_DETECTORS = [
    detect_generic_address,
    detect_stiff_kinship,
    detect_meta_note_rendering,
    detect_unapproved_benchmark,
    detect_weak_evidence,
]


class CanonizationGate:
    """Gate that evaluates proposed renderings before they enter authoritative
    project assets.

    The gate runs a configurable set of protection-rule *detectors* against
    each proposal, classifies the result as SAFE / RISKY / REJECTED, and
    determines routing (canonical asset vs. unresolved_decisions).

    Example::

        gate = CanonizationGate()
        verdict = gate.classify(
            chinese_term="大小姐",
            proposed_rendering="Young Lady",
            category=RenderingCategory.ADDRESS_TERM,
            evidence_strength="strong",
            user_approved=True,
        )
        if verdict.risk == RenderingRisk.SAFE:
            promote_to_assets(verdict)
        elif verdict.risk == RenderingRisk.RISKY:
            write_to_unresolved(verdict)
        else:
            report_rejected(verdict)
    """

    def __init__(
        self,
        detectors: Optional[List] = None,
        rejected_map: Optional[Dict[str, List[str]]] = None,
    ):
        self._detectors = (
            list(detectors) if detectors is not None else list(_DEFAULT_DETECTORS)
        )
        self._rejected_map: Dict[str, List[str]] = rejected_map or {}
        self._rejected_loaded: bool = rejected_map is not None

    def _ensure_rejected_map(self) -> Dict[str, List[str]]:
        """Lazy-load rejected alternatives from project assets on disk."""
        if not self._rejected_loaded:
            try:
                from app.translate.project_context import load_asset

                for asset_name in ("unresolved_decisions", "titles_and_terms", "glossary"):
                    text = load_asset(asset_name)
                    if text:
                        parsed = parse_rejected_alternatives(text)
                        for heading, terms in parsed.items():
                            if heading not in self._rejected_map:
                                self._rejected_map[heading] = []
                            for t in terms:
                                if t not in self._rejected_map[heading]:
                                    self._rejected_map[heading].append(t)
            except Exception:
                pass  # If assets can't be loaded, we have no rejection data
            self._rejected_loaded = True
        return self._rejected_map

    def evaluate(self, proposal: ProposedRendering) -> CanonizationVerdict:
        """Evaluate a proposed rendering through the canonization gate.

        Runs all configured protection rules and evidence checks, then produces
        a verdict with routing decision.
        """
        signals: List[RiskSignal] = []
        target_asset = classify_target_asset(proposal.category)

        # 1. Run all protection rule detectors
        for detector in self._detectors:
            signal = detector(proposal)
            if signal:
                signals.append(signal)

        # 2. Run user-rejected check (needs the rejected map)
        rejected_map = self._ensure_rejected_map()
        rejected_signal = detect_user_rejected(proposal, rejected_map)
        if rejected_signal:
            signals.append(rejected_signal)

        # 3. Classify risk level
        blockers = [s for s in signals if s.severity == "blocker"]
        warnings = [s for s in signals if s.severity == "warning"]

        if blockers:
            risk = RenderingRisk.REJECTED
        elif warnings:
            risk = RenderingRisk.RISKY
        else:
            risk = RenderingRisk.SAFE

        # 4. Even without specific rule triggers, risky categories need
        #    strong evidence or explicit approval to be SAFE.
        if (
            risk == RenderingRisk.SAFE
            and proposal.category in _RISKY_CATEGORIES
            and proposal.evidence_strength != "strong"
            and proposal.user_approved is not True
        ):
            risk = RenderingRisk.RISKY
            route_to_unresolved = True
            signals.append(
                RiskSignal(
                    signal_type="category_risk",
                    description=(
                        f"{proposal.category.value} is a risky category and "
                        f"requires strong evidence or explicit approval "
                        f"before canonization, even when no specific rule "
                        f"was triggered."
                    ),
                    severity="warning",
                )
            )
        else:
            route_to_unresolved = risk in (RenderingRisk.RISKY,)

        # 5. Build verdict summary
        if risk == RenderingRisk.REJECTED:
            sig_descs = "; ".join(s.description for s in signals)
            verdict_summary = (
                f"REJECTED: {proposal.proposed_rendering!r} for "
                f"{proposal.chinese_term!r}. {sig_descs}"
            )
        elif risk == RenderingRisk.RISKY:
            sig_descs = "; ".join(s.description for s in signals)
            verdict_summary = (
                f"RISKY: {proposal.proposed_rendering!r} for "
                f"{proposal.chinese_term!r}. Route to unresolved_decisions. "
                f"{sig_descs}"
            )
        else:
            verdict_summary = (
                f"SAFE: {proposal.chinese_term!r} "
                f"→ {proposal.proposed_rendering!r}. "
                f"No risk signals detected. Ready for canonization."
            )

        return CanonizationVerdict(
            proposal=proposal,
            risk=risk,
            signals=signals,
            target_asset=target_asset,
            verdict_summary=verdict_summary,
            route_to_unresolved=route_to_unresolved,
        )

    def classify(
        self,
        chinese_term: str,
        proposed_rendering: str,
        category: RenderingCategory = RenderingCategory.UNKNOWN,
        source: str = "",
        user_approved: Optional[bool] = None,
        evidence_strength: str = "weak",
        notes: str = "",
    ) -> CanonizationVerdict:
        """Convenience wrapper: build a ProposedRendering and evaluate it."""
        proposal = ProposedRendering(
            chinese_term=chinese_term,
            proposed_rendering=proposed_rendering,
            category=category,
            source=source,
            user_approved=user_approved,
            evidence_strength=evidence_strength,
            notes=notes,
        )
        return self.evaluate(proposal)

    def safe_rendering(
        self,
        chinese_term: str,
        proposed_rendering: str,
        category: RenderingCategory = RenderingCategory.UNKNOWN,
        **kwargs,
    ) -> bool:
        """Quick check: is this rendering safe to canonize?"""
        verdict = self.classify(
            chinese_term=chinese_term,
            proposed_rendering=proposed_rendering,
            category=category,
            **kwargs,
        )
        return verdict.risk == RenderingRisk.SAFE
