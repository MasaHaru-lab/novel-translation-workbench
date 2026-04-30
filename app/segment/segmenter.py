import re
from dataclasses import dataclass
from typing import List, Optional


# Batch 4B: granularity-driven segment target sizes
GRANULARITY_TARGETS = {
    "standard": {"max_chars": 1200, "min_chars": 800},
    "finer": {"max_chars": 800, "min_chars": 500},
}


def resolve_granularity_targets(granularity: str) -> tuple:
    """Resolve (max_chars, min_chars) from a granularity name.

    Args:
        granularity: "standard" or "finer". Unknown values fall back to standard.

    Returns:
        (max_chars, min_chars) tuple.
    """
    targets = GRANULARITY_TARGETS.get(granularity, GRANULARITY_TARGETS["standard"])
    return targets["max_chars"], targets["min_chars"]


@dataclass
class Segment:
    """A segment of text for translation."""
    segment_id: int
    text: str
    prev_segment_text: Optional[str] = None
    next_segment_text: Optional[str] = None


def clip_context(text: Optional[str], max_chars: int = 200) -> Optional[str]:
    """Clip context text to a brief prefix for boundary coherence.

    Reduces next_segment_text from full adjacent segment length (800-1200
    chars) to ~max_chars, preferring to break at a sentence boundary.
    This prevents the model from treating large context blocks as
    translatable material (the known next_context spill pattern).

    Only `next_context` is clipped — `prev_context` is already-translated
    material and does not exhibit the same leakage.

    Returns None if text is None, original text if already within max_chars.
    """
    if text is None:
        return None
    if len(text) <= max_chars:
        return text
    # Find the LAST sentence/paragraph boundary within [50, max_chars)
    # so the clipped text is as long as possible while still ending cleanly.
    best_pos = -1
    for sep in ('\n', '。', '！', '？', '.', '!', '?'):
        pos = text.rfind(sep, 50, max_chars)
        if pos >= 50 and pos > best_pos:
            best_pos = pos
    if best_pos >= 50:
        return text[:best_pos + 1].strip()
    # Hard cut if no suitable boundary found.
    return text[:max_chars].rstrip() + "…"


def split_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs (by blank lines)."""
    # Split by \n\n and also handle single newline if preceded by punctuation? Simpler: re.split(r'\n\s*\n', text)
    paragraphs = re.split(r'\n\s*\n', text.strip())
    # Filter out empty strings
    return [p.strip() for p in paragraphs if p.strip()]


def create_segments(text: str, max_chars: int = 1200, min_chars: int = 800) -> List[Segment]:
    """Split text into segments of roughly max_chars characters, preserving paragraph boundaries.

    Each segment will contain one or more whole paragraphs. If a single paragraph exceeds max_chars,
    it will be split by sentence boundaries (fallback to character boundary).
    """
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        return []

    segments = []
    current_chunk: List[str] = []
    current_length = 0

    for i, para in enumerate(paragraphs):
        para_len = len(para)
        # If adding this paragraph would exceed max_chars and we already have something in current chunk,
        # finalize the current chunk.
        if current_length + para_len > max_chars and current_chunk:
            # Create segment from current_chunk
            segment_text = '\n\n'.join(current_chunk)
            segments.append(segment_text)
            # Start new chunk with this paragraph
            current_chunk = [para]
            current_length = para_len
        else:
            current_chunk.append(para)
            current_length += para_len

    # Add the last chunk
    if current_chunk:
        segment_text = '\n\n'.join(current_chunk)
        segments.append(segment_text)

    # Now create Segment objects with prev/next context
    segment_objects = []
    for idx, seg_text in enumerate(segments):
        prev = segments[idx - 1] if idx > 0 else None
        nxt = segments[idx + 1] if idx + 1 < len(segments) else None
        segment_objects.append(Segment(
            segment_id=idx + 1,
            text=seg_text,
            prev_segment_text=prev,
            next_segment_text=clip_context(nxt)
        ))

    return segment_objects


if __name__ == "__main__":
    # Simple test
    test_text = """第一段。

第二段。

第三段。"""
    segs = create_segments(test_text, max_chars=10, min_chars=5)
    for s in segs:
        print(f"ID: {s.segment_id}")
        print(f"Text: {s.text}")
        print(f"Prev: {s.prev_segment_text}")
        print(f"Next: {s.next_segment_text}")
        print()