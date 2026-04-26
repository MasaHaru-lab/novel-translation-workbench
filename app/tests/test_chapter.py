import sys
import os
from contextlib import ExitStack
from typing import Callable
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.chapter.manifest import ChapterStatus, ResumeConfig, SegmentStatus
from app.chapter.models import ChapterPlan, ChapterResult
from app.chapter.orchestrator import (
    ChapterOrchestrator,
    extract_chapter_title,
    format_aggregated_translation,
)
from app.segment.segmenter import Segment
from app.translate.schema import TranslationInput, TranslationOutput
from app.translate.translator import BudgetConfig


# ── helpers ──────────────────────────────────────────────────────────────

def _make_segments(count: int) -> list[Segment]:
    return [
        Segment(
            segment_id=i + 1,
            text=f"测试段落{i + 1}的内容。",
            prev_segment_text=(
                f"测试段落{i}的内容。" if i > 0 else None
            ),
            next_segment_text=(
                f"测试段落{i + 2}的内容。" if i + 1 < count else None
            ),
        )
        for i in range(count)
    ]


# ── models ───────────────────────────────────────────────────────────────

def test_chapter_plan_defaults():
    plan = ChapterPlan(chapter_title="Test", source_text="hello")
    assert plan.segment_count == 0
    assert plan.segments == []


def test_chapter_plan_with_segments():
    segs = _make_segments(3)
    plan = ChapterPlan(
        chapter_title="第一章",
        source_text="第一章\n\n内容。",
        segments=segs,
    )
    assert plan.segment_count == 3
    assert plan.segments[0].segment_id == 1


def test_chapter_result_defaults():
    result = ChapterResult(chapter_title="Test", source_text="hello")
    assert result.segment_count == 0
    assert result.aggregated_translation == ""


def test_chapter_result_with_results():
    segs = _make_segments(2)
    results = [
        TranslationOutput(segment_id="1", draft_translation="d1", polished_translation="First segment."),
        TranslationOutput(segment_id="2", draft_translation="d2", polished_translation="Second segment."),
    ]
    result = ChapterResult(
        chapter_title="第一章",
        source_text="source",
        segment_results=results,
        aggregated_translation="Full chapter text.",
    )
    assert result.segment_count == 2
    assert result.aggregated_translation == "Full chapter text."


# ── extract_chapter_title ────────────────────────────────────────────────

def test_extract_chapter_title_from_first_line():
    text = "第一章\n\n这是内容。"
    assert extract_chapter_title(text) == "第一章"


def test_extract_chapter_title_skips_empty_lines():
    text = "\n\n\n第一章\n内容。"
    assert extract_chapter_title(text) == "第一章"


def test_extract_chapter_title_fallback():
    assert extract_chapter_title("") == "Untitled Chapter"
    assert extract_chapter_title("   \n  \n") == "Untitled Chapter"


# ── format_aggregated_translation ────────────────────────────────────────

def test_format_aggregated_single_segment():
    results = [
        TranslationOutput(segment_id="1", draft_translation="", polished_translation="Single paragraph."),
    ]
    out = format_aggregated_translation("Chapter 1", results)
    assert out == "Single paragraph."


def test_format_aggregated_multiple_segments():
    results = [
        TranslationOutput(segment_id="1", draft_translation="", polished_translation="First para."),
        TranslationOutput(segment_id="2", draft_translation="", polished_translation="Second para."),
    ]
    out = format_aggregated_translation("Chapter 2", results)
    assert out == "First para.\n\nSecond para."
    # Check ordering
    first_idx = out.index("First para.")
    second_idx = out.index("Second para.")
    assert first_idx < second_idx


def test_format_aggregated_skips_empty():
    results = [
        TranslationOutput(segment_id="1", draft_translation="", polished_translation="Only this."),
        TranslationOutput(segment_id="2", draft_translation="", polished_translation=""),
    ]
    out = format_aggregated_translation("Test", results)
    assert "Only this." in out


