"""Run manifest and progress record for chapter-level translation.

This module establishes the runtime stability foundation for chapter tasks:

- RunManifest: a persistent, JSON-serializable record of a single chapter run
- SegmentRecord: per-segment status, retry count, and error tracking
- RunStatus / SegmentStatus: explicit state machine for execution lifecycle
- ResumeConfig: bounded retry / downgrade discipline

Every chapter run produces a manifest file that can be inspected after the
fact or used to resume an interrupted run.
"""

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class SegmentStatus(str, Enum):
    """Status of a single segment within a chapter run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ChapterStatus(str, Enum):
    """Overall status of a chapter run.

    State transitions:
      pending -> running -> completed
                         -> partial (some segments failed)
                         -> failed (all segments failed)
    """

    PENDING = "pending"
    RUNNING = "running"
    PARTIAL = "partial"  # some segments completed, some failed
    COMPLETED = "completed"  # all segments completed successfully
    FAILED = "failed"  # all segments failed


@dataclass
class ResumeConfig:
    """Conservative retry / downgrade discipline for segment execution.

    These bounds exist to prevent infinite retry loops and uncontrolled
    degradation. They are simple, explicit, and testable.
    """

    max_retries: int = 2
    """Maximum number of retry attempts per segment before marking it failed."""

    retry_delay_seconds: float = 1.0
    """Base delay between retry attempts (no exponential backoff in v1)."""

    auto_retry_on_resume: bool = True
    """When True, failed segments are automatically retried on resume."""


@dataclass
class SegmentRecord:
    """Runtime record for a single segment in a chapter run."""

    segment_id: str
    status: SegmentStatus = SegmentStatus.PENDING
    retry_count: int = 0
    error_message: str = ""
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration_seconds: Optional[float] = None

    def mark_running(self) -> None:
        self.status = SegmentStatus.RUNNING
        self.started_at = time.time()

    def mark_completed(self) -> None:
        self.status = SegmentStatus.COMPLETED
        self.completed_at = time.time()
        if self.started_at is not None:
            self.duration_seconds = self.completed_at - self.started_at

    def mark_failed(self, error: str) -> None:
        self.status = SegmentStatus.FAILED
        self.error_message = error
        self.completed_at = time.time()
        if self.started_at is not None:
            self.duration_seconds = self.completed_at - self.started_at

    def should_retry(self, config: ResumeConfig) -> bool:
        """Return True if this segment can be retried within bounds."""
        return self.retry_count < config.max_retries


@dataclass
class RunManifest:
    """Persistent progress record for a single chapter translation run.

    The manifest is the single source of truth for what has happened during
    a chapter run. It is saved to disk after each segment so that progress
    survives process restarts.

    Attributes:
        run_id: Unique identifier for this run.
        chapter_title: Title of the chapter being translated.
        source_text_hash: Hash of the source text (for detecting changes).
        total_segments: Total number of segments in the chapter.
        status: Overall chapter-level status.
        segments: Per-segment records indexed by segment_id.
        resume_config: Retry / downgrade bounds in effect for this run.
        started_at: When the run started (epoch seconds).
        completed_at: When the run completed (epoch seconds), if finished.
        manifest_path: Path where this manifest is (or should be) persisted.
    """

    run_id: str = ""
    chapter_title: str = ""
    source_text_hash: str = ""
    total_segments: int = 0
    status: ChapterStatus = ChapterStatus.PENDING
    segments: Dict[str, SegmentRecord] = field(default_factory=dict)
    resume_config: ResumeConfig = field(default_factory=ResumeConfig)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    manifest_path: Optional[str] = None
    quality_summary: Optional[dict] = None
    """Post-aggregation quality-gate summary.

    Persisted so a "completed" manifest cannot mask a failed quality gate.
    Shape::

        {"passed": bool, "error_count": int, "warning_count": int,
         "codes": [str, ...]}

    ``None`` means the quality gate was not run (e.g. older runs before
    the gate was wired in)."""

    smoke_test: bool = False
    """True when this run was executed in smoke-test mode (mock translation,
    no real model backend). Smoke-test runs skip quality gates and
    consistency passes; their output is not a real translation."""

    @staticmethod
    def create(
        chapter_title: str,
        source_text: str,
        segment_ids: List[str],
        resume_config: Optional[ResumeConfig] = None,
        manifest_path: Optional[str] = None,
        smoke_test: bool = False,
    ) -> "RunManifest":
        """Create a new RunManifest for a chapter run.

        Args:
            chapter_title: The chapter title.
            source_text: Full source text (used for change detection).
            segment_ids: Ordered list of segment IDs.
            resume_config: Retry/downgrade bounds (defaults if omitted).
            manifest_path: Where to persist the manifest (optional).

        Returns:
            A new RunManifest in PENDING state.
        """
        return RunManifest(
            run_id=uuid.uuid4().hex[:12],
            chapter_title=chapter_title,
            source_text_hash=_hash_text(source_text),
            total_segments=len(segment_ids),
            status=ChapterStatus.PENDING,
            segments={
                sid: SegmentRecord(segment_id=sid)
                for sid in segment_ids
            },
            resume_config=resume_config or ResumeConfig(),
            manifest_path=manifest_path,
            smoke_test=smoke_test,
        )

    # ── Status helpers ─────────────────────────────────────────────────

    def start_run(self) -> None:
        """Mark the run as started."""
        self.status = ChapterStatus.RUNNING
        self.started_at = time.time()

    def _recompute_chapter_status(self) -> None:
        """Recompute the overall chapter status from segment states.

        During active execution: PENDING and RUNNING segments mean the
        chapter is still RUNNING.
        """
        if not self.segments:
            return
        statuses = {s.status for s in self.segments.values()}
        if statuses == {SegmentStatus.COMPLETED}:
            self.status = ChapterStatus.COMPLETED
        elif SegmentStatus.RUNNING in statuses or SegmentStatus.PENDING in statuses:
            self.status = ChapterStatus.RUNNING
        elif statuses == {SegmentStatus.FAILED}:
            self.status = ChapterStatus.FAILED
        else:
            self.status = ChapterStatus.PARTIAL

    def mark_segment_running(self, segment_id: str) -> None:
        """Mark a segment as running."""
        rec = self.segments.get(segment_id)
        if rec is not None:
            rec.mark_running()

    def mark_segment_completed(self, segment_id: str) -> None:
        """Mark a segment as completed and update chapter status."""
        rec = self.segments.get(segment_id)
        if rec is not None:
            rec.mark_completed()
        self._recompute_chapter_status()

    def mark_segment_failed(self, segment_id: str, error: str) -> None:
        """Mark a segment as failed and update chapter status."""
        rec = self.segments.get(segment_id)
        if rec is not None:
            rec.retry_count += 1
            rec.mark_failed(error)
        self._recompute_chapter_status()

    def complete_run(self) -> None:
        """Mark the entire run as finished with a terminal status.

        Terminal status logic (different from during-run recompute):
        - All segments COMPLETED -> COMPLETED
        - All segments FAILED -> FAILED
        - Any other mix (some completed, some failed, some pending) -> PARTIAL
        """
        if not self.segments:
            return
        statuses = {s.status for s in self.segments.values()}
        if statuses == {SegmentStatus.COMPLETED}:
            self.status = ChapterStatus.COMPLETED
        elif statuses == {SegmentStatus.FAILED}:
            self.status = ChapterStatus.FAILED
        else:
            self.status = ChapterStatus.PARTIAL
        self.completed_at = time.time()

    # ── Resume helpers ─────────────────────────────────────────────────

    def is_resumable(self) -> bool:
        """Return True if the run can be resumed (not already fully done)."""
        return self.status in (
            ChapterStatus.RUNNING,
            ChapterStatus.PARTIAL,
            ChapterStatus.FAILED,
        )

    def get_pending_segment_ids(self) -> List[str]:
        """Return segment IDs that still need work (pending or failed)."""
        return [
            sid
            for sid, rec in self.segments.items()
            if rec.status in (
                SegmentStatus.PENDING,
                SegmentStatus.RUNNING,
                SegmentStatus.FAILED,
            )
        ]

    def get_completed_segment_ids(self) -> List[str]:
        """Return segment IDs that completed successfully."""
        return [
            sid
            for sid, rec in self.segments.items()
            if rec.status == SegmentStatus.COMPLETED
        ]

    def get_summary(self) -> dict:
        """Return a human-readable summary of the run progress."""
        total = self.total_segments
        completed = len(self.get_completed_segment_ids())
        failed = sum(
            1 for r in self.segments.values() if r.status == SegmentStatus.FAILED
        )
        pending = total - completed - failed
        return {
            "run_id": self.run_id,
            "chapter_title": self.chapter_title,
            "status": self.status.value,
            "total_segments": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "resumable": self.is_resumable(),
        }

    # ── Persistence ────────────────────────────────────────────────────

    def save(self) -> None:
        """Persist the manifest to disk as JSON."""
        if self.manifest_path is None:
            raise RuntimeError("manifest_path is not set; cannot save")
        path = Path(self.manifest_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @staticmethod
    def load(manifest_path: str) -> "RunManifest":
        """Load a manifest from a JSON file on disk."""
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        return RunManifest.from_dict(data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        d = asdict(self)
        d["status"] = self.status.value
        d["segments"] = {
            sid: {
                **asdict(rec),
                "status": rec.status.value,
            }
            for sid, rec in self.segments.items()
        }
        d["resume_config"] = asdict(self.resume_config)
        return json.dumps(d, indent=2, ensure_ascii=False)

    @staticmethod
    def from_dict(d: dict) -> "RunManifest":
        """Deserialize from a dictionary."""
        segments = {}
        for sid, sdata in d.get("segments", {}).items():
            sdata["status"] = SegmentStatus(sdata["status"])
            segments[sid] = SegmentRecord(**sdata)

        rc_data = d.get("resume_config", {})
        resume_config = ResumeConfig(**rc_data) if rc_data else ResumeConfig()

        return RunManifest(
            run_id=d.get("run_id", ""),
            chapter_title=d.get("chapter_title", ""),
            source_text_hash=d.get("source_text_hash", ""),
            total_segments=d.get("total_segments", 0),
            status=ChapterStatus(d.get("status", "pending")),
            segments=segments,
            resume_config=resume_config,
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            manifest_path=d.get("manifest_path"),
            quality_summary=d.get("quality_summary"),
            smoke_test=d.get("smoke_test", False),
        )

    @staticmethod
    def default_manifest_path(output_path: str) -> str:
        """Derive the manifest path from the chapter output path."""
        return str(Path(output_path).with_suffix(".manifest.json"))


def _hash_text(text: str) -> str:
    """Simple stable hash for change detection (not cryptographic)."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
