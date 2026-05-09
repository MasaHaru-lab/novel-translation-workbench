"""High-level book intake orchestration.

``import_novel`` is the single entry point: take raw novel text plus a
filename label, save the original verbatim, split into chapters,
write one file per chapter, then persist the ``Book`` and initial
``BookJob`` records. Translation is not invoked here.

Re-importing the same content (same ``source_hash``) is idempotent:
the existing ``Book`` is returned untouched and the existing job is
preserved. Importing different content produces a different
``book_id`` and a separate workspace.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from app.library.models import Book, BookJob, BookJobStatus
from app.library.splitter import SplitResult, split_by_chapter
from app.library.store import (
    book_exists,
    load_book,
    load_job,
    save_book,
    save_chapter_text,
    save_job,
    save_source_text,
)


class BookImportError(ValueError):
    """Raised when a novel cannot be imported."""


def _hash_source(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _book_id_from_hash(source_hash: str) -> str:
    """Short, content-derived book id. 12 hex chars is enough to avoid
    collisions for any realistic library size."""
    return f"bk_{source_hash[:12]}"


def _title_from_filename(filename: str) -> str:
    """Best-effort book title from the upload filename.

    Strips the extension and any directory components. The future
    HTTP layer can override the title; this is just a sensible default
    when the kernel is called directly.
    """
    stem = Path(filename).stem.strip()
    return stem or "Untitled"


def import_novel(
    source_text: str,
    *,
    original_filename: str,
    library_root: Optional[Path] = None,
) -> Book:
    """Import a full novel into the library.

    Args:
        source_text: Full text of the novel.
        original_filename: Filename the upload arrived under. Used to
            derive a default title and is stored verbatim on the Book
            record.
        library_root: Override the library root directory. Falls back
            to the ``LIBRARY_ROOT`` env var, then to ``data/library``.

    Returns:
        The ``Book`` record for the imported (or existing) workspace.

    Raises:
        BookImportError: when ``source_text`` is empty/whitespace, or
            when no chapter headings can be detected. The kernel does
            not silently turn an unparseable upload into a one-chapter
            workspace; the caller (HTTP layer or test) decides how to
            surface the failure.
    """
    if not source_text or not source_text.strip():
        raise BookImportError("source_text is empty")

    source_hash = _hash_source(source_text)
    book_id = _book_id_from_hash(source_hash)

    # Idempotent re-import: same content → return existing book unchanged.
    if book_exists(book_id, library_root):
        existing = load_book(book_id, library_root)
        if existing is not None:
            return existing

    split: SplitResult = split_by_chapter(source_text)
    if not split.chapters:
        raise BookImportError(
            "No chapter headings (第N章 …) detected in source_text"
        )

    save_source_text(book_id, source_text, library_root)
    for chapter in split.chapters:
        save_chapter_text(
            book_id,
            chapter.index,
            chapter.slug,
            chapter.body,
            library_root,
        )

    book = Book(
        book_id=book_id,
        title=_title_from_filename(original_filename),
        source_filename=original_filename,
        source_hash=source_hash,
        detected_chapter_count=len(split.chapters),
        has_preamble=split.preamble is not None,
    )
    save_book(book, library_root)

    # Only create an initial job when none exists. A re-import that
    # somehow reaches this branch (book.json absent, job.json present)
    # is unusual but should not clobber prior progress.
    if load_job(book_id, library_root) is None:
        job = BookJob(
            book_id=book_id,
            detected_chapter_count=len(split.chapters),
            status=BookJobStatus.PENDING,
        )
        save_job(job, library_root)

    return book