# ── Output format contract (Batch 5A) ────────────────────────────────────


def test_format_aggregated_does_not_prepend_chinese_chapter_title():
    """Contract rule 1: orchestrator must NOT inject the raw Chinese
    ``chapter_title`` as a heading on the aggregated output.

    The visible heading is whatever the segment-level translator produced
    inside segment 1.
    """
    results = [
        TranslationOutput(
            segment_id="1",
            draft_translation="",
            polished_translation="# Chapter 1: The Arrival\n\nShe walked into the room.",
        ),
        TranslationOutput(
            segment_id="2",
            draft_translation="",
            polished_translation="The room was quiet.",
        ),
    ]
    out = format_aggregated_translation("第一章 到来", results)
    first_line = out.splitlines()[0]
    assert "第一章" not in first_line
    assert first_line == "# Chapter 1: The Arrival"


def test_format_aggregated_first_line_has_no_cjk_when_segment_translates_heading():
    """Contract rule 2: when the segment-level translator produces an
    English heading, no CJK characters appear in the first non-empty line.
    """
    results = [
        TranslationOutput(
            segment_id="1",
            draft_translation="",
            polished_translation="Chapter 1: The Arrival\n\nShe walked into the room.",
        ),
    ]
    out = format_aggregated_translation("第一章 到来", results)

    first_non_empty = next((l for l in out.splitlines() if l.strip()), "")
    assert first_non_empty == "Chapter 1: The Arrival"
    # No CJK characters in the first non-empty line.
    assert all(not ('一' <= ch <= '鿿') for ch in first_non_empty)


# ── ChapterOrchestrator.plan ─────────────────────────────────────────────

def test_plan_single_segment():
    text = "第一章\n\n简短短段落。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)
    assert plan.chapter_title == "第一章"
    assert len(plan.segments) >= 1
    assert plan.source_text == text


def test_plan_multiple_segments():
    """Long text should produce multiple segments."""
    para = "测试段落内容。" * 200  # ~700 chars
    text = "第零章\n\n" + "\n\n".join([para for _ in range(5)])
    orch = ChapterOrchestrator()
    plan = orch.plan(text)
    assert plan.chapter_title == "第零章"
    assert plan.segment_count > 1
    assert plan.segments[0].segment_id == 1


def test_plan_preserves_prev_next_context():
    para = "测试段落内容。" * 100
    text = "第一章\n\n" + "\n\n".join([para for _ in range(4)])
    orch = ChapterOrchestrator()
    plan = orch.plan(text)
    if plan.segment_count >= 2:
        assert plan.segments[0].next_segment_text is not None
        assert plan.segments[0].prev_segment_text is None
        assert plan.segments[-1].prev_segment_text is not None
        assert plan.segments[-1].next_segment_text is None


# ── ChapterOrchestrator.execute ──────────────────────────────────────────

def test_execute_with_mock_translate():
    """Execute should translate each segment using the provided function."""
    text = "第一章\n\n内容。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )

    # polish_translation needs backend config + mock response.
    # Mock review says no major issue, so draft is kept as polished text.
    def mock_backend(prompt, max_tokens=None, **extra):
        return "major_issue: none\nwhy_it_matters: n/a\nrecommended_fix: none\noptional_notes: n/a"

    patches = [
        patch("app.translate.backend_adapter.call_model_backend", side_effect=mock_backend),
        patch("app.config.config.MODEL_BACKEND_URL", "http://fake:9999"),
    ]
    for p in patches:
        p.start()
    try:
        result = orch.execute(plan, translate_draft_fn=mock_draft_fn)
    finally:
        for p in patches:
            p.stop()
    assert result.segment_count == plan.segment_count
    for r in result.segment_results:
        assert "[DRAFT" in r.draft_translation
        # When review finds no major issue, polished equals draft
        assert r.polished_translation == r.draft_translation


