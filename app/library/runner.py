"""Backend-owned sequential book translation runner.

Iterates over the chapter files written by ``app.library.intake`` and
hands each one to a caller-supplied translation function (real model
profile, smoke mode, etc.) in turn. Updates ``BookJob`` after every
chapter and writes the translated output and per-chapter manifest
under the book workspace.

Product contract:
    The runner uses the actual chapter files on disk to decide what
    to do next, NOT ``Book.detected_chapter_count`` — that field is a
    splitter snapshot, not an absolute total. The translation
    contract is sequential: translate the next unfinished chapter
    until no next chapter remains.

Runner does NOT decide which model backend to use. The caller passes
in ``translate_chapter_fn`` and chooses smoke vs. real there.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from app.chapter.manifest import ChapterStatus
from app.chapter.models import ChapterResult
from app.library.models import BookJob, BookJobStatus
from app.library.store import (
    book_dir,
    book_exists,
    list_chapter_files,
    load_job,
    save_job,
)


# (chapter_source_text, manifest_output_path) -> ChapterResult
ChapterTranslateFn = Callable[[str, str], ChapterResult]


class BookRunnerError(RuntimeError):
    """Raised when a book cannot be advanced (e.g., missing book)."""


@dataclass(frozen=True)
class RunNextResult:
    """Outcome of a single ``run_next_chapter`` call."""

    book_id: str
    ran_index: Optional[int]
    """Chapter index that was attempted, or None when no chapter was available."""
    success: bool
    """True iff ``ChapterResult.chapter_status == COMPLETED``."""
    chapter_result: Optional[ChapterResult]
    output_path: Optional[Path]
    manifest_path: Optional[Path]
    error_message: Optional[str]
    job: BookJob


@dataclass(frozen=True)
class RunUntilDoneResult:
    """Outcome of a ``run_until_done`` loop."""

    book_id: str
    chapters_attempted: List[int] = field(default_factory=list)
    chapters_succeeded: List[int] = field(default_factory=list)
    chapters_failed: List[int] = field(default_factory=list)
    stopped_reason: str = ""
    """One of: 'no_more_chapters', 'failure', 'max_chapters_reached'."""
    job: Optional[BookJob] = None


# ── Workspace helpers ──────────────────────────────────────────────────

def translations_dir(book_id: str, root: Optional[Path] = None) -> Path:
    target = book_dir(book_id, root) / "translations"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _parse_chapter_filename(path: Path) -> Optional[Tuple[int, str]]:
    """Extract ``(index, slug)`` from a chapter filename ``NNNN_<slug>.txt``.

    Returns None when the filename doesn't match the kernel layout."""
    stem = path.stem
    head, sep, slug = stem.partition("_")
    if not sep or not head.isdigit():
        return None
    return int(head), slug


def _chapter_inventory(
    book_id: str,
    root: Optional[Path] = None,
) -> List[Tuple[int, str, Path]]:
    """All on-disk chapters as a sorted list of ``(index, slug, path)``."""
    out: List[Tuple[int, str, Path]] = []
    for path in list_chapter_files(book_id, root):
        parsed = _parse_chapter_filename(path)
        if parsed is None:
            continue
        idx, slug = parsed
        out.append((idx, slug, path))
    out.sort(key=lambda triple: triple[0])
    return out


def _translation_paths(
    book_id: str,
    index: int,
    slug: str,
    root: Optional[Path] = None,
) -> Tuple[Path, Path]:
    """Return ``(translation_md_path, manifest_json_path)`` for a chapter."""
    target_dir = translations_dir(book_id, root)
    base = f"{index:04d}_{slug}_en"
    return target_dir / f"{base}.md", target_dir / f"{base}.manifest.json"


# ── Job-state transitions ──────────────────────────────────────────────

def _recompute_book_status(job: BookJob, all_indexes: List[int]) -> None:
    """Update ``job.status`` based on the current set of on-disk chapter
    indexes. Mutates in place; does not save.

    The on-disk inventory is the source of truth for "is the book done?"
    — ``detected_chapter_count`` is intentionally not used here.
    """
    inventory = set(all_indexes)
    completed = set(job.completed_chapter_indexes)
    failed = set(job.failed_chapter_indexes)
    if not inventory:
        # No chapter files at all — unusual, but don't pretend success.
        job.status = BookJobStatus.PENDING
    elif inventory <= completed:
        job.status = BookJobStatus.COMPLETE
    elif inventory <= (completed | failed):
        # Every on-disk chapter has been attempted at least once.
        job.status = BookJobStatus.PARTIAL if completed else BookJobStatus.FAILED
    else:
        # Still chapters left to attempt.
        job.status = BookJobStatus.RUNNING


