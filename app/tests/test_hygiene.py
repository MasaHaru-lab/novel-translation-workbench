"""Tests for workspace hygiene reporter."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from app.hygiene.reporter import (
    FILE_CATEGORY_GENERATED_OUTPUT,
    FILE_CATEGORY_LOCAL_CONFIG,
    FILE_CATEGORY_PROJECT_CHANGE,
    FILE_CATEGORY_PROJECT_HOOK,
    FILE_CATEGORY_RUNTIME_JUNK,
    FILE_CATEGORY_SAMPLE_INPUT,
    FILE_CATEGORY_UNKNOWN,
    FileEntry,
    HygieneReport,
    scan_workspace,
    _classify,
)


# ── Helper ───────────────────────────────────────────────────────────────────


def _check(path: str, status: str) -> str:
    """Return the category string for a (path, status) pair."""
    return _classify(Path(path), status).category


# ── Pure classification tests (no git dependency) ───────────────────────────


class TestClassifyModifiedTracked:
    def test_claude_md_staged(self):
        assert _check("CLAUDE.md", "M") == FILE_CATEGORY_PROJECT_CHANGE

    def test_claude_md_unstaged(self):
        assert _check("CLAUDE.md", "M") == FILE_CATEGORY_PROJECT_CHANGE

    def test_settings_json(self):
        assert _check(".claude/settings.json", "M") == FILE_CATEGORY_PROJECT_CHANGE

    def test_unknown_modified_tracked(self):
        assert _check("src/foo.py", "M") == FILE_CATEGORY_UNKNOWN


class TestClassifyHooks:
    def test_new_hook_file(self):
        assert _check(".claude/hooks/check-foo.sh", "??") == FILE_CATEGORY_PROJECT_HOOK

    def test_modified_hook_file(self):
        assert _check(".claude/hooks/check-gstack.sh", "M") == FILE_CATEGORY_PROJECT_HOOK

    def test_ignored_hook_file(self):
        assert _check(".claude/hooks/check-cwd.sh", "--") == FILE_CATEGORY_PROJECT_HOOK


class TestClassifySampleInput:
    def test_chapter_source(self):
        assert _check("data/source/ch1131_v1.txt", "??") == FILE_CATEGORY_SAMPLE_INPUT

    def test_other_txt_source(self):
        assert _check("data/source/foo.txt", "??") == FILE_CATEGORY_SAMPLE_INPUT

    def test_non_txt_in_source_not_sample(self):
        """Non-.txt files under data/source/ are not classified as samples."""
        assert _check("data/source/notes.md", "??") == FILE_CATEGORY_UNKNOWN

    def test_modified_source_not_sample(self):
        """Tracked file under data/source/ that is modified is NOT sample_input."""
        assert _check("data/source/one_chapter_quality_source.txt", "M") == FILE_CATEGORY_UNKNOWN


class TestClassifyGeneratedOutput:
    def test_export_markdown(self):
        assert (
            _check("data/exports/ch1131_v1_en.md", "--")
            == FILE_CATEGORY_GENERATED_OUTPUT
        )

    def test_export_manifest(self):
        assert (
            _check("data/exports/ch1131_v1_en.manifest.json", "--")
            == FILE_CATEGORY_GENERATED_OUTPUT
        )

    def test_data_output(self):
        assert _check("data/output/result.json", "--") == FILE_CATEGORY_GENERATED_OUTPUT

    def test_data_samples(self):
        assert _check("data/samples/test.txt", "--") == FILE_CATEGORY_GENERATED_OUTPUT

    def test_outputs_dir(self):
        assert _check("outputs/run1.json", "--") == FILE_CATEGORY_GENERATED_OUTPUT


class TestClassifyRuntimeJunk:
    def test_pycache_file(self):
        assert _check("__pycache__/foo.cpython-311.pyc", "--") == FILE_CATEGORY_RUNTIME_JUNK

    def test_pycache_nested(self):
        assert _check("app/__pycache__/bar.cpython-311.pyc", "--") == FILE_CATEGORY_RUNTIME_JUNK

    def test_ds_store(self):
        assert _check(".DS_Store", "--") == FILE_CATEGORY_RUNTIME_JUNK

    def test_log_file(self):
        assert _check("adapter.log", "--") == FILE_CATEGORY_RUNTIME_JUNK


class TestClassifyLocalConfig:
    def test_env_local(self):
        assert _check(".env.local", "--") == FILE_CATEGORY_LOCAL_CONFIG

    def test_settings_local_json(self):
        assert (
            _check(".claude/settings.local.json", "--")
            == FILE_CATEGORY_LOCAL_CONFIG
        )


class TestClassifyUntrackedFallthrough:
    def test_unknown_untracked(self):
        assert _check("random_file.json", "??") == FILE_CATEGORY_UNKNOWN

    def test_unknown_dir_file(self):
        assert _check("bridges/foo.yaml", "??") == FILE_CATEGORY_UNKNOWN


class TestClassifyIgnoredFallthrough:
    def test_unknown_ignored_is_generated(self):
        """Any unrecognized gitignored file falls through to generated_output."""
        assert _check(".some-cache.bin", "--") == FILE_CATEGORY_GENERATED_OUTPUT


# ── HygieneReport summary ────────────────────────────────────────────────────


class TestHygieneReport:
    def test_empty_report(self):
        r = HygieneReport(entries=[])
        assert r.summary == "clean"

    def test_single_category(self):
        r = HygieneReport(entries=[
            FileEntry(Path("x.txt"), "??", FILE_CATEGORY_UNKNOWN, "", ""),
        ])
        assert "1 unknown" in r.summary

    def test_multiple_categories(self):
        r = HygieneReport(entries=[
            FileEntry(Path("a"), "??", FILE_CATEGORY_SAMPLE_INPUT, "", ""),
            FileEntry(Path("b"), "M", FILE_CATEGORY_PROJECT_CHANGE, "", ""),
            FileEntry(Path("c"), "--", FILE_CATEGORY_GENERATED_OUTPUT, "", ""),
        ])
        assert "1 sample_input" in r.summary
        assert "1 project_change" in r.summary
        assert "1 generated_output" in r.summary

    def test_summary_clean_reset(self):
        """After a clean workspace is reported, summary is 'clean'."""
        r = HygieneReport(entries=[])
        assert r.summary == "clean"

    def test_empty_report_print(self, capsys):
        """Printing an empty report shows 'clean' message."""
        report = HygieneReport(entries=[])
        report.print_report()
        captured = capsys.readouterr()
        assert "clean" in captured.out
        assert "No action needed" in captured.out


# ── Integration: scan_workspace against a temp git repo ─────────────────────


def _git(cmd: list[str], cwd: Path) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(["git"] + cmd, cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(cmd)}: {result.stderr}")
    return result.stdout.strip()


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary git repo with project-like structure and known state."""
    root = tmp_path / "project"
    root.mkdir()
    _git(["init"], root)
    _git(["config", "user.email", "test@test.com"], root)
    _git(["config", "user.name", "Test"], root)

    # Tracked files
    (root / "CLAUDE.md").write_text("# project rules")
    claude_dir = root / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text("{}")
    hooks_dir = claude_dir / "hooks"
    hooks_dir.mkdir()
    (hooks_dir / "check-gstack.sh").write_text("#!/bin/bash\necho ok")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "initial"], root)

    # .gitignore with project-relevant patterns
    (root / ".gitignore").write_text(
        "data/exports/\ndata/output/\n*.log\n__pycache__/\n.env.local\n.claude/settings.local.json\n"
    )
    _git(["add", ".gitignore"], root)
    _git(["commit", "-m", "add gitignore"], root)

    # ── Create files in various categories ──

    # 1. Modified tracked (project change)
    (root / "CLAUDE.md").write_text("# project rules\n## Skill Routing\n...")
    (claude_dir / "settings.json").write_text('{"hooks": []}')

    # 2. New hook file
    (hooks_dir / "check-cwd.sh").write_text("#!/bin/bash\necho cwd")

    # 3. Sample input
    src_dir = root / "data" / "source"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "ch1131_v1.txt").write_text("chapter source")
    (src_dir / "ch1228_v1.txt").write_text("another chapter")

    # 4. Generated output (gitignored)
    export_dir = root / "data" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    (export_dir / "ch1131_v1_en.md").write_text("# Chapter")
    (export_dir / "ch1131_v1_en.manifest.json").write_text("{}")

    # 5. Runtime junk
    pycache = root / "__pycache__"
    pycache.mkdir(exist_ok=True)
    (pycache / "foo.cpython-311.pyc").write_text("junk")
    (root / "adapter.log").write_text("log content")

    # 6. Local config (gitignored)
    (root / ".env.local").write_text("SECRET=xyz")
    (claude_dir / "settings.local.json").write_text('{"theme": "dark"}')

    # 7. Unknown untracked (non-ignored)
    bridge_dir = root / "bridges"
    bridge_dir.mkdir(exist_ok=True)
    (bridge_dir / "scratch.yaml").write_text("unknown")

    return root


