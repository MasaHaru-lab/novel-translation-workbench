"""Tests for the Phase C Stage 5 validation helper (inspector module)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from app.chapter.inspector import (
    ChapterArtifacts,
    ManifestSummary,
    NextStep,
    find_artifacts,
    format_inspection_guide,
    load_manifest,
    suggest_next_step,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _write_manifest(path: Path, data: Dict[str, Any]) -> Path:
    """Write a minimal RunManifest JSON fixture to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def completed_manifest(tmp_path: Path) -> Path:
    """A COMPLETED manifest with a passing quality gate."""
    return _write_manifest(tmp_path / "completed.manifest.json", {
        "run_id": "abc123",
        "chapter_title": "Test Chapter",
        "source_text_hash": "aabbccdd",
        "total_segments": 5,
        "status": "completed",
        "segments": {
            f"seg_{i}": {
                "segment_id": f"seg_{i}",
                "status": "completed",
                "retry_count": 0,
                "error_message": "",
                "polished_text": "",
                "started_at": 1000.0 + i,
                "completed_at": 1100.0 + i,
                "duration_seconds": 100.0,
            }
            for i in range(1, 6)
        },
        "resume_config": {"max_retries": 2, "retry_delay_seconds": 1.0, "auto_retry_on_resume": True},
        "started_at": 1000.0,
        "completed_at": 1600.0,
        "manifest_path": str(tmp_path / "completed.manifest.json"),
        "quality_summary": {"passed": True, "error_count": 0, "warning_count": 0, "codes": []},
        "smoke_test": False,
        "git_ref": "main @ abc1234",
    })


@pytest.fixture
def failed_quality_manifest(tmp_path: Path) -> Path:
    """A COMPLETED manifest with a FAILED quality gate."""
    return _write_manifest(tmp_path / "failed_quality.manifest.json", {
        "run_id": "def456",
        "chapter_title": "Bad Chapter",
        "source_text_hash": "bbccddee",
        "total_segments": 3,
        "status": "completed",
        "segments": {
            f"seg_{i}": {
                "segment_id": f"seg_{i}",
                "status": "completed",
                "retry_count": 0,
                "error_message": "",
                "polished_text": "",
                "started_at": 2000.0 + i,
                "completed_at": 2100.0 + i,
                "duration_seconds": 100.0,
            }
            for i in range(1, 4)
        },
        "resume_config": {"max_retries": 2, "retry_delay_seconds": 1.0, "auto_retry_on_resume": True},
        "started_at": 2000.0,
        "completed_at": 2400.0,
        "manifest_path": str(tmp_path / "failed_quality.manifest.json"),
        "quality_summary": {
            "passed": False,
            "error_count": 2,
            "warning_count": 1,
            "codes": ["cjk_residue", "placeholder_leak"],
        },
        "smoke_test": False,
        "git_ref": "work/branch @ def789",
    })


@pytest.fixture
def partial_manifest(tmp_path: Path) -> Path:
    """A PARTIAL manifest (some segments completed, some failed)."""
    return _write_manifest(tmp_path / "partial.manifest.json", {
        "run_id": "ghi789",
        "chapter_title": "Partial Chapter",
        "source_text_hash": "ccddeeff",
        "total_segments": 4,
        "status": "partial",
        "segments": {
            "seg_1": {
                "segment_id": "seg_1",
                "status": "completed",
                "retry_count": 0,
                "error_message": "",
                "polished_text": "",
                "started_at": 3000.0,
                "completed_at": 3100.0,
                "duration_seconds": 100.0,
            },
            "seg_2": {
                "segment_id": "seg_2",
                "status": "completed",
                "retry_count": 0,
                "error_message": "",
                "polished_text": "",
                "started_at": 3100.0,
                "completed_at": 3200.0,
                "duration_seconds": 100.0,
            },
            "seg_3": {
                "segment_id": "seg_3",
                "status": "failed",
                "retry_count": 2,
                "error_message": "Model backend timeout",
                "polished_text": "",
                "started_at": 3200.0,
                "completed_at": 3500.0,
                "duration_seconds": 300.0,
            },
            "seg_4": {
                "segment_id": "seg_4",
                "status": "pending",
                "retry_count": 0,
                "error_message": "",
                "polished_text": "",
                "started_at": None,
                "completed_at": None,
                "duration_seconds": None,
            },
        },
        "resume_config": {"max_retries": 2, "retry_delay_seconds": 1.0, "auto_retry_on_resume": True},
        "started_at": 3000.0,
        "completed_at": 3500.0,
        "manifest_path": str(tmp_path / "partial.manifest.json"),
        "quality_summary": {"passed": True, "error_count": 0, "warning_count": 0, "codes": []},
        "smoke_test": False,
        "git_ref": "",
    })


