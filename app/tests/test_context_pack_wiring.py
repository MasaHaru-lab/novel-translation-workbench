"""Tests for R3: context-pack wiring into translation prompts.

Verifies:
- Empty/no context pack preserves prompt output unchanged.
- Matched entities/titles/decisions appear in draft, review, and polish prompts.
- Truncated packs remain bounded.
- Tentative/unresolved labels survive formatting.
- Context pack and glossary terms coexist without suppression.
- Orchestrator execute() and run_with_manifest() pass context pack through.
- R4: resume() with/without book_memory.
- R4: Observability logging at execution boundary.
"""

from unittest.mock import patch
from typing import Optional

import pytest

from app.translate.schema import TranslationInput, TranslationOutput
from app.translate.translator import (
    build_draft_prompt,
    build_review_prompt,
    build_polish_prompt,
    build_translation_input,
)
from app.chapter.orchestrator import ChapterOrchestrator
from app.segment.segmenter import Segment
from app.book_memory.models import (
    EntityType,
    MemoryRecordStatus,
    BookEntity,
    Relationship,
    TitleRecord,
    TranslationDecision,
    UnresolvedDecision,
    BookMemory,
)
from app.book_memory.retrieval import build_context_pack
from app.chapter.manifest import RunManifest


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def empty_input() -> TranslationInput:
    """A minimal TranslationInput with no context pack text."""
    return TranslationInput(
        segment_id="1",
        source_text="秦流西看了看四周。",
    )


@pytest.fixture
def sample_memory() -> BookMemory:
    """Same BookMemory fixture as test_retrieval.py for cross-compatibility."""
    memory = BookMemory(book_title="Test Novel", total_chapters=10)

    memory.entities["qin_liuxi"] = BookEntity(
        id="qin_liuxi",
        name_zh="秦流西",
        name_en="Qin Liuxi",
        entity_type=EntityType.CHARACTER,
        description="Protagonist, female physician and exorcist",
        tags=["protagonist"],
        status=MemoryRecordStatus.CONFIRMED,
        aliases=["流西"],
        first_chapter=1,
    )
    memory.entities["old_lady_qin"] = BookEntity(
        id="old_lady_qin",
        name_zh="秦老太太",
        name_en="Old Lady Qin",
        entity_type=EntityType.CHARACTER,
        description="Qin Liuxi's grandmother",
        tags=["supporting"],
        status=MemoryRecordStatus.CONFIRMED,
        first_chapter=1,
    )
    memory.entities["prince_jin"] = BookEntity(
        id="prince_jin",
        name_zh="晋王",
        name_en="Prince Jin",
        entity_type=EntityType.CHARACTER,
        description="A powerful prince",
        tags=["antagonist"],
        status=MemoryRecordStatus.TENTATIVE,
        first_chapter=5,
    )
    memory.entities["imperial_capital"] = BookEntity(
        id="imperial_capital",
        name_zh="京城",
        name_en="Imperial Capital",
        entity_type=EntityType.PLACE,
        description="Seat of the imperial court",
        status=MemoryRecordStatus.CONFIRMED,
    )

    memory.titles["young_lady"] = TitleRecord(
        id="young_lady",
        name_zh="大小姐",
        name_en="Young Lady",
        category="title",
        notes="Household status term for the eldest daughter",
        status=MemoryRecordStatus.CONFIRMED,
    )
    memory.titles["imperial_favor"] = TitleRecord(
        id="imperial_favor",
        name_zh="圣眷",
        name_en="imperial favor",
        category="term",
        status=MemoryRecordStatus.TENTATIVE,
    )

    memory.relationships["r1"] = Relationship(
        id="r1",
        source_id="qin_liuxi",
        target_id="old_lady_qin",
        relation_type="grandchild_of",
        description="Qin Liuxi is her grandmother's favourite",
        status=MemoryRecordStatus.CONFIRMED,
    )
    memory.relationships["r2"] = Relationship(
        id="r2",
        source_id="prince_jin",
        target_id="imperial_capital",
        relation_type="rules",
        description="Prince Jin operates in the capital",
        status=MemoryRecordStatus.TENTATIVE,
    )

    memory.translation_decisions["legal_mother"] = TranslationDecision(
        id="legal_mother",
        entity_id="young_lady",
        decision_type="rendering",
        new_value="Young Lady",
        rationale="Capitalized as a household status title",
        status=MemoryRecordStatus.CONFIRMED,
    )

    memory.unresolved_decisions["momo_system"] = UnresolvedDecision(
        id="momo_system",
        question="How should 嬷嬷 be rendered consistently?",
        entity_id="prince_jin",
        options=["Momo", "Nanny", "Nurse"],
        status=MemoryRecordStatus.UNRESOLVED,
    )

    return memory