def test_execute_aggregates_results():
    text = "第一章\n\n内容。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation=f"Polished output for seg {inp.segment_id}.",
        )

    def mock_backend(prompt, max_tokens=None, **extra):
        return "major_issue: none\nwhy_it_matters: n/a\nrecommended_fix: none\noptional_notes: n/a"

    patches = [
        patch("app.translate.backend_adapter.call_model_backend", side_effect=mock_backend),
        patch("app.config.config.MODEL_BACKEND_URL", "http://fake:9999"),
    ]
    for p in patches:
        p.start()
    try:
        result = orch.execute(plan, translate_draft_fn=mock_draft_fn)
    finally:
        for p in patches:
            p.stop()
    assert len(result.aggregated_translation) > 0
    for r in result.segment_results:
        assert r.polished_translation in result.aggregated_translation


# ── ChapterOrchestrator.run ──────────────────────────────────────────────

def test_run_full_pipeline_with_mock():
    """run() should compose plan + execute + aggregate."""
    text = "第一章\n\n测试内容。"
    orch = ChapterOrchestrator()

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
        )

    # Mock review says no major issue, so draft is kept as polished.
    def mock_backend(prompt, max_tokens=None, **extra):
        return "major_issue: none\nwhy_it_matters: n/a\nrecommended_fix: none\noptional_notes: n/a"

    patches = [
        patch("app.translate.backend_adapter.call_model_backend", side_effect=mock_backend),
        patch("app.config.config.MODEL_BACKEND_URL", "http://fake:9999"),
    ]
    for p in patches:
        p.start()
    try:
        result = orch.run(text, translate_draft_fn=mock_draft_fn)
    finally:
        for p in patches:
            p.stop()
    assert result.chapter_title == "第一章"
    assert result.segment_count >= 1
    # Aggregated translation includes the draft text (no revision needed)
    assert "draft" in result.aggregated_translation


def test_run_preserves_source_text():
    text = "第一章\n\n原始内容。"
    orch = ChapterOrchestrator()

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="English.",
        )

    def mock_backend(prompt, max_tokens=None, **extra):
        return "major_issue: none\nwhy_it_matters: n/a\nrecommended_fix: none\noptional_notes: n/a"

    patches = [
        patch("app.translate.backend_adapter.call_model_backend", side_effect=mock_backend),
        patch("app.config.config.MODEL_BACKEND_URL", "http://fake:9999"),
    ]
    for p in patches:
        p.start()
    try:
        result = orch.run(text, translate_draft_fn=mock_draft_fn)
    finally:
        for p in patches:
            p.stop()
    assert result.source_text == text


# ═══════════════════════════════════════════════════════════════════════
# Batch 2: run_with_manifest — failure isolation, retry, resume
# ═══════════════════════════════════════════════════════════════════════

# ── helpers ───────────────────────────────────────────────────────────

def _mock_backend_review_ok(prompt, max_tokens=None, **extra):
    """Mock backend review response — no major issue, keep draft as-is."""
    return "major_issue: none\nwhy_it_matters: n/a\nrecommended_fix: none\noptional_notes: n/a"


def _patch_backend():
    """Context manager that applies all backend patches.

    Use: ``with _patch_backend():``
    """
    stack = ExitStack()
    stack.enter_context(patch(
        "app.translate.backend_adapter.call_model_backend",
        side_effect=_mock_backend_review_ok,
    ))
    stack.enter_context(patch(
        "app.config.config.MODEL_BACKEND_URL",
        "http://fake:9999",
    ))
    return stack


def _make_mock_draft_fn() -> Callable:
    """Create a mock translate_draft_fn that returns a TranslationOutput."""
    def fn(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )
    return fn


# ── run_with_manifest: basic success ──────────────────────────────────

def _long_chapter_text(num_paragraphs: int = 6) -> str:
    """Generate a chapter text long enough to produce multiple segments."""
    para = "测试段落内容。" * 200  # ~700 chars per paragraph
    paras = "\n\n".join(para for _ in range(num_paragraphs))
    return "第一章\n\n" + paras


