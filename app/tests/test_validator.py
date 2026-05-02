"""Tests for pre-run validation guardrails (Stage 4).

Covers all checks in app/chapter/validator.py:
- Source file validity (exists, not a directory, empty, bad encoding)
- Quality sample guard
- Book memory existence
- Dry-run advisory
- Git ref resolution
- Combined validation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import patch
import pytest
from pathlib import Path

from app.chapter.validator import (
    ValidationResult,
    _check_source,
    _check_quality_sample,
    _check_book_memory,
    _check_dry_run_advisory,
    resolve_git_ref,
    validate_chapter_run,
)


# ── ValidationResult ─────────────────────────────────────────────────────────


def test_validation_result_passed_no_errors():
    r = ValidationResult()
    assert r.passed is True


def test_validation_result_passed_with_warnings():
    r = ValidationResult(warnings=["warning"])
    assert r.passed is True


def test_validation_result_failed_with_errors():
    r = ValidationResult(errors=["error"])
    assert r.passed is False


def test_validation_result_has_output():
    assert ValidationResult(errors=["e"]).has_output() is True
    assert ValidationResult(warnings=["w"]).has_output() is True
    assert ValidationResult().has_output() is False


def test_validation_result_format_lines():
    r = ValidationResult(errors=["e1"], warnings=["w1"])
    lines = r.format_lines()
    assert "Pre-run validation:" in lines[0]
    assert "Error: e1" in lines[1]


# ── _check_source ────────────────────────────────────────────────────────────


def test_check_source_missing_file():
    errors, warnings = _check_source(Path("/nonexistent/path.txt"))
    assert len(errors) == 1
    assert "not found" in errors[0]


def test_check_source_is_directory(tmp_path):
    d = tmp_path / "a_directory"
    d.mkdir()
    errors, warnings = _check_source(d)
    assert len(errors) == 1
    assert "not a file" in errors[0]


def test_check_source_empty_file(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    errors, warnings = _check_source(f)
    assert len(errors) == 1
    assert "empty" in errors[0]


def test_check_source_whitespace_only(tmp_path):
    f = tmp_path / "whitespace.txt"
    f.write_text("   \n  \n  ", encoding="utf-8")
    errors, warnings = _check_source(f)
    assert len(errors) == 1
    assert "empty" in errors[0]


def test_check_source_bad_encoding(tmp_path):
    f = tmp_path / "bad.txt"
    f.write_bytes(b"\xff\xfe\x00\xff")
    errors, warnings = _check_source(f)
    assert len(errors) == 1
    assert "UTF-8" in errors[0]


def test_check_source_valid_file(tmp_path):
    f = tmp_path / "valid.txt"
    f.write_text("第一章\n\nContent.", encoding="utf-8")
    errors, warnings = _check_source(f)
    assert errors == []
    assert warnings == []


def test_check_source_non_ascii_valid(tmp_path):
    f = tmp_path / "chinese.txt"
    f.write_text("秦老太太叫住了她。", encoding="utf-8")
    errors, warnings = _check_source(f)
    assert errors == []
    assert warnings == []


# ── _check_quality_sample ────────────────────────────────────────────────────


def test_quality_sample_matches(tmp_path):
    f = tmp_path / "one_chapter_quality_source.txt"
    f.write_text("content", encoding="utf-8")
    warnings = _check_quality_sample(f)
    assert len(warnings) == 1
    assert "quality sample" in warnings[0]


def test_quality_sample_other_file(tmp_path):
    f = tmp_path / "chapter_03.txt"
    f.write_text("content", encoding="utf-8")
    warnings = _check_quality_sample(f)
    assert warnings == []


def test_quality_sample_other_name(tmp_path):
    f = tmp_path / "random.txt"
    f.write_text("content", encoding="utf-8")
    warnings = _check_quality_sample(f)
    assert warnings == []


# ── _check_book_memory ───────────────────────────────────────────────────────


def test_book_memory_none():
    assert _check_book_memory(None) == []


def test_book_memory_exists(tmp_path):
    f = tmp_path / "memory.json"
    f.write_text("{}", encoding="utf-8")
    assert _check_book_memory(f) == []


def test_book_memory_missing(tmp_path):
    f = tmp_path / "missing.json"
    errors = _check_book_memory(f)
    assert len(errors) == 1
    assert "not found" in errors[0]


def test_book_memory_is_directory(tmp_path):
    d = tmp_path / "a_dir"
    d.mkdir()
    errors = _check_book_memory(d)
    assert len(errors) == 1
    assert "not a file" in errors[0]


# ── _check_dry_run_advisory ──────────────────────────────────────────────────


def test_dry_run_advisory_skipped_on_dry_run(tmp_path):
    f = tmp_path / "chapter.txt"
    f.write_text("content", encoding="utf-8")
    warnings = _check_dry_run_advisory(f, is_dry_run=True, is_resume=False)
    assert warnings == []


def test_dry_run_advisory_skipped_on_resume(tmp_path):
    f = tmp_path / "chapter.txt"
    f.write_text("content", encoding="utf-8")
    warnings = _check_dry_run_advisory(f, is_dry_run=False, is_resume=True)
    assert warnings == []


def test_dry_run_advisory_new_source(tmp_path):
    f = tmp_path / "new_chapter.txt"
    f.write_text("content", encoding="utf-8")
    warnings = _check_dry_run_advisory(f, is_dry_run=False, is_resume=False)
    assert len(warnings) == 1
    assert "dry-run" in warnings[0]


# ── resolve_git_ref ──────────────────────────────────────────────────────────


def test_resolve_git_ref_in_repo():
    """Should return a non-empty string when called inside a git repo."""
    ref = resolve_git_ref()
    assert ref is not None
    assert "@" in ref
    assert len(ref) > 5


def test_resolve_git_ref_outside_repo(tmp_path):
    """Should return None when called outside a git repo."""
    ref = resolve_git_ref(project_root=tmp_path)
    assert ref is None


def test_resolve_git_ref_git_failure():
    """Should return None when git command fails."""
    with patch("subprocess.run", side_effect=FileNotFoundError("no git")):
        ref = resolve_git_ref()
        assert ref is None


# ── validate_chapter_run (integration) ───────────────────────────────────────


def test_validate_chapter_run_valid(tmp_path):
    source = tmp_path / "chapter_01.txt"
    source.write_text("第一章\n\n内容。", encoding="utf-8")
    result = validate_chapter_run(source)
    assert result.passed is True


def test_validate_chapter_run_missing_source(tmp_path):
    result = validate_chapter_run(tmp_path / "missing.txt")
    assert result.passed is False
    assert any("not found" in e for e in result.errors)


def test_validate_chapter_run_empty_source(tmp_path):
    source = tmp_path / "empty.txt"
    source.write_text("", encoding="utf-8")
    result = validate_chapter_run(source)
    assert result.passed is False
    assert any("empty" in e for e in result.errors)


def test_validate_chapter_run_bad_encoding(tmp_path):
    source = tmp_path / "bad.txt"
    source.write_bytes(b"\xff\xfe\x00\xff")
    result = validate_chapter_run(source)
    assert result.passed is False
    assert any("UTF-8" in e for e in result.errors)


def test_validate_chapter_run_quality_sample_warning(tmp_path):
    source = tmp_path / "one_chapter_quality_source.txt"
    source.write_text("第一章\n\n内容。", encoding="utf-8")
    result = validate_chapter_run(source)
    assert result.passed is True  # warnings don't block
    assert any("quality sample" in w for w in result.warnings)


def test_validate_chapter_run_dry_run_advisory(tmp_path):
    source = tmp_path / "new_chapter.txt"
    source.write_text("第一章\n\n内容。", encoding="utf-8")
    result = validate_chapter_run(source)
    assert result.passed is True
    assert any("dry-run" in w for w in result.warnings)


def test_validate_chapter_run_no_dry_run_advisory_on_dry_run(tmp_path):
    source = tmp_path / "new_chapter.txt"
    source.write_text("第一章\n\n内容。", encoding="utf-8")
    result = validate_chapter_run(source, is_dry_run=True)
    assert result.passed is True
    assert not any("dry-run" in w for w in result.warnings)


def test_validate_chapter_run_book_memory_missing(tmp_path):
    source = tmp_path / "chapter.txt"
    source.write_text("第一章\n\n内容。", encoding="utf-8")
    bm = tmp_path / "no_such_file.json"
    result = validate_chapter_run(source, book_memory_path=bm)
    assert result.passed is False
    assert any("not found" in e for e in result.errors)


def test_validate_chapter_run_passes_git_ref(tmp_path):
    """Smoke test: valid source + valid book memory = clean pass."""
    source = tmp_path / "chapter_03.txt"
    source.write_text("第一章\n\n内容。", encoding="utf-8")
    bm = tmp_path / "memory.json"
    bm.write_text("{}", encoding="utf-8")
    result = validate_chapter_run(source, book_memory_path=bm, is_dry_run=True)
    assert result.passed is True
    assert result.errors == []
    assert result.warnings == []


def test_validate_chapter_run_output_path_reserved(tmp_path):
    """Output path parameter is reserved for future checks."""
    source = tmp_path / "chapter.txt"
    source.write_text("内容。", encoding="utf-8")
    result = validate_chapter_run(source, output_path=tmp_path / "out.md")
    assert result.passed is True
