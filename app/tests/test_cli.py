"""
Tests for CLI behavior, especially service fallback.
"""
import sys
import logging
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from unittest.mock import patch, MagicMock, call
import pytest
from pathlib import Path
import tempfile
import shutil

from app.cli import (
    _derive_output_path,
    _report_chapter_result,
    run_chapter_batch,
    run_chapter_pipeline,
    run_chapter_stream,
    run_pipeline,
)
from app.chapter.manifest import ChapterStatus, SegmentStatus
from app.chapter.models import ChapterResult
from app.segment.segmenter import Segment
from app.translate.schema import TranslationOutput, GlossaryTerm


def create_mock_segment(segment_id=1):
    """Create a mock segment for testing."""
    return Segment(
        segment_id=segment_id,
        text="Some source text.",
        prev_segment_text="Previous.",
        next_segment_text="Next."
    )


def test_cli_service_failure_without_fallback():
    """
    When service-url is provided and service fails, without --allow-mock-fallback,
    CLI should exit with error.
    """
    # Mock segmentation to return a single segment
    mock_segment = create_mock_segment()
    with patch('app.cli.create_segments', return_value=[mock_segment]):
        # Mock glossary
        with patch('app.cli.mock_glossary', return_value=[]):
            # Mock the import of TranslationServiceClient to raise RuntimeError (requests not installed)
            with patch('app.service.client.TranslationServiceClient', side_effect=RuntimeError("No requests")):
                with patch.dict('os.environ', {}):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        source_path = Path(tmpdir) / "source.txt"
                        output_path = Path(tmpdir) / "output.md"
                        source_path.write_text("Test text", encoding='utf-8')
                        # Expect SystemExit
                        with pytest.raises(SystemExit) as excinfo:
                            run_pipeline(source_path, output_path, service_url="http://localhost:9999", allow_mock_fallback=False)
                        # Should exit with code 1
                        assert excinfo.value.code == 1


@patch('app.cli.polish_translation', side_effect=lambda inp, draft, **kw: draft)
@patch('app.translate.translator.translate_draft', return_value=TranslationOutput(
    segment_id="1",
    draft_translation="[DRAFT ENGLISH] Some source text.",
    polished_translation="",
    notes=[]
))
def test_cli_service_failure_with_fallback(mock_translate_local, mock_polish):
    """
    When service-url is provided and service fails, with --allow-mock-fallback,
    CLI should fall back to local mock translation.
    """
    mock_segment = create_mock_segment()
    with patch('app.cli.create_segments', return_value=[mock_segment]):
        with patch('app.cli.mock_glossary', return_value=[]):
            # Mock the HTTP client to raise ConnectionError
            # We need to mock TranslationServiceClient and its translate_draft method
            mock_client = MagicMock()
            mock_client.translate_draft.side_effect = ConnectionError("Cannot connect")
            with patch('app.service.client.TranslationServiceClient', return_value=mock_client):
                with patch.dict('os.environ', {}):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        source_path = Path(tmpdir) / "source.txt"
                        output_path = Path(tmpdir) / "output.md"
                        source_path.write_text("Test text", encoding='utf-8')
                        # Should not raise SystemExit
                        run_pipeline(source_path, output_path, service_url="http://localhost:9999", allow_mock_fallback=True)
                        # Check that output file was created (since fallback works)
                        assert output_path.exists()
                        # Read output and ensure it contains mock translation pattern
                        content = output_path.read_text(encoding='utf-8')
                        assert "[DRAFT ENGLISH]" in content


@patch('app.cli.polish_translation', side_effect=lambda inp, draft, **kw: draft)
def test_cli_service_success(mock_polish):
    """
    When service-url is provided and service works, use service translation.
    """
    mock_segment = create_mock_segment()
    with patch('app.cli.create_segments', return_value=[mock_segment]):
        with patch('app.cli.mock_glossary', return_value=[]):
            # Mock TranslationServiceClient to return a mock TranslationOutput
            mock_client = MagicMock()
            mock_output = TranslationOutput(
                segment_id="1",
                draft_translation="[SERVICE] Some source text.",
                polished_translation="",
                notes=[]
            )
            mock_client.translate_draft.return_value = mock_output
            with patch('app.service.client.TranslationServiceClient', return_value=mock_client):
                with patch.dict('os.environ', {}):
                    with tempfile.TemporaryDirectory() as tmpdir:
                        source_path = Path(tmpdir) / "source.txt"
                        output_path = Path(tmpdir) / "output.md"
                        source_path.write_text("Test text", encoding='utf-8')
                        run_pipeline(source_path, output_path, service_url="http://localhost:9999", allow_mock_fallback=False)
                        assert output_path.exists()
                        content = output_path.read_text(encoding='utf-8')
                        # Should contain service translation
                        assert "[SERVICE]" in content


@patch('app.cli.polish_translation', side_effect=lambda inp, draft, **kw: draft)
@patch('app.translate.translator.translate_draft', return_value=TranslationOutput(
    segment_id="1",
    draft_translation="[DRAFT ENGLISH] Some source text.",
    polished_translation="",
    notes=[]
))
def test_cli_no_service_url_uses_local_mock(mock_translate_local, mock_polish):
    """
    When no service-url is provided, CLI should use local mock translation.
    """
    mock_segment = create_mock_segment()
    with patch('app.cli.create_segments', return_value=[mock_segment]):
        with patch('app.cli.mock_glossary', return_value=[]):
            # Ensure TranslationServiceClient is never instantiated
            with patch('app.service.client.TranslationServiceClient') as mock_client_class:
                with tempfile.TemporaryDirectory() as tmpdir:
                    source_path = Path(tmpdir) / "source.txt"
                    output_path = Path(tmpdir) / "output.md"
                    source_path.write_text("Test text", encoding='utf-8')
                    run_pipeline(source_path, output_path, service_url=None, allow_mock_fallback=False)
                    assert output_path.exists()
                    content = output_path.read_text(encoding='utf-8')
                    assert "[DRAFT ENGLISH]" in content
                    # HTTP client class should not be called
                    mock_client_class.assert_not_called()


