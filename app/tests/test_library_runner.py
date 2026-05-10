"""Tests for app.library.runner.

End-to-end through the real chapter orchestrator in smoke mode (no
model backend). The runner itself does not pick a backend; the test
constructs a smoke-mode ``translate_chapter_fn`` and feeds it in.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.chapter.manifest import ChapterStatus
from app.chapter.models import ChapterResult
from app.chapter.orchestrator import ChapterOrchestrator
from app.config import config
from app.translate.translator import set_smoke_mode
from app.library.intake import import_novel
from app.library.models import BookJobStatus
from app.library.runner import (
    BookRunnerError,
    RunNextResult,
    RunUntilDoneResult,
    run_next_chapter,
    run_until_done,
    translations_dir,
)
from app.library.store import load_job


@pytest.fixture(autouse=True)
def _smoke_mode_fixture():
    """Force smoke mode on the translator and clear any backend URL,
    matching the protection used by the existing /api/chapters smoke
    path. Restored after each test."""
    original_backend_url = config.MODEL_BACKEND_URL
    config.MODEL_BACKEND_URL = ""
    set_smoke_mode(True)
    try:
        yield
    finally:
        set_smoke_mode(False)
        config.MODEL_BACKEND_URL = original_backend_url


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


def _smoke_translate(source_text: str, manifest_path: str) -> ChapterResult:
    """Translate a chapter via the real orchestrator in smoke mode."""
    return ChapterOrchestrator().run_with_manifest(
        source_text=source_text,
        manifest_path=manifest_path,
        smoke_test=True,
    )


def _failing_translate(source_text: str, manifest_path: str) -> ChapterResult:
    raise RuntimeError("simulated backend failure")


def _import_three_chapter_book(tmp_path: Path) -> str:
    book = import_novel(
        THREE_CHAPTER_TEXT,
        original_filename="某某传.txt",
        library_root=tmp_path,
    )
    return book.book_id


def test_run_next_chapter_picks_first_unfinished(tmp_path):
    book_id = _import_three_chapter_book(tmp_path)
    result = run_next_chapter(
        book_id, _smoke_translate, library_root=tmp_path,
    )
    assert isinstance(result, RunNextResult)
    assert result.ran_index == 1
    assert result.success is True
    assert result.output_path is not None and result.output_path.exists()
    assert result.manifest_path is not None and result.manifest_path.exists()
    assert result.job.completed_chapter_indexes == [1]
    assert result.job.failed_chapter_indexes == []
    assert result.job.status is BookJobStatus.RUNNING


def test_run_next_chapter_writes_output_to_workspace(tmp_path):
    book_id = _import_three_chapter_book(tmp_path)
    result = run_next_chapter(
        book_id, _smoke_translate, library_root=tmp_path,
    )
    expected_dir = translations_dir(book_id, root=tmp_path)
    assert result.output_path is not None
    assert result.output_path.parent == expected_dir
    assert result.output_path.name.startswith("0001_")
    assert result.output_path.name.endswith("_en.md")
    # Manifest sits next to the .md.
    assert result.manifest_path is not None
    assert result.manifest_path.parent == expected_dir
    assert result.manifest_path.name.endswith(".manifest.json")
    # Translation text is non-empty (smoke produces deterministic mock).
    assert result.output_path.read_text(encoding="utf-8").strip() != ""


def test_run_next_chapter_advances_sequentially(tmp_path):
    book_id = _import_three_chapter_book(tmp_path)
    indexes = []
    for _ in range(3):
        r = run_next_chapter(book_id, _smoke_translate, library_root=tmp_path)
        indexes.append(r.ran_index)
    assert indexes == [1, 2, 3]
    job = load_job(book_id, root=tmp_path)
    assert job is not None
    assert job.completed_chapter_indexes == [1, 2, 3]
    assert job.status is BookJobStatus.COMPLETE


def test_run_next_chapter_is_noop_when_done(tmp_path):
    book_id = _import_three_chapter_book(tmp_path)
    run_until_done(book_id, _smoke_translate, library_root=tmp_path)
    # All chapters complete — calling again must be a no-op.
    result = run_next_chapter(
        book_id, _smoke_translate, library_root=tmp_path,
    )
    assert result.ran_index is None
    assert result.success is False
    assert result.chapter_result is None
    assert result.job.status is BookJobStatus.COMPLETE


def test_run_until_done_translates_every_chapter(tmp_path):
    book_id = _import_three_chapter_book(tmp_path)
    summary = run_until_done(
        book_id, _smoke_translate, library_root=tmp_path,
    )
    assert isinstance(summary, RunUntilDoneResult)
    assert summary.chapters_attempted == [1, 2, 3]
    assert summary.chapters_succeeded == [1, 2, 3]
    assert summary.chapters_failed == []
    assert summary.stopped_reason == "no_more_chapters"
    assert summary.job is not None
    assert summary.job.status is BookJobStatus.COMPLETE
    # Each chapter produced an output file.
    out_dir = translations_dir(book_id, root=tmp_path)
    md_files = sorted(p.name for p in out_dir.iterdir() if p.suffix == ".md")
    assert md_files == [
        "0001_序_en.md",
        "0002_中_en.md",
        "0003_末_en.md",
    ]


def test_run_until_done_stops_on_first_failure(tmp_path):
    book_id = _import_three_chapter_book(tmp_path)
    summary = run_until_done(
        book_id, _failing_translate, library_root=tmp_path,
    )
    assert summary.chapters_attempted == [1]
    assert summary.chapters_succeeded == []
    assert summary.chapters_failed == [1]
    assert summary.stopped_reason == "failure"
    assert summary.job is not None
    # Status reflects on-disk reality (chapters 2 and 3 are still unattempted),
    # so the job is RUNNING, not FAILED. The procedural "we stopped because
    # of failure" lives on RunUntilDoneResult.stopped_reason.
    assert summary.job.status is BookJobStatus.RUNNING
    assert summary.job.error_message is not None
    assert "simulated backend failure" in summary.job.error_message


def test_run_until_done_status_failed_when_only_chapter_fails(tmp_path):
    """When the only on-disk chapter fails, status becomes FAILED —
    every chapter has been attempted, none completed."""
    book = import_novel(
        "第一章 序\n甲段。\n",
        original_filename="single.txt",
        library_root=tmp_path,
    )
    summary = run_until_done(
        book.book_id, _failing_translate, library_root=tmp_path,
    )
    assert summary.stopped_reason == "failure"
    assert summary.job is not None
    assert summary.job.status is BookJobStatus.FAILED


def test_failed_chapter_is_not_auto_retried(tmp_path):
    book_id = _import_three_chapter_book(tmp_path)
    # First pass: fail chapter 1.
    run_until_done(book_id, _failing_translate, library_root=tmp_path)
    # Second pass with a working translator: the runner skips the failed
    # index 1 and translates 2 and 3, leaving the job partial.
    summary = run_until_done(
        book_id, _smoke_translate, library_root=tmp_path,
    )
    assert summary.chapters_succeeded == [2, 3]
    assert summary.stopped_reason == "no_more_chapters"
    job = load_job(book_id, root=tmp_path)
    assert job is not None
    assert job.completed_chapter_indexes == [2, 3]
    assert job.failed_chapter_indexes == [1]
    assert job.status is BookJobStatus.PARTIAL


def test_max_chapters_bound(tmp_path):
    book_id = _import_three_chapter_book(tmp_path)
    summary = run_until_done(
        book_id, _smoke_translate, library_root=tmp_path, max_chapters=2,
    )
    assert summary.chapters_attempted == [1, 2]
    assert summary.chapters_succeeded == [1, 2]
    assert summary.stopped_reason == "max_chapters_reached"
    job = load_job(book_id, root=tmp_path)
    assert job is not None
    # Status reflects in-progress, not complete — chapter 3 is still untranslated.
    assert job.status is BookJobStatus.RUNNING


def test_runner_uses_disk_inventory_not_detected_count(tmp_path):
    """The runner stops based on on-disk chapter availability, not
    Book.detected_chapter_count. If a chapter file is removed after
    import, the runner stops at the new boundary without complaint."""
    book_id = _import_three_chapter_book(tmp_path)
    # Remove chapter 3 file post-import — the splitter's snapshot says 3
    # but only 2 are actually available.
    for path in (tmp_path / book_id / "chapters").iterdir():
        if path.name.startswith("0003_"):
            path.unlink()
    summary = run_until_done(
        book_id, _smoke_translate, library_root=tmp_path,
    )
    assert summary.chapters_attempted == [1, 2]
    assert summary.stopped_reason == "no_more_chapters"
    job = load_job(book_id, root=tmp_path)
    assert job is not None
    # With only 2 on-disk chapters and both completed, status is COMPLETE
    # — the splitter's detected_chapter_count of 3 is informational only.
    assert job.status is BookJobStatus.COMPLETE


def test_run_next_chapter_unknown_book_raises(tmp_path):
    with pytest.raises(BookRunnerError):
        run_next_chapter(
            "bk_does_not_exi",
            _smoke_translate,
            library_root=tmp_path,
        )


def test_job_is_persisted_after_each_chapter(tmp_path):
    """After a single chapter, the on-disk job.json reflects progress
    even before the runner returns control to a higher-level caller."""
    book_id = _import_three_chapter_book(tmp_path)
    run_next_chapter(book_id, _smoke_translate, library_root=tmp_path)
    persisted = load_job(book_id, root=tmp_path)
    assert persisted is not None
    assert persisted.completed_chapter_indexes == [1]
    assert persisted.status is BookJobStatus.RUNNING
