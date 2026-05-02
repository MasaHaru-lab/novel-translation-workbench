"""Report-only workspace hygiene checker.

Classifies dirty / untracked / gitignored files into categories and
produces a readable operator-facing report with recommendations.
This is v1 — report only. No cleanup automation.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional


# ── Classification ──────────────────────────────────────────────────────────

FILE_CATEGORY_PROJECT_CHANGE = "project_change"
FILE_CATEGORY_PROJECT_HOOK = "project_hook"
FILE_CATEGORY_SAMPLE_INPUT = "sample_input"
FILE_CATEGORY_GENERATED_OUTPUT = "generated_output"
FILE_CATEGORY_RUNTIME_JUNK = "runtime_junk"
FILE_CATEGORY_LOCAL_CONFIG = "local_config"
FILE_CATEGORY_UNKNOWN = "unknown"

# Mapping from internal category to display label
_CATEGORY_LABELS = {
    FILE_CATEGORY_PROJECT_CHANGE: "project-change",
    FILE_CATEGORY_PROJECT_HOOK: "project-hook",
    FILE_CATEGORY_SAMPLE_INPUT: "sample-input",
    FILE_CATEGORY_GENERATED_OUTPUT: "generated-output",
    FILE_CATEGORY_RUNTIME_JUNK: "runtime-junk",
    FILE_CATEGORY_LOCAL_CONFIG: "local-config",
    FILE_CATEGORY_UNKNOWN: "unknown",
}


def _category_label(cat: str) -> str:
    return _CATEGORY_LABELS.get(cat, cat)


@dataclass
class FileEntry:
    """A single file found by the hygiene scan."""

    path: Path
    status_code: str  # git status code: "M" (modified tracked), "??" (untracked),
    # "--" (ignored)
    category: str
    explanation: str
    recommendation: str


@dataclass
class HygieneReport:
    """Full workspace hygiene report."""

    entries: List[FileEntry] = field(default_factory=list)

    @property
    def summary(self) -> str:
        by_cat: dict[str, int] = {}
        for e in self.entries:
            by_cat[e.category] = by_cat.get(e.category, 0) + 1
        parts = []
        for cat in sorted(by_cat):
            parts.append(f"{by_cat[cat]} {cat}")
        return ", ".join(parts) if parts else "clean"

    def print_report(self, file=None) -> None:
        if file is None:
            file = sys.stdout
        """Print a formatted report to *file*."""
        if not self.entries:
            print("Workspace is clean. No dirty, untracked, or unexpected files.", file=file)
            print("No action needed.", file=file)
            return

        for e in self.entries:
            _tag = _category_label(e.category)
            _path = str(e.path)
            _status = e.status_code
            print(f"[{_tag}] {_path}  ({_status})", file=file)
            print(f"       {e.explanation}", file=file)
            print(f"       → {e.recommendation}", file=file)
            print(file=file)

        print(f"--- Summary: {self.summary} ---", file=file)


# ── Path-pattern helpers ─────────────────────────────────────────────────────

_PROJECT_CHANGE_PATHS = {"CLAUDE.md", ".claude/settings.json"}
_HOOK_PARENT = ".claude/hooks/"
_SAMPLE_PARENT = "data/source/"
_GENERATED_PARENTS = {"data/exports/", "data/output/", "data/samples/", "outputs/"}
_RUNTIME_JUNK_NAMES = {".DS_Store", "__pycache__", ".pytest_cache"}
_RUNTIME_JUNK_SUFFIXES = {".pyc", ".pyo", ".log"}
_LOCAL_CONFIG_PATHS = {".env.local", ".claude/settings.local.json"}


def _path_has_parent(sp: str, parent: str) -> bool:
    """Check if *sp* starts with the given parent path segment."""
    return sp == parent.rstrip("/") or sp.startswith(parent)


# ── Classification ───────────────────────────────────────────────────────────


def _classify(path: Path, status_code: str) -> FileEntry:
    """Classify a single file and return a populated ``FileEntry``.

    Classification priority (first match wins):
      1. Modified tracked project files (CLAUDE.md, .claude/settings.json)
      2. Project hook scripts (.claude/hooks/*)
      3. Sample input sources (data/source/*.txt) — untracked only
      4. Gitignored — generated outputs by known path prefix
      5. Gitignored — runtime junk by name/suffix
      6. Gitignored — local config files
      7. Gitignored — catch-all (any other ignored path)
      8. Untracked (non-ignored) — unknown / needs inspection
      9. Modified tracked — unknown
    """
    sp = str(path)
    is_modified = status_code.startswith("M") or status_code.startswith(" M")
    is_untracked = status_code == "??"
    is_ignored = status_code == "--"

    # ── 1. Modified tracked project files ──────────────────────────────
    if is_modified and sp in _PROJECT_CHANGE_PATHS:
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_PROJECT_CHANGE,
            explanation="Project-level config or rules file for this repo.",
            recommendation="Review diff; commit when stable.",
        )

    # ── 2. Project hooks (.claude/hooks/) ──────────────────────────────
    if _path_has_parent(sp, _HOOK_PARENT):
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_PROJECT_HOOK,
            explanation="Pre/post-tool hook script — project safety guard.",
            recommendation="Commit together with .claude/settings.json.",
        )

    # ── 3. Sample input files (data/source/*.txt) — untracked only ─────
    if is_untracked and sp.startswith(_SAMPLE_PARENT) and sp.endswith(".txt"):
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_SAMPLE_INPUT,
            explanation="Local chapter sample for ad-hoc translation runs.",
            recommendation="Keep local; do not commit. Delete when no longer needed.",
        )

    # ── 4. Generated outputs by known parent path ──────────────────────
    for parent in _GENERATED_PARENTS:
        if _path_has_parent(sp, parent):
            return FileEntry(
                path=path, status_code=status_code,
                category=FILE_CATEGORY_GENERATED_OUTPUT,
                explanation="Generated translation output — produced by pipeline runs. Path is gitignored.",
                recommendation="Verify content; gitignored so no commit needed.",
            )

    # ── 5. Runtime junk by name or suffix ──────────────────────────────
    if sp in _RUNTIME_JUNK_NAMES or any(sp.endswith(sfx) for sfx in _RUNTIME_JUNK_SUFFIXES):
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_RUNTIME_JUNK,
            explanation="Cached / temporary file — safe to delete.",
            recommendation="No action (gitignored or harmless).",
        )
    # Also catch files inside __pycache__ directories
    if "/__pycache__/" in sp or sp.startswith("__pycache__/"):
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_RUNTIME_JUNK,
            explanation="Python bytecode cache — regenerated automatically.",
            recommendation="No action (gitignored).",
        )

    # ── 6. Local config files ──────────────────────────────────────────
    if sp in _LOCAL_CONFIG_PATHS:
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_LOCAL_CONFIG,
            explanation="Local-only configuration (API keys, personal settings). Gitignored.",
            recommendation="Keep local; never commit.",
        )

    # ── 7. Gitignored catch-all ────────────────────────────────────────
    if is_ignored:
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_GENERATED_OUTPUT,
            explanation="Gitignored artifact — generated or cached.",
            recommendation="No action (gitignored).",
        )

    # ── 8. Untracked (non-ignored) fallthrough ─────────────────────────
    if is_untracked:
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_UNKNOWN,
            explanation="Untracked file not matching any known pattern.",
            recommendation="Inspect manually. Add to .gitignore or commit if it belongs.",
        )

    # ── 9. Modified tracked fallthrough ────────────────────────────────
    if is_modified:
        return FileEntry(
            path=path, status_code=status_code,
            category=FILE_CATEGORY_UNKNOWN,
            explanation="Modified tracked file not matching known project files.",
            recommendation="Review diff; decide whether to commit or discard.",
        )

    # ── 10. Edge case ──────────────────────────────────────────────────
    return FileEntry(
        path=path, status_code=status_code,
        category=FILE_CATEGORY_UNKNOWN,
        explanation="File found in scan that does not match expected categories.",
        recommendation="Inspect manually and decide.",
    )


# ── Scan (git-based) ────────────────────────────────────────────────────────


def _run_git(args: List[str], cwd: Optional[Path] = None) -> str:
    """Run a git subcommand and return stdout."""
    cmd = ["git"] + args
    result = subprocess.run(
        cmd,
        capture_output=True, text=True,
        cwd=str(cwd) if cwd else None,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git command {' '.join(cmd)!r} failed: {result.stderr.strip()}"
        )
    return result.stdout


def scan_workspace(project_root: Optional[Path] = None) -> HygieneReport:
    """Scan the workspace and return a classification report.

    Uses three git queries:
      1. ``git status --porcelain -uall`` — modified tracked + untracked (individual files)
      2. ``git ls-files --others --ignored --exclude-standard`` — gitignored files
      3. ``git ls-files --others --exclude-standard`` — untracked non-ignored files
         (backstop for any missed by --porcelain when ``status.showUntrackedFiles`` is set)

    Args:
        project_root: Project root directory. Auto-detects from CWD when None.

    Returns:
        A ``HygieneReport`` with all classified entries.
    """
    root = project_root or Path.cwd()

    entries: List[FileEntry] = []
    seen: set[Path] = set()

    # Phase 1: modified tracked + untracked files via status porcelain
    # Use -uall to avoid directory collapsing.
    porcelain = _run_git(
        ["status", "--porcelain", "-uall"], cwd=root,
    )
    for line in porcelain.splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            continue
        status_code = line[:2].strip()  # normalize "M " -> "M", "??" -> "??"
        if status_code == "R":  # renamed — second column has status
            status_code = line[1:2].strip() or "M"
        file_path_str = line[3:]
        fp = Path(file_path_str)
        seen.add(fp)
        entries.append(_classify(fp, status_code))

    # Phase 2: gitignored files (not already listed)
    ignored_out = _run_git(
        ["ls-files", "--others", "--ignored", "--exclude-standard"], cwd=root,
    )
    for line in ignored_out.splitlines():
        line = line.strip()
        if not line:
            continue
        fp = Path(line)
        if fp in seen:
            continue
        seen.add(fp)
        entries.append(_classify(fp, "--"))

    # Phase 3: untracked non-ignored backstop (files missed by porcelain)
    untracked_out = _run_git(
        ["ls-files", "--others", "--exclude-standard"], cwd=root,
    )
    for line in untracked_out.splitlines():
        line = line.strip()
        if not line:
            continue
        fp = Path(line)
        if fp in seen:
            continue
        seen.add(fp)
        entries.append(_classify(fp, "??"))

    return HygieneReport(entries=entries)
