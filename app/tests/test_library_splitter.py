"""Tests for app.library.splitter."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.library.splitter import split_by_chapter


def test_split_two_chapters_arabic_numerals():
    text = (
        "第1章 起点\n"
        "正文一。\n"
        "正文二。\n"
        "\n"
        "第2章 转折\n"
        "正文三。\n"
    )
    result = split_by_chapter(text)
    assert result.preamble is None
    assert result.chapter_count == 2

    first, second = result.chapters
    assert first.index == 1
    assert first.heading_line == "第1章 起点"
    assert first.body.startswith("第1章 起点")
    assert "正文二。" in first.body
    assert "第2章" not in first.body

    assert second.index == 2
    assert second.heading_line == "第2章 转折"
    assert second.body.startswith("第2章 转折")


def test_split_chinese_numeral_headings():
    text = (
        "第一章 序\n"
        "甲。\n"
        "第二十一章 中段\n"
        "乙。\n"
        "第三十一章 长姐\n"
        "丙。\n"
    )
    result = split_by_chapter(text)
    assert result.chapter_count == 3
    indexes = [c.index for c in result.chapters]
    headings = [c.heading_line for c in result.chapters]
    assert indexes == [1, 2, 3]
    assert headings == ["第一章 序", "第二十一章 中段", "第三十一章 长姐"]


def test_preamble_is_preserved_separately():
    text = (
        "书名：某某传\n"
        "作者：某某\n"
        "\n"
        "第一章 开篇\n"
        "正文。\n"
    )
    result = split_by_chapter(text)
    assert result.preamble is not None
    assert "书名" in result.preamble
    assert result.chapter_count == 1
    # Preamble must not bleed into the chapter body.
    assert "书名" not in result.chapters[0].body
    assert result.chapters[0].body.startswith("第一章 开篇")


def test_no_headings_returns_text_as_preamble():
    text = "纯散文，没有章节标题。\n"
    result = split_by_chapter(text)
    assert result.chapter_count == 0
    assert result.preamble == text


def test_empty_input():
    result = split_by_chapter("")
    assert result.chapter_count == 0
    assert result.preamble is None


def test_heading_only_matched_at_line_start():
    """A 第N章 token in the middle of a line must not split."""
    text = (
        "第一章 实战\n"
        "他翻开第二章看了看，又合上。\n"
        "第二章 续\n"
        "下一段。\n"
    )
    result = split_by_chapter(text)
    assert result.chapter_count == 2
    # The mid-line mention should stay inside chapter 1's body.
    assert "他翻开第二章看了看" in result.chapters[0].body
    # Chapter 2 must still start at its own heading.
    assert result.chapters[1].heading_line == "第二章 续"


def test_heading_word_boundary_excludes_false_positive():
    """``第二章程`` (章 inside a longer word) must not match as a heading."""
    text = (
        "第一章 序\n"
        "他报名了第二章程培训班。\n"
    )
    result = split_by_chapter(text)
    assert result.chapter_count == 1
    assert result.chapters[0].heading_line == "第一章 序"


def test_slug_strips_punctuation_and_truncates():
    text = "第一章 长姐形象是……坏！\n正文。\n"
    result = split_by_chapter(text)
    assert result.chapter_count == 1
    slug = result.chapters[0].slug
    # No raw punctuation that would be filename-hostile.
    for bad in ["……", "！", " ", "\t", "/"]:
        assert bad not in slug
    assert len(slug) <= 24
    assert slug  # Not empty.


def test_slug_falls_back_when_title_empty():
    text = "第一章\n仅正文。\n"
    result = split_by_chapter(text)
    assert result.chapter_count == 1
    assert result.chapters[0].slug == "chapter_1"


def test_real_data_concatenated_fixture():
    """Concatenate two real source chapters and verify the splitter
    recovers them as two chapters with the original headings intact."""
    repo_root = Path(__file__).resolve().parents[2]
    source_dir = repo_root / "data" / "source"
    samples = []
    for name in ("ch001.txt", "ch003.txt"):
        path = source_dir / name
        if path.exists():
            samples.append(path.read_text(encoding="utf-8"))
    if len(samples) < 2:
        # Real fixture not present in this checkout — skip rather than fail.
        import pytest
        pytest.skip("real ch001.txt / ch003.txt fixtures not present")

    combined = samples[0].rstrip() + "\n\n" + samples[1].lstrip()
    result = split_by_chapter(combined)
    assert result.chapter_count == 2
    # Each detected chapter must start with the original 第N章 heading.
    for chapter in result.chapters:
        assert chapter.body.startswith(chapter.heading_line)
        assert chapter.heading_line.startswith("第")
        assert "章" in chapter.heading_line
