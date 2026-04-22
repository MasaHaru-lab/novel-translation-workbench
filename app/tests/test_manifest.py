import sys
import os
import json
import tempfile
import time
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.chapter.manifest import (
    ChapterStatus,
    ResumeConfig,
    RunManifest,
    SegmentRecord,
    SegmentStatus,
)


# ── SegmentRecord ──────────────────────────────────────────────────────

def test_segment_record_starts_pending():
    rec = SegmentRecord(segment_id="1")
    assert rec.status == SegmentStatus.PENDING
    assert rec.retry_count == 0
    assert rec.error_message == ""


def test_segment_record_mark_running():
    rec = SegmentRecord(segment_id="1")
    rec.mark_running()
    assert rec.status == SegmentStatus.RUNNING
    assert rec.started_at is not None


def test_segment_record_mark_completed():
    rec = SegmentRecord(segment_id="1")
    rec.mark_running()
    rec.mark_completed()
    assert rec.status == SegmentStatus.COMPLETED
    assert rec.completed_at is not None
    assert rec.duration_seconds is not None
    assert rec.duration_seconds >= 0


def test_segment_record_mark_failed():
    rec = SegmentRecord(segment_id="1")
    rec.mark_running()
    rec.mark_failed("Something went wrong")
    assert rec.status == SegmentStatus.FAILED
    assert rec.error_message == "Something went wrong"
    assert rec.completed_at is not None


def test_segment_record_should_retry_within_bounds():
    config = ResumeConfig(max_retries=2)
    rec = SegmentRecord(segment_id="1")
    assert rec.should_retry(config) is True
    rec.retry_count = 1
    assert rec.should_retry(config) is True
    rec.retry_count = 2
    assert rec.should_retry(config) is False


def test_segment_record_should_retry_zero_max():
    config = ResumeConfig(max_retries=0)
    rec = SegmentRecord(segment_id="1")
    assert rec.should_retry(config) is False


# ── RunManifest.create ─────────────────────────────────────────────────

def test_create_manifest():
    manifest = RunManifest.create(
        chapter_title="第一章",
        source_text="第一章\n\n内容。",
        segment_ids=["1", "2", "3"],
    )
    assert manifest.run_id
    assert manifest.chapter_title == "第一章"
    assert manifest.total_segments == 3
    assert manifest.status == ChapterStatus.PENDING
    assert len(manifest.segments) == 3
    for sid in ["1", "2", "3"]:
        assert manifest.segments[sid].status == SegmentStatus.PENDING


def test_create_manifest_with_custom_config():
    config = ResumeConfig(max_retries=5, retry_delay_seconds=0.5)
    manifest = RunManifest.create(
        chapter_title="Test",
        source_text="test",
        segment_ids=["1"],
        resume_config=config,
    )
    assert manifest.resume_config.max_retries == 5
    assert manifest.resume_config.retry_delay_seconds == 0.5


# ── Status transitions ─────────────────────────────────────────────────

def test_start_run():
    manifest = RunManifest.create("Test", "test", ["1", "2"])
    manifest.start_run()
    assert manifest.status == ChapterStatus.RUNNING
    assert manifest.started_at is not None


def test_all_segments_completed():
    manifest = RunManifest.create("Test", "test", ["1", "2"])
    manifest.start_run()
    manifest.mark_segment_completed("1")
    manifest.mark_segment_completed("2")
    manifest.complete_run()
    assert manifest.status == ChapterStatus.COMPLETED


def test_some_segments_failed():
    manifest = RunManifest.create("Test", "test", ["1", "2", "3"])
    manifest.start_run()
    manifest.mark_segment_completed("1")
    manifest.mark_segment_completed("2")
    manifest.mark_segment_failed("3", "Translation error")
    manifest.complete_run()
    assert manifest.status == ChapterStatus.PARTIAL


def test_all_segments_failed():
    manifest = RunManifest.create("Test", "test", ["1", "2"])
    manifest.start_run()
    manifest.mark_segment_failed("1", "Error 1")
    manifest.mark_segment_failed("2", "Error 2")
    manifest.complete_run()
    assert manifest.status == ChapterStatus.FAILED


# ── Resume helpers ─────────────────────────────────────────────────────

def test_is_resumable_when_partial():
    manifest = RunManifest.create("Test", "test", ["1", "2", "3"])
    manifest.start_run()
    manifest.mark_segment_completed("1")
    manifest.mark_segment_failed("2", "err")
    manifest.complete_run()
    assert manifest.is_resumable() is True


