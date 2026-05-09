"""Book and BookJob dataclasses for the library kernel.

``Book`` is descriptive (what was imported). ``BookJob`` is enacted
state (what has run). They are kept separate so that the planned-vs-
enacted discipline used elsewhere in the project also holds at the
book level.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class BookJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"
    COMPLETE = "complete"
    FAILED = "failed"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Book:
    """Descriptive metadata about an imported novel.

    Carries no translation runtime state. The companion ``BookJob``
    record carries enactment.
    """

    book_id: str
    title: str
    source_filename: str
    source_hash: str
    chapter_count: int
    has_preamble: bool = False
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "book_id": self.book_id,
            "title": self.title,
            "source_filename": self.source_filename,
            "source_hash": self.source_hash,
            "chapter_count": self.chapter_count,
            "has_preamble": self.has_preamble,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Book":
        return cls(
            book_id=data["book_id"],
            title=data["title"],
            source_filename=data["source_filename"],
            source_hash=data["source_hash"],
            chapter_count=int(data["chapter_count"]),
            has_preamble=bool(data.get("has_preamble", False)),
            created_at=data.get("created_at") or _utc_now_iso(),
        )


@dataclass
class BookJob:
    """Enacted translation-job state for a single book.

    A book has exactly one current job record. Per-chapter manifests
    live alongside the chapter files when translation actually runs;
    this record is the book-level summary.
    """

    book_id: str
    total_chapters: int
    status: BookJobStatus = BookJobStatus.PENDING
    completed_chapter_indexes: List[int] = field(default_factory=list)
    failed_chapter_indexes: List[int] = field(default_factory=list)
    error_message: Optional[str] = None
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "book_id": self.book_id,
            "total_chapters": self.total_chapters,
            "status": self.status.value,
            "completed_chapter_indexes": list(self.completed_chapter_indexes),
            "failed_chapter_indexes": list(self.failed_chapter_indexes),
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BookJob":
        return cls(
            book_id=data["book_id"],
            total_chapters=int(data["total_chapters"]),
            status=BookJobStatus(data.get("status", BookJobStatus.PENDING.value)),
            completed_chapter_indexes=list(data.get("completed_chapter_indexes", [])),
            failed_chapter_indexes=list(data.get("failed_chapter_indexes", [])),
            error_message=data.get("error_message"),
            created_at=data.get("created_at") or _utc_now_iso(),
            updated_at=data.get("updated_at") or _utc_now_iso(),
        )