def test_run_with_manifest_all_succeed():
    """run_with_manifest should translate all segments and report COMPLETED."""
    text = _long_chapter_text(6)
    orch = ChapterOrchestrator()
    draft_fn = _make_mock_draft_fn()

    with _patch_backend():
        result = orch.run_with_manifest(text, translate_draft_fn=draft_fn)

    assert result.chapter_status.value == "completed"
    assert result.is_complete is True
    assert result.is_partial is False
    assert result.segment_count >= 2  # Should produce multiple segments
    assert result.failed_segment_ids == []
    assert result.resumable is False
    assert len(result.aggregated_translation) > 0
    assert result.manifest is not None
    assert result.manifest.status.value == "completed"


def test_run_with_manifest_tracks_segment_statuses():
    """Each segment's status should be recorded."""
    text = _long_chapter_text(6)
    orch = ChapterOrchestrator()
    draft_fn = _make_mock_draft_fn()

    with _patch_backend():
        result = orch.run_with_manifest(text, translate_draft_fn=draft_fn)

    assert len(result.segment_statuses) >= 2
    for sid, status in result.segment_statuses.items():
        assert status.value == "completed", f"Segment {sid} not completed: {status}"


# ── run_with_manifest: failure isolation ──────────────────────────────

def test_run_with_manifest_one_segment_fails_others_succeed():
    """When one segment fails, completed segments should be preserved."""
    text = _long_chapter_text(6)
    orch = ChapterOrchestrator()
    failed_seg_id = None

    # Draft fn that fails for segment "2" but succeeds for others.
    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        nonlocal failed_seg_id
        if inp.segment_id == "2":
            failed_seg_id = inp.segment_id
            raise RuntimeError("Translation service unavailable for seg 2")
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )

    with _patch_backend():
        result = orch.run_with_manifest(
            text,
            translate_draft_fn=mock_draft_fn,
            resume_config=ResumeConfig(max_retries=0),
        )

    # Chapter should be PARTIAL (some succeeded, some failed)
    assert result.chapter_status.value == "partial"
    assert result.is_partial is True
    assert result.is_complete is False
    assert failed_seg_id in result.failed_segment_ids
    assert result.segment_statuses.get(failed_seg_id).value == "failed"

    # Completed segments should be preserved
    completed_ids = result.manifest.get_completed_segment_ids()
    assert len(completed_ids) >= 1
    assert failed_seg_id not in completed_ids
    assert result.resumable is True


def test_run_with_manifest_all_segments_fail():
    """When all segments fail, chapter status should be FAILED."""
    text = _long_chapter_text(4)
    orch = ChapterOrchestrator()

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        raise RuntimeError("Backend down")

    with _patch_backend():
        result = orch.run_with_manifest(
            text,
            translate_draft_fn=mock_draft_fn,
            resume_config=ResumeConfig(max_retries=0),
        )

    assert result.chapter_status.value == "failed"
    assert result.is_complete is False
    assert result.is_partial is False
    assert len(result.failed_segment_ids) == result.manifest.total_segments
    assert result.resumable is True


# ── Resume ────────────────────────────────────────────────────────────

def test_resume_from_manifest(tmp_path):
    """Resume should skip completed segments and continue from pending ones."""
    manifest_path = str(tmp_path / "resume_test.manifest.json")
    text = _long_chapter_text(6)
    orch = ChapterOrchestrator()
    failed_seg_id = None

    # Phase 1: run with a failure on segment 2
    def mock_draft_fn_v1(inp: TranslationInput) -> TranslationOutput:
        nonlocal failed_seg_id
        if inp.segment_id == "2":
            failed_seg_id = inp.segment_id
            raise RuntimeError("Transient error on seg 2")
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )

    with _patch_backend():
        result1 = orch.run_with_manifest(
            text,
            translate_draft_fn=mock_draft_fn_v1,
            manifest_path=manifest_path,
            resume_config=ResumeConfig(max_retries=0),
        )

    assert result1.chapter_status.value == "partial"
    assert failed_seg_id in result1.failed_segment_ids
    # At least one segment completed before the failure
    completed1 = result1.manifest.get_completed_segment_ids()
    assert len(completed1) >= 1
    assert failed_seg_id not in completed1

    # Phase 2: resume with a working draft fn for the failed segment
    def mock_draft_fn_v2(inp: TranslationInput) -> TranslationOutput:
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )

    with _patch_backend():
        result2 = orch.resume(
            text,
            manifest_path,
            translate_draft_fn=mock_draft_fn_v2,
        )

    assert result2 is not None
    assert result2.chapter_status.value == "completed"
    assert result2.is_complete is True
    assert result2.failed_segment_ids == []

    # All segments should now be completed
    completed2 = result2.manifest.get_completed_segment_ids()
    assert len(completed2) == result2.manifest.total_segments


