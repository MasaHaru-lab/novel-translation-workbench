"""Chapter-level consistency audit and limited correction.

Batch 3 capability: after segment-level translation and aggregation, this module
provides a chapter-level consistency pass that detects and optionally fixes the
most common "doesn't read like one unified chapter" problems.

Architecture:
  1. Build reference maps from project assets (characters, titles, glossary)
  2. Audit: scan the aggregated text for each known consistency issue category
  3. Correct: apply limited, conservative term-level replacements
  4. Report: structured output so callers know what was found and what was fixed

Design constraints (from Batch 3 requirements):
  - Must NOT do full-chapter rewriting
  - Must NOT do "translate the whole chapter again"
  - Must NOT do high-freedom prose polishing
  - Must NOT restyle or reshape prose
  - Corrections are limited to term unification only
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.translate.project_context import ASSET_NAMES, load_asset
from app.translate.translator import _count_cjk


def _contains_cjk(text: str) -> bool:
    """True if ``text`` contains at least one CJK character.

    Used by the chapter Markdown output format contract to decide whether
    a source ``chapter_title`` carries Chinese metadata that must not
    leak into the visible aggregated output.
    """
    return _count_cjk(text or "") > 0

logger = logging.getLogger(__name__)


# ── Issue Categories ──────────────────────────────────────────────────────


class ConsistencyIssueCategory(str, Enum):
    """Categories of consistency issues detectable at the chapter level."""

    NAME_VARIANT = "name_variant"
    """A character name appears in a non-canonical variant form."""

    TITLE_VARIANT = "title_variant"
    """A title or form of address appears in a non-canonical variant."""

    TERM_VARIANT = "term_variant"
    """A glossary term appears in a non-canonical variant."""

    TITLE_FORMAT = "title_format"
    """The raw source ``chapter_title`` (e.g. the Chinese first line of
    the source) leaked into the visible aggregated output, or the
    aggregated output is empty. Heading shape (``#`` level, exact wording)
    is intentionally NOT checked here — that is the segment-level
    translator's responsibility, per the chapter Markdown output format
    contract documented on
    ``app.chapter.orchestrator.format_aggregated_translation``."""

    SEGMENT_BOUNDARY = "segment_boundary"
    """An adjacent-segment boundary has an obvious inconsistency (e.g. repeated
    information, contradictory statement, jarring transition, or a segment
    that appears truncated mid-sentence)."""


# ── Data Models ───────────────────────────────────────────────────────────


@dataclass
class ConsistencyIssue:
    """A single detected consistency issue.

    Attributes:
        category: What kind of issue this is.
        segment_id: Which segment the issue was found in (empty for
            chapter-level issues like title_format).
        term: The canonical term that has a consistency problem.
        found: What was actually found in the text (the variant).
        expected: What the text should use instead.
        context_snippet: A short excerpt of surrounding text for context.
        auto_fixable: True if this issue can be automatically corrected via
            simple replacement.
        auto_fixed: True if this issue was corrected during the correction pass.
        detail: Optional human-readable explanation.
    """

    category: ConsistencyIssueCategory
    segment_id: str
    term: str
    found: str
    expected: str
    context_snippet: str = ""
    auto_fixable: bool = False
    auto_fixed: bool = False
    detail: str = ""


@dataclass
class ConsistencyAudit:
    """Full audit result for one chapter.

    Contains all detected issues and a summary by category.
    """

    issues: List[ConsistencyIssue] = field(default_factory=list)
    chapter_title: str = ""
    total_segments: int = 0

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def count_by_category(self) -> Dict[str, int]:
        """Return a dict mapping category names to issue counts."""
        counts: Dict[str, int] = {}
        for issue in self.issues:
            cat = issue.category.value
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def issues_by_category(self, category: ConsistencyIssueCategory) -> List[ConsistencyIssue]:
        """Return all issues matching a specific category."""
        return [i for i in self.issues if i.category == category]

    def get_summary(self) -> dict:
        """Return a structured summary suitable for reporting."""
        by_cat = self.count_by_category()
        return {
            "chapter_title": self.chapter_title,
            "total_segments": self.total_segments,
            "total_issues": self.issue_count,
            "by_category": by_cat,
            "auto_fixable": sum(1 for i in self.issues if i.auto_fixable),
            "auto_fixed": sum(1 for i in self.issues if i.auto_fixed),
        }


@dataclass
class CorrectionAction:
    """A single correction applied during the correction pass."""

    category: ConsistencyIssueCategory
    segment_id: str
    old_text: str
    new_text: str
    detail: str = ""


@dataclass
class CorrectionSummary:
    """Summary of all corrections applied during the correction pass."""

    actions: List[CorrectionAction] = field(default_factory=list)
    total_replaced: int = 0

    @property
    def has_corrections(self) -> bool:
        return len(self.actions) > 0

    @property
    def correction_count(self) -> int:
        return len(self.actions)

    def get_summary(self) -> dict:
        by_cat: Dict[str, int] = {}
        for action in self.actions:
            cat = action.category.value
            by_cat[cat] = by_cat.get(cat, 0) + 1
        return {
            "total_corrections": self.correction_count,
            "total_replacements": self.total_replaced,
            "by_category": by_cat,
        }


# ── Reference Builder: parse project assets into structured maps ──────────


@dataclass
class CharacterRef:
    """Canonical character name and known variant patterns."""

    canonical: str
    """The approved English rendering."""

    variants: List[str] = field(default_factory=list)
    """Common variant forms that should be corrected to canonical."""


@dataclass
class TitleRef:
    """Canonical title/address rendering."""

    canonical: str
    """The approved English rendering."""

    variants: List[str] = field(default_factory=list)
    """Common variant forms."""


@dataclass
class GlossaryRef:
    """Canonical glossary term rendering."""

    canonical: str
    """The approved English rendering."""

    variants: List[str] = field(default_factory=list)
    """Common variant forms."""


@dataclass
class ConsistencyReference:
    """All reference data extracted from project assets for consistency checking."""

    characters: List[CharacterRef] = field(default_factory=list)
    titles: List[TitleRef] = field(default_factory=list)
    glossary_terms: List[GlossaryRef] = field(default_factory=list)


# Pattern: "### {name}" followed by "- English rendering: {rendering}"
_ENGLISH_RENDERING_RE = re.compile(
    r"English rendering\s*:\s*(.+?)$", re.IGNORECASE | re.MULTILINE
)

# Pattern for Notes lines in character/title entries
_NOTES_LINE_RE = re.compile(r"- Notes\s*:\s*(.+)", re.IGNORECASE)


def _parse_rendering_value(line: str) -> Optional[str]:
    """Extract the rendering value from an 'English rendering: VALUE' line."""
    m = _ENGLISH_RENDERING_RE.search(line)
    if m:
        return m.group(1).strip()
    return None


def _extract_variants_from_notes(notes_text: str) -> List[str]:
    """Parse variant hints from a Notes line.

    Look for patterns like:
      'Do not drift to "Qi Liuxi" or other variants.'
      'Do not alternate casually with Madam Wang'
      'Do not map this mechanically onto...'

    Extracts the quoted variant names.
    """
    variants = []
    # Match quoted phrases that look like name variants
    for m in re.finditer(r'"([^"]+)"', notes_text):
        candidate = m.group(1).strip()
        if candidate and len(candidate) > 1:
            variants.append(candidate)
    return variants


def _parse_character_refs(asset_text: str) -> List[CharacterRef]:
    """Parse characters.md into structured CharacterRef objects."""
    refs = []
    # Split by "### " headings
    sections = re.split(r"^### ", asset_text, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().splitlines()
        name_heading = lines[0].strip() if lines else ""
        full_text = "\n".join(lines)

        rendering = _parse_rendering_value(full_text)
        if not rendering:
            continue

        notes_line = _NOTES_LINE_RE.search(full_text)
        variants = _extract_variants_from_notes(
            notes_line.group(1) if notes_line else ""
        )

        refs.append(CharacterRef(canonical=rendering, variants=variants))
    return refs


def _parse_title_refs(asset_text: str) -> List[TitleRef]:
    """Parse titles_and_terms.md into structured TitleRef objects."""
    refs = []
    sections = re.split(r"^### ", asset_text, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        lines = section.strip().splitlines()
        # First line is the Chinese term, skip it
        full_text = "\n".join(lines)

        rendering = _parse_rendering_value(full_text)
        if not rendering:
            continue

        notes_line = _NOTES_LINE_RE.search(full_text)
        variants = _extract_variants_from_notes(
            notes_line.group(1) if notes_line else ""
        )

        refs.append(TitleRef(canonical=rendering, variants=variants))
    return refs


def _parse_glossary_refs(asset_text: str) -> List[GlossaryRef]:
    """Parse glossary.md into structured GlossaryRef objects."""
    refs = []
    sections = re.split(r"^### ", asset_text, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        full_text = "\n".join(section.strip().splitlines())

        rendering = _parse_rendering_value(full_text)
        if not rendering:
            continue

        notes_line = _NOTES_LINE_RE.search(full_text)
        variants = _extract_variants_from_notes(
            notes_line.group(1) if notes_line else ""
        )

        refs.append(GlossaryRef(canonical=rendering, variants=variants))
    return refs


def build_consistency_reference() -> ConsistencyReference:
    """Load project assets and build a structured consistency reference.

    Returns a ConsistencyReference containing all canonical renderings and
    known variants extracted from the project assets. If an asset file is
    missing, its section is simply empty — no crash.
    """
    chars_text = load_asset("characters") or ""
    titles_text = load_asset("titles_and_terms") or ""
    glossary_text = load_asset("glossary") or ""

    return ConsistencyReference(
        characters=_parse_character_refs(chars_text),
        titles=_parse_title_refs(titles_text),
        glossary_terms=_parse_glossary_refs(glossary_text),
    )


# ── Auditor: detect consistency issues ────────────────────────────────────


def _find_segment_boundaries(
    segment_texts: List[Tuple[str, str]],
) -> List[Tuple[int, str, str]]:
    """Build segment boundary descriptors.

    Returns list of (segment_id_int, last_chars_of_segment,
    first_chars_of_next_segment). Uses a sliding window to detect
    repeated text at the boundary regardless of exact alignment.
    """
    boundaries = []
    for i in range(len(segment_texts) - 1):
        seg_id, text = segment_texts[i]
        _, next_text = segment_texts[i + 1]
        # Use the last ~300 chars and first ~300 chars for overlap detection
        tail = text.strip()[-300:] if len(text.strip()) > 300 else text.strip()
        head = next_text.strip()[:300] if len(next_text.strip()) > 300 else next_text.strip()
        boundaries.append((int(seg_id), tail, head))
    return boundaries


# ── Truncation Detection ──────────────────────────────────────────────────────────

_SENTENCE_END_CHARS: set = {
    ".", "!", "?", "…", "—",
    "」", "』", "”", "’",
    ")", "}", "]",
    "。", "！", "？",
}

_CLOSING_PUNCTUATION: set = {
    '"', "'", "“", "‘",
    "」", "』",
    ")", "}", "]",
}


def _ends_sentence_cleanly(text: str) -> bool:
    """Check whether ``text`` ends with sentence-ending punctuation.

    Returns True when the last non-whitespace character is a recognized
    sentence-ending character (period, question mark, exclamation, ellipsis,
    closing bracket after sentence punctuation, etc.). Empty or whitespace-only
    strings return False.

    This is deliberately conservative: a bare closing quote or bracket
    (with no prior sentence-ending punctuation) still counts as a clean
    end, since it likely closes dialogue or a parenthetical.
    """
    stripped = (text or "").strip()
    if not stripped:
        return False
    last = stripped[-1]
    if last in _SENTENCE_END_CHARS:
        return True
    # Closing punctuation alone still counts as clean (dialogue end, etc).
    if last in _CLOSING_PUNCTUATION:
        return True
    return False


class ChapterConsistencyAuditor:
    """Audits a fully aggregated chapter for consistency issues.

    The auditor operates on the aggregated text and per-segment results,
    using project asset reference data to detect drift.

    Batch 4B: accepts an optional ``intensity`` parameter.
    - "standard" (default): existing behavior — only explicit known variants
      are flagged and auto-fixable.
    - "enhanced": also derives partial-word variants from multi-word names
      and marks them as auto-fixable, and checks for broader variant patterns.
    """

    def __init__(
        self,
        reference: Optional[ConsistencyReference] = None,
        intensity: str = "standard",
    ):
        self.reference = reference or build_consistency_reference()
        self.intensity = intensity

    def audit(
        self,
        aggregated_text: str,
        chapter_title: str,
        segment_texts: List[Tuple[str, str]],
    ) -> ConsistencyAudit:
        """Run a full consistency audit on the chapter.

        Args:
            aggregated_text: The full aggregated chapter text (markdown).
            chapter_title: The canonical chapter title from the source.
            segment_texts: List of (segment_id, polished_text) pairs, in order.

        Returns:
            ConsistencyAudit with all detected issues.
        """
        audit = ConsistencyAudit(
            chapter_title=chapter_title,
            total_segments=len(segment_texts),
        )

        # 1. Title format check
        title_issues = self._check_title_format(aggregated_text, chapter_title)
        audit.issues.extend(title_issues)

        # 2. Character name consistency
        name_issues = self._check_character_names(segment_texts)
        audit.issues.extend(name_issues)

        # 3. Title / address consistency
        title_term_issues = self._check_titles(segment_texts)
        audit.issues.extend(title_term_issues)

        # 4. Glossary term consistency
        glossary_issues = self._check_glossary_terms(segment_texts)
        audit.issues.extend(glossary_issues)

        # 5. Segment boundary check
        boundary_issues = self._check_segment_boundaries(segment_texts)
        audit.issues.extend(boundary_issues)

        # 6. Enhanced mode: broader partial-name detection
        if self.intensity == "enhanced":
            enhanced_name_issues = self._check_enhanced_name_variants(segment_texts)
            audit.issues.extend(enhanced_name_issues)

        return audit

    def _check_title_format(
        self, aggregated_text: str, chapter_title: str
    ) -> List[ConsistencyIssue]:
        """Check the chapter Markdown output format contract.

        Per the contract documented on
        ``app.chapter.orchestrator.format_aggregated_translation``:

        * The aggregated text must not be empty.
        * The raw source ``chapter_title`` (which for a Chinese source is
          a Chinese string like ``"第一章"``) must not surface as the
          first non-empty line, with or without a leading ``# ``.

        Heading shape, level, and wording are NOT checked here; the
        segment-level translator owns that. Issues raised by this check
        are deliberately ``auto_fixable=False`` — re-introducing the raw
        source title literal into the visible output would corrupt the
        chapter, so any fix requires re-translation rather than
        mechanical replacement.
        """
        issues = []

        if not aggregated_text:
            issues.append(ConsistencyIssue(
                category=ConsistencyIssueCategory.TITLE_FORMAT,
                segment_id="",
                term=chapter_title,
                found="(empty)",
                expected="non-empty translated chapter Markdown",
                detail="Aggregated chapter output is empty.",
                auto_fixable=False,
            ))
            return issues

        first_non_empty = ""
        for line in aggregated_text.splitlines():
            stripped = line.strip()
            if stripped:
                first_non_empty = stripped
                break

        if not first_non_empty:
            issues.append(ConsistencyIssue(
                category=ConsistencyIssueCategory.TITLE_FORMAT,
                segment_id="",
                term=chapter_title,
                found="(empty)",
                expected="non-empty translated chapter Markdown",
                detail="Aggregated chapter output has no non-empty lines.",
                auto_fixable=False,
            ))
            return issues

        # Only treat a verbatim title match as a "leak" when the source
        # chapter_title contains CJK characters. For projects whose source
        # title already happens to be English (or for English-only test
        # fixtures), a matching first line is the desired outcome, not a
        # contract violation.
        title_stripped = (chapter_title or "").strip()
        if title_stripped and _contains_cjk(title_stripped):
            normalized = first_non_empty.lstrip("#").strip()
            if normalized == title_stripped:
                issues.append(ConsistencyIssue(
                    category=ConsistencyIssueCategory.TITLE_FORMAT,
                    segment_id="",
                    term=chapter_title,
                    found=first_non_empty,
                    expected="translated chapter heading (English first line)",
                    detail=(
                        f"Raw source chapter_title {chapter_title!r} appears "
                        f"verbatim as the first line of the aggregated output. "
                        f"This violates the chapter Markdown output format "
                        f"contract: segment 1 must produce a translated heading."
                    ),
                    auto_fixable=False,
                ))

        return issues

    def _check_character_names(
        self, segment_texts: List[Tuple[str, str]]
    ) -> List[ConsistencyIssue]:
        """Check each segment for character name variants."""
        issues = []

        for char_ref in self.reference.characters:
            canonical = char_ref.canonical
            # Build variants to check:
            # 1. Explicit known variants from the asset file (e.g. "Qi Liuxi")
            # 2. Lowercase version of canonical (e.g. "qin liuxi")
            # We do NOT auto-derive partial words from multi-word names here
            # because they produce too many false positives (e.g. "Qin" is a
            # surname shared by many characters).
            variants_to_check: List[Tuple[str, bool]] = [
                (v, True) for v in char_ref.variants
            ]
            if canonical.lower() != canonical:
                variants_to_check.append((canonical.lower(), True))

            for seg_id, text in segment_texts:
                canonical_present = canonical.lower() in text.lower()
                for variant, is_explicit_variant in variants_to_check:
                    # Skip if variant is literally the same string as canonical
                    # (case-sensitive). Case-only differences ARE legitimate
                    # variants to check.
                    if variant == canonical:
                        continue
                    if variant.lower() in text.lower():
                        # Get the actual text at the match position.
                        idx = text.lower().index(variant.lower())
                        actual_found = text[idx:idx + len(variant)]

                        # If the actual text IS the canonical form (exact match),
                        # then this isn't really a variant. Case differences
                        # ARE variants (e.g. "young lady" vs "Young Lady").
                        if actual_found == canonical:
                            continue

                        # Found a variant — check if canonical is also present.
                        # If canonical is also present, the variant might be
                        # a legitimate partial reference (e.g. "Liuxi" after
                        # "Qin Liuxi" was already established). We still flag
                        # it if the variant is an explicit known variant.
                        if canonical_present and not is_explicit_variant:
                            continue

                        start = max(0, idx - 40)
                        end = min(len(text), idx + len(variant) + 40)
                        context = text[start:end].strip()

                        issues.append(ConsistencyIssue(
                            category=ConsistencyIssueCategory.NAME_VARIANT,
                            segment_id=seg_id,
                            term=canonical,
                            found=actual_found,
                            expected=canonical,
                            context_snippet=context,
                            auto_fixable=is_explicit_variant,
                            detail=(
                                f"Character {canonical!r} appears as "
                                f"{actual_found!r} in segment {seg_id}."
                                if is_explicit_variant
                                else f"Possible partial reference to {canonical!r} in segment {seg_id}."
                            ),
                        ))

        return issues

    def _check_titles(
        self, segment_texts: List[Tuple[str, str]]
    ) -> List[ConsistencyIssue]:
        """Check each segment for title/address variants."""
        issues = []

        for title_ref in self.reference.titles:
            canonical = title_ref.canonical
            variants_to_check: List[Tuple[str, bool]] = [
                (v, True) for v in title_ref.variants
            ]
            # Lowercase version (e.g. "young lady" vs "Young Lady")
            if canonical.lower() != canonical:
                variants_to_check.append((canonical.lower(), True))

            for seg_id, text in segment_texts:
                canonical_present = canonical.lower() in text.lower()
                for variant, is_explicit in variants_to_check:
                    # Skip only if variant is literally the same string as canonical.
                    # Case differences are legitimate variants.
                    if variant == canonical:
                        continue
                    if variant.lower() in text.lower():
                        # Get actual text at match position.
                        idx = text.lower().index(variant.lower())
                        actual_found = text[idx:idx + len(variant)]

                        # Skip if the actual text IS the canonical form (exact match).
                        # Case differences ARE variants (e.g. "young lady" vs "Young Lady").
                        if actual_found == canonical:
                            continue

                        if canonical_present and not is_explicit:
                            continue

                        start = max(0, idx - 40)
                        end = min(len(text), idx + len(variant) + 40)

                        issues.append(ConsistencyIssue(
                            category=ConsistencyIssueCategory.TITLE_VARIANT,
                            segment_id=seg_id,
                            term=canonical,
                            found=actual_found,
                            expected=canonical,
                            context_snippet=text[start:end].strip(),
                            auto_fixable=is_explicit,
                            detail=(
                                f"Title {canonical!r} appears as "
                                f"{actual_found!r} in segment {seg_id}."
                            ),
                        ))

        return issues

    def _check_glossary_terms(
        self, segment_texts: List[Tuple[str, str]]
    ) -> List[ConsistencyIssue]:
        """Check each segment for glossary term variants."""
        issues = []

        for term_ref in self.reference.glossary_terms:
            canonical = term_ref.canonical
            variants_to_check: List[Tuple[str, bool]] = [
                (v, True) for v in term_ref.variants
            ]
            if canonical.lower() != canonical:
                variants_to_check.append((canonical.lower(), True))

            for seg_id, text in segment_texts:
                for variant, is_explicit in variants_to_check:
                    # Skip only if variant is literally the same string as canonical.
                    if variant == canonical:
                        continue
                    if variant.lower() in text.lower():
                        # Get actual text at match position.
                        idx = text.lower().index(variant.lower())
                        actual_found = text[idx:idx + len(variant)]

                        # Skip if the actual text IS the canonical form (exact match).
                        if actual_found == canonical:
                            continue

                        start = max(0, idx - 40)
                        end = min(len(text), idx + len(variant) + 40)

                        issues.append(ConsistencyIssue(
                            category=ConsistencyIssueCategory.TERM_VARIANT,
                            segment_id=seg_id,
                            term=canonical,
                            found=actual_found,
                            expected=canonical,
                            context_snippet=text[start:end].strip(),
                            auto_fixable=is_explicit,
                            detail=(
                                f"Glossary term {canonical!r} appears as "
                                f"{actual_found!r} in segment {seg_id}."
                            ),
                        ))

        return issues

    def _check_segment_boundaries(
        self, segment_texts: List[Tuple[str, str]]
    ) -> List[ConsistencyIssue]:
        """Check adjacent segment boundaries for obvious inconsistencies.

        Checks:
        - Repeated identical phrases at segment boundaries (overlap)
        - Per-segment mid-sentence truncation (segment ends mid-sentence)
        """
        issues = []
        boundaries = _find_segment_boundaries(segment_texts)

        for seg_id, tail, head in boundaries:
            # ── Overlap detection ────────────────────────────────────────
            # Check if the start of the next segment appears in the tail of
            # the current segment (suggesting repeated content across the
            # segment boundary). Use a minimum match length of 25 chars.
            if len(tail) > 30 and len(head) > 30:
                # Try increasingly long prefixes of head
                overlap_found = None
                for length in range(25, min(100, len(head))):
                    prefix = head[:length]
                    if prefix.lower() in tail.lower():
                        overlap_found = prefix
                    else:
                        break  # once we miss, longer won't match

                if overlap_found and len(overlap_found) >= 25:
                    issues.append(ConsistencyIssue(
                        category=ConsistencyIssueCategory.SEGMENT_BOUNDARY,
                        segment_id=str(seg_id),
                        term="",
                        found=overlap_found,
                        expected="",
                        context_snippet=f"...{tail[-100:]} | {head[:100]}...",
                        auto_fixable=False,
                        detail=(
                            f"Possible repeated content at boundary between "
                            f"segment {seg_id} and {seg_id + 1}: "
                            f"{len(overlap_found)}-char overlap detected."
                        ),
                    ))

        # ── Truncation detection ─────────────────────────────────────────
        # Check each segment (except the last, which may end a chapter) for
        # mid-sentence truncation. A segment that ends without sentence-ending
        # punctuation likely had its output cut off during generation.
        for seg_id, text in segment_texts:
            if not _ends_sentence_cleanly(text):
                lines = (text or "").strip().splitlines()
                last_lines = lines[-3:] if len(lines) >= 3 else lines
                snippet = "\n".join(last_lines) if last_lines else ""
                # Trim the snippet to a reasonable preview length.
                if len(snippet) > 120:
                    snippet = snippet[-120:]
                issues.append(ConsistencyIssue(
                    category=ConsistencyIssueCategory.SEGMENT_BOUNDARY,
                    segment_id=str(seg_id),
                    term="", found="", expected="",
                    context_snippet=snippet,
                    auto_fixable=False,
                    detail=(
                        f"Segment {seg_id} may be truncated — output does not "
                        f"end with sentence-ending punctuation. Last characters: "
                        f"{repr(snippet[-40:]) if snippet else '(empty)'}"
                    ),
                ))

        return issues

    def _check_enhanced_name_variants(
        self, segment_texts: List[Tuple[str, str]]
    ) -> List[ConsistencyIssue]:
        """Enhanced name variant detection for ENHANCED intensity mode.

        Detects partial-name drift (e.g. "Liuxi" appearing without "Qin Liuxi"
        in a segment). Under this book's name-reference policy, drifting from
        full canonical name to last-word-only is NOT treated as a valid English
        abbreviation — it is flagged as a high-priority audit issue.

        These issues are NOT auto-fixed because:
        - The policy is a book-level rule, not a universal NLP heuristic.
        - The correct resolution depends on context (which segment, whether the
          full name was recently established, whether a nickname exception is
          declared in project assets).
        - Auto-replacing "Liuxi" → "Qin Liuxi" would be mechanical and could
          produce unnatural prose if the partial reference was intentional.

        Future enhancement: if a project asset declares an explicit nickname /
        special-address exception for a character, that character's partial
        references will be excluded from this check.
        """
        issues = []

        # Build set of characters that have an explicit nickname exception
        # in their project asset entry. Currently not populated; placeholder
        # for future book-level rule support.
        exempt_partials: set = set()

        for char_ref in self.reference.characters:
            canonical = char_ref.canonical
            words = canonical.split()
            if len(words) < 2:
                continue
            partial = words[-1]
            if len(partial) < 3:
                continue
            if partial in char_ref.variants:
                continue
            if partial.lower() in ("the", "of", "de", "la", "von"):
                continue
            if partial in exempt_partials:
                continue

            for seg_id, text in segment_texts:
                if partial.lower() in text.lower():
                    canonical_present = canonical.lower() in text.lower()
                    if canonical_present:
                        continue
                    idx = text.lower().index(partial.lower())
                    start = max(0, idx - 40)
                    end = min(len(text), idx + len(partial) + 40)
                    context = text[start:end].strip()

                    issues.append(ConsistencyIssue(
                        category=ConsistencyIssueCategory.NAME_VARIANT,
                        segment_id=seg_id,
                        term=canonical,
                        found=partial,
                        expected=canonical,
                        context_snippet=context,
                        auto_fixable=False,  # book-level rule, not universal heuristic
                        detail=(
                            f"Partial name reference '{partial}' found in segment {seg_id} "
                            f"without full canonical '{canonical}'. "
                            f"Under this book's name-reference policy, surname-drop drift "
                            f"(full name → last-word-only) is not allowed by default. "
                            f"Review manually to determine if this is an intentional "
                            f"abbreviation or a consistency drift."
                        ),
                    ))

        return issues


# ── Corrector: apply limited, conservative corrections ────────────────────


class ChapterCorrector:
    """Apply limited, conservative corrections based on audit findings.

    Correction rules:
      1. Only fix explicit known variants (auto_fixable=True).
      2. Only replace variant text with canonical text (simple string replacement).
      3. No prose rewriting, no sentence restructuring.
      4. Each replacement is logged as a CorrectionAction.
      5. Never touch segments that have no auto-fixable issues.
    """

    def __init__(self, reference: Optional[ConsistencyReference] = None):
        self.reference = reference or build_consistency_reference()

    def correct(
        self,
        aggregated_text: str,
        audit: ConsistencyAudit,
    ) -> Tuple[str, CorrectionSummary]:
        """Apply corrections to the aggregated text based on audit findings.

        Args:
            aggregated_text: The full aggregated chapter text to correct.
            audit: The consistency audit whose auto-fixable issues guide corrections.

        Returns:
            (corrected_text, correction_summary)
        """
        summary = CorrectionSummary()
        corrected = aggregated_text

        # Collect all auto-fixable issues, group by replacement mapping
        # to avoid redundant work.
        replacements: Dict[str, str] = {}
        for issue in audit.issues:
            if not issue.auto_fixable:
                continue
            if issue.found and issue.expected:
                replacements[issue.found] = issue.expected

        # Apply replacements in order of decreasing length (longer matches first)
        # to avoid partial replacement issues (e.g. "Old Madam" before "Madam").
        for old_text in sorted(replacements.keys(), key=len, reverse=True):
            new_text = replacements[old_text]
            if old_text == new_text:
                continue
            # Count occurrences
            count = corrected.count(old_text)
            if count > 0:
                corrected = corrected.replace(old_text, new_text)
                summary.actions.append(CorrectionAction(
                    category=ConsistencyIssueCategory.NAME_VARIANT,
                    segment_id="",
                    old_text=old_text,
                    new_text=new_text,
                    detail=f"Replaced {old_text!r} with {new_text!r} ({count} occurrence(s))",
                ))
                summary.total_replaced += count

        # Update the audit issues to mark which ones were fixed
        if summary.has_corrections:
            # Build set of what was corrected
            corrected_map: Dict[str, str] = {}
            for action in summary.actions:
                corrected_map[action.old_text] = action.new_text

            for issue in audit.issues:
                if issue.found in corrected_map:
                    issue.auto_fixed = True

        return corrected, summary


# ── Convenience: run audit + correct in one call ──────────────────────────


def run_consistency_pass(
    aggregated_text: str,
    chapter_title: str,
    segment_texts: List[Tuple[str, str]],
    reference: Optional[ConsistencyReference] = None,
    intensity: str = "standard",
) -> Tuple[str, ConsistencyAudit, CorrectionSummary]:
    """Run audit + limited correction on an aggregated chapter.

    This is the primary entry point for Batch 3's consistency pass.

    Batch 4B: accepts ``intensity`` parameter.
    - "standard" (default): existing behavior.
    - "enhanced": also detects partial-name drift (high-priority audit issues,
      not auto-fixed).

    Args:
        aggregated_text: The full aggregated chapter text.
        chapter_title: The canonical chapter title from source.
        segment_texts: List of (segment_id, polished_text) pairs.
        reference: Optional pre-built consistency reference (will build from
            assets if not provided).
        intensity: "standard" or "enhanced".

    Returns:
        (corrected_text, audit, correction_summary)
    """
    if reference is None:
        reference = build_consistency_reference()

    auditor = ChapterConsistencyAuditor(reference, intensity=intensity)
    audit = auditor.audit(aggregated_text, chapter_title, segment_texts)

    corrector = ChapterCorrector(reference)
    corrected_text, correction_summary = corrector.correct(aggregated_text, audit)

    return corrected_text, audit, correction_summary