def test_is_not_resumable_when_completed():
    manifest = RunManifest.create("Test", "test", ["1"])
    manifest.start_run()
    manifest.mark_segment_completed("1")
    manifest.complete_run()
    assert manifest.is_resumable() is False


def test_is_not_resumable_when_pending():
    manifest = RunManifest.create("Test", "test", ["1"])
    # Not started yet — PENDING state, not resumable
    assert manifest.is_resumable() is False


def test_get_pending_segment_ids():
    manifest = RunManifest.create("Test", "test", ["1", "2", "3"])
    manifest.start_run()
    manifest.mark_segment_completed("1")
    manifest.mark_segment_failed("2", "err")
    pending = manifest.get_pending_segment_ids()
    assert "1" not in pending
    assert "2" in pending  # Failed segments are pending for retry
    assert "3" in pending


def test_get_completed_segment_ids():
    manifest = RunManifest.create("Test", "test", ["1", "2", "3"])
    manifest.start_run()
    manifest.mark_segment_completed("1")
    manifest.mark_segment_completed("2")
    completed = manifest.get_completed_segment_ids()
    assert "1" in completed
    assert "2" in completed
    assert "3" not in completed


def test_get_summary():
    manifest = RunManifest.create("Test", "test", ["1", "2"])
    manifest.start_run()
    manifest.mark_segment_completed("1")
    manifest.complete_run()
    summary = manifest.get_summary()
    assert summary["status"] == "partial"  # segment 2 is pending
    assert summary["total_segments"] == 2
    assert summary["completed"] == 1
    assert summary["failed"] == 0
    assert summary["pending"] == 1


# ── Persistence ────────────────────────────────────────────────────────

def test_save_and_load(tmp_path):
    original = RunManifest.create("Test", "test", ["1", "2", "3"])
    original.start_run()
    original.mark_segment_completed("1")
    original.mark_segment_failed("2", "Some error")
    original.complete_run()  # Set terminal status before saving
    path = str(tmp_path / "test.manifest.json")
    original.manifest_path = path
    original.save()

    assert Path(path).exists()
    loaded = RunManifest.load(path)
    assert loaded.run_id == original.run_id
    assert loaded.chapter_title == "Test"
    assert loaded.total_segments == 3
    assert loaded.status == ChapterStatus.PARTIAL
    assert loaded.segments["1"].status == SegmentStatus.COMPLETED
    assert loaded.segments["2"].status == SegmentStatus.FAILED
    assert loaded.segments["2"].error_message == "Some error"
    assert loaded.segments["3"].status == SegmentStatus.PENDING


def test_save_and_load_full_completion(tmp_path):
    original = RunManifest.create("Complete", "test", ["1"])
    original.start_run()
    original.mark_segment_completed("1")
    original.complete_run()
    path = str(tmp_path / "complete.manifest.json")
    original.manifest_path = path
    original.save()

    loaded = RunManifest.load(path)
    assert loaded.status == ChapterStatus.COMPLETED
    assert loaded.completed_at is not None
    assert loaded.is_resumable() is False


def test_default_manifest_path():
    path = RunManifest.default_manifest_path("outputs/chapter1_en.md")
    assert path.endswith(".manifest.json")
    assert "outputs" in path


def test_load_nonexistent_manifest():
    from app.chapter.orchestrator import ChapterOrchestrator
    orch = ChapterOrchestrator()
    result = orch.load_manifest("/nonexistent/path.manifest.json")
    assert result is None


def test_load_corrupted_manifest(tmp_path):
    from app.chapter.orchestrator import ChapterOrchestrator
    bad_path = tmp_path / "bad.manifest.json"
    bad_path.write_text("not json", encoding="utf-8")
    orch = ChapterOrchestrator()
    result = orch.load_manifest(str(bad_path))
    assert result is None


# ── SegmentRecord retry_count ──────────────────────────────────────────

def test_mark_segment_failed_increments_retry():
    manifest = RunManifest.create("Test", "test", ["1"])
    manifest.start_run()
    assert manifest.segments["1"].retry_count == 0
    manifest.mark_segment_failed("1", "err")
    assert manifest.segments["1"].retry_count == 1
    assert manifest.segments["1"].status == SegmentStatus.FAILED