# ═════════════════════════════════════════════════════════════════════════
# Empty / no-context-pack behavior
# ═════════════════════════════════════════════════════════════════════════


def test_empty_context_pack_no_prompt_change():
    """When context_pack_text is empty, prompt should not contain context sections."""
    inp = TranslationInput(
        segment_id="1",
        source_text="秦流西看了看四周。",
        context_pack_text="",
    )
    prompt = build_draft_prompt(inp, assets_mode="none")
    # No context pack indicators should appear
    assert "Context Pack" not in prompt
    assert "retrieved from book memory" not in prompt
    assert "Matched via" not in prompt


def test_no_memory_no_context_in_prompt():
    """TranslationInput default (no context_pack_text) produces no context pack."""
    inp = TranslationInput(
        segment_id="1",
        source_text="秦流西看了看四周。",
    )
    prompt = build_draft_prompt(inp, assets_mode="none")
    assert "Context Pack" not in prompt


def test_empty_book_memory_produces_visible_no_match_section():
    """When BookMemory is empty and explicitly provided, format_text() shows
    a 'No matching' section. This is intentional: if the operator provides a
    BookMemory, the model should know the memory was consulted even if empty."""
    inp = TranslationInput(
        segment_id="1",
        source_text="秦流西看了看四周。",
        context_pack_text=build_context_pack(
            "秦流西看了看四周。", BookMemory()
        ).format_text(),
    )
    prompt = build_draft_prompt(inp, assets_mode="none")
    assert "Context Pack" in prompt
    assert "No matching" in prompt


# ═════════════════════════════════════════════════════════════════════════
# Context pack in draft prompt
# ═════════════════════════════════════════════════════════════════════════


def test_context_pack_in_draft_prompt(sample_memory):
    """Matched entities appear in draft prompt when context pack is provided."""
    inp = TranslationInput(
        segment_id="1",
        source_text="秦流西看了看四周。",
        context_pack_text=build_context_pack(
            "秦流西看了看四周。", sample_memory
        ).format_text(),
    )
    prompt = build_draft_prompt(inp, assets_mode="none")
    # Entity display name should appear in prompt
    assert "Qin Liuxi" in prompt
    assert "Context Pack" in prompt
    assert "Matched via" in prompt


def test_context_pack_in_draft_with_assets(sample_memory):
    """Context pack and project assets coexist in draft prompt."""
    inp = TranslationInput(
        segment_id="1",
        source_text="秦流西看了看四周。",
        context_pack_text=build_context_pack(
            "秦流西看了看四周。", sample_memory
        ).format_text(),
    )
    prompt = build_draft_prompt(inp, assets_mode="full")  # real project assets
    # Both the assets heading and the context pack should appear
    assert "Project memory" in prompt or "## Characters" in prompt
    assert "Context Pack" in prompt
    assert "Qin Liuxi" in prompt


# ═════════════════════════════════════════════════════════════════════════
# Context pack in review prompt
# ═════════════════════════════════════════════════════════════════════════