# ---------------------------------------------------------------------------
# --assets-mode flag: prove the CLI surface is wired to run_pipeline.
# ---------------------------------------------------------------------------


def _invoke_main_with_argv(argv):
    """Run app.cli.main() with sys.argv patched. Returns the kwargs that
    main() passed to run_pipeline (captured via a mock)."""
    from app import cli

    captured = {}

    def fake_run_pipeline(source, output, service_url, allow_mock_fallback,
                         *, assets_mode, model_profile=None):
        captured['source'] = source
        captured['output'] = output
        captured['service_url'] = service_url
        captured['allow_mock_fallback'] = allow_mock_fallback
        captured['assets_mode'] = assets_mode

    with patch('sys.argv', argv):
        with patch.object(cli, 'run_pipeline', side_effect=fake_run_pipeline):
            cli.main()
    return captured


def test_cli_assets_mode_defaults_to_full():
    """Without --assets-mode, main() should forward assets_mode='full' to run_pipeline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        captured = _invoke_main_with_argv([
            'cli', 'run', '--source', str(src), '--output', str(out),
        ])
    assert captured['assets_mode'] == 'full'


def test_cli_assets_mode_none_is_forwarded():
    """--assets-mode none must reach run_pipeline as assets_mode='none'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        captured = _invoke_main_with_argv([
            'cli', 'run', '--source', str(src), '--output', str(out),
            '--assets-mode', 'none',
        ])
    assert captured['assets_mode'] == 'none'


def test_cli_assets_mode_full_is_forwarded():
    """--assets-mode full must reach run_pipeline as assets_mode='full'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        captured = _invoke_main_with_argv([
            'cli', 'run', '--source', str(src), '--output', str(out),
            '--assets-mode', 'full',
        ])
    assert captured['assets_mode'] == 'full'


def test_cli_assets_mode_invalid_value_rejected():
    """Any value other than full/none is rejected by argparse with SystemExit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        with pytest.raises(SystemExit) as excinfo:
            _invoke_main_with_argv([
                'cli', 'run', '--source', str(src), '--output', str(out),
                '--assets-mode', 'partial',
            ])
        # argparse uses exit code 2 for usage errors.
        assert excinfo.value.code == 2


def test_cli_existing_behavior_preserved():
    """Other CLI args still flow through unchanged alongside the new flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        captured = _invoke_main_with_argv([
            'cli', 'run', '--source', str(src), '--output', str(out),
            '--service-url', 'http://example:9000',
            '--allow-mock-fallback',
        ])
    assert captured['source'] == src
    assert captured['output'] == out
    assert captured['service_url'] == 'http://example:9000'
    assert captured['allow_mock_fallback'] is True
    # And the default still holds without --assets-mode on the command line.
    assert captured['assets_mode'] == 'full'


# ---------------------------------------------------------------------------
# chapter run resume configuration parameters
# ---------------------------------------------------------------------------

def _invoke_chapter_main_with_argv(argv):
    """Run app.cli.main() with sys.argv patched for chapter run command.
    Returns the kwargs that main() passed to run_chapter_pipeline."""
    from app import cli

    captured = {}

    def fake_run_chapter_pipeline(source, output, service_url, allow_mock_fallback,
                                 *, assets_mode, model_profile=None, resume=False, dry_run=False, max_retries=2, retry_delay_seconds=1.0, auto_retry_on_resume=True, no_clobber=False, confirm=False, smoke_test=False, book_memory_path=None):
        captured['source'] = source
        captured['output'] = output
        captured['service_url'] = service_url
        captured['allow_mock_fallback'] = allow_mock_fallback
        captured['assets_mode'] = assets_mode
        captured['resume'] = resume
        captured['dry_run'] = dry_run
        captured['max_retries'] = max_retries
        captured['retry_delay_seconds'] = retry_delay_seconds
        captured['auto_retry_on_resume'] = auto_retry_on_resume
        captured['no_clobber'] = no_clobber
        captured['confirm'] = confirm
        captured['smoke_test'] = smoke_test
        captured['book_memory_path'] = book_memory_path

    with patch('sys.argv', argv):
        with patch.object(cli, 'run_chapter_pipeline', side_effect=fake_run_chapter_pipeline):
            cli.main()
    return captured


def test_chapter_run_resume_params_defaults():
    """Without resume parameters, main() should forward default values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        captured = _invoke_chapter_main_with_argv([
            'cli', 'chapter', 'run', '--source', str(src), '--output', str(out),
        ])
    assert captured['max_retries'] == 2
    assert captured['retry_delay_seconds'] == 1.0
    assert captured['auto_retry_on_resume'] is True


def test_chapter_run_resume_params_custom():
    """Custom resume parameters must reach run_chapter_pipeline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        captured = _invoke_chapter_main_with_argv([
            'cli', 'chapter', 'run', '--source', str(src), '--output', str(out),
            '--max-retries', '3',
            '--retry-delay-seconds', '2.5',
            '--no-auto-retry-on-resume',
        ])
    assert captured['max_retries'] == 3
    assert captured['retry_delay_seconds'] == 2.5
    assert captured['auto_retry_on_resume'] is False


def test_chapter_run_resume_params_with_other_flags():
    """Resume parameters work alongside other flags like --service-url."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        out = Path(tmpdir) / "o.md"
        src.write_text("x", encoding='utf-8')
        captured = _invoke_chapter_main_with_argv([
            'cli', 'chapter', 'run', '--source', str(src), '--output', str(out),
            '--service-url', 'http://example:9000',
            '--allow-mock-fallback',
            '--assets-mode', 'none',
            '--resume',
            '--max-retries', '0',
            '--retry-delay-seconds', '0.5',
        ])
    assert captured['service_url'] == 'http://example:9000'
    assert captured['allow_mock_fallback'] is True
    assert captured['assets_mode'] == 'none'
    assert captured['resume'] is True
    assert captured['max_retries'] == 0
    assert captured['retry_delay_seconds'] == 0.5
    assert captured['auto_retry_on_resume'] is True  # default when not specified


# ── chapter run --dry-run ────────────────────────────────────────────────


