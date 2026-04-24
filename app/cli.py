#!/usr/bin/env python3
"""
CLI for novel translation workbench.
"""
import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from app.chapter.manifest import RunManifest, ResumeConfig
from app.chapter.orchestrator import ChapterOrchestrator
from app.chapter.models import ChapterResult
from app.segment.segmenter import create_segments
from app.translate.translator import (
    ASSETS_MODES,
    DEFAULT_ASSETS_MODE,
    AssetsMode,
    _validate_assets_mode,
    build_translation_input,
    mock_glossary,
    polish_translation,
    translate_draft,
)
from app.translate.schema import TranslationInput, TranslationOutput


def read_source_file(source_path: Path) -> str:
    """Read the source text file."""
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")
    return source_path.read_text(encoding='utf-8')


def write_markdown(output_path: Path, segments, translation_outputs):
    """Write the markdown file with segments, drafts, polished translations, and notes."""
    with output_path.open('w', encoding='utf-8') as f:
        f.write("# Chapter 1\n\n")
        f.write("---\n\n")
        for seg, out in zip(segments, translation_outputs):
            f.write(f"## Segment {seg.segment_id}\n\n")
            f.write("### Draft\n")
            f.write(out.draft_translation + "\n\n")
            f.write("### Polished\n")
            f.write(out.polished_translation + "\n\n")
            if out.notes:
                f.write("### Notes\n")
                for note in out.notes:
                    f.write(f"- {note}\n")
                f.write("\n")
            f.write("---\n\n")


def run_pipeline(
    source_path: Path,
    output_path: Path,
    service_url: Optional[str] = None,
    allow_mock_fallback: bool = False,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
):
    """Run the translation pipeline.

    ``assets_mode`` is threaded through to the translation-call layer. The
    default ("full") preserves existing behavior; the CLI exposes this via
    ``--assets-mode``. See ``translator.build_project_assets_block`` for
    semantics.
    """
    _validate_assets_mode(assets_mode)
    print(f"Reading source from {source_path}")
    text = read_source_file(source_path)
    print(f"Loaded {len(text)} characters.")

    print("Segmenting text...")
    segments = create_segments(text)
    print(f"Created {len(segments)} segments.")

    glossary = mock_glossary()
    translation_outputs = []

    # Choose translation method
    http_translate_fn = None
    if service_url:
        print(f"Using translation service at {service_url}")
        # Try to import HTTP client
        try:
            from app.service.client import TranslationServiceClient
            # Create client with explicit base_url
            client = TranslationServiceClient(base_url=service_url)
            http_translate_fn = client.translate_draft
            print("  Service client imported successfully.")
        except Exception as e:
            print(f"  Warning: Could not import translation service client: {e}")
            if not allow_mock_fallback:
                print("  Falling back to local mock translation is not allowed (--allow-mock-fallback not set).")
                print(f"  Error: Service unavailable. Exiting.")
                sys.exit(1)
            else:
                print("  Falling back to local mock translation (--allow-mock-fallback enabled).")
                http_translate_fn = None

    # Local mock translation function. Wrap so assets_mode is threaded through
    # whenever the pipeline falls back to (or starts on) local translation.
    # HTTP service path intentionally keeps its existing single-arg contract.
    from app.translate.translator import translate_draft as local_translate_draft

    def local_translate_fn(inp):
        return local_translate_draft(inp, assets_mode=assets_mode)

    # Decide which function to use
    if service_url and http_translate_fn is not None:
        translate_draft_fn = http_translate_fn
        translation_mode = "service"
    else:
        translate_draft_fn = local_translate_fn
        translation_mode = "local mock"

    print(f"Translating using {translation_mode}...")
    service_failed = False
    for seg in segments:
        print(f"  Segment {seg.segment_id}...")
        # Build structured input
        input = build_translation_input(seg, glossary)
        # Draft translation
        try:
            draft_out = translate_draft_fn(input)
        except Exception as e:
            if not allow_mock_fallback:
                print(f"  Error: Translation service call failed: {e}")
                print(f"  Service URL: {service_url}")
                print(f"  Falling back to local mock translation is not allowed (--allow-mock-fallback not set).")
                sys.exit(1)
            else:
                print(f"  Warning: Translation service call failed: {e}")
                print(f"  Service URL: {service_url}")
                print(f"  Falling back to local mock translation (--allow-mock-fallback enabled).")
                # Switch to local translation for this and subsequent segments
                translate_draft_fn = local_translate_fn
                translation_mode = "local mock"
                service_failed = True
                # Retry with local translation
                draft_out = translate_draft_fn(input)
        # Polish translation (always local mock for now)
        final_out = polish_translation(input, draft_out, assets_mode=assets_mode)
        translation_outputs.append(final_out)

    print(f"Writing output to {output_path}")
    write_markdown(output_path, segments, translation_outputs)
    print("Done.")


