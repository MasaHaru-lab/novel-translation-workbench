"""Filesystem persistence for Book and BookJob records.

Layout under ``<library_root>/<book_id>/``::

    book.json                 # Book record
    job.json                  # BookJob record
    source.txt                # Original upload, byte-identical
    chapters/0001_<slug>.txt  # One file per chapter, heading on line 1
    chapters/0002_<slug>.txt
    ...

Mirrors the JSON-on-disk pattern used by ``app.chapter.manifest``;
no database. The default ``library_root`` is ``data/library``
relative to the project root, but every public function accepts an
explicit override so tests can use ``tmp_path``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from app.library.models import Book, BookJob


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIBRARY_ROOT = PROJECT_ROOT / "data" / "library"
LIBRARY_ROOT_ENV = "LIBRARY_ROOT"


def library_root(override: Optional[Path] = None) -> Path:
    """Resolve the library root directory.

    Resolution order: explicit ``override`` arg → ``LIBRARY_ROOT``
    environment variable → project default ``data/library``.
    """
    if override is not None:
        return Path(override)
    env_value = os.environ.get(LIBRARY_ROOT_ENV)
    if env_value:
        return Path(env_value)
    return DEFAULT_LIBRARY_ROOT


def book_dir(book_id: str, root: Optional[Path] = None) -> Path:
    return library_root(root) / book_id


def chapters_dir(book_id: str, root: Optional[Path] = None) -> Path:
    return book_dir(book_id, root) / "chapters"


def book_path(book_id: str, root: Optional[Path] = None) -> Path:
    return book_dir(book_id, root) / "book.json"


def job_path(book_id: str, root: Optional[Path] = None) -> Path:
    return book_dir(book_id, root) / "job.json"


def source_path(book_id: str, root: Optional[Path] = None) -> Path:
    return book_dir(book_id, root) / "source.txt"


def chapter_path(
    book_id: str,
    index: int,
    slug: str,
    root: Optional[Path] = None,
) -> Path:
    """Path for a chapter file, zero-padded index + slug."""
    filename = f"{index:04d}_{slug}.txt"
    return chapters_dir(book_id, root) / filename


def ensure_book_workspace(book_id: str, root: Optional[Path] = None) -> Path:
    target = book_dir(book_id, root)
    target.mkdir(parents=True, exist_ok=True)
    chapters_dir(book_id, root).mkdir(parents=True, exist_ok=True)
    return target


def save_book(book: Book, root: Optional[Path] = None) -> Path:
    ensure_book_workspace(book.book_id, root)
    target = book_path(book.book_id, root)
    target.write_text(
        json.dumps(book.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def load_book(book_id: str, root: Optional[Path] = None) -> Optional[Book]:
    target = book_path(book_id, root)
    if not target.exists():
        return None
    data = json.loads(target.read_text(encoding="utf-8"))
    return Book.from_dict(data)


def save_job(job: BookJob, root: Optional[Path] = None) -> Path:
    ensure_book_workspace(job.book_id, root)
    target = job_path(job.book_id, root)
    target.write_text(
        json.dumps(job.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def load_job(book_id: str, root: Optional[Path] = None) -> Optional[BookJob]:
    target = job_path(book_id, root)
    if not target.exists():
        return None
    data = json.loads(target.read_text(encoding="utf-8"))
    return BookJob.from_dict(data)


def save_source_text(
    book_id: str,
    text: str,
    root: Optional[Path] = None,
) -> Path:
    ensure_book_workspace(book_id, root)
    target = source_path(book_id, root)
    target.write_text(text, encoding="utf-8")
    return target


def save_chapter_text(
    book_id: str,
    index: int,
    slug: str,
    body: str,
    root: Optional[Path] = None,
) -> Path:
    ensure_book_workspace(book_id, root)
    target = chapter_path(book_id, index, slug, root)
    target.write_text(body, encoding="utf-8")
    return target


def list_chapter_files(
    book_id: str,
    root: Optional[Path] = None,
) -> List[Path]:
    """List chapter files in numeric order. Empty when none exist."""
    target = chapters_dir(book_id, root)
    if not target.exists():
        return []
    return sorted(p for p in target.iterdir() if p.is_file() and p.suffix == ".txt")


def book_exists(book_id: str, root: Optional[Path] = None) -> bool:
    return book_path(book_id, root).exists()
