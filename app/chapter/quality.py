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
  * ``segment_overlap`` — adjacent segment outputs share text at their boundary.
  * ``short_output`` — segment polished output is suspiciously short (< 30 chars).
  * ``placeholder_leak`` — final output contains an unresolved bracketed
    placeholder like ``[Surname]`` or ``[Name]``. These come from project
    asset notation patterns that were not instantiated.
  * ``slash_list_leak`` — final output contains a slash-separated multi-
    candidate list like ``top-tier / ace / master / champion``. These come
    from glossary/style guidance that lists alternative renderings and must
    never appear inline in prose.
  * ``segment_truncation`` — non-final segment polished output ends without
    sentence-terminal punctuation, indicating its generation was cut off
    mid-thought (e.g. ending with ``"...septicemia. So"``).

A non-empty :class:`QualityReport` means the chapter run completed but
quality validation flagged at least one issue. Callers MUST treat such a
result as "not green".

This module is one of three that together enforce the chapter Markdown
output format contract documented on
``app.chapter.orchestrator.format_aggregated_translation``. The
``title_untranslated`` rule below enforces contract rule 2 (no CJK in
the first non-empty line of the final visible output); the consistency
audit's ``TITLE_FORMAT`` check enforces the related "raw source title
must not leak verbatim" rule. The two checks are aligned and must not
contradict each other — see that contract docstring before changing
either gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.chapter.consistency import _ends_sentence_cleanly
from app.chapter.models import ChapterResult
from app.translate.translator import _CJK_RE, _count_cjk


# Bracketed placeholder like ``[Surname]``, ``[Name]``, ``[Title]``. Requires
# at least one lowercase letter inside the brackets to discriminate genuine
# pattern placeholders from test-fixture or editorial markers like
# ``[DRAFT 1]`` or ``[POLISHED]``. Numeric markers such as ``[1]`` or
# ``[...]`` are also not flagged.
_PLACEHOLDER_LEAK_RE = re.compile(
    r"\[[A-Za-z][A-Za-z0-9 _-]*[a-z][A-Za-z0-9 _-]*\]"
)

# Three or more slash-separated alphanumeric/hyphenated tokens with single
# spaces around each ``/``. Matches glossary candidate-list contamination
# such as ``top-tier / ace / master / champion``. The minimum-three-token
# requirement avoids false positives on legitimate "this/that" and
# "either / or" punctuation.
_SLASH_LIST_LEAK_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9-]*"
    r"(?:\s/\s[A-Za-z][A-Za-z0-9-]*){2,}"
)


# Chapter-level absolute threshold. A 4-char idiom like 旁观者清 is clearly
# untranslated content and must be caught. Isolated 1-2 char remnants
# (e.g. 王爷 in a long passage) are below this bar.
_CHAPTER_RESIDUE_THRESHOLD = 4

# Segment-level threshold catches per-segment CJK leakage at the idiom
# level. A 3-char span (e.g. 禄/权/忌) in one segment triggers.
_SEGMENT_RESIDUE_THRESHOLD = 3

# A segment whose polished output has fewer than this many non-whitespace
# characters is suspiciously short — likely a failed/truncated translation.
_SHORT_OUTPUT_THRESHOLD = 30