def test_resume_from_manifest_preserves_prior_completed(tmp_path):
    """Resume should not re-execute segments that already completed."""
    manifest_path = str(tmp_path / "resume_preserve.manifest.json")
    text = _long_chapter_text(6)
    orch = ChapterOrchestrator()
    execution_order = []
    failed_seg_id = None

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        execution_order.append(inp.segment_id)
        nonlocal failed_seg_id
        if inp.segment_id == "2":
            failed_seg_id = inp.segment_id
            raise RuntimeError("Fail seg 2")
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )

    with _patch_backend():
        result1 = orch.run_with_manifest(
            text,
            translate_draft_fn=mock_draft_fn,
            manifest_path=manifest_path,
            resume_config=ResumeConfig(max_retries=0),
        )

    assert result1.chapter_status.value == "partial"
    execution_order.clear()

    # Resume: only the failed segment should be re-executed
    def mock_draft_fn_working(inp: TranslationInput) -> TranslationOutput:
        execution_order.append(inp.segment_id)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )

    with _patch_backend():
        result2 = orch.resume(text, manifest_path, translate_draft_fn=mock_draft_fn_working)

    assert result2 is not None
    # Only the previously failed segment should be executed during resume
    assert execution_order == [failed_seg_id]
    assert result2.chapter_status.value == "completed"


def test_resume_already_complete_returns_none(tmp_path):
    """Resuming a completed chapter should return None."""
    manifest_path = str(tmp_path / "complete_resume.manifest.json")
    text = "第一章\n\n内容。"
    orch = ChapterOrchestrator()
    draft_fn = _make_mock_draft_fn()

    with _patch_backend():
        orch.run_with_manifest(text, translate_draft_fn=draft_fn, manifest_path=manifest_path)

    # Resume should detect already-complete and return None
    with _patch_backend():
        result = orch.resume(text, manifest_path, translate_draft_fn=draft_fn)

    assert result is None


def test_resume_nonexistent_manifest_returns_none():
    """Resuming with no manifest file should return None."""
    orch = ChapterOrchestrator()
    result = orch.resume("text", "/nonexistent/manifest.json")
    assert result is None


# ── Retry discipline ──────────────────────────────────────────────────

def test_retry_succeeds_on_second_attempt():
    """Segment should succeed after one retry."""
    # Use text that produces exactly one segment.
    text = "第一章\n\n简短短段落。"
    orch = ChapterOrchestrator()
    attempt = [0]

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        attempt[0] += 1
        if attempt[0] == 1:
            raise RuntimeError("Transient error")
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation=f"[DRAFT {inp.segment_id}]",
            polished_translation="",
        )

    with _patch_backend():
        result = orch.run_with_manifest(
            text,
            translate_draft_fn=mock_draft_fn,
            resume_config=ResumeConfig(max_retries=1),
        )

    assert result.chapter_status.value == "completed"
    assert result.is_complete is True
    assert attempt[0] == 2  # First attempt failed, second succeeded