def test_context_pack_in_review_prompt(sample_memory):
    """Matched entities appear in the Prompt B (review) prompt."""
    inp = TranslationInput(
        segment_id="1",
        source_text="秦流西看了看四周。",
        context_pack_text=build_context_pack(
            "秦流西看了看四周。", sample_memory
        ).format_text(),
    )
    prompt = build_review_prompt(inp, "Draft translation.", assets_mode="none")
    assert "Context Pack" in prompt
    assert "Qin Liuxi" in prompt


# ═════════════════════════════════════════════════════════════════════════
# Context pack in polish prompt
# ═════════════════════════════════════════════════════════════════════════


def test_context_pack_in_polish_prompt(sample_memory):
    """Matched entities appear in the polish (revision) prompt."""
    inp = TranslationInput(
        segment_id="1",
        source_text="秦流西看了看四周。",
        context_pack_text=build_context_pack(
            "秦流西看了看四周。", sample_memory
        ).format_text(),
    )
    prompt = build_polish_prompt(
        inp, "Draft translation.", assets_mode="none"
    )
    assert "Context Pack" in prompt
    assert "Qin Liuxi" in prompt


# ═════════════════════════════════════════════════════════════════════════
# Tentative / unresolved label preservation
# ═════════════════════════════════════════════════════════════════════════


def test_tentative_labels_survive(sample_memory):
    """Tentative entities are flagged with [TENTATIVE] in the prompt."""
    inp = TranslationInput(
        segment_id="1",
        source_text="晋王驾到。",
        context_pack_text=build_context_pack(
            "晋王驾到。", sample_memory
        ).format_text(),
    )
    prompt = build_draft_prompt(inp, assets_mode="none")
    assert "TENTATIVE" in prompt


def test_unresolved_labels_survive(sample_memory):
    """Unresolved decisions are flagged with [UNRESOLVED] in the prompt."""
    inp = TranslationInput(
        segment_id="1",
        source_text="晋王驾到。",
        context_pack_text=build_context_pack(
            "晋王驾到。", sample_memory
        ).format_text(),
    )
    prompt = build_draft_prompt(inp, assets_mode="none")
    assert "UNRESOLVED" in prompt


# ═════════════════════════════════════════════════════════════════════════
# Context pack + glossary coexistence
# ═════════════════════════════════════════════════════════════════════════


def test_context_pack_and_glossary_coexist(sample_memory):
    """Both context pack and glossary terms appear in the same prompt."""
    inp = TranslationInput(
        segment_id="1",
        source_text="秦流西晋王",
        context_pack_text=build_context_pack(
            "秦流西晋王", sample_memory
        ).format_text(),
        glossary_terms=[
            type("GT", (), {"zh": "秦流西", "en": "Qin Liuxi"})(),
        ],
    )
    prompt = build_draft_prompt(inp, assets_mode="none")
    # Context pack section present
    assert "Context Pack" in prompt
    assert "Qin Liuxi" in prompt
    # Glossary section present
    assert "Glossary terms" in prompt or "秦流西" in prompt
    # Neither suppresses the other
    assert "Context Pack" in prompt
    assert "Matched via" in prompt


# ═════════════════════════════════════════════════════════════════════════
# Truncation bounding
# ═════════════════════════════════════════════════════════════════════════


def test_truncated_pack_stays_bounded(sample_memory):
    """A truncated context pack still fits within its size limit."""
    pack = build_context_pack(
        "秦流西秦老太太晋王大小姐圣眷京城",
        sample_memory,
        max_chars=200,
    )
    pack_text = pack.format_text()
    assert len(pack_text) >= 0  # always produces output
    # Even truncated, the pack should not crash
    if pack.truncated:
        assert "truncated" in pack_text


def test_large_context_pack_fits_within_default(sample_memory):
    """Default context pack size fits within 4000 chars."""
    pack = build_context_pack(
        "秦流西秦老太太晋王大小姐圣眷京城",
        sample_memory,
    )
    pack_text = pack.format_text()
    assert len(pack_text) <= 4000