class TestScanWorkspace:
    def test_reports_all_categories(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        cats = {e.category for e in report.entries}
        assert FILE_CATEGORY_PROJECT_CHANGE in cats
        assert FILE_CATEGORY_PROJECT_HOOK in cats
        assert FILE_CATEGORY_SAMPLE_INPUT in cats
        assert FILE_CATEGORY_GENERATED_OUTPUT in cats
        assert FILE_CATEGORY_RUNTIME_JUNK in cats
        assert FILE_CATEGORY_LOCAL_CONFIG in cats
        assert FILE_CATEGORY_UNKNOWN in cats
        # No duplicates (same path appearing twice)
        paths = [str(e.path) for e in report.entries]
        assert len(paths) == len(set(paths)), f"duplicate paths: {paths}"

    def test_modified_claude_md_classified(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        entry = next(e for e in report.entries if str(e.path) == "CLAUDE.md")
        assert entry.category == FILE_CATEGORY_PROJECT_CHANGE

    def test_modified_settings_json_classified(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        entry = next(e for e in report.entries if str(e.path) == ".claude/settings.json")
        assert entry.category == FILE_CATEGORY_PROJECT_CHANGE

    def test_new_hook_classified(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        entry = next(e for e in report.entries if ".claude/hooks/check-cwd.sh" in str(e.path))
        assert entry.category == FILE_CATEGORY_PROJECT_HOOK

    def test_sample_input_classified(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        entry = next(e for e in report.entries if "ch1131_v1.txt" in str(e.path))
        assert entry.category == FILE_CATEGORY_SAMPLE_INPUT

    def test_generated_export_classified(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        entry = next(e for e in report.entries if "ch1131_v1_en.md" in str(e.path))
        assert entry.category == FILE_CATEGORY_GENERATED_OUTPUT

    def test_runtime_junk_classified(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        entry = next(e for e in report.entries if "adapter.log" in str(e.path))
        assert entry.category == FILE_CATEGORY_RUNTIME_JUNK

    def test_local_config_classified(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        entry = next(e for e in report.entries if str(e.path) == ".env.local")
        assert entry.category == FILE_CATEGORY_LOCAL_CONFIG

    def test_unknown_untracked_classified(self, temp_project: Path):
        report = scan_workspace(project_root=temp_project)
        entry = next(e for e in report.entries if "scratch.yaml" in str(e.path))
        assert entry.category == FILE_CATEGORY_UNKNOWN

    def test_clean_workspace(self, tmp_path: Path):
        """A fresh git repo with nothing dirty should produce an empty report."""
        root = tmp_path / "clean"
        root.mkdir()
        _git(["init"], root)
        _git(["config", "user.email", "t@t.com"], root)
        _git(["config", "user.name", "T"], root)
        (root / "README.md").write_text("# clean")
        _git(["add", "-A"], root)
        _git(["commit", "-m", "init"], root)

        report = scan_workspace(project_root=root)
        assert len(report.entries) == 0
        assert report.summary == "clean"

    def test_populated_report_print(self, capsys, temp_project: Path):
        """Printing a populated report shows expected labels."""
        report = scan_workspace(project_root=temp_project)
        report.print_report()
        captured = capsys.readouterr()
        assert "[project-change]" in captured.out
        assert "[project-hook]" in captured.out
        assert "[sample-input]" in captured.out
        assert "[generated-output]" in captured.out
        assert "[runtime-junk]" in captured.out
        assert "[local-config]" in captured.out
        assert "[unknown]" in captured.out
        assert "Summary:" in captured.out