def test_retry_exhausted_marks_segment_failed():
    """Segment should be marked failed after exhausting retries."""
    # Use text that produces exactly one segment.
    text = "第一章\n\n简短短段落。"
    orch = ChapterOrchestrator()
    attempt = [0]

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        attempt[0] += 1
        raise RuntimeError("Persistent error")

    with _patch_backend():
        result = orch.run_with_manifest(
            text,
            translate_draft_fn=mock_draft_fn,
            resume_config=ResumeConfig(max_retries=2),
        )

    assert result.chapter_status.value == "failed"
    assert attempt[0] == 3  # Initial + 2 retries = 3 attempts
    assert result.failed_segment_ids == ["1"]
    assert result.segment_statuses["1"].value == "failed"


def test_zero_retries_means_no_retry():
    """With max_retries=0, a failure should immediately mark the segment failed."""
    # Use text that produces exactly one segment.
    text = "第一章\n\n简短短段落。"
    orch = ChapterOrchestrator()
    attempt = [0]

    def mock_draft_fn(inp: TranslationInput) -> TranslationOutput:
        attempt[0] += 1
        raise RuntimeError("Error")

    with _patch_backend():
        result = orch.run_with_manifest(
            text,
            translate_draft_fn=mock_draft_fn,
            resume_config=ResumeConfig(max_retries=0),
        )

    assert result.chapter_status.value == "failed"
    assert attempt[0] == 1  # Only 1 attempt, no retry


# ── ChapterResult status fields ───────────────────────────────────────

def test_chapter_result_defaults():
    result = ChapterResult(chapter_title="Test", source_text="hello")
    assert result.chapter_status.value == "pending"
    assert result.segment_statuses == {}
    assert result.failed_segment_ids == []
    assert result.resumable is False
    assert result.is_complete is False
    assert result.is_partial is False
    assert result.success_count == 0


def test_chapter_result_properties():
    result = ChapterResult(
        chapter_title="Test",
        source_text="hello",
        chapter_status=ChapterStatus.COMPLETED,
        segment_statuses={"1": SegmentStatus.COMPLETED, "2": SegmentStatus.COMPLETED},
    )
    assert result.is_complete is True
    assert result.is_partial is False
    assert result.success_count == 2


def test_chapter_result_partial_properties():
    result = ChapterResult(
        chapter_title="Test",
        source_text="hello",
        chapter_status=ChapterStatus.PARTIAL,
        segment_statuses={"1": SegmentStatus.COMPLETED, "2": SegmentStatus.FAILED},
        failed_segment_ids=["2"],
    )
    assert result.is_complete is False
    assert result.is_partial is True
    assert result.success_count == 1
    assert result.failed_segment_ids == ["2"]


# ── Batch 4B: Strategy enactment tests ──────────────────────────────────

def test_resolve_budget_from_plan_without_strategy():
    """Test _resolve_budget_from_plan falls back to standard when strategy_plan is None."""
    orchestrator = ChapterOrchestrator()
    plan = ChapterPlan(
        chapter_title="Test",
        source_text="Test chapter",
        segments=[],
        strategy_plan=None,
    )
    budget_config = orchestrator._resolve_budget_from_plan(plan)
    # Should return standard budget config (4096/2048/4096)
    assert budget_config.draft_max_tokens == 4096
    assert budget_config.review_max_tokens == 2048
    assert budget_config.polish_max_tokens == 4096


def test_resolve_budget_from_plan_with_strategy():
    """Test _resolve_budget_from_plan reads budget_profile from strategy_plan."""
    orchestrator = ChapterOrchestrator()
    plan = ChapterPlan(
        chapter_title="Test",
        source_text="Test chapter",
        segments=[],
        strategy_plan={
            "overall_strategy": {
                "budget_profile": "light",
                "consistency_intensity": "standard",
                "segmentation_granularity": "standard",
            }
        },
    )
    budget_config = orchestrator._resolve_budget_from_plan(plan)
    # Light budget config (2048/1024/2048)
    assert budget_config.draft_max_tokens == 2048
    assert budget_config.review_max_tokens == 1024
    assert budget_config.polish_max_tokens == 2048