def _resolve_translate_fn(
    service_url: Optional[str],
    allow_mock_fallback: bool,
    assets_mode: AssetsMode,
) -> tuple[Optional[Callable[[TranslationInput], TranslationOutput]], str]:
    """Resolve which translate function to use: service client or local.

    Returns (translate_fn, mode_label).
    ``translate_fn`` is None when neither service nor local is available.
    """
    _validate_assets_mode(assets_mode)
    from app.translate.translator import translate_draft as local_translate_draft

    def local_fn(inp):
        return local_translate_draft(inp, assets_mode=assets_mode)

    http_fn = None
    if service_url:
        try:
            from app.service.client import TranslationServiceClient
            client = TranslationServiceClient(base_url=service_url)
            http_fn = client.translate_draft
        except Exception as e:
            print(f"  Warning: Could not import translation service client: {e}")
            if not allow_mock_fallback:
                print("  Service client unavailable. Use --allow-mock-fallback to fall back to local translation.")
                return None, "error"
            print("  Falling back to local mock translation (--allow-mock-fallback enabled).")

    if http_fn is not None:
        return http_fn, "service"
    return local_fn, "local mock"


def run_chapter_pipeline(
    source_path: Path,
    output_path: Path,
    service_url: Optional[str] = None,
    allow_mock_fallback: bool = False,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
    resume: bool = False,
    dry_run: bool = False,
    max_retries: int = 2,
    retry_delay_seconds: float = 1.0,
    auto_retry_on_resume: bool = True,
):
    """Run the chapter-level translation pipeline.

    Reads a full chapter, auto-segments, auto-translates each segment,
    and aggregates into a complete chapter-level English output file.

    When ``resume=True``, attempts to load a saved run manifest for the
    output path and continue from where a previous run left off.
    """
    _validate_assets_mode(assets_mode)
    # Validate resume configuration parameters
    if max_retries < 0:
        raise ValueError(f"max_retries must be >= 0, got {max_retries}")
    if retry_delay_seconds < 0:
        raise ValueError(f"retry_delay_seconds must be >= 0, got {retry_delay_seconds}")

    # Create ResumeConfig instance
    resume_config = ResumeConfig(
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
        auto_retry_on_resume=auto_retry_on_resume,
    )

    try:
        text = read_source_file(source_path)
    except FileNotFoundError as e:
        print(f"  Error: {e}")
        sys.exit(1)
    print(f"Loaded {len(text)} characters.")

    # ── Dry-run path ─────────────────────────────────────────────────────
    if dry_run:
        orchestrator = ChapterOrchestrator()
        plan = orchestrator.plan(text)
        _display_plan(plan)
        return

    translate_fn, mode = _resolve_translate_fn(service_url, allow_mock_fallback, assets_mode)
    if translate_fn is None:
        print(f"  Error: Service unavailable. Exiting.")
        sys.exit(1)

    manifest_path = RunManifest.default_manifest_path(str(output_path))
    orchestrator = ChapterOrchestrator()

    # ── Resume path ──────────────────────────────────────────────────────
    if resume:
        try:
            manifest = orchestrator.load_manifest(manifest_path)
        except Exception:
            manifest = None

        if manifest is not None:
            summary = manifest.get_summary()
            print(f"\nFound saved manifest for run {summary['run_id']}:")
            print(f"  Status:      {summary['status']}")
            print(f"  Completed:   {summary['completed']}/{summary['total_segments']} segments")
            print(f"  Failed:      {summary['failed']}")
            print(f"  Pending:     {summary['pending']}")
            print(f"  Manifest:    {manifest_path}")
            if summary['resumable']:
                completed = summary['completed']
                pending = summary['pending']
                failed = summary['failed']
                print(f"  → Completed segments ({completed}) will be reused.")
                if pending:
                    print(f"  → Pending segments ({pending}) will be translated now.")
                if failed:
                    print(f"  → Failed segments ({failed}) will be retried (up to {max_retries} attempts each).")
                print(f"\nContinuing the chapter run from saved progress...")
                resume_start = time.monotonic()
                try:
                    result = orchestrator.resume(
                        text,
                        manifest_path,
                        translate_draft_fn=translate_fn,
                        assets_mode=assets_mode,
                        resume_config=resume_config,
                    )
                except Exception as e:
                    print(f"  Error: Resume failed: {e}")
                    print("  Starting a fresh run instead.")
                    result = None
                if result is not None:
                    _report_chapter_result(result, output_path, elapsed_seconds=time.monotonic() - resume_start)
                    return
                else:
                    print("  Could not resume. Starting a fresh run.")
            else:
                print("  The saved run cannot be resumed because it is already complete or no longer resumable.")
                print("  Starting a fresh run.")
        else:
            print(f"No manifest found at {manifest_path}.")
            print(f"  (The manifest is created automatically when a chapter run starts.)")
            print(f"  Starting a fresh run.")

    # ── Fresh run path ───────────────────────────────────────────────────
    plan = orchestrator.plan(text)
    print(f"Chapter: '{plan.chapter_title}' ({plan.segment_count} segments)")
    print(f"\nTranslating using {mode}...")

    # Temporary stdout logging so the operator sees per-segment progress.
    orch_log = logging.getLogger('app.chapter.orchestrator')
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    prev_level = orch_log.level
    orch_log.setLevel(logging.INFO)
    orch_log.addHandler(handler)
    run_start = time.monotonic()
    try:
        result = orchestrator.run_with_manifest(
            text,
            translate_draft_fn=translate_fn,
            assets_mode=assets_mode,
            resume_config=resume_config,
            manifest_path=manifest_path,
        )
    except Exception as e:
        print(f"  Error: Chapter translation pipeline failed: {e}")
        sys.exit(1)
    else:
        _report_chapter_result(result, output_path, elapsed_seconds=time.monotonic() - run_start)
    finally:
        orch_log.removeHandler(handler)
        handler.close()
        orch_log.setLevel(prev_level)