# Minimum overlap length (characters) at a segment boundary to fire the
# overlap gate. Aligns with the consistency auditor's segment-boundary check.
_OVERLAP_MIN_LENGTH = 25


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
    seg_results = result.segment_results

    final_text = result.final_translation or ""

    # ── Title preservation ─────────────────────────────────────────────
    # The first non-empty line of the output should not be Chinese — the
    # title is part of the first segment's input and should be translated
    # by the segment-level translator like any other content. Skipping
    # leading blank lines keeps this gate aligned with the consistency
    # audit's TITLE_FORMAT check (see orchestrator output format
    # contract).
    first_non_empty = ""
    for line in (result.final_translation or "").splitlines():
        stripped = line.strip()
        if stripped:
            first_non_empty = stripped
            break
    if first_non_empty and _count_cjk(first_non_empty) >= 1:
        issues.append(
            QualityIssue(
                code="title_untranslated",
                severity="error",
                message=(
                    f"Output first line still in Chinese: {first_non_empty!r}. "
                    "The chapter heading was not translated."
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

    # ── Placeholder leak ───────────────────────────────────────────────
    # Bracketed pattern values like ``[Surname]`` come from project asset
    # notation and must never appear in final output.
    placeholder_match = _PLACEHOLDER_LEAK_RE.search(final_text)
    if placeholder_match:
        sample = placeholder_match.group(0)
        issues.append(
            QualityIssue(
                code="placeholder_leak",
                severity="error",
                message=(
                    f"Final output contains an unresolved bracketed "
                    f"placeholder ({sample!r}). This indicates a project "
                    f"asset pattern (e.g. 'Doctor [Surname]') leaked into "
                    f"the rendered chapter."
                ),
            )
        )

    # ── Slash-list candidate leak ──────────────────────────────────────
    # Multi-candidate guidance (``top-tier / ace / master / champion``)
    # must never appear inline. If detected, an unsafe substitution rule
    # ran somewhere upstream.
    slash_match = _SLASH_LIST_LEAK_RE.search(final_text)
    if slash_match:
        sample = slash_match.group(0)
        issues.append(
            QualityIssue(
                code="slash_list_leak",
                severity="error",
                message=(
                    f"Final output contains a slash-separated candidate "
                    f"list ({sample!r}). Glossary/style guidance must not "
                    f"be applied as literal substitution."
                ),
            )
        )

    # ── Per-segment checks ─────────────────────────────────────────────
    last_seg_index = len(seg_results) - 1
    for seg_index, seg_out in enumerate(seg_results):
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

        # ── Short output detection ────────────────────────────────────
        content_len = len(polished.replace(" ", ""))
        if content_len < _SHORT_OUTPUT_THRESHOLD:
            issues.append(
                QualityIssue(
                    code="short_output",
                    severity="error",
                    message=(
                        f"Segment {seg_id} polished output is suspiciously "
                        f"short ({content_len} non-space characters)."
                    ),
                    segment_id=seg_id,
                )
            )

        # ── Mid-thought truncation detection ──────────────────────────
        # A non-final segment whose polished output does not end with
        # sentence-terminal punctuation almost certainly had its
        # generation cut off (e.g. ``"...septicemia. So"``). Skip the
        # last segment because legitimate chapter endings vary.
        if seg_index != last_seg_index and not _ends_sentence_cleanly(polished):
            tail = polished[-60:].replace("\n", " ")
            issues.append(
                QualityIssue(
                    code="segment_truncation",
                    severity="error",
                    message=(
                        f"Segment {seg_id} appears truncated — its polished "
                        f"output does not end with sentence-terminal "
                        f"punctuation. Tail: {tail!r}"
                    ),
                    segment_id=seg_id,
                )
            )

    # ── Segment overlap detection ─────────────────────────────────────────
    # Checks if the start of the next segment's output appears as a substring
    # at the end of the current segment's output (substring, not position-aligned).
    for i in range(len(seg_results) - 1):
        curr = (seg_results[i].polished_translation or "").strip()
        nxt = (seg_results[i + 1].polished_translation or "").strip()
        if not curr or not nxt:
            continue
        # Probe window: last 80 chars of curr, first 80 chars of nxt.
        curr_tail = curr[-80:] if len(curr) >= 80 else curr
        nxt_head = nxt[:80] if len(nxt) >= 80 else nxt
        if len(nxt_head) < _OVERLAP_MIN_LENGTH:
            continue
        probe = nxt_head[:_OVERLAP_MIN_LENGTH]
        start_pos = curr_tail.find(probe)
        if start_pos < 0:
            continue
        # Extend the match as far as possible.
        match_len = _OVERLAP_MIN_LENGTH
        while (start_pos + match_len < len(curr_tail)
               and match_len < len(nxt_head)
               and curr_tail[start_pos + match_len] == nxt_head[match_len]):
            match_len += 1
        if match_len >= _OVERLAP_MIN_LENGTH:
            issues.append(
                QualityIssue(
                    code="segment_overlap",
                    severity="error",
                    message=(
                        f"Segments {seg_results[i].segment_id} and "
                        f"{seg_results[i + 1].segment_id} overlap by "
                        f"{match_len} characters at segment boundary."
                    ),
                )
            )

    return QualityReport(issues=issues)