@pytest.fixture
def failed_manifest(tmp_path: Path) -> Path:
    """A FAILED manifest (all segments failed)."""
    return _write_manifest(tmp_path / "failed.manifest.json", {
        "run_id": "jkl012",
        "chapter_title": "Failed Chapter",
        "source_text_hash": "ddeeffgg",
        "total_segments": 2,
        "status": "failed",
        "segments": {
            "seg_1": {
                "segment_id": "seg_1",
                "status": "failed",
                "retry_count": 2,
                "error_message": "Backend unreachable",
                "polished_text": "",
                "started_at": 4000.0,
                "completed_at": 4300.0,
                "duration_seconds": 300.0,
            },
            "seg_2": {
                "segment_id": "seg_2",
                "status": "failed",
                "retry_count": 2,
                "error_message": "Backend unreachable",
                "polished_text": "",
                "started_at": 4300.0,
                "completed_at": 4600.0,
                "duration_seconds": 300.0,
            },
        },
        "resume_config": {"max_retries": 2, "retry_delay_seconds": 1.0, "auto_retry_on_resume": True},
        "started_at": 4000.0,
        "completed_at": 4600.0,
        "manifest_path": str(tmp_path / "failed.manifest.json"),
        "quality_summary": None,
        "smoke_test": False,
        "git_ref": "",
    })


@pytest.fixture
def smoke_test_manifest(tmp_path: Path) -> Path:
    """A smoke-test manifest."""
    return _write_manifest(tmp_path / "smoke.manifest.json", {
        "run_id": "mno345",
        "chapter_title": "Smoke Chapter",
        "source_text_hash": "eeffgghh",
        "total_segments": 3,
        "status": "completed",
        "segments": {
            f"seg_{i}": {
                "segment_id": f"seg_{i}",
                "status": "completed",
                "retry_count": 0,
                "error_message": "",
                "polished_text": "",
                "started_at": 5000.0 + i,
                "completed_at": 5100.0 + i,
                "duration_seconds": 100.0,
            }
            for i in range(1, 4)
        },
        "resume_config": {"max_retries": 2, "retry_delay_seconds": 1.0, "auto_retry_on_resume": True},
        "started_at": 5000.0,
        "completed_at": 5400.0,
        "manifest_path": str(tmp_path / "smoke.manifest.json"),
        "quality_summary": None,
        "smoke_test": True,
        "git_ref": "main @ abc1234",
    })


# ── Artifact discovery ────────────────────────────────────────────────────────


class TestFindArtifacts:
    def test_basic_source_stem(self):
        """Path derivation for a typical source name."""
        artifacts = find_artifacts("ch1131_v1")
        assert artifacts.source == Path("data/source/ch1131_v1.txt")
        assert artifacts.output == Path("data/exports/ch1131_v1_en.md")
        assert artifacts.manifest == Path("data/exports/ch1131_v1_en.manifest.json")
        assert artifacts.inspection_record == Path("data/exports/ch1131_v1_inspection.md")

    def test_source_stem_with_hyphens(self):
        """Source names with hyphens work correctly."""
        artifacts = find_artifacts("ch-asc-01")
        assert artifacts.source == Path("data/source/ch-asc-01.txt")
        assert artifacts.output == Path("data/exports/ch-asc-01_en.md")

    def test_source_stem_with_underscores(self):
        """Source names with underscores work correctly."""
        artifacts = find_artifacts("my_chapter_03")
        assert artifacts.source == Path("data/source/my_chapter_03.txt")
        assert artifacts.output == Path("data/exports/my_chapter_03_en.md")

    def test_artifact_object_type(self):
        """find_artifacts returns a ChapterArtifacts instance."""
        artifacts = find_artifacts("test")
        assert isinstance(artifacts, ChapterArtifacts)