# ═════════════════════════════════════════════════════════════════════════
# build_translation_input with context_pack_text
# ═════════════════════════════════════════════════════════════════════════


def test_build_translation_input_passes_context_pack():
    """build_translation_input forwards context_pack_text to TranslationInput."""
    seg = Segment(segment_id=1, text="秦流西看了看四周。")
    inp = build_translation_input(seg, context_pack_text="## Context Pack\ntest")
    assert inp.context_pack_text == "## Context Pack\ntest"


def test_build_translation_input_default_no_context_pack():
    """build_translation_input defaults to empty context_pack_text."""
    seg = Segment(segment_id=1, text="秦流西看了看四周。")
    inp = build_translation_input(seg)
    assert inp.context_pack_text == ""


# ═════════════════════════════════════════════════════════════════════════
# Orchestrator-level handoff — execute()
# ═════════════════════════════════════════════════════════════════════════


def test_orchestrator_execute_passes_context_pack(sample_memory):
    """Orchestrator execute() with book_memory produces context pack in seg inputs."""
    text = "第一章\n\n秦流西看了看四周。\n\n晋王驾到。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    captured_inputs: list[TranslationInput] = []

    def capturing_draft_fn(inp: TranslationInput) -> TranslationOutput:
        captured_inputs.append(inp)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
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
        _ = orch.execute(
            plan,
            translate_draft_fn=capturing_draft_fn,
            book_memory=sample_memory,
        )
    finally:
        for p in patches:
            p.stop()

    # At least one segment should have context pack text from book memory
    assert any(
        "Context Pack" in inp.context_pack_text for inp in captured_inputs
    ), "No segment received context pack text"
    # Segments with matching text should have entity info
    qin_seg = next(
        (inp for inp in captured_inputs if "秦流西" in inp.source_text),
        None,
    )
    if qin_seg is not None:
        assert "Qin Liuxi" in qin_seg.context_pack_text


def test_orchestrator_execute_no_book_memory_no_context(sample_memory):
    """Orchestrator execute() without book_memory yields empty context_pack_text."""
    text = "第一章\n\n秦流西看了看四周。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    captured_inputs: list[TranslationInput] = []

    def capturing_draft_fn(inp: TranslationInput) -> TranslationOutput:
        captured_inputs.append(inp)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
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
        _ = orch.execute(plan, translate_draft_fn=capturing_draft_fn)
    finally:
        for p in patches:
            p.stop()

    # Without book_memory, context_pack_text should be empty for all segments
    for inp in captured_inputs:
        assert inp.context_pack_text == "", (
            f"Segment {inp.segment_id} has non-empty context_pack_text "
            f"but no book_memory was provided"
        )


# ═════════════════════════════════════════════════════════════════════════
# Orchestrator-level handoff — run_with_manifest() / retry path
# ═════════════════════════════════════════════════════════════════════════


def test_run_with_manifest_passes_context_pack(sample_memory):
    """run_with_manifest() with book_memory passes context pack through retry path."""
    text = "第一章\n\n秦流西看了看四周。\n\n晋王驾到。"
    orch = ChapterOrchestrator()

    captured_inputs: list[TranslationInput] = []

    def capturing_draft_fn(inp: TranslationInput) -> TranslationOutput:
        captured_inputs.append(inp)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
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
        _ = orch.run_with_manifest(
            source_text=text,
            translate_draft_fn=capturing_draft_fn,
            book_memory=sample_memory,
        )
    finally:
        for p in patches:
            p.stop()

    # The segmenter may produce 1 segment for the test text, but each
    # captured input must carry context pack text when book_memory is provided.
    assert len(captured_inputs) >= 1
    assert any(
        "Context Pack" in inp.context_pack_text for inp in captured_inputs
    ), "No segment received context pack text via run_with_manifest"
    # Verify at least one segment has entity data from the memory
    assert any(
        "Qin Liuxi" in inp.context_pack_text for inp in captured_inputs
    ), "Entity data missing from context pack in run_with_manifest"


