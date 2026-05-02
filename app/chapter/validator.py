"""Pre-run validation guardrails for chapter-level translation runs.

Stage 4 checks, all deterministic and offline:
- Source file validity (exists, readable, non-empty, valid UTF-8)
- Protected source detection (approved quality sample)
- Book memory file existence
- Dry-run advisory for new sources
- Git ref resolution for run traceability
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from app.config_loader import find_project_root


APPROVED_QUALITY_SAMPLE = "data/source/one_chapter_quality_source.txt"
"""Path of the approved quality sample, relative to project root."""


@dataclass
class ValidationResult:
    """Result of a pre-run validation check."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when no hard errors were found."""
        return len(self.errors) == 0

    def has_output(self) -> bool:
        """True when there are errors or warnings to report."""
        return bool(self.errors) or bool(self.warnings)

    def format_lines(self) -> List[str]:
        """Return formatted output lines for the CLI.

        Hard errors first, then warnings. Each line starts with a
        two-space indent and a symbol for quick visual scanning.
        """
        lines: List[str] = []
        if self.errors:
            lines.append("Pre-run validation:")
            for e in self.errors:
                lines.append(f"  Error: {e}")
        if self.warnings:
            if not self.errors:
                lines.append("Pre-run validation:")
            for w in self.warnings:
                lines.append(f"  Warning: {w}")
        return lines


def _check_source(source_path: Path) -> Tuple[List[str], List[str]]:
    """Check source file validity: exists, is file, valid UTF-8, non-empty.

    Returns (errors, warnings). On fatal issues (not found, not a file,
    bad encoding), returns early with no further checks.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not source_path.exists():
        errors.append(f"Source file not found: {source_path}")
        return errors, warnings

    if not source_path.is_file():
        errors.append(f"Source path is not a file: {source_path}")
        return errors, warnings

    try:
        text = source_path.read_bytes()
    except Exception as exc:
        errors.append(f"Cannot read source file {source_path}: {exc}")
        return errors, warnings

    try:
        decoded = text.decode("utf-8")
    except UnicodeDecodeError:
        errors.append(f"Source file is not valid UTF-8: {source_path}")
        return errors, warnings

    if not decoded.strip():
        errors.append(f"Source file is empty: {source_path}")

    return errors, warnings


def _check_quality_sample(source_path: Path) -> List[str]:
    """Check if the source is the approved quality sample.

    Returns warnings when the sample is being run outside a quality-loop
    context. The operator can still proceed — the warning is advisory.
    """
    try:
        if source_path.resolve().name == "one_chapter_quality_source.txt":
            return [
                f"Source is the approved quality sample "
                f"({APPROVED_QUALITY_SAMPLE}). This file is reserved "
                f"for quality-loop runs and validation."
            ]
    except (OSError, ValueError):
        pass
    return []


def _check_book_memory(book_memory_path: Optional[Path]) -> List[str]:
    """Check that the book memory file exists if one was declared.

    Returns errors when the file is missing or not a regular file.
    """
    if book_memory_path is None:
        return []
    if not book_memory_path.exists():
        return [f"Book memory file not found: {book_memory_path}"]
    if not book_memory_path.is_file():
        return [f"Book memory path is not a file: {book_memory_path}"]
    return []


def _check_dry_run_advisory(
    source_path: Path,
    is_dry_run: bool,
    is_resume: bool,
) -> List[str]:
    """Suggest a dry-run for new sources that have never been translated.

    The heuristic is simple: if no manifest exists at the default path
    for this source, the source is new and a dry-run would be useful.
    """
    if is_dry_run or is_resume:
        return []

    default_manifest = (
        find_project_root() / "data/exports" / f"{source_path.stem}_en.manifest.json"
    )
    if not default_manifest.exists():
        return [
            f"No previous run found for {source_path.name}. "
            f"Consider running with --dry-run first to preview "
            f"the chapter plan."
        ]
    return []


def validate_chapter_run(
    source_path: Path,
    output_path: Optional[Path] = None,
    book_memory_path: Optional[Path] = None,
    is_dry_run: bool = False,
    is_resume: bool = False,
) -> ValidationResult:
    """Run all pre-run validation checks for a chapter translation.

    Checks are ordered so that early failures (missing source) prevent
    cascading downstream checks that depend on the source file.

    Args:
        source_path: Path to the source text file.
        output_path: Path to the output file (reserved for future checks).
        book_memory_path: Path to a BookMemory JSON file, if any.
        is_dry_run: True if the run is a dry-run (skips dry-run advisory).
        is_resume: True if the run is a resume (skips dry-run advisory).

    Returns:
        A ValidationResult with errors (blockers) and warnings (advisories).
    """
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Source file checks (exists, readable, non-empty, valid UTF-8).
    src_errors, src_warnings = _check_source(source_path)
    errors.extend(src_errors)
    warnings.extend(src_warnings)

    # 2. Quality sample guard — only check if source is usable.
    if not errors:
        warnings.extend(_check_quality_sample(source_path))

    # 3. Book memory file existence (if declared).
    errors.extend(_check_book_memory(book_memory_path))

    # 4. Dry-run advisory for new sources.
    if not errors:
        warnings.extend(_check_dry_run_advisory(
            source_path, is_dry_run, is_resume,
        ))

    return ValidationResult(errors=errors, warnings=warnings)


def resolve_git_ref(project_root: Optional[Path] = None) -> Optional[str]:
    """Resolve the current git branch and short commit hash.

    Returns a string like ``"main @ abc1234"``, or ``None`` if not
    inside a git repository or if git is unavailable.

    This is best-effort: failures are silent so that translation runs
    are never blocked on git metadata.
    """
    try:
        cwd = str(project_root) if project_root else None
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=5,
        )
        if branch.returncode == 0 and commit.returncode == 0:
            b = branch.stdout.strip()
            c = commit.stdout.strip()
            if b and c:
                return f"{b} @ {c}"
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return None