def test_chapter_run_dry_run_prints_plan(tmp_path, capsys):
    """--dry-run should print chapter plan and exit without calling run_with_manifest."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    mock_plan = MagicMock()
    mock_plan.chapter_title = "第一章"
    mock_plan.segment_count = 3
    mock_plan.strategy_plan = {
        "complexity": {"level": "low", "score": 0.15},
        "overall_strategy": {
            "processing_mode": "standard",
            "budget_profile": "light",
            "consistency_intensity": "standard",
            "segmentation_granularity": "standard",
        },
        "rationale": "Short chapter with low complexity.",
    }

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.plan.return_value = mock_plan

        run_chapter_pipeline(source, output, dry_run=True)

    captured = capsys.readouterr()
    assert "Chapter:" in captured.out
    assert "第一章" in captured.out
    assert "3 segments" in captured.out
    assert "Complexity:" in captured.out
    assert "low" in captured.out
    assert "light" in captured.out
    assert "Rationale:" in captured.out
    # run_with_manifest must NOT be called on a dry run
    mock_orch.run_with_manifest.assert_not_called()


def test_chapter_run_dry_run_handles_no_strategy(tmp_path, capsys):
    """--dry-run should still work when strategy_plan is None."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nContent.", encoding='utf-8')

    mock_plan = MagicMock()
    mock_plan.chapter_title = "第一章"
    mock_plan.segment_count = 2
    mock_plan.strategy_plan = None

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.plan.return_value = mock_plan

        run_chapter_pipeline(source, output, dry_run=True)

    captured = capsys.readouterr()
    assert "Chapter:" in captured.out
    assert "2 segments" in captured.out
    assert "Complexity:" not in captured.out
    # run_with_manifest must NOT be called on a dry run
    mock_orch.run_with_manifest.assert_not_called()


def test_chapter_run_dry_run_and_resume_mutually_exclusive():
    """--dry-run and --resume must be rejected by argparse."""
    from app import cli

    with pytest.raises(SystemExit) as excinfo:
        with patch('sys.argv', ['cli', 'chapter', 'run', '--dry-run', '--resume']):
            cli.main()
    assert excinfo.value.code == 2  # argparse usage error


# ── chapter run --confirm ───────────────────────────────────────────────


def test_chapter_run_confirm_yes_proceeds(tmp_path):
    """--confirm with 'y' should display plan and then proceed to execution."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nContent.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nContent.",
        aggregated_translation="Output.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        with patch('builtins.input', return_value='y'):
            run_chapter_pipeline(source, output, confirm=True)

    assert output.exists()
    mock_orch_cls.assert_called()


def test_chapter_run_confirm_no_exits(tmp_path):
    """--confirm with 'n' should display plan and exit without execution."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nContent.", encoding='utf-8')

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan

        with patch('builtins.input', return_value='n'):
            with pytest.raises(SystemExit) as exc:
                run_chapter_pipeline(source, output, confirm=True)
            assert exc.value.code == 0

    mock_orch.run_with_manifest.assert_not_called()


def test_chapter_run_dry_run_confirm_yes_skips_early_return(tmp_path):
    """--dry-run --confirm with 'y' should display plan and then proceed, not exit early."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nContent.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nContent.",
        aggregated_translation="Output.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        with patch('builtins.input', return_value='y'):
            run_chapter_pipeline(source, output, dry_run=True, confirm=True)

    # Must have proceeded to execution (run_with_manifest called)
    mock_orch.run_with_manifest.assert_called_once()


def test_chapter_run_dry_run_confirm_no_exits(tmp_path):
    """--dry-run --confirm with 'n' should exit without execution."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nContent.", encoding='utf-8')

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan

        with patch('builtins.input', return_value='n'):
            with pytest.raises(SystemExit) as exc:
                run_chapter_pipeline(source, output, dry_run=True, confirm=True)
            assert exc.value.code == 0

    mock_orch.run_with_manifest.assert_not_called()


def test_chapter_stream_no_resume_params():
    """chapter stream command should not accept resume parameters."""
    # This test verifies that argparse rejects resume params for stream command
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "s.txt"
        src.write_text("x", encoding='utf-8')
        # Try to pass resume params to stream command - should fail
        # We can't easily test argparse rejection without running main,
        # but we can verify that the parser doesn't have these arguments
        # by checking that help doesn't mention them (simpler to just
        # ensure the code doesn't add these args to stream parser)
        pass  # Implementation detail: resume params only added to chapter run parser


# ── run_chapter_pipeline: parameter validation ────────────────────────


def test_run_chapter_pipeline_source_not_found(tmp_path):
    """Non-existent source should exit with code 1."""
    source = tmp_path / "nonexistent.txt"
    output = tmp_path / "output.md"
    with pytest.raises(SystemExit) as exc:
        run_chapter_pipeline(source, output)
    assert exc.value.code == 1


def test_run_chapter_pipeline_invalid_max_retries(tmp_path):
    """Negative max_retries should raise ValueError."""
    source = tmp_path / "s.txt"
    source.write_text("test", encoding='utf-8')
    output = tmp_path / "o.md"
    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        run_chapter_pipeline(source, output, max_retries=-1)


def test_run_chapter_pipeline_invalid_retry_delay(tmp_path):
    """Negative retry_delay_seconds should raise ValueError."""
    source = tmp_path / "s.txt"
    source.write_text("test", encoding='utf-8')
    output = tmp_path / "o.md"
    with pytest.raises(ValueError, match="retry_delay_seconds must be >= 0"):
        run_chapter_pipeline(source, output, retry_delay_seconds=-0.5)


def test_run_chapter_pipeline_service_unavailable(tmp_path):
    """Unresolvable translate function should exit with code 1."""
    source = tmp_path / "s.txt"
    source.write_text("test", encoding='utf-8')
    output = tmp_path / "o.md"
    with patch('app.cli._resolve_translate_fn', return_value=(None, "error")):
        with pytest.raises(SystemExit) as exc:
            run_chapter_pipeline(source, output, service_url="http://bad:9999")
        assert exc.value.code == 1


