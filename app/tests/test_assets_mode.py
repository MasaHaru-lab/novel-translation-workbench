"""Focused prompt-construction checks for the assets_mode control.

Proves that:
  - default behavior (mode="full") is unchanged and injects the assets block
  - mode="none" skips the assets block entirely
  - invalid mode values are rejected
  - non-asset content (instructions, source text, glossary, context) is
    identical between modes — only the assets block differs
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from app.translate.schema import GlossaryTerm, TranslationInput, TranslationOutput
from app.translate.translator import (
    ASSETS_MODES,
    DEFAULT_ASSETS_MODE,
    build_draft_prompt,
    build_polish_prompt,
    build_project_assets_block,
    polish_translation,
    translate_draft,
    translate_polish_with_backend,
)


ASSETS_HEADER = "Project memory (authoritative reference"


def _input() -> TranslationInput:
    return TranslationInput(
        segment_id="t1",
        source_text="大小姐 called 王爷",
        prev_context="前文。",
        next_context="后文。",
        glossary_terms=[GlossaryTerm(zh="大小姐", en="Young Lady")],
    )


def test_default_mode_is_full():
    """Default mode preserves existing behavior (backwards compatibility)."""
    assert DEFAULT_ASSETS_MODE == "full"
    assert build_draft_prompt(_input()) == build_draft_prompt(_input(), "full")


def test_assets_block_full_vs_none():
    """Assets block is non-empty in 'full' mode and empty in 'none' mode."""
    full = build_project_assets_block("full")
    none = build_project_assets_block("none")
    assert none == ""
    # 'full' will have content iff any asset file exists on disk; if the
    # project has at least one asset, the block must carry the header.
    if full:
        assert ASSETS_HEADER in full


def test_draft_prompt_differs_between_modes():
    inp = _input()
    full_prompt = build_draft_prompt(inp, "full")
    none_prompt = build_draft_prompt(inp, "none")

    # 'none' must not contain the assets block header.
    assert ASSETS_HEADER not in none_prompt
    # If any asset exists, 'full' must contain it — proving the modes differ.
    if build_project_assets_block("full"):
        assert ASSETS_HEADER in full_prompt
        assert full_prompt != none_prompt
        assert len(full_prompt) > len(none_prompt)

    # Non-asset content should be identical between modes.
    for needle in [
        "Original Chinese text:",
        inp.source_text,
        "Glossary terms",
        "大小姐 → Young Lady",
        "Previous segment",
        inp.prev_context,
        "Next segment",
        inp.next_context,
        "Draft translation:",
    ]:
        assert needle in full_prompt
        assert needle in none_prompt


def test_polish_prompt_differs_between_modes():
    inp = _input()
    draft = "Young Lady called Prince."
    full_prompt = build_polish_prompt(inp, draft, "full")
    none_prompt = build_polish_prompt(inp, draft, "none")

    assert ASSETS_HEADER not in none_prompt
    if build_project_assets_block("full"):
        assert ASSETS_HEADER in full_prompt
        assert full_prompt != none_prompt

    for needle in ["Draft translation to polish:", draft, "Polished translation:"]:
        assert needle in full_prompt
        assert needle in none_prompt


def _assert_raises_value_error(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError(f"expected ValueError from {fn!r}")


def test_invalid_mode_rejected():
    _assert_raises_value_error(lambda: build_project_assets_block("partial"))
    _assert_raises_value_error(lambda: build_draft_prompt(_input(), "bogus"))
    _assert_raises_value_error(lambda: build_polish_prompt(_input(), "draft", ""))


def test_modes_enumerated():
    assert set(ASSETS_MODES) == {"full", "none"}


# ---------------------------------------------------------------------------
# Translation-call layer: prove assets_mode now flows through the higher-level
# functions (translate_draft / polish_translation / translate_polish_with_backend),
# not just the prompt builders.
# ---------------------------------------------------------------------------


class _PromptCapture:
    """Context manager that captures prompts sent to call_model_backend."""

    def __init__(self, return_value: str = "mock-output"):
        self.return_value = return_value
        self.prompts: list[str] = []

    def __enter__(self):
        from app.config import config
        original_env = os.environ.get('MODEL_BACKEND_URL')
        self._original_env = original_env
        # config.MODEL_BACKEND_URL is frozen at config-module import time
        # from env, so setting the env var alone isn't enough once another
        # test has already caused app.config to load. Patch the attribute too.
        self._config_patcher = patch.object(
            config,
            'MODEL_BACKEND_URL',
            'http://test-backend.example.com/generate',
        )
        self._config_patcher.start()
        os.environ['MODEL_BACKEND_URL'] = 'http://test-backend.example.com/generate'

        def fake_backend(prompt: str, **kwargs) -> str:
            self.prompts.append(prompt)
            return self.return_value

        # Patch where backend_adapter is imported; translator imports it
        # lazily inside the functions.
        self._patcher = patch(
            'app.translate.backend_adapter.call_model_backend',
            side_effect=fake_backend,
        )
        self._patcher.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._patcher.stop()
        self._config_patcher.stop()
        if self._original_env is not None:
            os.environ['MODEL_BACKEND_URL'] = self._original_env
        else:
            os.environ.pop('MODEL_BACKEND_URL', None)


def test_translate_draft_default_forwards_full_mode():
    """Calling translate_draft with no assets_mode preserves existing behavior."""
    if not build_project_assets_block("full"):
        return  # No assets on disk; default-vs-none comparison is meaningless.
    with _PromptCapture(return_value="draft-result") as cap:
        out = translate_draft(_input())
    assert out.draft_translation.startswith("draft-result") or "draft-result" in out.draft_translation
    assert len(cap.prompts) == 1
    assert ASSETS_HEADER in cap.prompts[0]


def test_translate_draft_none_suppresses_asset_injection():
    """assets_mode='none' at the translation-call layer removes the assets block."""
    with _PromptCapture(return_value="draft-result") as cap:
        translate_draft(_input(), assets_mode="none")
    assert len(cap.prompts) == 1
    assert ASSETS_HEADER not in cap.prompts[0]
    # Non-asset content is still present.
    assert "Original Chinese text:" in cap.prompts[0]
    assert _input().source_text in cap.prompts[0]


def test_translate_draft_full_vs_none_differ_at_call_layer():
    """Higher-level forwarding produces distinct prompts for 'full' vs 'none'."""
    if not build_project_assets_block("full"):
        return
    with _PromptCapture() as cap:
        translate_draft(_input(), assets_mode="full")
        translate_draft(_input(), assets_mode="none")
    full_prompt, none_prompt = cap.prompts
    assert ASSETS_HEADER in full_prompt
    assert ASSETS_HEADER not in none_prompt
    assert full_prompt != none_prompt


def _capture_polish_prompts(draft_output, **polish_kwargs):
    """Run polish_translation and return the list of prompts hit on the backend.

    Uses a scripted backend: the review call returns reviewer scaffolding
    that flags a major_issue, the revision call returns prose. This guarantees
    both prompts (review + revision) are observed.
    """
    from app.config import config
    review_reply = (
        "major_issue: register drift\n"
        "recommended_fix: restore neutral tone\n"
    )
    revision_reply = "Young Lady spoke to the Prince."
    captured: list[str] = []

    def fake_backend(prompt: str, **kwargs) -> str:
        captured.append(prompt)
        if "English translation under review:" in prompt:
            return review_reply
        return revision_reply

    with patch.object(
        config, 'MODEL_BACKEND_URL', 'http://test-backend.example.com/generate'
    ), patch(
        'app.translate.backend_adapter.call_model_backend',
        side_effect=fake_backend,
    ):
        polish_translation(_input(), draft_output, **polish_kwargs)
    return captured


def test_polish_translation_none_suppresses_asset_injection():
    """polish_translation forwards assets_mode='none' through every prompt in
    the A → B → revise workflow (review + revision)."""
    draft_output = TranslationOutput(
        segment_id="t1",
        draft_translation="Young Lady called Prince.",
        polished_translation="",
        notes=[],
    )
    prompts = _capture_polish_prompts(draft_output, assets_mode="none")
    # Review + revision prompts both captured.
    assert len(prompts) == 2
    for p in prompts:
        assert ASSETS_HEADER not in p
        assert draft_output.draft_translation in p
    assert "English translation under review:" in prompts[0]
    assert "Draft translation to polish:" in prompts[1]


def test_polish_translation_default_forwards_full_mode():
    if not build_project_assets_block("full"):
        return
    draft_output = TranslationOutput(
        segment_id="t1",
        draft_translation="Young Lady called Prince.",
        polished_translation="",
        notes=[],
    )
    prompts = _capture_polish_prompts(draft_output)
    assert len(prompts) == 2
    for p in prompts:
        assert ASSETS_HEADER in p


def test_translate_polish_with_backend_forwards_mode():
    """The backend-facing polish helper also accepts and forwards assets_mode."""
    with _PromptCapture(return_value="polished-result") as cap:
        translate_polish_with_backend(_input(), "draft text", assets_mode="none")
    assert ASSETS_HEADER not in cap.prompts[0]


def test_translate_draft_invalid_mode_rejected():
    _assert_raises_value_error(lambda: translate_draft(_input(), assets_mode="bogus"))


def test_polish_translation_invalid_mode_rejected():
    draft_output = TranslationOutput(
        segment_id="t1",
        draft_translation="x",
        polished_translation="",
        notes=[],
    )
    _assert_raises_value_error(
        lambda: polish_translation(_input(), draft_output, assets_mode="partial")
    )


# ---------------------------------------------------------------------------
# Orchestration layer: prove assets_mode flows through run_pipeline end-to-end
# (the smallest orchestration step above the translation-call functions).
# ---------------------------------------------------------------------------


def _run_pipeline_capturing_prompts(assets_mode_kwargs: dict) -> list[str]:
    """Invoke run_pipeline with a single mock segment and capture the prompts
    that hit the backend.

    The orchestration layer runs draft + review + (conditional) revision. We
    force the reviewer to flag a major issue so the revision pass also runs —
    that way all three prompts are observable for the assets-mode check.
    """
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from app.cli import run_pipeline
    from app.segment.segmenter import Segment

    seg = Segment(
        segment_id=1,
        text="大小姐 called 王爷",
        prev_segment_text="前文。",
        next_segment_text="后文。",
    )

    from app.config import config
    captured: list[str] = []

    def fake_backend(prompt: str, **kwargs) -> str:
        captured.append(prompt)
        if "English translation under review:" in prompt:
            return (
                "major_issue: register drift\n"
                "recommended_fix: restore neutral tone\n"
            )
        return "mock-output"

    with patch.object(
        config, 'MODEL_BACKEND_URL', 'http://test-backend.example.com/generate'
    ), patch(
        'app.translate.backend_adapter.call_model_backend',
        side_effect=fake_backend,
    ), patch("app.cli.create_segments", return_value=[seg]), patch(
        "app.cli.mock_glossary", return_value=[]
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "source.txt"
            output_path = Path(tmpdir) / "output.md"
            source_path.write_text("Test text", encoding="utf-8")
            run_pipeline(
                source_path,
                output_path,
                service_url=None,
                allow_mock_fallback=False,
                **assets_mode_kwargs,
            )
    return captured


def test_run_pipeline_default_forwards_full_mode():
    """run_pipeline with no assets_mode argument preserves 'full' behavior."""
    if not build_project_assets_block("full"):
        return
    prompts = _run_pipeline_capturing_prompts({})
    # Three prompts: draft + review + revision. All three carry assets block.
    assert len(prompts) == 3
    for p in prompts:
        assert ASSETS_HEADER in p


def test_run_pipeline_none_suppresses_asset_injection():
    """run_pipeline(..., assets_mode='none') must suppress asset injection in
    every prompt emitted by the orchestration layer."""
    prompts = _run_pipeline_capturing_prompts({"assets_mode": "none"})
    assert len(prompts) == 3
    for p in prompts:
        assert ASSETS_HEADER not in p
    # Draft prompt carries the source.
    assert "Original Chinese text:" in prompts[0]
    # Review prompt carries the reviewer marker.
    assert "English translation under review:" in prompts[1]
    # Revision prompt carries the polish marker.
    assert "Draft translation to polish:" in prompts[2]


def test_run_pipeline_full_vs_none_differ():
    """Orchestration-layer forwarding produces distinct prompts for full vs none."""
    if not build_project_assets_block("full"):
        return
    full_prompts = _run_pipeline_capturing_prompts({"assets_mode": "full"})
    none_prompts = _run_pipeline_capturing_prompts({"assets_mode": "none"})
    assert ASSETS_HEADER in full_prompts[0]
    assert ASSETS_HEADER not in none_prompts[0]
    assert full_prompts[0] != none_prompts[0]
    assert full_prompts[1] != none_prompts[1]


def test_run_pipeline_invalid_mode_rejected():
    """Invalid assets_mode fails cleanly at the orchestration layer."""
    import tempfile
    from pathlib import Path

    from app.cli import run_pipeline

    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "source.txt"
        output_path = Path(tmpdir) / "output.md"
        source_path.write_text("Test text", encoding="utf-8")
        _assert_raises_value_error(
            lambda: run_pipeline(
                source_path,
                output_path,
                service_url=None,
                allow_mock_fallback=False,
                assets_mode="bogus",
            )
        )


if __name__ == "__main__":
    test_default_mode_is_full()
    test_assets_block_full_vs_none()
    test_draft_prompt_differs_between_modes()
    test_polish_prompt_differs_between_modes()
    test_invalid_mode_rejected()
    test_modes_enumerated()
    test_translate_draft_default_forwards_full_mode()
    test_translate_draft_none_suppresses_asset_injection()
    test_translate_draft_full_vs_none_differ_at_call_layer()
    test_polish_translation_none_suppresses_asset_injection()
    test_polish_translation_default_forwards_full_mode()
    test_translate_polish_with_backend_forwards_mode()
    test_translate_draft_invalid_mode_rejected()
    test_polish_translation_invalid_mode_rejected()
    test_run_pipeline_default_forwards_full_mode()
    test_run_pipeline_none_suppresses_asset_injection()
    test_run_pipeline_full_vs_none_differ()
    test_run_pipeline_invalid_mode_rejected()
    print("All assets_mode tests passed.")