def _display_plan(plan) -> None:
    """Print a human-readable chapter plan summary to stdout.

    CLI-only helper. Not reused for HTTP or programmatic callers.
    """
    strategy = plan.strategy_plan
    print(f"Chapter: '{plan.chapter_title}' ({plan.segment_count} segments)")
    if strategy:
        complexity = strategy.get("complexity", {})
        overall = strategy.get("overall_strategy", {})
        if complexity:
            level = complexity.get("level", "—")
            score = complexity.get("score")
            mode = overall.get("processing_mode", "—") if overall else "—"
            line = f"  Complexity:     {level}"
            if score is not None:
                try:
                    line += f" ({float(score):.2f})"
                except (TypeError, ValueError):
                    line += f" ({score})"
            line += f" · Mode: {mode}"
            print(line)
        if overall:
            seg = overall.get("segmentation_granularity", "—")
            budget = overall.get("budget_profile", "—")
            cons = overall.get("consistency_intensity", "—")
            print(f"  Segmentation:   {seg} · {plan.segment_count} segments · Budget: {budget}")
            print(f"  Consistency:    {cons}")
        rationale = strategy.get("rationale")
        if rationale:
            print(f"  Rationale:      {rationale}")


def _report_chapter_result(result: ChapterResult, output_path: Path, elapsed_seconds: Optional[float] = None) -> None:
    """Print a status summary and write output for a chapter run result.

    Batch 3 addition: reports consistency audit findings and correction
    summary when available as a one-line status summary with category
    breakdown when issues exist.
    """
    status_label = result.chapter_status.value
    print(f"\nChapter '{result.chapter_title}' result:")
    print(f"  Status:      {status_label}")
    print(f"  Completed:   {result.success_count}/{result.segment_count} segments")
    if result.failed_segment_ids:
        if result.success_count == 0:
            # All segments failed — compact summary avoids noise
            print(f"  Failed:      all {len(result.failed_segment_ids)} segments")
        else:
            # Mixed result: individual failures are actionable
            print(f"  Failed:      {len(result.failed_segment_ids)} segments")
            for fid in result.failed_segment_ids:
                rec = result.manifest.segments.get(fid) if result.manifest else None
                err = f" ({rec.error_message})" if rec and rec.error_message else ""
                print(f"    - Segment {fid}{err}")


    # Write output — prefer corrected version when available
    output_text = result.final_translation
    if result.is_complete or result.is_partial:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_text:
            output_path.write_text(output_text, encoding='utf-8')
            labels = []
            if result.corrected_translation is not None:
                labels.append("post-consistency")
            if result.is_partial:
                labels.append(f"partial — {result.success_count}/{result.segment_count} segments")
            suffix = f" ({', '.join(labels)})" if labels else ""
            print(f"  Written to:  {output_path}{suffix}")
        else:
            print(f"  No output written: translation is empty.")
    else:
        if result.failed_segment_ids and result.success_count == 0:
            print(f"  No output written: all segments failed.")
        else:
            print(f"  No output written: chapter status is '{status_label}'.")

    # Manifest + resume guidance (consolidated)
    manifest_path = result.manifest.manifest_path if result.manifest else None
    if result.is_partial and manifest_path:
        completed = result.success_count
        pending_failed = result.segment_count - completed
        print(f"  Manifest:    {manifest_path}")
        print(f"  Next step:   run with --resume to continue")
        print(f"               (reuses {completed} completed segments; "
              f"processes {pending_failed} remaining segments, subject to retry limits)")
    elif result.resumable and manifest_path:
        # All segments failed — still resumable
        print(f"  Manifest:    {manifest_path}")
        print(f"  Next step:   run with --resume to retry all segments")
    elif manifest_path:
        # Completed or terminal — manifest is a run record
        print(f"  Manifest:    {manifest_path}")

    # Batch 3: consistency report — readable status summary
    audit = result.consistency_audit
    correction = result.correction_summary
    if audit:
        total = audit['total_issues']
        auto_fixed = audit['auto_fixed']
        if total == 0:
            print(f"  Consistency:     no issues found")
        elif auto_fixed == total:
            plural = "s" if total != 1 else ""
            print(f"  Consistency:     all resolved ({total} issue{plural} auto-fixed)")
        elif auto_fixed > 0:
            print(f"  Consistency:     {total} issues ({auto_fixed} auto-fixed)")
        else:
            print(f"  Consistency:     {total} issues found")
        if total > 0:
            for cat, count in sorted(audit['by_category'].items()):
                print(f"    {cat}: {count}")
        if correction and correction['total_corrections'] > 0:
            print(f"  Corrections:")
            for cat, count in sorted(correction['by_category'].items()):
                print(f"    {cat}: {count}")
        if result.corrected_translation is not None:
            print(f"  Corrected:       {len(result.corrected_translation)} chars (post-consistency)")

    # Strategy overview: display planned strategy from existing fields only.
    strategy = result.strategy_plan_summary
    if strategy:
        complexity = strategy.get("complexity", {})
        overall = strategy.get("overall_strategy", {})
        if complexity or overall:
            print(f"  Strategy:")
        if complexity:
            level = complexity.get("level", "—")
            score = complexity.get("score")
            mode = overall.get("processing_mode", "—") if overall else "—"
            line = f"    Complexity:   {level}"
            if score is not None:
                line += f" ({score:.2f})"
            line += f" · Mode: {mode}"
            print(line)
        if overall:
            seg = overall.get("segmentation_granularity", "—")
            budget = overall.get("budget_profile", "—")
            cons = overall.get("consistency_intensity", "—")
            print(f"    Segmentation: {seg} · {result.segment_count} segments · Budget: {budget}")
            print(f"    Consistency:  {cons}")

    if elapsed_seconds is not None:
        print(f"Elapsed: {elapsed_seconds:.1f}s")

    print("Done.")