# ── Manifest loading ─────────────────────────────────────────────────────────


class TestLoadManifest:
    def test_loads_completed_manifest(self, completed_manifest: Path):
        """Load a COMPLETED manifest with passing quality gate."""
        summary = load_manifest(completed_manifest)
        assert summary.present is True
        assert summary.status == "completed"
        assert summary.run_id == "abc123"
        assert summary.chapter_title == "Test Chapter"
        assert summary.quality_passed is True
        assert summary.quality_error_count == 0
        assert summary.total_segments == 5
        assert summary.completed_segments == 5
        assert summary.failed_segments == 0
        assert summary.smoke_test is False
        assert summary.git_ref == "main @ abc1234"

    def test_loads_failed_quality_manifest(self, failed_quality_manifest: Path):
        """Load a COMPLETED manifest with failed quality gate."""
        summary = load_manifest(failed_quality_manifest)
        assert summary.present is True
        assert summary.quality_passed is False
        assert summary.quality_error_count == 2
        assert summary.quality_warning_count == 1
        assert summary.quality_codes == ["cjk_residue", "placeholder_leak"]

    def test_loads_partial_manifest(self, partial_manifest: Path):
        """Load a PARTIAL manifest."""
        summary = load_manifest(partial_manifest)
        assert summary.present is True
        assert summary.status == "partial"
        assert summary.total_segments == 4
        assert summary.completed_segments == 2
        assert summary.failed_segments == 1
        assert summary.pending_segments == 1

    def test_loads_failed_manifest(self, failed_manifest: Path):
        """Load a FAILED manifest with no quality_summary."""
        summary = load_manifest(failed_manifest)
        assert summary.present is True
        assert summary.status == "failed"
        assert summary.quality_passed is None
        assert summary.total_segments == 2
        assert summary.completed_segments == 0
        assert summary.failed_segments == 2

    def test_loads_smoke_test_manifest(self, smoke_test_manifest: Path):
        """Load a smoke-test manifest."""
        summary = load_manifest(smoke_test_manifest)
        assert summary.present is True
        assert summary.smoke_test is True

    def test_missing_manifest(self):
        """Loading a non-existent manifest returns present=False."""
        summary = load_manifest(Path("/nonexistent/manifest.json"))
        assert summary.present is False

    def test_corrupt_manifest(self, tmp_path: Path):
        """Loading a corrupt JSON file returns present=False."""
        bad_path = tmp_path / "garbage.json"
        bad_path.write_text("this is not json", encoding="utf-8")
        summary = load_manifest(bad_path)
        assert summary.present is False

    def test_manifest_without_quality(self, tmp_path: Path):
        """A manifest with no quality_summary field handles gracefully."""
        path = _write_manifest(tmp_path / "no_quality.manifest.json", {
            "run_id": "xyz789",
            "chapter_title": "",
            "source_text_hash": "",
            "total_segments": 1,
            "status": "completed",
            "segments": {},
            "resume_config": {
                "max_retries": 2, "retry_delay_seconds": 1.0, "auto_retry_on_resume": True,
            },
            "started_at": None,
            "completed_at": None,
            "manifest_path": str(tmp_path / "no_quality.manifest.json"),
            "smoke_test": False,
            "git_ref": "",
        })
        summary = load_manifest(path)
        assert summary.present is True
        assert summary.quality_passed is None


# ── Next-step guidance ────────────────────────────────────────────────────────