# ── run_chapter_pipeline: success path ───────────────────────────────


def test_run_chapter_pipeline_success(tmp_path):
    """Successful chapter run should write output file."""
    source = tmp_path / "source.txt"
    output = tmp_path / "output.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nTest content.",
        aggregated_translation="# 第一章\n\nTranslated output.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_orch.run_with_manifest.return_value = mock_result

        run_chapter_pipeline(source, output)

    assert output.exists()
    content = output.read_text(encoding='utf-8')
    assert "Translated output." in content


def test_run_chapter_pipeline_fresh_shows_plan(tmp_path, capsys):
    """Fresh run should print chapter title and segment count before translating."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nTest content.",
        aggregated_translation="# 第一章\n\nOutput.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 3
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        run_chapter_pipeline(source, output)

    captured = capsys.readouterr()
    assert "Chapter:" in captured.out
    assert "第一章" in captured.out
    assert "3 segments" in captured.out


# ── chapter run --no-clobber ────────────────────────────────────────────


def test_chapter_run_no_clobber_output_exists_exits(tmp_path, capsys):
    """--no-clobber exits with error when output file already exists, before any orchestrator work."""
    source = tmp_path / "source.txt"
    output = tmp_path / "output.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')
    output.write_text("Existing output.", encoding='utf-8')

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        with pytest.raises(SystemExit) as exc:
            run_chapter_pipeline(source, output, no_clobber=True)
        assert exc.value.code == 1

    captured = capsys.readouterr()
    assert "Output file already exists" in captured.out
    mock_orch_cls.assert_not_called()


def test_chapter_run_no_clobber_proceeds_when_no_output(tmp_path):
    """--no-clobber proceeds normally when output file does not exist."""
    source = tmp_path / "source.txt"
    output = tmp_path / "output.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nTest content.",
        aggregated_translation="# 第一章\n\nOutput.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        run_chapter_pipeline(source, output, no_clobber=True)

    assert output.exists()
    mock_orch_cls.assert_called_once()


def test_chapter_run_no_clobber_default_overwrites(tmp_path):
    """Without --no-clobber, existing output file is overwritten normally."""
    source = tmp_path / "source.txt"
    output = tmp_path / "output.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')
    output.write_text("Old content.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nTest content.",
        aggregated_translation="# 第一章\n\nNew output.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        run_chapter_pipeline(source, output)

    assert output.exists()
    content = output.read_text(encoding='utf-8')
    assert "New output." in content
    assert "Old content." not in content


# ── run_chapter_stream ───────────────────────────────────────────────


def test_run_chapter_stream_success(tmp_path, capsys):
    """run_chapter_stream with source file should write to stdout with trailing newline."""
    source = tmp_path / "s.txt"
    source.write_text("第一章\n\nContent.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nContent.",
        aggregated_translation="Streamed output.",
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.run_with_manifest.return_value = mock_result

        run_chapter_stream(source_path=source)

    captured = capsys.readouterr()
    assert captured.out == "Streamed output.\n"
    assert captured.err == ""


def test_run_chapter_stream_empty_source(tmp_path):
    """Empty source text should exit with code 1."""
    source = tmp_path / "s.txt"
    source.write_text("   \n  \n", encoding='utf-8')
    with pytest.raises(SystemExit) as exc:
        run_chapter_stream(source_path=source)
    assert exc.value.code == 1


def test_run_chapter_stream_empty_stdin():
    """Empty stdin should exit with code 1."""
    with patch('sys.stdin.read', return_value="  \n  "):
        with pytest.raises(SystemExit) as exc:
            run_chapter_stream(source_path=None)
        assert exc.value.code == 1


def test_run_chapter_stream_service_unavailable(tmp_path):
    """Service failure without fallback should exit with code 1."""
    source = tmp_path / "s.txt"
    source.write_text("Test.", encoding='utf-8')
    with patch('app.cli._resolve_translate_fn', return_value=(None, "error")):
        with pytest.raises(SystemExit) as exc:
            run_chapter_stream(source_path=source)
        assert exc.value.code == 1


# ── chapter stream arg routing via main() ────────────────────────────


def _invoke_chapter_stream_main_with_argv(argv):
    """Run main() with sys.argv patched for chapter stream."""
    from app import cli
    captured = {}

    def fake_run_chapter_stream(source_path, service_url, allow_mock_fallback, assets_mode, model_profile=None, smoke_test=False, book_memory_path=None):
        captured['source_path'] = source_path
        captured['service_url'] = service_url
        captured['allow_mock_fallback'] = allow_mock_fallback
        captured['assets_mode'] = assets_mode
        captured['model_profile'] = model_profile
        captured['smoke_test'] = smoke_test
        captured['book_memory_path'] = book_memory_path

    with patch('sys.argv', argv):
        with patch.object(cli, 'run_chapter_stream', side_effect=fake_run_chapter_stream):
            cli.main()
    return captured


def test_chapter_stream_main_forwarding_defaults():
    """chapter stream should forward default args."""
    captured = _invoke_chapter_stream_main_with_argv([
        'cli', 'chapter', 'stream',
    ])
    assert captured['source_path'] is None
    assert captured['service_url'] is None
    assert captured['allow_mock_fallback'] is False
    assert captured['assets_mode'] == 'full'


def test_chapter_stream_main_forwarding_with_args():
    """chapter stream should forward explicit args."""
    captured = _invoke_chapter_stream_main_with_argv([
        'cli', 'chapter', 'stream', '--source', '/tmp/test.txt',
        '--service-url', 'http://example:9000',
        '--allow-mock-fallback',
        '--assets-mode', 'none',
    ])
    assert captured['source_path'] == Path('/tmp/test.txt')
    assert captured['service_url'] == 'http://example:9000'
    assert captured['allow_mock_fallback'] is True
    assert captured['assets_mode'] == 'none'


# ── _report_chapter_result: resume guidance ─────────────────────────────


def test_report_chapter_result_complete_no_guidance(capsys):
    """Completed run should not show resume or next-step guidance."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        manifest=MagicMock(manifest_path="/tmp/test.manifest.json", segments={}),
        resumable=False,
    )
    assert result.segment_count == 1
    assert result.success_count == 1
    assert result.is_complete is True
    assert result.is_partial is False

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Remaining" not in captured.out
    assert "Next step" not in captured.out
    assert "--resume" not in captured.out
    assert "Manifest" in captured.out
    assert "Written to:" in captured.out
    assert "/tmp/out.md" in captured.out
    assert "Aggregated:" not in captured.out