def test_resolve_consistency_intensity_from_plan():
    """Test _resolve_consistency_intensity_from_plan reads from strategy_plan."""
    orchestrator = ChapterOrchestrator()

    # Test with missing strategy_plan
    plan_no_strategy = ChapterPlan(
        chapter_title="Test",
        source_text="Test chapter",
        segments=[],
        strategy_plan=None,
    )
    intensity = orchestrator._resolve_consistency_intensity_from_plan(plan_no_strategy)
    assert intensity == "standard"

    # Test with strategy_plan
    plan_with_strategy = ChapterPlan(
        chapter_title="Test",
        source_text="Test chapter",
        segments=[],
        strategy_plan={
            "overall_strategy": {
                "budget_profile": "standard",
                "consistency_intensity": "enhanced",
                "segmentation_granularity": "standard",
            }
        },
    )
    intensity = orchestrator._resolve_consistency_intensity_from_plan(plan_with_strategy)
    assert intensity == "enhanced"


def test_build_enactment_minimal():
    """Test _build_enactment only records known values, leaves unknown as None."""
    orchestrator = ChapterOrchestrator()

    # Plan with strategy
    plan = ChapterPlan(
        chapter_title="Test",
        source_text="Test chapter",
        segments=[],
        strategy_plan={
            "overall_strategy": {
                "budget_profile": "conservative",
                "consistency_intensity": "enhanced",
                "segmentation_granularity": "finer",
            }
        },
    )

    budget_config = BudgetConfig(draft_max_tokens=6144, review_max_tokens=3072, polish_max_tokens=6144)
    enactment = orchestrator._build_enactment(
        plan=plan,
        budget_config=budget_config,
        consistency_intensity="enhanced",
        segmentation_granularity="finer",
        segment_count=5,
    )

    assert enactment is not None
    assert enactment["planned"]["budget_profile"] == "conservative"
    assert enactment["planned"]["consistency_intensity"] == "enhanced"
    assert enactment["planned"]["segmentation_granularity"] == "finer"

    # Enacted values should match what was passed
    assert enactment["enacted"]["segmentation"]["granularity"] == "finer"
    assert enactment["enacted"]["segmentation"]["segment_count"] == 5
    assert enactment["enacted"]["segmentation"]["max_chars"] is None  # Not known
    assert enactment["enacted"]["segmentation"]["min_chars"] is None  # Not known

    assert enactment["enacted"]["budget"]["profile"] == "conservative"
    assert enactment["enacted"]["budget"]["draft_max_tokens"] == 6144
    assert enactment["enacted"]["budget"]["review_max_tokens"] == 3072
    assert enactment["enacted"]["budget"]["polish_max_tokens"] == 6144

    assert enactment["enacted"]["consistency"]["intensity"] == "enhanced"
    assert enactment["enacted"]["consistency"]["audit_issues_found"] is None
    assert enactment["enacted"]["consistency"]["auto_fixable"] is None
    assert enactment["enacted"]["consistency"]["auto_fixed"] is None
    assert enactment["enacted"]["consistency"]["corrections_applied"] is None

    # consistent should be None (cannot determine without more context)
    assert enactment["consistent"] is None


def test_build_enactment_no_strategy():
    """Test _build_enactment returns None when strategy_plan is missing."""
    orchestrator = ChapterOrchestrator()

    plan = ChapterPlan(
        chapter_title="Test",
        source_text="Test chapter",
        segments=[],
        strategy_plan=None,
    )

    budget_config = BudgetConfig()
    enactment = orchestrator._build_enactment(
        plan=plan,
        budget_config=budget_config,
        consistency_intensity="standard",
        segmentation_granularity="standard",
        segment_count=3,
    )

    assert enactment is None


