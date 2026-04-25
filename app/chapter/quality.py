"""Chapter-level quality validation gates.

Deterministic, post-hoc checks over a translated chapter result. These
gates do NOT auto-correct; they surface failure types so a "completed"
manifest cannot mask bad output.

The gates here are intentionally narrow and false-positive averse. They
target the failure types observed in real-run quality reviews:

  * ``cjk_residue`` — untranslated Chinese left in the aggregated output.
  * ``title_untranslated`` — the chapter heading is still Chinese.
  * ``segment_residue`` — per-segment polished output retains CJK
    characters above the segment-level threshold.
  * ``empty_segments`` — segment-level polished output is empty/whitespace.

A non-empty :class:`QualityReport` means the chapter run completed but
quality validation flagged at least one issue. Callers MUST treat such a
result as "not green".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.chapter.models import ChapterResult
from app.translate.translator import _CJK_RE, _count_cjk


# Chapter-level absolute threshold. Aggregated output is large, so a single
# stray name should not trip the gate; many residue spans should.
_CHAPTER_RESIDUE_THRESHOLD = 8

# Segment-level threshold mirrors the segment coverage gate.
_SEGMENT_RESIDUE_THRESHOLD = 5


@dataclass
class QualityIssue:
    """A single quality-gate failure."""

    code: str
    """Stable identifier for the failure type (e.g. ``cjk_residue``)."""

    severity: str
    """One of ``"error"`` (must-fix) or ``"warning"`` (review-and-confirm)."""

    message: str
    """Human-readable description of the failure."""

    segment_id: Optional[str] = None
    """Segment scope, if the issue applies to a single segment."""


@dataclass
class QualityReport:
    """Aggregate quality-gate result over a :class:`ChapterResult`."""

    issues: List[QualityIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when no error-severity issues were detected."""
        return not any(i.severity == "error" for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def codes(self) -> List[str]:
        return [i.code for i in self.issues]

    def to_summary(self) -> dict:
        """Compact, JSON-safe summary suitable for persistence in manifests."""
        return {
            "passed": self.passed,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "codes": self.codes(),
        }


def validate_chapter_output(result: ChapterResult) -> QualityReport:
    """Run deterministic quality gates against a completed chapter result.

    Inspects ``result.final_translation`` (consistency-corrected text when
    available, else aggregated) plus per-segment ``polished_translation``.

    The function never raises and never modifies ``result``. It produces a
    :class:`QualityReport` describing every failure it found.
    """
    issues: List[QualityIssue] = []

    final_text = result.final_translation or ""

    # ── Title preservation ─────────────────────────────────────────────
    # The orchestrator currently prepends the raw chapter title as a
    # markdown heading. If the title is still Chinese, the heading is too.
    title = (result.chapter_title or "").strip()
    if title and _count_cjk(title) >= 1:
        issues.append(
            QualityIssue(
                code="title_untranslated",
                severity="error",
                message=(
                    f"Chapter heading still in Chinese: {title!r}. "
                    "Aggregated output exposes an untranslated title."
                ),
            )
        )

    # ── Chapter-level CJK residue ──────────────────────────────────────
    cjk_count = _count_cjk(final_text)
    if cjk_count >= _CHAPTER_RESIDUE_THRESHOLD:
        sample = "".join(_CJK_RE.findall(final_text)[:8])
        issues.append(
            QualityIssue(
                code="cjk_residue",
                severity="error",
                message=(
                    f"Aggregated output retains {cjk_count} CJK characters "
                    f"(e.g. {sample!r})."
                ),
            )
        )

    # ── Per-segment checks ─────────────────────────────────────────────
    for seg_out in result.segment_results:
        polished = (seg_out.polished_translation or "").strip()
        seg_id = str(seg_out.segment_id)

        if not polished:
            issues.append(
                QualityIssue(
                    code="empty_segment",
                    severity="error",
                    message=(
                        f"Segment {seg_id} produced empty polished output."
                    ),
                    segment_id=seg_id,
                )
            )
            continue

        seg_cjk = _count_cjk(polished)
        if seg_cjk >= _SEGMENT_RESIDUE_THRESHOLD:
            sample = "".join(_CJK_RE.findall(polished)[:6])
            issues.append(
                QualityIssue(
                    code="segment_residue",
                    severity="error",
                    message=(
                        f"Segment {seg_id} polished output retains "
                        f"{seg_cjk} CJK characters (e.g. {sample!r})."
                    ),
                    segment_id=seg_id,
                )
            )

    return QualityReport(issues=issues)