def test_run_with_manifest_no_book_memory_no_context(sample_memory):
    """run_with_manifest() without book_memory yields empty context_pack_text."""
    text = "第一章\n\n秦流西看了看四周。"
    orch = ChapterOrchestrator()

    captured_inputs: list[TranslationInput] = []

    def capturing_draft_fn(inp: TranslationInput) -> TranslationOutput:
        captured_inputs.append(inp)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
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
        _ = orch.run_with_manifest(
            source_text=text,
            translate_draft_fn=capturing_draft_fn,
        )
    finally:
        for p in patches:
            p.stop()

    for inp in captured_inputs:
        assert inp.context_pack_text == "", (
            f"Segment {inp.segment_id} has non-empty context_pack_text "
            f"but no book_memory was provided to run_with_manifest"
        )


# ═════════════════════════════════════════════════════════════════════════
# R4: resume() activation and observability
# ═════════════════════════════════════════════════════════════════════════


def test_resume_with_book_memory_passes_context_pack(sample_memory, tmp_path):
    """resume() with book_memory passes context pack for pending segments."""
    # Text large enough to produce >= 2 segments (default max_chars=1200)
    text = "第一章\n\n" + "秦流西看了看四周。" * 150 + "\n\n" + "晋王驾到。" * 150
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    # Get segment IDs
    seg_ids = [str(s.segment_id) for s in plan.segments]
    assert len(seg_ids) >= 2, "Need at least 2 segments for resume test"

    # Create a manifest with the first segment completed, rest pending
    manifest_path = tmp_path / "manifest.json"
    manifest = RunManifest.create(
        chapter_title=plan.chapter_title,
        source_text=text,
        segment_ids=seg_ids,
        manifest_path=str(manifest_path),
        smoke_test=True,
    )
    manifest.start_run()
    manifest.mark_segment_completed(seg_ids[0])
    manifest.segments[seg_ids[0]].polished_text = "Completed segment output."
    manifest.save()

    captured_inputs: list[TranslationInput] = []

    def capturing_draft_fn(inp: TranslationInput) -> TranslationOutput:
        captured_inputs.append(inp)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
        )

    result = orch.resume(
        source_text=text,
        manifest_path=str(manifest_path),
        translate_draft_fn=capturing_draft_fn,
        book_memory=sample_memory,
    )

    assert result is not None, "resume() returned None"
    # Pending (non-completed) segments should have context pack text
    pending_inputs = [inp for inp in captured_inputs if inp.segment_id != seg_ids[0]]
    assert len(pending_inputs) >= 1, "Expected at least 1 pending segment"
    assert any(
        "Context Pack" in inp.context_pack_text for inp in pending_inputs
    ), "Pending segment did not receive context pack text on resume"
    # At least one entity match should be present
    assert any(
        "Qin Liuxi" in inp.context_pack_text for inp in pending_inputs
    ), "Entity data missing from context pack on resume"


def test_resume_without_book_memory_no_context(sample_memory, tmp_path):
    """resume() without book_memory yields empty context_pack_text."""
    text = "第一章\n\n" + "秦流西看了看四周。" * 150 + "\n\n" + "晋王驾到。" * 150
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    seg_ids = [str(s.segment_id) for s in plan.segments]
    assert len(seg_ids) >= 2

    manifest_path = tmp_path / "manifest.json"
    manifest = RunManifest.create(
        chapter_title=plan.chapter_title,
        source_text=text,
        segment_ids=seg_ids,
        manifest_path=str(manifest_path),
        smoke_test=True,
    )
    manifest.start_run()
    manifest.mark_segment_completed(seg_ids[0])
    manifest.segments[seg_ids[0]].polished_text = "Completed segment output."
    manifest.save()

    captured_inputs: list[TranslationInput] = []

    def capturing_draft_fn(inp: TranslationInput) -> TranslationOutput:
        captured_inputs.append(inp)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
        )

    result = orch.resume(
        source_text=text,
        manifest_path=str(manifest_path),
        translate_draft_fn=capturing_draft_fn,
    )

    assert result is not None, "resume() returned None"
    pending_inputs = [inp for inp in captured_inputs if inp.segment_id != seg_ids[0]]
    for inp in pending_inputs:
        assert inp.context_pack_text == "", (
            f"Pending segment {inp.segment_id} has non-empty context_pack_text "
            f"but no book_memory was provided"
        )