def run_chapter_stream(
    source_path: Optional[Path] = None,
    service_url: Optional[str] = None,
    allow_mock_fallback: bool = False,
    assets_mode: AssetsMode = DEFAULT_ASSETS_MODE,
) -> None:
    """Stream chapter translation: read source, translate, output final text to stdout.

    If source_path is None, read from stdin.
    """
    _validate_assets_mode(assets_mode)

    # Read source text
    if source_path is not None:
        text = read_source_file(source_path)
    else:
        # Read from stdin
        text = sys.stdin.read()

    if not text.strip():
        sys.stderr.write("ERROR: source text cannot be empty.\n")
        sys.exit(1)

    # Resolve translation function (same logic as chapter pipeline)
    translate_fn, mode = _resolve_translate_fn(service_url, allow_mock_fallback, assets_mode)
    if translate_fn is None:
        sys.stderr.write("ERROR: Service unavailable and fallback not allowed.\n")
        sys.exit(1)

    # Run chapter translation
    try:
        orchestrator = ChapterOrchestrator()
        result = orchestrator.run_with_manifest(
            text,
            translate_draft_fn=translate_fn,
            assets_mode=assets_mode,
            manifest_path=None,  # No persistent manifest for stream mode
        )
    except Exception as e:
        sys.stderr.write(f"Chapter translation failed: {e}\n")
        sys.exit(1)

    # Output final translation text to stdout
    output_text = result.final_translation
    if output_text:
        sys.stdout.write(output_text + "\n")
    else:
        sys.stderr.write("ERROR: No translation output produced.\n")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Novel translation workbench MVP")
    subparsers = parser.add_subparsers(dest='command', required=True)

    run_parser = subparsers.add_parser('run', help='Run translation pipeline')
    # Optional arguments for input/output paths
    run_parser.add_argument('--source', type=Path, default=Path('data/source/chapter1.txt'),
                            help='Path to source text file')
    run_parser.add_argument('--output', type=Path, default=Path('data/exports/chapter1_en.md'),
                            help='Path to output markdown file')
    run_parser.add_argument('--service-url', type=str, default=None,
                            help='URL of translation service (e.g., http://localhost:8000). If not provided, use local mock.')
    run_parser.add_argument('--allow-mock-fallback', action='store_true',
                            help='If service fails, allow falling back to local mock translation.')
    run_parser.add_argument('--assets-mode', dest='assets_mode',
                            choices=list(ASSETS_MODES), default=DEFAULT_ASSETS_MODE,
                            help='Project-asset injection mode. "full" (default) injects '
                                 'the project memory block into translation prompts; "none" '
                                 'suppresses it entirely.')

    chapter_parser = subparsers.add_parser('chapter', help='Translate a full chapter (auto-segment -> auto-translate -> aggregate -> consistency)')
    chapter_sub = chapter_parser.add_subparsers(dest='chapter_command', required=True)
    chapter_run_parser = chapter_sub.add_parser('run', help='Run chapter-level translation pipeline')
    chapter_run_parser.add_argument('--source', type=Path, default=Path('data/source/chapter1.txt'),
                                    help='Path to full chapter source text file')
    chapter_run_parser.add_argument('--output', type=Path, default=Path('data/exports/chapter1_en.md'),
                                    help='Path to final chapter-level output file (post-consistency corrected when applicable)')
    chapter_run_parser.add_argument('--service-url', type=str, default=None,
                                    help='URL of translation service (e.g., http://localhost:8000). If not provided, use local mock.')
    chapter_run_parser.add_argument('--allow-mock-fallback', action='store_true',
                                    help='If service fails, allow falling back to local mock translation.')
    chapter_run_parser.add_argument('--assets-mode', dest='assets_mode',
                                    choices=list(ASSETS_MODES), default=DEFAULT_ASSETS_MODE,
                                    help='Project-asset injection mode. "full" (default) injects '
                                         'the project memory block into translation prompts; "none" '
                                         'suppresses it entirely.')
    # --resume and --dry-run are mutually exclusive
    resume_group = chapter_run_parser.add_mutually_exclusive_group()
    resume_group.add_argument('--resume', action='store_true',
                              help='Resume an incomplete chapter run from its saved manifest. '
                                   'Completed segments are reused; pending and failed segments '
                                   'are processed again subject to retry limits. The manifest '
                                   'file lives at <output>.manifest.json. Use this to continue '
                                   'a partial or interrupted chapter run.')
    resume_group.add_argument('--dry-run', action='store_true',
                              help='Preview the chapter plan and exit without translating. '
                                   'Shows segment count, complexity, and strategy decisions. '
                                   'Cannot be combined with --resume.')
    chapter_run_parser.add_argument('--max-retries', type=int, default=2,
                                    help='Maximum number of retry attempts per segment before marking it failed (default: 2).')
    chapter_run_parser.add_argument('--retry-delay-seconds', type=float, default=1.0,
                                    help='Base delay between retry attempts in seconds (default: 1.0).')
    chapter_run_parser.add_argument('--no-auto-retry-on-resume', action='store_false', dest='auto_retry_on_resume',
                                    help='Disable automatic retry of failed segments on resume (default: auto-retry enabled).')

    chapter_stream_parser = chapter_sub.add_parser('stream', help='Stream chapter translation: read source, translate, output final translation to stdout')
    chapter_stream_parser.add_argument('--source', type=Path, default=None,
                                       help='Path to full chapter source text file (if omitted, read from stdin)')
    chapter_stream_parser.add_argument('--service-url', type=str, default=None,
                                       help='URL of translation service (e.g., http://localhost:8000). If not provided, use local mock.')
    chapter_stream_parser.add_argument('--allow-mock-fallback', action='store_true',
                                       help='If service fails, allow falling back to local mock translation.')
    chapter_stream_parser.add_argument('--assets-mode', dest='assets_mode',
                                       choices=list(ASSETS_MODES), default=DEFAULT_ASSETS_MODE,
                                       help='Project-asset injection mode. "full" (default) injects '
                                            'the project memory block into translation prompts; "none" '
                                            'suppresses it entirely.')

    args = parser.parse_args()

    if args.command == 'run':
        # Ensure output directory exists
        args.output.parent.mkdir(parents=True, exist_ok=True)
        run_pipeline(
            args.source,
            args.output,
            args.service_url,
            args.allow_mock_fallback,
            assets_mode=args.assets_mode,
        )
    elif args.command == 'chapter':
        if args.chapter_command == 'run':
            run_chapter_pipeline(
                args.source,
                args.output,
                args.service_url,
                args.allow_mock_fallback,
                assets_mode=args.assets_mode,
                resume=args.resume,
                dry_run=args.dry_run,
                max_retries=args.max_retries,
                retry_delay_seconds=args.retry_delay_seconds,
                auto_retry_on_resume=args.auto_retry_on_resume,
            )
        elif args.chapter_command == 'stream':
            run_chapter_stream(
                source_path=args.source,
                service_url=args.service_url,
                allow_mock_fallback=args.allow_mock_fallback,
                assets_mode=args.assets_mode,
            )
    else:
        parser.print_help()


if __name__ == '__main__':
    main()