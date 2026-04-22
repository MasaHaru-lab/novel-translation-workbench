import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.segment.segmenter import create_segments, split_paragraphs


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