def test_budget_config_passed_to_translation_functions():
    """Test that budget_config resolved from plan is passed to translate_draft and polish_translation."""
    orchestrator = ChapterOrchestrator()

    # Mock downstream functions
    with patch('app.chapter.orchestrator.translate_draft') as mock_translate_draft, \
         patch('app.chapter.orchestrator.polish_translation') as mock_polish_translation:

        # Setup mock returns
        mock_draft_output = TranslationOutput(
            segment_id="1",
            draft_translation="Draft text",
            polished_translation="",
        )
        mock_final_output = TranslationOutput(
            segment_id="1",
            draft_translation="Draft text",
            polished_translation="Polished text",
        )
        mock_translate_draft.return_value = mock_draft_output
        mock_polish_translation.return_value = mock_final_output

        # Create plan with light budget profile
        plan = ChapterPlan(
            chapter_title="Test",
            source_text="Test chapter",
            segments=[Segment(segment_id=1, text="Test text", prev_segment_text=None, next_segment_text=None)],
            strategy_plan={
                "overall_strategy": {
                    "budget_profile": "light",
                    "consistency_intensity": "standard",
                    "segmentation_granularity": "standard",
                }
            },
        )

        # Call execute (which resolves budget_config from plan)
        result = orchestrator.execute(plan)

        # Verify translate_draft called with budget_config
        assert mock_translate_draft.called
        call_args = mock_translate_draft.call_args
        assert 'budget_config' in call_args.kwargs
        budget_config = call_args.kwargs['budget_config']
        assert isinstance(budget_config, BudgetConfig)
        # Light budget config: 2048/1024/2048
        assert budget_config.draft_max_tokens == 2048
        assert budget_config.review_max_tokens == 1024
        assert budget_config.polish_max_tokens == 2048

        # Verify polish_translation called with same budget_config
        assert mock_polish_translation.called
        polish_call_args = mock_polish_translation.call_args
        assert 'budget_config' in polish_call_args.kwargs
        polish_budget_config = polish_call_args.kwargs['budget_config']
        assert polish_budget_config.draft_max_tokens == 2048


def test_consistency_intensity_passed_to_consistency_pass():
    """Test that consistency_intensity resolved from plan is passed to consistency pass."""
    orchestrator = ChapterOrchestrator()

    # Mock plan() to return a plan with enhanced consistency intensity
    mock_plan = ChapterPlan(
        chapter_title="Test",
        source_text="Test chapter",
        segments=[Segment(segment_id=1, text="Test text", prev_segment_text=None, next_segment_text=None)],
        strategy_plan={
            "overall_strategy": {
                "budget_profile": "standard",
                "consistency_intensity": "enhanced",
                "segmentation_granularity": "standard",
            }
        },
    )

    # Mock consistency pass and translation functions
    with patch.object(orchestrator, 'plan', return_value=mock_plan), \
         patch('app.chapter.orchestrator.run_consistency_pass') as mock_run_consistency, \
         patch('app.chapter.orchestrator.translate_draft') as mock_translate_draft, \
         patch('app.chapter.orchestrator.polish_translation') as mock_polish_translation:

        # Setup mock returns
        mock_draft_output = TranslationOutput(
            segment_id="1",
            draft_translation="Draft text",
            polished_translation="",
        )
        mock_final_output = TranslationOutput(
            segment_id="1",
            draft_translation="Draft text",
            polished_translation="Polished text",
        )
        mock_translate_draft.return_value = mock_draft_output
        mock_polish_translation.return_value = mock_final_output

        mock_run_consistency.return_value = (
            "Corrected text",
            MagicMock(get_summary=lambda: {"total_issues": 0}),
            MagicMock(get_summary=lambda: {"total_corrections": 0}, has_corrections=False),
        )

        # Call run_with_manifest (which will use our mocked plan)
        result = orchestrator.run_with_manifest(
            source_text="Test chapter",
            glossary=[],
            manifest_path=None,
        )

        # Verify run_consistency_pass was called with intensity="enhanced"
        assert mock_run_consistency.called
        call_args = mock_run_consistency.call_args
        assert 'intensity' in call_args.kwargs
        assert call_args.kwargs['intensity'] == "enhanced"
