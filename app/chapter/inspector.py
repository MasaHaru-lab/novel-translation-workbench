"""Phase C Stage 5 validation helper: artifact discovery, manifest readback,
and next-step guidance for the real-sample validation workflow.

This is a thin operator-facing layer that reduces manual copy/paste by:

- Finding and displaying all artifact paths (source, output, manifest, inspection template)
- Reading and summarizing the run manifest (status, quality, segments, git ref)
- Providing next-step guidance based on manifest status + quality gate

It does NOT modify the orchestrator, quality gate, manifests, or prompts.
It does NOT run translations or quality checks — it reads what already exists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from app.chapter.manifest import RunManifest
from app.config_loader import find_project_root

# ── Project root-relative path constants ──────────────────────────────────────
_PROJECT_ROOT = find_project_root()
SOURCE_DIR = _PROJECT_ROOT / "data/source"
EXPORT_DIR = _PROJECT_ROOT / "data/exports"
TEMPLATE_PATH = _PROJECT_ROOT / "docs/templates/INSPECTION_RECORD_TEMPLATE.md"


@dataclass
class ChapterArtifacts:
    """Resolved paths for a single chapter validation run."""

    source: Path
    """Path to the source text file (e.g. data/source/ch1131_v1.txt)."""

    output: Path
    """Path to the translated output file (e.g. data/exports/ch1131_v1_en.md)."""

    manifest: Path
    """Path to the run manifest (e.g. data/exports/ch1131_v1_en.manifest.json)."""

    inspection_record: Path
    """Path to the inspection record (e.g. data/exports/ch1131_v1_inspection.md)."""


@dataclass
class ManifestSummary:
    """Human-readable summary of a loaded RunManifest."""

    present: bool
    """True when a manifest file exists and was successfully loaded."""

    run_id: str = ""
    chapter_title: str = ""
    status: str = ""
    quality_passed: Optional[bool] = None
    quality_error_count: int = 0
    quality_warning_count: int = 0
    quality_codes: List[str] = field(default_factory=list)
    total_segments: int = 0
    completed_segments: int = 0
    failed_segments: int = 0
    pending_segments: int = 0
    smoke_test: bool = False
    git_ref: str = ""


@dataclass
class NextStep:
    """Suggested operator action based on manifest state."""

    action: str
    """One of 'inspect', 'resume', 'capture', 'run', or 'review_quality'."""

    message: str
    """Human-readable guidance message."""

    commands: List[str] = field(default_factory=list)
    """Suggested CLI commands to execute."""


# ── Artifact discovery ───────────────────────────────────────────────────────


def find_artifacts(source_stem: str) -> ChapterArtifacts:
    """Resolve all artifact paths for a chapter from its source filename stem.

    The stem is the source filename without extension
    (e.g. ``"ch1131_v1"`` from ``"ch1131_v1.txt"``).

    Path convention (from PHASE_C_PRODUCTION_WORKFLOW.md §7):
        data/source/<stem>.txt       → source
        data/exports/<stem>_en.md    → output
        data/exports/<stem>_en.manifest.json → manifest
        data/exports/<stem>_inspection.md   → inspection record
    """
    return ChapterArtifacts(
        source=SOURCE_DIR / f"{source_stem}.txt",
        output=EXPORT_DIR / f"{source_stem}_en.md",
        manifest=EXPORT_DIR / f"{source_stem}_en.manifest.json",
        inspection_record=EXPORT_DIR / f"{source_stem}_inspection.md",
    )


# ── Manifest readback ────────────────────────────────────────────────────────


def load_manifest(manifest_path: Path) -> ManifestSummary:
    """Load a RunManifest from disk and return a human-readable summary.

    Returns a ``ManifestSummary`` with ``present=False`` when the manifest
    file does not exist or cannot be loaded.
    """
    if not manifest_path.exists():
        return ManifestSummary(present=False)

    try:
        manifest = RunManifest.load(str(manifest_path))
    except Exception:
        return ManifestSummary(present=False)

    seg_summary = manifest.get_summary()
    quality = manifest.quality_summary or {}

    return ManifestSummary(
        present=True,
        run_id=manifest.run_id,
        chapter_title=manifest.chapter_title,
        status=seg_summary["status"],
        quality_passed=quality.get("passed"),
        quality_error_count=quality.get("error_count", 0),
        quality_warning_count=quality.get("warning_count", 0),
        quality_codes=quality.get("codes", []),
        total_segments=seg_summary["total_segments"],
        completed_segments=seg_summary["completed"],
        failed_segments=seg_summary["failed"],
        pending_segments=seg_summary["pending"],
        smoke_test=manifest.smoke_test,
        git_ref=manifest.git_ref,
    )


# ── Next-step guidance ───────────────────────────────────────────────────────


def suggest_next_step(summary: ManifestSummary) -> NextStep:
    """Determine the suggested next operator action from the manifest summary.

    Decision matrix (from PHASE_C_PRODUCTION_WORKFLOW.md §6.1 Step 5):

        | Manifest status | Quality gate      | Suggested action |
        |-----------------|-------------------|------------------|
        | COMPLETED       | passed            | inspect          |
        | COMPLETED       | failed / N/A      | review_quality   |
        | PARTIAL         | passed / failed   | resume           |
        | FAILED          | N/A               | capture          |
        | no manifest     | N/A               | run              |
        | smoke test      | N/A               | inspect (mock)   |
    """
    if not summary.present:
        return NextStep(
            action="run",
            message="No run manifest found. The chapter has not been translated yet.",
            commands=["venv/bin/python -m app.cli chapter run --dry-run --source data/source/<name>.txt"],
        )

    if summary.smoke_test:
        return NextStep(
            action="inspect",
            message=(
                "Last run was a smoke test (mock translation, not real model output). "
                "The output is not a real translation. Run without --smoke-test for a real translation."
            ),
        )

    status = summary.status.upper()

    if status == "COMPLETED":
        if summary.quality_passed is False:
            return NextStep(
                action="review_quality",
                message=(
                    f"Chapter completed but quality gate FAILED "
                    f"({summary.quality_error_count} error(s): "
                    f"{', '.join(summary.quality_codes)}). "
                    "Review quality issues before inspection."
                ),
            )
        if summary.quality_passed is True:
            return NextStep(
                action="inspect",
                message=(
                    "Chapter completed and quality gate passed. "
                    "Proceed to Step 4 (Inspect). Create an inspection record "
                    "and compare output against source passage by passage."
                ),
                commands=[
                    f"cp {TEMPLATE_PATH} data/exports/<stem>_inspection.md",
                ],
            )
        # quality_passed is None (quality gate was not run)
        return NextStep(
            action="inspect",
            message=(
                "Chapter completed (quality gate not run). "
                "Proceed to Step 4 (Inspect)."
            ),
        )

    if status == "PARTIAL":
        return NextStep(
            action="resume",
            message=(
                f"Chapter is PARTIAL ({summary.completed_segments}/"
                f"{summary.total_segments} segments completed). "
                "Run with --resume to continue."
            ),
            commands=[
                "venv/bin/python -m app.cli chapter run --resume --source data/source/<name>.txt",
            ],
        )

    if status == "FAILED":
        return NextStep(
            action="capture",
            message=(
                "All segments failed. Capture the chapter state for investigation "
                "using the bad-case capture template."
            ),
            commands=[
                f"cp docs/templates/BAD_CASE_CAPTURE_TEMPLATE.md data/captures/<name>/capture_note.md",
            ],
        )

    # Fallback: unknown status
    return NextStep(
        action="run",
        message=f"Manifest has unexpected status {status!r}. Consider re-running.",
    )


# ── CLI-friendly output ──────────────────────────────────────────────────────


def format_inspection_guide(artifacts: ChapterArtifacts, summary: ManifestSummary) -> str:
    """Format a human-readable validation helper summary for CLI output."""
    lines: List[str] = []
    lines.append("")
    lines.append("Phase C Stage 5 — Validation Helper")
    lines.append("=" * 40)

    # ── Artifact paths ──────────────────────────────────────────────────
    lines.append("")
    lines.append("Artifact Paths")
    lines.append("-" * 40)
    pairs = [
        ("Source", artifacts.source),
        ("Output", artifacts.output),
        ("Manifest", artifacts.manifest),
        ("Inspection", artifacts.inspection_record),
        ("Template", TEMPLATE_PATH),
    ]
    for label, path in pairs:
        exists = "✓" if path.exists() else "—"
        lines.append(f"  {label:12s}  {path}  {exists}")

    # ── Manifest summary ────────────────────────────────────────────────
    lines.append("")
    lines.append("Manifest Summary")
    lines.append("-" * 40)
    if not summary.present:
        lines.append("  No manifest found — chapter has not been translated yet.")
    else:
        lines.append(f"  Status:        {summary.status.upper()}")
        if summary.chapter_title:
            lines.append(f"  Chapter:       {summary.chapter_title}")
        lines.append(f"  Segments:      {summary.completed_segments}/{summary.total_segments}")
        quality_label = _format_quality_label(summary)
        lines.append(f"  Quality:       {quality_label}")
        lines.append(f"  Smoke test:    {'YES' if summary.smoke_test else 'NO'}")
        if summary.git_ref:
            lines.append(f"  Git ref:       {summary.git_ref}")

    # ── Next-step guidance ──────────────────────────────────────────────
    lines.append("")
    lines.append("Next Step")
    lines.append("-" * 40)
    step = suggest_next_step(summary)
    lines.append(f"  {step.message}")
    for cmd in step.commands:
        lines.append(f"    $ {cmd}")
    if step.commands:
        lines.append("")

    return "\n".join(lines)


def _format_quality_label(summary: ManifestSummary) -> str:
    """Format the quality gate result as a short label string."""
    if summary.smoke_test:
        return "SKIPPED (smoke test)"
    if summary.quality_passed is None:
        return "not run"
    if summary.quality_passed:
        if summary.quality_warning_count > 0:
            return f"passed ({summary.quality_warning_count} warning(s))"
        return "passed"
    return (
        f"FAILED — {summary.quality_error_count} error(s) "
        f"[{', '.join(summary.quality_codes)}]"
    )