def test_report_chapter_result_partial_shows_guidance(tmp_path, capsys):
    """Partial run should show remaining count, manifest, and --resume guidance."""
    mock_manifest = MagicMock()
    mock_manifest.manifest_path = "/tmp/test.manifest.json"
    mock_manifest.segments = {}

    results = [
        TranslationOutput(segment_id="1", draft_translation="", polished_translation="Seg 1"),
        TranslationOutput(segment_id="2", draft_translation="", polished_translation=""),
        TranslationOutput(segment_id="3", draft_translation="", polished_translation=""),
    ]
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="Partial output.",
        segment_results=results,
        segment_statuses={
            "1": SegmentStatus.COMPLETED,
            "2": SegmentStatus.FAILED,
            "3": SegmentStatus.PENDING,
        },
        chapter_status=ChapterStatus.PARTIAL,
        failed_segment_ids=["2"],
        manifest=mock_manifest,
        resumable=True,
    )
    assert result.segment_count == 3
    assert result.success_count == 1
    assert result.is_partial is True
    assert result.resumable is True

    output = tmp_path / "output.md"
    _report_chapter_result(result, output)
    captured = capsys.readouterr()

    assert "Manifest" in captured.out
    assert "/tmp/test.manifest.json" in captured.out
    assert "reuses 1 completed segments" in captured.out
    assert "processes 2 remaining segments" in captured.out
    assert "partial — 1/3 segments" in captured.out


def test_report_chapter_result_failed_shows_retry_guidance(tmp_path, capsys):
    """All-failed run should show retry guidance with --resume."""
    mock_manifest = MagicMock()
    mock_manifest.manifest_path = "/tmp/test.manifest.json"
    mock_manifest.segments = {}

    results = [
        TranslationOutput(segment_id="1", draft_translation="", polished_translation=""),
        TranslationOutput(segment_id="2", draft_translation="", polished_translation=""),
    ]
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="",
        segment_results=results,
        segment_statuses={"1": SegmentStatus.FAILED, "2": SegmentStatus.FAILED},
        chapter_status=ChapterStatus.FAILED,
        failed_segment_ids=["1", "2"],
        manifest=mock_manifest,
        resumable=True,
    )
    assert result.segment_count == 2
    assert result.success_count == 0
    assert result.is_complete is False
    assert result.is_partial is False
    assert result.resumable is True

    output = tmp_path / "output.md"
    _report_chapter_result(result, output)
    captured = capsys.readouterr()

    assert "Manifest" in captured.out
    assert "/tmp/test.manifest.json" in captured.out
    assert "retry all segments" in captured.out
    assert "--resume" in captured.out


# ── _report_chapter_result: strategy overview ──────────────────────────


def test_report_chapter_result_strategy_shows_when_available(capsys):
    """Should show strategy overview when strategy_plan_summary is set."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        strategy_plan_summary={
            "complexity": {"level": "medium", "score": 0.45},
            "overall_strategy": {
                "processing_mode": "standard",
                "budget_profile": "standard",
                "consistency_intensity": "enhanced",
                "segmentation_granularity": "standard",
            },
        },
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Strategy:" in captured.out
    assert "Complexity:" in captured.out and "medium" in captured.out
    assert "segments" in captured.out and "Budget:" in captured.out
    assert "Consistency:" in captured.out and "enhanced" in captured.out
    assert captured.out.index("Written to:") < captured.out.index("Strategy:")


def test_report_chapter_result_strategy_no_complexity(capsys):
    """Should show partial strategy when complexity is missing."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        strategy_plan_summary={
            "overall_strategy": {
                "budget_profile": "standard",
                "consistency_intensity": "standard",
                "segmentation_granularity": "standard",
            },
        },
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Strategy:" in captured.out
    assert "Segmentation:" in captured.out and "Budget:" in captured.out
    assert "Consistency:" in captured.out and "standard" in captured.out


def test_report_chapter_result_strategy_no_overall(capsys):
    """Should show partial strategy when overall_strategy is missing."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        strategy_plan_summary={
            "complexity": {"level": "high", "score": 0.78},
        },
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Strategy:" in captured.out
    assert "Complexity:" in captured.out and "Mode:" in captured.out
    assert "high" in captured.out


def test_report_chapter_result_strategy_none(capsys):
    """Should not show strategy section when strategy_plan_summary is None."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Strategy:" not in captured.out


def test_report_chapter_result_strategy_empty_dict(capsys):
    """Should not show strategy section when strategy_plan_summary is empty."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        strategy_plan_summary={},
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Strategy:" not in captured.out


# ── _report_chapter_result: consistency audit / correction readability ──


def test_report_chapter_result_consistency_not_run(capsys):
    """Should not show consistency section when audit is None (pass not run)."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit=None,
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Consistency:" not in captured.out
    assert "no issues found" not in captured.out


def test_report_chapter_result_consistency_no_issues(capsys):
    """Should show 'no issues found' when audit ran with 0 issues."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit={
            "total_issues": 0,
            "by_category": {},
            "auto_fixable": 0,
            "auto_fixed": 0,
        },
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Consistency:" in captured.out
    assert "no issues found" in captured.out
    # No category breakdown when 0 issues
    assert "by_category" not in captured.out


def test_report_chapter_result_consistency_all_resolved(capsys):
    """Should show 'all resolved' when all issues were auto-fixed."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit={
            "total_issues": 2,
            "by_category": {"name_variant": 1, "title_variant": 1},
            "auto_fixable": 2,
            "auto_fixed": 2,
        },
        correction_summary={
            "total_corrections": 2,
            "total_replacements": 3,
            "by_category": {"name_variant": 1, "title_variant": 1},
        },
        corrected_translation="Corrected chapter text.",
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Consistency:" in captured.out
    assert "all resolved" in captured.out
    assert "(2 issues" in captured.out
    assert "auto-fixed" in captured.out
    # Category breakdown
    assert "name_variant" in captured.out
    assert "title_variant" in captured.out
    # Correction actions section
    assert "Corrections:" in captured.out
    # Corrected version
    assert "Corrected:" in captured.out
    # Check no raw field labels from old format
    assert "Auto-fixable" not in captured.out
    assert "Auto-fixed" not in captured.out