def _next_unfinished(
    inventory: List[Tuple[int, str, Path]],
    job: BookJob,
) -> Optional[Tuple[int, str, Path]]:
    """First on-disk chapter that is neither completed nor previously failed.

    Failed chapters are intentionally NOT auto-retried — the operator
    decides whether to clear them and re-run.
    """
    completed = set(job.completed_chapter_indexes)
    failed = set(job.failed_chapter_indexes)
    for idx, slug, path in inventory:
        if idx in completed or idx in failed:
            continue
        return idx, slug, path
    return None


# ── Public API ─────────────────────────────────────────────────────────

def run_next_chapter(
    book_id: str,
    translate_chapter_fn: ChapterTranslateFn,
    *,
    library_root: Optional[Path] = None,
) -> RunNextResult:
    """Translate the next unfinished chapter of ``book_id``.

    Looks at the chapter files on disk, picks the lowest-indexed one
    that has neither ``completed`` nor ``failed`` status on the job,
    invokes ``translate_chapter_fn``, writes the translated text and
    per-chapter manifest under ``data/library/<book_id>/translations/``,
    updates the BookJob, and persists.

    Returns a ``RunNextResult`` describing what happened. When no
    chapter remains, ``ran_index`` is None and the job state is
    refreshed to reflect the on-disk inventory.
    """
    if not book_exists(book_id, library_root):
        raise BookRunnerError(f"book {book_id} not found")

    job = load_job(book_id, library_root)
    if job is None:
        raise BookRunnerError(f"book {book_id} has no job record")

    inventory = _chapter_inventory(book_id, library_root)
    all_indexes = [idx for idx, _, _ in inventory]

    target = _next_unfinished(inventory, job)
    if target is None:
        # No chapter left to attempt — refresh status and persist.
        _recompute_book_status(job, all_indexes)
        job.touch()
        save_job(job, library_root)
        return RunNextResult(
            book_id=book_id,
            ran_index=None,
            success=False,
            chapter_result=None,
            output_path=None,
            manifest_path=None,
            error_message=None,
            job=job,
        )

    index, slug, source_path = target
    output_path, manifest_path = _translation_paths(
        book_id, index, slug, library_root,
    )
    source_text = source_path.read_text(encoding="utf-8")

    job.status = BookJobStatus.RUNNING
    job.touch()
    save_job(job, library_root)

    error_message: Optional[str] = None
    chapter_result: Optional[ChapterResult] = None
    success = False
    try:
        chapter_result = translate_chapter_fn(source_text, str(manifest_path))
    except Exception as exc:  # surface any backend failure as a chapter failure
        error_message = f"{type(exc).__name__}: {exc}"

    if chapter_result is not None:
        success = chapter_result.chapter_status == ChapterStatus.COMPLETED
        if success:
            output_path.write_text(
                chapter_result.final_translation,
                encoding="utf-8",
            )
        else:
            error_message = (
                f"chapter status: {chapter_result.chapter_status.value}"
            )

    if success:
        if index not in job.completed_chapter_indexes:
            job.completed_chapter_indexes.append(index)
            job.completed_chapter_indexes.sort()
        job.error_message = None
    else:
        if index not in job.failed_chapter_indexes:
            job.failed_chapter_indexes.append(index)
            job.failed_chapter_indexes.sort()
        job.error_message = error_message

    _recompute_book_status(job, all_indexes)
    job.touch()
    save_job(job, library_root)

    return RunNextResult(
        book_id=book_id,
        ran_index=index,
        success=success,
        chapter_result=chapter_result,
        output_path=output_path if success else None,
        manifest_path=manifest_path,
        error_message=error_message,
        job=job,
    )


def run_until_done(
    book_id: str,
    translate_chapter_fn: ChapterTranslateFn,
    *,
    library_root: Optional[Path] = None,
    max_chapters: Optional[int] = None,
) -> RunUntilDoneResult:
    """Translate chapter by chapter until no next chapter remains.

    Stops on the first failure (a failed chapter is recorded but the
    runner does not auto-skip past it). ``max_chapters`` is an
    operator-level safety bound; defaults to None (run to completion).
    """
    attempted: List[int] = []
    succeeded: List[int] = []
    failed: List[int] = []
    job: Optional[BookJob] = None
    stopped_reason = "no_more_chapters"

    while True:
        if max_chapters is not None and len(attempted) >= max_chapters:
            stopped_reason = "max_chapters_reached"
            break
        result = run_next_chapter(
            book_id,
            translate_chapter_fn,
            library_root=library_root,
        )
        job = result.job
        if result.ran_index is None:
            stopped_reason = "no_more_chapters"
            break
        attempted.append(result.ran_index)
        if result.success:
            succeeded.append(result.ran_index)
        else:
            failed.append(result.ran_index)
            stopped_reason = "failure"
            break

    return RunUntilDoneResult(
        book_id=book_id,
        chapters_attempted=attempted,
        chapters_succeeded=succeeded,
        chapters_failed=failed,
        stopped_reason=stopped_reason,
        job=job,
    )
