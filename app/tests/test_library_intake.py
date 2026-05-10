"""Tests for app.library.intake."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.library.intake import BookImportError, import_novel
from app.library.models import BookJobStatus
from app.library.store import (
    book_dir,
    chapters_dir,
    list_chapter_files,
    load_book,
    load_job,
    source_path,
)


THREE_CHAPTER_TEXT = (
    "第一章 序\n"
    "甲段。\n"
    "\n"
    "第二章 中\n"
    "乙段。\n"
    "\n"
    "第三章 末\n"
    "丙段。\n"
)


def test_import_writes_book_workspace(tmp_path):
    book = import_novel(
        THREE_CHAPTER_TEXT,
        original_filename="某某传.txt",
        library_root=tmp_path,
    )
    assert book.book_id.startswith("bk_")
    assert book.detected_chapter_count == 3
    assert book.title == "某某传"
    assert book.source_filename == "某某传.txt"
    assert book.has_preamble is False

    workspace = book_dir(book.book_id, root=tmp_path)
    assert workspace.is_dir()
    assert (workspace / "book.json").exists()
    assert (workspace / "job.json").exists()
    assert (workspace / "source.txt").exists()
    assert chapters_dir(book.book_id, root=tmp_path).is_dir()


def test_import_creates_one_file_per_chapter_with_heading_first(tmp_path):
    book = import_novel(
        THREE_CHAPTER_TEXT,
        original_filename="x.txt",
        library_root=tmp_path,
    )
    files = list_chapter_files(book.book_id, root=tmp_path)
    assert len(files) == 3
    headings = [f.read_text(encoding="utf-8").splitlines()[0] for f in files]
    assert headings == ["第一章 序", "第二章 中", "第三章 末"]


def test_import_persists_initial_pending_job(tmp_path):
    book = import_novel(
        THREE_CHAPTER_TEXT,
        original_filename="x.txt",
        library_root=tmp_path,
    )
    job = load_job(book.book_id, root=tmp_path)
    assert job is not None
    assert job.status is BookJobStatus.PENDING
    assert job.detected_chapter_count == 3
    assert job.completed_chapter_indexes == []
    assert job.failed_chapter_indexes == []


def test_import_source_text_is_byte_identical(tmp_path):
    book = import_novel(
        THREE_CHAPTER_TEXT,
        original_filename="x.txt",
        library_root=tmp_path,
    )
    saved = source_path(book.book_id, root=tmp_path).read_text(encoding="utf-8")
    assert saved == THREE_CHAPTER_TEXT


def test_import_is_idempotent_for_same_content(tmp_path):
    first = import_novel(
        THREE_CHAPTER_TEXT,
        original_filename="x.txt",
        library_root=tmp_path,
    )
    # Mutate the job to simulate later progress, then re-import.
    job = load_job(first.book_id, root=tmp_path)
    assert job is not None
    job.status = BookJobStatus.PARTIAL
    job.completed_chapter_indexes = [1]
    from app.library.store import save_job
    save_job(job, root=tmp_path)

    second = import_novel(
        THREE_CHAPTER_TEXT,
        original_filename="some-other-name.txt",
        library_root=tmp_path,
    )
    # Same content → same workspace, original Book record preserved.
    assert second.book_id == first.book_id
    assert second.source_filename == first.source_filename == "x.txt"

    # Existing job state preserved.
    job_after = load_job(first.book_id, root=tmp_path)
    assert job_after is not None
    assert job_after.status is BookJobStatus.PARTIAL
    assert job_after.completed_chapter_indexes == [1]


def test_import_different_content_produces_different_book_ids(tmp_path):
    first = import_novel(
        THREE_CHAPTER_TEXT,
        original_filename="a.txt",
        library_root=tmp_path,
    )
    altered = THREE_CHAPTER_TEXT + "第四章 多出\n丁段。\n"
    second = import_novel(
        altered,
        original_filename="b.txt",
        library_root=tmp_path,
    )
    assert first.book_id != second.book_id
    assert second.detected_chapter_count == 4


def test_import_records_preamble_flag(tmp_path):
    text = "封面：某某传\n作者：佚名\n\n" + THREE_CHAPTER_TEXT
    book = import_novel(
        text,
        original_filename="b.txt",
        library_root=tmp_path,
    )
    assert book.has_preamble is True
    # Source file is verbatim — preamble lives only in source.txt, not as a chapter.
    files = list_chapter_files(book.book_id, root=tmp_path)
    assert len(files) == 3


def test_import_rejects_empty_text(tmp_path):
    with pytest.raises(BookImportError):
        import_novel("", original_filename="empty.txt", library_root=tmp_path)
    with pytest.raises(BookImportError):
        import_novel("   \n\n  ", original_filename="ws.txt", library_root=tmp_path)


def test_import_rejects_text_without_chapter_headings(tmp_path):
    with pytest.raises(BookImportError):
        import_novel(
            "纯散文，没有任何章节标题。\n",
            original_filename="prose.txt",
            library_root=tmp_path,
        )


def test_import_with_real_concatenated_fixture(tmp_path):
    """End-to-end happy path against real source data, when available."""
    repo_root = Path(__file__).resolve().parents[2]
    source_dir = repo_root / "data" / "source"
    parts = []
    for name in ("ch001.txt", "ch003.txt"):
        path = source_dir / name
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    if len(parts) < 2:
        pytest.skip("real fixtures ch001.txt / ch003.txt not present")

    combined = parts[0].rstrip() + "\n\n" + parts[1].lstrip()
    book = import_novel(
        combined,
        original_filename="real_concat.txt",
        library_root=tmp_path,
    )
    assert book.detected_chapter_count == 2
    files = list_chapter_files(book.book_id, root=tmp_path)
    assert len(files) == 2
    for f in files:
        first_line = f.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("第") and "章" in first_line