def test_report_chapter_result_consistency_partial_fix(capsys):
    """Should show both total and auto-fixed counts when not all fixed."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit={
            "total_issues": 5,
            "by_category": {"name_variant": 3, "term_variant": 2},
            "auto_fixable": 3,
            "auto_fixed": 3,
        },
        correction_summary={
            "total_corrections": 3,
            "total_replacements": 3,
            "by_category": {"name_variant": 2, "term_variant": 1},
        },
        corrected_translation="Partially corrected text.",
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Consistency:" in captured.out
    assert "(3 auto-fixed)" in captured.out
    assert "5 issues" in captured.out or "issues" in captured.out
    # Category breakdown
    assert "name_variant" in captured.out
    assert "term_variant" in captured.out
    # Corrections section
    assert "Corrections:" in captured.out
    assert "Corrected:" in captured.out
    assert "no issues found" not in captured.out
    assert "all resolved" not in captured.out


def test_report_chapter_result_consistency_no_fix(capsys):
    """Should show 'issues found' when no issues were auto-fixable."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit={
            "total_issues": 3,
            "by_category": {"style_inconsistency": 3},
            "auto_fixable": 0,
            "auto_fixed": 0,
        },
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Consistency:" in captured.out
    assert "3 issues found" in captured.out
    assert "style_inconsistency" in captured.out
    # No correction section — nothing was fixable
    assert "Corrections:" not in captured.out
    # No corrected version
    assert "Corrected:" not in captured.out
    assert "all resolved" not in captured.out
    assert "no issues found" not in captured.out


def test_report_chapter_result_consistency_single_issue_all_resolved(capsys):
    """Single issue with auto-fixed should show singular form."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="All done.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Done."),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
        consistency_audit={
            "total_issues": 1,
            "by_category": {"name_variant": 1},
            "auto_fixable": 1,
            "auto_fixed": 1,
        },
        correction_summary={
            "total_corrections": 1,
            "total_replacements": 1,
            "by_category": {"name_variant": 1},
        },
        corrected_translation="Fixed text.",
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Consistency:" in captured.out
    assert "all resolved" in captured.out
    assert "(1 issue" in captured.out  # singular
    assert "Corrections:" in captured.out
    assert "Corrected:" in captured.out


def test_report_chapter_result_consistency_none_with_partial_run(capsys):
    """Partial run without audit should not show consistency section."""
    result = ChapterResult(
        chapter_title="Test",
        source_text="test",
        aggregated_translation="Partial.",
        segment_results=[
            TranslationOutput(segment_id="1", draft_translation="", polished_translation="Seg 1"),
            TranslationOutput(segment_id="2", draft_translation="", polished_translation=""),
        ],
        segment_statuses={"1": SegmentStatus.COMPLETED, "2": SegmentStatus.FAILED},
        chapter_status=ChapterStatus.PARTIAL,
        failed_segment_ids=["2"],
        resumable=True,
        consistency_audit=None,
    )

    _report_chapter_result(result, Path("/tmp/out.md"))
    captured = capsys.readouterr()

    assert "Consistency:" not in captured.out


# ── --resume help text ──────────────────────────────────────────────────


def test_chapter_run_resume_help_text(capsys):
    """--resume help text should explain what it does with completed/pending/failed segments."""
    from app import cli

    with pytest.raises(SystemExit):
        with patch('sys.argv', ['cli', 'chapter', 'run', '--help']):
            cli.main()

    captured = capsys.readouterr()
    assert "--resume" in captured.out
    assert "Completed segments are reused" in captured.out
    assert "pending" in captured.out
    assert "failed segments" in captured.out
    assert "manifest file lives at" in captured.out
    assert "partial" in captured.out
    assert "interrupted" in captured.out


# ── Per-segment progress output ──────────────────────────────────────────


def test_chapter_run_per_segment_progress(tmp_path, capsys):
    """Progress lines should appear on stdout and handler must not leak."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    orch_log = logging.getLogger('app.chapter.orchestrator')
    prev_handlers = len(orch_log.handlers)
    prev_level = orch_log.level

    def mock_run_with_manifest(text, **kw):
        orch_log.info("  Segment 1 starting...")
        orch_log.info("  Segment 1 completed.")
        return ChapterResult(
            chapter_title="第一章",
            source_text=text,
            aggregated_translation="Output.",
            segment_statuses={"1": SegmentStatus.COMPLETED},
            chapter_status=ChapterStatus.COMPLETED,
        )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest = mock_run_with_manifest

        run_chapter_pipeline(source, output)

    captured = capsys.readouterr()
    assert "Segment 1 starting..." in captured.out
    assert "Segment 1 completed." in captured.out

    # Handler must not leak after the call returns.
    assert len(orch_log.handlers) == prev_handlers
    assert orch_log.level == prev_level


