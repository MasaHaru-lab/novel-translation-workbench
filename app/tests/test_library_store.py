"""Tests for app.library.store."""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.library.models import Book, BookJob, BookJobStatus
from app.library.store import (
    book_dir,
    book_exists,
    chapter_path,
    chapters_dir,
    library_root,
    list_chapter_files,
    load_book,
    load_job,
    save_book,
    save_chapter_text,
    save_job,
    save_source_text,
    source_path,
)


def _make_book(book_id: str = "bk_testaaaaaaaaaa") -> Book:
    return Book(
        book_id=book_id,
        title="某某传",
        source_filename="某某传.txt",
        source_hash="a" * 64,
        detected_chapter_count=3,
        has_preamble=True,
    )


def _make_job(book_id: str = "bk_testaaaaaaaaaa") -> BookJob:
    return BookJob(
        book_id=book_id,
        detected_chapter_count=3,
        status=BookJobStatus.PENDING,
    )


def test_library_root_override_takes_precedence(tmp_path):
    assert library_root(tmp_path) == tmp_path


def test_library_root_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRARY_ROOT", str(tmp_path))
    assert library_root() == tmp_path


def test_book_roundtrip(tmp_path):
    book = _make_book()
    saved = save_book(book, root=tmp_path)
    assert saved.exists()
    loaded = load_book(book.book_id, root=tmp_path)
    assert loaded is not None
    assert loaded == book


def test_load_book_returns_none_when_missing(tmp_path):
    assert load_book("bk_missing", root=tmp_path) is None


def test_book_exists_false_until_saved(tmp_path):
    book = _make_book()
    assert not book_exists(book.book_id, root=tmp_path)
    save_book(book, root=tmp_path)
    assert book_exists(book.book_id, root=tmp_path)


def test_job_roundtrip_preserves_status_and_lists(tmp_path):
    job = _make_job()
    job.completed_chapter_indexes = [1, 2]
    job.failed_chapter_indexes = [3]
    job.status = BookJobStatus.PARTIAL
    save_job(job, root=tmp_path)
    loaded = load_job(job.book_id, root=tmp_path)
    assert loaded is not None
    assert loaded.status is BookJobStatus.PARTIAL
    assert loaded.completed_chapter_indexes == [1, 2]
    assert loaded.failed_chapter_indexes == [3]


def test_load_job_returns_none_when_missing(tmp_path):
    assert load_job("bk_missing", root=tmp_path) is None


def test_save_source_text_writes_verbatim(tmp_path):
    book_id = "bk_source01"
    text = "原文 verbatim\n第一章 序\n正文。\n"
    target = save_source_text(book_id, text, root=tmp_path)
    assert target == source_path(book_id, root=tmp_path)
    assert target.read_text(encoding="utf-8") == text


def test_save_chapter_text_uses_padded_index(tmp_path):
    book_id = "bk_chapter1"
    target = save_chapter_text(book_id, 7, "slug-x", "第7章 标题\n正文。", root=tmp_path)
    expected = chapter_path(book_id, 7, "slug-x", root=tmp_path)
    assert target == expected
    assert target.name.startswith("0007_")
    assert target.read_text(encoding="utf-8").startswith("第7章 标题")


def test_list_chapter_files_returns_sorted(tmp_path):
    book_id = "bk_listfiles"
    save_chapter_text(book_id, 2, "second", "x", root=tmp_path)
    save_chapter_text(book_id, 1, "first", "x", root=tmp_path)
    save_chapter_text(book_id, 11, "eleventh", "x", root=tmp_path)
    files = list_chapter_files(book_id, root=tmp_path)
    names = [f.name for f in files]
    assert names == ["0001_first.txt", "0002_second.txt", "0011_eleventh.txt"]


def test_book_workspace_layout(tmp_path):
    """Confirm the on-disk shape matches the documented layout."""
    book = _make_book("bk_layout01")
    job = _make_job("bk_layout01")
    save_book(book, root=tmp_path)
    save_job(job, root=tmp_path)
    save_source_text(book.book_id, "raw\n", root=tmp_path)
    save_chapter_text(book.book_id, 1, "alpha", "第1章 alpha\n正文。", root=tmp_path)

    root = book_dir(book.book_id, root=tmp_path)
    assert (root / "book.json").exists()
    assert (root / "job.json").exists()
    assert (root / "source.txt").exists()
    assert chapters_dir(book.book_id, root=tmp_path).is_dir()

    # JSON is human-readable UTF-8.
    book_data = json.loads((root / "book.json").read_text(encoding="utf-8"))
    assert book_data["title"] == "某某传"
