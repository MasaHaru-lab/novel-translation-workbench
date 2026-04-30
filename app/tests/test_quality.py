"""Regression tests for chapter-level quality gates.

These exercise ``app.chapter.quality.validate_chapter_output`` against
hand-built ``ChapterResult`` instances. No real LLM backend is required.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.chapter.models import ChapterResult
from app.chapter.quality import (
    QualityIssue,
    QualityReport,
    validate_chapter_output,
)
from app.translate.schema import TranslationOutput


def _seg(seg_id: str, polished: str) -> TranslationOutput:
    return TranslationOutput(
        segment_id=seg_id,
        draft_translation=polished,
        polished_translation=polished,
        notes=[],
    )


def _good_chapter() -> ChapterResult:
    return ChapterResult(
        chapter_title="Chapter 1: The Arrival",
        source_text="第一章 到来\n\n她走进房间。",
        segment_results=[
            _seg("1", "Chapter 1: The Arrival\n\nShe walked into the room."),
        ],
        aggregated_translation=(
            "# Chapter 1: The Arrival\n\nShe walked into the room."
        ),
    )


# ── Title preservation ───────────────────────────────────────────────────


def test_title_untranslated_triggers():
    """First line of output still in Chinese triggers the gate."""
    result = ChapterResult(
        chapter_title="Chapter 1: Preface",  # metadata is English — gate checks output, not metadata
        source_text="第一章 序\n\n她走进房间。",
        segment_results=[_seg("1", "She walked into the room.")],
        aggregated_translation="第一章 序\n\nShe walked into the room.",
    )
    report = validate_chapter_output(result)
    assert not report.passed
    assert "title_untranslated" in report.codes()


def test_title_translated_does_not_trigger_title_rule():
    report = validate_chapter_output(_good_chapter())
    assert "title_untranslated" not in report.codes()


def test_title_untranslated_skips_leading_blank_lines():
    """Leading blank lines must not mask a Chinese first non-empty line."""
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="第一章\n\n她走进房间。",
        segment_results=[_seg("1", "She walked into the room.")],
        aggregated_translation="\n\n第一章\n\nShe walked into the room.",
    )
    report = validate_chapter_output(result)
    assert "title_untranslated" in report.codes()


# ── Output format contract alignment (Batch 5A) ──────────────────────────


def test_quality_and_consistency_agree_on_chinese_title_leak():
    """Contract alignment: when the raw Chinese ``chapter_title`` leaks
    into the first line of the aggregated output, BOTH the quality gate
    (``title_untranslated``) and the consistency audit (``TITLE_FORMAT``)
    must flag it. Neither may stay silent, neither may auto-fix it
    mechanically.
    """
    from app.chapter.consistency import (
        ChapterConsistencyAuditor,
        ConsistencyIssueCategory,
    )

    aggregated = "# 第一章\n\nShe walked into the room."
    chapter_title = "第一章"

    result = ChapterResult(
        chapter_title=chapter_title,
        source_text="第一章\n\n她走进房间。",
        segment_results=[_seg("1", "She walked into the room.")],
        aggregated_translation=aggregated,
    )
    report = validate_chapter_output(result)
    assert "title_untranslated" in report.codes()

    auditor = ChapterConsistencyAuditor()
    audit = auditor.audit(aggregated, chapter_title, [])
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) == 1
    assert title_issues[0].auto_fixable is False


def test_quality_and_consistency_agree_on_clean_english_first_line():
    """Contract alignment: when the segment-level translator produces an
    English heading and the Chinese metadata stays out of the visible
    output, NEITHER gate may flag the chapter.
    """
    from app.chapter.consistency import (
        ChapterConsistencyAuditor,
        ConsistencyIssueCategory,
    )

    aggregated = "# Chapter 1: The Arrival\n\nShe walked into the room."
    chapter_title = "第一章 到来"  # Chinese metadata stays metadata

    result = ChapterResult(
        chapter_title=chapter_title,
        source_text="第一章 到来\n\n她走进房间。",
        segment_results=[_seg("1", "Chapter 1: The Arrival\n\nShe walked into the room.")],
        aggregated_translation=aggregated,
    )
    report = validate_chapter_output(result)
    assert "title_untranslated" not in report.codes()
    assert report.passed

    auditor = ChapterConsistencyAuditor()
    audit = auditor.audit(aggregated, chapter_title, [])
    title_issues = audit.issues_by_category(ConsistencyIssueCategory.TITLE_FORMAT)
    assert len(title_issues) == 0


# ── Chapter-level CJK residue ────────────────────────────────────────────


def test_chapter_cjk_residue_triggers():
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="第一章\n\n她走进房间。",
        segment_results=[_seg("1", "She walked 进入 the 房间 quickly today.")],
        aggregated_translation=(
            "# Chapter 1\n\n她走进房间。这里有一些未翻译的中文。" * 2
        ),
    )
    report = validate_chapter_output(result)
    assert not report.passed
    assert "cjk_residue" in report.codes()


def test_chapter_cjk_residue_below_threshold_notrigger():
    """Two stray CJK chars in a long English chapter should not fire."""
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="ignored",
        segment_results=[_seg("1", "She greeted 王爷 warmly.")],
        aggregated_translation="# Chapter 1\n\nShe greeted 王爷 warmly.",
    )
    report = validate_chapter_output(result)
    assert "cjk_residue" not in report.codes()


# ── Per-segment checks ───────────────────────────────────────────────────


def test_empty_segment_triggers():
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="ignored",
        segment_results=[
            _seg("1", "She walked in."),
            _seg("2", "   "),
        ],
        aggregated_translation="# Chapter 1\n\nShe walked in.",
    )
    report = validate_chapter_output(result)
    codes = report.codes()
    assert "empty_segment" in codes
    empty_issue = next(i for i in report.issues if i.code == "empty_segment")
    assert empty_issue.segment_id == "2"


def test_segment_residue_triggers():
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="ignored",
        segment_results=[
            _seg("1", "She said 「明天再来」 and left silently."),
        ],
        aggregated_translation="# Chapter 1\n\nShe said 「明天再来」 and left silently.",
    )
    report = validate_chapter_output(result)
    assert "segment_residue" in report.codes()
    issue = next(i for i in report.issues if i.code == "segment_residue")
    assert issue.segment_id == "1"


# ── Clean run ────────────────────────────────────────────────────────────


def test_good_chapter_passes():
    report = validate_chapter_output(_good_chapter())
    assert report.passed
    assert report.error_count == 0
    assert report.issues == []


# ── Segment overlap detection ───────────────────────────────────────────────


def test_segment_overlap_triggers():
    """Adjacent segments with shared text at boundary must be caught."""
    shared_tail = "the onlooker sees the game best and that makes all the difference"
    result = ChapterResult(
        chapter_title="Chapter 16",
        source_text="ignored",
        segment_results=[
            _seg("1", f"She observed quietly. {shared_tail}"),
            _seg("2", f"{shared_tail} in this world of politics and power."),
        ],
        aggregated_translation=f"# Chapter 16\n\nShe observed quietly. {shared_tail} in this world of politics and power.",
    )
    report = validate_chapter_output(result)
    assert "segment_overlap" in report.codes()
    assert not report.passed


def test_segment_overlap_no_false_positive():
    """Adjacent segments with no meaningful overlap must pass."""
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="ignored",
        segment_results=[
            _seg("1", "She walked into the room and looked around carefully."),
            _seg("2", "The old woman sat by the window, her hands folded."),
        ],
        aggregated_translation="# Chapter 1\n\nShe walked into the room. The old woman sat by the window.",
    )
    report = validate_chapter_output(result)
    assert "segment_overlap" not in report.codes()


def test_segment_overlap_below_threshold_notrigger():
    """Short accidental similarity below _OVERLAP_MIN_LENGTH should not fire."""
    # Both segments end/start with "the" — too short to be real overlap.
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="ignored",
        segment_results=[
            _seg("1", "She entered the room and found the"),
            _seg("2", "the old woman waiting by the fire."),
        ],
        aggregated_translation="# Chapter 1\n\nShe entered the room and found the the old woman waiting by the fire.",
    )
    report = validate_chapter_output(result)
    assert "segment_overlap" not in report.codes()


# ── Short output detection ────────────────────────────────────────────────


def test_short_output_triggers():
    """Non-empty but suspiciously short segment output must be caught."""
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="这是一个很长的中文段落，描述了很多内容。",
        segment_results=[
            _seg("1", "He nodded."),
        ],
        aggregated_translation="# Chapter 1\n\nHe nodded.",
    )
    report = validate_chapter_output(result)
    assert "short_output" in report.codes()
    issue = next(i for i in report.issues if i.code == "short_output")
    assert issue.segment_id == "1"


def test_short_output_does_not_fire_on_empty():
    """Empty segment should fire empty_segment, not short_output."""
    result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="ignored",
        segment_results=[
            _seg("1", ""),
        ],
        aggregated_translation="# Chapter 1\n\n",
    )
    report = validate_chapter_output(result)
    assert "short_output" not in report.codes()
    assert "empty_segment" in report.codes()


def test_short_output_does_not_fire_on_normal_length():
    """Normal-length segment output must pass the short check."""
    report = validate_chapter_output(_good_chapter())
    assert "short_output" not in report.codes()


# ── Orchestrator status demotion ────────────────────────────────────────────


def test_quality_failure_demotes_chapter_status(tmp_path):
    """Quality failure must demote ChapterResult.chapter_status to PARTIAL
    in the manifest execution path."""
    from app.chapter.orchestrator import ChapterOrchestrator
    from app.chapter.manifest import RunManifest, ChapterStatus
    from app.translate.schema import TranslationInput
    import app.chapter.orchestrator as orch_mod

    def fake_translate_draft(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="d",
            polished_translation="",
            notes=[],
        )

    def fake_polish(inp, draft_out, **_kwargs):
        # Segment leaves 「明天再来」 in output — CJK residue triggers the gate.
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=draft_out.draft_translation,
            polished_translation="She said 「明天再来」 and left silently.",
            notes=[],
        )

    manifest_path = tmp_path / "demotion.manifest.json"
    original_polish = orch_mod.polish_translation
    orch_mod.polish_translation = fake_polish
    try:
        orch = ChapterOrchestrator()
        result = orch.run_with_manifest(
            source_text="Chapter 1\n\n她走进房间。",
            translate_draft_fn=fake_translate_draft,
            assets_mode="none",
            manifest_path=str(manifest_path),
        )
    finally:
        orch_mod.polish_translation = original_polish

    # Chapter status must be demoted from COMPLETED to PARTIAL.
    assert result.chapter_status == ChapterStatus.PARTIAL

    # Manifest must also reflect the demotion.
    loaded = RunManifest.load(str(manifest_path))
    assert loaded.status == ChapterStatus.PARTIAL


def test_quality_pass_preserves_completed_status(tmp_path):
    """Clean quality must leave chapter_status as COMPLETED."""
    from app.chapter.orchestrator import ChapterOrchestrator
    from app.chapter.manifest import RunManifest, ChapterStatus
    from app.translate.schema import TranslationInput
    import app.chapter.orchestrator as orch_mod

    def fake_translate_draft(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="d",
            polished_translation="",
            notes=[],
        )

    def fake_polish(inp, draft_out, **_kwargs):
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=draft_out.draft_translation,
            polished_translation="She walked into the room and looked around carefully, noting the old furniture.",
            notes=[],
        )

    manifest_path = tmp_path / "pass.manifest.json"
    original_polish = orch_mod.polish_translation
    orch_mod.polish_translation = fake_polish
    try:
        orch = ChapterOrchestrator()
        result = orch.run_with_manifest(
            source_text="Chapter 1\n\n她走进房间。",
            translate_draft_fn=fake_translate_draft,
            assets_mode="none",
            manifest_path=str(manifest_path),
        )
    finally:
        orch_mod.polish_translation = original_polish

    assert result.chapter_status == ChapterStatus.COMPLETED
    assert result.quality_report is not None
    assert result.quality_report.passed


# ── Report API ───────────────────────────────────────────────────────────


def test_quality_report_passed_property():
    r = QualityReport(issues=[
        QualityIssue(code="x", severity="warning", message="m"),
    ])
    assert r.passed
    assert r.warning_count == 1

    r = QualityReport(issues=[
        QualityIssue(code="x", severity="error", message="m"),
    ])
    assert not r.passed
    assert r.error_count == 1


# ── Orchestrator integration ─────────────────────────────────────────────


def test_orchestrator_attaches_quality_report():
    """``execute()`` must attach a quality_report so manifest completion
    cannot mask bad output."""
    from app.chapter.orchestrator import ChapterOrchestrator
    from app.translate.schema import TranslationInput, GlossaryTerm

    def fake_translate_draft(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="Translated draft for " + inp.segment_id,
            polished_translation="",
            notes=[],
        )

    orch = ChapterOrchestrator()
    plan = orch.plan("Chapter 1: Arrival\n\nShe walked into the room.")

    # Patch polish_translation to bypass the backend.
    import app.chapter.orchestrator as orch_mod

    def fake_polish(inp, draft_out, **_kwargs):
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=draft_out.draft_translation,
            polished_translation="She walked into the room.",
            notes=[],
        )

    original_polish = orch_mod.polish_translation
    orch_mod.polish_translation = fake_polish
    try:
        result = orch.execute(
            plan,
            translate_draft_fn=fake_translate_draft,
            assets_mode="none",
        )
    finally:
        orch_mod.polish_translation = original_polish

    assert result.quality_report is not None
    assert isinstance(result.quality_report, QualityReport)


# ── Quality summary persistence and operator visibility ─────────────────


def test_quality_report_to_summary_shape():
    """Summary must be JSON-friendly and stable for manifest persistence."""
    r = QualityReport(issues=[
        QualityIssue(code="cjk_residue", severity="error", message="m"),
        QualityIssue(code="title_untranslated", severity="error", message="m"),
        QualityIssue(code="x", severity="warning", message="m"),
    ])
    s = r.to_summary()
    assert s["passed"] is False
    assert s["error_count"] == 2
    assert s["warning_count"] == 1
    assert "cjk_residue" in s["codes"]
    assert "title_untranslated" in s["codes"]


def test_run_with_manifest_persists_quality_summary(tmp_path):
    """A failed quality gate must be reflected in the persisted manifest
    JSON, not only in the in-memory ChapterResult."""
    from app.chapter.orchestrator import ChapterOrchestrator
    from app.chapter.manifest import RunManifest
    from app.translate.schema import TranslationInput
    import app.chapter.orchestrator as orch_mod

    def fake_translate_draft(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="d",
            polished_translation="",
            notes=[],
        )

    def fake_polish(inp, draft_out, **_kwargs):
        # Deliberately leave untranslated Chinese to fail the gate.
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=draft_out.draft_translation,
            polished_translation="She said 「明天再来」 and left silently.",
            notes=[],
        )

    manifest_path = tmp_path / "run.manifest.json"
    original_polish = orch_mod.polish_translation
    orch_mod.polish_translation = fake_polish
    try:
        orch = ChapterOrchestrator()
        result = orch.run_with_manifest(
            source_text="Chapter 1\n\n她走进房间。",
            translate_draft_fn=fake_translate_draft,
            assets_mode="none",
            manifest_path=str(manifest_path),
        )
    finally:
        orch_mod.polish_translation = original_polish

    assert result.quality_report is not None
    assert not result.quality_report.passed

    loaded = RunManifest.load(str(manifest_path))
    assert loaded.quality_summary is not None
    assert loaded.quality_summary["passed"] is False
    assert loaded.quality_summary["error_count"] >= 1
    assert "segment_residue" in loaded.quality_summary["codes"]


def test_cli_report_prints_quality_failure(capsys):
    """The CLI report must surface a quality fail; an operator must not see
    a clean ``Status: completed`` while the quality gate flagged errors."""
    from pathlib import Path
    from app.chapter.models import ChapterResult
    from app.chapter.manifest import ChapterStatus
    from app.cli import _report_chapter_result

    bad_result = ChapterResult(
        chapter_title="Chapter 1",
        source_text="ignored",
        segment_results=[_seg("1", "She said 「明天再来」 and left silently.")],
        aggregated_translation="# Chapter 1\n\nShe said 「明天再来」 and left.",
        chapter_status=ChapterStatus.COMPLETED,
    )
    bad_result.quality_report = validate_chapter_output(bad_result)
    assert not bad_result.quality_report.passed

    _report_chapter_result(bad_result, Path("/tmp/__quality_test_unused.md"))
    out = capsys.readouterr().out
    assert "Quality:" in out
    assert "FAILED" in out
    assert "segment_residue" in out


def test_cli_report_prints_quality_pass(capsys):
    from pathlib import Path
    from app.chapter.models import ChapterResult
    from app.chapter.manifest import ChapterStatus
    from app.cli import _report_chapter_result

    good = _good_chapter()
    good.chapter_status = ChapterStatus.COMPLETED
    good.quality_report = validate_chapter_output(good)
    assert good.quality_report.passed

    _report_chapter_result(good, Path("/tmp/__quality_test_unused.md"))
    out = capsys.readouterr().out
    assert "Quality:     passed" in out
