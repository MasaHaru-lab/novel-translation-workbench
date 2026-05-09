"""Chapter splitter for full-novel source text.

Pure functions only. Given the raw text of a novel, identify chapter
boundaries and return the preamble (everything before the first
chapter) plus a list of ``ChapterSplit`` records, each carrying its
heading line and body so the chapter file can be written verbatim.

The supported heading shape matches the existing data in
``data/source/``: ``第<numeral>章 <title>`` anchored at the start of
a line. Numerals may be Arabic digits or Chinese numerals. Other
heading conventions (``Chapter N``, ``第N回``, etc.) are intentionally
out of scope for the kernel — extend on real failure, not speculation.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional

# 第 + (digits OR Chinese-numeral run) + 章, anchored to line start.
# Allow optional leading whitespace so indented headings still match.
# A trailing space-or-end-of-line guard prevents matching tokens like
# ``第二章程`` (where 章 is part of a longer word).
_HEADING_RE = re.compile(
    r"^[ \t]*第[\d一二三四五六七八九十百千零〇两]+章(?=$|[\s 　：:、，,。.])",
    re.MULTILINE,
)

# Heading prefix used by ``_slug_for_heading`` to peel off the 第N章 token.
_HEADING_PREFIX_RE = re.compile(r"^[ \t]*第[\d一二三四五六七八九十百千零〇两]+章")


@dataclass(frozen=True)
class ChapterSplit:
    """One detected chapter, ready to be written to disk verbatim."""

    index: int  # 1-based position in the book
    heading_line: str  # The original heading line, stripped of trailing newline
    body: str  # Heading line + everything until the next heading
    slug: str  # Filename-safe short token derived from the heading


@dataclass(frozen=True)
class SplitResult:
    """Output of ``split_by_chapter``."""

    preamble: Optional[str]
    chapters: List[ChapterSplit]

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)


def _slug_for_heading(heading_line: str, fallback_index: int) -> str:
    """Build a short filename-safe slug from a chapter heading.

    Strips the ``第N章`` prefix, then keeps only Unicode letters,
    numbers, and ``_``. Anything else (whitespace, punctuation,
    full-width or CJK punctuation, control chars) collapses to a
    single ``_``. Falls back to ``chapter_<index>`` when nothing
    usable remains. Slugs are not required to be unique across
    chapters; the chapter index already provides uniqueness.
    """
    stripped = _HEADING_PREFIX_RE.sub("", heading_line, count=1).strip()
    out: List[str] = []
    last_underscore = False
    for ch in stripped:
        if ch == "_" or unicodedata.category(ch)[0] in {"L", "N"}:
            out.append(ch)
            last_underscore = False
        elif not last_underscore:
            out.append("_")
            last_underscore = True
    cleaned = "".join(out).strip("_")
    if not cleaned:
        return f"chapter_{fallback_index}"
    if len(cleaned) > 24:
        cleaned = cleaned[:24]
    return cleaned


def split_by_chapter(text: str) -> SplitResult:
    """Split full-novel text into preamble + chapters.

    Behavior:
    - Each chapter's ``body`` starts at its heading line and ends just
      before the next heading (or at end-of-text for the last chapter).
    - Trailing whitespace on each body is stripped, but the heading
      line is preserved verbatim so it remains the first non-empty
      line — matching what ``ChapterOrchestrator.extract_chapter_title``
      expects.
    - Text before the first heading is returned as ``preamble`` when
      it contains any non-whitespace content; otherwise ``preamble``
      is None.
    - If no headings are found, ``chapters`` is empty and the entire
      text becomes the preamble (when non-empty). Callers decide how
      to handle that case.
    """
    if not text:
        return SplitResult(preamble=None, chapters=[])

    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        preamble = text if text.strip() else None
        return SplitResult(preamble=preamble, chapters=[])

    first_start = matches[0].start()
    preamble_text = text[:first_start]
    preamble = preamble_text if preamble_text.strip() else None

    chapters: List[ChapterSplit] = []
    for i, match in enumerate(matches):
        body_start = match.start()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].rstrip()
        # Heading line is everything up to the first newline within the body.
        newline_pos = body.find("\n")
        heading_line = body if newline_pos < 0 else body[:newline_pos]
        heading_line = heading_line.strip()
        index = i + 1
        slug = _slug_for_heading(heading_line, index)
        chapters.append(
            ChapterSplit(
                index=index,
                heading_line=heading_line,
                body=body,
                slug=slug,
            )
        )

    return SplitResult(preamble=preamble, chapters=chapters)