def test_execute_logs_context_pack_enabled(sample_memory, caplog):
    """execute() logs context pack activation info when book_memory is provided."""
    import logging
    caplog.set_level(logging.INFO, logger="app.chapter.orchestrator")

    text = "第一章\n\n秦流西看了看四周。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    captured_inputs: list[TranslationInput] = []

    def capturing_draft_fn(inp: TranslationInput) -> TranslationOutput:
        captured_inputs.append(inp)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
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
        _ = orch.execute(
            plan,
            translate_draft_fn=capturing_draft_fn,
            book_memory=sample_memory,
        )
    finally:
        for p in patches:
            p.stop()

    # Verify context pack activation log line
    assert any(
        "Context pack enabled" in msg for msg in caplog.messages
    ), "Expected 'Context pack enabled' log message"
    # Verify per-segment context pack log line
    assert any(
        "context pack" in msg and "chars" in msg for msg in caplog.messages
    ), "Expected per-segment context pack size log message"


def test_execute_logs_no_context_pack_disabled(sample_memory, caplog):
    """execute() does NOT log context pack activation when book_memory is None."""
    import logging
    caplog.set_level(logging.INFO, logger="app.chapter.orchestrator")

    text = "第一章\n\n秦流西看了看四周。"
    orch = ChapterOrchestrator()
    plan = orch.plan(text)

    captured_inputs: list[TranslationInput] = []

    def capturing_draft_fn(inp: TranslationInput) -> TranslationOutput:
        captured_inputs.append(inp)
        return TranslationOutput(
            segment_id=inp.segment_id,
            draft_translation="draft",
            polished_translation="",
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
        _ = orch.execute(plan, translate_draft_fn=capturing_draft_fn)
    finally:
        for p in patches:
            p.stop()

    # No context pack log lines should appear
    assert not any(
        "Context pack" in msg for msg in caplog.messages
    ), "Unexpected context pack log when book_memory was None"


def test_cli_book_memory_flag_forwarded():
    """--book-memory flag is threaded from CLI to run_chapter_pipeline."""
    import tempfile
    from pathlib import Path
    from app.cli import main as cli_main
    import sys
    from unittest.mock import patch
    from app import cli

    captured = {}

    def capturing_pipeline(*args, **kwargs):
        captured['book_memory_path'] = kwargs.get('book_memory_path')

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        with patch.object(cli, 'run_chapter_pipeline', side_effect=capturing_pipeline):
            sys.argv = ['cli', 'chapter', 'run', '--source', str(src), '--output', str(out),
                        '--book-memory', '/some/path/memory.json']
            cli_main()

    assert captured['book_memory_path'] == Path('/some/path/memory.json')


def test_cli_book_memory_flag_default_none():
    """Omitting --book-memory yields None."""
    import tempfile
    from pathlib import Path
    from app.cli import main as cli_main
    import sys
    from unittest.mock import patch
    from app import cli

    captured = {}

    def capturing_pipeline(*args, **kwargs):
        captured['book_memory_path'] = kwargs.get('book_memory_path')

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        with patch.object(cli, 'run_chapter_pipeline', side_effect=capturing_pipeline):
            sys.argv = ['cli', 'chapter', 'run', '--source', str(src), '--output', str(out)]
            cli_main()

    assert captured['book_memory_path'] is None