class TestSuggestNextStep:
    def test_no_manifest(self):
        """No manifest → suggest 'run'."""
        summary = ManifestSummary(present=False)
        step = suggest_next_step(summary)
        assert step.action == "run"
        assert "not been translated" in step.message

    def test_smoke_test(self):
        """Smoke test → suggest 'inspect' with note that it's mock."""
        summary = ManifestSummary(present=True, status="completed", smoke_test=True)
        step = suggest_next_step(summary)
        assert step.action == "inspect"
        assert "smoke test" in step.message.lower()

    def test_completed_quality_passed(self):
        """COMPLETED + quality passed → suggest 'inspect'."""
        summary = ManifestSummary(
            present=True, status="completed", quality_passed=True,
            total_segments=6, completed_segments=6,
        )
        step = suggest_next_step(summary)
        assert step.action == "inspect"
        assert "Proceed to Step 4" in step.message

    def test_completed_quality_failed(self):
        """COMPLETED + quality FAILED → suggest 'review_quality'."""
        summary = ManifestSummary(
            present=True, status="completed", quality_passed=False,
            quality_error_count=3, quality_codes=["cjk_residue"],
        )
        step = suggest_next_step(summary)
        assert step.action == "review_quality"
        assert "FAILED" in step.message

    def test_completed_quality_not_run(self):
        """COMPLETED + quality not run → suggest 'inspect'."""
        summary = ManifestSummary(
            present=True, status="completed", quality_passed=None,
            total_segments=4, completed_segments=4,
        )
        step = suggest_next_step(summary)
        assert step.action == "inspect"
        assert "quality gate not run" in step.message.lower()

    def test_partial(self):
        """PARTIAL → suggest 'resume'."""
        summary = ManifestSummary(
            present=True, status="partial",
            total_segments=5, completed_segments=3, failed_segments=2,
        )
        step = suggest_next_step(summary)
        assert step.action == "resume"
        assert "--resume" in str(step.commands)

    def test_failed(self):
        """FAILED → suggest 'capture'."""
        summary = ManifestSummary(
            present=True, status="failed",
            total_segments=2, completed_segments=0, failed_segments=2,
        )
        step = suggest_next_step(summary)
        assert step.action == "capture"
        assert "capture" in step.message.lower()


# ── Format output ─────────────────────────────────────────────────────────────


class TestFormatInspectionGuide:
    def test_no_manifest(self):
        """Format output for a source with no manifest."""
        artifacts = find_artifacts("new_chapter")
        summary = ManifestSummary(present=False)
        output = format_inspection_guide(artifacts, summary)
        assert "Validation Helper" in output
        assert "No manifest found" in output
        assert "data/source/new_chapter.txt" in output
        assert "data/exports/new_chapter_en.md" in output

    def test_completed_manifest(self, completed_manifest: Path):
        """Format output for a completed run."""
        artifacts = find_artifacts("test_chapter")
        summary = load_manifest(completed_manifest)
        output = format_inspection_guide(artifacts, summary)
        assert "COMPLETED" in output
        assert "passed" in output
        assert "Proceed to Step 4" in output

    def test_failed_quality(self, failed_quality_manifest: Path):
        """Format output for failed quality gate."""
        artifacts = find_artifacts("bad_chapter")
        summary = load_manifest(failed_quality_manifest)
        output = format_inspection_guide(artifacts, summary)
        assert "FAILED" in output
        assert "cjk_residue" in output
        assert "placeholder_leak" in output

    def test_smoke_test(self, smoke_test_manifest: Path):
        """Format output for a smoke-test run."""
        artifacts = find_artifacts("smoke_chapter")
        summary = load_manifest(smoke_test_manifest)
        output = format_inspection_guide(artifacts, summary)
        assert "SKIPPED (smoke test)" in output
        assert "YES" in output

    def test_dynamic_artifact_checkmarks(self, tmp_path: Path):
        """Existing files are marked with ✓, missing with —."""
        # Create just the source file
        source_dir = Path("data/source")
        source_dir.mkdir(parents=True, exist_ok=True)
        source_file = source_dir / "existing.txt"
        source_file.write_text("test", encoding="utf-8")

        try:
            artifacts = ChapterArtifacts(
                source=source_file,
                output=Path("data/exports/nonexistent_en.md"),
                manifest=Path("data/exports/nonexistent_en.manifest.json"),
                inspection_record=Path("data/exports/nonexistent_inspection.md"),
            )
            summary = ManifestSummary(present=False)
            output = format_inspection_guide(artifacts, summary)
            assert "✓" in output
        finally:
            source_file.unlink()
