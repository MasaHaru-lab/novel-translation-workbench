import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.segment.segmenter import create_segments, split_paragraphs, clip_context


def test_split_paragraphs():
    text = """第一段。

第二段。

第三段。"""
    paras = split_paragraphs(text)
    assert len(paras) == 3
    assert paras[0] == "第一段。"
    assert paras[1] == "第二段。"
    assert paras[2] == "第三段。"


def test_create_segments_small():
    text = """第一段。

第二段。

第三段。"""
    # Each paragraph is ~4 chars, set max_chars=5 to force separation
    segments = create_segments(text, max_chars=5, min_chars=1)
    assert len(segments) == 3
    assert segments[0].segment_id == 1
    assert segments[0].text == "第一段。"
    assert segments[0].prev_segment_text is None
    assert segments[0].next_segment_text == "第二段。"
    assert segments[1].prev_segment_text == "第一段。"
    assert segments[1].next_segment_text == "第三段。"
    assert segments[2].prev_segment_text == "第二段。"
    assert segments[2].next_segment_text is None


def test_clip_context_none():
    """None input returns None."""
    assert clip_context(None) is None


def test_clip_context_short():
    """Text under max_chars is returned unchanged."""
    text = "你好世界。"
    assert clip_context(text) == text


def test_clip_context_long_chinese():
    """Long Chinese text — first sentence boundary too short, falls to hard cut."""
    long = "第一句。" + "A" * 300 + "第二句。" + "B" * 300
    result = clip_context(long)
    assert result is not None
    assert len(result) < len(long)
    assert "第一句。" in result
    assert result.endswith("…")  # hard cut indicator


def test_clip_context_sentence_boundary():
    """Long text clipped at sentence boundary when it's within [min_chars, max_chars]."""
    # Build a string where the first '.' is at ~100 chars (well within the valid range)
    prefix = "A" * 95 + ". "
    assert 80 < len(prefix) < 200
    long = prefix + "B" * 300
    result = clip_context(long)
    assert result is not None
    assert len(result) < len(long)
    assert result.endswith(".")  # clipped at the period


def test_clip_context_paragraph_boundary():
    """Paragraph break is detected as a clipping boundary."""
    prefix = "A" * 60 + "\n\n"
    long = prefix + "B" * 300
    result = clip_context(long)
    assert result is not None
    assert result.endswith(prefix.strip())


def test_clip_context_hard_cut():
    """Text with no sentence boundary near the cutoff gets a hard cut."""
    # Use a long string of dashes (no sentence terminators except at very end)
    long = "a" * 300
    result = clip_context(long, max_chars=100)
    assert result is not None
    assert len(result) <= 100 + len("…")  # 100 + ellipsis
    assert result.endswith("…")


def test_create_segments_chunking():
    # Create paragraphs each of length 500 chars
    para = "a" * 500
    text = f"{para}\n\n{para}\n\n{para}"
    # max_chars 1000, min_chars 800, should chunk two paragraphs together
    segments = create_segments(text, max_chars=1000, min_chars=800)
    # Expect two segments: first two paragraphs together, third alone
    assert len(segments) == 2
    assert segments[0].text == f"{para}\n\n{para}"
    assert segments[1].text == para


if __name__ == "__main__":
    test_split_paragraphs()
    test_create_segments_small()
    test_create_segments_chunking()
    print("All tests passed.")