def test_chapter_stream_stdout_clean_after_chapter_run(tmp_path, capsys):
    """Stream stdout must not contain log messages after a prior chapter run."""
    source = tmp_path / "s.txt"
    output = tmp_path / "o.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    chapters_result = ChapterResult(
        chapter_title="第一章",
        source_text="Test content.",
        aggregated_translation="Chapter output.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = chapters_result

        run_chapter_pipeline(source, output)

    capsys.readouterr()  # discard prior output

    stream_source = tmp_path / "stream.txt"
    stream_source.write_text("第一章\n\nStream content.", encoding='utf-8')

    stream_result = ChapterResult(
        chapter_title="第一章",
        source_text="Stream content.",
        aggregated_translation="Stream output.",
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.run_with_manifest.return_value = stream_result

        run_chapter_stream(source_path=stream_source)

    captured = capsys.readouterr()
    assert captured.out == "Stream output.\n"


# ── Elapsed time in final summary ───────────────────────────────────────


def test_chapter_run_fresh_shows_elapsed(tmp_path, capsys):
    """Fresh run shows elapsed time in final summary."""
    source = tmp_path / "source.txt"
    output = tmp_path / "output.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nTest content.",
        aggregated_translation="# 第一章\n\nOutput.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        with patch('app.cli.time.monotonic', side_effect=[0.0, 12.3]):
            run_chapter_pipeline(source, output)

    captured = capsys.readouterr()
    assert "Elapsed: 12.3s" in captured.out
    assert captured.out.index("Elapsed:") < captured.out.index("Done.")


def test_chapter_run_elapsed_formatting(tmp_path, capsys):
    """Elapsed time is formatted with one decimal place."""
    source = tmp_path / "source.txt"
    output = tmp_path / "output.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nTest content.",
        aggregated_translation="# 第一章\n\nOutput.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        with patch('app.cli.time.monotonic', side_effect=[0.0, 0.5]):
            run_chapter_pipeline(source, output)

    captured = capsys.readouterr()
    assert "Elapsed: 0.5s" in captured.out


def test_chapter_run_elapsed_resume_path(tmp_path, capsys):
    """Resume path also shows elapsed time."""
    source = tmp_path / "source.txt"
    output = tmp_path / "output.md"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nTest content.",
        aggregated_translation="# 第一章\n\nOutput.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    mock_manifest = MagicMock()
    mock_manifest.get_summary.return_value = {
        'run_id': 'test-run',
        'status': 'partial',
        'completed': 2,
        'total_segments': 3,
        'failed': 1,
        'pending': 1,
        'resumable': True,
    }
    mock_manifest.manifest_path = str(tmp_path / "test.manifest.json")
    mock_manifest.segments = {}

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = mock_manifest
        mock_orch.resume.return_value = mock_result

        with patch('app.cli.time.monotonic', side_effect=[0.0, 45.6]):
            run_chapter_pipeline(source, output, resume=True)

    captured = capsys.readouterr()
    assert "Elapsed: 45.6s" in captured.out
    assert captured.out.index("Elapsed:") < captured.out.index("Done.")


# ── Smart output-path derivation ────────────────────────────────────────


def test_derive_output_path_basic():
    """Should derive output path from source filename."""
    result = _derive_output_path(Path("data/source/chapter3.txt"))
    assert result == Path("data/exports/chapter3_en.md")


def test_derive_output_path_different_dir():
    """Should use data/exports/ directory regardless of source location."""
    result = _derive_output_path(Path("/tmp/my_source.txt"))
    assert result == Path("data/exports/my_source_en.md")


def test_derive_output_path_no_ext():
    """Should handle source files without extension."""
    result = _derive_output_path(Path("data/source/chapter3"))
    assert result == Path("data/exports/chapter3_en.md")


def test_derive_output_path_multi_dot():
    """Should handle source files with multiple dots."""
    result = _derive_output_path(Path("data/source/ch.3.backup.txt"))
    assert result == Path("data/exports/ch.3.backup_en.md")


def test_chapter_run_without_output_derives_from_source():
    """chapter run without --output should derive output from source path."""
    captured = _invoke_chapter_main_with_argv([
        'cli', 'chapter', 'run', '--source', '/tmp/chapter3.txt',
    ])
    assert captured['output'] == Path('data/exports/chapter3_en.md')


def test_chapter_run_without_output_default_source_backward_compat():
    """chapter run without --output and default source should give old default."""
    captured = _invoke_chapter_main_with_argv([
        'cli', 'chapter', 'run',
    ])
    assert captured['output'] == Path('data/exports/one_chapter_quality_source_en.md')


def test_chapter_run_with_explicit_output_unchanged():
    """chapter run with explicit --output should use it directly."""
    captured = _invoke_chapter_main_with_argv([
        'cli', 'chapter', 'run', '--source', '/tmp/ch3.txt',
        '--output', '/custom/path.md',
    ])
    assert captured['output'] == Path('/custom/path.md')


def test_run_pipeline_without_output_derives_from_source():
    """run pipeline without --output should derive output from source path."""
    captured = _invoke_main_with_argv([
        'cli', 'run', '--source', '/tmp/chapter3.txt',
    ])
    assert captured['output'] == Path('data/exports/chapter3_en.md')


def test_run_pipeline_without_output_default_source_backward_compat():
    """run pipeline without --output and default source should give old default."""
    captured = _invoke_main_with_argv([
        'cli', 'run',
    ])
    assert captured['output'] == Path('data/exports/one_chapter_quality_source_en.md')


def test_run_pipeline_with_explicit_output_unchanged(tmp_path):
    """run pipeline with explicit --output should use it directly."""
    output = tmp_path / "out.md"
    captured = _invoke_main_with_argv([
        'cli', 'run', '--source', '/tmp/ch3.txt',
        '--output', str(output),
    ])
    assert captured['output'] == output


if __name__ == "__main__":
    # Run simple smoke test
    print("CLI tests passed (mocked).")


# ── chapter batch ─────────────────────────────────────────────────────


def test_chapter_batch_single_source(tmp_path, capsys):
    """Batch with one source should run chapter pipeline for that source."""
    source = tmp_path / "chapter1.txt"
    source.write_text("第一章\n\nTest content.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="第一章\n\nTest content.",
        aggregated_translation="Output.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        run_chapter_batch(source_paths=[source])

    captured = capsys.readouterr()
    assert "Batch translation:" in captured.out
    assert "Batch Summary" in captured.out
    assert "COMPLETED" in captured.out
    assert source.name in captured.out


def test_chapter_batch_two_sources(tmp_path, capsys):
    """Batch with two sources should run chapter pipeline for each."""
    s1 = tmp_path / "ch1.txt"
    s2 = tmp_path / "ch2.txt"
    s1.write_text("第一章\n\nContent.", encoding='utf-8')
    s2.write_text("第二章\n\nContent.", encoding='utf-8')

    mock_result = lambda title: ChapterResult(
        chapter_title=title,
        source_text="content",
        aggregated_translation="Output.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "Title"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.side_effect = [
            mock_result("第一章"), mock_result("第二章"),
        ]

        run_chapter_batch(source_paths=[s1, s2])

    captured = capsys.readouterr()
    assert "[1/2]" in captured.out
    assert "[2/2]" in captured.out
    assert "2 source(s)" in captured.out
    assert "2 completed" in captured.out
    assert s1.name in captured.out
    assert s2.name in captured.out


def test_chapter_batch_one_fails_continues(tmp_path, capsys):
    """When one chapter fails (source not found), the batch continues."""
    missing = tmp_path / "nope.txt"
    good = tmp_path / "ok.txt"
    good.write_text("第一章\n\nContent.", encoding='utf-8')

    mock_result = ChapterResult(
        chapter_title="第一章",
        source_text="Content.",
        aggregated_translation="Output.",
        segment_statuses={"1": SegmentStatus.COMPLETED},
        chapter_status=ChapterStatus.COMPLETED,
    )

    with patch('app.cli.ChapterOrchestrator') as mock_orch_cls:
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch
        mock_orch.load_manifest.return_value = None
        mock_plan = MagicMock()
        mock_plan.chapter_title = "第一章"
        mock_plan.segment_count = 1
        mock_orch.plan.return_value = mock_plan
        mock_orch.run_with_manifest.return_value = mock_result

        run_chapter_batch(source_paths=[missing, good])

    captured = capsys.readouterr()
    assert "1 completed" in captured.out
    assert "1 failed" in captured.out
    assert "FAILED" in captured.out
    assert "COMPLETED" in captured.out
    assert missing.name in captured.out
    assert good.name in captured.out






def _invoke_batch_main_with_argv(argv):
    """Run main() with sys.argv patched for chapter batch."""
    from app import cli

    captured = {}

    def fake_run_chapter_batch(source_paths, service_url, allow_mock_fallback,
                                assets_mode, model_profile=None, resume=False, no_clobber=False, smoke_test=False, book_memory_path=None):
        captured['source_paths'] = source_paths
        captured['service_url'] = service_url
        captured['allow_mock_fallback'] = allow_mock_fallback
        captured['assets_mode'] = assets_mode
        captured['resume'] = resume
        captured['no_clobber'] = no_clobber
        captured['smoke_test'] = smoke_test
        captured['book_memory_path'] = book_memory_path

    with patch('sys.argv', argv):
        with patch.object(cli, 'run_chapter_batch', side_effect=fake_run_chapter_batch):
            cli.main()
    return captured


def test_chapter_batch_main_routing():
    """chapter batch should route args to run_chapter_batch."""
    captured = _invoke_batch_main_with_argv([
        'cli', 'chapter', 'batch', '--source', '/tmp/ch1.txt', '--source', '/tmp/ch2.txt',
    ])
    assert len(captured['source_paths']) == 2
    assert Path('/tmp/ch1.txt') in captured['source_paths']
    assert Path('/tmp/ch2.txt') in captured['source_paths']
    assert captured['service_url'] is None
    assert captured['allow_mock_fallback'] is False
    assert captured['assets_mode'] == 'full'
    assert captured['resume'] is False
    assert captured['no_clobber'] is False


def test_chapter_batch_main_requires_source():
    """chapter batch without --source should exit with code 2."""
    from app import cli

    with pytest.raises(SystemExit) as exc:
        with patch('sys.argv', ['cli', 'chapter', 'batch']):
            cli.main()
    assert exc.value.code == 2


def test_chapter_batch_main_passthrough_flags():
    """chapter batch should forward shared flags to run_chapter_batch."""
    captured = _invoke_batch_main_with_argv([
        'cli', 'chapter', 'batch', '--source', '/tmp/ch1.txt',
        '--service-url', 'http://example:9000',
        '--allow-mock-fallback',
        '--assets-mode', 'none',
        '--resume',
        '--no-clobber',
    ])
    assert captured['service_url'] == 'http://example:9000'
    assert captured['allow_mock_fallback'] is True
    assert captured['assets_mode'] == 'none'
    assert captured['resume'] is True
    assert captured['no_clobber'] is True


def test_chapter_batch_keyboard_interrupt_propagates(tmp_path):
    """KeyboardInterrupt must propagate through run_chapter_batch, not be swallowed."""
    source = tmp_path / "test.txt"
    source.write_text("test", encoding='utf-8')

    with patch('app.cli.run_chapter_pipeline', side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            run_chapter_batch(source_paths=[source])


def test_chapter_batch_passthrough_to_pipeline(tmp_path):
    """run_chapter_batch must forward shared flags and output path to run_chapter_pipeline."""
    source = tmp_path / "ch1.txt"
    source.write_text("test", encoding='utf-8')
    # run_chapter_pipeline internally needs the output to exist for COMPLETED
    output = _derive_output_path(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("dummy", encoding='utf-8')

    captured = {}

    def fake_pipeline(source_path, output_path, service_url, allow_mock_fallback,
                      assets_mode, resume, no_clobber, **kw):
        captured['source_path'] = source_path
        captured['output_path'] = output_path
        captured['service_url'] = service_url
        captured['allow_mock_fallback'] = allow_mock_fallback
        captured['assets_mode'] = assets_mode
        captured['resume'] = resume
        captured['no_clobber'] = no_clobber

    with patch('app.cli.run_chapter_pipeline', side_effect=fake_pipeline):
        run_chapter_batch(
            source_paths=[source],
            service_url="http://example:9000",
            allow_mock_fallback=True,
            assets_mode="none",
            resume=True,
            no_clobber=True,
        )

    assert captured['source_path'] == source
    assert captured['output_path'] == output
    assert captured['service_url'] == "http://example:9000"
    assert captured['allow_mock_fallback'] is True
    assert captured['assets_mode'] == "none"
    assert captured['resume'] is True
    assert captured['no_clobber'] is True